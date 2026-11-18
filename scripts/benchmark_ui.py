"""Visible Widgets paint/interaction probe, using only synthetic benchmark indexes.

Run benchmark.py first. These are CPU paint and event-loop timings, NOT display FPS.
"""

import json
import statistics
import time
from dataclasses import replace
from pathlib import Path

import psutil
from PySide6.QtCore import QEvent, QEventLoop, QTimer
from PySide6.QtWidgets import QApplication, QTreeView

from zotero_file_explorer.app import Controller
from zotero_file_explorer.storage.config import ConfigStore
from zotero_file_explorer.storage.index import SearchFilter
from zotero_file_explorer.ui.dialogs import RulesDialog, SettingsDialog
from zotero_file_explorer.ui.paper_view import PaperView
from zotero_file_explorer.ui.theme import apply_theme
from zotero_file_explorer.ui.windows import MainWindow, QuickWindow

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "build/benchmark-ui"
EVIDENCE.mkdir(parents=True, exist_ok=True)
app = QApplication([])
app.setQuitOnLastWindowClosed(False)
paint_ms, paint_stamps = [], []


def paint(view, event):
    start = time.perf_counter()
    QTreeView.paintEvent(view, event)
    paint_ms.append((time.perf_counter() - start) * 1000)
    paint_stamps.append(time.perf_counter())


PaperView.paintEvent = paint


def pump(milliseconds):
    loop = QEventLoop()
    QTimer.singleShot(milliseconds, loop.quit)
    loop.exec()


def wait_idle(controller):
    deadline = time.perf_counter() + 15
    while controller.tasks and time.perf_counter() < deadline:
        pump(10)
    assert not controller.tasks


def stats(values):
    ordered = sorted(values)
    return {
        "count": len(values),
        "median_ms": statistics.median(values),
        "p95_ms": ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))],
        "max_ms": max(values),
    }


report = {
    "measurement": "Visible raster Widgets CPU paint, not compositor/present/display FPS",
    "screen_hz_reported": app.primaryScreen().refreshRate(),
    "samples": [],
}
for count in (500, 5000, 20000):
    controller = Controller(
        app, ConfigStore(ROOT / f"build/benchmarks/{count}/appdata"), start_sync=False, register_hotkey=False
    )
    controller.show_main()
    wait_idle(controller)
    pump(250)
    view = controller.main.view
    assert controller.main.total == count and view.model_data.rowCount() == 500
    assert controller.quick.view.model_data.rowCount() == 200
    paint_ms.clear()
    paint_stamps.clear()
    beats, interactions, expand_timings, scroll_timings = [], [], [], []
    frame = [0]

    def tick(
        beats=beats,
        frame=frame,
        view=view,
        interactions=interactions,
        expand_timings=expand_timings,
        scroll_timings=scroll_timings,
    ):
        beats.append(time.perf_counter())
        n = frame[0]
        frame[0] += 1
        start = time.perf_counter()
        view.verticalScrollBar().setValue((n * 73) % max(1, view.verticalScrollBar().maximum()))
        scroll_timings.append((time.perf_counter() - start) * 1000)
        if n % 20 == 0:
            idx = view.indexAt(view.viewport().rect().center()).siblingAtColumn(0)
            start = time.perf_counter()
            view.setExpanded(idx, not view.isExpanded(idx))
            expand_timings.append((time.perf_counter() - start) * 1000)
        if n % 60 == 0:
            start = time.perf_counter()
            apply_theme(app, "dark" if n % 120 == 0 else "light")
            interactions.append((time.perf_counter() - start) * 1000)

    timer = QTimer()
    timer.setInterval(16)
    timer.timeout.connect(tick)
    timer.start()
    pump(2200)
    timer.stop()
    scroll_stats = stats(paint_ms)
    gaps = [(b - a) * 1000 for a, b in zip(beats, beats[1:], strict=False)]
    quick_search = []
    for term in ["中文 author 3", "quantum", "no-synthetic-match", ""]:
        start = time.perf_counter()
        controller.search(controller.quick, SearchFilter(text=term, limit=200))
        wait_idle(controller)
        quick_search.append((time.perf_counter() - start) * 1000)
    for _ in range(10):
        controller.show_quick()
        pump(10)
        controller.quick.hide()
        assert controller.quick.windowOpacity() == 1
    wait_idle(controller)
    # Actual async writer work while both windows continue to accept interaction.
    start = time.perf_counter()
    controller.reclassify()
    timer.start()
    wait_idle(controller)
    timer.stop()
    reclassify_ms = (time.perf_counter() - start) * 1000
    if count == 20000:
        for lang, theme in [("zh_CN", "light"), ("en", "dark")]:
            controller.tr.language = lang
            controller.main.hide()
            controller.quick.hide()
            controller.main.deleteLater()
            controller.quick.deleteLater()
            controller.main = MainWindow(controller)
            controller.main.connection_label.setText(controller.tr("offline"))
            controller.quick = QuickWindow(controller)
            view = controller.main.view
            apply_theme(app, theme)
            controller.show_main()
            controller.main.query()
            wait_idle(controller)
            view.verticalScrollBar().setValue(0)
            pump(260)
            controller.main.grab().save(str(EVIDENCE / f"motion-main-{lang}-{theme}.png"))
            controller.show_quick()
            wait_idle(controller)
            pump(260)
            controller.quick.grab().save(str(EVIDENCE / f"motion-quick-{lang}-{theme}.png"))
            controller.quick.hide()
            dialog = SettingsDialog(
                replace(controller.settings, language=lang), controller.tr, controller.main
            )
            dialog.show()
            pump(260)
            dialog.grab().save(str(EVIDENCE / f"motion-settings-{lang}-{theme}.png"))
            dialog.close()
            dialog.deleteLater()
        rules = RulesDialog(controller.settings, controller.tr, controller.main)
        rules.show()
        pump(250)
        rules.grab().save(str(EVIDENCE / "motion-rules-en-dark.png"))
        rules.close()
        rules.deleteLater()
        # Warm-up then bounded 300-cycle lifetime exercise; not a long-duration leak proof.
        pump(50)
        before = psutil.Process().memory_info().rss
        for _ in range(300):
            controller.quick.show()
            controller.quick.hide()
            app.processEvents()
        pump(250)
        report["quick_300_cycles_rss_delta_mb"] = (psutil.Process().memory_info().rss - before) / 1024**2
    sample = {
        "papers": count,
        "expand_call": stats(expand_timings),
        "scroll_call": stats(scroll_timings),
        "paint": scroll_stats,
        "scroll_event_loop": stats(gaps),
        "theme_change": stats(interactions),
        "quick_search_roundtrip": stats(quick_search),
        "background_reclassification_ms": reclassify_ms,
        "rss_mb": psutil.Process().memory_info().rss / 1024**2,
        "motion_system_enabled": controller.motion.policy.system_enabled,
    }
    report["samples"].append(sample)
    print(json.dumps(sample), flush=True)
    controller.quitting = True
    controller.main.hide()
    controller.quick.hide()
    controller.tray.hide()
    app.removeNativeEventFilter(controller.hotkey)
    app.removeEventFilter(controller.motion)
    controller.main.deleteLater()
    controller.quick.deleteLater()
    controller.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)

(EVIDENCE / "performance-ui-motion.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
