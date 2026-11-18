"""Read-only tree model: one record per row, no per-cell QObject allocation."""

from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import QAbstractItemModel, QModelIndex, Qt
from PySide6.QtGui import QFont

ROLE = int(Qt.ItemDataRole.UserRole) + 1
ROOT_INDEX = QModelIndex()
COLUMNS = ["title", "authors", "year", "doi", "type", "filename", "size", "library", "status", "card_state"]


def human_size(size: int) -> str:
    if not size:
        return "—"
    return f"{size / 1024 / 1024:.1f} MB" if size >= 1024 * 1024 else f"{size / 1024:.0f} KB"


def identity(data):
    return (
        data["instance"],
        data["library"],
        data["document_key"],
        (data.get("attachment") or {}).get("key"),
        data["is_document"],
    )


@dataclass(eq=False, slots=True)
class Row:
    position: int
    values: tuple
    payload: dict
    parent: Row | None = None
    children: list = field(default_factory=list)
    tooltip: str = ""


class PaperModel(QAbstractItemModel):
    def __init__(self, tr, parent=None):
        super().__init__(parent)
        self.tr = tr
        self.rows = []
        self.snapshot = None
        self.bold = QFont()
        self.bold.setWeight(QFont.Weight.DemiBold)

    def columnCount(self, parent=ROOT_INDEX):
        return len(COLUMNS)

    def rowCount(self, parent=ROOT_INDEX):
        if parent.isValid():
            return len(parent.internalPointer().children) if parent.column() == 0 else 0
        return len(self.rows)

    def index(self, row, column, parent=ROOT_INDEX):
        if not self.hasIndex(row, column, parent):
            return QModelIndex()
        rows = parent.internalPointer().children if parent.isValid() else self.rows
        return self.createIndex(row, column, rows[row])

    def parent(self, index):
        if index.isValid() and (parent := index.internalPointer().parent) is not None:
            return self.createIndex(parent.position, 0, parent)
        return QModelIndex()

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = index.internalPointer()
        if role == ROLE:
            return row.payload
        if role == Qt.ItemDataRole.DisplayRole:
            return row.values[index.column()]
        if role == Qt.ItemDataRole.ToolTipRole:
            return row.tooltip if index.column() == 0 and row.tooltip else row.values[index.column()]
        if role == Qt.ItemDataRole.FontRole and row.parent is None and index.column() == 0:
            return self.bold
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.tr(COLUMNS[section]) if 0 <= section < len(COLUMNS) else None
        return None

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        attachment = index.internalPointer().payload.get("attachment")
        if attachment and attachment["state"] == "original":
            flags |= Qt.ItemFlag.ItemIsDragEnabled
        return flags

    def replace(self, records, libraries, mode):
        snapshot = (records, libraries, mode, self.tr.language)
        if self.snapshot == snapshot:
            return False
        rows = []
        for record in records:
            originals = [a for a in record["attachments"] if a["state"] == "original"]
            shown = (
                originals
                if mode == "all"
                else [
                    a
                    for a in record["attachments"]
                    if (
                        a["state"] == mode
                        if mode in {"review", "translated"}
                        else a["status"] != "available" and a["state"] != "excluded"
                    )
                ]
            )
            primary = next((a for a in originals if a["key"] == record["primary_key"]), None)
            payload = {
                "instance": record["instance"],
                "library": record["library"],
                "document_key": record["key"],
                "attachment": primary,
                "is_document": True,
                "title": record["title"],
                "authors": record["authors"],
                "year": record["year"],
                "doi": record["doi"],
                "original_path": (primary or {}).get("path", ""),
                "card_state": record.get("card_state", "card_unknown"),
            }
            values = (
                record["title"],
                record["authors"],
                record["year"],
                record["doi"],
                record["type"].lstrip(".").upper(),
                record["filename"],
                human_size(record["size"]),
                libraries.get(record["library"], record["library"]),
                self.tr(record["status"]),
                self.tr(payload["card_state"]),
            )
            node = Row(len(rows), tuple(map(str, values)), payload)
            for attachment in shown:
                child_values = (
                    attachment["filename"],
                    "",
                    "",
                    "",
                    attachment["filename"].rsplit(".", 1)[-1].upper(),
                    attachment["filename"],
                    human_size(attachment["size"]),
                    self.tr(attachment["state"]),
                    self.tr(attachment["status"]),
                    "",
                )
                node.children.append(
                    Row(
                        len(node.children),
                        tuple(map(str, child_values)),
                        {**payload, "attachment": attachment, "is_document": False},
                        node,
                        tooltip=self.tr.reason(attachment["reason"]) + "\n" + attachment["path"],
                    )
                )
            rows.append(node)
        self.beginResetModel()
        self.rows, self.snapshot = rows, snapshot
        self.endResetModel()
        return True
