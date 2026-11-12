import threading
import time

import pytest
from PySide6.QtCore import QThread, QThreadPool, QTimer
from PySide6.QtWidgets import QApplication

from zotero_file_explorer.app import Controller
from zotero_file_explorer.storage.config import ConfigStore
from zotero_file_explorer.storage.index import SearchFilter
from zotero_file_explorer.ui.workers import Task


def test_task_completion_runs_on_gui_thread(qapp, qtbot):
    main_thread = threading.get_ident()
    results = []
    pool = QThreadPool()
    task = Task(threading.get_ident)

    def done(result, error):
        results.append((result, error, threading.get_ident(), QThread.currentThread() == qapp.thread()))

    task.signals.finished.connect(done)
    pool.start(task)
    qtbot.waitUntil(lambda: bool(results))
    pool.waitForDone(1000)
    worker, error, callback, on_gui = results[0]
    assert error is None
    assert worker != main_thread
    assert callback == main_thread and on_gui


@pytest.fixture
def controller(qapp, qtbot, index):
    value = Controller(qapp, ConfigStore(index.directory), start_sync=False, register_hotkey=False)
    qtbot.addWidget(value.main)
    qtbot.addWidget(value.quick)
    value.show_main()
    qtbot.waitUntil(lambda: not value.tasks)
    yield value
    value.quitting = True
    value.cancel.set()
    value.poll.stop()
    value.tray.hide()
    value.pool.waitForDone(10000)
    qapp.processEvents()
    qapp.removeNativeEventFilter(value.hotkey)


def test_navigation_and_render_never_read_index_on_gui(controller, qtbot, monkeypatch):
    gui = threading.get_ident()
    for name in ["libraries", "collections", "active_instance"]:
        original = getattr(controller.index, name)

        def checked(*args, operation=original, **kwargs):
            assert threading.get_ident() != gui, "Blocking metadata read on the GUI thread"
            return operation(*args, **kwargs)

        monkeypatch.setattr(controller.index, name, checked)
    controller.main.reload_navigation()
    controller.main.query()
    qtbot.waitUntil(lambda: not controller.tasks)
    assert controller.main.view.model_data.rowCount() == 1


def test_manual_choice_does_not_wait_for_sync_lock(controller, qtbot):
    held, release = threading.Event(), threading.Event()

    def writer():
        with controller.index.lock:
            held.set()
            release.wait(2)

    thread = threading.Thread(target=writer)
    thread.start()
    assert held.wait(1)
    view = controller.main.view
    view.setCurrentIndex(view.model_data.index(0, 0))
    try:
        start = time.perf_counter()
        controller.file_action("primary", view)
        elapsed = time.perf_counter() - start
        assert elapsed < 0.2, f"UI waited {elapsed:.3f}s for the background writer"
        controller.main.search.setText("glover")
        qtbot.wait(50)
        assert controller.main.search.text() == "glover"
    finally:
        release.set()
        thread.join(3)
    qtbot.waitUntil(lambda: not controller.tasks)
    assert controller.index.override("server1", "user:0", "PAPER001")["primary"] == "ATTACH01"


def test_slow_file_validation_keeps_event_loop_alive(controller, qtbot, monkeypatch, qapp):
    release, started = threading.Event(), threading.Event()
    from zotero_file_explorer.services.paths import valid_file_paths

    def slow(paths):
        started.set()
        release.wait(2)
        return valid_file_paths(paths)

    monkeypatch.setattr("zotero_file_explorer.app.valid_file_paths", slow)
    monkeypatch.setattr("zotero_file_explorer.platform.files.valid_file_paths", slow)
    view = controller.main.view
    view.setCurrentIndex(view.model_data.index(0, 0))
    beats = []
    timer = QTimer()
    timer.timeout.connect(lambda: beats.append(time.perf_counter()))
    timer.start(10)
    try:
        start = time.perf_counter()
        controller.file_action("copy_files", view)
        assert time.perf_counter() - start < 0.2
        qtbot.waitUntil(started.is_set)
        qtbot.wait(100)
        assert len(beats) >= 3
    finally:
        release.set()
        timer.stop()
    qtbot.waitUntil(lambda: not controller.tasks)
    assert qapp.clipboard().mimeData().hasUrls()
    qapp.clipboard().clear()


def test_rapid_search_coalesces_stale_work(controller, qtbot, monkeypatch):
    release, started = threading.Event(), threading.Event()
    calls = []
    original = controller.index.search

    def slow(filters):
        calls.append(filters.text)
        started.set()
        release.wait(2)
        return original(filters)

    monkeypatch.setattr(controller.index, "search", slow)
    controller.search(controller.main, SearchFilter(text="first"))
    assert started.wait(1)
    try:
        for number in range(60):
            controller.search(controller.main, SearchFilter(text=str(number)))
        controller.search(controller.main, SearchFilter(text="glover"))
        assert len(controller.tasks) <= 1
    finally:
        release.set()
    qtbot.waitUntil(lambda: not controller.tasks)
    assert calls == ["first", "glover"]
    assert controller.main.view.model_data.rowCount() == 1


def test_quick_keyboard_navigation_and_pending_enter(controller, qtbot, monkeypatch):
    from PySide6.QtCore import Qt

    calls = []
    monkeypatch.setattr(controller, "file_action", lambda *args: calls.append(args))
    controller.show_quick()
    qtbot.waitUntil(lambda: not controller.tasks)
    quick = controller.quick
    qtbot.keyClick(quick.search, Qt.Key.Key_Down)
    assert quick.view.currentIndex().isValid()
    assert len(quick.view.selected_data()) == 1
    quick.search.setFocus()
    quick.search.setText("no matching result")
    qtbot.keyClick(quick.search, Qt.Key.Key_Return)
    assert not calls  # Never open the old result while a new query is pending.
    qtbot.waitUntil(lambda: quick.view.model_data.rowCount() == 0)
    quick.search.setText("glover")
    qtbot.waitUntil(lambda: quick.view.model_data.rowCount() == 1)
    # A failed query must not make the retained old result actionable via Enter.
    quick.generation += 1
    qtbot.keyClick(quick.search, Qt.Key.Key_Return)
    assert not calls


def test_startup_clicks_remain_responsive_during_api_timeout(controller, qtbot, monkeypatch):
    from zotero_file_explorer.api.client import APIError

    release, started = threading.Event(), threading.Event()

    def slow_api(*args, **kwargs):
        started.set()
        release.wait(2)
        raise APIError(0, "offline")

    monkeypatch.setattr("zotero_file_explorer.app.SyncService.synchronize", slow_api)
    controller.synchronize()
    assert started.wait(1)
    try:
        for _ in range(5):
            controller.main.search.setText("quantum")
            controller.main.query()
            controller.main.reload_navigation()
            controller.show_quick()
            controller.quick.hide()
        qtbot.waitUntil(lambda: controller.main.view.model_data.rowCount() == 1)
        assert controller.main.search.text() == "quantum"
        assert controller.syncing
    finally:
        release.set()
    qtbot.waitUntil(lambda: not controller.tasks)
    assert not controller.syncing
    assert controller.main.sync_button.isEnabled()
    assert controller.tr("offline") in controller.main.connection_label.text()


@pytest.mark.parametrize("held", [True, False])
def test_prepared_drag_uses_copy_only_and_requires_held_button(controller, qtbot, monkeypatch, held):
    from unittest.mock import patch

    from PySide6.QtCore import Qt

    view = controller.main.view
    view.setCurrentIndex(view.model_data.index(0, 0))
    monkeypatch.setattr(
        QApplication, "mouseButtons", lambda: Qt.MouseButton.LeftButton if held else Qt.MouseButton.NoButton
    )
    with patch("zotero_file_explorer.platform.files.QDrag") as drag:
        controller.file_action("drag", view)
        qtbot.waitUntil(lambda: not controller.tasks)
        if held:
            drag.return_value.exec.assert_called_once_with(Qt.DropAction.CopyAction, Qt.DropAction.CopyAction)
            mime = drag.return_value.setMimeData.call_args.args[0]
            assert mime.urls()[0].isLocalFile()
        else:
            drag.assert_not_called()


@pytest.mark.parametrize("window_name", ["main", "quick"])
def test_debounce_invalidates_inflight_results_and_all_file_actions(
    controller, qtbot, monkeypatch, qapp, window_name,
):
    window = getattr(controller, window_name)
    window.view.setCurrentIndex(window.view.model_data.index(0, 0))
    window.debounce.setInterval(1000)
    release, started = threading.Event(), threading.Event()
    original = controller.index.search

    def slow(filters):
        started.set()
        release.wait(2)
        return original(filters)

    monkeypatch.setattr(controller.index, "search", slow)
    controller.search(window, SearchFilter(text="quantum"))
    assert started.wait(1)
    previous_generation = window.displayed_generation
    try:
        window.search.setText("absent fixture")
        assert not window.results_ready
        release.set()
        qtbot.waitUntil(lambda: not controller.tasks)
        assert window.debounce.isActive()
        assert window.displayed_generation == previous_generation
        qapp.clipboard().setText("unchanged fixture")
        controller.file_action("copy_names", window.view)
        assert qapp.clipboard().text() == "unchanged fixture"
        window.query()
        qtbot.waitUntil(lambda: not controller.tasks)
        assert window.view.model_data.rowCount() == 0
        assert window.results_ready
    finally:
        release.set()
        window.debounce.stop()
        qapp.clipboard().clear()


def test_pending_page_cannot_skip_and_failed_page_can_retry(controller, qtbot, monkeypatch):
    from copy import deepcopy

    original_row = controller.index.search(SearchFilter())[0][0]
    release, started = threading.Event(), threading.Event()
    calls = []
    fail = [False]

    def pages(filters):
        calls.append(filters.offset)
        if filters.offset == 1:
            started.set()
            release.wait(2)
        if fail[0]:
            raise OSError("synthetic read failure")
        row = deepcopy(original_row)
        row["key"] = f"PAGE{filters.offset}"
        row["title"] = f"Page {filters.offset}"
        return [row], 3

    monkeypatch.setattr(controller.index, "search", pages)
    main = controller.main
    main.limit = 1
    main.query()
    qtbot.waitUntil(lambda: not controller.tasks)
    main.load_more()
    assert started.wait(1)
    try:
        main.load_more()
        main.load_previous()
        assert main.offset == 1
        assert not main.more.isEnabled() and not main.previous.isEnabled()
    finally:
        release.set()
    qtbot.waitUntil(lambda: not controller.tasks)
    assert calls == [0, 1]
    fail[0] = True
    main.load_more()
    qtbot.waitUntil(lambda: not controller.tasks)
    assert main.retry.isVisible() and not main.results_ready
    assert main.view.model_data.index(0, 0).data() == "Page 1"
    fail[0] = False
    main.retry.click()
    qtbot.waitUntil(lambda: not controller.tasks)
    assert main.results_ready and not main.retry.isVisible()
    assert main.view.model_data.index(0, 0).data() == "Page 2"


@pytest.mark.parametrize("remaining", [0, 1])
def test_index_shrink_recovers_valid_page(controller, qtbot, monkeypatch, remaining):
    row = controller.index.search(SearchFilter())[0][0]

    def pages(filters):
        return ([row] if filters.offset < remaining else []), remaining

    monkeypatch.setattr(controller.index, "search", pages)
    main = controller.main
    main.offset = 1000
    main.query()
    qtbot.waitUntil(lambda: not controller.tasks)
    assert main.offset == 0 and main.results_ready
    assert main.view.model_data.rowCount() == remaining
    assert not main.previous.isVisible()


def test_accessible_inputs_empty_state_and_selection_actions(controller, qtbot):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QInputMethodEvent

    main = controller.main
    assert main.search.accessibleName() == controller.tr("search_name")
    for widget, key in [(main.year, "year"), (main.tag, "tag"), (main.library, "library")]:
        assert widget.accessibleName() == controller.tr(key)
    assert not main.copy_button.isEnabled()
    main.view.setCurrentIndex(main.view.model_data.index(0, 0))
    assert main.copy_button.isEnabled()
    main.search.setText("absent fixture")
    assert not main.copy_button.isEnabled()
    qtbot.waitUntil(lambda: main.results_ready)
    assert main.empty_label.isVisible()
    assert abs(main.empty_label.geometry().center().y() - main.view.viewport().rect().center().y()) < 25
    main.search.clear()
    qtbot.waitUntil(lambda: main.results_ready)
    opened = []
    main.controller.file_action = lambda *args: opened.append(args)
    QApplication.sendEvent(main.search, QInputMethodEvent("拼音", []))
    qtbot.keyClick(main.search, Qt.Key.Key_Return)
    assert not opened
    QApplication.sendEvent(main.search, QInputMethodEvent("", []))
    qtbot.keyClick(main.search, Qt.Key.Key_Down)
    assert main.view.currentIndex().isValid()
    qtbot.keyClick(main.search, Qt.Key.Key_Return)
    assert len(opened) == 1


def test_quick_copy_receipt_survives_search_and_expires_in_place(controller, qtbot, monkeypatch, qapp):
    from zotero_file_explorer.services.paths import valid_file_paths

    release, started = threading.Event(), threading.Event()

    def slow(paths):
        started.set()
        release.wait(2)
        return valid_file_paths(paths)

    monkeypatch.setattr("zotero_file_explorer.app.valid_file_paths", slow)
    controller.main.hide()
    controller.show_quick()
    qtbot.waitUntil(lambda: controller.quick.results_ready)
    quick = controller.quick
    quick.view.setCurrentIndex(quick.view.model_data.index(0, 0))
    try:
        controller.file_action("copy_files", quick.view)
        qtbot.waitUntil(started.is_set)
        assert quick.operation_text == controller.tr("checking_files")
        assert not controller.main.operation_text
        quick.search.setText("glover")
        qtbot.waitUntil(lambda: quick.results_ready)
    finally:
        release.set()
    qtbot.waitUntil(lambda: not controller.tasks)
    assert quick.operation_text == controller.tr("copied", count=1)
    assert quick.operation_text in quick.search_status.text()
    assert not controller.main.isVisible()
    assert qapp.clipboard().mimeData().hasUrls()
    quick.operation_timer.start(1)
    qtbot.waitUntil(lambda: not quick.operation_text)
    assert quick.search_status.text() == controller.tr("counts", count=1, shown=1, selected=1)
    qapp.clipboard().clear()


def test_quick_copy_failure_is_visible_and_next_operation_replaces_it(controller, qtbot, monkeypatch):
    controller.show_quick()
    qtbot.waitUntil(lambda: controller.quick.results_ready)
    quick = controller.quick
    quick.view.setCurrentIndex(quick.view.model_data.index(0, 0))
    monkeypatch.setattr("zotero_file_explorer.app.valid_file_paths", lambda _: [])
    controller.file_action("copy_files", quick.view)
    qtbot.waitUntil(lambda: not controller.preparing_files)
    assert quick.operation_text == controller.tr("no_available_files")
    assert not quick.operation_timer.isActive()
    quick.query()
    qtbot.waitUntil(lambda: quick.results_ready)
    assert quick.operation_text in quick.search_status.text()
    quick.set_operation_feedback(controller.tr("checking_files"), timeout=0)
    assert controller.tr("no_available_files") not in quick.search_status.text()


def test_layout_roundtrip_and_reset_preserve_selection(controller, qtbot):
    from PySide6.QtCore import Qt

    from zotero_file_explorer.ui.windows import MainWindow

    main = controller.main
    view = main.view
    parent = view.model_data.index(0, 0)
    view.expand(parent)
    view.setCurrentIndex(view.model_data.index(1, 0, parent))
    selected = view.selected_attachments(True)
    # Qt clamps restored geometry to the screen; hosted Windows has a small display.
    available = main.screen().availableGeometry()
    main.resize(min(1380, available.width() - 64), min(840, available.height() - 96))
    main.splitter.setSizes([290, 1000])
    view.setColumnWidth(0, 470)
    view.setColumnWidth(1, 180)
    view.header().moveSection(view.header().visualIndex(8), 1)
    main.toggle_column(5, True)
    qtbot.wait(20)
    expected_sizes = main.splitter.sizes()
    main.hide()
    stored = controller.config.load()
    assert stored.window_layouts["main"]["auto_title"] is False
    assert stored.window_layouts["main"]["splitter"] == expected_sizes
    restored = MainWindow(controller)
    qtbot.addWidget(restored)
    restored.show()
    qtbot.waitExposed(restored)
    assert restored.size() == main.size()
    assert restored.view.columnWidth(0) == 470
    assert restored.view.columnWidth(1) == 180
    assert restored.view.header().visualIndex(8) == 1
    assert not restored.view.isColumnHidden(5)
    assert restored.view.header().sortIndicatorSection() == 0
    assert restored.view.header().sortIndicatorOrder() == Qt.SortOrder.AscendingOrder
    # Reset affects presentation only, including a selected child attachment.
    main.show()
    main.reset_layout()
    assert view.selected_attachments(True) == selected
    assert view.isExpanded(parent)
    assert view.auto_title_width
    assert all(view.isColumnHidden(c) for c in [3, 5, 6, 7])


@pytest.mark.parametrize("state", [None, [], {"geometry": "bad hex", "header": "00", "splitter": [-1, 0]}])
def test_invalid_optional_layout_does_not_break_window(controller, qtbot, state):
    from zotero_file_explorer.ui.windows import MainWindow

    controller.settings.window_layouts = {"main": state}
    main = MainWindow(controller)
    qtbot.addWidget(main)
    main.show()
    assert not main.view.isColumnHidden(0)
    assert main.width() >= main.minimumWidth()


def test_legacy_visible_columns_and_manual_title_width_are_preserved(controller, qtbot):
    from zotero_file_explorer.ui.windows import MainWindow

    controller.settings.hidden_columns = []
    main = MainWindow(controller)
    qtbot.addWidget(main)
    main.show()
    assert not any(main.view.isColumnHidden(c) for c in range(9))
    main.view.setColumnWidth(0, 190)
    main.display(*controller.index.search(main.filters()))
    assert main.view.columnWidth(0) == 190


def test_copy_receipt_routes_to_recreated_quick_window(controller, qtbot, monkeypatch):
    from PySide6.QtCore import QCoreApplication, QEvent

    from zotero_file_explorer.ui.windows import QuickWindow

    pending = []
    monkeypatch.setattr(controller, "submit", lambda work, done: pending.append((work, done)))
    # This temporary window is deliberately deleted; qtbot owns the fixture windows
    # until teardown and must not be asked to close an already deleted C++ object.
    old = QuickWindow(controller)
    controller.quick = old
    old.display(*controller.index.search(SearchFilter()))
    old.search_pending = False
    old.displayed_generation = old.generation
    old.view.setCurrentIndex(old.view.model_data.index(0, 0))
    controller.file_action("copy_files", old.view)
    controller.quick = QuickWindow(controller)
    qtbot.addWidget(controller.quick)
    old.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    work, done = pending[0]
    # Validation found no file: the error must appear on the surviving window.
    done([], None)
    assert controller.quick.operation_text == controller.tr("no_available_files")
    assert not controller.preparing_files
