from __future__ import annotations

import os
import struct
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QMimeData, QPoint, Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QDrag, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QWidget

from ..services.paths import valid_file_paths


def file_mime_data(paths: list[str], *, validated: bool = False) -> QMimeData:
    # GUI callers validate on a worker before constructing the Qt-owned object.
    valid = paths if validated else valid_file_paths(paths)
    if not valid:
        raise ValueError("no_available_files")
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(path) for path in valid])
    # Qt's Windows MIME converter exposes local URLs as the native CF_HDROP.
    # Explicit copy preference is also honored by Explorer on clipboard paste.
    mime.setData('application/x-qt-windows-mime;value="Preferred DropEffect"', struct.pack("<I", 1))
    return mime


def copy_files(paths: list[str], *, validated: bool = False) -> int:
    mime = file_mime_data(paths, validated=validated)
    count = len(mime.urls())
    QApplication.clipboard().setMimeData(mime)
    return count


def drag_files(source: QWidget, paths: list[str], *, validated: bool = False) -> Qt.DropAction:
    drag = QDrag(source)
    mime = file_mime_data(paths, validated=validated)
    drag.setMimeData(mime)
    # A small device-scaled badge; the native URLs remain the actual drag payload.
    ratio = source.devicePixelRatioF()
    preview = QPixmap(round(76 * ratio), round(40 * ratio))
    preview.setDevicePixelRatio(ratio)
    preview.fill(Qt.GlobalColor.transparent)
    painter = QPainter(preview)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor("#365ff0"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(0, 0, 76, 40, 8, 8)
    painter.setPen(Qt.GlobalColor.white)
    painter.drawText(0, 0, 76, 40, Qt.AlignmentFlag.AlignCenter, f"+  {len(mime.urls())}")
    painter.end()
    drag.setPixmap(preview)
    drag.setHotSpot(QPoint(12, 12))
    # A target cannot negotiate MoveAction, including when Shift is pressed.
    return drag.exec(Qt.DropAction.CopyAction, Qt.DropAction.CopyAction)


def open_file(path: str) -> bool:
    valid = valid_file_paths([path])
    if not valid:
        raise ValueError("no_available_files")
    if sys.platform == "win32":
        os.startfile(valid[0])
        return True
    return QDesktopServices.openUrl(QUrl.fromLocalFile(valid[0]))


def reveal_file(path: str) -> None:
    if not path or not Path(path).is_absolute():
        raise ValueError("no_available_files")
    if sys.platform == "win32":
        # Use argument vectors and the absolute system binary, never a shell string.
        explorer = str(Path(os.environ.get("WINDIR", r"C:\Windows")) / "explorer.exe")
        subprocess.Popen([explorer, "/select,", os.path.normpath(path)], close_fds=True)
    else:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).parent)))
