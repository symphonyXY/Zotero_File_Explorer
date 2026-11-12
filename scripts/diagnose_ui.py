"""Read-only live GUI probe with a heartbeat-triggered Python stack dump."""

import faulthandler
import os
import sqlite3
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from zotero_file_explorer.app import Controller
from zotero_file_explorer.storage.config import ConfigStore

ROOT = Path(__file__).resolve().parents[1]
data = ROOT / "build/responsiveness-probe"
data.mkdir(parents=True, exist_ok=True)
source = Path(os.environ["LOCALAPPDATA"]) / "ZoteroFileExplorer/index.sqlite3"
if source.exists() and not (data / "index.sqlite3").exists():
    with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as original:
        with sqlite3.connect(data / "index.sqlite3") as target:
            original.backup(target)
trace = (data / "stacks.log").open("w", encoding="utf-8")
faulthandler.enable(trace)
app = QApplication(sys.argv[:1])
app.setQuitOnLastWindowClosed(False)
app.setStyle("Fusion")
controller = Controller(app, ConfigStore(data), register_hotkey=False)
timer = QTimer()
timer.setInterval(500)
timer.timeout.connect(lambda: faulthandler.dump_traceback_later(5, file=trace))
timer.start()
controller.show_main()
code = app.exec()
faulthandler.cancel_dump_traceback_later()
trace.close()
sys.exit(code)
