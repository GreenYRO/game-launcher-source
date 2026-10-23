"""The Continue playing card at the top of the library (Phase 32).

It replaces the Recently played shelf with one answer instead of eight: the game you were
last playing, its wide art, how long you have put into it, the first line of your note if
you left one -- and Play, one press away. A game marked Finished or Dropped is passed
over, because offering to continue something you said you were done with is the wrong
suggestion.

The card paints its own art and words, and holds two real buttons, so the mouse, the
keyboard and the pad all have something to land on. It folds away as the grid scrolls,
exactly as the shelves did, by driving maximumHeight: see _apply_height.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QEvent, QPropertyAnimation, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QPushButton, QSizePolicy, QWidget

from shared import humanize
from shared import rules
from presentation import ui_covers
from presentation import ui_icons
from presentation import ui_rules
from presentation import ui_theme

log = logging.getLogger(__name__)

PLAY, DETAILS = 0, 1
# Qt puts a button's icon right against its words and offers no stylesheet spacing for
# it, so the words carry their own. The first render showed the play symbol touching "Play".
PLAY_TEXT, STOP_TEXT, DETAILS_TEXT = "  Play", "  Stop", "Details"  # Details has no icon (Phase 56)


def eligible(views: list) -> list:
    """The games that may be offered to continue: played, and not finished or dropped.

    Hidden games and demos/tools are never offered, whatever the switches above the grid
    say -- the same rule the shelves followed. Played means the launcher timed it, or
    Steam's own manifest says when it last ran. The side rail's Jump back in (Phase 60)
    offers by the same rule.
    """
    return [
        view for view in views
        if not view.hidden
        and not view.is_non_game
        and view.last_played is not None
        and view.status not in ui_rules.CONTINUE_SKIP_STATUSES
    ]


def pick(views: list):
    """The game to offer: the one played most recently that you have not finished or dropped."""
    offered = eligible(views)
    if not offered:
        return None
    return max(offered, key=lambda view: view.last_played.timestamp())


def source_label(view) -> str:
    return rules.SOURCE_LABELS.get(view.entry.source, view.entry.source.capitalize())


def meta_line(view) -> str:
    """How long and when. The store's name stands in for time the launcher cannot see."""
    parts = []
    if view.entry.launch_kind == "exe":
        if view.playtime_seconds > 0:
            parts.append(f"{humanize.playtime(view.playtime_seconds)} played")
    else:
        parts.append(source_label(view))
    parts.append(f"last played {humanize.when(view.last_played)}")
    return "   ·   ".join(parts)


def note_line(view) -> str:
    """The first line of the note, quoted -- usually exactly where you left off."""
    lines = [line.strip() for line in view.notes.splitlines() if line.strip()]
    return f"“{lines[0]}”" if lines else ""


class ContinueCard(QWidget):
    """The card itself. Empty (and out of the layout) until it has a game to offer."""

    playRequested = Signal(str)
    stopRequested = Signal(str)
    detailsRequested = Signal(str)
    contextRequested = Signal(str, object)

    def __init__(self, covers, metrics, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("ContinueCard")
        self.covers = covers
        self.metrics = metrics
        self.view = None
        self.running = False
        self.starting = False  # Phase 99: Play pressed, the game not up yet
        self.present = False  # has a game, and the page wants it shown
        self.collapsed = False  # folded away because the grid is scrolled
        self.reduce_animations = ui_rules.REDUCE_ANIMATIONS_DEFAULT
        self._animation = None
        self._focused = PLAY
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(0)

        self.play_button = QPushButton(PLAY_TEXT, self)
        self.play_button.setObjectName("HeroPlay")
        self.play_button.clicked.connect(self._play_or_stop)
        self.details_button = QPushButton(DETAILS_TEXT, self)
        self.details_button.setObjectName("HeroGhost")
        self.details_button.setToolTip("Open this game's page")
        self.details_button.clicked.connect(self._details)
        for button in self.buttons:
            # A click must not leave a focus ring behind; the pad and Tab still reach them.
            button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            # The card draws their ring, outside them (Phase 56), so it repaints as they
            # take and lose the focus.
            button.installEventFilter(self)

        self.apply_metrics(metrics)
        self.setMaximumHeight(0)
        self.setVisible(False)

    @property
    def buttons(self) -> tuple[QPushButton, QPushButton]:
        return (self.play_button, self.details_button)

    # -- contents -------------------------------------------------------------------------

    def set_game(self, view) -> None:
        self.view = view
        if view is not None:
            self.play_button.setAccessibleName(
                f"{'Stop' if self.running else 'Play'} {view.display_name}"
            )
            self.details_button.setAccessibleName(f"Details of {view.display_name}")
        self.update()

    def set_running(self, running: bool) -> None:
        """Play becomes Stop while this game is up -- the rule the game page follows."""
        if running == self.running:
            return
        self.running = running
        self.play_button.setText(STOP_TEXT if running else PLAY_TEXT)
        self.play_button.setObjectName("HeroStop" if running else "HeroPlay")
        self.play_button.setToolTip(
            "Close this game (unsaved progress will be lost)" if running else ""
        )
        self._apply_icons()
        # A stylesheet is matched when the object name is set; restyle, or it keeps Play's
        # look -- the Phase 21 trap.
        self.play_button.style().unpolish(self.play_button)
        self.play_button.style().polish(self.play_button)
        self._size_buttons()
        self.set_game(self.view)

    def set_starting(self, starting: bool) -> None:
        """Play says Starting... and rests until the game is up (Phase 99); Stop, once it runs, is set_running's."""
        if starting == self.starting:
            return
        self.starting = starting
        if not self.running:
            self.play_button.setText(f"  {ui_rules.STARTING_TEXT}" if starting else PLAY_TEXT)
        self.play_button.setEnabled(not starting)
        self._size_buttons()

    def _play_or_stop(self) -> None:
        if self.view is not None:
            (self.stopRequested if self.running else self.playRequested).emit(self.view.key)

    def _details(self) -> None:
        if self.view is not None:
            self.detailsRequested.emit(self.view.key)

    # -- the pad --------------------------------------------------------------------------

    @property
    def focused_index(self) -> int:
        return self._focused

    def focus_button(self, index: int) -> None:
        self._focused = max(PLAY, min(DETAILS, index))
        self.buttons[self._focused].setFocus(Qt.FocusReason.OtherFocusReason)

    def focus_step(self, step: int) -> None:
        self.focus_button(self._focused + step)

    def clear_focus(self) -> None:
        for button in self.buttons:
            if button.hasFocus():
                button.clearFocus()
        self._focused = PLAY

    def activate_focused(self) -> None:
        self.buttons[self._focused].click()

    # -- folding --------------------------------------------------------------------------

    @property
    def shown(self) -> bool:
        """On the page and open, so the pad can move up into it.

        Deliberately not `isVisible()`, which is False whenever the library page itself is
        not on top -- the Phase 17 trap.
        """
        return self.present and not self.collapsed

    def set_present(self, present: bool) -> None:
        self.present = present and self.view is not None
        self._apply_height(animate=False)

    def set_collapsed(self, collapsed: bool, animate: bool = True) -> None:
        if collapsed == self.collapsed:
            return
        self.collapsed = collapsed
        self._apply_height(animate=animate)

    def full_height(self) -> int:
        """The card, plus the gap above the chips (no room for a shadow since Phase 56)."""
        s = self.metrics.scale
        return round((ui_rules.CONTINUE_HEIGHT + ui_rules.CONTINUE_GAP) * s)

    def _apply_height(self, animate: bool) -> None:
        """Drive maximumHeight, never a fixed height -- the shelves' mechanism, kept.

        stop() can report the animation finished, so the handler reads the state as it is
        now rather than a target it closed over: that is what once left a shelf with a full
        maximumHeight and a height of zero.
        """
        target = self.full_height() if self.shown else 0
        if self._animation is not None:
            self._animation.stop()
            self._animation = None
        if not animate or self.reduce_animations:
            self.setMaximumHeight(target)
            self._settle_visibility()
            return
        self.setVisible(self.present)
        animation = QPropertyAnimation(self, b"maximumHeight", self)
        animation.setDuration(ui_rules.CONTINUE_FOLD_MS)
        animation.setEasingCurve(ui_theme.easing(ui_rules.CONTINUE_FOLD_EASING))
        animation.setStartValue(self.height())
        animation.setEndValue(target)
        animation.finished.connect(self._settle_visibility)
        animation.start()
        self._animation = animation

    def _settle_visibility(self) -> None:
        self.setVisible(self.present and self.maximumHeight() > 0)

    # -- geometry -------------------------------------------------------------------------

    def sizeHint(self) -> QSize:
        return QSize(super().sizeHint().width(), self.full_height())

    def minimumSizeHint(self) -> QSize:
        return QSize(0, 0)

    def card_rect(self) -> QRectF:
        """The card's body. Anchored to the bottom, so folding slides it up and away.

        Inset at the sides by as much as the grid's first cover is (Phase 55), so the
        card, the chips and the covers share one left edge, as in the design.
        """
        s = self.metrics.scale
        inset = self.metrics.grid_inset
        body = round(ui_rules.CONTINUE_HEIGHT * s)
        reserve = round(ui_rules.CONTINUE_GAP * s)
        return QRectF(inset, self.height() - reserve - body, self.width() - 2 * inset, body)

    def apply_metrics(self, metrics) -> None:
        self.metrics = metrics
        self._apply_icons()
        self._size_buttons()
        self.updateGeometry()
        self._apply_height(animate=False)

    def _size_buttons(self) -> None:
        """Each button as wide as its words and the stylesheet's padding make it (Phase 56):
        Play and Stop differ in width, and Details moves along with them."""
        height = max(20, round(ui_rules.CONTINUE_BUTTON_HEIGHT * self.metrics.scale))
        for button in self.buttons:
            button.ensurePolished()
            button.setFixedSize(button.sizeHint().width(), height)
        self._place_buttons()

    def _apply_icons(self) -> None:
        px = max(10, round(ui_rules.CONTINUE_BUTTON_PX * self.metrics.scale))
        if self.running:
            self.play_button.setIcon(ui_icons.icon("stop_solid", ui_rules.COLOR_STOP, px))
        else:
            self.play_button.setIcon(ui_icons.icon("play_solid", ui_rules.COLOR_ACCENT, px))
        self.play_button.setIconSize(QSize(px, px))

    def _place_buttons(self) -> None:
        s = self.metrics.scale
        card = self.card_rect()
        y = round(card.bottom() - ui_rules.CONTINUE_PADDING_Y * s) - self.play_button.height()
        x = round(card.left() + ui_rules.CONTINUE_PADDING_X * s)
        self.play_button.move(x, y)
        self.details_button.move(
            x + self.play_button.width() + round(ui_rules.CONTINUE_BUTTON_GAP * s), y
        )
        self.update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._place_buttons()

    def eventFilter(self, watched, event) -> bool:
        if watched in self.buttons:
            if event.type() in (QEvent.Type.FocusIn, QEvent.Type.FocusOut):
                self.update()
            elif event.type() == QEvent.Type.StyleChange:
                # The words' width comes from the stylesheet, which arrives after the card.
                self._size_buttons()
        return super().eventFilter(watched, event)

    def ring_width(self) -> int:
        """The focus ring's width: the tiles' (TV mode's thicker one included), at this scale."""
        width = getattr(self.parentWidget(), "focus_ring_width", ui_rules.FOCUS_RING_WIDTH)
        return max(1, round(width * self.metrics.scale))

    # -- painting -------------------------------------------------------------------------

    def paintEvent(self, event) -> None:
        if self.view is None:
            return
        s = self.metrics.scale
        card = self.card_rect()
        radius = ui_rules.CONTINUE_RADIUS * s
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        outline = QPainterPath()
        outline.addRoundedRect(card, radius, radius)
        painter.save()
        painter.setClipPath(outline)
        art = self._art(round(card.width()), round(card.height()))
        if not art.isNull():
            painter.drawPixmap(card.topLeft(), art)
        scrim = QLinearGradient(card.topLeft(), card.topRight())
        dark = QColor(ui_rules.COLOR_SCRIM)
        for stop, alpha in ui_rules.CONTINUE_SCRIM:
            dark.setAlpha(alpha)
            scrim.setColorAt(stop, dark)
        painter.fillRect(card, scrim)
        painter.restore()
        # The design's edge: a 1 px hairline just outside the card, where a shadow used to fall.
        painter.setPen(QPen(QColor(ui_rules.COLOR_BORDER), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(card.adjusted(-0.5, -0.5, 0.5, 0.5), radius + 0.5, radius + 0.5)

        self._paint_words(painter, card, s)
        self._paint_ring(painter, s)

    def _paint_ring(self, painter: QPainter, s: float) -> None:
        """The design's focus ring: 2 px of the accent, 2 px outside the button the pad or the
        keyboard is on (TV mode's thicker ring included) -- drawn by the card, which owns the
        room around its buttons, where a stylesheet could only thicken the button's own edge."""
        focused = next((button for button in self.buttons if button.hasFocus()), None)
        if focused is None:
            return
        ring = self.ring_width()
        out = ui_rules.FOCUS_RING_GAP * s + ring / 2
        radius = ui_rules.CONTROL_RADIUS * s + out
        painter.setPen(QPen(QColor(ui_rules.TILE_FOCUS_COLOR), ring))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(QRectF(focused.geometry()).adjusted(-out, -out, out, out), radius, radius)

    def _art(self, width: int, height: int) -> QPixmap:
        """The wide art if there is some, else the cover cropped to the card, sharp.

        Not CoverFactory.banner's fallback, which blurs and darkens a cover into a backdrop
        for the game page: under this card's own scrim it rendered as a near-black
        smudge. Only a game with no art at all gets that accent wash. Cropped about 30% of
        the way down, as the design frames it (Phase 56).
        """
        for path in (self.view.banner_source, self.view.cover_source):
            if ui_covers.is_image(path):
                pixmap = self.covers.image(path, width, height, ui_rules.CONTINUE_ART_ANCHOR)
                if not pixmap.isNull():
                    return pixmap
        return self.covers.banner(self.view, width, height)

    def _paint_words(self, painter: QPainter, card: QRectF, s: float) -> None:
        """The design's words stand on the card's foot (Phase 56): stacked upwards from the
        buttons, each in a line box its size times the design's line height, 6 px apart."""
        x = card.left() + ui_rules.CONTINUE_PADDING_X * s
        width = min(card.width() - 2 * ui_rules.CONTINUE_PADDING_X * s, ui_rules.CONTINUE_TEXT_MAX * s)
        gap = ui_rules.CONTINUE_LINE_GAP * s
        foot = self.play_button.y() - (ui_rules.CONTINUE_BUTTONS_ABOVE * s + gap)

        eyebrow = _font(ui_icons.body_family(), ui_rules.CONTINUE_EYEBROW_PX * s)
        eyebrow.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing,
                                 ui_rules.CONTINUE_EYEBROW_PX * ui_rules.CONTINUE_EYEBROW_TRACKING * s)
        title = _font(ui_icons.display_family(), ui_rules.CONTINUE_TITLE_PX * s,
                      QFont.Weight(ui_rules.HEADING_WEIGHT))
        title.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing,
                               ui_theme.tracking(ui_rules.CONTINUE_TITLE_PX) * s)
        meta = _font(ui_icons.body_family(), ui_rules.CONTINUE_META_PX * s)
        quiet = _font(ui_icons.body_family(), ui_rules.CONTINUE_NOTE_PX * s)
        quiet.setItalic(True)
        line = ui_rules.TEXT_LINE_HEIGHT
        lines = [
            (eyebrow, "CONTINUE PLAYING", ui_rules.COLOR_ACCENT, ui_rules.CONTINUE_EYEBROW_PX * line),
            (title, self.view.display_name, ui_rules.COLOR_TEXT,
             ui_rules.CONTINUE_TITLE_PX * ui_rules.CONTINUE_TITLE_LINE),
            (meta, meta_line(self.view), ui_rules.COLOR_TEXT_SOFT, ui_rules.CONTINUE_META_PX * line),
        ]
        note = note_line(self.view)
        if note:
            lines.append((quiet, note, ui_rules.COLOR_TEXT_QUIET, ui_rules.CONTINUE_NOTE_PX * line))
        top = foot - sum(box * s for *_rest, box in lines) - gap * (len(lines) - 1)
        for font, text, colour, box in lines:
            _line(painter, font, text, colour, x, top, width, box * s)
            top += box * s + gap

    # -- mouse ----------------------------------------------------------------------------

    def mouseReleaseEvent(self, event) -> None:
        # Anywhere on the card that is not a button opens the game's page.
        if (self.view is not None and event.button() == Qt.MouseButton.LeftButton
                and self.card_rect().contains(event.position())):
            self.detailsRequested.emit(self.view.key)
            return
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event) -> None:
        if self.view is not None:
            self.contextRequested.emit(self.view.key, event.globalPos())


def _font(family: str, pixels: float, weight=QFont.Weight(ui_rules.BODY_WEIGHT)) -> QFont:
    font = QFont(family)
    font.setPixelSize(max(1, round(pixels)))
    font.setWeight(weight)
    return font


def _line(painter: QPainter, font: QFont, text: str, colour: str, x: float, y: float,
          width: float, box: float) -> None:
    """Draw one line centred in a box `box` tall, cut short with an ellipsis if it would
    run too far."""
    metrics = QFontMetricsF(font)
    painter.setFont(font)
    painter.setPen(QColor(colour))
    shown = metrics.elidedText(text, Qt.TextElideMode.ElideRight, width)
    painter.drawText(QRectF(x, y, width + metrics.averageCharWidth(), box),
                     int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), shown)


def stylesheet(scale: float) -> str:
    """Play, Stop and Details -- here and on the game page, which shares them (its sizes are
    its own). Outlined since Phase 56, over a little of the ground so they read on any art;
    their focus ring is drawn by whoever holds them (the card, outside; the page, ui_detail)."""
    s = lambda value: max(1, round(value * scale))  # noqa: E731
    primary, secondary = ui_rules.COLOR_ON_ART_PRIMARY, ui_rules.COLOR_ON_ART_SECONDARY
    return f"""
    QWidget#ContinueCard {{ background: transparent; }}
    QPushButton#HeroPlay, QPushButton#HeroStop, QPushButton#HeroGhost {{
        border: 1px solid transparent;
        border-radius: {s(ui_rules.CONTROL_RADIUS)}px;
        font-size: {s(ui_rules.CONTINUE_BUTTON_PX)}px;
        font-weight: {ui_rules.HEADING_WEIGHT};
        padding: 0 {s(ui_rules.CONTINUE_PLAY_PADDING)}px;
    }}
    QPushButton#HeroPlay {{
        background: {primary};
        border-color: {ui_rules.COLOR_ACCENT};
        color: {ui_rules.COLOR_ACCENT};
    }}
    QPushButton#HeroPlay:hover {{ background: {ui_theme.layered(primary, ui_rules.COLOR_PRIMARY_HOVER)}; }}
    QPushButton#HeroPlay:pressed {{ background: {ui_theme.layered(primary, ui_rules.COLOR_PRIMARY_PRESSED)}; }}
    QPushButton#HeroStop {{
        background: {primary};
        border-color: {ui_rules.COLOR_STOP};
        color: {ui_rules.COLOR_STOP};
    }}
    QPushButton#HeroStop:hover {{ background: {ui_theme.layered(primary, ui_rules.COLOR_STOP_TINT)}; }}
    QPushButton#HeroStop:pressed {{ background: {ui_theme.layered(primary, ui_rules.COLOR_STOP_TINT_PRESSED)}; }}
    QPushButton#HeroGhost {{
        background: {secondary};
        border-color: {ui_rules.COLOR_DIVIDER};
        color: {ui_rules.COLOR_TEXT};
        padding: 0 {s(ui_rules.CONTINUE_DETAILS_PADDING)}px;
    }}
    QPushButton#HeroGhost:hover {{ background: {ui_theme.layered(secondary, ui_rules.COLOR_SECONDARY_HOVER)}; }}
    QPushButton#HeroGhost:pressed {{ background: {ui_theme.layered(secondary, ui_rules.COLOR_SECONDARY_PRESSED)}; }}
    """
