from __future__ import annotations

from PySide6.QtCore import QItemSelection, QItemSelectionModel, Qt, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QAbstractItemView, QLabel, QMenu, QSizePolicy, QTreeView, QVBoxLayout

from .paper_model import COLUMNS, ROLE, PaperModel, identity


class PaperView(QTreeView):
    copyRequested = Signal()
    actionRequested = Signal(str)
    operationError = Signal(str)
    sortRequested = Signal(str, bool)

    def __init__(self, tr, parent=None, compact=False):
        super().__init__(parent)
        self.tr = tr
        self.compact = compact
        self.auto_title_width = True
        self._fitting_title = False
        self.model_data = PaperModel(tr, self)
        self.setModel(self.model_data)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setUniformRowHeights(True)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setAlternatingRowColors(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.setDefaultDropAction(Qt.DropAction.CopyAction)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.context_menu)
        self.doubleClicked.connect(lambda _: self.actionRequested.emit("open"))
        self.header().setSectionsClickable(True)
        self.header().setSectionsMovable(True)
        self.header().setSortIndicatorShown(True)
        self.header().setSortIndicator(0, Qt.SortOrder.AscendingOrder)
        self.header().sectionClicked.connect(self.sort_clicked)
        self.header().setStretchLastSection(False)
        self.header().sectionResized.connect(self.column_resized)
        self.setAccessibleName(self.tr("results"))
        self.empty_label = QLabel(self.viewport())
        self.empty_label.setObjectName("muted")
        self.empty_label.setWordWrap(True)
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setMaximumWidth(560)
        self.empty_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.empty_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.empty_label.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        empty_layout = QVBoxLayout(self.viewport())
        empty_layout.setContentsMargins(32, 24, 32, 24)
        empty_layout.addStretch()
        empty_layout.addWidget(self.empty_label)
        empty_layout.addStretch()
        self.empty_label.hide()
        self.retranslate()

    def column_resized(self, column, old_size, new_size):
        if not self._fitting_title and self.isVisible():
            if column == 0:
                self.auto_title_width = False
            else:
                self.fit_title_column()

    def fit_title_column(self):
        if self.compact or not self.auto_title_width:
            return
        other_width = sum(
            self.columnWidth(c) for c in range(1, len(COLUMNS)) if not self.isColumnHidden(c)
        )
        self._fitting_title = True
        try:
            self.setColumnWidth(0, max(260, self.viewport().width() - other_width))
        finally:
            self._fitting_title = False

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit_title_column()

    def set_message(self, text):
        self.empty_label.setText(text)
        self.empty_label.setVisible(bool(text) and not self.model_data.rowCount())

    def retranslate(self):
        self.model_data.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, len(COLUMNS) - 1)

    def sort_clicked(self, column):
        current = self.header().sortIndicatorSection()
        descending = current == column and self.header().sortIndicatorOrder() == Qt.SortOrder.AscendingOrder
        self.header().setSortIndicator(
            column, Qt.SortOrder.DescendingOrder if descending else Qt.SortOrder.AscendingOrder
        )
        self.sortRequested.emit(COLUMNS[column], descending)

    def selected_data(self) -> list[dict]:
        return [index.data(ROLE) for index in self.selectionModel().selectedRows(0) if index.data(ROLE)]

    def selected_attachments(self, originals_only=False) -> list[dict]:
        result, seen = [], set()
        for data in self.selected_data():
            attachment = data.get("attachment")
            if not attachment or (originals_only and attachment["state"] != "original"):
                continue
            ident = (data["instance"], data["library"], attachment["key"])
            if ident not in seen:
                seen.add(ident)
                result.append(
                    {
                        **attachment,
                        "instance": data["instance"],
                        "library": data["library"],
                        "document_key": data["document_key"],
                    }
                )
        return result

    def startDrag(self, supported_actions):
        self.actionRequested.emit("drag")

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Copy):
            self.copyRequested.emit()
            event.accept()
        elif event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter}:
            self.actionRequested.emit("open")
        else:
            super().keyPressEvent(event)

    def context_menu(self, point):
        index = self.indexAt(point)
        if not index.isValid():
            return
        if not self.selectionModel().isSelected(index):
            self.setCurrentIndex(index)
        menu = QMenu(self)
        for key in [
            "open",
            "copy_files",
            "copy_paths",
            "copy_names",
            "reveal",
            "folder",
            "details",
            "primary",
            "relocate",
            "mark_original",
            "mark_translated",
            "auto_classify",
        ]:
            if key in {"details", "primary", "mark_original"}:
                menu.addSeparator()
            action = menu.addAction(self.tr(key))
            action.triggered.connect(
                lambda checked=False, operation=key: self.actionRequested.emit(operation)
            )
        menu.exec(self.viewport().mapToGlobal(point))
        menu.deleteLater()

    def populate(self, rows: list[dict], library_names: dict[str, str], mode="all"):
        model = self.model_data
        expanded = {
            identity(model.index(r, 0).data(ROLE))[:3]
            for r in range(model.rowCount())
            if self.isExpanded(model.index(r, 0))
        }
        selected = {identity(d) for d in self.selected_data()}
        current = self.currentIndex().data(ROLE)
        current_id = identity(current) if current else None
        scroll = self.verticalScrollBar().value()
        # Bulk restoration must not launch hundreds of native branch animations.
        animated = self.isAnimated()
        self.setAnimated(False)
        self.setUpdatesEnabled(False)
        try:
            if not model.replace(rows, library_names, mode):
                return
            selection = QItemSelection()
            restore = expanded or selected or current_id or mode != "all"
            for row in range(model.rowCount() if restore else 0):
                parent = model.index(row, 0)
                if identity(parent.data(ROLE))[:3] in expanded or mode != "all":
                    self.expand(parent)
                for idx in [parent] + [model.index(c, 0, parent) for c in range(model.rowCount(parent))]:
                    key = identity(idx.data(ROLE))
                    if key in selected:
                        selection.select(idx, model.index(idx.row(), len(COLUMNS) - 1, idx.parent()))
                    if key == current_id:
                        self.selectionModel().setCurrentIndex(idx, QItemSelectionModel.SelectionFlag.NoUpdate)
            self.selectionModel().select(selection, QItemSelectionModel.SelectionFlag.Select)
            self.verticalScrollBar().setValue(scroll)
        finally:
            self.setUpdatesEnabled(True)
            self.setAnimated(animated)
        if self.auto_title_width and self.columnWidth(0) < 200:
            self.setColumnWidth(0, 340 if self.compact else 360)
