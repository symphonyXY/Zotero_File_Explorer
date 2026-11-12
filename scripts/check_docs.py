"""Check repository Markdown relative links and GitHub-style local heading anchors.

Scope: root Markdown, docs, release metadata and tests/fixtures. External URLs are not fetched.
Supports inline links/images and full/collapsed reference links; fenced code is ignored.
"""

import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
INLINE = re.compile(r"!?\[[^\]\n]*\]\((<[^>]+>|[^\s()]*(?:\([^)]*\)[^\s()]*)*)(?:\s+\"[^\"]*\")?\)")
REFERENCE = re.compile(r"^ {0,3}\[([^\]]+)\]:\s*<?([^\s>]+)>?", re.MULTILINE)


def prose(text: str) -> str:
    lines = []
    fence = ""
    for line in text.splitlines():
        match = re.match(r"^\s*(`{3,}|~{3,})", line)
        if match:
            mark = match[1]
            if not fence:
                fence = mark
            elif mark[0] == fence[0] and len(mark) >= len(fence):
                fence = ""
            continue
        if not fence:
            lines.append(line)
    return "\n".join(lines)


def anchors(text: str) -> set[str]:
    result = set()
    for match in re.finditer(r"^ {0,3}#{1,6}\s+(.+?)(?:\s+#+)?$", prose(text), re.MULTILINE):
        heading = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", match[1])
        heading = re.sub(r"<[^>]+>", "", heading).lower()
        slug = "".join(c for c in heading if c.isalnum() or c in "_- ").replace(" ", "-")
        name = slug
        index = 0
        while name in result:
            index += 1
            name = f"{slug}-{index}"
        result.add(name)
    result.update(re.findall(r'<(?:a|h[1-6])[^>]+(?:id|name)=[\"\x27]([^\"\x27]+)', text))
    return result


def check_file(root: Path, path: Path) -> tuple[int, list[str]]:
    body = prose(path.read_text(encoding="utf-8-sig"))
    # Remove inline code so literal Markdown examples are not treated as links.
    body = re.sub(r"`+[^`\n]*`+", "", body)
    targets = [m[1].strip("<>") for m in INLINE.finditer(body)]
    definitions = {m[1].casefold(): m[2] for m in REFERENCE.finditer(body)}
    errors = []
    for match in re.finditer(r"!?\[([^\]\n]+)\]\[([^\]\n]*)\]", body):
        label = (match[2] or match[1]).casefold()
        if label not in definitions:
            errors.append(f"{path.relative_to(root)}: undefined reference [{label}]")
        else:
            targets.append(definitions[label])
    targets.extend(definitions.values())
    count = 0
    for target in targets:
        parts = urlsplit(target)
        if parts.scheme in {"https", "http", "mailto"}:
            continue
        count += 1
        if parts.scheme or parts.netloc or target.startswith(("/", "\\")):
            errors.append(f"{path.relative_to(root)}: expected relative link: {target}")
            continue
        destination = (path.parent / unquote(parts.path)).resolve() if parts.path else path
        if not destination.is_relative_to(root) or not destination.exists():
            errors.append(f"{path.relative_to(root)}: missing/outside target: {target}")
        elif parts.fragment and destination.suffix.lower() == ".md":
            if unquote(parts.fragment) not in anchors(destination.read_text(encoding="utf-8-sig")):
                errors.append(f"{path.relative_to(root)}: missing anchor: {target}")
    return count, errors


def main() -> None:
    files = sorted(set(ROOT.glob("*.md")) | set((ROOT / "releases").glob("README.md"))
                   | set((ROOT / "releases").glob("v*/README.md")) | {
        p for base in ("docs", "tests/fixtures") for p in (ROOT / base).rglob("*.md")
        if not p.is_symlink()
    })
    checked = 0
    errors = []
    for path in files:
        count, failures = check_file(ROOT, path)
        checked += count
        errors.extend(failures)
    for error in errors:
        print(error)
    print(f"Checked {len(files)} Markdown files, {checked} local links; {len(errors)} errors.")
    raise SystemExit(bool(errors))


if __name__ == "__main__":
    main()
