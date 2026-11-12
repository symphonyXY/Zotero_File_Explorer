import hashlib
import json
import zipfile
from pathlib import Path

from check_repository import audit_repository

from zotero_file_explorer import __version__

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
report = audit_repository(ROOT)
if report["errors"]:
    raise ValueError("Publication audit failed: " + "; ".join(report["errors"]))
# A per-release checksum includes this ZIP's hash; do not put it back in the ZIP.
report["files"] = [
    entry for entry in report["files"]
    if not (entry["path"].startswith("releases/v") and entry["path"].endswith("/SHA256SUMS.txt"))
]
report["total_bytes"] = sum(entry["bytes"] for entry in report["files"])
source = DIST / f"source/ZoteroFileExplorer-{__version__}-Source.zip"
source.parent.mkdir(parents=True, exist_ok=True)
temporary = source.with_suffix(".zip.tmp")
with zipfile.ZipFile(temporary, "x", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
    for entry in report["files"]:
        archive.write(ROOT / entry["path"], entry["path"])
for path in [temporary]:
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == {entry["path"] for entry in report["files"]}
        for entry in report["files"]:
            assert hashlib.sha256(archive.read(entry["path"])).hexdigest() == entry["sha256"]
temporary.replace(source)
manifest = source.with_suffix(".manifest.json")
manifest.write_text(json.dumps(report, indent=2), encoding="utf-8")
checksums = {
    str(p.relative_to(DIST)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
    for p in DIST.rglob("*")
    if p.is_file() and p.name not in {"SHA256SUMS.txt", "delivery.json"}
}
(DIST / "SHA256SUMS.txt").write_text(
    "".join(f"{sha}  {name}\n" for name, sha in sorted(checksums.items())), encoding="utf-8"
)
(DIST / "delivery.json").write_text(
    json.dumps(
        {"version": __version__, "status": "local release; see documented validation limits",
         "source_snapshot_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(), "sha256": checksums},
        indent=2,
    ),
    encoding="utf-8",
)
print(json.dumps({p.name: p.stat().st_size for p in DIST.iterdir() if p.is_file()}, indent=2))
