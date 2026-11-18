"""Bounded, interruptible Widgets motion; never intercept input or delay closing."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QObject,
    QPersistentModelIndex,
    QPropertyAnimation,
    Qt,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QComboBox,
    QDialog,
    QGraphicsOpacityEffect,
    QLabel,
    QLineEdit,
    QMenu,
    QProxyStyle,
    QStyle,
    QStyledItemDelegate,
    QTreeView,
    QWidget,
)
from shiboken6 import isValid

from ..platform.windows import animations_enabled


@dataclass(frozen=True)
class MotionTokens:
    press: int = 90
    hover: int = 150
    focus: int = 150
    menu: int = 150
    window: int = 190
    quick_window: int = 120
    dialog: int = 220
    expand: int = 220
    status: int = 140
    easing: QEasingCurve.Type = QEasingCurve.Type.OutCubic


class MotionPolicy(QObject):
    changed = Signal()

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.tokens = MotionTokens()
        self.configure(settings)

    def configure(self, settings):
        self.mode = settings.motion
        self.speed = settings.animation_speed
        self.system_enabled = animations_enabled()
        self.changed.emit()

    def refresh_system(self):
        enabled = animations_enabled()
        if enabled != self.system_enabled:
            self.system_enabled = enabled
            self.changed.emit()

    @property
    def full(self):
        return self.mode == "full" and self.system_enabled

    def duration(self, token):
        if self.mode == "off" or not self.system_enabled:
            return 0
        duration = getattr(self.tokens, token)
        if self.mode == "reduced":
            duration = min(70, duration)
        return round(duration / self.speed)


class MotionStyle(QProxyStyle):
    """Keep native branch hit testing; only supply the shared duration hint."""

    def __init__(self, policy):
        super().__init__("Fusion")
        self.policy = policy

    def styleHint(self, hint, option=None, widget=None, returnData=None):
        if hint == QStyle.StyleHint.SH_Widget_Animation_Duration and isinstance(widget, QTreeView):
            return self.policy.duration("expand") if self.policy.full else 0
        return super().styleHint(hint, option, widget, returnData)


class ControlFeedback(QWidget):
    """One lightweight paint overlay per used control, transparent to all input."""

    def __init__(self, control, policy):
        super().__init__(control)
        self.policy = policy
        self.level = 0.0
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.animation = QVariantAnimation(self)
        self.animation.setEasingCurve(policy.tokens.easing)
        self.animation.valueChanged.connect(self.update_level)
        control.installEventFilter(self)
        if isinstance(control, QAbstractButton):
            control.pressed.connect(lambda: self.transition("press"))
            control.released.connect(lambda: self.transition("hover"))
        policy.changed.connect(self.settle)
        self.setGeometry(control.rect())
        self.show()

    def target(self):
        control = self.parentWidget()
        if not control.isEnabled() or not control.isVisible():
            return 0.0
        if isinstance(control, QAbstractButton) and control.isDown():
            return 1.0
        return 0.65 if control.hasFocus() else 0.35 if control.underMouse() else 0.0

    def update_level(self, value):
        value = float(value)
        if self.level == value:
            return
        self.level = value
        self.update()

    def settle(self):
        self.animation.stop()
        self.update_level(self.target())

    def transition(self, token, target=None):
        target = self.target() if target is None else target
        # Repeated hover/focus signals must not restart a transition to the same state.
        if self.animation.state() == QVariantAnimation.State.Running and self.animation.endValue() == target:
            return
        self.animation.stop()
        duration = self.policy.duration(token)
        if duration and self.level != target:
            self.animation.setStartValue(self.level)
            self.animation.setEndValue(target)
            self.animation.setDuration(duration)
            self.animation.start()
        else:
            self.update_level(target)

    def eventFilter(self, obj, event):
        kind = event.type()
        if kind == QEvent.Type.Resize:
            self.setGeometry(obj.rect())
        elif kind == QEvent.Type.Hide:
            self.animation.stop()
            self.update_level(0)
        elif kind in {
            QEvent.Type.Enter,
            QEvent.Type.Leave,
            QEvent.Type.FocusIn,
            QEvent.Type.FocusOut,
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseButtonRelease,
            QEvent.Type.EnabledChange,
        }:
            target = self.target()
            if kind == QEvent.Type.MouseButtonPress and obj.isEnabled():
                target = 1.0
            elif kind == QEvent.Type.MouseButtonRelease:
                target = (
                    (0.65 if obj.hasFocus() else 0.35 if obj.underMouse() else 0.0)
                    if obj.isEnabled() else 0
                )
            token = (
                "press" if kind == QEvent.Type.MouseButtonPress
                else "focus" if kind in {QEvent.Type.FocusIn, QEvent.Type.FocusOut} else "hover"
            )
            if kind == QEvent.Type.EnabledChange and not obj.isEnabled():
                self.settle()
            else:
                self.transition(token, target)
        return False

    def paintEvent(self, event):
        if self.level <= 0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor("#587bf5")
        color.setAlphaF(self.level * 0.65)
        painter.setPen(QPen(color, 1.5))
        fill = QColor("#587bf5")
        fill.setAlphaF(self.level * 0.07)
        painter.setBrush(fill)
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 6, 6)


class WindowEntrance(QObject):
    def __init__(self, window, policy):
        super().__init__(window)
        self.window, self.policy = window, policy
        self.animation = QPropertyAnimation(window, b"windowOpacity", self)
        self.animation.setEasingCurve(policy.tokens.easing)
        window.installEventFilter(self)
        policy.changed.connect(self.finish)

    def finish(self):
        self.animation.stop()
        # Windows can send Hide while Qt is tearing down a child dialog.
        if isValid(self.window):
            self.window.setWindowOpacity(1)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Show:
            self.finish()
            token = (
                "menu" if isinstance(obj, QMenu) else "dialog" if isinstance(obj, QDialog)
                else "quick_window" if obj.property("zfeQuickWindow") else "window"
            )
            duration = self.policy.duration(token)
            if duration:
                # Never start invisible: keyboard and mouse are usable on the first frame.
                obj.setWindowOpacity(0.88 if self.policy.full else 0.96)
                self.animation.setStartValue(obj.windowOpacity())
                self.animation.setEndValue(1.0)
                self.animation.setDuration(duration)
                self.animation.start()
        elif event.type() in {QEvent.Type.Hide, QEvent.Type.Close}:
            self.finish()
        return False


class TreeFeedback(QStyledItemDelegate):
    """A single hover animation per view, irrespective of library size."""

    def __init__(self, view, policy):
        super().__init__(view)
        self.view, self.policy = view, policy
        self.hover = QPersistentModelIndex()
        self.leaving = QPersistentModelIndex()
        self.leaving_start = 0.0
        self.leaving_level = 0.0
        self.hover_start = 0.0
        self.level = 0.0
        self.animation = QVariantAnimation(self)
        self.animation.setEasingCurve(policy.tokens.easing)
        self.animation.valueChanged.connect(self.update_level)
        view.setMouseTracking(True)
        view.viewport().installEventFilter(self)
        view.installEventFilter(self)
        view.verticalScrollBar().valueChanged.connect(self.clear)
        view.horizontalScrollBar().valueChanged.connect(self.clear)
        view.model().modelAboutToBeReset.connect(self.clear)
        policy.changed.connect(self.configure)
        self.configure()

    def configure(self):
        self.view.setAnimated(self.policy.full)
        self.clear()

    def update_level(self, value):
        self.level = (
            self.hover_start + (1.0 - self.hover_start) * float(value) if self.hover.isValid() else 0.0
        )
        self.leaving_level = self.leaving_start * (1.0 - float(value))
        self.update_rows()

    def update_rows(self):
        for index in (self.hover, self.leaving):
            if not index.isValid():
                continue
            rect = self.view.visualRect(index)
            rect.setLeft(0)
            rect.setWidth(self.view.viewport().width())
            self.view.viewport().update(rect)

    def clear(self, *_):
        self.animation.stop()
        self.level = self.leaving_level = self.leaving_start = self.hover_start = 0.0
        self.update_rows()
        self.hover = QPersistentModelIndex()
        self.leaving = QPersistentModelIndex()

    def move_hover(self, index):
        if index == self.hover:
            return
        leaving = self.hover if self.hover.isValid() else self.leaving
        strength = self.level if self.hover.isValid() else self.leaving_level
        start = self.leaving_level if index == self.leaving else 0.0
        self.clear()
        if not index.isValid() and strength == 0:
            return
        self.hover = QPersistentModelIndex(index)
        duration = self.policy.duration("hover")
        if duration:
            self.leaving, self.leaving_start = leaving, strength
            self.hover_start = start
            self.update_level(0.0)
            self.animation.setStartValue(0.0)
            self.animation.setEndValue(1.0)
            self.animation.setDuration(duration)
            self.animation.start()
        else:
            self.update_level(1.0)

    def eventFilter(self, obj, event):
        if event.type() in {
            QEvent.Type.Hide, QEvent.Type.Wheel, QEvent.Type.Resize,
            QEvent.Type.MouseButtonPress, QEvent.Type.WindowDeactivate,
        }:
            self.clear()
        elif event.type() == QEvent.Type.Leave:
            self.move_hover(QPersistentModelIndex())
        elif event.type() == QEvent.Type.MouseMove:
            if event.buttons():
                self.clear()
                return False
            index = self.view.indexAt(event.position().toPoint()).siblingAtColumn(0)
            self.move_hover(index)
        return False

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        row = index.siblingAtColumn(0)
        level = self.level if row == self.hover else self.leaving_level if row == self.leaving else 0
        if level and not option.state & QStyle.StateFlag.State_Selected:
            color = QColor("#587bf5")
            color.setAlphaF(0.07 * level)
            painter.fillRect(option.rect, color)


class FeedbackLabel(QLabel):
    """A single finite receipt on a small label, with immediate accessible text."""

    def __init__(self, policy, parent=None):
        super().__init__(parent)
        self.policy = policy
        self.setObjectName("muted")
        self.setWordWrap(True)
        self.effect = QGraphicsOpacityEffect(self)
        self.effect.setOpacity(1)
        self.setGraphicsEffect(self.effect)
        self.animation = QPropertyAnimation(self.effect, b"opacity", self)
        self.animation.setEasingCurve(policy.tokens.easing)
        policy.changed.connect(self.settle)

    def settle(self):
        self.animation.stop()
        self.effect.setOpacity(1)

    def set_message(self, text, *, animate=False):
        if self.text() == text:
            return
        self.settle()
        self.setText(text)
        if animate and self.isVisible() and self.policy.full:
            self.effect.setOpacity(0.82)
            self.animation.setStartValue(0.82)
            self.animation.setEndValue(1.0)
            self.animation.setDuration(self.policy.duration("status"))
            self.animation.start()

    def hideEvent(self, event):
        self.settle()
        super().hideEvent(event)


class MotionSystem(QObject):
    def __init__(self, app, settings, parent=None):
        super().__init__(parent)
        self.app = app
        self.policy = MotionPolicy(settings, self)
        app.installEventFilter(self)
        app.applicationStateChanged.connect(self.refresh_system)

    def refresh_system(self, *_):
        self.policy.refresh_system()

    def eventFilter(self, obj, event):
        if event.type() != QEvent.Type.Show or not isinstance(obj, QWidget):
            return False
        # Limit enhancements to explicitly enrolled application windows and their children.
        window = obj.window()
        owner = window
        while owner and not owner.property("zfeMotion"):
            owner = owner.parentWidget()
        if owner is None:
            return False
        if isinstance(obj, (QAbstractButton, QLineEdit, QComboBox)) and not hasattr(obj, "_motion_feedback"):
            obj._motion_feedback = ControlFeedback(obj, self.policy)
        if obj.isWindow() and not hasattr(obj, "_motion_entrance"):
            obj._motion_entrance = WindowEntrance(obj, self.policy)
            obj._motion_entrance.eventFilter(obj, event)
        if isinstance(obj, QTreeView) and not obj.property("zfeMotionTree"):
            obj.setProperty("zfeMotionTree", True)
            obj._motion_delegate = TreeFeedback(obj, self.policy)
            obj.setItemDelegate(obj._motion_delegate)
        return False
