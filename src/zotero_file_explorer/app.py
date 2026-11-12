from __future__ import annotations

import argparse
import logging
import logging.handlers
import sys
import threading
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QLockFile, QObject, Qt, QThreadPool, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QMenu, QMessageBox, QSystemTrayIcon

from . import __version__
from .i18n.strings import Translator
from .platform.files import copy_files, drag_files, open_file, reveal_file
from .platform.windows import (
    GlobalHotkey,
    autostart_enabled,
    resource_path,
    session_lock_name,
    set_app_id,
    set_autostart,
)
from .services.paths import detected_directories, valid_file_paths
from .services.sync import SyncService
from .storage.config import ConfigStore
from .storage.index import Index
from .ui.dialogs import RulesDialog, SettingsDialog
from .ui.motion import MotionStyle, MotionSystem
from .ui.theme import apply_theme
from .ui.windows import MainWindow, QuickWindow
from .ui.workers import Task

log = logging.getLogger("zfe")


class Controller(QObject):
    def __init__(self, app: QApplication, config: ConfigStore, start_sync=True, register_hotkey=True):
        super().__init__()
        self.app, self.config = app, config
        self.settings = config.load()
        self.motion = MotionSystem(app, self.settings, self)
        app.setStyle(MotionStyle(self.motion.policy))
        self.tr = Translator(self.settings.language)
        self.index = Index(config.directory)
        self.icon = QIcon(str(resource_path("assets/icons/app.ico")))
        self.app.setWindowIcon(self.icon)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(3)
        self.tasks = set()
        self.searches = {}
        self.navigation_generation = 0
        self.reclassifying = False
        self.reclassify_pending = False
        self.preparing_files = False
        self.syncing = False
        self.pending_force_sync = False
        self.quitting = False
        self.cancel = threading.Event()
        self.connection_text = self.tr("offline")
        self.hotkey = GlobalHotkey(self.show_quick)
        self.app.installNativeEventFilter(self.hotkey)
        self.main = MainWindow(self)
        self.quick = QuickWindow(self)
        if not start_sync:
            self.main.connection_label.setText(self.connection_text)
        self.tray = QSystemTrayIcon(self.icon, self)
        self.tray.setToolTip(self.tr("app"))
        self.create_tray()
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()
        self.poll = QTimer(self)
        self.poll.setInterval(self.settings.poll_seconds * 1000)
        self.poll.timeout.connect(self.synchronize)
        if start_sync:
            self.poll.start()
        self.app.styleHints().colorSchemeChanged.connect(
            lambda *_: apply_theme(self.app, self.settings.theme)
        )
        apply_theme(self.app, self.settings.theme)
        self.hotkey_enabled = register_hotkey
        if register_hotkey:
            QTimer.singleShot(500, self.register_hotkey)
        self.main.query()
        self.quick.query()
        for warning in [config.warning, self.index.recovery, self.index.override_warning]:
            if warning:
                QTimer.singleShot(500, lambda key=warning: self.notice(key))
        if start_sync:
            QTimer.singleShot(100, self.synchronize)

    def submit(self, function, callback, progress=None):
        if self.quitting:
            return None
        task = Task(function)
        self.tasks.add(task)

        def done(result, error):
            self.tasks.discard(task)
            if not self.quitting:
                callback(result, error)

        task.signals.finished.connect(done)
        if progress:
            task.signals.progress.connect(progress)
        self.pool.start(task)
        return task

    def create_tray(self):
        menu = QMenu()
        for key, callback in [
            ("main", self.show_main),
            ("quick", self.show_quick),
            ("refresh", self.synchronize),
            ("settings", self.show_settings),
            ("quit", self.quit),
        ]:
            action = menu.addAction(self.tr(key))
            action.triggered.connect(lambda checked=False, call=callback: call())
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda reason: self.show_main() if reason == QSystemTrayIcon.ActivationReason.Trigger else None
        )
        self.tray_menu = menu

    def show_main(self):
        if self.main.isMinimized():
            self.main.showNormal()
        else:
            self.main.show()
        self.main.raise_()
        self.main.activateWindow()

    def show_quick(self):
        self.quick.showNormal()
        self.quick.raise_()
        self.quick.activateWindow()
        self.quick.search.setFocus()
        self.quick.search.selectAll()
        self.quick.query()

    def register_hotkey(self):
        try:
            success = self.hotkey.register(self.settings.hotkey)
        except ValueError:
            success = False
        if not success:
            self.notice("hotkey_failed")

    def notice(self, key: str):
        if not self.quitting:
            QMessageBox.warning(self.app.activeWindow() or self.main, self.tr("error"), self.tr(key))

    def synchronize(self, force_paths=False):
        if self.quitting:
            return
        if self.syncing:
            self.pending_force_sync |= force_paths
            return
        self.syncing = True
        self.main.sync_button.setEnabled(False)
        self.main.connection_label.setText(self.tr("syncing"))
        settings = replace(self.settings, rules=[dict(r) for r in self.settings.rules])

        def progress(text):
            self.main.connection_label.setText(
                self.tr("syncing") + " · " + text.replace("personal", self.tr("personal"))
            )

        # Bind progress before starting the runnable to avoid a fast completion race.
        task = Task(
            lambda: SyncService(self.index, settings).synchronize(
                force_paths=force_paths, progress=task.signals.progress.emit, cancelled=self.cancel.is_set
            )
        )
        self.tasks.add(task)
        task.signals.progress.connect(progress)

        def finished(result, error):
            self.tasks.discard(task)
            self.syncing = False
            if self.quitting:
                return
            self.main.sync_button.setEnabled(True)
            if error:
                key = error.args[0] if error.args and isinstance(error.args[0], str) else "api_error"
                log.warning("sync failed: %s code=%s", type(error).__name__, getattr(error, "code", ""))
                self.connection_text = self.tr("offline") + (" · " + self.tr(key) if key != "offline" else "")
                if key in {"instance_changed", "library_changed_during_sync"}:
                    QTimer.singleShot(2500, self.synchronize)
                # Offline filesystem changes still update cached availability.
                self.reclassify()
            else:
                self.connection_text = (
                    self.tr("online") + " · " + self.tr("last_sync", time=datetime.now().strftime("%H:%M:%S"))
                )
                if result["legacy"]:
                    self.connection_text += " · " + self.tr("legacy")
                self.main.reload_navigation()
            self.main.connection_label.setText(self.connection_text)
            self.main.query()
            self.quick.query()
            if not error and settings.rules != self.settings.rules:
                self.reclassify()
            if self.pending_force_sync:
                self.pending_force_sync = False
                QTimer.singleShot(100, lambda: self.synchronize(force_paths=True))

        task.signals.finished.connect(finished)
        self.pool.start(task)

    def search(self, window, filters):
        window.debounce.stop()
        window.generation += 1
        generation = window.generation
        window.search_started()
        # Keep at most one running and one latest query per window. Rapid typing,
        # sorting and navigation must not fill the shared worker pool with stale jobs.
        if window in self.searches:
            self.searches[window] = (generation, filters)
            return
        self._search(window, generation, filters)

    def _search(self, window, generation, filters):
        self.searches[window] = None

        def query():
            rows, count = self.index.search(filters)
            return rows, count, self.index.libraries(), self.index.active_instance()

        def complete(result, error):
            pending = self.searches.pop(window, None)
            if generation == window.generation and error:
                log.warning("search failed: %s", type(error).__name__)
                window.search_finished(error)
            elif generation == window.generation:
                # A refreshed index may have fewer pages than the previously visible one.
                if filters.offset and filters.offset >= result[1]:
                    window.offset = (max(0, result[1] - 1) // filters.limit) * filters.limit
                    if result[1]:
                        window.query()
                        return
                window.displayed_generation = generation
                window.display(*result)
                window.search_finished()
            if pending:
                self._search(window, *pending)

        self.submit(query, complete)

    def load_navigation(self, window):
        self.navigation_generation += 1
        generation = self.navigation_generation

        def complete(result, error):
            if generation != self.navigation_generation or window is not self.main:
                return
            if error:
                log.warning("navigation failed: %s", type(error).__name__)
                return
            window.apply_navigation(*result)

        self.submit(lambda: (self.index.libraries(), self.index.collections()), complete)

    def reclassify(self):
        if self.reclassifying:
            self.reclassify_pending = True
            return
        self.reclassifying = True
        rules = [dict(rule) for rule in self.settings.rules]

        def complete(result, error):
            self.reclassifying = False
            if error:
                self.notice("api_error")
            self.main.query()
            self.quick.query()
            if self.reclassify_pending:
                self.reclassify_pending = False
                self.reclassify()

        self.submit(lambda: self.index.reclassify(rules), complete)

    def save_overrides(self, attachments, values):
        # The index writer holds its lock during projection and filesystem checks.
        # Never wait for that lock on the GUI thread.
        def write():
            for attachment, value in zip(attachments, values, strict=True):
                self.index.set_override(
                    attachment["instance"],
                    attachment["library"],
                    value.pop("key", attachment["key"]),
                    **value,
                )

        def complete(result, error):
            if error:
                self.notice("overrides_invalid" if str(error) == "overrides_invalid" else "api_error")
            else:
                self.reclassify()

        self.submit(write, complete)

    def prepare_files(self, key, paths, view):
        if self.preparing_files:
            return
        self.preparing_files = True
        window = view.window()
        window.set_operation_feedback(self.tr("checking_files"), timeout=0)

        def complete(valid, error):
            self.preparing_files = False
            # Language changes may replace the source window while validation runs.
            target = self.quick if view.compact else self.main
            if target is not window:
                target.set_operation_feedback(self.tr("checking_files"), timeout=0)
            if error or not valid:
                target.set_operation_feedback(self.tr("no_available_files"), timeout=0)
                return
            try:
                if key == "copy_files":
                    count = copy_files(valid, validated=True)
                    target.set_operation_feedback(self.tr("copied", count=count))
                else:
                    target.clear_operation_feedback()
                    if target is window and QApplication.mouseButtons() & Qt.MouseButton.LeftButton:
                        drag_files(view, valid, validated=True)
            except (OSError, ValueError):
                target.set_operation_feedback(self.tr("no_available_files"), timeout=0)

        self.submit(lambda: valid_file_paths(paths), complete)

    def file_action(self, key: str, view):
        window = view.window()
        if window in {self.main, self.quick} and not window.results_ready:
            return
        attachments = view.selected_attachments(originals_only=key in {"copy_files", "primary", "drag"})
        if not attachments:
            self.notice("no_available_files")
            return
        first = attachments[0]
        paths = [a["path"] for a in attachments]
        try:
            if key in {"copy_files", "drag"}:
                self.prepare_files(key, paths, view)
            elif key in {"copy_paths", "copy_names"}:
                text = "\n".join(
                    dict.fromkeys(a["path"] if key == "copy_paths" else a["filename"] for a in attachments)
                )
                self.app.clipboard().setText(text)
            elif key == "open":
                self.submit(
                    lambda: open_file(first["path"]),
                    lambda result, error: self.notice("no_available_files") if error or not result else None,
                )
            elif key == "reveal":
                reveal_file(first["path"])
            elif key == "folder":
                if not first["path"]:
                    raise ValueError("no_available_files")
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(first["path"]).parent)))
            elif key == "details":
                text = "\n\n".join(
                    self.tr(k) + ": " + value
                    for k, value in [
                        ("attachment_title", first["title"]),
                        ("filename", first["filename"]),
                        ("path", first["path"] or self.tr("no_path")),
                        ("status", self.tr(first["status"])),
                        ("result", self.tr(first["state"])),
                        ("reason", self.tr.reason(first["reason"])),
                    ]
                )
                QMessageBox.information(view, self.tr("details"), text)
            elif key == "relocate":
                path, _ = QFileDialog.getOpenFileName(
                    view,
                    self.tr("relocate"),
                    str(Path(first["path"]).parent) if first["path"] else "",
                    "Documents (*.pdf *.doc *.docx *.epub)",
                )
                if path:
                    if Path(path).suffix.lower() not in {
                        ".pdf",
                        ".doc",
                        ".docx",
                        ".epub",
                    }:
                        raise ValueError("no_available_files")

                    def located(valid, error):
                        if error or not valid:
                            self.notice("no_available_files")
                        else:
                            self.save_overrides([first], [{"path": valid[0]}])

                    self.submit(lambda: valid_file_paths([path]), located)
            elif key == "primary":
                self.save_overrides([first], [{"key": first["document_key"], "primary": first["key"]}])
            elif key in {"mark_original", "mark_translated", "auto_classify"}:
                state = {"mark_original": "original", "mark_translated": "translated", "auto_classify": ""}[
                    key
                ]
                self.save_overrides(attachments, [{"state": state} for _ in attachments])
        except (OSError, ValueError) as error:
            log.warning("file operation failed: %s", type(error).__name__)
            self.notice("overrides_invalid" if str(error) == "overrides_invalid" else "no_available_files")

    def show_rules(self):
        dialog = RulesDialog(self.settings, self.tr, self.main)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.settings.rules = dialog.rules()
            self.config.save(self.settings)
            self.reclassify()
        dialog.deleteLater()

    def show_settings(self):
        dialog = SettingsDialog(self.settings, self.tr, self.main, submit=self.submit)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            dialog.deleteLater()
            return
        updated = dialog.value()
        autostart = dialog.autostart.isChecked()
        dialog.deleteLater()
        try:
            # The toggle is changed only following an explicit Save from the user.
            if autostart != autostart_enabled():
                set_autostart(autostart)
            self.config.save(updated)
        except OSError:
            self.notice("invalid_settings")
            return
        language_changed = updated.language != self.settings.language
        connection_changed = (updated.api_url, updated.data_directory, updated.attachment_base) != (
            self.settings.api_url,
            self.settings.data_directory,
            self.settings.attachment_base,
        )
        self.settings = updated
        self.motion.policy.configure(updated)
        old_tr = Translator(self.tr.language)
        self.tr.language = updated.language
        if language_changed:
            for key in ["offline", "online", "legacy"]:
                self.connection_text = self.connection_text.replace(old_tr(key), self.tr(key))
        self.poll.setInterval(updated.poll_seconds * 1000)
        apply_theme(self.app, updated.theme)
        if self.hotkey_enabled:
            self.register_hotkey()
        if language_changed:
            previous_main, previous_quick = self.main, self.quick
            previous_main.remember_layout()
            previous_quick.remember_layout()
            quick_visible = previous_quick.isVisible()
            previous_main.generation += 1
            previous_quick.generation += 1
            previous_main.hide()
            previous_quick.hide()
            self.main = MainWindow(self)
            self.main.connection_label.setText(self.tr("syncing") if self.syncing else self.connection_text)
            self.quick = QuickWindow(self)
            previous_main.deleteLater()
            previous_quick.deleteLater()
            self.create_tray()
            self.show_main()
            if quick_visible:
                self.show_quick()
            self.main.query()
        if connection_changed:
            QTimer.singleShot(100, lambda: self.synchronize(force_paths=True))

    def rebuild_index(self):
        if self.syncing:
            self.notice("busy")
            return
        if (
            QMessageBox.question(self.main, self.tr("rebuild"), self.tr("rebuild_help"))
            != QMessageBox.StandardButton.Yes
        ):
            return
        self.submit(
            self.index.rebuild,
            lambda result, error: self.notice("api_error") if error else self.synchronize(force_paths=True),
        )

    def quit(self):
        if self.quitting:
            return
        self.quitting = True
        self.cancel.set()
        self.poll.stop()
        self.hotkey.unregister()
        self.main.hide()
        self.quick.hide()
        self.tray.hide()
        # Keep the GUI event loop alive while bounded network calls finish.
        self.quit_timer = QTimer(self)
        self.quit_timer.setInterval(100)
        self.quit_timer.timeout.connect(self.finish_quit)
        self.quit_timer.start()

    def finish_quit(self):
        if self.pool.activeThreadCount() == 0:
            self.quit_timer.stop()
            self.app.removeNativeEventFilter(self.hotkey)
            self.app.quit()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--background", action="store_true")
    parser.add_argument("--quick", action="store_true")
    parser.add_argument(
        "--data-dir", type=Path, help="Override this app's user-data directory for isolated testing"
    )
    parser.add_argument(
        "--no-sync", action="store_true", help="Load the offline index without network requests"
    )
    parser.add_argument("--smoke-test", action="store_true", help="Run a packaged self-check and exit")
    args = parser.parse_args()
    set_app_id()
    app = QApplication(sys.argv[:1])
    app.setApplicationName("ZoteroFileExplorer")
    app.setApplicationVersion(__version__)
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")
    config = ConfigStore(args.data_dir)
    logdir = config.directory / "logs"
    logdir.mkdir(exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        logdir / "errors.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.WARNING)
    if args.smoke_test:
        from .platform.files import file_mime_data
        from .storage.config import atomic_json
        from .storage.index import SearchFilter

        icon = QIcon(str(resource_path("assets/icons/app.ico")))
        probe_path = config.directory / "smoke attachment.txt"
        probe_path.write_text("build self-check", encoding="utf-8")
        mime = file_mime_data([str(probe_path)])
        index = Index(config.directory)
        result = {
            "version": __version__,
            "qt_application_version": app.applicationVersion(),
            "icon_loaded": not icon.isNull(),
            "offline_count": index.search(SearchFilter())[1],
            "file_urls": len(mime.urls()),
            "python_bundled": bool(getattr(sys, "frozen", False)),
            "source_module": str(Path(__file__).name),
        }
        atomic_json(config.directory / "self-check.json", result)
        return 0 if result["icon_loaded"] and result["file_urls"] == 1 else 2
    name = session_lock_name(config.directory)
    socket = QLocalSocket()
    socket.connectToServer(name)
    if socket.waitForConnected(500):
        socket.write(b"quick" if args.quick else b"main")
        socket.waitForBytesWritten(500)
        socket.disconnectFromServer()
        return 0
    lock = QLockFile(str(config.directory / "app.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        return 1
    server = QLocalServer()
    QLocalServer.removeServer(name)
    if not server.listen(name):
        return 1
    controller = Controller(app, config, start_sync=not args.no_sync)
    if not controller.settings.data_directory:

        def detected(result, error):
            if error:
                return
            directories, base = result
            if directories and not controller.settings.data_directory:
                controller.settings.data_directory = directories[0]
            if base and not controller.settings.attachment_base:
                controller.settings.attachment_base = base

        controller.submit(detected_directories, detected)

    def new_connection():
        client = server.nextPendingConnection()

        def read():
            message = bytes(client.readAll())
            controller.show_quick() if message == b"quick" else controller.show_main()
            client.disconnectFromServer()
            client.deleteLater()

        if client.bytesAvailable():
            read()
        else:
            client.readyRead.connect(read)

    server.newConnection.connect(new_connection)
    if args.quick:
        controller.show_quick()
    elif not args.background or not controller.tray.isVisible():
        controller.show_main()
    exit_code = app.exec()
    server.close()
    lock.unlock()
    return exit_code
