"""The single-game page: its art, what you can do with it, and everything known about it.

Redesigned in Phase 33 (step 3 of 5 of the redesign). The art runs edge to edge and fades
into the backdrop, which on this page glows in the game's own colours. Over it: the cover,
the title, the facts as pills, and one row of actions -- Play, three round buttons
(favorite, folder, and "..." for everything else, which is the right-click menu), and
Playing / Finished / Dropped as one switch. Under it, everything else is a card.

Designed from the empty state outwards. An entry with no Steam record -- every game the
name search could not match -- has no description, no genres and no screenshots, ever. So
each card is shown only when it has something in it, and a page showing nothing but art,
the note card and the details is a normal outcome rather than a broken one.

Back, Previous game and Next game float over the top corners of the page and stay there
while it scrolls, so leaving never means scrolling back up first.
"""

from __future__ import annotations

import html
import logging
from datetime import date, datetime

from PySide6.QtCore import QEvent, QPoint, QRect, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFontMetrics
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from logic import gamedetails
from shared import humanize
from logic import lineage
from logic import rate  # Phase 102
from shared import paths
from shared import rules
from logic import sessions
from presentation import ui_icons
from presentation import ui_rules
from presentation import ui_screenshots
from presentation import ui_theme
from presentation.ui_cards import Card, FlowLayout, FocusRing, SessionBars, clear_widget
from presentation.ui_continue import PLAY_TEXT, STOP_TEXT
from presentation.ui_hero import Banner, CoverArt, Pill, PillRow, TopFade
from adapters.screenshot_worker import HeroWorker, NewsWorker, ScreenshotWorker, plan

log = logging.getLogger(__name__)

CACHE_DIR = str(paths.cache_dir())

BACK_KEYS = (Qt.Key.Key_Escape, Qt.Key.Key_Backspace)
PREV_KEYS = (Qt.Key.Key_Left, Qt.Key.Key_A)
NEXT_KEYS = (Qt.Key.Key_Right, Qt.Key.Key_D)

# The pills under the title, in order: (fact label, icon). The label is the one
# gamedetails.metadata gives the same fact, so facts() can answer by it.
PILLS = (
    ("Running", "play_solid"),  # a game seen running, started outside the launcher (Phase 93)
    # When, how long and how big side by side (the user's order, Phase 102 extension).
    ("Last played", "calendar"),
    ("Played", "clock"),
    ("Installed", "disk"),
    ("Usually", "history"),  # the median of its sessions, with 3 or more of them (Phase 98)
    ("Saves copied", "save"),
    ("Controller", "controller"),  # outlined; the top bar's brand is the filled one
)
NOTE_PROMPT = "Where you left off, the settings that worked -- anything worth remembering."
# The page's buttons that wear the design's ring outside them (Phase 57). The three marks
# are ringed inside instead, by the stylesheet, as the design rings a segmented choice.
RINGED = ("NavPill", "HeroPlay", "HeroStop", "Round", "TextButton", "Danger", "HeroGhost")
# Phase 93: what the page says while the game is seen running in the process list.
OBSERVED_WORDS = "Running — timed by watching"
OBSERVED_PLAY_TEXT = "Running"
OBSERVED_TIP = ("Seen running, started outside the launcher: its session is timed by watching, each end within "
                "a few seconds. The launcher never stops a game it did not start.")
APPROXIMATE = "≈ "  # before an observed session's length: its ends are only as sharp as the looks
FIT_FACT = "Fit"  # Phase 98: a waiting game's fit, in the For you page's own words (the label column is narrow)
# The Played pill (Phase 102 extension): the game's hours as the reports count them -- the launcher's own time
# and Steam's counter on the accounts marked yours, an app once -- and, on a hover, where they came from.
PLAYED_TIP_BOTH = "{steam} on Steam, {launcher} timed by this launcher"
PLAYED_TIP_STEAM = "Steam's own count, on the Steam accounts marked yours"
PLAYED_TIP_LAUNCHER = "Timed by this launcher"


def played_tip(hours: dict) -> str:
    """Where a game's hours came from, for its Played pill: Steam's counter, the launcher's own time, or both."""
    steam = round((hours.get("steam") or 0) * 60)
    launcher = round((hours.get("launcher") or 0) * 60)
    if steam > 0 and launcher > 0:
        return PLAYED_TIP_BOTH.format(steam=humanize.playtime(steam), launcher=humanize.playtime(launcher))
    return PLAYED_TIP_STEAM if steam > 0 else PLAYED_TIP_LAUNCHER


class DetailPage(QWidget):
    playRequested = Signal(str)
    openFolderRequested = Signal(str)
    toggleFavoriteRequested = Signal(str)
    stopRequested = Signal(str)
    uninstallRequested = Signal(str)
    statusRequested = Signal(str, str)  # game key, status -- "" clears it
    rateRequested = Signal(str, str, int)  # game key, its session's start, stars -- a late rating (Phase 102)
    notesRequested = Signal(str)
    menuRequested = Signal(str, object)  # game key, where to open it (a global position)
    backRequested = Signal()
    navigate = Signal(int)
    # A new version of a game you had (Phase 36): this game's key, the earlier install's.
    carryOverRequested = Signal(str, str)
    notSameRequested = Signal(str, str)

    def __init__(self, covers, metrics, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("DetailPage")
        self.covers = covers
        self.metrics = metrics
        self.view = None
        # The window's store, asked for a game's ratings (Phase 102); None where it keeps none.
        self.ratings_of = None
        self._session_starts: list[str] = []
        self.allow_network = True
        self.running = False
        self.observed = False  # seen running in the process list, not started here (Phase 93)
        self.starting = False  # Play pressed, the game not up yet (Phase 99)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._shots: list[tuple[str, str]] = []
        self._thumb_paths: dict[int, str] = {}
        self._full_paths: dict[int, str] = {}
        self._thumb_worker: ScreenshotWorker | None = None
        self._full_worker: ScreenshotWorker | None = None
        self._hero_worker: HeroWorker | None = None
        self._news_worker: NewsWorker | None = None
        self._viewer = None
        self._fact_values: dict[str, str] = {}
        self.steamgriddb_key = ""
        # Asked on every set_view for earlier installs that look like this game (Phase 36):
        # the window's, since only it knows what is installed. None asks nothing.
        self.earlier_for = None
        self.money_for = None  # the window's store, asked what this game cost (Phase 74)
        self.steam_time_for = None  # the window, asked Steam's own hours on my accounts (Phase 76)
        self.hours_for = None  # the window, asked the game's hours as the reports count them (Phase 102 extension)
        self.recommend_for = None  # the window, asked the typical session and the fit (Phase 98)
        self.offer = None  # the earlier install the card is offering, if any
        self.focus_ring_width = ui_rules.FOCUS_RING_WIDTH  # the window's, TV mode's thicker one

        self._build()
        self.apply_metrics(metrics)

    # -- construction ------------------------------------------------------------------------

    def _build(self) -> None:
        self.banner = Banner(self.covers, self.metrics)
        self._build_hero()
        self._build_cards()

        self.content = clear_widget("DetailContent")
        content = QVBoxLayout(self.content)
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)
        content.addWidget(self.banner)
        body_row = QHBoxLayout()
        self._body_row = body_row
        # The cards take all the width up to their cap, and only then do the two sides share
        # what is left. Stretches of 1 against 100 still handed each side a hundredth of the
        # window -- 12 px at 1280, the cards' edge off the cover's (found against the design).
        body_row.addStretch(0)
        body_row.addWidget(self.body, 1)
        body_row.addStretch(0)
        content.addLayout(body_row)
        content.addStretch(1)

        self.scroll = QScrollArea()
        self.scroll.setObjectName("DetailScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # arrows move between games
        self.scroll.viewport().setObjectName("DetailViewport")
        self.scroll.viewport().installEventFilter(self)  # the hero follows its width
        self.scroll.setWidget(self.content)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.scroll)

        # A dark fade across the top that comes in as the page scrolls, so whatever passes
        # under the floating buttons never fights them for legibility.
        self.top_fade = TopFade(self)
        self.scroll.verticalScrollBar().valueChanged.connect(self._fade_follows_scroll)

        # Floating over the top corners, above the scrolling page, so they never scroll away.
        self.back_button = self._nav_button("Library", "back", "Back to the library  (Esc)")
        self.back_button.clicked.connect(self.backRequested)
        # Labelled, and nowhere near the dots in the picture, which move between *this*
        # game's images: two sets of bare arrows would leave you guessing (Phase 11).
        self.prev_button = self._nav_button("Previous game", "chevron_left",
                                            "Previous game  (Left arrow or A)")
        self.prev_button.clicked.connect(lambda: self.navigate.emit(-1))
        self.next_button = self._nav_button("Next game", "chevron_right",
                                            "Next game  (Right arrow or D)")
        self.next_button.setLayoutDirection(Qt.LayoutDirection.RightToLeft)  # arrow after the words
        # Right to left, the space has to follow the words to sit between them and the arrow.
        self.next_button.setText("Next game ")
        self.next_button.clicked.connect(lambda: self.navigate.emit(1))

        self.focus_ring = FocusRing(self, lambda widget: isinstance(widget, QPushButton)
                                    and widget.objectName() in RINGED)
        self.focus_ring.clip = self.scroll.viewport()

    def _nav_button(self, text: str, glyph: str, tip: str) -> QPushButton:
        # Qt leaves 4 px between an icon and the words; one space makes about the design's 6.
        button = QPushButton(f" {text}", self)
        button.setObjectName("NavPill")
        button.setToolTip(tip)
        button.setAccessibleName(text)
        button.setProperty("glyph", glyph)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        return button

    def _round_button(self, glyph: str, tip: str) -> QPushButton:
        button = QPushButton()
        button.setObjectName("Round")
        button.setToolTip(tip)
        button.setAccessibleName(tip)
        button.setProperty("glyph", glyph)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFocusPolicy(Qt.FocusPolicy.TabFocus)  # a click must not leave a ring
        return button

    def _build_hero(self) -> None:
        """Cover, title, facts and the Play row, laid over the foot of the picture."""
        self.cover_art = CoverArt(self.covers, self.metrics)

        self.title_label = QLabel()
        self.title_label.setObjectName("HeroTitle")
        self.title_label.setWordWrap(True)
        self.title_label.setTextFormat(Qt.TextFormat.PlainText)

        self.pills: dict[str, Pill] = {}
        self.pill_row = PillRow()  # a pill's words on a hover: the row shows them (Phase 102 extension)
        self._pill_flow = FlowLayout(self.pill_row)
        for fact, _glyph in PILLS:
            pill = Pill(fact)
            pill.setVisible(False)
            self.pills[fact] = pill
            self._pill_flow.addWidget(pill)

        self.play_button = QPushButton(PLAY_TEXT)
        self.play_button.setObjectName("HeroPlay")
        # "variant", not "size": every widget already has a property called size (its
        # dimensions), and a stylesheet selector on it never matched. Caught by a test.
        self.play_button.setProperty("variant", "large")
        self.play_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.play_button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.play_button.clicked.connect(self._play_or_stop)

        # Right beside Play: starring is a thing you do about the game you are looking at.
        self.favorite_button = self._round_button("star", "Add to favorites")
        self.favorite_button.setCheckable(True)
        self.favorite_button.clicked.connect(lambda: self._emit(self.toggleFavoriteRequested))
        self.folder_button = self._round_button("folder", "Open the game's folder")
        self.folder_button.clicked.connect(lambda: self._emit(self.openFolderRequested))
        # Everything else -- art, rename, the exe, saves, hide, uninstall -- is the menu the
        # grid's right-click opens. One list of actions, reachable from the pad too.
        self.more_button = self._round_button("more", "More: artwork, rename, saves, hide...")
        self.more_button.clicked.connect(self._open_menu)

        # Yours rather than the store's: where you are with the game. One switch of three;
        # pressing the lit one again clears it. No button group: an exclusive group could
        # never be switched off again, and the window's answer re-syncs all three anyway.
        self.status_buttons: dict[str, QPushButton] = {}
        self.segment_lines: list[QFrame] = []
        self.segment_bar = QFrame()
        self.segment_bar.setObjectName("SegmentBar")
        segments = QHBoxLayout(self.segment_bar)
        segments.setSpacing(0)
        last = len(rules.STATUSES) - 1
        for index, status in enumerate(rules.STATUSES):
            if index:
                line = QFrame()
                line.setObjectName("SegmentLine")
                line.setFixedWidth(1)
                self.segment_lines.append(line)
                segments.addWidget(line)
            button = QPushButton(ui_rules.STATUS_LABELS[status])
            button.setObjectName("Segment")
            button.setProperty("status", status)
            # The two ends follow the switch's rounded corners when lit.
            button.setProperty("edge", "first" if index == 0 else "last" if index == last else "")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
            button.clicked.connect(lambda _checked=False, s=status: self._toggle_status(s))
            self.status_buttons[status] = button
            segments.addWidget(button)

        # Since when the mark stands (Phase 103), under the switch, in the room above the first card: placed by
        # hand (`_place_since`), so the Play row keeps its measured place.
        self.mark_since = QLabel(self.banner)
        self.mark_since.setObjectName("MarkSince")
        self.mark_since.setTextFormat(Qt.TextFormat.PlainText)
        self.mark_since.setVisible(False)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        self._actions_row = actions
        actions.addWidget(self.play_button)
        # The row's own gap between everything, and a little more before the switch.
        self._gap_before_switch = QSpacerItem(0, 0)
        for button in (self.favorite_button, self.folder_button, self.more_button):
            actions.addWidget(button)
        actions.addSpacerItem(self._gap_before_switch)
        actions.addWidget(self.segment_bar)
        actions.addStretch(1)

        info = QVBoxLayout()
        info.setContentsMargins(0, 0, 0, 0)
        self._info = info
        info.addStretch(1)
        info.addWidget(self.title_label)
        info.addWidget(self.pill_row)
        info.addLayout(actions)

        block = QHBoxLayout()
        block.setContentsMargins(0, 0, 0, 0)
        self._block = block
        block.addWidget(self.cover_art, 0, Qt.AlignmentFlag.AlignBottom)
        block.addLayout(info, 1)

        hero = QVBoxLayout(self.banner)
        hero.addStretch(1)
        hero.addLayout(block)

    @staticmethod
    def _card(title: str) -> Card:
        """A card at the design's size (Phase 57): 18 px top and bottom, 20 either side."""
        return Card(title, padding=(ui_rules.GAME_CARD_PADDING_X, ui_rules.GAME_CARD_PADDING_Y),
                    title_gap=ui_rules.GAME_CARD_TITLE_GAP)

    def _build_cards(self) -> None:
        """Everything under the picture. A card exists on the page only while it has content."""
        # A question, and only while there is one to ask: this looks like a new version of
        # a game you had installed before -- carry its past over? (Phase 36.) First, above
        # the note, because until it is answered this page shows a game with no history.
        self.earlier_card = self._card("Played before?")
        self.earlier_card.setProperty("tone", "offer")
        self.earlier_text = QLabel()
        self.earlier_text.setObjectName("OfferText")
        self.earlier_text.setWordWrap(True)
        self.earlier_text.setTextFormat(Qt.TextFormat.PlainText)  # a game's name is never markup
        self.carry_button = QPushButton("Carry it over")
        self.carry_button.setProperty("variant", "accent")
        self.not_same_button = QPushButton("Not the same game")
        offer_row = QHBoxLayout()
        offer_row.setContentsMargins(0, 0, 0, 0)
        for button in (self.carry_button, self.not_same_button):
            button.setObjectName("HeroGhost")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
            offer_row.addWidget(button)
        offer_row.addStretch(1)
        self.carry_button.clicked.connect(lambda: self._answer(self.carryOverRequested))
        self.not_same_button.clicked.connect(lambda: self._answer(self.notSameRequested))
        self.earlier_card.body.addWidget(self.earlier_text)
        self.earlier_card.body.addLayout(offer_row)
        self.earlier_card.setVisible(False)

        # Your note, next: it is usually where you left off.
        self.note_card = self._card("Your note")
        self.notes_button = QPushButton("Add a note...")
        self.notes_button.setObjectName("TextButton")
        self.notes_button.setToolTip("Where you left off, settings that worked -- anything.")
        self.notes_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.notes_button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.notes_button.clicked.connect(lambda: self._emit(self.notesRequested))
        self.note_card.add_to_header(self.notes_button)
        self.note = QLabel()
        self.note.setObjectName("Note")
        self.note.setWordWrap(True)
        self.note.setTextFormat(Qt.TextFormat.PlainText)  # a note is never markup
        self.note.setIndent(0)  # with a border Qt indents the words; the design's 12 px is all
        self.note.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.note.setVisible(False)
        self.note_prompt = QLabel(NOTE_PROMPT)
        self.note_prompt.setObjectName("NotePrompt")
        self.note_prompt.setWordWrap(True)
        self.note_card.body.addWidget(self.note)
        self.note_card.body.addWidget(self.note_prompt)

        self.about_card = self._card("About")
        self.description = QLabel()
        self.description.setObjectName("Description")
        self.description.setWordWrap(True)
        # Rich text only for its line spacing (see spaced); the words are escaped first.
        self.description.setTextFormat(Qt.TextFormat.RichText)
        self.description.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.about_card.body.addWidget(self.description)

        # Paths get a card of their own, in the wide column: a path has no spaces to wrap
        # at, so a narrow column clips its tail rather than wrapping it (Phase 10).
        self.files_card = self._card("Files")
        self.files_list = QVBoxLayout()
        self.files_list.setContentsMargins(0, 0, 0, 0)
        self.files_card.body.addLayout(self.files_list)

        self.news_card = self._card("Recent updates")
        self.news_layout = QVBoxLayout()
        self.news_layout.setContentsMargins(0, 0, 0, 0)
        self.news_layout.setSpacing(ui_rules.NEWS_ITEM_SPACING)
        self.news_card.body.addLayout(self.news_layout)

        # Every game that has sessions: launched ones, and since Phase 93 observed ones -- a Steam game
        # started from Steam has them too; an observed one's length is marked as approximate.
        self.sessions_card = self._card("Recent sessions")
        self.week_label = QLabel()
        self.week_label.setObjectName("Meta")
        self.sessions_card.add_to_header(self.week_label)
        self.session_bars = SessionBars()
        self.session_bars.rateClicked.connect(self._session_rated)  # Phase 102: a late rating
        self.sessions_card.body.addWidget(self.session_bars)

        self.details_card = self._card("Details")
        self.facts_grid = QGridLayout()
        self.facts_grid.setContentsMargins(0, 0, 0, 0)
        self.details_card.body.addLayout(self.facts_grid)
        # Last in the last card, well away from Play. Its label is the tier's own wording
        # rather than a flat "Uninstall" (Phase 25): what the launcher can do about a game
        # depends on who installed it, and the button says which.
        self.uninstall_button = QPushButton("Uninstall...")
        self.uninstall_button.setObjectName("Danger")
        self.uninstall_button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.uninstall_button.clicked.connect(lambda: self._emit(self.uninstallRequested))
        uninstall_row = QHBoxLayout()
        uninstall_row.addWidget(self.uninstall_button)
        uninstall_row.addStretch(1)
        self.details_card.body.addSpacing(ui_rules.DETAIL_FACT_ROW_GAP)
        self.details_card.body.addLayout(uninstall_row)

        self.shots_card = self._card("Screenshots")
        self.strip = ui_screenshots.ScreenshotStrip(self.metrics, self)
        self.strip.opened.connect(self.open_viewer)
        self.shots_card.body.addWidget(self.strip)

        self.cards = (self.earlier_card, self.note_card, self.about_card, self.files_card,
                      self.news_card, self.sessions_card, self.details_card, self.shots_card)
        for card in (self.about_card, self.files_card, self.news_card, self.sessions_card,
                     self.shots_card):
            card.setVisible(False)

        self.body = clear_widget("DetailBody")
        body = QVBoxLayout(self.body)
        columns = QHBoxLayout()
        columns.setContentsMargins(0, 0, 0, 0)
        self._columns = columns
        self.left_column = QVBoxLayout()
        self.right_column = QVBoxLayout()
        for card in (self.earlier_card, self.note_card, self.about_card, self.files_card,
                     self.news_card):
            self.left_column.addWidget(card)
        for card in (self.sessions_card, self.details_card):
            self.right_column.addWidget(card)
        self.left_column.addStretch(1)
        self.right_column.addStretch(1)
        columns.addLayout(self.left_column, ui_rules.DETAIL_LEFT_WEIGHT)
        columns.addLayout(self.right_column, ui_rules.DETAIL_RIGHT_WEIGHT)
        body.addLayout(columns)
        body.addWidget(self.shots_card)

    # -- geometry ------------------------------------------------------------------------------

    def _place(self) -> None:
        """Line the words over the picture up with the cards, and size the picture.

        The cards are centred in a column that never gets wider than DETAIL_BODY_MAX_WIDTH,
        and the cover and title start on the same left edge, so on a wide screen the page
        is one column rather than words at the far left over cards in the middle.
        """
        scale = self.metrics.scale
        viewport = self.scroll.viewport()
        width = max(1, viewport.width())
        margin = round(ui_rules.DETAIL_PAGE_MARGIN * scale)
        body = min(width - margin * 2, round(ui_rules.DETAIL_BODY_MAX_WIDTH * scale))
        side = max(margin, (width - body) // 2)
        top = round((ui_rules.DETAIL_NAV_TOP + ui_rules.DETAIL_NAV_HEIGHT) * scale
                    + ui_rules.DETAIL_ROW_GAP * 2 * scale)
        foot = round(ui_rules.DETAIL_HERO_BOTTOM * scale)
        # The cover's widget carries room for its shadow; its visible edge is what lines up.
        art = self.cover_art
        self.banner.layout().setContentsMargins(side - art.spread, top, side,
                                                max(0, foot - art.room_bottom))
        self._info.setContentsMargins(0, 0, 0, art.room_bottom
                                      + round(ui_rules.DETAIL_INFO_FOOT * scale))
        self.banner.dots_right = side
        self._body_row.setContentsMargins(margin, 0, margin, 0)
        self.body.setMaximumWidth(round(ui_rules.DETAIL_BODY_MAX_WIDTH * scale))

        # As tall as the design, its share of a taller window, or as the cover and the words
        # need -- whichever is most.
        wanted = max(round(ui_rules.DETAIL_HERO_HEIGHT * scale),
                     round(viewport.height() * ui_rules.DETAIL_HERO_FRACTION))
        layout = self.banner.layout()
        needed = (layout.totalHeightForWidth(width) if layout.hasHeightForWidth()
                  else layout.totalMinimumSize().height())
        self.banner.setFixedHeight(max(wanted, needed))

        # Nothing may be squeezed: below the width the Play row needs, the page scrolls
        # sideways instead of clipping a label (the Phase 27 rule, kept).
        self._block.invalidate()
        self.content.setMinimumWidth(self._block.minimumSize().width() + margin * 2)
        self._place_nav()
        self._place_since()
        self.focus_ring.place()

    def _fill_since(self, view) -> None:
        """ "Finished since 3 Oct" under the switch when the mark is dated (Phase 103); nothing when it is not."""
        moment = None
        if view.status_since:
            try:
                moment = datetime.fromisoformat(view.status_since)
            except ValueError:
                log.warning("%s: a mark's date it cannot read, %r -- no since line", view.key, view.status_since)
        self.mark_since.setText(f"{ui_rules.STATUS_LABELS[view.status]} since {humanize.day(moment)}" if moment else "")
        self.mark_since.setVisible(moment is not None)
        self._place_since()
        QTimer.singleShot(0, self._place_since)  # again once the page's layout has settled

    def _place_since(self) -> None:
        label = self.mark_since
        if label.isHidden():
            return
        label.adjustSize()
        bar = self.segment_bar
        at = bar.mapTo(self.banner, QPoint(0, bar.height()))
        label.move(at.x() + (bar.width() - label.width()) // 2,
                   at.y() + round(ui_rules.DETAIL_SINCE_GAP * self.metrics.scale))
        label.raise_()

    def _place_nav(self) -> None:
        top = round(ui_rules.DETAIL_NAV_TOP * self.metrics.scale)
        side = round(ui_rules.DETAIL_NAV_SIDE * self.metrics.scale)
        bar = self.scroll.verticalScrollBar()
        room = self.width() - (bar.width() if bar.isVisible() else 0)
        self.top_fade.setGeometry(0, 0, max(0, room),
                                  round(ui_rules.DETAIL_TOP_FADE * self.metrics.scale))
        self.top_fade.raise_()
        self._fade_follows_scroll(bar.value())
        for button in (self.back_button, self.prev_button, self.next_button):
            button.adjustSize()
            button.raise_()
        self.back_button.move(side, top)
        gap = round(ui_rules.DETAIL_NAV_GAP * self.metrics.scale)
        right = room - side
        self.next_button.move(right - self.next_button.width(), top)
        self.prev_button.move(self.next_button.x() - gap - self.prev_button.width(), top)

    def _fade_follows_scroll(self, value: int) -> None:
        """None at the top, where the picture is, and all of it a fade's height further down."""
        self.top_fade.set_strength(min(1.0, value / max(1, self.top_fade.height())))

    def eventFilter(self, watched, event) -> bool:
        if watched is self.scroll.viewport() and event.type() == QEvent.Type.Resize:
            self._place()
        return super().eventFilter(watched, event)

    def pill_at(self, pos: QPoint):
        """The pill shown at `pos` in the pill row, or None."""
        return self.pill_row.pill_at(pos)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._place()

    # -- content ---------------------------------------------------------------------------

    def set_view(self, view) -> None:
        if self.view is None or view.key != self.view.key:
            # Another game's page starts at its top, not wherever the last one was left.
            self.scroll.verticalScrollBar().setValue(0)
        self.view = view
        self.banner.set_view(view)
        self.cover_art.set_view(view)
        self.title_label.setText(view.display_name)

        self.favorite_button.setChecked(view.favorite)
        self.favorite_button.setToolTip(
            "Remove from favorites" if view.favorite else "Add to favorites"
        )
        self.favorite_button.setAccessibleName(self.favorite_button.toolTip())
        self._apply_favorite_icon()
        for status, button in self.status_buttons.items():
            button.setChecked(view.status == status)
        self._fill_since(view)

        self._fill_earlier(view)
        self.note.setText(view.notes)
        self.note.setVisible(bool(view.notes))
        self.note_prompt.setVisible(not view.notes)
        self.notes_button.setText("Edit note..." if view.notes else "Add a note...")

        record = gamedetails.record_for(view)
        text = gamedetails.description(record)
        self.description.setText(spaced(text, self.metrics.scale))
        self.about_card.setVisible(bool(text))

        money = self.money_for(view) if self.money_for is not None else None
        steam = self.steam_time_for(view) if self.steam_time_for is not None else None
        rows = gamedetails.metadata(record, view, money, steam)
        usual, fit = self.recommend_for(view) if self.recommend_for is not None else ("", "")
        if fit:
            # For a game waiting to be played: For you's own fit, beside the genres it is worked out from.
            at = next((i + 1 for i, (label, _value) in enumerate(rows) if label == "Genres"), len(rows))
            rows = rows[:at] + [(FIT_FACT, fit)] + rows[at:]
        self._fill_pills(view, record, rows, usual)
        self._space_info()
        self._fill_facts(rows)
        self._start_screenshots(view, record)
        self._fill_sessions(view)
        self._start_news(view)
        self._place()

    def _fill_earlier(self, view) -> None:
        """The "Played before?" card: shown while an earlier install looks like this game."""
        found = list(self.earlier_for(view)) if self.earlier_for is not None else []
        self.offer = found[0] if found else None
        self.earlier_card.setVisible(self.offer is not None)
        if self.offer is None:
            return
        self.earlier_text.setText(offer_text(self.offer, len(found) - 1))

    def _answer(self, signal) -> None:
        if self.view is not None and self.offer is not None:
            signal.emit(self.view.key, self.offer.key)

    def _fill_pills(self, view, record, rows, usual: str = "") -> None:
        """The few facts worth seeing first, each as a pill under the title."""
        values = dict(rows)
        scale = self.metrics.scale
        # fact -> (words, value, tone): every pill's words are neutral but one -- saves that
        # have been copied, in the accent, as the design has it.
        shown: dict[str, tuple[str, str, str]] = {}
        tips: dict[str, str] = {}
        if self.observed:
            shown["Running"] = (OBSERVED_WORDS, OBSERVED_WORDS, "saved")
        hours = self.hours_for(view) if self.hours_for is not None else None
        if hours is not None:
            # The game's hours as the reports count them (Phase 102 extension): the launcher's own and Steam's
            # on the accounts marked yours, an app once. Unknown is no pill, never 0; an exe game says so.
            seconds = round(hours["minutes"] * 60)
            if seconds > 0:
                played = humanize.playtime(seconds)
                shown["Played"] = (f"{played} played", played, "")
                tips["Played"] = played_tip(hours)
            elif view.entry.launch_kind == "exe":
                shown["Played"] = ("Not played yet", "", "")
        elif view.entry.launch_kind == "exe":
            # A store that cannot count the hours (the JSON library): the launcher's own time, as before.
            played = values.get("Played", "")
            words = f"{played} played" if view.playtime_seconds > 0 else "Not played yet"
            shown["Played"] = (words, played, "")
        elif view.playtime_seconds > 0 and view.entry.source not in rules.HOURS_KEPT_BY_STORE:
            # An Epic or Xbox game seen running (Phase 93): the time watched is its time here.
            played = humanize.playtime(view.playtime_seconds)
            shown["Played"] = (f"{played} played", played, "")
        if usual:
            shown["Usually"] = (usual, usual, "")
        if view.last_played is not None:
            shown["Last played"] = (f"Last played {values.get('Last played', '')}",
                                    values.get("Last played", ""), "")
        if values.get("Installed"):
            shown["Installed"] = (values["Installed"], values["Installed"], "")
        copied = values.get("Saves copied", "")
        if copied:
            when = copied.split("  (")[0]
            if copied == "not yet":
                shown["Saves copied"] = ("Saves not copied yet", copied, "")
            else:
                shown["Saves copied"] = (f"Saves copied {when}", copied, "saved")
        if gamedetails.has_full_controller_support(record):
            shown["Controller"] = ("Full controller support", "yes", "")

        for fact, glyph in PILLS:
            pill = self.pills[fact]
            if fact in shown:
                words, value, tone = shown[fact]
                pill.show_fact(words, value, glyph, tone, scale)
            if fact != "Running":  # the Running pill's words are its own (set_observed)
                pill.setToolTip(tips.get(fact, ""))
            pill.setVisible(fact in shown)
        self.pill_row.setVisible(bool(shown))
        self._pill_flow.invalidate()

    def _space_info(self) -> None:
        """The gaps between the title, the pills and the Play row, as the design measures them.

        The design sets the title on a line exactly as tall as its letters; a QLabel's box is
        the font's whole height, a few pixels more above and below the letters, so the gap
        under the title is that much smaller here. Measured once the stylesheet's font is on.
        """
        scale = self.metrics.scale
        self.title_label.ensurePolished()
        font = self.title_label.font()
        size = font.pixelSize() if font.pixelSize() > 0 else round(ui_rules.DETAIL_TITLE_PX * scale)
        metrics = QFontMetrics(font)
        overhang = max(0, round((metrics.ascent() + metrics.descent() - size) / 2))
        under_title = max(0, round(ui_rules.DETAIL_ROW_GAP * scale) - overhang)
        self._pill_flow.setContentsMargins(0, under_title, 0, 0)
        above_play = round(ui_rules.DETAIL_ACTIONS_TOP * scale)
        if self.pill_row.isHidden():
            above_play += under_title
        else:
            above_play += round(ui_rules.DETAIL_ROW_GAP * scale)
        self._actions_row.setContentsMargins(0, above_play, 0, 0)

    def _fill_facts(self, rows) -> None:
        """The rest of the facts: paths into the Files card, everything else into Details.

        The facts already shown as pills are not repeated here.
        """
        for layout in (self.facts_grid, self.files_list):
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.setParent(None)  # not deleteLater: the Phase 23 lesson
                    widget.deleteLater()

        self._fact_values = {}
        details = [(label, value) for label, value in rows
                   if label not in gamedetails.SUMMARY_FACTS and label not in gamedetails.PATH_FACTS]
        files = [(label, value) for label, value in rows if label in gamedetails.PATH_FACTS]
        label_width = max(60, round(ui_rules.DETAIL_FACT_LABEL_WIDTH * self.metrics.scale))
        for row, (label, value) in enumerate(details):
            name = QLabel(label)
            name.setObjectName("FactLabel")
            name.setFixedWidth(label_width)
            name.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            content = self._fact_value(value)
            self.facts_grid.addWidget(name, row, 0)
            self.facts_grid.addWidget(content, row, 1)
            self._fact_values[label] = value
        for label, value in files:
            name = QLabel(label)
            name.setObjectName("FactLabel")
            self.files_list.addWidget(name)
            self.files_list.addWidget(self._fact_value(value))
            self._fact_values[label] = value
        self.files_card.setVisible(bool(files))

    def _fact_value(self, value: str) -> QLabel:
        content = QLabel(value)
        content.setObjectName("FactValue")
        content.setWordWrap(True)
        content.setToolTip(value)
        content.setTextFormat(Qt.TextFormat.PlainText)
        content.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        return content

    def facts(self) -> dict[str, str]:
        """Every fact the page is showing, by its label: the pills, the details, the files."""
        shown = {pill.fact: pill.value for pill in self.pills.values() if not pill.isHidden()}
        shown.update(self._fact_values)
        return shown

    # -- recent sessions ---------------------------------------------------------------------

    def _fill_sessions(self, view) -> None:
        """The last few play sessions as bars, with the week's total on the card's title line."""
        entries = sessions.load(view.data)
        recent = sessions.recent(entries, ui_rules.SESSIONS_SHOWN)
        self.sessions_card.setVisible(bool(recent))
        if not recent:
            self.session_bars.set_rows([])
            return
        week = sessions.minutes_this_week(entries)
        self.week_label.setText(
            f"{humanize.playtime(week * 60)} this week" if week else "Nothing this week"
        )
        today = datetime.now().date()
        # Each session's stars (Phase 102): as rated, or five quiet ones to click for a session of the last
        # RATE_LATE_DAYS long enough to be asked about; nothing older is asked for.
        ratings = self.ratings_of(view.key) if self.ratings_of is not None else None
        self._session_starts = [rate.started_text(session.start) for session in recent]
        stars = None if ratings is None else [
            (ratings.get(start), start not in ratings and session.minutes >= rules.RATE_MIN_MINUTES
             and rate.rateable(session.start))
            for start, session in zip(self._session_starts, recent)]
        self.session_bars.set_rows([
            (session_day(session.start, today), session.minutes,
             (APPROXIMATE if session.origin == rules.SESSION_OBSERVED else "") + humanize.playtime(session.minutes * 60))
            for session in recent
        ], stars)

    def refresh_sessions(self, view) -> None:
        """Recent sessions again -- a rating written (Phase 102)."""
        self._fill_sessions(view)

    def _session_rated(self, row: int, stars: int) -> None:
        if self.view is not None and 0 <= row < len(self._session_starts):
            self.rateRequested.emit(self.view.key, self._session_starts[row], stars)

    # -- recent updates -------------------------------------------------------------------

    def _start_news(self, view) -> None:
        """Ask for this game's update posts in the background, if it can have any."""
        self._stop_news()
        self._clear_news()
        appid = view.matched_appid
        if not appid:
            return  # no appid, no news -- the same rule the description follows
        worker = NewsWorker(appid, CACHE_DIR, self.allow_network, self)
        worker.ready.connect(self._show_news)
        worker.start()
        self._news_worker = worker

    def _show_news(self, appid: str, items: list) -> None:
        """Fill the card, or leave it off the page when there is nothing to say."""
        if self.view is None or self.view.matched_appid != appid:
            return  # the user moved on while this was in flight
        self._clear_news()
        for item in items:
            self.news_layout.addWidget(self._news_entry(item))
        self.news_card.setVisible(bool(items))

    def _news_entry(self, item) -> QWidget:
        entry = clear_widget()
        layout = QVBoxLayout(entry)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        title = QLabel(item.title)
        title.setObjectName("NewsTitle")
        title.setWordWrap(True)
        layout.addWidget(title)

        if item.posted is not None:
            when = QLabel(humanize.moment(item.posted))
            when.setObjectName("Meta")
            layout.addWidget(when)

        if item.snippet:
            body = QLabel(spaced(item.snippet, self.metrics.scale))
            body.setObjectName("Description")
            body.setTextFormat(Qt.TextFormat.RichText)
            body.setWordWrap(True)
            layout.addWidget(body)

        if item.url:
            more = QPushButton("Read more")
            more.setObjectName("TextButton")
            more.setToolTip(item.url)
            more.setCursor(Qt.CursorShape.PointingHandCursor)
            more.clicked.connect(lambda _=False, url=item.url: self._open_news(url))
            row = QHBoxLayout()
            row.addWidget(more)
            row.addStretch(1)
            layout.addLayout(row)
        return entry

    def _open_news(self, url: str) -> None:
        """Hand the post to the default browser -- this app does not render web pages."""
        if not QDesktopServices.openUrl(QUrl(url)):
            log.warning("could not open %s in a browser", url)

    def _clear_news(self) -> None:
        while self.news_layout.count():
            item = self.news_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self.news_card.setVisible(False)

    def _stop_news(self) -> None:
        worker = self._news_worker
        if worker is not None and worker.isRunning():
            worker.requestInterruption()
            worker.wait(3000)
        self._news_worker = None

    # -- screenshots -------------------------------------------------------------------------

    def stop_downloads(self) -> None:
        """Stop any screenshot fetch in flight.

        Must be called before the window goes away: Qt aborts the process if a QThread is
        still running when its owner is destroyed, which showed up as the tests exiting
        non-zero *after* printing their results.
        """
        self._stop_news()
        for attribute in ("_thumb_worker", "_full_worker", "_hero_worker"):
            worker = getattr(self, attribute)
            if worker is not None and worker.isRunning():
                worker.requestInterruption()
                worker.wait(3000)
            setattr(self, attribute, None)

    def _stop_workers(self) -> None:
        self.stop_downloads()

    def _start_screenshots(self, view, record) -> None:
        self._stop_workers()
        self._thumb_paths.clear()
        self._full_paths.clear()

        self._shots = gamedetails.screenshots(record, ui_rules.SCREENSHOT_MAX_PER_GAME)
        self.strip.reset(len(self._shots))
        self.shots_card.setVisible(bool(self._shots))
        if not self._shots:
            # Nothing from Steam to cycle. SteamGridDB heroes can fill that gap, if the
            # user has a key and has not already chosen this banner themselves.
            self._start_hero_frames(view)
            return

        appid = str(view.entry.extra.get("appid") or "")
        jobs, existing = plan(CACHE_DIR, appid, self._shots, full=False)
        for index, path in existing.items():
            self._thumb_paths[index] = path
            self.strip.set_image(index, path)

        if not jobs:
            self._start_cycle_frames()
            return
        if not self.allow_network:
            log.info("network off; %d screenshot(s) not fetched", len(jobs))
            self._start_cycle_frames()
            return

        worker = ScreenshotWorker(jobs, self)
        worker.ready.connect(self._thumb_ready)
        worker.done.connect(self._start_cycle_frames)
        self._thumb_worker = worker
        worker.start()

    def _thumb_ready(self, index: int, path: str) -> None:
        self._thumb_paths[index] = path
        self.strip.set_image(index, path)

    def _start_cycle_frames(self) -> None:
        """Fetch the full-size images the picture cycles through.

        Thumbnails first, then these, so the strip fills in quickly and the cycle grows
        afterwards. Capped, because each frame is a full-size download.
        """
        if self.view is None or not self._shots:
            return
        wanted = self._shots[: ui_rules.BANNER_CYCLE_MAX_FRAMES]
        appid = str(self.view.entry.extra.get("appid") or "")
        jobs, existing = plan(CACHE_DIR, appid, wanted, full=True)

        for index, path in sorted(existing.items()):
            self._full_paths[index] = path
            self.banner.add_frame(path)

        if not jobs or not self.allow_network or not self.banner.cycling_allowed:
            return
        worker = ScreenshotWorker(jobs, self)
        worker.ready.connect(self._cycle_frame_ready)
        self._full_worker = worker
        worker.start()

    def _start_hero_frames(self, view) -> None:
        """Cycle SteamGridDB heroes for a game Steam has no screenshots for."""
        if not self.allow_network or not self.steamgriddb_key.strip():
            return
        if not self.banner.cycling_allowed:
            log.debug("%s has a hand-picked banner; not fetching heroes", view.display_name)
            return
        worker = HeroWorker(
            view.display_name,
            self.steamgriddb_key,
            CACHE_DIR,
            rules.SGDB_HERO_CYCLE_MAX,
            self,
        )
        worker.ready.connect(self.banner.add_frame)
        self._hero_worker = worker
        worker.start()

    def _cycle_frame_ready(self, index: int, path: str) -> None:
        self._full_paths[index] = path
        self.banner.add_frame(path)
        if self._viewer is not None:
            self._viewer.set_image(index, path)

    def open_viewer(self, index: int) -> None:
        if not self._shots:
            return
        # Start from the thumbnails so something is on screen immediately, then swap each
        # full-size image in as it arrives.
        initial = dict(self._thumb_paths)
        initial.update(self._full_paths)
        viewer = ui_screenshots.ScreenshotViewer(initial, len(self._shots), index, self)
        self._viewer = viewer

        appid = str(self.view.entry.extra.get("appid") or "") if self.view else ""
        jobs, existing = plan(CACHE_DIR, appid, self._shots, full=True)
        for done_index, path in existing.items():
            self._full_paths[done_index] = path
            viewer.set_image(done_index, path)

        if jobs and self.allow_network:
            worker = ScreenshotWorker(jobs, self)
            worker.ready.connect(self._full_ready)
            self._full_worker = worker
            worker.start()

        viewer.exec()
        self._viewer = None

    def _full_ready(self, index: int, path: str) -> None:
        self._full_paths[index] = path
        if self._viewer is not None:
            self._viewer.set_image(index, path)

    def close_viewer(self) -> bool:
        """Shut the viewer if it is open. Returns whether there was one."""
        if self._viewer is not None:
            self._viewer.accept()
            return True
        return False

    @property
    def viewer_open(self) -> bool:
        return self._viewer is not None

    def viewer_step(self, direction: int) -> None:
        if self._viewer is not None:
            self._viewer.step(direction)

    # -- actions -----------------------------------------------------------------------------

    def _emit(self, signal) -> None:
        if self.view is not None:
            signal.emit(self.view.key)

    def _toggle_status(self, status: str) -> None:
        if self.view is None:
            return
        # Qt has already flipped the button by now; the window's answer re-syncs all three
        # through set_view, so the page never shows a state that was not saved.
        self.statusRequested.emit(self.view.key, "" if self.view.status == status else status)

    def cover_rect_in(self, widget: QWidget) -> QRect:
        """Where the cover itself is drawn -- not its widget, which has room for the shadow --
        in `widget`'s coordinates. One end of the cover flight (Phase 34)."""
        body = self.cover_art.cover_rect()
        return QRect(self.cover_art.mapTo(widget, body.topLeft()), body.size())

    def cover_on_screen(self) -> bool:
        """Whether the cover is in view, or scrolled away -- no flight from off the screen."""
        viewport = self.scroll.viewport()
        return viewport.rect().contains(self.cover_rect_in(viewport).center())

    def menu_position(self) -> QPoint:
        """Where the "..." menu opens: just under its button, whoever asked for it."""
        return self.more_button.mapToGlobal(QPoint(0, self.more_button.height()))

    def _open_menu(self) -> None:
        if self.view is not None:
            self.menuRequested.emit(self.view.key, self.menu_position())

    def scroll_by(self, direction: str) -> None:
        """Up and down on the pad move the page; the shoulders move it a screen at a time."""
        bar = self.scroll.verticalScrollBar()
        step = round(ui_rules.DETAIL_PAD_SCROLL * self.metrics.scale)
        change = {"up": -step, "down": step, "page_up": -bar.pageStep(),
                  "page_down": bar.pageStep()}.get(direction, 0)
        bar.setValue(bar.value() + change)

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key in PREV_KEYS:
            self.navigate.emit(-1)
        elif key in NEXT_KEYS:
            self.navigate.emit(1)
        elif key in BACK_KEYS:
            self.backRequested.emit()
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._emit(self.playRequested)
        else:
            super().keyPressEvent(event)
            return
        event.accept()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.banner.set_active(True)
        self._place()

    def hideEvent(self, event) -> None:
        # The library page is showing: no reason to keep cycling a picture nobody can see.
        self.banner.set_active(False)
        super().hideEvent(event)

    def set_uninstall(self, label: str, enabled: bool, tooltip: str = "") -> None:
        """Label the button with what this game's source actually allows.

        Set by the window, which is the only thing holding the config and the tracker the
        tier depends on. Kept enabled even when the answer is a refusal, so the reason can
        be read rather than guessed at from a dead control.
        """
        self.uninstall_button.setText(label)
        self.uninstall_button.setToolTip(tooltip)
        self.uninstall_button.setProperty("blocked", not enabled)
        self.uninstall_button.style().unpolish(self.uninstall_button)
        self.uninstall_button.style().polish(self.uninstall_button)

    def set_running(self, running: bool) -> None:
        """Play becomes Stop while this game is up, and turns back afterwards.

        One button rather than two: a second control that is disabled most of the time
        would take space on every page for the sake of the few minutes a game is running.
        """
        if running == self.running:
            return
        self.running = running
        self.play_button.setText(STOP_TEXT if running else PLAY_TEXT)
        self.play_button.setObjectName("HeroStop" if running else "HeroPlay")
        self.play_button.setToolTip(
            "Close this game (unsaved progress will be lost)" if running else ""
        )
        self._apply_play_icon()
        # A stylesheet is matched when the object name is set, so the widget has to be
        # told to restyle itself or it keeps the colour it was built with.
        self.play_button.style().unpolish(self.play_button)
        self.play_button.style().polish(self.play_button)

    def set_starting(self, starting: bool) -> None:
        """Play says Starting... and rests until the game is up (Phase 99). Running and seen running win."""
        if starting == self.starting:
            return
        self.starting = starting
        if not self.running and not self.observed:
            self.play_button.setText(ui_rules.STARTING_TEXT if starting else PLAY_TEXT)
        self.play_button.setEnabled(not starting and not self.observed)

    def set_observed(self, observed: bool) -> None:
        """The game is seen running, started outside the launcher (Phase 93): the page says so, and Play
        rests -- a second copy of a running game is never started from here, and nothing the launcher
        did not start is ever stopped by it, so there is no Stop either."""
        if observed == self.observed:
            return
        self.observed = observed
        if not self.running:
            self.play_button.setText(OBSERVED_PLAY_TEXT if observed else PLAY_TEXT)
            self.play_button.setToolTip(OBSERVED_TIP if observed else "")
        self.play_button.setEnabled(not observed)
        pill = self.pills["Running"]
        if observed:
            pill.show_fact(OBSERVED_WORDS, OBSERVED_WORDS, "play_solid", "saved", self.metrics.scale)
        pill.setVisible(observed)
        self.pill_row.setVisible(any(not p.isHidden() for p in self.pills.values()))
        self._pill_flow.invalidate()

    def _play_or_stop(self) -> None:
        if self.observed and not self.running:
            return
        self._emit(self.stopRequested if self.running else self.playRequested)

    def focus_play(self) -> None:
        """Put the keyboard and the pad on Play, so a suggestion is one press from running."""
        self.play_button.setFocus(Qt.FocusReason.OtherFocusReason)

    def set_reduce_animations(self, reduce: bool) -> None:
        self.banner.reduce_animations = reduce
        if reduce:
            self.banner._dwell.stop()
            self.banner._animation.stop()
        else:
            self.banner._maybe_start()

    # -- scale ---------------------------------------------------------------------------------

    def _apply_play_icon(self) -> None:
        px = max(12, round(ui_rules.DETAIL_PLAY_PX * self.metrics.scale))
        if self.running:
            # In the colour of the outline since Phase 56: the accent, or Stop's red.
            self.play_button.setIcon(ui_icons.icon("stop_solid", ui_rules.COLOR_STOP, px))
        else:
            self.play_button.setIcon(ui_icons.icon("play_solid", ui_rules.COLOR_ACCENT, px))
        self.play_button.setIconSize(QSize(px, px))

    def _apply_favorite_icon(self) -> None:
        px = max(10, round(ui_rules.DETAIL_ROUND_ICON_PX * self.metrics.scale))
        starred = self.favorite_button.isChecked()
        self.favorite_button.setIcon(ui_icons.icon(
            "star_full" if starred else "star",
            ui_rules.FAVORITE_BADGE_COLOR if starred else ui_rules.COLOR_TEXT, px,
        ))
        self.favorite_button.setIconSize(QSize(px, px))

    def apply_metrics(self, metrics) -> None:
        self.metrics = metrics
        scale = metrics.scale
        s = lambda value: max(1, round(value * scale))  # noqa: E731 -- a local shorthand
        self.banner.apply_metrics(metrics)
        self.cover_art.apply_metrics(metrics)
        self.strip.metrics = metrics
        self.session_bars.apply_scale(scale)
        for card in self.cards:
            card.apply_scale(scale)

        # The cover's own room on its right is the gap to the words (CoverArt.room_right).
        self._block.setSpacing(max(0, s(ui_rules.DETAIL_COVER_GAP) - self.cover_art.room_right))
        # The gaps between the title, the pills and the Play row are margins: _space_info.
        self._info.setSpacing(0)
        self._pill_flow.set_spacing(s(ui_rules.DETAIL_PILL_GAP))
        self._actions_row.setSpacing(s(ui_rules.DETAIL_ACTION_GAP))
        self._gap_before_switch.changeSize(s(ui_rules.DETAIL_SWITCH_GAP) - s(ui_rules.DETAIL_ACTION_GAP), 0)
        self._actions_row.invalidate()
        self._space_info()
        gap = s(ui_rules.GAME_CARD_GAP)
        self._columns.setSpacing(gap)
        self.left_column.setSpacing(gap)
        self.right_column.setSpacing(gap)
        # The art's foot already holds the room between the cover and the first card.
        self.body.layout().setContentsMargins(0, 0, 0, gap * 2)
        self.body.layout().setSpacing(gap)
        self.sessions_card.body.setContentsMargins(0, s(ui_rules.SESSIONS_TOP), 0, 0)
        self.facts_grid.setHorizontalSpacing(s(ui_rules.DETAIL_FACT_GAP))
        self.facts_grid.setVerticalSpacing(s(ui_rules.DETAIL_FACT_ROW_GAP))

        self.play_button.setFixedSize(s(ui_rules.DETAIL_PLAY_WIDTH), s(ui_rules.DETAIL_ACTION_HEIGHT))
        self._apply_play_icon()
        corner = s(ui_rules.CONTROL_RADIUS)
        for button in (self.play_button, self.back_button, self.prev_button, self.next_button,
                       self.notes_button, self.uninstall_button, self.carry_button,
                       self.not_same_button):
            button.setProperty("ringRadius", corner)  # for the ring outside it
        # The Continue card's buttons, at its height: their corner radius is half of it,
        # and a stylesheet stops rounding anything shorter (the Phase 35 lesson).
        for button in (self.carry_button, self.not_same_button):
            button.setFixedHeight(s(ui_rules.CONTINUE_BUTTON_HEIGHT))
        round_size = s(ui_rules.DETAIL_ROUND_BUTTON)
        for button in (self.favorite_button, self.folder_button, self.more_button):
            button.setFixedSize(round_size, round_size)
            button.setProperty("ringRadius", round_size / 2)
            if button is not self.favorite_button:
                icon_px = s(ui_rules.DETAIL_MORE_ICON_PX if button is self.more_button
                            else ui_rules.DETAIL_ROUND_ICON_PX)
                button.setIcon(ui_icons.icon(button.property("glyph"), ui_rules.COLOR_TEXT, icon_px))
                button.setIconSize(QSize(icon_px, icon_px))
        self._apply_favorite_icon()

        # One hairline round the switch and one between its choices; the choices fill it.
        self.segment_bar.layout().setContentsMargins(1, 1, 1, 1)
        self.segment_bar.setFixedHeight(s(ui_rules.DETAIL_SEGMENT_HEIGHT))
        inner = s(ui_rules.DETAIL_SEGMENT_HEIGHT) - 2
        for button in self.status_buttons.values():
            button.setFixedHeight(inner)
        for line in self.segment_lines:
            line.setFixedHeight(inner)

        for button in (self.back_button, self.prev_button, self.next_button):
            nav_px = s(ui_rules.DETAIL_BACK_ICON_PX if button is self.back_button
                       else ui_rules.DETAIL_NAV_ICON_PX)
            button.setIcon(ui_icons.icon(button.property("glyph"), ui_rules.COLOR_TEXT, nav_px))
            button.setIconSize(QSize(nav_px, nav_px))
            button.setFixedHeight(s(ui_rules.DETAIL_NAV_HEIGHT))

        if self.view is not None:
            self.set_view(self.view)
        self._place()


def spaced(text: str, scale: float) -> str:
    """Plain words as rich text set on the design's line height (13.5 px type on 1.6).

    A QLabel ignores a stylesheet's line-height and only rich text carries one, so the
    words are escaped first: whatever they hold is shown, never read as markup.
    """
    if not text:
        return ""
    line = ui_rules.GAME_CARD_TEXT_PX * ui_rules.GAME_CARD_TEXT_LINE * scale
    body = html.escape(text).replace("\n", "<br>")
    return f'<div style="line-height: {line:.1f}px">{body}</div>'


def session_day(start: datetime, today: date) -> str:
    """A session's day as the design writes it: Today, Yesterday, "Mon 5 Oct", "5 Oct 2025"."""
    day = start.astimezone().date() if start.tzinfo is not None else start.date()
    if day == today:
        return "Today"
    if (today - day).days == 1:
        return "Yesterday"
    if day.year == today.year:
        return f"{day:%a} {day.day} {day:%b}"
    return f"{day.day} {day:%b} {day.year}"


def offer_text(earlier, others: int = 0) -> str:
    """The "Played before?" card's words: which game, what it holds, and the question."""
    reason = ("it has the same name" if earlier.why == lineage.SAME_NAME
              else "it keeps its saves in the same folder")
    text = (f"This looks like a new version of “{earlier.name}”, which was installed "
            f"before -- {reason}. It has {lineage.summary(earlier)}.\n\n"
            "Carry all of that over to this one? Nothing is lost if you are wrong: a copy "
            "of your library data is kept first.")
    if others:
        text += (f"\n\n{others} more earlier install{'s look' if others != 1 else ' looks'} "
                 "similar -- “Same game as an earlier install...” in the ... menu "
                 "lists them all.")
    return text


def stylesheet(scale: float, ring: int = ui_rules.FOCUS_RING_WIDTH) -> str:
    """The game page's own look (Phase 57: the design's). `ring` is the tiles' focus width,
    TV's included: the three marks wear it inside; every other button on the page is ringed
    outside by the page's FocusRing."""
    s = lambda value: max(1, round(value * scale))  # noqa: E731
    pt = lambda px: f"{ui_theme.px_to_pt(px * scale):.2f}pt"  # noqa: E731 -- fractional px
    ring = s(ring)
    display = ui_icons.display_family()
    corner = s(ui_rules.CONTROL_RADIUS)
    inner = max(0, corner - 1)
    glass, nav = ui_rules.COLOR_ON_ART_FAINT, ui_rules.COLOR_NAV
    page = "QWidget#DetailPage"
    return f"""
    QPushButton#HeroPlay[variant="large"], QPushButton#HeroStop[variant="large"] {{
        background: {glass};
        border-radius: {corner}px;
        font-size: {s(ui_rules.DETAIL_PLAY_PX)}px;
        padding: 0;
    }}
    QPushButton#HeroPlay[variant="large"]:hover {{ background: {ui_theme.layered(glass, ui_rules.COLOR_PRIMARY_HOVER)}; }}
    QPushButton#HeroPlay[variant="large"]:pressed {{ background: {ui_theme.layered(glass, ui_rules.COLOR_PRIMARY_PRESSED)}; }}
    QPushButton#HeroStop[variant="large"]:hover {{ background: {ui_theme.layered(glass, ui_rules.COLOR_STOP_TINT)}; }}
    QPushButton#HeroStop[variant="large"]:pressed {{ background: {ui_theme.layered(glass, ui_rules.COLOR_STOP_TINT_PRESSED)}; }}
    QPushButton#Round {{
        background: transparent;
        border: 1px solid {ui_rules.COLOR_DIVIDER};
        border-radius: {s(ui_rules.DETAIL_ROUND_BUTTON) // 2}px;
        padding: 0;
    }}
    QPushButton#Round:hover {{ background: {ui_rules.COLOR_SECONDARY_HOVER}; }}
    QPushButton#Round:pressed {{ background: {ui_rules.COLOR_SECONDARY_PRESSED}; }}
    QFrame#SegmentBar {{
        background: transparent;
        border: 1px solid {ui_rules.COLOR_DIVIDER};
        border-radius: {corner}px;
    }}
    QFrame#SegmentLine {{ background: {ui_rules.COLOR_DIVIDER}; border: none; }}
    QLabel#MarkSince {{ font-size: {s(ui_rules.DETAIL_SINCE_PX)}px; color: {ui_rules.COLOR_TEXT_MUTED}; background: transparent; }}  /* Phase 103 */
    /* One weight whether chosen or not, so a choice is never wider than its room. */
    QPushButton#Segment {{
        background: transparent;
        border: 1px solid transparent;
        border-radius: 0;
        padding: 0 {s(ui_rules.DETAIL_SEGMENT_SIDE_PADDING)}px;
        font-size: {s(ui_rules.DETAIL_SEGMENT_PX)}px;
        font-weight: {ui_rules.BODY_WEIGHT};
        color: {ui_rules.COLOR_TEXT};
    }}
    QPushButton#Segment[edge="first"] {{ border-top-left-radius: {inner}px; border-bottom-left-radius: {inner}px; }}
    QPushButton#Segment[edge="last"] {{ border-top-right-radius: {inner}px; border-bottom-right-radius: {inner}px; }}
    QPushButton#Segment:hover {{ background: {ui_rules.COLOR_SECONDARY_HOVER}; }}
    /* The chosen one: the accent's words, ringed inside in the accent. */
    QPushButton#Segment:checked, QPushButton#Segment:checked:hover {{
        background: transparent;
        border-color: {ui_rules.COLOR_ACCENT};
        color: {ui_rules.COLOR_ACCENT};
    }}
    /* The pad and the keyboard land on these too; the design rings a choice inside it. */
    QPushButton#Segment:focus {{ border: {ring}px solid {ui_rules.TILE_FOCUS_COLOR}; }}
    QPushButton#NavPill {{
        background: {nav};
        border: 1px solid {ui_rules.COLOR_NAV_BORDER};
        border-radius: {corner}px;
        padding: 0 {s(ui_rules.DETAIL_NAV_SIDE_PADDING)}px;
        font-size: {s(ui_rules.DETAIL_NAV_PX)}px;
        font-weight: {ui_rules.HEADING_WEIGHT};
        color: {ui_rules.COLOR_TEXT};
    }}
    QPushButton#NavPill:hover {{ background: {ui_theme.layered(nav, ui_rules.COLOR_SECONDARY_HOVER)}; }}
    QPushButton#NavPill:pressed {{ background: {ui_theme.layered(nav, ui_rules.COLOR_SECONDARY_PRESSED)}; }}
    QPushButton#Pill {{
        background: transparent;  /* the glass and the edge are painted round (ui_hero.Pill, Phase 99) */
        border: 1px solid transparent;
        border-radius: {s(ui_rules.DETAIL_PILL_HEIGHT) // 2}px;
        padding: 0 {s(ui_rules.DETAIL_PILL_SIDE_PADDING)}px;
        font-size: {pt(ui_rules.DETAIL_PILL_PX)};
        color: {ui_rules.COLOR_PILL_TEXT};
    }}
    QPushButton#Pill[tone="saved"] {{ color: {ui_rules.COLOR_PILL_SAVED}; }}
    QLabel#HeroTitle {{
        font-family: "{display}";
        font-size: {s(ui_rules.DETAIL_TITLE_PX)}px;
        font-weight: {ui_rules.HEADING_WEIGHT};
        letter-spacing: {ui_theme.tracking(ui_rules.DETAIL_TITLE_PX) * scale:.2f}px;
        color: {ui_rules.COLOR_TEXT};
    }}
    QFrame#Card {{
        background: {ui_rules.COLOR_CARD};
        border: 1px solid {ui_rules.COLOR_CARD_BORDER};
        border-radius: {s(ui_rules.DETAIL_CARD_RADIUS)}px;
    }}
    /* "Played before?" (Phase 36): a question, so it is edged in the accent colour. */
    QFrame#Card[tone="offer"] {{ border-color: {ui_rules.COLOR_ACCENT}; }}
    QLabel#OfferText {{ color: {ui_rules.COLOR_TEXT}; }}
    QFrame#Card QPushButton#HeroGhost {{ background: transparent; }}
    QFrame#Card QPushButton#HeroGhost:hover {{ background: {ui_rules.COLOR_SECONDARY_HOVER}; }}
    QFrame#Card QPushButton#HeroGhost:pressed {{ background: {ui_rules.COLOR_SECONDARY_PRESSED}; }}
    QFrame#Card QPushButton#HeroGhost[variant="accent"] {{
        border-color: {ui_rules.COLOR_ACCENT};
        color: {ui_rules.COLOR_ACCENT};
    }}
    QFrame#Card QPushButton#HeroGhost[variant="accent"]:hover {{ background: {ui_rules.COLOR_PRIMARY_HOVER}; }}
    QFrame#Card QPushButton#HeroGhost[variant="accent"]:pressed {{ background: {ui_rules.COLOR_PRIMARY_PRESSED}; }}
    QLabel#CardTitle {{
        font-family: "{display}";
        font-size: {s(ui_rules.DETAIL_CARD_TITLE_PX)}px;
        font-weight: {ui_rules.HEADING_WEIGHT};
    }}
    /* The game page's cards at the design's sizes; Stats keeps the older ones until its step. */
    {page} QLabel#CardTitle {{ font-size: {s(ui_rules.GAME_CARD_TITLE_PX)}px; }}
    {page} QLabel#Description, {page} QLabel#FactValue {{
        font-size: {pt(ui_rules.GAME_CARD_TEXT_PX)};
        color: {ui_rules.COLOR_GAME_CARD_TEXT};
    }}
    {page} QLabel#FactLabel, {page} QLabel#NotePrompt {{
        font-size: {pt(ui_rules.GAME_CARD_TEXT_PX)};
        color: {ui_rules.COLOR_TEXT_MUTED};
    }}
    {page} QLabel#Meta {{ font-size: {s(ui_rules.GAME_WEEK_PX)}px; color: {ui_rules.COLOR_TEXT_MUTED}; }}
    QLabel#Note {{
        font-size: {pt(ui_rules.GAME_CARD_TEXT_PX)};
        color: {ui_rules.COLOR_NOTE};
        border-left: {s(ui_rules.NOTE_MARK)}px solid {ui_rules.COLOR_NOTE_MARK};
        padding-left: {s(ui_rules.NOTE_INDENT) - s(ui_rules.NOTE_MARK)}px;
    }}
    QPushButton#TextButton {{
        background: transparent;
        border: 1px solid transparent;
        border-radius: {corner}px;
        color: {ui_rules.COLOR_ACCENT};
        font-size: {pt(ui_rules.GAME_TEXT_BUTTON_PX)};
        font-weight: {ui_rules.HEADING_WEIGHT};
        padding: {s(6)}px {s(3)}px;
    }}
    QPushButton#TextButton:hover {{ background: {ui_rules.COLOR_TEXT_BUTTON_HOVER}; }}
    """
