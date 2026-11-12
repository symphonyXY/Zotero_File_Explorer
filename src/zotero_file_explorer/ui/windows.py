from __future__ import annotations

import logging

from PySide6.QtCore import QByteArray, QEvent, Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QPushButton,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..storage.index import SearchFilter
from .motion import FeedbackLabel
from .paper_view import COLUMNS, PaperView
from .theme import ui_icon

DEFAULT_WIDTHS = [420, 140, 68, 180, 65, 240, 85, 140, 150]
DEFAULT_ORDER = [0, 1, 2, 4, 8, 5, 6, 7, 3]
DEFAULT_HIDDEN = [3, 5, 6, 7]


class SearchWindow(QMainWindow):
    """Keep retained results visible, but actionable only for the current query."""

    def __init__(self, controller):
        super().__init__()
        self.controller, self.tr = controller, controller.tr
        self.generation = 0
        self.displayed_generation = -1
        self.search_pending = True
        self.search_failed = False
        self.action_buttons = {}
        self.preedit_active = False
        self.operation_text = ""
        self.operation_timer = QTimer(self)
        self.operation_timer.setSingleShot(True)
        self.operation_timer.timeout.connect(self.clear_operation_feedback)
        self.layout_key = ""

    @property
    def results_ready(self):
        return (
            not self.search_pending and not self.search_failed and not self.debounce.isActive()
            and self.displayed_generation == self.generation
        )

    def add_search_feedback(self, layout):
        self.empty_label = self.view.empty_label
        self.search.installEventFilter(self)
        self.search.setAccessibleName(self.tr("search_name"))
        self.search.setAccessibleDescription(self.tr("search"))
        self.search.setToolTip(self.tr("search"))
        row = QHBoxLayout()
        self.search_status = FeedbackLabel(self.controller.motion.policy)
        self.search_status.setMinimumWidth(0)
        row.addWidget(self.search_status, 1)
        self.retry = QPushButton(self.tr("retry"))
        self.retry.clicked.connect(self.query)
        size_policy = self.retry.sizePolicy()
        size_policy.setRetainSizeWhenHidden(True)
        self.retry.setSizePolicy(size_policy)
        self.search_status.setMinimumHeight(max(
            self.search_status.fontMetrics().lineSpacing() * 2, self.retry.sizeHint().height(),
        ))
        row.addWidget(self.retry)
        layout.addLayout(row)
        self.retry.hide()
        self.view.set_message(self.tr("searching"))
        self.render_feedback()

    def render_feedback(self, *, animate=False):
        counts = self.tr(
            "counts", count=getattr(self, "total", 0), shown=self.view.model_data.rowCount(),
            selected=len(self.view.selected_data()),
        )
        if self.search_pending or self.search_failed:
            text = self.tr("search_failed" if self.search_failed else "searching")
            if self.view.model_data.rowCount():
                text += "\n" + self.tr("retained_counts", counts=counts)
        else:
            text = counts
        if self.operation_text:
            text = self.operation_text + "\n" + text
        self.search_status.set_message(text, animate=animate)

    def set_operation_feedback(self, text, *, timeout=8000):
        self.operation_timer.stop()
        self.operation_text = text
        self.render_feedback(animate=True)
        if timeout:
            self.operation_timer.start(timeout)

    def clear_operation_feedback(self):
        self.operation_timer.stop()
        self.operation_text = ""
        self.render_feedback()

    def update_counts(self, *_):
        self.render_feedback()
        self.update_search_controls()

    def restore_layout(self, key):
        self.layout_key = key
        layouts = self.controller.settings.window_layouts
        state = layouts.get(key, {}) if isinstance(layouts, dict) else {}
        if not isinstance(state, dict):
            return
        restorers = [("geometry", self.restoreGeometry), ("header", self.view.header().restoreState)]
        for name, restore in restorers:
            value = state.get(name)
            if isinstance(value, str) and len(value) <= 32768:
                try:
                    restore(QByteArray(bytes.fromhex(value)))
                except ValueError:
                    pass
        self.view.auto_title_width = state.get("auto_title", True) is not False
        if hasattr(self, "splitter"):
            sizes = state.get("splitter")
            if (
                isinstance(sizes, list) and len(sizes) == 2
                and all(type(n) is int and 0 < n < 100000 for n in sizes)
            ):
                self.splitter.setSizes(sizes)
            # Sort/filter state is deliberately independent of the persisted layout.
            self.view.header().setSortIndicator(COLUMNS.index(self.sort), Qt.SortOrder.AscendingOrder)
        self.view.fit_title_column()

    def remember_layout(self):
        if not self.layout_key:
            return
        state = {
            "geometry": bytes(self.saveGeometry()).hex(),
            "header": bytes(self.view.header().saveState()).hex(),
            "auto_title": self.view.auto_title_width,
        }
        if hasattr(self, "splitter"):
            state["splitter"] = self.splitter.sizes()
        settings = self.controller.settings
        if not isinstance(settings.window_layouts, dict):
            settings.window_layouts = {}
        if settings.window_layouts.get(self.layout_key) == state:
            return
        settings.window_layouts[self.layout_key] = state
        try:
            self.controller.config.save(settings)
        except OSError:
            logging.getLogger("zfe").warning("Could not save window layout")

    def hideEvent(self, event):
        self.remember_layout()
        super().hideEvent(event)

    def invalidate_search(self):
        # Invalidate immediately, including the debounce interval before a worker starts.
        self.generation += 1
        self.search_started()

    def search_started(self):
        self.search_pending, self.search_failed = True, False
        self.render_feedback()
        self.view.set_message(self.tr("searching"))
        self.update_search_controls()

    def search_finished(self, error=None):
        self.search_pending, self.search_failed = False, error is not None
        self.render_feedback(animate=True)
        if error:
            self.view.set_message(self.tr("search_failed"))
        self.update_search_controls()

    def update_search_controls(self):
        self.retry.setVisible(self.search_failed)
        for key, button in self.action_buttons.items():
            if not self.results_ready:
                button.setEnabled(False)
                continue
            attachments = self.view.selected_attachments(originals_only=key == "copy_files")
            button.setEnabled(any(
                a["path"] and a["status"] == "available" for a in attachments
            ))

    def eventFilter(self, obj, event):
        if obj is self.search:
            if event.type() == QEvent.Type.InputMethod:
                self.preedit_active = bool(event.preeditString())
            elif event.type() == QEvent.Type.FocusOut:
                self.preedit_active = False
            elif event.type() == QEvent.Type.KeyPress and not self.preedit_active:
                if event.key() in {Qt.Key.Key_Down, Qt.Key.Key_Return, Qt.Key.Key_Enter}:
                    if self.results_ready and self.view.model_data.rowCount():
                        if not self.view.currentIndex().isValid() or event.key() == Qt.Key.Key_Down:
                            self.view.setCurrentIndex(self.view.model_data.index(0, 0))
                        if event.key() == Qt.Key.Key_Down:
                            self.view.setFocus()
                        else:
                            self.controller.file_action("open", self.view)
                    return True
        return super().eventFilter(obj, event)


class MainWindow(SearchWindow):
    def __init__(self, controller):
        super().__init__(controller)
        self.setProperty("zfeMotion", True)
        self.controller = controller
        self.tr = controller.tr
        self.setWindowIcon(controller.icon)
        self.setWindowTitle(self.tr("app"))
        self.resize(1240, 780)
        self.setMinimumSize(940, 580)
        self.mode = "all"
        self.nav_library = ""
        self.collection = ""
        self.total = 0
        self.limit = 500
        self.offset = 0
        self.sort = "title"
        self.descending = False
        outer = QWidget()
        self.setCentralWidget(outer)
        layout = QHBoxLayout(outer)
        layout.setContentsMargins(16, 20, 16, 8)
        layout.setSpacing(0)
        splitter = self.splitter = QSplitter()
        splitter.setHandleWidth(12)
        layout.addWidget(splitter)
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setMinimumWidth(200)
        left = QVBoxLayout(sidebar)
        left.setContentsMargins(16, 20, 16, 16)
        left.setSpacing(10)
        brand_row = QHBoxLayout()
        mark = QLabel()
        mark.setPixmap(controller.icon.pixmap(36, 36))
        brand_row.addWidget(mark)
        brand = QLabel("Zotero\nFile Explorer")
        brand.setObjectName("brand")
        brand_row.addWidget(brand, 1)
        left.addLayout(brand_row)
        subtitle = QLabel(self.tr("subtitle"))
        subtitle.setObjectName("muted")
        left.addWidget(subtitle)
        navigation_caption = QLabel(self.tr("navigation"))
        navigation_caption.setObjectName("sectionCaption")
        left.addWidget(navigation_caption)
        self.navigation = QTreeWidget()
        self.navigation.setObjectName("navigation")
        self.navigation.setAccessibleName(self.tr("navigation"))
        self.navigation.setHeaderHidden(True)
        self.navigation.setIndentation(14)
        self.navigation.currentItemChanged.connect(
            lambda item, previous: self.navigate(item) if item else None
        )
        left.addWidget(self.navigation, 1)
        tools_caption = QLabel(self.tr("tools"))
        tools_caption.setObjectName("sectionCaption")
        left.addWidget(tools_caption)
        for key, callback, icon in [
            ("quick", controller.show_quick, "quick"),
            ("rules", controller.show_rules, "rules"),
            ("rebuild", controller.rebuild_index, "refresh"),
            ("settings", controller.show_settings, "settings"),
        ]:
            button = QPushButton(self.tr(key))
            button.setObjectName("sidebarAction")
            button.setIcon(ui_icon(icon))
            button.clicked.connect(callback)
            left.addWidget(button)
        splitter.addWidget(sidebar)
        content = QWidget()
        content.setObjectName("contentPanel")
        right = QVBoxLayout(content)
        right.setContentsMargins(20, 20, 20, 16)
        right.setSpacing(12)
        top = QHBoxLayout()
        title_block = QVBoxLayout()
        title_block.setSpacing(2)
        caption = QLabel(self.tr("workspace"))
        caption.setObjectName("sectionCaption")
        title_block.addWidget(caption)
        self.heading = QLabel(self.tr("all"))
        self.heading.setObjectName("heading")
        title_block.addWidget(self.heading)
        top.addLayout(title_block, 1)
        self.copy_button = QPushButton(self.tr("copy_files") + "  Ctrl+C")
        self.copy_button.setEnabled(False)
        self.copy_button.setObjectName("primary")
        self.copy_button.setToolTip(self.tr("select_original"))
        self.copy_button.clicked.connect(lambda: controller.file_action("copy_files", self.view))
        self.action_buttons["copy_files"] = self.copy_button
        top.addWidget(self.copy_button)
        self.sync_button = QPushButton(self.tr("refresh"))
        self.sync_button.setIcon(ui_icon("refresh"))
        self.sync_button.clicked.connect(lambda: controller.synchronize(force_paths=True))
        top.addWidget(self.sync_button)
        right.addLayout(top)
        self.connection_label = QLabel(self.tr("reconnecting"))
        self.connection_label.setObjectName("connectionStatus")
        self.connection_label.setWordWrap(True)
        right.addWidget(self.connection_label)
        self.search = QLineEdit()
        self.search.setObjectName("searchInput")
        self.search.setClearButtonEnabled(True)
        self.search.setPlaceholderText(self.tr("search"))
        self.search.setMinimumHeight(28)
        search_row = QHBoxLayout()
        search_row.addWidget(self.search, 1)
        search_hint = QLabel("Ctrl F")
        search_hint.setObjectName("keycap")
        search_row.addWidget(search_hint)
        right.addLayout(search_row)
        filters = QHBoxLayout()
        self.library = QComboBox()
        self.library.setAccessibleName(self.tr("library"))
        self.library.setMinimumWidth(150)
        self.library.addItem(self.tr("all_libraries"), "")
        filters.addWidget(self.filter_field("library", self.library), 2)
        self.file_type = QComboBox()
        self.file_type.setAccessibleName(self.tr("type"))
        self.file_type.addItem(self.tr("all_types"), "")
        for suffix in [".pdf", ".doc", ".docx", ".epub"]:
            self.file_type.addItem(suffix[1:].upper(), suffix)
        filters.addWidget(self.filter_field("type", self.file_type))
        self.year = QLineEdit()
        self.year.setAccessibleName(self.tr("year"))
        self.year.setToolTip(self.tr("year"))
        self.year.setPlaceholderText("YYYY")
        self.year.setMaximumWidth(85)
        filters.addWidget(self.filter_field("year", self.year))
        self.tag = QLineEdit()
        self.tag.setAccessibleName(self.tr("tag"))
        self.tag.setToolTip(self.tr("tag"))
        self.tag.setPlaceholderText(self.tr("any_tag"))
        self.tag.setMaximumWidth(140)
        filters.addWidget(self.filter_field("tag", self.tag))
        self.available = QCheckBox(self.tr("available_only"))
        filters.addWidget(self.available, 0, Qt.AlignmentFlag.AlignBottom)
        right.addLayout(filters)
        self.view = PaperView(self.tr)
        for column, width in enumerate(DEFAULT_WIDTHS):
            self.view.setColumnWidth(column, width)
        for position, column in enumerate(DEFAULT_ORDER):
            self.view.header().moveSection(self.view.header().visualIndex(column), position)
        self.view.actionRequested.connect(lambda key: controller.file_action(key, self.view))
        self.view.copyRequested.connect(lambda: controller.file_action("copy_files", self.view))
        self.view.operationError.connect(controller.notice)
        self.view.sortRequested.connect(self.set_sort)
        self.view.selectionModel().selectionChanged.connect(self.update_counts)
        right.addWidget(self.view, 1)
        footer = QHBoxLayout()
        self.add_search_feedback(footer)
        self.previous = QPushButton(self.tr("previous"))
        self.previous.clicked.connect(self.load_previous)
        footer.addWidget(self.previous)
        self.more = QPushButton(self.tr("more"))
        self.more.clicked.connect(self.load_more)
        footer.addWidget(self.more)
        columns = QPushButton(self.tr("columns"))
        menu = QMenu(columns)
        self.column_actions = {}
        for column, key in enumerate(COLUMNS):
            action = QAction(self.tr(key), menu)
            action.setCheckable(True)
            action.setChecked(column not in controller.settings.hidden_columns)
            action.setEnabled(column != 0)
            action.toggled.connect(lambda shown, col=column: self.toggle_column(col, shown))
            menu.addAction(action)
            self.column_actions[column] = action
            self.view.setColumnHidden(column, not action.isChecked())
        menu.addSeparator()
        menu.addAction(self.tr("reset_layout"), self.reset_layout)
        columns.setMenu(menu)
        footer.addWidget(columns)
        right.addLayout(footer)
        splitter.addWidget(content)
        splitter.setSizes([230, 990])
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        self.statusBar().showMessage(self.tr("read_only"))
        self.debounce = QTimer(self)
        self.debounce.setSingleShot(True)
        self.debounce.setInterval(180)
        self.debounce.timeout.connect(self.query)
        for widget in [self.search, self.year, self.tag]:
            widget.textChanged.connect(self.filters_changed)
        self.library.currentIndexChanged.connect(self.library_changed)
        self.file_type.currentIndexChanged.connect(self.filters_changed)
        self.available.toggled.connect(self.filters_changed)
        shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        shortcut.activated.connect(self.search.setFocus)
        shortcut = QShortcut(QKeySequence("F5"), self)
        shortcut.activated.connect(lambda: controller.synchronize(force_paths=True))
        shortcut = QShortcut(QKeySequence("Ctrl+Q"), self)
        shortcut.activated.connect(controller.quit)
        self.update_search_controls()
        self.restore_layout("main")
        # Column visibility in existing settings takes precedence over saved header state.
        for column, action in self.column_actions.items():
            self.view.setColumnHidden(column, not action.isChecked())
        self.reload_navigation()

    def filter_field(self, key, widget):
        field = QWidget()
        field_layout = QVBoxLayout(field)
        field_layout.setContentsMargins(0, 0, 0, 0)
        field_layout.setSpacing(5)
        label = QLabel(self.tr(key))
        label.setObjectName("filterCaption")
        label.setBuddy(widget)
        field_layout.addWidget(label)
        field_layout.addWidget(widget)
        return field

    def toggle_column(self, column, shown):
        self.view.setColumnHidden(column, not shown)
        self.view.fit_title_column()
        self.controller.settings.hidden_columns = [
            c for c in range(1, len(COLUMNS)) if self.view.isColumnHidden(c)
        ]
        self.controller.config.save(self.controller.settings)

    def reset_layout(self):
        for position, column in enumerate(DEFAULT_ORDER):
            self.view.header().moveSection(self.view.header().visualIndex(column), position)
        for column, width in enumerate(DEFAULT_WIDTHS):
            self.view.setColumnWidth(column, width)
            action = self.column_actions[column]
            action.blockSignals(True)
            action.setChecked(column not in DEFAULT_HIDDEN)
            action.blockSignals(False)
            self.view.setColumnHidden(column, column in DEFAULT_HIDDEN)
        self.controller.settings.hidden_columns = DEFAULT_HIDDEN.copy()
        self.view.auto_title_width = True
        self.splitter.setSizes([230, 990])
        self.resize(1240, 780)
        self.view.fit_title_column()
        self.remember_layout()

    def reload_navigation(self):
        self.controller.load_navigation(self)

    def apply_navigation(self, libraries, all_collections):
        self.navigation.blockSignals(True)
        selected = (self.mode, self.nav_library, self.collection)
        self.navigation.clear()
        self.library.blockSignals(True)
        old_library = self.library.currentData()
        self.library.clear()
        self.library.addItem(self.tr("all_libraries"), "")
        self.add_nav(self.tr("all"), ("all", "", ""))
        group_root = None
        for library in libraries:
            name = self.tr("personal") if library["name"] == "personal" else library["name"]
            self.library.addItem(name, library["id"])
            if library["id"].startswith("group:"):
                if group_root is None:
                    group_root = self.add_nav(self.tr("groups"), None)
                root = self.add_nav(name, ("all", library["id"], ""), group_root)
            else:
                root = self.add_nav(name, ("all", library["id"], ""))
            self.add_nav(self.tr("unfiled"), ("all", library["id"], "__unfiled__"), root)
            collection_root = self.add_nav(self.tr("collections"), None, root)
            nodes = {}
            remaining = [c for c in all_collections if c["library"] == library["id"]]
            # Missing parents/cycles cannot make the UI loop or hide all collections.
            while remaining:
                ready = [c for c in remaining if not c["parent"] or c["parent"] in nodes]
                if not ready:
                    ready = remaining[:1]
                for collection in ready:
                    parent = nodes.get(collection["parent"], collection_root)
                    nodes[collection["key"]] = self.add_nav(
                        collection["name"], ("all", library["id"], collection["key"]), parent
                    )
                    remaining.remove(collection)
            root.setExpanded(True)
            collection_root.setExpanded(True)
        for key in ["review", "translated", "errors"]:
            self.add_nav(self.tr(key), (key, "", ""))
        self.library.setCurrentIndex(max(0, self.library.findData(old_library)))
        self.library.blockSignals(False)
        for item in self.navigation.findItems("*", Qt.MatchFlag.MatchWildcard | Qt.MatchFlag.MatchRecursive):
            if item.data(0, Qt.ItemDataRole.UserRole) == selected:
                self.navigation.setCurrentItem(item)
                break
        self.navigation.blockSignals(False)

    def add_nav(self, text, value, parent=None):
        item = QTreeWidgetItem([text])
        item.setToolTip(0, text)
        icon = value[0] if value and value[0] in {"review", "errors", "translated"} else "folder"
        item.setIcon(0, ui_icon(icon))
        item.setData(0, Qt.ItemDataRole.UserRole, value)
        (parent.addChild if parent else self.navigation.addTopLevelItem)(item)
        return item

    def navigate(self, item):
        value = item.data(0, Qt.ItemDataRole.UserRole)
        if value:
            self.mode, self.nav_library, self.collection = value
            self.heading.setText(item.text(0))
            # Navigation to a library updates the visible library filter too.
            self.library.setCurrentIndex(max(0, self.library.findData(self.nav_library)))
            self.filters_changed()

    def filters_changed(self, *_):
        self.limit = 500
        self.offset = 0
        self.invalidate_search()
        self.debounce.start()

    def library_changed(self, *_):
        if (self.library.currentData() or "") != self.nav_library:
            self.collection = ""
            self.nav_library = self.library.currentData() or ""
        self.filters_changed()

    def filters(self):
        return SearchFilter(
            text=self.search.text(),
            library=self.library.currentData() or "",
            collection=self.collection,
            file_type=self.file_type.currentData() or "",
            year=self.year.text().strip(),
            tag=self.tag.text().strip(),
            available=self.available.isChecked(),
            mode=self.mode,
            limit=self.limit,
            offset=self.offset,
            sort=self.sort,
            descending=self.descending,
        )

    def query(self):
        self.controller.search(self, self.filters())

    def display(self, rows, count, library_rows=(), instance=""):
        self.total = count
        libraries = {
            lib["id"]: self.tr("personal") if lib["name"] == "personal" else lib["name"]
            for lib in library_rows
        }
        self.view.populate(rows, libraries, self.mode)
        self.view.set_message(self.tr("first_run") if not instance else self.tr("empty"))
        self.more.setVisible(self.offset + len(rows) < count)
        self.previous.setVisible(self.offset > 0)
        self.update_counts()

    def update_search_controls(self):
        super().update_search_controls()
        self.previous.setEnabled(self.results_ready and self.offset > 0)
        self.more.setEnabled(self.results_ready and self.offset + self.limit < self.total)

    def load_more(self):
        if not self.results_ready or self.offset + self.limit >= self.total:
            return
        self.offset += self.limit
        self.query()

    def load_previous(self):
        if not self.results_ready or not self.offset:
            return
        self.offset = max(0, self.offset - self.limit)
        self.query()

    def set_sort(self, key, descending):
        self.sort, self.descending = key, descending
        self.query()

    def closeEvent(self, event):
        if self.controller.quitting:
            event.accept()
        elif self.controller.settings.close_to_tray and self.controller.tray.isVisible():
            event.ignore()
            self.hide()
        else:
            event.ignore()
            self.controller.quit()


class QuickWindow(SearchWindow):
    def __init__(self, controller):
        super().__init__(controller)
        self.setProperty("zfeMotion", True)
        self.setProperty("zfeQuickWindow", True)
        self.controller, self.tr = controller, controller.tr
        self.setWindowTitle(self.tr("app") + " · " + self.tr("quick"))
        self.setWindowIcon(controller.icon)
        self.resize(650, 480)
        self.setMinimumSize(450, 300)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, controller.settings.quick_on_top)
        widget = QWidget()
        widget.setObjectName("quickPanel")
        self.setCentralWidget(widget)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(18, 18, 18, 16)
        layout.setSpacing(10)
        bar = QHBoxLayout()
        label = QLabel(self.tr("quick"))
        label.setObjectName("brand")
        bar.addWidget(label, 1)
        self.on_top = QCheckBox(self.tr("top"))
        self.on_top.setChecked(controller.settings.quick_on_top)
        self.on_top.toggled.connect(self.toggle_top)
        bar.addWidget(self.on_top)
        button = QPushButton(self.tr("main"))
        button.clicked.connect(controller.show_main)
        bar.addWidget(button)
        layout.addLayout(bar)
        self.search = QLineEdit()
        self.search.setObjectName("searchInput")
        self.search.setPlaceholderText(self.tr("search"))
        self.search.setClearButtonEnabled(True)
        layout.addWidget(self.search)
        self.view = PaperView(self.tr, compact=True)
        self.view.setColumnWidth(0, 370)
        self.view.setColumnWidth(8, 170)
        self.view.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.view.header().setSectionResizeMode(8, QHeaderView.ResizeMode.ResizeToContents)
        for column in range(1, 8):
            self.view.setColumnHidden(column, True)
        self.view.actionRequested.connect(lambda key: controller.file_action(key, self.view))
        self.view.copyRequested.connect(lambda: controller.file_action("copy_files", self.view))
        self.view.operationError.connect(controller.notice)
        self.view.sortRequested.connect(lambda *_: self.query())
        self.view.selectionModel().selectionChanged.connect(self.update_counts)
        layout.addWidget(self.view, 1)
        self.add_search_feedback(layout)
        bar = QHBoxLayout()
        for key in ["copy_files", "open", "reveal"]:
            button = QPushButton(self.tr(key))
            button.setEnabled(False)
            if key == "copy_files":
                button.setObjectName("primary")
            self.action_buttons[key] = button
            button.setToolTip(self.tr("select_original" if key == "copy_files" else "select_attachment"))
            button.clicked.connect(
                lambda checked=False, operation=key: controller.file_action(operation, self.view)
            )
            bar.addWidget(button)
        layout.addLayout(bar)
        self.debounce = QTimer(self)
        self.debounce.setInterval(150)
        self.debounce.setSingleShot(True)
        self.debounce.timeout.connect(self.query)
        self.search.textChanged.connect(self.filters_changed)
        shortcut = QShortcut(QKeySequence("Escape"), self)
        shortcut.activated.connect(self.hide)
        self.restore_layout("quick")
        for column in range(1, 8):
            self.view.setColumnHidden(column, True)
        self.view.setColumnHidden(0, False)
        self.view.setColumnHidden(8, False)

    def filters_changed(self, *_):
        self.invalidate_search()
        self.debounce.start()

    def toggle_top(self, enabled):
        self.controller.settings.quick_on_top = enabled
        self.controller.config.save(self.controller.settings)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, enabled)
        self.show()

    def query(self):
        self.controller.search(self, SearchFilter(text=self.search.text(), limit=200))

    def display(self, rows, count, library_rows=(), instance=""):
        self.total = count
        self.view.populate(rows, {})
        self.view.set_message(self.tr("first_run") if not instance else self.tr("empty"))
        self.update_counts()

    def closeEvent(self, event):
        if self.controller.quitting:
            event.accept()
        else:
            event.ignore()
            self.hide()
