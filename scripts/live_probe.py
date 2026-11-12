"""Read-only acceptance; stores only aggregate evidence outside the private index."""

import argparse
import json
import platform
import time
from pathlib import Path

from zotero_file_explorer.api.client import LocalAPI
from zotero_file_explorer.services.paths import detected_directories
from zotero_file_explorer.services.sync import SyncService
from zotero_file_explorer.storage.config import Settings
from zotero_file_explorer.storage.index import Index, SearchFilter

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, default=root / "docs/evidence/live-zotero-current.json")
args = parser.parse_args()
directories, base = detected_directories()
settings = Settings(data_directory=directories[0] if directories else "", attachment_base=base)
index = Index(root / "build/live-probe")
api = LocalAPI()
probe = api.probe()
start = time.perf_counter()
result = SyncService(index, settings, api).synchronize(progress=lambda value: print(value, flush=True))
elapsed = time.perf_counter() - start
rows, count = index.search(SearchFilter(limit=5000))
_, translations = index.search(SearchFilter(mode="translated"))
_, reviews = index.search(SearchFilter(mode="review"))
_, errors = index.search(SearchFilter(mode="errors"))
glover = [a for row in rows for a in row["attachments"] if a["key"] in {"MQ4LNIWG", "LVA27WQM"}]
result.pop("instance")
report = {
    "zotero_version": probe.headers.get("x-zotero-version"),
    "platform": platform.platform(),
    "server_id_present": bool(api.server_id),
    "detected_data_directory": bool(directories),
    "sync": result,
    "seconds": elapsed,
    "original_papers": count,
    "papers_with_translations": translations,
    "papers_needing_review": reviews,
    "papers_with_unavailable_files": errors,
    "collections": len(index.collections()),
    "glover": [{k: a[k] for k in ["key", "filename", "state", "reason", "status", "size"]} for a in glover],
    "offline_reopen_papers": Index(index.directory).search(SearchFilter())[1],
    "writes_to_zotero": 0,
}
args.output.write_text(
    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(json.dumps(report, ensure_ascii=False, indent=2))
