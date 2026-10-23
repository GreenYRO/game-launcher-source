"""For you (Phase 98): a place of its own, under Library -- what is waiting, most like what you play, and why;
and what fits tonight.

The page shows logic/recommend.py's Page and nothing it does not say: the first FORYOU_GAMES waiting games
large, each with its reason line and Play and Details; the rest a line each; the waiting games with no
genres named apart (the cold start), and the ones played lately, which Jump back in offers already; then
Tonight -- a chooser, and the games whose typical session fits. Its words are the wishlist's own, because
the fit is the same function (logic/fit.py). Then, when there is any, Left behind (Phase 103): the games marked
Playing that nothing has been heard of for a while, each with three answers -- Finished, Dropped, Still playing.
A nudge waits here, where it will be seen; nothing else announces it.

The pad: up and down move between the page's rows (the three, each line, the chooser, Tonight's games),
left and right along a row -- past either end, to the next place along the bar, as on every tab -- A plays,
X opens the game's menu (Details first), Y moves Tonight's choice along; one ring on screen. On Left behind
the ring stands on an answer, and A gives it.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy,
                               QVBoxLayout, QWidget)

from logic import recommend as recommend_module
from presentation import ui_icons
from presentation import ui_pageshell
from presentation import ui_rules
from presentation.ui_cards import FocusRing
from presentation.ui_library import Chip
from presentation.ui_stats import rounded
from shared import rules

log = logging.getLogger(__name__)

RINGED = ("ForYouPick", "ForYouRow", "ForYouTonight", "Chip", "ForYouAnswer")


class _Answer(QPushButton):
    """One of Left behind's three answers for one game (Phase 103)."""

    def __init__(self, key: str, answer: str, words: str) -> None:
        super().__init__(words)
        self.setObjectName("ForYouAnswer")
        self.key = key
        self.answer = answer
        self.setCursor(Qt.CursorShape.PointingHandCursor)


class _Game(QFrame):
    """A game on the page -- large, a line, or Tonight's: a cover, words, and a round Play. Takes the focus,
    so the pad's ring is on it; its buttons never do."""

    def __init__(self, page, kind: str, key: str) -> None:
        super().__init__()
        self.page, self.key = page, key
        self.setObjectName(kind)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event) -> None:
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        self.page.detailsRequested.emit(self.key)

    def contextMenuEvent(self, event) -> None:
        self.page.menuRequested.emit(self.key, event.globalPos())


class ForYouPage(QWidget):
    """The page. B or Escape leaves, as from every tab; nothing here writes but Tonight's remembered choice."""

    backRequested = Signal()
    tabSelected = Signal(str)
    playRequested = Signal(str)  # a game's key
    detailsRequested = Signal(str)
    menuRequested = Signal(str, object)  # key, where (global)
    choiceChanged = Signal(int)  # Tonight's choice, in minutes
    answered = Signal(str, str)  # Left behind (Phase 103): a game's key, and "finished", "dropped" or "still"

    def __init__(self, metrics, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("ForYouPage")
        self.metrics = metrics
        self.focus_ring_width = ui_rules.FOCUS_RING_WIDTH
        self.model: recommend_module.Page | None = None
        self.views: dict = {}  # key -> GameView, set by the window: covers and names come from them
        self.covers = None  # the window's CoverFactory
        self.rows: list[list[QWidget]] = []  # what the pad walks, top to bottom
        self.plays: dict[str, list[QPushButton]] = {}  # each game's Play buttons on the page (Phase 99: Starting...)
        self.starting_key: str | None = None
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._build()

    # -- construction -----------------------------------------------------------------------

    def _build(self) -> None:
        self.header_row = ui_pageshell.PageHeader(ui_pageshell.TAB_FORYOU, self)
        self.header_row.backRequested.connect(self.backRequested)
        self.header_row.tabSelected.connect(self.tabSelected)
        self.page_title = QLabel("For you")
        self.page_title.setObjectName("PageTitle")
        self.page_title.setVisible(False)
        self.rail = False
        self.subtitle = QLabel("What you have and have not started yet, most like what you play")
        self.subtitle.setObjectName("ForYouSubtitle")
        self.subtitle.setWordWrap(True)

        self.body = QWidget()
        self.body.setObjectName("Clear")
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)

        self.content = QWidget()
        self.content.setObjectName("Clear")
        outer = QVBoxLayout(self.content)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.page_title)
        outer.addWidget(self.subtitle)
        outer.addWidget(self.body)
        outer.addStretch(1)
        self.column = ui_pageshell.PageColumn(self.content, ui_rules.FORYOU_CONTENT_MAX_WIDTH)
        self.header_column = ui_pageshell.PageColumn(self.header_row, ui_rules.FORYOU_CONTENT_MAX_WIDTH)
        self.scroll = QScrollArea(self)
        self.scroll.setObjectName("ForYouScroll")
        self.scroll.viewport().setObjectName("ForYouViewport")
        self.scroll.setWidget(self.column)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout = QVBoxLayout(self)
        layout.addWidget(self.header_column)
        layout.addWidget(self.scroll, 1)

        self.chips: dict[int, Chip] = {}
        self.chip_group = QButtonGroup(self)
        self.chip_group.setExclusive(True)
        for minutes, words, _within in rules.TONIGHT_CHOICES:
            chip = Chip(words)
            chip.setCheckable(True)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setFocusPolicy(Qt.FocusPolicy.TabFocus)
            chip.clicked.connect(lambda _checked=False, m=minutes: self.choose(m))
            self.chip_group.addButton(chip)
            self.chips[minutes] = chip

        self.focus_ring = FocusRing(self, lambda widget: widget.objectName() in RINGED and self.isAncestorOf(widget))
        self.focus_ring.clip = self.scroll.viewport()
        self.apply_metrics(self.metrics)

    def _s(self, value: float) -> int:
        return max(1, round(value * self.metrics.scale))

    def _label(self, words: str, name: str, wrap: bool = False) -> QLabel:
        label = QLabel(words)
        label.setObjectName(name)
        label.setWordWrap(wrap)
        label.setTextFormat(Qt.TextFormat.PlainText)
        return label

    def _thumb(self, key: str, size: tuple[int, int]) -> QLabel:
        width, height = self._s(size[0]), self._s(size[1])
        view = self.views.get(key)
        art = self.covers.cover(view, width, height, with_name=False) if (self.covers and view) else None
        thumb = QLabel()
        thumb.setObjectName("ForYouThumb")
        thumb.setFixedSize(width, height)
        thumb.setPixmap(rounded(art, width, height, self._s(ui_rules.FORYOU_THUMB_RADIUS), self.devicePixelRatioF() or 1.0))
        return thumb

    def _round_play(self, key: str) -> QPushButton:
        button = QPushButton()
        button.setObjectName("ForYouRound")
        button.setIcon(ui_icons.icon("play_solid", ui_rules.COLOR_ACCENT_HOVER, self._s(16)))
        button.setFixedSize(self._s(ui_rules.FORYOU_ROUND_PX), self._s(ui_rules.FORYOU_ROUND_PX))
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setToolTip("Play")
        button.clicked.connect(lambda: self.playRequested.emit(key))
        self.plays.setdefault(key, []).append(button)
        return button

    def _section(self, words: str) -> QLabel:
        return self._label(words.upper(), "ForYouSection")

    # -- filling it in ----------------------------------------------------------------------

    def set_page(self, model: recommend_module.Page | None) -> None:
        self.model = model
        self._refill()

    def _clear(self) -> None:
        while self.body_layout.count():
            item = self.body_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)  # off the screen now; deleteLater only frees it later (Phase 23)
                widget.deleteLater()
            elif item.layout() is not None:
                self._drop(item.layout())

    def _drop(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item.widget() is not None:
                if item.widget() in self.chips.values():
                    item.widget().setParent(None)  # the chips are the page's own, kept for the next fill
                    continue
                item.widget().setParent(None)
                item.widget().deleteLater()
            elif item.layout() is not None:
                self._drop(item.layout())

    def _fill(self) -> None:
        self._clear()
        self.rows = []
        self.plays = {}
        model = self.model
        if model is None:
            self.body_layout.addWidget(self._label("For you needs the library database; it comes with the "
                                                   "launcher's next start.", "ForYouNote", wrap=True))
            return
        gap = self._s(ui_rules.FORYOU_SECTION_GAP)
        self.body_layout.addWidget(self._section("Waiting for you"))
        if model.picks:
            row = QHBoxLayout()
            row.setSpacing(self._s(ui_rules.FORYOU_PICK_GAP))
            picks = [self._pick(s) for s in model.picks]
            for widget in picks:
                row.addWidget(widget, 1)
            for _ in range(rules.FORYOU_GAMES - len(picks)):
                row.addStretch(1)
            self.body_layout.addLayout(row)
            self.rows.append(picks)
            self.body_layout.addWidget(self._label(recommend_module.QUIET, "ForYouNote", wrap=True))
        elif model.empty:
            self.body_layout.addWidget(self._label(model.empty, "ForYouEmpty", wrap=True))
        if model.more:
            self.body_layout.addSpacing(gap // 2)
            self.body_layout.addWidget(self._section("Also waiting"))
            for suggestion in model.more:
                line = self._line(suggestion)
                self.body_layout.addWidget(line)
                self.rows.append([line])
            if model.beyond:
                self.body_layout.addWidget(self._label(f"and {model.beyond} more", "ForYouNote"))
        for words in (model.cold_line, model.recent_line):
            if words:
                self.body_layout.addWidget(self._label(words, "ForYouQuiet", wrap=True))
        self.body_layout.addSpacing(gap)
        rule = QFrame()
        rule.setObjectName("ForYouRule")
        rule.setFixedHeight(1)
        self.body_layout.addWidget(rule)
        self.body_layout.addSpacing(gap // 2)
        self._fill_tonight()
        if model.left:
            self._fill_left()
        if self.starting_key is not None:
            self.set_starting(self.starting_key)

    def _pick(self, suggestion) -> QWidget:
        card = _Game(self, "ForYouPick", suggestion.key)
        pad = self._s(ui_rules.FORYOU_PICK_PADDING)
        line = QHBoxLayout(card)
        line.setContentsMargins(pad, pad, pad, pad)
        line.setSpacing(pad)
        line.addWidget(self._thumb(suggestion.key, ui_rules.FORYOU_PICK_COVER), 0, Qt.AlignmentFlag.AlignTop)
        words = QVBoxLayout()
        words.setSpacing(self._s(4))
        words.addWidget(self._label(suggestion.name, "ForYouPickName", wrap=True))
        words.addWidget(self._label(suggestion.likeness, "ForYouLike", wrap=True))
        words.addWidget(self._label(suggestion.genres, "ForYouText", wrap=True))
        words.addWidget(self._label(suggestion.played, "ForYouMuted", wrap=True))
        words.addStretch(1)
        buttons = QHBoxLayout()
        buttons.setSpacing(self._s(8))
        play = QPushButton(" Play")
        play.setObjectName("ForYouPlay")
        play.setIcon(ui_icons.icon("play_solid", ui_rules.COLOR_ACCENT_HOVER, self._s(14)))
        play.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        play.clicked.connect(lambda: self.playRequested.emit(suggestion.key))
        self.plays.setdefault(suggestion.key, []).append(play)
        details = QPushButton("Details")
        details.setObjectName("ForYouDetails")
        details.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        details.clicked.connect(lambda: self.detailsRequested.emit(suggestion.key))
        buttons.addWidget(play)
        buttons.addWidget(details)
        buttons.addStretch(1)
        words.addLayout(buttons)
        line.addLayout(words, 1)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        return card

    def _line(self, suggestion) -> QWidget:
        row = _Game(self, "ForYouRow", suggestion.key)
        row.setFixedHeight(self._s(ui_rules.FORYOU_ROW_HEIGHT))
        line = QHBoxLayout(row)
        line.setContentsMargins(self._s(6), 0, self._s(6), 0)
        line.setSpacing(self._s(12))
        line.addWidget(self._thumb(suggestion.key, ui_rules.FORYOU_ROW_COVER))
        name = self._label(suggestion.name, "ForYouRowName")
        name.setMinimumWidth(1)
        line.addWidget(name, 36)
        reason = self._label(suggestion.reason, "ForYouText")
        reason.setMinimumWidth(1)
        line.addWidget(reason, 46)
        played = self._label(suggestion.played, "ForYouMuted")
        played.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        line.addWidget(played, 18)
        line.addWidget(self._round_play(suggestion.key))
        return row

    def _fill_tonight(self) -> None:
        tonight = self.model.tonight
        head = QHBoxLayout()
        head.setSpacing(self._s(8))
        head.addWidget(self._section("Tonight"))
        head.addSpacing(self._s(16))
        for minutes, chip in self.chips.items():
            chip.scale = self.metrics.scale
            chip.setFixedHeight(max(20, round(ui_rules.CHIP_HEIGHT * self.metrics.scale)))
            chip.setChecked(minutes == tonight.minutes)
            head.addWidget(chip)
        head.addStretch(1)
        if tonight.note:
            head.addWidget(self._label(tonight.note, "ForYouNote"))
        self.body_layout.addLayout(head)
        self.rows.append(list(self.chips.values()))
        if tonight.games:
            row = QHBoxLayout()
            row.setSpacing(self._s(ui_rules.FORYOU_PICK_GAP))
            cards = [self._tonight_card(typical, words) for typical, words in tonight.games]
            for card in cards:
                row.addWidget(card, 1)
            for _ in range(rules.FORYOU_TONIGHT - len(cards)):
                row.addStretch(1)
            self.body_layout.addLayout(row)
            self.rows.append(cards)
        else:
            self.body_layout.addWidget(self._label(tonight.empty, "ForYouEmpty", wrap=True))

    def _tonight_card(self, typical, words: str) -> QWidget:
        card = _Game(self, "ForYouTonight", typical.key)
        card.setFixedHeight(self._s(ui_rules.FORYOU_TONIGHT_HEIGHT))
        line = QHBoxLayout(card)
        line.setContentsMargins(self._s(10), self._s(10), self._s(10), self._s(10))
        line.setSpacing(self._s(12))
        line.addWidget(self._thumb(typical.key, ui_rules.FORYOU_TONIGHT_COVER))
        text = QVBoxLayout()
        text.setSpacing(self._s(2))
        name = self._label(typical.name, "ForYouRowName")
        name.setMinimumWidth(1)
        text.addWidget(name)
        text.addWidget(self._label(typical.usual, "ForYouText"))
        text.addWidget(self._label(words, "ForYouMuted"))
        line.addLayout(text, 1)
        line.addWidget(self._round_play(typical.key))
        return card

    def _fill_left(self) -> None:
        """Left behind (Phase 103): after Tonight, the games marked Playing nothing has been heard of for a while,
        each with its cover, how long ago and at how many hours, and three answers. A line of answers is one
        row for the pad."""
        gap = self._s(ui_rules.FORYOU_SECTION_GAP)
        self.body_layout.addSpacing(gap)
        rule = QFrame()
        rule.setObjectName("ForYouRule")
        rule.setFixedHeight(1)
        self.body_layout.addWidget(rule)
        self.body_layout.addSpacing(gap // 2)
        head = QHBoxLayout()
        head.addWidget(self._section("Left behind"))
        head.addStretch(1)
        head.addWidget(self._label(recommend_module.LEFT_NOTE, "ForYouNote"))
        self.body_layout.addLayout(head)
        games = list(self.model.left)
        per_line = ui_rules.FORYOU_LEFT_PER_LINE
        for start in range(0, len(games), per_line):
            line = QHBoxLayout()
            line.setSpacing(self._s(ui_rules.FORYOU_PICK_GAP))
            answers: list[QPushButton] = []
            for game in games[start:start + per_line]:
                card, buttons = self._left_card(game)
                line.addWidget(card, 1)
                answers += buttons
            for _ in range(per_line - len(games[start:start + per_line])):
                line.addStretch(1)
            self.body_layout.addLayout(line)
            self.rows.append(answers)
        self.body_layout.addWidget(self._label(recommend_module.STILL_LINE, "ForYouQuiet", wrap=True))

    def _left_card(self, game) -> tuple[QWidget, list]:
        card = QFrame()
        card.setObjectName("ForYouLeft")
        pad = self._s(ui_rules.FORYOU_PICK_PADDING)
        line = QHBoxLayout(card)
        line.setContentsMargins(pad, pad, pad, pad)
        line.setSpacing(pad)
        line.addWidget(self._thumb(game.key, ui_rules.FORYOU_LEFT_COVER), 0, Qt.AlignmentFlag.AlignTop)
        words = QVBoxLayout()
        words.setSpacing(self._s(4))
        words.addWidget(self._label(game.name, "ForYouPickName", wrap=True))
        words.addWidget(self._label(game.words, "ForYouText", wrap=True))
        row = QHBoxLayout()
        row.setSpacing(self._s(8))
        buttons = []
        for answer, text in recommend_module.ANSWERS:
            button = _Answer(game.key, answer, text)
            button.clicked.connect(lambda _checked=False, k=game.key, a=answer: self.answered.emit(k, a))
            row.addWidget(button)
            buttons.append(button)
        row.addStretch(1)
        words.addLayout(row)
        line.addLayout(words, 1)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        return card, buttons

    def on_answer(self) -> bool:
        """Whether the ring stands on one of Left behind's answers -- the TV's hints say A answers."""
        return isinstance(self.focusWidget(), _Answer)

    def set_starting(self, key: str | None) -> None:
        """While a game starts (Phase 99) its Play buttons here rest, the large one saying so."""
        self.starting_key = key
        for game, buttons in self.plays.items():
            for button in buttons:
                button.setEnabled(game != key)
                if button.objectName() == "ForYouPlay":
                    button.setText(f" {ui_rules.STARTING_TEXT}" if game == key else " Play")

    # -- Tonight's choice -------------------------------------------------------------------

    def choose(self, minutes: int) -> None:
        """A choice made: the games for it, worked out from what the page already holds; remembered."""
        if self.model is None:
            return
        tonight = recommend_module.tonight(self.model.typical, minutes)
        self.model = recommend_module.Page(**{**self.model.__dict__, "tonight": tonight})
        self._refill()
        self.choiceChanged.emit(tonight.minutes)

    def _refill(self) -> None:
        """Filled again where the ring stays put: the same row and place, the chosen chip on the chooser --
        the rows above Tonight do not change with it, and the pad must not lose its place."""
        at = self._at()
        self._fill()
        if at is None or not self.rows:
            return
        row = self.rows[min(at[0], len(self.rows) - 1)]
        target = row[min(at[1], len(row) - 1)]
        if row == list(self.chips.values()):
            target = self.chips[self.model.tonight.minutes]
        target.setFocus(Qt.FocusReason.OtherFocusReason)

    def next_choice(self) -> None:
        """Y on the pad: Tonight's choice one along, round to the first."""
        minutes = [m for m, *_ in rules.TONIGHT_CHOICES]
        now = self.model.tonight.minutes if self.model is not None else rules.TONIGHT_DEFAULT
        self.choose(minutes[(minutes.index(now) + 1) % len(minutes)])

    # -- the pad and the keyboard -----------------------------------------------------------

    def _at(self) -> tuple[int, int] | None:
        current = self.focusWidget()
        for r, row in enumerate(self.rows):
            if current in row:
                return r, row.index(current)
        return None

    def ensure_focus(self) -> None:
        """On the way in: the first game, or the chooser when nothing is waiting."""
        if self.rows:
            self.rows[0][0].setFocus(Qt.FocusReason.OtherFocusReason)
            self.scroll.ensureWidgetVisible(self.rows[0][0])
        else:
            self.setFocus(Qt.FocusReason.OtherFocusReason)

    def move(self, dx: int, dy: int) -> bool:
        """One step. False when a sideways step would leave the row: the window moves to the next place."""
        at = self._at()
        if at is None:
            self.ensure_focus()
            return True
        r, c = at
        if dy:
            r = max(0, min(len(self.rows) - 1, r + dy))
            target = self.rows[r][min(c, len(self.rows[r]) - 1)]
            if self.rows[r] == list(self.chips.values()):
                target = self.chips[self.model.tonight.minutes]
        else:
            c += dx
            if not 0 <= c < len(self.rows[r]):
                return False
            target = self.rows[r][c]
            if target in self.chips.values():
                self.choose(next(m for m, chip in self.chips.items() if chip is target))
                return True
        target.setFocus(Qt.FocusReason.OtherFocusReason)
        self.scroll.ensureWidgetVisible(target, 0, self._s(24))
        return True

    def current_key(self) -> str | None:
        current = self.focusWidget()
        return current.key if isinstance(current, (_Game, _Answer)) else None

    def activate_current(self) -> None:
        current = self.focusWidget()
        if isinstance(current, _Answer):  # Left behind: A gives the answer the ring is on (Phase 103)
            self.answered.emit(current.key, current.answer)
            return
        key = self.current_key()
        if key is not None:
            self.playRequested.emit(key)

    def context_for_current(self) -> None:
        current = self.focusWidget()
        if isinstance(current, (_Game, _Answer)):
            self.menuRequested.emit(current.key, current.mapToGlobal(current.rect().center()))

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.backRequested.emit()
            return
        steps = {Qt.Key.Key_Up: (0, -1), Qt.Key.Key_Down: (0, 1), Qt.Key.Key_Left: (-1, 0), Qt.Key.Key_Right: (1, 0)}
        if key in steps:
            self.move(*steps[key])
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.activate_current()
            return
        super().keyPressEvent(event)

    # -- chrome -----------------------------------------------------------------------------

    def apply_metrics(self, metrics) -> None:
        self.metrics = metrics
        s = metrics.scale
        top = ui_rules.RAIL_PAGE_TOP if getattr(self, "rail", False) else ui_rules.PAGE_COLUMN_TOP
        self.layout().setContentsMargins(0, max(6, round(top * s)), 0, 0)
        self.layout().setSpacing(0)
        self.content.layout().setContentsMargins(0, 0, 0, max(10, round(ui_rules.STATS_PAGE_MARGIN * s)))
        self.content.layout().setSpacing(max(6, round(ui_rules.FORYOU_SECTION_GAP * s / 2)))
        self.body_layout.setSpacing(max(6, round(ui_rules.FORYOU_SECTION_GAP * s / 2)))
        cap = round(ui_rules.FORYOU_CONTENT_MAX_WIDTH * s)
        self.content.setMaximumWidth(cap)
        self.header_row.setMaximumWidth(cap)
        for column in (self.column, self.header_column):
            column.set_scale(s)
        if self.model is not None:
            self._refill()

    def set_rail(self, rail: bool) -> None:
        """Beside the side rail or under the top bar (Phase 60): the column's place, the top."""
        self.rail = rail
        self.page_title.setVisible(rail)
        for column in (self.column, self.header_column):
            column.set_rail(rail)
        self.apply_metrics(self.metrics)


def stylesheet(scale: float) -> str:
    """Appended to the app stylesheet; only affects this page."""
    s = lambda value: max(1, round(value * scale))  # noqa: E731
    radius = s(ui_rules.FORYOU_RADIUS)
    return f"""
    QScrollArea#ForYouScroll, QWidget#ForYouViewport {{ background: transparent; border: none; }}
    QWidget#ForYouPage QLabel {{ background: transparent; border: none; }}
    QLabel#ForYouSubtitle {{ font-size: {s(ui_rules.FORYOU_SUBTITLE_PX)}px; color: {ui_rules.COLOR_TEXT_MUTED}; }}
    QLabel#ForYouSection {{
        font-size: {s(ui_rules.FORYOU_SECTION_PX)}px; font-weight: {ui_rules.HEADING_WEIGHT};
        letter-spacing: {ui_rules.FORYOU_SECTION_TRACKING * scale:.1f}px; color: {ui_rules.COLOR_SECTION_LABEL};
    }}
    QFrame#ForYouPick, QFrame#ForYouTonight, QFrame#ForYouLeft {{
        background: {ui_rules.COLOR_SURFACE}; border: 1px solid {ui_rules.COLOR_BORDER}; border-radius: {radius}px;
    }}
    QFrame#ForYouLeft QLabel {{ background: transparent; border: none; }}
    QFrame#ForYouRow {{ background: transparent; border: none; border-radius: {s(8)}px; }}
    QFrame#ForYouRow:hover, QFrame#ForYouPick:hover, QFrame#ForYouTonight:hover {{ border-color: {ui_rules.COLOR_ACCENT_700}; }}
    QFrame#ForYouPick QLabel, QFrame#ForYouRow QLabel, QFrame#ForYouTonight QLabel {{ background: transparent; border: none; }}
    QLabel#ForYouPickName {{ font-size: {s(ui_rules.FORYOU_PICK_NAME_PX)}px; font-weight: {ui_rules.HEADING_WEIGHT};
                            color: {ui_rules.COLOR_TEXT}; }}
    QLabel#ForYouLike {{ font-size: {s(ui_rules.FORYOU_PICK_LIKE_PX)}px; font-weight: {ui_rules.HEADING_WEIGHT};
                        color: {ui_rules.COLOR_ACCENT_HOVER}; }}
    QLabel#ForYouRowName {{ font-size: {s(ui_rules.FORYOU_ROW_NAME_PX)}px; font-weight: {ui_rules.HEADING_WEIGHT};
                           color: {ui_rules.COLOR_TEXT}; }}
    QLabel#ForYouText {{ font-size: {s(ui_rules.FORYOU_ROW_TEXT_PX)}px; color: {ui_rules.COLOR_TEXT_SOFT}; }}
    QLabel#ForYouMuted {{ font-size: {s(ui_rules.FORYOU_ROW_TEXT_PX)}px; color: {ui_rules.COLOR_TEXT_MUTED}; }}
    QLabel#ForYouNote {{ font-size: {s(ui_rules.FORYOU_NOTE_PX)}px; color: {ui_rules.COLOR_TEXT_FAINT}; }}
    QLabel#ForYouQuiet {{ font-size: {s(ui_rules.FORYOU_NOTE_PX + 1)}px; color: {ui_rules.COLOR_TEXT_QUIET}; }}
    QLabel#ForYouEmpty {{ font-size: {s(ui_rules.FORYOU_PICK_LIKE_PX)}px; color: {ui_rules.COLOR_TEXT_MUTED}; }}
    QLabel#ForYouThumb {{ background: transparent; }}
    QFrame#ForYouRule {{ background: {ui_rules.COLOR_DIVIDER}; border: none; }}
    QPushButton#ForYouRound {{ border: 1.5px solid {ui_rules.COLOR_ACCENT}; border-radius: {s(ui_rules.FORYOU_ROUND_PX) // 2}px;
                              background: transparent; padding: 0; }}
    QPushButton#ForYouRound:hover {{ background: {ui_rules.COLOR_PRIMARY_HOVER}; }}
    QPushButton#ForYouPlay {{ border: 1px solid {ui_rules.COLOR_ACCENT}; color: {ui_rules.COLOR_ACCENT_HOVER};
                             border-radius: {s(10)}px; padding: {s(6)}px {s(14)}px; font-weight: {ui_rules.HEADING_WEIGHT}; }}
    QPushButton#ForYouPlay:hover {{ background: {ui_rules.COLOR_PRIMARY_HOVER}; }}
    QPushButton#ForYouDetails {{ border-radius: {s(10)}px; padding: {s(6)}px {s(14)}px; font-weight: {ui_rules.HEADING_WEIGHT}; }}
    QPushButton#ForYouAnswer {{ border-radius: {s(10)}px; padding: {s(6)}px {s(12)}px; font-weight: {ui_rules.HEADING_WEIGHT}; }}
    """
