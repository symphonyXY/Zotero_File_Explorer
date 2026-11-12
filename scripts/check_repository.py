"""Audit the current publication tree without staging files or rewriting history."""

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
from pathlib import Path

ROOT_FILES = {
    "README.md", "AGENTS.md", "CHANGELOG.md", "LICENSE", "THIRD_PARTY_NOTICES.md",
    "pyproject.toml", "requirements-dev.lock", ".gitignore", ".gitattributes",
    "CONTRIBUTING.md", "SECURITY.md",
}
ROOT_DIRS = {".github", "src", "assets", "config", "tests", "scripts", "installer", "docs", "licenses"}
BLOCKED_SUFFIXES = {
    ".exe", ".dll", ".zip", ".xz", ".whl", ".pdf", ".sqlite", ".sqlite3", ".db",
    ".pyc", ".pyo", ".log", ".pem", ".key",
}


def git_names(root, *arguments):
    result = subprocess.run(["git", "-C", str(root), *arguments], check=True, capture_output=True)
    return {os.fsdecode(name).replace("\\", "/") for name in result.stdout.split(b"\0") if name}


def audit_repository(root):
    root = Path(root).absolute()
    names = git_names(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    ignored_tracked = git_names(root, "ls-files", "-z", "-ci", "--exclude-standard")
    errors = [f"Tracked ignored file: {name}" for name in sorted(ignored_tracked)]
    files = []
    home = str(Path.home())
    private_markers = [home, home.replace("\\", "/"), home.replace("\\", "\\\\")]
    for name in sorted(names):
        path = root / name
        if not path.exists() and not path.is_symlink():
            continue  # Respect working-tree deletions without changing the index.
        try:
            if not path.is_relative_to(root) or ".." in path.parts:
                raise ValueError("Outside publication boundary")
            for parent in [path, *path.parents]:
                info = parent.lstat()
                if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                    raise ValueError("Link/reparse point")
                if parent == root:
                    break
            if not path.is_file():
                raise ValueError("Not a regular publication file")
            relative = path.relative_to(root)
            release_metadata = (
                relative.parts[0] == "releases" and path.name in {"README.md", "SHA256SUMS.txt"}
            )
            if name not in ROOT_FILES and relative.parts[0] not in ROOT_DIRS and not release_metadata:
                raise ValueError("Outside documented source tree")
            if (path.suffix.lower() in BLOCKED_SUFFIXES or "__pycache__" in relative.parts
                    or any(part.endswith(".egg-info") for part in relative.parts)
                    or path.name.lower().startswith(".env")
                    or (name.startswith("docs/evidence/") and "private" in path.name.lower())):
                raise ValueError("Runtime data, credential or delivery file")
            content = path.read_bytes()
            if len(content) > 20 * 1024 * 1024:
                raise ValueError("Oversized source file; review separately")
            if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".ico"}:
                text = content.decode("utf-8", errors="replace")
                if any(marker in text for marker in private_markers):
                    raise ValueError("Personal home path; redact public evidence")
                if re.search(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", text):
                    raise ValueError("Private key material")
            files.append({"path": name, "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()})
        except (OSError, ValueError) as error:
            errors.append(f"{name}: {error}")
    return {"files": files, "errors": errors, "total_bytes": sum(entry["bytes"] for entry in files)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit_repository(Path(__file__).absolute().parents[1])
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"files": len(report["files"]), "bytes": report["total_bytes"],
                      "errors": report["errors"]}, indent=2))
    raise SystemExit(bool(report["errors"]))


if __name__ == "__main__":
    main()
