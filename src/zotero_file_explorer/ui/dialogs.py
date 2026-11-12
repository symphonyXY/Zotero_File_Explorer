from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core.classification import FilterRule, default_rules, rule_to_dict
from ..core.models import Record
from ..platform.windows import autostart_enabled, parse_hotkey
from ..services.paths import detected_directories
from ..storage.config import Settings


class RulesDialog(QDialog):
    def __init__(self, settings: Settings, tr, parent=None):
        super().__init__(parent)
        self.tr = tr
        self.setWindowTitle(tr("rules"))
        self.resize(850, 480)
        layout = QVBoxLayout(self)
        help_text = QLabel(tr("rule_help"))
        help_text.setWordWrap(True)
        layout.addWidget(help_text)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            [tr(k) for k in ["enabled", "name", "pattern", "target", "result"]]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)
        bar = QHBoxLayout()
        for key, callback in [
            ("add", lambda: self.add_rule({"name": "", "pattern": "*.translated.pdf"})),
            ("delete", self.remove_rule),
            ("defaults", self.restore_defaults),
        ]:
            button = QPushButton(tr(key))
            button.clicked.connect(callback)
            bar.addWidget(button)
        bar.addStretch()
        layout.addLayout(bar)
        self.sample_file = QLineEdit()
        self.sample_file.setPlaceholderText(tr("test_filename"))
        self.sample_title = QLineEdit()
        self.sample_title.setPlaceholderText(tr("test_title"))
        bar = QHBoxLayout()
        bar.addWidget(self.sample_file)
        bar.addWidget(self.sample_title)
        button = QPushButton(tr("test"))
        button.clicked.connect(self.test_rules)
        bar.addWidget(button)
        layout.addLayout(bar)
        self.preview = QLabel()
        self.preview.setWordWrap(True)
        layout.addWidget(self.preview)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText(tr("save"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("cancel"))
        buttons.accepted.connect(self.accept_validated)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        for rule in settings.rules:
            self.add_rule(rule)

    def add_rule(self, raw):
        row = self.table.rowCount()
        self.table.insertRow(row)
        checkbox = QTableWidgetItem()
        checkbox.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
        checkbox.setCheckState(Qt.CheckState.Checked if raw.get("enabled", True) else Qt.CheckState.Unchecked)
        self.table.setItem(row, 0, checkbox)
        for col, field_name in [(1, "name"), (2, "pattern")]:
            self.table.setItem(row, col, QTableWidgetItem(raw.get(field_name, "")))
        for col, fields, selected in [
            (3, ["filename", "title"], raw.get("target", "filename")),
            (4, ["translated", "original", "review"], raw.get("state", "translated")),
        ]:
            combo = QComboBox()
            for value in fields:
                combo.addItem(self.tr(value), value)
            combo.setCurrentIndex(max(0, combo.findData(selected)))
            self.table.setCellWidget(row, col, combo)

    def remove_rule(self):
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)

    def restore_defaults(self):
        self.table.setRowCount(0)
        for rule in default_rules():
            self.add_rule(rule)

    def rules(self):
        return [
            rule_to_dict(
                FilterRule(
                    name=self.table.item(r, 1).text().strip(),
                    pattern=self.table.item(r, 2).text(),
                    target=self.table.cellWidget(r, 3).currentData(),
                    state=self.table.cellWidget(r, 4).currentData(),
                    enabled=self.table.item(r, 0).checkState() == Qt.CheckState.Checked,
                )
            )
            for r in range(self.table.rowCount())
        ]

    def test_rules(self):
        try:
            sample = Record(
                "SAMPLE01", "attachment", filename=self.sample_file.text(), title=self.sample_title.text()
            )
            results = [rule for raw in self.rules() if (rule := FilterRule(**raw)).matches(sample)]
            self.preview.setText(
                "; ".join(r.name + " → " + self.tr(r.state) for r in results)
                if results
                else self.tr("no_rule_match")
            )
        except ValueError:
            self.preview.setText(self.tr("invalid_settings"))

    def accept_validated(self):
        try:
            self.rules()
            self.accept()
        except ValueError:
            QMessageBox.warning(self, self.tr("error"), self.tr("invalid_settings"))


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, tr, parent=None, submit=None):
        super().__init__(parent)
        self.submit = submit
        self.settings = settings
        self.tr = tr
        self.setWindowTitle(tr("settings"))
        self.resize(700, 520)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)
        self.language = QComboBox()
        self.language.addItem("简体中文", "zh_CN")
        self.language.addItem("English", "en")
        self.language.setCurrentIndex(self.language.findData(settings.language))
        form.addRow(tr("language"), self.language)
        self.theme = QComboBox()
        for value in ["system", "light", "dark"]:
            self.theme.addItem(tr(value), value)
        self.theme.setCurrentIndex(self.theme.findData(settings.theme))
        form.addRow(tr("theme"), self.theme)
        self.motion = QComboBox()
        for value in ["full", "reduced", "off"]:
            self.motion.addItem(tr("motion_" + value), value)
        self.motion.setCurrentIndex(self.motion.findData(settings.motion))
        form.addRow(tr("motion"), self.motion)
        self.animation_speed = QComboBox()
        for value in sorted({0.5, 1.0, 1.5, 2.0, settings.animation_speed}):
            self.animation_speed.addItem(f"{value:g}×", value)
        self.animation_speed.setCurrentIndex(self.animation_speed.findData(settings.animation_speed))
        form.addRow(tr("animation_speed"), self.animation_speed)
        self.api = QLineEdit(settings.api_url)
        form.addRow(tr("api_url"), self.api)
        self.data_dir = QLineEdit(settings.data_directory)
        self.base_dir = QLineEdit(settings.attachment_base)
        for key, edit in [("data_directory", self.data_dir), ("attachment_base", self.base_dir)]:
            container = QWidget()
            row = QHBoxLayout(container)
            row.setContentsMargins(0, 0, 0, 0)
            row.addWidget(edit)
            browse = QPushButton(tr("browse"))
            browse.clicked.connect(lambda checked=False, target=edit: self.browse(target))
            row.addWidget(browse)
            if key == "data_directory":
                button = QPushButton(tr("detect"))
                button.clicked.connect(self.detect)
                row.addWidget(button)
            form.addRow(tr(key), container)
        self.poll = QSpinBox()
        self.poll.setRange(15, 86400)
        self.poll.setValue(settings.poll_seconds)
        form.addRow(tr("poll"), self.poll)
        self.hotkey = QKeySequenceEdit(QKeySequence(settings.hotkey))
        self.hotkey.setMaximumSequenceLength(1)
        form.addRow(tr("hotkey"), self.hotkey)
        self.close_tray = QCheckBox(tr("close_to_tray"))
        self.close_tray.setChecked(settings.close_to_tray)
        form.addRow(self.close_tray)
        self.autostart = QCheckBox(tr("autostart"))
        self.autostart.setChecked(autostart_enabled())
        form.addRow(self.autostart)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText(tr("save"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("cancel"))
        buttons.accepted.connect(self.accept_validated)
        buttons.rejected.connect(self.reject)
        layout.addStretch()
        layout.addWidget(buttons)

    def browse(self, edit):
        path = QFileDialog.getExistingDirectory(self, self.tr("browse"), edit.text())
        if path:
            edit.setText(path)

    def detect(self):
        if self.submit:
            self.submit(detected_directories, self.detected)
            return
        directories, base = detected_directories()
        self.detected((directories, base), None)

    def detected(self, result, error):
        if error or not self.isVisible():
            return
        directories, base = result
        if directories:
            self.data_dir.setText(directories[0])
        if base:
            self.base_dir.setText(base)

    def value(self) -> Settings:
        settings = replace(
            self.settings,
            language=self.language.currentData(),
            theme=self.theme.currentData(),
            motion=self.motion.currentData(),
            animation_speed=self.animation_speed.currentData(),
            api_url=self.api.text().strip(),
            data_directory=self.data_dir.text().strip(),
            attachment_base=self.base_dir.text().strip(),
            poll_seconds=self.poll.value(),
            hotkey=self.hotkey.keySequence().toString(QKeySequence.SequenceFormat.PortableText),
            close_to_tray=self.close_tray.isChecked(),
        )
        settings.validate()
        parse_hotkey(settings.hotkey)
        for path in [settings.data_directory, settings.attachment_base]:
            # Network directories may be temporarily unavailable. Validating their
            # existence here blocks the modal GUI; sync checks availability later.
            if path and (not Path(path).is_absolute() or "\x00" in path):
                raise ValueError("Invalid directory")
        return settings

    def accept_validated(self):
        try:
            self.value()
            self.accept()
        except ValueError:
            QMessageBox.warning(self, self.tr("error"), self.tr("invalid_settings"))
