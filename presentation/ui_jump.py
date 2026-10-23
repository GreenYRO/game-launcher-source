"""Jump back in (Phase 60): three of the games played last, as wide cards above the grid.

The side rail's library -- the design's #1b -- has these three where the top bar's library
has the one Continue playing card. The three answer the library page exactly as that card
does: present or not, open or folded away as the grid scrolls, the pad moving between
their Play buttons, A pressing one, the menu opening at it. So the page only has to know
which of the two it is showing, never how either works.

Which games: the Continue card's rule (ui_continue.eligible), the three played last, newest
first. The first is the wider card, edged in the accent; a click anywhere but Play opens the
game's page, as on the card it replaces.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPropertyAnimation, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSizePolicy, QSpacerItem, QVBoxLayout, QWidget

from presentation import ui_continue
from presentation import ui_covers
from presentation import ui_icons
from presentation import ui_rules
from presentation import ui_theme
from shared import humanize

PLAY_TIP = "Play"
STOP_TIP = "Close this game (unsaved progress will be lost)"


def recent(views: list, count: int = ui_rules.JUMP_COUNT) -> list:
    """The games played last, newest first, by the Continue card's rule."""
    return sorted(ui_continue.eligible(views), key=lambda view: view.last_played.timestamp(),
                  reverse=True)[:count]


def meta_line(view) -> str:
    """How long and when, as the design writes it: "41h 12m · yesterday"."""
    when = humanize.when(view.last_played)
    if view.entry.launch_kind == "exe":
        return f"{humanize.playtime(view.playtime_seconds)} · {when}" if view.playtime_seconds > 0 else when
    return f"{ui_continue.source_label(view)} · {when}"


def ring_width_of(widget: QWidget, scale: float) -> int:
    """The focus ring's width: the library page's (TV mode's thicker one included)."""
    page = widget.parentWidget()
    while page is not None and not hasattr(page, "focus_ring_width"):
        page = page.parentWidget()
    width = page.focus_ring_width if page is not None else ui_rules.FOCUS_RING_WIDTH
    return max(1, round(width * scale))


class JumpCard(QWidget):
    """One game: its art, its name and how long and when, and a round Play."""

    playRequested = Signal(str)
    stopRequested = Signal(str)
    detailsRequested = Signal(str)
    contextRequested = Signal(str, object)

    def __init__(self, covers, metrics, first: bool, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("JumpCard")
        self.covers = covers
        self.metrics = metrics
        self.first = first
        self.view = None
        self.running = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.play_button = QPushButton(self)
        self.play_button.setObjectName("JumpPlay")
        self.play_button.setToolTip(PLAY_TIP)
        # A click must not leave a ring behind; the pad and Tab still reach it.
        self.play_button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.play_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.play_button.clicked.connect(self._play_or_stop)
        self.play_button.installEventFilter(self)
        self.apply_metrics(metrics)

    def set_game(self, view) -> None:
        self.view = view
        if view is not None:
            self.play_button.setAccessibleName(f"{'Stop' if self.running else 'Play'} {view.display_name}")
        self.update()

    def set_running(self, running: bool) -> None:
        """Play becomes Stop while this game is up -- the rule the game page follows."""
        if running == self.running:
            return
        self.running = running
        self.play_button.setObjectName("JumpStop" if running else "JumpPlay")
        self.play_button.setToolTip(STOP_TIP if running else PLAY_TIP)
        self._apply_icon()
        # Restyle, or it keeps the look it was built with -- the Phase 21 trap.
        self.play_button.style().unpolish(self.play_button)
        self.play_button.style().polish(self.play_button)
        self.set_game(self.view)

    def set_starting(self, starting: bool) -> None:
        """Play rests while its game starts (Phase 99), and says why."""
        self.play_button.setEnabled(not starting)
        self.play_button.setToolTip(ui_rules.STARTING_TEXT if starting else (STOP_TIP if self.running else PLAY_TIP))

    def _play_or_stop(self) -> None:
        if self.view is not None:
            (self.stopRequested if self.running else self.playRequested).emit(self.view.key)

    def apply_metrics(self, metrics) -> None:
        self.metrics = metrics
        s = metrics.scale
        self.setFixedHeight(max(60, round(ui_rules.JUMP_HEIGHT * s)))
        size = max(16, round(ui_rules.JUMP_PLAY * s))
        self.play_button.setFixedSize(size, size)
        self.play_button.setProperty("ringRadius", size / 2)
        self._apply_icon()
        self._place()

    def _apply_icon(self) -> None:
        px = max(8, round(ui_rules.JUMP_PLAY_ICON_PX * self.metrics.scale))
        glyph, colour = ("stop_solid", ui_rules.COLOR_STOP) if self.running else ("play_solid", ui_rules.COLOR_ACCENT)
        self.play_button.setIcon(ui_icons.icon(glyph, colour, px))
        self.play_button.setIconSize(QSize(px, px))

    def _place(self) -> None:
        s = self.metrics.scale
        size = self.play_button.width()
        self.play_button.move(self.width() - round(ui_rules.JUMP_PADDING_X * s) - size,
                              self.height() - round(ui_rules.JUMP_PADDING_BOTTOM * s) - size)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._place()

    def eventFilter(self, watched, event) -> bool:
        if watched is self.play_button and event.type() in (QEvent.Type.FocusIn, QEvent.Type.FocusOut):
            self.update()
        return super().eventFilter(watched, event)

    def _art(self, width: int, height: int) -> QPixmap:
        """The wide art if there is some, else the cover cropped to the card, as the
        Continue card does; only a game with no art at all gets its accent wash."""
        for path in (self.view.banner_source, self.view.cover_source):
            if ui_covers.is_image(path):
                pixmap = self.covers.image(path, width, height)
                if not pixmap.isNull():
                    return pixmap
        return self.covers.banner(self.view, width, height)

    def paintEvent(self, event) -> None:
        if self.view is None:
            return
        s = self.metrics.scale
        card = QRectF(self.rect())
        radius = ui_rules.JUMP_RADIUS * s
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
        # The ground over the art's foot, so the words read on any picture.
        scrim = QLinearGradient(0, card.bottom(), 0, card.top())
        dark = QColor(ui_rules.COLOR_SCRIM)
        for stop, alpha in ui_rules.JUMP_SCRIM:
            dark.setAlpha(alpha)
            scrim.setColorAt(stop, dark)
        painter.fillRect(card, scrim)
        painter.restore()
        edge = ui_rules.COLOR_JUMP_FIRST_EDGE if self.first else ui_rules.COLOR_BORDER
        painter.setPen(QPen(QColor(edge), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(card.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)

        # The name over how long and when, standing on the card's foot beside Play.
        left = card.left() + ui_rules.JUMP_PADDING_X * s
        room = self.play_button.x() - ui_rules.JUMP_TEXT_GAP * s - left
        foot = card.bottom() - ui_rules.JUMP_PADDING_BOTTOM * s
        name = QFont(ui_icons.display_family())
        name.setPixelSize(max(8, round(ui_rules.JUMP_NAME_PX * s)))
        name.setWeight(QFont.Weight(ui_rules.HEADING_WEIGHT))
        meta = QFont(ui_icons.body_family())
        meta.setPixelSize(max(7, round(ui_rules.JUMP_META_PX * s)))
        meta_box = QFontMetricsF(meta).height()
        name_box = QFontMetricsF(name).height()
        for font, text, colour, top, box in (
            (meta, meta_line(self.view), ui_rules.COLOR_JUMP_META, foot - meta_box, meta_box),
            (name, self.view.display_name, ui_rules.COLOR_TEXT, foot - meta_box - name_box, name_box),
        ):
            painter.setFont(font)
            painter.setPen(QColor(colour))
            shown = QFontMetricsF(font).elidedText(text, Qt.TextElideMode.ElideRight, max(0.0, room))
            painter.drawText(QRectF(left, top, max(0.0, room) + 2, box),
                             int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), shown)

        # The design's ring, 2 px out from Play, when the pad or the keyboard is on it.
        if self.play_button.hasFocus():
            ring = ring_width_of(self, s)
            out = ui_rules.FOCUS_RING_GAP * s + ring / 2
            painter.setPen(QPen(QColor(ui_rules.TILE_FOCUS_COLOR), ring))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QRectF(self.play_button.geometry()).adjusted(-out, -out, out, out))

    def mouseReleaseEvent(self, event) -> None:
        # Anywhere on the card that is not Play opens the game's page.
        if self.view is not None and event.button() == Qt.MouseButton.LeftButton:
            self.detailsRequested.emit(self.view.key)
            return
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event) -> None:
        if self.view is not None:
            self.contextRequested.emit(self.view.key, event.globalPos())


class JumpBackIn(QWidget):
    """The label and the three cards, folding away as the grid scrolls (the Continue card's
    mechanism, kept whole: maximumHeight driven, anchored to its foot)."""

    playRequested = Signal(str)
    stopRequested = Signal(str)
    detailsRequested = Signal(str)
    contextRequested = Signal(str, object)

    def __init__(self, covers, metrics, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("JumpBackIn")
        self.metrics = metrics
        self.present = False
        self.collapsed = False
        self.reduce_animations = ui_rules.REDUCE_ANIMATIONS_DEFAULT
        self._animation = None
        self._focused = 0
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(0)

        self.label = QLabel("JUMP BACK IN")
        self.label.setObjectName("SectionLabel")
        self.cards = [JumpCard(covers, metrics, first=index == 0) for index in range(ui_rules.JUMP_COUNT)]
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        for card, weight in zip(self.cards, ui_rules.JUMP_WEIGHTS):
            row.addWidget(card, weight)
            for signal in ("playRequested", "stopRequested", "detailsRequested", "contextRequested"):
                getattr(card, signal).connect(getattr(self, signal))
        self._row = row
        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.addStretch(1)  # anchored to its foot, so folding slides it up and away
        layout.addWidget(self.label)
        self._under_label = QSpacerItem(0, 0)
        layout.addSpacerItem(self._under_label)
        layout.addLayout(row)
        self.apply_metrics(metrics)
        self.setMaximumHeight(0)
        self.setVisible(False)

    # -- contents -------------------------------------------------------------------------

    @property
    def games(self) -> list:
        return [card for card in self.cards if card.view is not None]

    @property
    def view(self):
        """The game the pad is on, or the first: what the backdrop and the menu are about."""
        games = self.games
        if not games:
            return None
        return games[min(self._focused, len(games) - 1)].view

    def set_games(self, views: list) -> None:
        for index, card in enumerate(self.cards):
            card.set_game(views[index] if index < len(views) else None)
            card.setVisible(index < len(views))

    def set_running(self, is_running) -> None:
        """Each card's Play becomes Stop while its game is up; `is_running(key)` says which."""
        for card in self.cards:
            card.set_running(card.view is not None and is_running(card.view.key))

    def set_starting(self, is_starting) -> None:
        """Each card's Play rests while its game starts (Phase 99)."""
        for card in self.cards:
            card.set_starting(card.view is not None and is_starting(card.view.key))

    def update(self, *args) -> None:  # the cards paint themselves
        super().update(*args)
        for card in self.cards:
            card.update()

    # -- the pad --------------------------------------------------------------------------

    @property
    def buttons(self) -> tuple:
        return tuple(card.play_button for card in self.games)

    @property
    def focused_index(self) -> int:
        return self._focused

    def focus_button(self, index: int) -> None:
        games = self.games
        if not games:
            return
        self._focused = max(0, min(len(games) - 1, index))
        games[self._focused].play_button.setFocus(Qt.FocusReason.OtherFocusReason)

    def focus_step(self, step: int) -> None:
        self.focus_button(self._focused + step)

    def clear_focus(self) -> None:
        for card in self.cards:
            if card.play_button.hasFocus():
                card.play_button.clearFocus()
        self._focused = 0

    def activate_focused(self) -> None:
        games = self.games
        if games:
            games[min(self._focused, len(games) - 1)].play_button.click()

    # -- folding --------------------------------------------------------------------------

    @property
    def shown(self) -> bool:
        """On the page and open, so the pad can move up into it (never isVisible: Phase 17)."""
        return self.present and not self.collapsed

    def set_present(self, present: bool) -> None:
        self.present = present and bool(self.games)
        self._apply_height(animate=False)

    def set_collapsed(self, collapsed: bool, animate: bool = True) -> None:
        if collapsed == self.collapsed:
            return
        self.collapsed = collapsed
        self._apply_height(animate=animate)

    def full_height(self) -> int:
        """The label, the cards, and the gap down to All games."""
        s = self.metrics.scale
        label = self.label.sizeHint().height()
        return (label + round(ui_rules.JUMP_LABEL_BELOW * s) + round(ui_rules.JUMP_HEIGHT * s)
                + round(ui_rules.RAIL_PAGE_GAP * s))

    def _apply_height(self, animate: bool) -> None:
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

    def sizeHint(self) -> QSize:
        return QSize(super().sizeHint().width(), self.full_height())

    def minimumSizeHint(self) -> QSize:
        return QSize(0, 0)

    def apply_metrics(self, metrics) -> None:
        self.metrics = metrics
        s = metrics.scale
        inset = metrics.grid_inset
        # In from the sides by as much as the grid's first cover is, so the cards, the
        # label and the covers share one left edge (the Continue card's rule, Phase 55).
        self.layout().setContentsMargins(inset, 0, inset, round(ui_rules.RAIL_PAGE_GAP * s))
        self._under_label.changeSize(0, round(ui_rules.JUMP_LABEL_BELOW * s))
        self._row.setSpacing(round(ui_rules.JUMP_GAP * s))
        for card in self.cards:
            card.apply_metrics(metrics)
        self.layout().invalidate()
        self.updateGeometry()
        self._apply_height(animate=False)


def stylesheet(scale: float) -> str:
    """The cards' round Play, the section labels the rail's library uses."""
    s = lambda value: max(1, round(value * scale))  # noqa: E731
    pt = lambda px: f"{ui_theme.px_to_pt(px * scale):.2f}pt"  # noqa: E731 -- fractional px
    primary = ui_rules.COLOR_ON_ART_PRIMARY
    return f"""
    QWidget#JumpBackIn, QWidget#JumpCard {{ background: transparent; }}
    QPushButton#JumpPlay, QPushButton#JumpStop {{
        background: {primary};
        border: 1px solid {ui_rules.COLOR_ACCENT};
        border-radius: {s(ui_rules.JUMP_PLAY) // 2}px;
        padding: 0;
    }}
    QPushButton#JumpPlay:hover {{ background: {ui_theme.layered(primary, ui_rules.COLOR_PRIMARY_HOVER)}; }}
    QPushButton#JumpPlay:pressed {{ background: {ui_theme.layered(primary, ui_rules.COLOR_PRIMARY_PRESSED)}; }}
    QPushButton#JumpStop {{ border-color: {ui_rules.COLOR_STOP}; }}
    QPushButton#JumpStop:hover {{ background: {ui_theme.layered(primary, ui_rules.COLOR_STOP_TINT)}; }}
    QLabel#SectionLabel {{
        background: transparent;
        color: {ui_rules.COLOR_SECTION_LABEL};
        font-size: {pt(ui_rules.SECTION_LABEL_PX)};
        letter-spacing: {ui_rules.SECTION_LABEL_PX * ui_rules.SECTION_LABEL_TRACKING * scale:.2f}px;
    }}
    """
