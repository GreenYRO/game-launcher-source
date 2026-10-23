"""How was it? (Phase 102): the rating card, bottom-right where the toast floats -- but a widget of its own,
because it takes clicks and the toast never does (a message over a tile must not swallow the click meant for it).

"<game>, 1h 23m. How was it?", five stars and a quiet Skip, nothing else. The mouse lights the stars up to the
one under it; a click rates. The pad's left and right move along the stars, A rates the lit one, B skips -- the
window hands the card those buttons while it shows (MainWindow._on_pad_action). A star says "Thanks" for a
moment and goes; Skip goes; no answer for rules.RATE_CARD_S and it goes by itself. Only a star writes anything,
and the window writes it, through the store. "Reduce animations": it appears and goes without a fade.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, QSize, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtWidgets import QGraphicsOpacityEffect, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from presentation import ui_icons
from presentation import ui_rules
from shared import rules


class RateCard(QWidget):
    """The card. `ask(text, ...)` shows it; `rated(stars)`, `skipped()` and `expired()` say how it ended."""

    rated = Signal(int)
    skipped = Signal()
    expired = Signal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("RateCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.scale = 1.0
        self.bottom_reserve = 0
        self.reduce_animations = False
        self.lit = 0  # the stars lit: under the mouse, or where the pad has moved to
        self._answered = False
        self.question = QLabel(self)
        self.question.setObjectName("RateQuestion")
        self.stars: list[QPushButton] = []
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        for number in range(1, rules.RATE_STARS + 1):
            star = QPushButton(self)
            star.setObjectName("RateStar")
            star.setFlat(True)
            star.setCursor(Qt.CursorShape.PointingHandCursor)
            star.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            star.setAccessibleName(f"{number} star{'s' if number != 1 else ''}")
            star.clicked.connect(lambda _checked=False, n=number: self.answer(n))
            star.installEventFilter(self)
            self.stars.append(star)
            row.addWidget(star)
        self.skip_gap = row.count()
        self.skip_button = QPushButton("Skip", self)
        self.skip_button.setObjectName("RateSkip")
        self.skip_button.setFlat(True)
        self.skip_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.skip_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.skip_button.clicked.connect(self.skip)
        row.addStretch(1)
        row.addWidget(self.skip_button)
        self.row = row
        layout = QVBoxLayout(self)
        layout.addWidget(self.question)
        layout.addLayout(row)
        self.layout_ = layout
        self.opacity = QGraphicsOpacityEffect(self)
        self.opacity.setOpacity(1.0)
        self.setGraphicsEffect(self.opacity)
        self.fade = QVariantAnimation(self)
        self.fade.valueChanged.connect(lambda v: self.opacity.setOpacity(float(v)))
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._expire)
        self.thanks_timer = QTimer(self)
        self.thanks_timer.setSingleShot(True)
        self.thanks_timer.timeout.connect(self.hide)
        self.hide()

    # -- showing it ---------------------------------------------------------------------------

    @property
    def showing(self) -> bool:
        """Asking: shown and not yet answered (a "Thanks" on its way out is no longer asking)."""
        return self.isVisible() and not self._answered

    def apply_scale(self, scale: float) -> None:
        self.scale = scale
        s = lambda v: max(1, round(v * scale))  # noqa: E731
        left, top = ui_rules.RATE_CARD_PADDING
        self.layout_.setContentsMargins(s(left), s(top), s(left), s(top))
        self.layout_.setSpacing(s(ui_rules.RATE_CARD_GAP))
        self.row.setSpacing(s(ui_rules.RATE_STAR_GAP))
        for star in self.stars:
            star.setFixedSize(s(ui_rules.RATE_STAR_BOX), s(ui_rules.RATE_STAR_BOX))
            star.setIconSize(QSize(s(ui_rules.RATE_STAR_PX), s(ui_rules.RATE_STAR_PX)))
        self.question.setStyleSheet(f"font-size: {s(ui_rules.RATE_TITLE_PX)}px; font-weight: {ui_rules.HEADING_WEIGHT};")
        self.skip_button.setStyleSheet(f"font-size: {s(ui_rules.RATE_SKIP_PX)}px; padding: 0 {s(6)}px;")
        self._paint_stars()
        self.reposition()

    def set_bottom_reserve(self, pixels: int) -> None:
        """Room to leave at the bottom -- TV mode's button-hint bar, as the toast leaves it."""
        self.bottom_reserve = pixels
        self.reposition()

    def ask(self, text: str) -> None:
        """Show the question; the clock starts. A card already asking is replaced."""
        self._answered = False
        self.lit = 0
        self.question.setText(text)
        for star in self.stars:
            star.setVisible(True)
            star.setEnabled(True)
        self.skip_button.setVisible(True)
        self._paint_stars()
        self.adjustSize()
        self.reposition()
        self.show()
        self.raise_()
        self.thanks_timer.stop()
        self.timer.start(rules.RATE_CARD_S * 1000)
        self._fade(0.0, 1.0)

    def _home(self) -> QPoint:
        parent = self.parentWidget()
        margin = round(ui_rules.TOAST_MARGIN * self.scale)
        return QPoint(parent.width() - self.width() - margin, parent.height() - self.height() - margin - self.bottom_reserve)

    def reposition(self) -> None:
        if self.parentWidget() is not None:
            self.adjustSize()
            self.move(self._home())

    def _fade(self, start: float, end: float) -> None:
        self.fade.stop()
        if self.reduce_animations:
            self.opacity.setOpacity(end)
            return
        self.fade.setDuration(ui_rules.RATE_FADE_MS)
        self.fade.setStartValue(start)
        self.fade.setEndValue(end)
        self.fade.start()

    # -- answering it -------------------------------------------------------------------------

    def _paint_stars(self) -> None:
        px = max(1, round(ui_rules.RATE_STAR_PX * self.scale))
        for number, star in enumerate(self.stars, start=1):
            full = number <= self.lit
            star.setIcon(ui_icons.glyph_pixmap("star_full" if full else "star",
                                               ui_rules.COLOR_ACCENT_HOVER if full else ui_rules.COLOR_TEXT_MUTED, px))

    def light(self, stars: int) -> None:
        self.lit = max(0, min(rules.RATE_STARS, stars))
        self._paint_stars()

    def step(self, delta: int) -> None:
        """The pad's left and right: one star fewer or more, never below one once moved."""
        self.timer.start(rules.RATE_CARD_S * 1000)  # an answer under way: the clock starts again
        self.light(max(1, self.lit + delta))

    def press(self) -> None:
        """The pad's A: the lit stars, or one when none is lit yet."""
        self.answer(max(1, self.lit))

    def answer(self, stars: int) -> None:
        if self._answered:
            return
        self._answered = True
        self.timer.stop()
        self.light(stars)
        self.question.setText(f"Thanks — {stars} star{'s' if stars != 1 else ''}")
        for star in self.stars:
            star.setEnabled(False)
        self.skip_button.setVisible(False)
        self.rated.emit(stars)
        self.thanks_timer.start(ui_rules.RATE_THANKS_MS)

    def skip(self) -> None:
        if self._answered or not self.isVisible():
            return
        self._answered = True
        self.timer.stop()
        self.hide()
        self.skipped.emit()

    def _expire(self) -> None:
        if self._answered:
            return
        self._answered = True
        self.hide()
        self.expired.emit()

    def withdraw(self) -> None:
        """Taken away without an answer -- a game started, the window went to the tray: nothing written."""
        if self.isVisible():
            self._answered = True
            self.timer.stop()
            self.thanks_timer.stop()
            self.hide()

    def eventFilter(self, watched, event) -> bool:
        if watched in self.stars and not self._answered:
            if event.type() == QEvent.Type.Enter:
                self.light(self.stars.index(watched) + 1)
            elif event.type() == QEvent.Type.Leave:
                self.light(0)
        return super().eventFilter(watched, event)
