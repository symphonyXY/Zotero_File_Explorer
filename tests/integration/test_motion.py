from copy import deepcopy
from dataclasses import replace

import pytest
from PySide6.QtCore import QAbstractAnimation, QEvent, QItemSelectionModel, QPoint, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QAbstractItemModelTester
from PySide6.QtWidgets import QApplication, QLineEdit, QPushButton, QVBoxLayout, QWidget

from zotero_file_explorer.i18n.strings import Translator
from zotero_file_explorer.storage.config import ConfigStore, Settings
from zotero_file_explorer.storage.index import SearchFilter
from zotero_file_explorer.ui.motion import (
    ControlFeedback,
    FeedbackLabel,
    MotionPolicy,
    TreeFeedback,
    WindowEntrance,
)
from zotero_file_explorer.ui.paper_model import ROLE
from zotero_file_explorer.ui.paper_view import PaperView
from zotero_file_explorer.ui.theme import apply_theme


def test_model_contract_and_duplicate_library_keys(qtbot, index):
    view = PaperView(Translator())
    qtbot.addWidget(view)
    model = view.model_data
    tester = QAbstractItemModelTester(model, QAbstractItemModelTester.FailureReportingMode.Warning)
    records = index.search(SearchFilter())[0]
    other = deepcopy(records[0])
    other["library"] = "group:42"
    records.append(other)
    view.populate(records, {})
    assert model.rowCount() == 2
    view.expand(model.index(0, 0))
    child = model.index(1, 0, model.index(0, 0))
    view.setCurrentIndex(child)
    # Same document key in another library must not inherit expanded/selected state.
    changed = deepcopy(records)
    changed[0]["title"] = "Updated title"
    view.populate(changed, {})
    assert view.isExpanded(model.index(0, 0))
    assert not view.isExpanded(model.index(1, 0))
    assert len(view.selected_data()) == 1
    assert view.currentIndex().data(ROLE)["library"] == "user:0"
    assert view.currentIndex().data(ROLE)["attachment"]["key"] == "ATTACH02"
    assert tester.model() is model


def test_equal_results_do_not_reset_selection_or_scroll(qtbot, index):
    view = PaperView(Translator())
    qtbot.addWidget(view)
    records = index.search(SearchFilter())[0]
    view.populate(records, {})
    view.setCurrentIndex(view.model_data.index(0, 0))
    resets = []
    view.model_data.modelReset.connect(lambda: resets.append(True))
    for _ in range(20):
        view.populate(deepcopy(records), {})
    assert not resets
    assert len(view.selected_attachments(True)) == 1


def test_motion_policy_system_override_and_settings_roundtrip(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr("zotero_file_explorer.ui.motion.animations_enabled", lambda: True)
    settings = Settings(motion="full", animation_speed=2)
    policy = MotionPolicy(settings)
    assert policy.duration("window") == 95 and policy.full
    policy.configure(replace(settings, motion="reduced"))
    assert policy.duration("window") <= 70 and not policy.full
    monkeypatch.setattr("zotero_file_explorer.ui.motion.animations_enabled", lambda: False)
    policy.refresh_system()
    assert policy.duration("window") == 0
    store = ConfigStore(tmp_path)
    store.save(settings)
    assert store.load() == settings
    for invalid in [
        Settings(motion="invalid"),
        Settings(animation_speed=0),
        Settings(animation_speed=float("nan")),
    ]:
        with pytest.raises(ValueError):
            invalid.validate()


def test_interrupted_entrance_and_feedback_settle(qtbot, monkeypatch):
    monkeypatch.setattr("zotero_file_explorer.ui.motion.animations_enabled", lambda: True)
    window = QWidget()
    qtbot.addWidget(window)
    edit = QLineEdit(window)
    QVBoxLayout(window).addWidget(edit)
    policy = MotionPolicy(Settings())
    entrance = WindowEntrance(window, policy)
    feedback = ControlFeedback(edit, policy)
    for _ in range(25):
        window.show()
        edit.setFocus()
        qtbot.wait(2)
        window.hide()
        assert window.windowOpacity() == 1
        assert entrance.animation.state() == QAbstractAnimation.State.Stopped
    window.show()
    policy.configure(Settings(motion="off"))
    assert window.windowOpacity() == 1
    assert feedback.animation.state() == QAbstractAnimation.State.Stopped
    assert feedback.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    qtbot.keyClicks(edit, "typed through feedback")
    assert edit.text() == "typed through feedback"


def test_tree_rapid_reverse_and_disable_keep_selection(qtbot, index, monkeypatch):
    monkeypatch.setattr("zotero_file_explorer.ui.motion.animations_enabled", lambda: True)
    view = PaperView(Translator())
    qtbot.addWidget(view)
    policy = MotionPolicy(Settings())
    delegate = TreeFeedback(view, policy)
    view.setItemDelegate(delegate)
    view.populate(index.search(SearchFilter())[0], {})
    view.show()
    parent = view.model_data.index(0, 0)
    child = view.model_data.index(1, 0, parent)
    view.selectionModel().select(
        child, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows
    )
    for _ in range(15):
        view.expand(parent)
        qtbot.wait(3)
        view.collapse(parent)
    policy.configure(Settings(motion="off"))
    view.expand(parent)
    qtbot.wait(250)
    assert not view.isAnimated()
    assert view.isExpanded(parent)
    assert view.visualRect(child).isValid()
    assert len(view.selected_attachments(True)) == 1
    assert delegate.animation.state() == QAbstractAnimation.State.Stopped


def test_theme_repaints_existing_controls_without_stale_styles(qapp, qtbot):
    edit = QLineEdit()
    edit.resize(200, 40)
    qtbot.addWidget(edit)
    edit.show()
    for theme, expected in [("light", "#ffffff"), ("dark", "#202632"), ("light", "#ffffff")]:
        apply_theme(qapp, theme)
        qtbot.wait(20)
        image = edit.grab().toImage()
        assert image.pixelColor(image.width() // 2, image.height() // 2).name() == expected


def test_disabled_button_clears_press_and_keyboard_uses_feedback(qtbot, monkeypatch):
    monkeypatch.setattr("zotero_file_explorer.ui.motion.animations_enabled", lambda: True)
    button = QPushButton("Run fixture")
    qtbot.addWidget(button)
    feedback = ControlFeedback(button, MotionPolicy(Settings(), button))
    button.show()
    button.setFocus()
    qtbot.keyPress(button, Qt.Key.Key_Space)
    assert button.isDown()
    qtbot.waitUntil(lambda: feedback.level > 0.7)
    button.setEnabled(False)
    qtbot.keyRelease(button, Qt.Key.Key_Space)
    assert feedback.level == 0
    assert feedback.animation.state() == QAbstractAnimation.State.Stopped
    button.setEnabled(True)
    button.setFocus()
    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
    feedback.animation.setCurrentTime(30)
    elapsed = feedback.animation.currentTime()
    QApplication.sendEvent(button, QEvent(QEvent.Type.FocusIn))
    assert feedback.animation.currentTime() >= elapsed


def test_horizontal_scroll_and_drag_clear_hover_without_changing_selection(qtbot, index, monkeypatch):
    monkeypatch.setattr("zotero_file_explorer.ui.motion.animations_enabled", lambda: True)
    view = PaperView(Translator())
    qtbot.addWidget(view)
    view.resize(400, 300)
    view.setColumnWidth(0, 600)
    delegate = TreeFeedback(view, MotionPolicy(Settings(), view))
    view.setItemDelegate(delegate)
    view.populate(index.search(SearchFilter())[0], {})
    view.show()
    qtbot.waitExposed(view)
    QApplication.processEvents()
    parent = view.model_data.index(0, 0)
    view.setCurrentIndex(parent)
    point = QPoint(60, view.visualRect(parent).center().y())
    # Deliver the Qt input event explicitly; OS pointer position depends on preceding windows.
    QApplication.sendEvent(view.viewport(), QMouseEvent(
        QEvent.Type.MouseMove, point, view.viewport().mapToGlobal(point),
        Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
    ))
    assert delegate.hover.isValid()
    view.horizontalScrollBar().setValue(20)
    assert not delegate.hover.isValid()
    assert delegate.animation.state() == QAbstractAnimation.State.Stopped
    assert len(view.selected_data()) == 1
    qtbot.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(60, 15))
    assert not delegate.hover.isValid()
    qtbot.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(60, 15))


@pytest.mark.parametrize("mode", ["full", "reduced", "off"])
def test_receipt_updates_immediately_interrupts_and_settles(qtbot, monkeypatch, mode):
    monkeypatch.setattr("zotero_file_explorer.ui.motion.animations_enabled", lambda: True)
    policy = MotionPolicy(Settings(motion=mode))
    label = FeedbackLabel(policy)
    qtbot.addWidget(label)
    label.show()
    for text in ["Searching", "Complete", "Failed", "Complete again"]:
        label.set_message(text, animate=True)
        assert label.text() == text
        if mode != "full":
            assert label.effect.opacity() == 1
            assert label.animation.state() == QAbstractAnimation.State.Stopped
    monkeypatch.setattr("zotero_file_explorer.ui.motion.animations_enabled", lambda: False)
    policy.refresh_system()
    assert label.effect.opacity() == 1
    assert label.animation.state() == QAbstractAnimation.State.Stopped
    policy.configure(Settings(motion="off"))
    assert label.effect.opacity() == 1
    assert label.animation.state() == QAbstractAnimation.State.Stopped
    label.hide()
    assert label.effect.opacity() == 1


def test_selected_attachments_preserve_instance_identity(qtbot, index):
    view = PaperView(Translator())
    qtbot.addWidget(view)
    rows = index.search(SearchFilter())[0]
    other = deepcopy(rows[0])
    other["instance"] = "second-server"
    view.populate([rows[0], other], {})
    view.selectAll()
    assert {a["instance"] for a in view.selected_attachments(True)} == {"server1", "second-server"}


def test_hover_crossfade_is_bounded_and_disabled_motion_clears_departing_row(qtbot, index, monkeypatch):
    monkeypatch.setattr("zotero_file_explorer.ui.motion.animations_enabled", lambda: True)
    view = PaperView(Translator())
    qtbot.addWidget(view)
    policy = MotionPolicy(Settings())
    delegate = TreeFeedback(view, policy)
    view.setItemDelegate(delegate)
    view.populate(index.search(SearchFilter())[0], {})
    parent = view.model_data.index(0, 0)
    view.expand(parent)
    child = view.model_data.index(0, 0, parent)
    delegate.move_hover(parent)
    delegate.animation.setCurrentTime(policy.duration("hover"))
    delegate.move_hover(child)
    assert delegate.hover == child
    assert delegate.leaving == parent and delegate.leaving_level == 1
    delegate.animation.setCurrentTime(60)
    assert 0 < delegate.leaving_level < 1 and 0 < delegate.level < 1
    previous_level = delegate.leaving_level
    delegate.move_hover(parent)
    assert delegate.level == previous_level  # Reversing preserves the row's visible strength.
    for _ in range(15):
        delegate.move_hover(parent)
        delegate.move_hover(child)
    assert len(delegate.findChildren(QAbstractAnimation)) == 1
    policy.configure(Settings(motion="off"))
    assert not delegate.hover.isValid() and not delegate.leaving.isValid()
    assert delegate.leaving_level == delegate.level == 0
    assert delegate.animation.state() == QAbstractAnimation.State.Stopped
    delegate.move_hover(parent)
    assert delegate.level == 1


def test_quick_entrance_uses_short_token_and_hiding_settles_immediately(qtbot, monkeypatch):
    monkeypatch.setattr("zotero_file_explorer.ui.motion.animations_enabled", lambda: True)
    window = QWidget()
    window.setProperty("zfeQuickWindow", True)
    qtbot.addWidget(window)
    policy = MotionPolicy(Settings())
    entrance = WindowEntrance(window, policy)
    window.show()
    assert entrance.animation.duration() == 120
    window.hide()
    assert window.windowOpacity() == 1
    assert entrance.animation.state() == QAbstractAnimation.State.Stopped
