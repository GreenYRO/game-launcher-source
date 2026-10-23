"""Messages as a card floating over the bottom-right corner, instead of a status bar.

It does not replace the status bar -- it *shows* it. The QStatusBar is still there, hidden,
and every one of the ~20 places that post a message still calls showMessage on it. The
Phase 14 queue still reads it, its timers still clear it, and every test that reads
currentMessage() still works. This card listens to messageChanged and mirrors whatever
the bar holds: text arrives, the card slides in; the bar clears, the card fades away.
"Ready", the bar's idle word, is never shown.
"""

from __future__ import annotations

from PySide6.QtCore import (QAbstractAnimation, QEasingCurve, QParallelAnimationGroup, QPoint,
                            QPropertyAnimation, Qt)
from PySide6.QtWidgets import (QGraphicsOpacityEffect, QHBoxLayout, QLabel, QSizePolicy,
                               QWidget)

from presentation import ui_icons
from presentation import ui_rules

IDLE = "Ready"


class Toast(QWidget):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("Toast")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        # Never in the way: a message over a tile must not swallow the click meant for it.
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.reduce_animations = False
        self.bottom_reserve = 0
        self.scale = 1.0

        self.glyph = QLabel()
        self.glyph.setObjectName("ToastGlyph")
        self.text = QLabel()
        self.text.setObjectName("ToastText")
        self.text.setWordWrap(True)
        self.text.setTextFormat(Qt.TextFormat.PlainText)
        self.text.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        row = QHBoxLayout(self)
        row.addWidget(self.glyph, 0, Qt.AlignmentFlag.AlignTop)
        row.addWidget(self.text, 1)
        self._apply_scale()

        self.effect = QGraphicsOpacityEffect(self)
        self.effect.setOpacity(0.0)
        self.setGraphicsEffect(self.effect)
        self.fade = QPropertyAnimation(self.effect, b"opacity", self)
        self.slide = QPropertyAnimation(self, b"pos", self)
        for animation in (self.fade, self.slide):
            animation.setDuration(ui_rules.TOAST_SHOW_MS)
            animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.motion = QParallelAnimationGroup(self)
        self.motion.addAnimation(self.fade)
        self.motion.addAnimation(self.slide)
        self.motion.finished.connect(self._settled)
        self._leaving = False
        self.hide()

    def apply_scale(self, scale: float) -> None:
        self.scale = scale
        self._apply_scale()
        self.reposition()

    def _apply_scale(self) -> None:
        s = self.scale
        margin_h, margin_v = round(16 * s), round(12 * s)
        self.layout().setContentsMargins(margin_h, margin_v, margin_h + round(4 * s), margin_v)
        self.layout().setSpacing(round(12 * s))
        px = max(12, round(ui_rules.ICON_GLYPH_PX * s))
        self.glyph.setPixmap(ui_icons.glyph_pixmap("info", ui_rules.COLOR_ACCENT, px,
                                                   self.devicePixelRatioF() or 1.0))
        self.setMaximumWidth(round(ui_rules.TOAST_MAX_WIDTH * s))

    # -- following the status bar ---------------------------------------------------------

    def show_message(self, message: str) -> None:
        message = (message or "").strip()
        if not message or message == IDLE:
            self._leave()
            return
        self.text.setText(message)
        # A wrapping label asks for as little width as it can get away with, which folded a
        # one-line message onto two. Ask for the line's own width, up to the card's limit.
        margins = self.layout().contentsMargins()
        room = (self.maximumWidth() - margins.left() - margins.right()
                - self.glyph.sizeHint().width() - self.layout().spacing())
        natural = self.text.fontMetrics().horizontalAdvance(message) + 4
        self.text.setMinimumWidth(max(1, min(natural, room)))
        self.adjustSize()
        self._leaving = False
        if self.isVisible() and self.effect.opacity() > 0.99:
            self.reposition()  # a new message over one already showing: just swap the words
            return
        self.show()
        self.raise_()
        home = self._home()
        if self.reduce_animations:
            self.motion.stop()
            self.move(home)
            self.effect.setOpacity(1.0)
            return
        self.motion.stop()
        self.fade.setStartValue(self.effect.opacity())
        self.fade.setEndValue(1.0)
        self.slide.setStartValue(home + QPoint(0, round(ui_rules.TOAST_SLIDE_PX * self.scale)))
        self.slide.setEndValue(home)
        self.motion.start()

    def _leave(self) -> None:
        if not self.isVisible() or self._leaving:
            return
        self._leaving = True
        if self.reduce_animations:
            self.motion.stop()
            self.hide()
            return
        self.motion.stop()
        self.fade.setStartValue(self.effect.opacity())
        self.fade.setEndValue(0.0)
        self.slide.setStartValue(self.pos())
        self.slide.setEndValue(self.pos())
        self.motion.start()

    def _settled(self) -> None:
        if self._leaving:
            self.hide()
            self._leaving = False

    # -- where it sits -----------------------------------------------------------------------

    def _home(self) -> QPoint:
        parent = self.parentWidget()
        margin = round(ui_rules.TOAST_MARGIN * self.scale)
        size = self.sizeHint().expandedTo(self.minimumSizeHint())
        width = min(size.width(), self.maximumWidth())
        self.resize(width, self.heightForWidth(width) if self.hasHeightForWidth() else size.height())
        return QPoint(parent.width() - self.width() - margin,
                      parent.height() - self.height() - margin - self.bottom_reserve)

    def reposition(self) -> None:
        # Compared explicitly: a PySide6 enum member is always truthy, so "not state()" would
        # have read as stopped even mid-slide.
        idle = self.motion.state() == QAbstractAnimation.State.Stopped
        if self.isVisible() and self.parentWidget() is not None and idle:
            self.move(self._home())

    def set_bottom_reserve(self, pixels: int) -> None:
        """Room to leave at the bottom -- TV mode's button-hint bar."""
        self.bottom_reserve = pixels
        self.reposition()
