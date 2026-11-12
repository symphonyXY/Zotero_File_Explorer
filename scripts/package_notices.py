import hashlib
import importlib.metadata
import json
import shutil
import sys
from pathlib import Path

from zotero_file_explorer import __version__

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "build/release/ZoteroFileExplorer"
TARGET.mkdir(parents=True, exist_ok=True)
for name in ["LICENSE", "THIRD_PARTY_NOTICES.md", "README.md", "CONTRIBUTING.md", "SECURITY.md"]:
    shutil.copy2(ROOT / name, TARGET / name)
readme_icon = TARGET / "assets/icons/app.png"
readme_icon.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(ROOT / "assets/icons/app.png", readme_icon)
shutil.copytree(ROOT / "licenses", TARGET / "licenses", dirs_exist_ok=True)
shutil.copytree(
    ROOT / "docs",
    TARGET / "docs",
    dirs_exist_ok=True,
    ignore=shutil.ignore_patterns("evidence", "final-report.md", "cleanup.md"),
)
license_path = Path(sys.base_prefix) / "LICENSE.txt"
if license_path.exists():
    shutil.copy2(license_path, TARGET / "licenses/Python-LICENSE.txt")
versions = {}
for name in ["PySide6-Essentials", "shiboken6", "PyInstaller", "pyinstaller-hooks-contrib"]:
    dist = importlib.metadata.distribution(name)
    versions[name] = dist.version
    for path in dist.files or []:
        if "license" in str(path).lower() and dist.locate_file(path).is_file():
            target = TARGET / "licenses/wheel-notices" / name / Path(path).name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dist.locate_file(path), target)
(TARGET / "dependency-versions.json").write_text(json.dumps(versions, indent=2), encoding="utf-8")
sources = {
    str(p.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
    for directory in ["src", "installer", "scripts"]
    for p in (ROOT / directory).rglob("*")
    if p.is_file()
    and "__pycache__" not in p.parts
    and not any(part.endswith(".egg-info") for part in p.parts)
}
(ROOT / f"docs/evidence/build-sources-{__version__}.json").write_text(
    json.dumps(sources, indent=2), encoding="utf-8"
)
(TARGET / "build-sources.json").write_text(json.dumps(sources, indent=2), encoding="utf-8")
print("Bundled dependency notices and source hashes")
