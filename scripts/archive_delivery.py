import hashlib
import json
from pathlib import Path

from check_repository import audit_repository
from delivery_files import write_sources

from zotero_file_explorer import __version__

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
report = audit_repository(ROOT)
if report["errors"]:
    raise ValueError("Publication audit failed: " + "; ".join(report["errors"]))
source = DIST / f"source/ZoteroFileExplorer-{__version__}-Source.zip"
write_sources(source, __version__, (e["path"] for e in report["files"]), lambda n: (ROOT / n).read_bytes())
manifest = source.with_suffix(".manifest.json")
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
