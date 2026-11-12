from functools import lru_cache

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPalette, QPen, QPixmap


@lru_cache(maxsize=12)
def ui_icon(kind):
    """Original outline glyphs, rendered once at 1x/2x; no files or per-row widgets."""
    icon = QIcon()
    for scale in (1, 2):
        pixmap = QPixmap(20 * scale, 20 * scale)
        pixmap.setDevicePixelRatio(scale)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#587bf5"), 1.6, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        path = QPainterPath()
        if kind == "folder":
            path.moveTo(3, 6)
            for x, y in [(3, 4), (8, 4), (10, 6), (17, 6), (17, 16), (3, 16), (3, 6)]:
                path.lineTo(x, y)
        elif kind == "quick":
            painter.drawEllipse(QRectF(3, 3, 10, 10))
            path.moveTo(12, 12)
            path.lineTo(17, 17)
        elif kind == "refresh":
            painter.drawArc(QRectF(4, 4, 12, 12), 35 * 16, 285 * 16)
            path.moveTo(17, 4)
            path.lineTo(17, 9)
            path.lineTo(12, 9)
        elif kind in {"rules", "settings"}:
            for y, knob in [(5, 7), (10, 13), (15, 9)]:
                painter.drawLine(3, y, knob - 2, y)
                painter.drawLine(knob + 2, y, 17, y)
                painter.drawEllipse(QRectF(knob - 2, y - 2, 4, 4))
        elif kind in {"review", "errors"}:
            painter.drawEllipse(QRectF(3, 3, 14, 14))
            painter.drawLine(10, 6, 10, 11)
            painter.drawPoint(10, 14)
        else:
            painter.drawRoundedRect(QRectF(4, 3, 12, 14), 2, 2)
            painter.drawLine(7, 8, 13, 8)
            painter.drawLine(7, 12, 12, 12)
        painter.drawPath(path)
        painter.end()
        icon.addPixmap(pixmap)
    return icon


def apply_theme(app, theme="system"):
    scheme = app.styleHints().colorScheme()
    dark = theme == "dark" or (theme == "system" and scheme == Qt.ColorScheme.Dark)
    background, panel, text, muted, border = (
        ("#171b23", "#202632", "#e7edf7", "#a8b6ca", "#323e52")
        if dark
        else ("#f4f6fb", "#ffffff", "#18243b", "#64748b", "#dfe5ef")
    )
    alternate = "#242b38" if dark else "#f8faff"
    hover = "#2b3547" if dark else "#edf2ff"
    accent_text = "#b5caff" if dark else "#294fc8"
    disabled = "#7e8a9e" if dark else "#8b98ab"
    palette = QPalette()
    for role, color in [
        (QPalette.ColorRole.Window, background),
        (QPalette.ColorRole.WindowText, text),
        (QPalette.ColorRole.Base, panel),
        (QPalette.ColorRole.AlternateBase, alternate),
        (QPalette.ColorRole.Text, text),
        (QPalette.ColorRole.Button, panel),
        (QPalette.ColorRole.ButtonText, text),
        (QPalette.ColorRole.Highlight, "#365ff0"),
        (QPalette.ColorRole.HighlightedText, "#ffffff"),
        (QPalette.ColorRole.ToolTipBase, panel),
        (QPalette.ColorRole.ToolTipText, text),
        (QPalette.ColorRole.PlaceholderText, muted),
        (QPalette.ColorRole.Mid, border),
        (QPalette.ColorRole.Dark, muted),
    ]:
        palette.setColor(role, QColor(color))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(disabled))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(disabled))
    if app.palette() != palette:
        app.setPalette(palette)
    stylesheet = f"""
        QWidget {{ font-family: 'Segoe UI', 'Microsoft YaHei UI'; font-size: 10pt; }}
        QMainWindow, QDialog {{ background: {background}; }}
        QWidget#sidebar, QWidget#contentPanel {{ background: {panel}; border: 1px solid {border};
          border-radius: 12px; }}
        QWidget#quickPanel {{ background: {panel}; }}
        QLabel#heading {{ font-size: 21pt; font-weight: 600; }}
        QLabel#brand {{ font-size: 12pt; font-weight: 600; }}
        QLabel#muted {{ color: {muted}; font-size: 9pt; }}
        QLabel#sectionCaption {{ color: {muted}; font-size: 9pt; font-weight: 600; padding-top: 4px; }}
        QLabel#filterCaption {{ color: {muted}; font-size: 9pt; }}
        QLabel#connectionStatus {{ color: {muted}; background: {alternate};
          border-radius: 6px; padding: 6px 10px; font-size: 9pt; }}
        QLabel#keycap {{ color: {muted}; background: {alternate}; border: 1px solid {border};
          border-radius: 5px; padding: 4px 7px; font-size: 9pt; }}
        QLineEdit, QComboBox, QSpinBox, QKeySequenceEdit {{ background: {panel}; color: {text};
          border: 1px solid {border}; border-radius: 6px; padding: 6px; min-height: 22px; }}
        QLineEdit:focus {{ border: 1px solid #587bf5; }}
        QLineEdit#searchInput {{ border-radius: 8px; padding: 9px 12px; background: {alternate}; }}
        QLineEdit#searchInput:focus {{ background: {panel}; border-color: #587bf5; }}
        QComboBox:focus, QSpinBox:focus, QKeySequenceEdit:focus {{ border-color: #587bf5; }}
        QComboBox::drop-down {{ border: none; width: 20px; }}
        QSpinBox QLineEdit, QKeySequenceEdit QLineEdit {{ border: none; padding: 0;
          min-height: 0; background: transparent; }}
        QPushButton, QToolButton {{ border: 1px solid {border}; border-radius: 6px; padding: 7px 12px;
          background: {panel}; color: {text}; }}
        QPushButton:hover, QToolButton:hover {{ border-color: #587bf5; background: {hover}; }}
        QPushButton:focus, QToolButton:focus {{ border: 2px solid #587bf5; padding: 6px 11px; }}
        QPushButton:pressed, QToolButton:pressed {{ background: {background}; border-color: #365ff0; }}
        QPushButton:disabled, QToolButton:disabled {{ color: {disabled}; border-color: {border}; }}
        QPushButton#primary {{ background: #365ff0; color: white; border-color: #365ff0; }}
        QPushButton#primary:pressed {{ background: #294bc9; }}
        QPushButton#primary:hover {{ background: #2d55df; }}
        QPushButton#primary:disabled {{ background: {border}; color: {muted};
          border-color: {border}; }}
        QPushButton#sidebarAction {{ text-align: left; background: transparent;
          border: 1px solid transparent; padding: 8px 10px; }}
        QPushButton#sidebarAction:hover {{ background: {hover}; color: {accent_text}; }}
        QPushButton#sidebarAction:focus {{ border: 1px solid #587bf5; padding: 8px 10px; }}
        QPushButton#sidebarAction:pressed {{ background: {border}; }}
        QCheckBox:focus {{ color: #587bf5; }}
        QToolTip {{ background: {panel}; color: {text};
          border: 1px solid {border}; padding: 5px; }}
        QTreeView, QTableView {{ background: {panel}; color: {text};
          border: 1px solid {border};
          border-radius: 8px; outline: none; alternate-background-color: {alternate}; }}
        QTreeView::item {{ min-height: 32px; padding: 2px; }}
        QTreeView:focus {{ border-color: #587bf5; }}
        QTreeView::item:selected {{ background: #365ff0; color: white; }}
        QTreeWidget#navigation {{ background: transparent; border: none; }}
        QTreeWidget#navigation::item {{ min-height: 30px; padding: 4px 6px; border-radius: 6px; }}
        QTreeWidget#navigation::item:selected {{ background: {hover}; color: {accent_text}; }}
        QHeaderView::section {{ background: {alternate}; color: {muted}; border: none;
          border-bottom: 1px solid {border}; padding: 10px 8px; font-size: 9pt; font-weight: 600; }}
        QMenu {{ background: {panel}; color: {text};
          border: 1px solid {border}; padding: 5px; }}
        QMenu::item {{ padding: 7px 18px; }}
        QMenu::item:selected {{ background: #365ff0; color: white; }}
        QStatusBar {{ color: {muted}; background: {background}; }}
        QSplitter::handle {{ background: transparent; width: 10px; }}
        QScrollBar:vertical {{ background: {panel}; width: 12px; margin: 2px; }}
        QScrollBar::handle:vertical {{ background: {border}; border-radius: 4px; min-height: 28px; }}
        QScrollBar::handle:vertical:hover {{ background: {muted}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
        QScrollBar:horizontal {{ background: {panel}; height: 12px; margin: 2px; }}
        QScrollBar::handle:horizontal {{ background: {border}; border-radius: 4px; min-width: 28px; }}
        QScrollBar::handle:horizontal:hover {{ background: {muted}; }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0px; }}
        QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
    """
    if app.styleSheet() != stylesheet:
        app.setStyleSheet(stylesheet)
