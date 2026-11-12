from __future__ import annotations

import ctypes
import os
import sys
from ctypes import wintypes
from pathlib import Path

from PySide6.QtCore import QAbstractNativeEventFilter

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "ZoteroFileExplorer"


def animations_enabled() -> bool:
    """Read SPI_GETCLIENTAREAANIMATION; a failed query does not disable the UI."""
    if sys.platform != "win32":
        return True
    enabled = wintypes.BOOL(True)
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    query = user32.SystemParametersInfoW
    query.argtypes = [wintypes.UINT, wintypes.UINT, ctypes.c_void_p, wintypes.UINT]
    query.restype = wintypes.BOOL
    return bool(enabled.value) if query(0x1042, 0, ctypes.byref(enabled), 0) else True


def startup_command() -> str:
    import subprocess

    args = (
        [sys.executable, "--background"]
        if getattr(sys, "frozen", False)
        else [sys.executable, "-m", "zotero_file_explorer", "--background"]
    )
    return subprocess.list2cmdline(args)


def autostart_enabled() -> bool:
    if sys.platform != "win32":
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value = winreg.QueryValueEx(key, RUN_NAME)[0]
        return value == startup_command()
    except OSError:
        return False


def set_autostart(enabled: bool) -> None:
    if sys.platform != "win32":
        return
    import winreg

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        if enabled:
            winreg.SetValueEx(key, RUN_NAME, 0, winreg.REG_SZ, startup_command())
        else:
            try:
                value = winreg.QueryValueEx(key, RUN_NAME)[0]
                # Do not remove an unrelated program's entry with the same name.
                if "zotero" in value.lower() and ("explorer" in value.lower()):
                    winreg.DeleteValue(key, RUN_NAME)
            except FileNotFoundError:
                pass


def parse_hotkey(value: str) -> tuple[int, int]:
    parts = value.upper().replace(" ", "").split("+")
    modifiers = {"CTRL": 0x2, "CONTROL": 0x2, "ALT": 0x1, "SHIFT": 0x4}
    flags = 0x4000  # MOD_NOREPEAT
    for part in parts[:-1]:
        if part not in modifiers:
            raise ValueError("Invalid shortcut modifier")
        flags |= modifiers[part]
    if len(parts) < 2:
        raise ValueError("A global shortcut must have a modifier")
    key = parts[-1]
    if len(key) == 1 and key.isascii() and key.isalnum():
        return flags, ord(key)
    if key.startswith("F") and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        return flags, 0x70 + int(key[1:]) - 1
    raise ValueError("Use a letter, number or F1–F24")


class GlobalHotkey(QAbstractNativeEventFilter):
    ID = 0x5A46

    def __init__(self, callback):
        super().__init__()
        self.callback = callback
        self.registered = False

    def register(self, sequence: str) -> bool:
        flags, key = parse_hotkey(sequence)
        self.unregister()
        if sys.platform == "win32":
            self.registered = bool(ctypes.windll.user32.RegisterHotKey(None, self.ID, flags, key))
        return self.registered

    def unregister(self):
        if self.registered:
            ctypes.windll.user32.UnregisterHotKey(None, self.ID)
            self.registered = False

    def nativeEventFilter(self, event_type, message):
        if sys.platform == "win32":
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == 0x0312 and msg.wParam == self.ID:
                self.callback()
                return True, 0
        return False, 0


def set_app_id():
    if sys.platform == "win32":
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ZoteroFileExplorer.Desktop.1")


def resource_path(relative: str) -> Path:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[3]))
    path = root / relative
    if path.exists():
        return path
    # Non-editable wheel installation uses setuptools' platform-neutral data scheme.
    return Path(sys.prefix) / "share" / "zotero_file_explorer" / relative


def session_lock_name(directory: Path) -> str:
    import hashlib

    ident = os.path.normcase(str(directory.resolve()))
    return "ZoteroFileExplorer-" + hashlib.sha256(ident.encode()).hexdigest()[:20]
