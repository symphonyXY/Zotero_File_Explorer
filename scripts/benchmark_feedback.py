"""Synthetic Widgets feedback timings; CPU paint/event loop, never display FPS."""

import argparse
import json
import platform
import statistics
import sys
import time
from pathlib import Path

import psutil
from PySide6 import __version__ as pyside_version
from PySide6.QtCore import QAbstractAnimation, QEventLoop, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QTreeView

from zotero_file_explorer.app import Controller
from zotero_file_explorer.core.models import Library, Record
from zotero_file_explorer.storage.config import ConfigStore, Settings
from zotero_file_explorer.storage.index import Index
from zotero_file_explorer.ui.paper_view import PaperView


def pump(milliseconds):
    loop = QEventLoop()
    QTimer.singleShot(milliseconds, loop.quit)
    loop.exec()


def wait_idle(controller):
    deadline = time.perf_counter() + 15
    while (controller.tasks or controller.main.debounce.isActive()) and time.perf_counter() < deadline:
        pump(5)
    if controller.tasks or controller.main.debounce.isActive():
        raise TimeoutError("Synthetic search did not finish")


def stats(values):
    ordered = sorted(values)
    return {
        "samples": len(values),
        "median_ms": statistics.median(values),
        "p95_ms": ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))],
        "max_ms": max(values),
    } if values else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True, help="New isolated benchmark directory")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    # Exclusive creation protects previous runs and user files from replacement.
    args.data_dir.mkdir(parents=True, exist_ok=False)
    if args.output.exists():
        raise FileExistsError(args.output)
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    paints = []
    original_paint = PaperView.paintEvent

    def paint(view, event):
        start = time.perf_counter()
        QTreeView.paintEvent(view, event)
        paints.append((time.perf_counter() - start) * 1000)

    PaperView.paintEvent = paint
    report = {
        "measurement": "Visible Widgets CPU paint and event loop; compositor/display FPS unmeasured",
        "platform": platform.platform(),
        "cpu": platform.processor(),
        "ram_gb": round(psutil.virtual_memory().total / 1024**3, 1),
        "python": sys.version,
        "pyside": pyside_version,
        "samples": [],
    }
    attachment = args.data_dir / "synthetic 中文 paper.pdf"
    attachment.write_bytes(b"%PDF synthetic feedback fixture")
    for count in (500, 5000, 20000):
        store = ConfigStore(args.data_dir / str(count))
        store.save(Settings(motion="full"))
        index = Index(store.directory)
        library = Library("user:0", "personal", "users/0")
        records = {}
        for n in range(count):
            key = f"P{n:07d}"
            records[key] = Record(key, "journalArticle", title=f"Quantum 中文 paper {n}")
            records[f"A{n:07d}"] = Record(
                f"A{n:07d}", "attachment", parent=key, filename=attachment.name,
                path=str(attachment), link_mode="linked_file",
            )
        index.replace_snapshot("feedback-benchmark", [(library, records, [], 1)], [])
        controller = Controller(app, store, start_sync=False, register_hotkey=False)
        controller.show_main()
        wait_idle(controller)
        pump(250)
        view = controller.main.view
        rows = index.search(controller.main.filters())[0]
        # Measure model population separately from event dispatch and paints.
        model_view = PaperView(controller.tr)
        start = time.perf_counter()
        model_view.populate(rows, {})
        population_ms = (time.perf_counter() - start) * 1000
        paints.clear()
        beats = []
        timer = QTimer()
        timer.timeout.connect(lambda values=beats: values.append(time.perf_counter()))
        timer.start(10)
        for n in range(60):
            row = view.model_data.index(n % 12, 0)
            QTest.mouseMove(view.viewport(), view.visualRect(row).center())
            if n % 10 == 0:
                view.expand(row)
                view.collapse(row)
            pump(8)
        for term in ("paper 1", "absent-fixture", "", "paper 2", ""):
            controller.main.search.setText(term)
            wait_idle(controller)
        timer.stop()
        gaps = [(b - a) * 1000 for a, b in zip(beats, beats[1:], strict=False)]
        for _ in range(30):
            controller.quick.show()
            pump(2)
            controller.quick.hide()
            assert controller.quick.windowOpacity() == 1
        sample = {
            "papers": count, "visible_page": view.model_data.rowCount(),
            "model_population_ms": population_ms, "paint": stats(paints),
            "event_loop": stats(gaps),
            "animation_objects": len(controller.main.findChildren(QAbstractAnimation)),
            "system_animations_enabled": controller.motion.policy.system_enabled,
        }
        report["samples"].append(sample)
        print(json.dumps(sample), flush=True)
        model_view.deleteLater()
        controller.quitting = True
        controller.cancel.set()
        controller.poll.stop()
        controller.main.hide()
        controller.quick.hide()
        controller.tray.hide()
        controller.pool.waitForDone(10000)
        app.removeNativeEventFilter(controller.hotkey)
        app.removeEventFilter(controller.motion)
        controller.main.deleteLater()
        controller.quick.deleteLater()
        controller.deleteLater()
        pump(10)
    PaperView.paintEvent = original_paint
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)


if __name__ == "__main__":
    main()
