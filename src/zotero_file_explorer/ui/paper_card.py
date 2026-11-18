"""Paper details, Markdown editing and manual recall in a single document-bound window."""

from dataclasses import replace

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ..api.client import APIError
from ..core.paper_cards import CardTarget, card_template
from ..platform.files import open_file
from ..services.paper_cards import MultipleCards, new_card


class MarkdownPreview(QTextBrowser):
    def __init__(self):
        super().__init__()
        self.setOpenLinks(False)
        self.anchorClicked.connect(
            lambda url: QDesktopServices.openUrl(url) if url.scheme() in {"http", "https"} else None
        )

    def loadResource(self, resource_type, url):
        # A card may travel between machines. Preview only the Markdown itself.
        return None

    def render_card(self, text):
        lines = text.lstrip("\ufeff").splitlines()
        if lines[:1] == ["---"] and "---" in lines[1:]:
            lines = lines[lines.index("---", 1) + 1 :]
        self.setMarkdown("\n".join(lines))


class PaperCardDialog(QDialog):
    def __init__(self, controller, paper, service, *, details=False, create=False):
        super().__init__(controller.main)
        self.controller, self.tr = controller, controller.tr
        self.target = CardTarget(paper["instance"], paper["library"], paper["document_key"])
        self.service, self.drafts = service, controller.card_drafts
        self.draft = self.pending = None
        self.confirmed_keys = frozenset()
        self.busy = self.dirty = self.closing = False
        self.setWindowTitle(self.tr("card_state") + " · " + paper["title"])
        self.resize(760, 620)
        self.setWindowModality(Qt.WindowModality.WindowModal)
        outer = QVBoxLayout(self)
        heading = QLabel(paper["title"])
        heading.setTextFormat(Qt.TextFormat.PlainText)
        heading.setWordWrap(True)
        heading.setObjectName("brand")
        outer.addWidget(heading)
        byline = QLabel(" · ".join(filter(None, [paper["authors"], paper["year"]])))
        byline.setTextFormat(Qt.TextFormat.PlainText)
        byline.setWordWrap(True)
        outer.addWidget(byline)
        tabs = QTabWidget()
        outer.addWidget(tabs, 1)
        info = QWidget()
        form = QFormLayout(info)
        attachment = paper.get("attachment") or {}
        for label, value in [
            ("doi", paper["doi"]),
            ("title", paper["title"]),
            ("attachment_title", attachment.get("title")),
            ("filename", attachment.get("filename")),
            ("path", attachment.get("path") or self.tr("no_path")),
            ("status", self.tr(attachment["status"]) if attachment else ""),
            ("result", self.tr(attachment["state"]) if attachment else ""),
            ("reason", self.tr.reason(attachment["reason"]) if attachment else ""),
        ]:
            if value:
                field = QLabel(value)
                field.setTextFormat(Qt.TextFormat.PlainText)
                field.setWordWrap(True)
                field.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                form.addRow(self.tr(label), field)
        tabs.addTab(info, self.tr("details"))
        page = QWidget()
        tabs.addTab(page, "Paper Card")
        tabs.setCurrentIndex(0 if details else 1)
        layout = QVBoxLayout(page)
        bar = QHBoxLayout()
        self.mode = QComboBox()
        for key in ["card_preview", "card_edit", "card_recall"]:
            self.mode.addItem(self.tr(key))
        bar.addWidget(self.mode)
        bar.addStretch()
        self.create = QPushButton(self.tr("card_create"))
        self.create.clicked.connect(self.start_create)
        bar.addWidget(self.create)
        self.save = QPushButton(self.tr("card_save"))
        self.save.setObjectName("primary")
        self.save.clicked.connect(self.commit)
        bar.addWidget(self.save)
        layout.addLayout(bar)
        self.stack = QStackedWidget()
        self.preview, self.editor = MarkdownPreview(), QPlainTextEdit()
        self.editor.setAccessibleName(self.tr("card_edit"))
        self.stack.addWidget(self.preview)
        self.stack.addWidget(self.editor)
        recall = QWidget()
        recall_layout = QVBoxLayout(recall)
        recall_layout.addWidget(QLabel(self.tr("card_prompt")))
        self.reveal = QPushButton(self.tr("card_reveal"))
        self.reveal.setCheckable(True)
        recall_layout.addWidget(self.reveal)
        self.answer = MarkdownPreview()
        recall_layout.addWidget(self.answer, 1)
        self.answer.hide()
        self.stack.addWidget(recall)
        layout.addWidget(self.stack, 1)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        footer = QHBoxLayout()
        self.retry = QPushButton(self.tr("retry"))
        self.retry.clicked.connect(lambda: self.load())
        self.merge = QPushButton(self.tr("card_compare"))
        self.merge.clicked.connect(self.compare)
        self.discard = QPushButton(self.tr("card_discard"))
        self.discard.clicked.connect(self.discard_draft)
        for button in (self.retry, self.merge, self.discard):
            footer.addWidget(button)
        footer.addStretch()
        original = QPushButton(self.tr("card_original"))
        original.setEnabled(bool(paper.get("original_path")))
        path = paper.get("original_path")
        original.clicked.connect(
            lambda: controller.submit(
                lambda: open_file(path),
                lambda ok, err: controller.notice("no_available_files") if err or not ok else None,
            )
        )
        footer.addWidget(original)
        layout.addLayout(footer)
        self.create.hide()
        self.retry.hide()
        self.merge.hide()
        self.discard.hide()
        self.editor.textChanged.connect(self.edited)
        self.mode.currentIndexChanged.connect(self.change_mode)
        self.reveal.toggled.connect(self.recalled)
        shortcut = QShortcut(QKeySequence.StandardKey.Save, self)
        shortcut.activated.connect(self.commit)
        self.poll = QTimer(self)
        self.poll.setInterval(150)
        self.poll.timeout.connect(self.check_draft)
        if details:

            def tab_opened(index):
                if index == 1:
                    tabs.currentChanged.disconnect(tab_opened)
                    self.load()

            tabs.currentChanged.connect(tab_opened)
        else:
            self.load(create)

    def store(self, value):
        self.pending = self.drafts.put(self.target, value)
        self.poll.start()
        return self.pending

    def controls(self):
        self.mode.setEnabled(bool(self.draft) and not self.busy)
        self.save.setEnabled(bool(self.draft) and self.dirty and not self.busy)
        self.editor.setReadOnly(self.busy or not self.draft)
        self.create.setEnabled(not self.busy)
        self.discard.setVisible(self.dirty and not self.busy)
        self.retry.setEnabled(not self.busy)
        self.merge.setEnabled(not self.busy)

    def task(self, function, complete):
        self.busy = True
        self.controls()

        def finished(value, error):
            self.busy = False
            if error:
                self.fail(error)
            else:
                complete(value)
            self.controls()

        self.controller.submit(function, finished)

    def fail(self, error):
        message = str(error) if isinstance(error, APIError) else ""
        label = self.tr("card_save_failed" if self.dirty else "card_read_error")
        self.status.setText(label + (" · " + self.tr(message) if message else ""))
        self.merge.setVisible(self.dirty and message == "card_conflict")
        self.retry.setVisible(not self.dirty)
        if isinstance(error, MultipleCards) and self.dirty and not self.closing:
            answer = QMessageBox.question(
                self,
                "Paper Card",
                self.tr("card_confirm_target", key=self.draft.attachment),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer == QMessageBox.StandardButton.Yes:
                self.confirmed_keys = error.keys
                self.commit()

    def load(self, create=False):
        self.retry.hide()
        self.create.hide()
        self.merge.hide()
        self.status.setText(self.tr("card_loading"))

        def fetch():
            local = self.drafts.load(self.target)
            return (local, []) if local else (None, self.service.candidates(self.target))

        def loaded(result):
            if self.closing:
                return
            local, cards = result
            if local:
                self.set_draft(local, dirty=True)
                self.status.setText(self.tr("card_restored"))
                return
            if not cards:
                self.create.show()
                self.status.setText(self.tr("card_none"))
                if create:
                    self.start_create()
                return
            key = cards[0].key
            if len(cards) > 1:
                options = [f"{c.title} · {c.key}" for c in cards]
                choice, ok = QInputDialog.getItem(
                    self, "Paper Card", self.tr("card_choose"), options, 0, False
                )
                if not ok:
                    self.status.setText(self.tr("card_multiple"))
                    self.retry.show()
                    return
                key = cards[options.index(choice)].key
                self.confirmed_keys = frozenset(c.key for c in cards)
            self.task(lambda: self.service.read(self.target, key), self.set_draft)

        self.task(fetch, loaded)

    def set_draft(self, value, dirty=False):
        self.draft, self.dirty = value, dirty
        self.editor.blockSignals(True)
        self.editor.setPlainText(value.text)
        self.editor.blockSignals(False)
        self.mode.setCurrentIndex(1 if dirty else 0)
        self.change_mode(self.mode.currentIndex())
        self.status.setText(self.tr("card_editing" if dirty else "card_loaded"))
        self.controls()

    def start_create(self):
        self.create.hide()
        self.set_draft(new_card(card_template(self.tr.language == "en")), dirty=True)
        self.commit()

    def edited(self):
        if self.draft is None:
            return
        self.draft = replace(self.draft, text=self.editor.toPlainText())
        self.dirty = True
        self.store(self.draft)
        self.status.setText(self.tr("card_editing"))
        self.controls()

    def change_mode(self, index):
        self.stack.setCurrentIndex(index)
        self.reveal.setChecked(False)
        if index == 0 and self.draft:
            self.preview.render_card(self.draft.text)

    def recalled(self, show):
        if show and self.draft:
            self.answer.render_card(self.draft.text)
        self.answer.setVisible(show)
        self.reveal.setText(self.tr("card_hide" if show else "card_reveal"))

    def commit(self):
        if self.busy or not self.dirty:
            return
        draft = self.draft
        confirmed = self.confirmed_keys
        self.status.setText(self.tr("card_saving"))
        self.merge.hide()
        pending = self.store(draft)

        def write():
            pending.result()
            saved = self.service.save(self.target, draft, confirmed)
            self.drafts.put(self.target, None).result()
            return saved

        def saved(value):
            self.set_draft(value)
            if draft.creating:
                self.mode.setCurrentIndex(1)
                self.editor.setFocus()
            self.status.setText(self.tr("card_saved"))
            self.controller.refresh_after_card()

        self.task(write, saved)

    def compare(self):
        def merge(latest):
            if self.closing:
                return
            dialog = QDialog(self)
            dialog.setWindowTitle(self.tr("card_compare"))
            dialog.resize(700, 550)
            box = QVBoxLayout(dialog)
            box.addWidget(QLabel(self.tr("card_current")))
            remote = QPlainTextEdit(latest.text)
            remote.setReadOnly(True)
            box.addWidget(remote)
            box.addWidget(QLabel(self.tr("card_merge_edit")))
            merged = QPlainTextEdit(self.draft.text)
            box.addWidget(merged)
            buttons = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
            )
            buttons.accepted.connect(dialog.accept)
            buttons.rejected.connect(dialog.reject)
            box.addWidget(buttons)
            if dialog.exec():
                self.set_draft(replace(latest, text=merged.toPlainText()), dirty=True)
                self.store(self.draft)
                self.merge.hide()

        self.task(lambda: self.service.read(self.target, self.draft.attachment), merge)

    def discard_draft(self):
        if (
            QMessageBox.question(self, "Paper Card", self.tr("card_confirm_discard"))
            != QMessageBox.StandardButton.Yes
        ):
            return
        self.store(None)

        def reload(_):
            self.draft, self.dirty = None, False
            self.editor.clear()
            self.preview.clear()
            self.mode.setCurrentIndex(0)
            self.load()

        self.task(self.pending.result, reload)

    def check_draft(self):
        if self.pending and self.pending.done():
            if self.pending.exception():
                self.poll.stop()
                self.status.setText(self.tr("card_draft_error"))
                self.closing = False
                return
            self.pending = None
        if self.closing and self.pending is None and not self.busy:
            super().reject()
        if self.pending is None and not self.closing:
            self.poll.stop()

    def reject(self):
        if self.busy or self.pending:
            self.closing = True
            self.poll.start()
            self.check_draft()
        else:
            super().reject()
