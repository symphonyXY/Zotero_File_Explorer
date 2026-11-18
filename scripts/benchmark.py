"""Measured synthetic metadata benchmarks; no real attachments are duplicated."""

import argparse
import json
import platform
import statistics
import sys
import threading
import time
from pathlib import Path

import psutil
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from zotero_file_explorer.core.models import Library, Record
from zotero_file_explorer.i18n.strings import Translator
from zotero_file_explorer.storage.index import Index, SearchFilter
from zotero_file_explorer.ui.paper_view import PaperView

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, default=root / "build/performance-current.json")
args = parser.parse_args()
app = QApplication([])
report = {
    "platform": platform.platform(),
    "python": sys.version,
    "cpu": platform.processor(),
    "ram_gb": round(psutil.virtual_memory().total / 1024**3, 1),
    "samples": [],
}
library = Library("user:0", "personal", "users/0")
for count in [500, 5000, 20000]:
    directory = root / "build/benchmarks" / str(count)
    directory.mkdir(parents=True, exist_ok=True)
    file = directory / "synthetic 中文 paper.pdf"
    file.write_bytes(b"%PDF fixture (not a real paper)")
    index = Index(directory / "appdata")
    index.rebuild()
    records = {}
    for n in range(count):
        parent, child = f"P{n:07d}", f"A{n:07d}"
        records[parent] = Record(
            parent,
            "journalArticle",
            title=f"Quantum optimization 中文 电路 {n}",
            authors=f"Author {n % 100}",
            year=str(2000 + n % 26),
            tags=["Ising", f"Tag{n % 10}"],
            collections=[f"C{n % 20:07d}"],
        )
        records[child] = Record(
            child, "attachment", parent=parent, filename=file.name, path=str(file), link_mode="linked_file"
        )
    start = time.perf_counter()
    index.replace_snapshot("benchmark", [(library, records, [], 1)], [])
    index_seconds = time.perf_counter() - start
    start = time.perf_counter()
    reopened = Index(directory / "appdata")
    rows, total = reopened.search(SearchFilter())
    startup_seconds = time.perf_counter() - start
    timings = []
    for n in range(20):
        start = time.perf_counter()
        reopened.search(SearchFilter(text=f"中文 author {n}", available=True))
        timings.append((time.perf_counter() - start) * 1000)
    start = time.perf_counter()
    reopened.search(SearchFilter(collection="C0000003"))
    collection_ms = (time.perf_counter() - start) * 1000
    view = PaperView(Translator())
    start = time.perf_counter()
    view.populate(rows, {"user:0": "personal"})
    app.processEvents()
    render_ms = (time.perf_counter() - start) * 1000
    heartbeats = []
    timer = QTimer()
    timer.setInterval(10)
    timer.timeout.connect(lambda samples=heartbeats: samples.append(time.perf_counter()))
    timer.start()
    error = []

    def background(index=index, records=records, error=error):
        try:
            index.replace_snapshot("benchmark", [(library, records, [], 2)], [])
        except Exception as exc:
            error.append(type(exc).__name__)

    thread = threading.Thread(target=background)
    loop = QEventLoop()
    done = QTimer()
    done.setInterval(20)
    done.timeout.connect(lambda thread=thread, loop=loop: None if thread.is_alive() else loop.quit())
    thread.start()
    done.start()
    loop.exec()
    thread.join()
    timer.stop()
    done.stop()
    assert not error and total == count
    entry = {
        "papers": count,
        "index_seconds": index_seconds,
        "reopen_and_first_page_seconds": startup_seconds,
        "search_median_ms": statistics.median(timings),
        "search_p95_ms": sorted(timings)[18],
        "collection_ms": collection_ms,
        "render_first_500_ms": render_ms,
        "process_rss_mb": psutil.Process().memory_info().rss / 1024**2,
        "background_gui_heartbeat_max_gap_ms": max(
            (b - a) * 1000 for a, b in zip(heartbeats, heartbeats[1:], strict=False)
        ),
        "background_gui_heartbeat_samples": len(heartbeats),
        "search_mode": "normalized substring AND",
    }
    report["samples"].append(entry)
    print(json.dumps(entry), flush=True)
    view.deleteLater()
    app.processEvents()
    del records
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
