import ctypes
import sys
from unittest.mock import patch

import pytest
from PySide6.QtCore import QItemSelectionModel, Qt

from zotero_file_explorer.app import Controller
from zotero_file_explorer.i18n.strings import CATALOG, Translator
from zotero_file_explorer.platform.files import copy_files, drag_files, file_mime_data
from zotero_file_explorer.platform.windows import parse_hotkey
from zotero_file_explorer.storage.config import ConfigStore, Settings
from zotero_file_explorer.storage.index import SearchFilter
from zotero_file_explorer.ui.dialogs import RulesDialog, SettingsDialog
from zotero_file_explorer.ui.paper_view import ROLE, PaperView
from zotero_file_explorer.ui.theme import apply_theme


def test_real_urls_multiselect_missing(qapp, tmp_path):
    paths = [tmp_path / "中文 文件.pdf", tmp_path / "Supplement space.docx"]
    for path in paths:
        path.write_bytes(b"fixture")
    mime = file_mime_data([str(p) for p in paths] + [str(paths[0]), str(tmp_path / "missing.pdf")])
    assert [url.toLocalFile() for url in mime.urls()] == [str(p).replace("\\", "/") for p in paths]
    assert mime.hasUrls()
    assert (
        bytes(mime.data('application/x-qt-windows-mime;value="Preferred DropEffect"')) == b"\x01\x00\x00\x00"
    )
    with pytest.raises(ValueError):
        file_mime_data([str(tmp_path / "missing.pdf")])


@pytest.mark.windows
@pytest.mark.skipif(sys.platform != "win32", reason="Windows clipboard")
def test_windows_clipboard_cf_hdrop(qapp, tmp_path):
    paths = [tmp_path / "中文 原件.pdf", tmp_path / "another file.docx"]
    for path in paths:
        path.write_bytes(b"fixture")
    assert copy_files([str(p) for p in paths]) == 2
    qapp.processEvents()
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    user32.OpenClipboard.argtypes = [ctypes.c_void_p]
    user32.GetClipboardData.argtypes = [ctypes.c_uint]
    user32.GetClipboardData.restype = ctypes.c_void_p
    shell32.DragQueryFileW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_wchar_p, ctypes.c_uint]
    shell32.DragQueryFileW.restype = ctypes.c_uint
    assert user32.OpenClipboard(None)
    try:
        assert user32.IsClipboardFormatAvailable(15)  # CF_HDROP, a real native file list
        handle = user32.GetClipboardData(15)
        assert handle
        count = shell32.DragQueryFileW(handle, 0xFFFFFFFF, None, 0)
        received = []
        for number in range(count):
            size = shell32.DragQueryFileW(handle, number, None, 0)
            buffer = ctypes.create_unicode_buffer(size + 1)
            shell32.DragQueryFileW(handle, number, buffer, size + 1)
            received.append(buffer.value)
        assert received == [str(p) for p in paths]
    finally:
        user32.CloseClipboard()
    assert all(p.exists() for p in paths)
    qapp.clipboard().clear()


def test_drag_offers_copy_only(qapp, tmp_path):
    path = tmp_path / "paper.pdf"
    path.write_bytes(b"fixture")
    view = PaperView(Translator())
    with patch("zotero_file_explorer.platform.files.QDrag") as drag:
        drag_files(view, [str(path)])
        drag.return_value.exec.assert_called_once_with(Qt.DropAction.CopyAction, Qt.DropAction.CopyAction)
    assert path.exists()


def test_view_paper_children_and_selection(qtbot, index):
    view = PaperView(Translator())
    qtbot.addWidget(view)
    view.populate(index.search(SearchFilter())[0], {"user:0": "Personal"})
    parent = view.model_data.index(0, 0)
    assert view.model_data.rowCount(parent) == 2  # translations hidden
    view.selectionModel().select(
        parent, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows
    )
    assert len(view.selected_attachments(True)) == 1
    view.selectionModel().select(
        view.model_data.index(1, 0, parent),
        QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows,
    )
    assert len(view.selected_attachments(True)) == 2
    view.populate(index.search(SearchFilter())[0], {})
    assert len(view.selected_attachments(True)) == 2
    view.populate(index.search(SearchFilter(mode="translated"))[0], {}, "translated")
    assert view.model_data.rowCount(view.model_data.index(0, 0)) == 1
    assert (
        view.model_data.index(0, 0, view.model_data.index(0, 0)).data(ROLE)["attachment"]["state"]
        == "translated"
    )


def test_rules_editor_and_settings(qtbot):
    tr = Translator()
    dialog = RulesDialog(Settings(), tr)
    qtbot.addWidget(dialog)
    dialog.add_rule({"name": "custom", "pattern": "*.translated.pdf", "state": "translated"})
    dialog.sample_file.setText("test.translated.pdf")
    dialog.test_rules()
    assert "custom" in dialog.preview.text()
    assert len(dialog.rules()) == 1
    dialog.remove_rule()  # no selection is harmless
    dialog.restore_defaults()
    assert dialog.rules() == []
    settings = SettingsDialog(Settings(), tr)
    qtbot.addWidget(settings)
    assert settings.value().hotkey == "Ctrl+Alt+Z"
    assert not settings.autostart.isChecked()


def test_controller_async_offline_and_quick(qtbot, qapp, tmp_path, index):
    controller = Controller(qapp, ConfigStore(index.directory), start_sync=False, register_hotkey=False)
    qtbot.addWidget(controller.main)
    qtbot.addWidget(controller.quick)
    try:
        assert not controller.poll.isActive()
        controller.show_main()
        qtbot.waitUntil(lambda: controller.main.view.model_data.rowCount() == 1)
        controller.show_quick()
        controller.quick.search.setText("glover")
        qtbot.waitUntil(lambda: controller.quick.view.model_data.rowCount() == 1)
        assert controller.quick.isVisible()
        controller.quick.toggle_top(False)
        assert not bool(controller.quick.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        controller.quick.hide()
        controller.main.search.setText("does-not-exist")
        qtbot.waitUntil(lambda: controller.main.view.model_data.rowCount() == 0)
        assert controller.main.empty_label.isVisible()
    finally:
        controller.quitting = True
        controller.cancel.set()
        controller.poll.stop()
        controller.hotkey.unregister()
        controller.tray.hide()
        controller.pool.waitForDone(10000)
        qapp.processEvents()
        qapp.removeNativeEventFilter(controller.hotkey)


@pytest.mark.parametrize("language", ["zh_CN", "en"])
def test_catalog_and_themes(qapp, language):
    tr = Translator(language)
    assert all(len(pair) == 2 and all(pair) for pair in CATALOG.values())
    assert tr("original") != tr("translated")
    for theme in ["light", "dark", "system"]:
        apply_theme(qapp, theme)


@pytest.mark.parametrize("shortcut", ["Ctrl+Alt+Z", "Alt+Shift+F12", "Ctrl+1"])
def test_hotkey_parse(shortcut):
    flags, key = parse_hotkey(shortcut)
    assert flags & 0x4000 and key > 0


@pytest.mark.parametrize("shortcut", ["Z", "Win+Z", "Ctrl+", "Ctrl+Alt+F99"])
def test_invalid_hotkeys(shortcut):
    with pytest.raises(ValueError):
        parse_hotkey(shortcut)
