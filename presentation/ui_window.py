"""The launcher window: two pages and everything that spans both.

The window itself owns very little now -- the page stack and the transition between them,
the merged list of games, playtime tracking and rescanning. The grid lives in ui_library,
the single-game view in ui_detail.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import date, datetime
from pathlib import Path

from PySide6.QtCore import QByteArray, QEvent, QEventLoop, QSize, Qt, QTimer
from PySide6.QtGui import QIcon, QKeyEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QMainWindow,
    QMenu,
    QMessageBox,
    QStackedWidget,
    QSystemTrayIcon,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from data_access import backups
from data_access import catalog_io
from adapters import controller
from adapters.launch_worker import LaunchWorker
from data_access import config_io
from logic import first_run
from logic import focus
from shared import drives
from shared import rules
from logic import sessions
from presentation import ui_actions
from presentation import ui_alert
from presentation import ui_rate
from presentation import ui_backdrop
from presentation import ui_backups
from presentation import ui_continue
from presentation import ui_detail
from presentation import ui_motion
from logic import alerts  # Phase 101: the price alerts
from logic import rate  # Phase 102: how was it?
from logic import autostart
from logic import gamedetails
from logic import lineage
from logic import migration
from logic import observe
from logic import prices
from logic import steam_projection
from logic import wishlist
from logic import steam_time
from shared import naming
from logic import save_backup
from logic import saves as saves_module
from logic import pick
from logic import removal
from presentation import ui_removal
from presentation import ui_rules
from presentation import ui_screenshots
from presentation import ui_jump
from presentation import ui_pageshell
from presentation import ui_foryou
from presentation import ui_rail
from presentation import ui_recap
from presentation import ui_stats
from presentation import ui_storage
from presentation import ui_reports
from presentation import ui_wishlist
from logic import stats as stats_module
from logic import recap as recap_module
from logic import recommend as recommend_module
from logic import reports as reports_module
from logic import storage as storage_module
from logic import taskbar
from presentation import ui_theme
from presentation import ui_topbar
from presentation import ui_tray
from presentation import ui_tv
from adapters.controller import ControllerHub
from adapters.folder_watch import FolderWatcher
from adapters.icons import IconLoader
from logic.launch import PlaytimeTracker
from adapters.process_worker import ProcessWorker
from adapters.save_worker import Job, SaveWorker, run_jobs
from adapters.scan_worker import ScanWorker
from adapters.update_worker import UpdateWorker
from adapters.screenshot_worker import CapsuleWorker
from logic import fill_covers  # Phase 105: missing covers, in one go
from logic import whats_new  # Phase 106: an update explains itself
from shared import paths
from shared import version
from web import steam_web
from web import updates
from presentation.ui_backdrop import Backdrop
from presentation.ui_covers import CoverFactory
from presentation.ui_detail import DetailPage
from presentation.ui_library import LibraryPage
from presentation import ui_earlier
from presentation import ui_cover_actions
from presentation import ui_fill_covers
from presentation import ui_first_run
from presentation import ui_whats_new
from presentation import ui_offer
from presentation import ui_splash
from presentation import ui_analysis
from presentation import ui_folders
from presentation import ui_library
from presentation import ui_settings
from presentation.ui_settings import DATA_REPLACED, SettingsDialog
from presentation.ui_stats import StatsPage
from presentation.ui_storage import StoragePage
from presentation.ui_reports import ReportsPage
from presentation.ui_wishlist import WishlistPage
from presentation.ui_foryou import ForYouPage
from presentation.ui_toast import Toast
from presentation.ui_tv import HintBar

log = logging.getLogger(__name__)

PLACEHOLDER_ICON_PX = 96
LIBRARY_PAGE, DETAIL_PAGE, STATS_PAGE, STORAGE_PAGE, REPORTS_PAGE = 0, 1, 2, 3, 4  # Reports: Phase 84
WISHLIST_PAGE = 5  # Phase 87
FORYOU_PAGE = 6  # Phase 98: under Library in the rail, after it in the top bar
# The places of the top bar and the rail, left to right: what the pad's left and right walk (Phase 84).
TAB_SEQUENCE = (LIBRARY_PAGE, FORYOU_PAGE, STATS_PAGE, STORAGE_PAGE, REPORTS_PAGE, WISHLIST_PAGE)
# The pages that keep the library's glow (Phase 35): the tabs of one place.
GLOWING_PAGES = TAB_SEQUENCE
STATUS_MS = 6000
BRIEF_STATUS_MS = 4000
# Longer than the rest: a game vanishing from the grid is the one message worth reading.
REMOVED_STATUS_MS = 12000
REMOVED_NAMES_SHOWN = 3
# The same weight for a game arriving: it is the answer to "did it pick up what I installed?"
NEW_STATUS_MS = 12000
NEW_NAMES_SHOWN = 3
READY_MESSAGE = "Ready"

# Pad directions on the storage list, synthesised as key presses so Qt keeps doing the
# wrapping, paging and scroll-into-view it already does for the grid -- the Phase 17 rule.
STORAGE_KEYS = {
    controller.UP: Qt.Key.Key_Up,
    controller.DOWN: Qt.Key.Key_Down,
    controller.PAGE_UP: Qt.Key.Key_PageUp,
    controller.PAGE_DOWN: Qt.Key.Key_PageDown,
}


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Game Launcher")
        self.resize(1280, 820)
        # Set on the window too, not only the application: a window created before the app
        # icon is applied would otherwise keep the default.
        if taskbar.ICON_PATH.is_file():
            self.setWindowIcon(QIcon(str(taskbar.ICON_PATH)))
        else:
            log.warning("no icon at %s", taskbar.ICON_PATH)

        # A fresh install has no config.json (Phase 77): nothing has been chosen yet, and the
        # window asks where the games are before its first scan. Looked at before anything here
        # can write one. Never on this machine, where the file exists; never in a sandboxed
        # suite, which copies it.
        self.first_run = not config_io.saved_exists()
        self._first_run_asked = False
        # The one question (Phase 99) is never asked on the start that asked the first-run ones.
        self._first_run_start = self.first_run
        self._offer_scheduled = False
        self._offer_tries = 0

        # Before anything in this session can write. The merge below stamps first_seen, a
        # scan can follow seconds later, and a backup taken after either is a backup of
        # whatever went wrong.
        self.startup_backup = backups.snapshot("startup")

        self.config = config_io.load_config()
        # What's new (Phase 106): the first start after an update shows the version's notes once, a moment after the
        # window appears -- the tray offer waits for them -- and only then writes the version seen.
        self._whats_new = whats_new.due(self.config, self.first_run)
        self._whats_new_scheduled = False
        self._whats_new_tries = 0
        # The accent (Phase 99) before any widget is made: whatever paints a colour once, paints this one.
        self.accent = ui_theme.use_accent(self.config.get(ui_rules.ACCENT_KEY))
        if self.first_run:
            # Until the answer: no folders. The defaults are this machine's, not a new user's,
            # and nothing -- the folder watch, the empty library -- may act on them meanwhile.
            log.info("first run: no config.json yet; where the games are is asked before the first scan")
            self.config["roots"] = []
        # Before the window is ever shown, so it opens where it was left rather than
        # appearing at the default size and then jumping.
        self._restore_geometry()
        self.scale = float(self.config.get("ui_scale", ui_rules.UI_SCALE_DEFAULT))
        self.reduce_animations = bool(
            self.config.get("reduce_animations", ui_rules.REDUCE_ANIMATIONS_DEFAULT)
        )
        self.metrics = ui_theme.Metrics(self.scale)

        # The library: the database since the switch (Phase 69), migrated from the JSON the
        # first time this runs with one -- or the JSON, should that migration be refused.
        self.overrides = migration.open_library()
        self.steam_times: dict = {}  # Steam's own hours on my accounts, by game (Phase 76)
        self.hours: dict = {}  # each game's hours as the reports count them, by game (Phase 102 extension)
        self._foryou = None  # For you's last answer, until the next reload (Phase 98)
        self._drop_wrong_save_folders()
        # Chosen covers and banners are stored with full paths; if the project folder was
        # renamed or moved since, point them at where they are now (Phase 37).
        catalog_io.relocate_artwork(self.overrides)
        # The catalog is only as fresh as the last scan. Anything deleted since then is
        # dropped now rather than shown as a tile that cannot start.
        self.entries, self.uninstalled = catalog_io.prune_missing(
            self.overrides.load_catalog(), self.overrides
        )
        self.views: list = []
        self.by_key: dict = {}
        self._status_queue: list[tuple[str, int]] = []
        self._tagged = False
        self._startup_scan_started = False
        self._last_pick = ""
        self.storage_sort = str(
            self.config.get("storage_sort", storage_module.SORT_SIZE)
        )

        self.icons = IconLoader(QSize(PLACEHOLDER_ICON_PX, PLACEHOLDER_ICON_PX))
        self.covers = CoverFactory(self.icons)
        self.tracker = PlaytimeTracker()
        self.worker: ScanWorker | None = None
        self.scan_was_quiet = False
        self.scan_was_background = False
        self._unbanked: dict[str, int] = {}
        # key -> how much of the live session is already in the game's total (Phase 53)
        self._banked: dict[str, int] = {}
        # key -> (when this session started, seconds so far)
        self._live_sessions: dict[str, tuple] = {}
        self._last_banked = time.monotonic()
        # The tiles' first wave (Phase 34) plays once, when the window first appears.
        self._entrance_played = False
        self.tv_mode = False
        # The ordinary window's size and place, kept aside while TV mode has it fullscreen:
        # closing from TV mode must remember the window, not the television.
        self._normal_geometry: QByteArray | None = None
        self._shown = False
        # A scan the folder watch asked for that has not been able to run yet.
        self._scan_wanted = False
        # Looking for saves and backing them up, off the GUI thread (Phase 29).
        self.save_worker: SaveWorker | None = None
        self._save_jobs: list[Job] = []
        self._saves_started = False
        # Is a newer version out (Phase 79)? An installed copy asks GitHub, off this thread.
        self.update_worker: UpdateWorker | None = None
        # The covers of wished games (Phase 87), fetched while the Wishlist page is looked at.
        self.capsule_worker: CapsuleWorker | None = None
        # Missing covers filled in one go (Phase 105): the batch's thread, a scan held back while it runs, the
        # covers written, and the grid redrawn at most once a second as they land.
        self.cover_fill_worker = None
        self._filling = False
        self._held_scan: dict | None = None
        self._covers_filled = 0
        self._fill_refresh = QTimer(self)
        self._fill_refresh.setSingleShot(True)
        self._fill_refresh.setInterval(rules.FILL_COVERS_REFRESH_MS)
        self._fill_refresh.timeout.connect(self._redraw_filled)
        self.update_answer = updates.last(paths.cache_dir())
        self._updates_started = False
        # Running in the background (Phase 92): with "Keep running" on, closing hides the window
        # into the tray icon and Quit lives in its menu.
        self.keep_running = bool(self.config.get(rules.KEEP_RUNNING_KEY, rules.KEEP_RUNNING_DEFAULT))
        self.tray: ui_tray.Tray | None = None
        self._in_tray = False  # hidden into the tray: nothing on screen to show a message on
        self._quitting = False  # Quit was chosen: the close that follows is a real one
        self._shut_down = False
        self._tray_wait: QTimer | None = None  # waiting for Windows' tray at sign-in
        self._tray_wait_began = 0.0
        # The tick (Phase 92): every BACKGROUND_TICK_MINUTES, is a reading due? Started by begin().
        self.tick = QTimer(self)
        self.tick.setInterval(rules.BACKGROUND_TICK_MINUTES * 60 * 1000)
        self.tick.timeout.connect(self._tick)
        self._last_scan_began = time.time()  # what "Steam's files written since the last scan" means
        # A Steam game was seen being played since the last scan: its counter has moved (Phase 92's tick).
        self._steam_played_since_scan = False
        # Games started outside the launcher (Phase 93): the look at the process list, and the
        # sessions it observes -- written here, on the GUI thread, the one writer.
        self.observer = observe.Observer()
        self.process_worker: ProcessWorker | None = None
        self._watched: dict[str, observe.Watched] = {}
        self._observed_last_bank = time.monotonic()

        self._build()
        self._apply_theme()
        self.top_bar.apply_scale(self.scale)
        self.rail.apply_scale(self.scale)
        self._apply_layout()
        self.toast.apply_scale(self.scale)
        self.library.set_sort(str(self.config.get("library_sort", "")))
        self.library.set_genre(self.config.get(ui_rules.LIBRARY_GENRE_KEY))  # Phase 99: an unknown one is all
        self.library.set_filter(str(self.config.get("library_filter", "")))
        self.reload_views()
        self._report_uninstalled()
        self._report_refused_roots()

        # Input is only ever acted on while the launcher is in front -- see controller.py.
        self.pads = ControllerHub(self._launcher_in_front, self)
        # Queued, not direct (Phase 49). The hub emits from inside its 16 ms poll timer, and
        # a press that opens a menu or a dialog runs that menu's own loop until it closes.
        # Called directly, that loop ran inside the timer's callback, and Qt does not fire a
        # timer again while its callback is still running -- so the pad went dead the moment
        # X opened a menu or Start opened Settings, and only the mouse could close them.
        # Queued, the poll returns at once and keeps reading the pad while the menu is open.
        self.pads.action.connect(self._on_pad_action, Qt.ConnectionType.QueuedConnection)
        self.pads.padsChanged.connect(
            lambda text: self.queue_status(f"Controller: {text}", BRIEF_STATUS_MS)
        )
        self.pads.powerChanged.connect(self.hint_bar.set_power)
        # The hint bar draws the buttons of the pad in use: Xbox's or PlayStation's (Phase 50).
        self.pads.familyChanged.connect(self.hint_bar.set_family)
        if self.config.get("enable_controller", rules.CONTROLLER_ENABLED_DEFAULT):
            self.pads.start()

        self.timer = QTimer(self)
        self.timer.setInterval(rules.PLAYTIME_POLL_MS)
        self.timer.timeout.connect(self._poll_playtime)
        self.timer.start()

        # A game installed while the window is open is noticed, and added once it has
        # finished arriving -- see folder_watch.py.
        self.watcher = FolderWatcher(self)
        self.watcher.scanWanted.connect(self._watch_wants_scan)
        self._arm_watcher()

        if not self.entries and not self.first_run:
            log.info("no catalog on disk; scanning at startup")
            self.start_scan(trigger="first_run")
        self._update_empty_state()
        self._apply_keep_running()

    # -- construction --------------------------------------------------------------------

    def _build(self) -> None:
        self.library = LibraryPage(self.covers, self.metrics, self)
        self.library.reduce_animations = self.reduce_animations
        self.library.gameActivated.connect(self.show_detail)
        self.library.contextRequested.connect(self._context_menu)
        self.library.rescanRequested.connect(self.start_scan)
        self.library.surpriseRequested.connect(self.play_something)
        self.library.settingsRequested.connect(self.open_settings)
        self.library.foldersRequested.connect(lambda: self.open_settings(focus="roots"))
        self.library.statsRequested.connect(self.show_stats)
        self.library.storageRequested.connect(self.show_storage)
        self.library.reportsRequested.connect(self.show_reports)
        self.library.wishlistRequested.connect(self.show_wishlist)
        self.library.foryouRequested.connect(self.show_foryou)
        self.library.sortChanged.connect(self.set_library_sort)
        self.library.genreChanged.connect(self.set_library_genre)  # Phase 99
        self.library.filterChanged.connect(self.set_library_filter)
        self.library.libraryRequested.connect(self.show_library)
        # The Continue playing card (Phase 32): its Play and Stop are the game page's own.
        self.library.playRequested.connect(self._play_key)
        self.library.stopRequested.connect(self._stop_key)
        self.library.is_running = self.tracker.is_running
        self.library.is_observed = self.observed_running  # Phase 93
        self.library.is_starting = self.is_starting  # Phase 99
        self.library.backdropChanged.connect(self._backdrop_follows)

        self.detail = DetailPage(self.covers, self.metrics, self)
        self.detail.playRequested.connect(self._play_key)
        self.detail.openFolderRequested.connect(self._open_folder_key)
        # Its "..." button opens the same menu the grid's right-click does (Phase 33).
        self.detail.menuRequested.connect(self._context_menu)
        self.detail.toggleFavoriteRequested.connect(self._toggle_favorite_key)
        self.detail.stopRequested.connect(self._stop_key)
        self.detail.uninstallRequested.connect(self._uninstall_key)
        self.detail.statusRequested.connect(self._set_status_key)
        self.detail.rateRequested.connect(self.rate_late)  # Phase 102
        self.detail.ratings_of = lambda key: (self.overrides.ratings_of(key)
                                              if getattr(self.overrides, "keeps_ratings", False) else None)
        self.detail.notesRequested.connect(self._edit_notes_key)
        # "Played before?" (Phase 36): the page asks, the window knows what is installed.
        self.detail.earlier_for = self.earlier_offers
        self.detail.money_for = self.money_of
        self.detail.steam_time_for = self.steam_time_of
        self.detail.hours_for = self.hours_of  # the Played pill (Phase 102 extension)
        self.detail.recommend_for = self.recommend_of  # the typical session and the fit (Phase 98)
        self.detail.carryOverRequested.connect(self._carry_over_key)
        self.detail.notSameRequested.connect(
            lambda key, earlier: ui_earlier.not_same_flow(self, key, earlier))
        self.detail.backRequested.connect(self.show_library)
        self.detail.navigate.connect(self._step)

        self.stats_page = StatsPage(self.metrics, self)
        self.stats_page.covers = self.covers  # the most-played games' covers (Phase 58)
        self.stats_page.backRequested.connect(self.show_library)
        self.stats_page.tabSelected.connect(self.show_tab)
        self.stats_page.shareRequested.connect(self.open_recap)

        self.storage_page = StoragePage(self.metrics, self)
        self.storage_page.backRequested.connect(self.show_library)
        self.storage_page.tabSelected.connect(self.show_tab)
        self.storage_page.gameActivated.connect(self.show_detail)
        self.storage_page.sortChanged.connect(self.set_storage_sort)
        self.storage_page.contextRequested.connect(self._context_menu)

        # The reports (Phase 84; eight since Phase 89, nine since 98): the database's answers, worked out on the way in.
        self.reports_page = ReportsPage(self.metrics, self)
        self.reports_page.backRequested.connect(self.show_library)
        self.reports_page.tabSelected.connect(self.show_tab)

        # The wishlist (Phase 87): what was said to be wanted, today's price, the fit.
        self.wishlist_page = WishlistPage(self.metrics, self)
        self.wishlist_page.backRequested.connect(self.show_library)
        self.wishlist_page.tabSelected.connect(self.show_tab)
        self.wishlist_page.storeRequested.connect(self.open_store)
        self.wishlist_page.menuRequested.connect(self._wishlist_menu)
        self.wishlist_page.choiceChanged.connect(self.set_wishlist_choice)

        # For you (Phase 98): what is waiting, most like what you play; and what fits tonight.
        self.foryou_page = ForYouPage(self.metrics, self)
        self.foryou_page.covers = self.covers
        self.foryou_page.backRequested.connect(self.show_library)
        self.foryou_page.tabSelected.connect(self.show_tab)
        self.foryou_page.playRequested.connect(self._play_key)
        self.foryou_page.detailsRequested.connect(self.show_detail)
        self.foryou_page.menuRequested.connect(self._foryou_menu)
        self.foryou_page.choiceChanged.connect(self.set_tonight_choice)
        self.foryou_page.answered.connect(self._answer_left_behind)  # Left behind (Phase 103)

        self.stack = QStackedWidget(self)
        self.stack.setObjectName("Pages")
        self.stack.addWidget(self.library)
        self.stack.addWidget(self.detail)
        self.stack.addWidget(self.stats_page)
        self.stack.addWidget(self.storage_page)
        self.stack.addWidget(self.reports_page)
        self.stack.addWidget(self.wishlist_page)
        self.stack.addWidget(self.foryou_page)

        self.hint_bar = HintBar(self.metrics, self)
        self.hint_bar.setVisible(False)

        # The top bar (Phase 31) sits above every page but a game's own. Stats and Storage
        # keep their old header object -- the pad's left/right still asks it which tab is
        # the other one -- but its tabs are the top bar's now, so it is not shown.
        self.top_bar = self.library.top_bar
        for page in (self.stats_page, self.storage_page, self.reports_page, self.wishlist_page, self.foryou_page):
            page.header_row.hide()

        # The shell paints the backdrop: the art of the game in focus, glowing through the
        # see-through library page (Phase 32). Plain background behind every other page.
        shell = Backdrop(self.covers, self)
        shell.cover_size = (self.metrics.cover_width, self.metrics.cover_height)
        shell.reduce_animations = self.reduce_animations
        self.backdrop = shell
        # The side rail (Phase 60) beside the pages, the top bar above them: at the desk the
        # window shows one or the other, as Settings says; TV mode always the bar.
        self.rail = self.library.rail
        pages = QVBoxLayout()
        pages.setContentsMargins(0, 0, 0, 0)
        pages.setSpacing(0)
        pages.addWidget(self.top_bar)
        pages.addWidget(self.stack, 1)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(self.rail)
        row.addLayout(pages, 1)
        layout = QVBoxLayout(shell)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(row, 1)
        layout.addWidget(self.hint_bar)
        self.setCentralWidget(shell)

        # Messages float as a card; the status bar underneath is kept, hidden, as the one
        # place every caller already posts to (see ui_toast).
        self.toast = Toast(shell)
        self.toast.reduce_animations = self.reduce_animations
        if hasattr(self, "rate_card"):
            self.rate_card.reduce_animations = self.reduce_animations
        # Motion (Phase 34): a page arriving, and a cover in flight. Both drawn on overlays
        # from pictures, never by animating the real widgets -- see ui_motion for the
        # measurements behind that. The message card stays on top of both.
        self.page_motion = ui_motion.PageTransition(shell)
        self.flight = ui_motion.CoverFlight(shell)
        # Starting... (Phase 99): from Play until the game is up, over everything but the message card.
        self.splash = ui_splash.LaunchSplash(shell)
        self.splash.dismissed.connect(self.end_starting)
        # How was it? (Phase 102): the rating card, where the toast floats but taking clicks.
        self.rate_card = ui_rate.RateCard(shell)
        self.rate_card.reduce_animations = self.reduce_animations
        self.rate_card.rated.connect(self._rated)
        self.rate_card.skipped.connect(lambda: self._rate_done("skipped"))
        self.rate_card.expired.connect(lambda: self._rate_done("no answer"))
        self._rate_ask: rate.Ask | None = None  # the session the card, or the tray's balloon, asks about
        self._rate_asked: dict[str, str] = {}  # game -> the day it was asked: once a game a day
        self._rate_tries = 0
        self.starting_key: str | None = None
        self._starting_timer = QTimer(self)
        self._starting_timer.setSingleShot(True)
        self._starting_timer.timeout.connect(lambda: self.end_starting("timeout"))
        QApplication.instance().applicationStateChanged.connect(self._on_app_state)
        self.toast.raise_()
        self.statusBar().hide()
        self.statusBar().messageChanged.connect(self.toast.show_message)
        self.statusBar().messageChanged.connect(self._on_status_cleared)
        self.statusBar().showMessage(READY_MESSAGE)

        search = QShortcut(QKeySequence.StandardKey.Find, self)
        search.activated.connect(self.focus_search)

    def _apply_theme(self) -> None:
        self.setStyleSheet(
            ui_theme.stylesheet(self.scale)
            + ui_tv.stylesheet(self.scale)
            + ui_screenshots.stylesheet(self.scale)
            + ui_stats.stylesheet(self.scale)
            + ui_storage.stylesheet(self.scale)
            + ui_reports.stylesheet(self.scale)
            + ui_wishlist.stylesheet(self.scale)
            + ui_foryou.stylesheet(self.scale)
            + ui_pageshell.stylesheet(self.scale)
            + ui_topbar.stylesheet(self.scale)
            + ui_continue.stylesheet(self.scale)
            + ui_jump.stylesheet(self.scale)
            + ui_rail.stylesheet(self.scale)
            + ui_detail.stylesheet(self.scale, self.library.focus_ring_width)
            + ui_settings.stylesheet(self.scale, self.library.focus_ring_width)
            + ui_folders.stylesheet(self.scale)
            + ui_first_run.stylesheet(self.scale)
            + ui_whats_new.stylesheet(self.scale)
            + ui_analysis.stylesheet(self.scale)
            + ui_library.stylesheet(self.scale)
            + ui_backdrop.stylesheet(self.scale)
        )

    # -- data ----------------------------------------------------------------------------

    def reload_views(self) -> None:
        self.detail.allow_network = bool(
            self.config.get("allow_network", rules.ALLOW_NETWORK_DEFAULT)
        )
        self.detail.set_reduce_animations(self.reduce_animations)
        self.detail.steamgriddb_key = str(self.config.get("steamgriddb_key", "") or "")
        self.views = catalog_io.merge(self.entries, self.overrides)
        self.by_key = {v.key: v for v in self.views}
        self._foryou = None  # For you's answer is asked again (Phase 98)
        # Each game's genres for the genre pill (Phase 99), read once a reload, as the Steam hours are.
        self.library.set_genres(self.overrides.genres() if hasattr(self.overrides, "genres") else {})
        self._refresh_watched()
        self._read_steam_times()
        self.library.set_views(self.views)
        self._update_empty_state()
        if self.detail.view is not None:
            refreshed = self.by_key.get(self.detail.view.key)
            if refreshed is not None:
                self.detail.set_view(refreshed)
        if self.stack.currentIndex() == FORYOU_PAGE:
            # A game marked Finished or hidden from its menu here leaves the page at once (Phase 98).
            self.foryou_page.views = self.by_key
            self.foryou_page.set_page(self.foryou_model())
        # New art for the game on screen (a cover just picked) must reach its glow too.
        self._sync_backdrop()

    def view_for(self, key: str):
        return self.by_key.get(key)

    # -- a new version of a game you had (Phase 36) -----------------------------------------

    def steam_time_of(self, view) -> dict | None:
        """Steam's own counter for this game on the accounts marked mine (Phase 76); None if none."""
        return self.steam_times.get(view.key)

    def hours_of(self, view) -> dict | None:
        """This game's hours as the reports count them (Phase 102 extension); None when the store has none."""
        return self.hours.get(view.key)

    def _read_steam_times(self) -> bool:
        """Ask the store once for every game's Steam hours -- and, with them, every game's hours as the reports
        count them (Phase 102 extension) -- True if either answer changed.

        One query for the whole library, kept here: a tile is painted many times a second
        while the grid moves, and must never ask the database. Read again on every reload,
        after a scan has landed a reading, and after the accounts' marks change in Settings.
        """
        times = self.overrides.steam_times() if getattr(self.overrides, "keeps_steam_time", False) else {}
        hours = self.overrides.hours() if hasattr(self.overrides, "hours") else {}
        changed = times != self.steam_times or hours != self.hours
        self.steam_times = times
        self.hours = hours
        self.library.steam_times = times
        return changed

    def _follow_steam_times(self) -> None:
        """A new answer reaches the tiles and the page on screen without rebuilding the grid."""
        if not self._read_steam_times():
            return
        self.library.list.viewport().update()
        if self.detail.view is not None and self.detail.view.key in self.by_key:
            self.detail.set_view(self.by_key[self.detail.view.key])

    def money_of(self, view) -> dict | None:
        """What the store knows of this game's money, for its page (Phase 74); None if nothing."""
        money = getattr(self.overrides, "money", None)
        return money(view.key) if money is not None else None

    def earlier_offers(self, view) -> list:
        """Earlier installs that look like this game, for its page to ask about."""
        return lineage.offers(view, self.overrides, self.by_key.keys())

    def _carry_over_key(self, key: str, earlier_key: str) -> None:
        view = self.by_key.get(key)
        offer = self.detail.offer
        if view is not None:
            name = offer.name if offer is not None and offer.key == earlier_key else ""
            ui_earlier.carry_flow(self, view, earlier_key, name)

    def _drop_wrong_save_folders(self) -> None:
        """Forget folders recorded as saves that never were: crash reports, telemetry.

        Recorded before Phase 36 learned to tell -- The Witcher 3's crash-report queue,
        a Firefox folder for Slow Roads. A save search drops them too, but only the next
        time that game is played; this makes the menu and the next copy right at once.
        """
        changes = {}
        for key, folders in self.overrides.values_of(rules.SAVE_DIRS_KEY).items():
            if not folders:
                continue
            kept = saves_module.only_save_folders(folders)
            if kept != folders:
                changes[key] = {rules.SAVE_DIRS_KEY: kept or None}
                log.info("%s: dropped %d folder(s) that were never its saves",
                         key, len(folders) - len(kept))
        self.overrides.update_many(changes)

    def mark_seen(self, key: str) -> None:
        """Take the NEW tag off a game, because its page was opened or it was started."""
        record = self.overrides.get(key)
        if not record or not record.get(rules.NEW_KEY):
            return
        # The view's data is this same record, so the tile loses its tag without a rebuild.
        self.overrides.update(key, **{rules.NEW_KEY: None})
        self.library.repaint_tiles()

    def play_something(self) -> None:
        """Suggest a game: open its page with Play already focused, ready to press.

        Pressing again re-rolls, and never lands on the same game twice running -- being
        offered the same title repeatedly is the one thing that would make this useless.
        """
        chosen = pick.choose(self.views, avoid_key=self._last_pick)
        if chosen is None:
            self.queue_status("Nothing to pick from yet", BRIEF_STATUS_MS)
            return
        self._last_pick = chosen.key
        self.show_detail(chosen.key)
        self.detail.focus_play()
        self.statusBar().showMessage(
            f"How about {chosen.display_name}?  (press again for another)", STATUS_MS
        )

    def _report_uninstalled(self) -> None:
        """Say which games went away, so the grid never changes silently."""
        if not self.uninstalled:
            return
        names = [entry.display_name for entry in self.uninstalled]
        shown = ", ".join(names[:REMOVED_NAMES_SHOWN])
        rest = len(names) - REMOVED_NAMES_SHOWN
        if rest > 0:
            shown += f" and {rest} more"
        word = "game" if len(names) == 1 else "games"
        self.queue_status(f"Removed {len(names)} {word} no longer on disk: {shown}",
                          REMOVED_STATUS_MS)

    def _report_refused_roots(self) -> None:
        """A whole drive or a Windows folder among the game folders -- a config.json from before
        1.2.2, or edited by hand -- is not scanned (Phase 82), and says so at every start until
        the user takes it out. The program never takes it out of his list itself."""
        for _root, why in drives.split_roots(self.config.get("roots", rules.DEFAULT_ROOTS))[1]:
            self.queue_status(f"{why} It is not scanned: choose the folder that holds the games "
                              "in Settings, under Game folders.", REMOVED_STATUS_MS)

    # -- the status bar, which three things want at once when the launcher opens ----------

    def queue_status(self, text: str, ms: int) -> None:
        """Show a message now, or hold it until the bar next falls silent.

        Opening the launcher can produce three announcements at once: a game was removed
        because it is no longer on disk, a controller was found, and the background scan
        finished. Posted directly, whichever came second erased the first inside about
        50 ms. Each one now waits its turn instead.

        Immediate `showMessage` is still right for anything the user just clicked -- by
        then the startup rush is long over and instant feedback matters more.

        Nothing is held while the window is in the tray (Phase 92): there is nothing to show
        it on, and a message saved for hours would be stale by the time anyone saw it.
        """
        if self._in_tray:
            log.debug("not shown, the window is in the tray: %s", text)
            return
        self._status_queue.append((text, ms))
        self._drain_status()

    def _drain_status(self) -> None:
        current = self.statusBar().currentMessage()
        if (current and current != READY_MESSAGE) or not self._status_queue:
            return
        text, ms = self._status_queue.pop(0)
        self.statusBar().showMessage(text, ms)

    def _on_status_cleared(self, text: str) -> None:
        if not text:
            self._drain_status()

    # -- pages ---------------------------------------------------------------------------

    def show_detail(self, key: str, arrive: str | None = None) -> None:
        view = self.by_key.get(key)
        if view is None:
            log.warning("asked to show a game that is not in the catalogue: %r", key)
            return
        # Opened from a tile? Then its cover flies from the tile to its place on the page
        # (Phase 34). Taken first, and whatever happens, so it is never used twice -- a
        # double click opens the page once and must not launch a second flight.
        origin = self.library.take_launch_rect(self.backdrop)
        if (self.stack.currentIndex() == DETAIL_PAGE and self.detail.view is not None
                and self.detail.view.key == key):
            # Already showing: the second half of a double click. Doing it all again would
            # cancel the cover still in the air -- found by a test -- and reset the page.
            self.detail.setFocus(Qt.FocusReason.OtherFocusReason)
            return
        flying = origin is not None and self._animated()
        self.flight.cancel()
        self.mark_seen(key)
        self.library.select_key(key)
        self.detail.set_view(view)
        self.refresh_running_state()
        art = self.detail.cover_art
        art.set_in_flight(flying)  # before _go, so the page's picture has an empty slot
        self._go(DETAIL_PAGE, arrive)
        if flying:
            target = self.detail.cover_rect_in(self.backdrop)
            picture = self.covers.cover(view, art.cover_width, art.cover_height, with_name=False)
            self.flight.fly(picture, origin, target, self.metrics.corner_radius, art.radius,
                            art.spread, lambda: art.set_in_flight(False), art.drop)
            self.toast.raise_()
        self.detail.setFocus(Qt.FocusReason.OtherFocusReason)

    def show_stats(self) -> None:
        """Work the figures out on the way in, never in the background.

        Nothing here is cached: it is one pass over a library of a few dozen records, and a
        cached copy would be wrong the moment a session ended behind it.
        """
        self.stats_page.views = self.views
        since = self.config.get(rules.WATCH_SINCE_KEY) if self.watch_on() else None
        self.stats_page.set_stats(stats_module.gather(self.views, self.overrides, watching_since=since))
        self.stats_page.set_recap(self.recap_line())
        self._go(STATS_PAGE)
        self.stats_page.setFocus(Qt.FocusReason.OtherFocusReason)

    def recap_line(self) -> str:
        """The Stats page's Recap line: this month's card, the one the dialog draws, in one line."""
        source = self.overrides.recap() if hasattr(self.overrides, "recap") else None
        if source is None:
            return "The recap needs the library database; it comes with the launcher's next start."
        return recap_module.summary(recap_module.build(source, recap_module.this_month()))

    def offer_recap(self) -> None:
        """Once a month, never nagging (Phase 96): on the first start or tick of a new month whose last month
        holds a session, one toast -- the tray's balloon when the window is hidden -- that its recap is ready;
        the year's from 15 December. Remembered by config.json's own keys; nothing goes to the database.
        Never in a first run, whose config.json is the question's to write."""
        if self.first_run or self._shut_down:
            return
        source = self.overrides.recap() if hasattr(self.overrides, "recap") else None
        if source is None:
            return
        due = recap_module.offers(None, self.config.get(rules.RECAP_OFFERED_KEY),
                                  self.config.get(rules.RECAP_YEAR_OFFERED_KEY),
                                  lambda period: source.one("recap_totals", **period.bounds()).get("sessions") or 0)
        for key, value, words in due:
            self.config[key] = value
            config_io.save_config({key: value})
            if self._in_tray and self.tray is not None:
                self.tray.say(words)
            else:
                self.queue_status(words, STATUS_MS)
            log.info("recap offered: %s", words)

    def open_recap(self) -> None:
        """Share as image... (Phase 96): the card previewed, a period to choose, Copy image, Save image."""
        source = self.overrides.recap() if hasattr(self.overrides, "recap") else None
        if source is None:
            self.statusBar().showMessage("The recap needs the library database.", BRIEF_STATUS_MS)
            return
        fit = None
        if self.tv_mode and self.screen() is not None:
            # On the TV the preview fits the screen; the image is still RECAP_IMAGE_WIDTH x HEIGHT.
            fit = round(self.screen().availableGeometry().height() * ui_rules.RECAP_PREVIEW_TV_SHARE)
        art = ui_recap.Art(self.icons, self.by_key)
        dialog = ui_recap.RecapDialog(source, art, self, fit_height=fit, scale=self.metrics.scale)
        dialog.exec()

    def foryou_model(self, fresh: bool = True):
        """For you's page (Phase 98), from the database's queries -- or None when the library cannot answer.
        Kept until the next reload, so a game's page asks it again only after something changed."""
        if fresh or self._foryou is None:
            source = self.overrides.recommend() if hasattr(self.overrides, "recommend") else None
            self._foryou = (recommend_module.page(source, self.config.get(rules.FORYOU_TONIGHT_KEY))
                            if source is not None else None)
        return self._foryou

    def show_foryou(self) -> None:
        """Worked out on the way in, as Reports is: what is waiting, by the fit, and what fits tonight."""
        self.foryou_page.views = self.by_key
        self.foryou_page.set_page(self.foryou_model())
        self._go(FORYOU_PAGE)
        self.foryou_page.ensure_focus()

    def _answer_left_behind(self, key: str, answer: str) -> None:
        """Left behind's answers (Phase 103): Finished and Dropped set the mark, dated as every mark is; Still
        playing writes only when it was answered, and the game is left alone for LEFT_BEHIND_DAYS."""
        view = self.by_key.get(key)
        if view is None:
            return
        if answer == "still":
            ui_actions.still_playing(self, view)
        elif answer in (rules.STATUS_FINISHED, rules.STATUS_DROPPED):
            ui_actions.set_status(self, view, answer)
        self._refresh_hints()

    def set_tonight_choice(self, minutes: int) -> None:
        """Tonight's choice, remembered by its own key."""
        self.config[rules.FORYOU_TONIGHT_KEY] = minutes
        config_io.save_config({rules.FORYOU_TONIGHT_KEY: minutes})

    def _foryou_menu(self, key: str, position) -> None:
        """The game's own menu, with Details first: the page's pad has no other way to a game's page."""
        view = self.by_key.get(key)
        if view is None:
            return
        menu = ui_actions.build_menu(self, view)
        details = menu.addAction("Details")
        details.triggered.connect(lambda: self.show_detail(key))
        menu.removeAction(details)
        menu.insertAction(menu.actions()[0], details)
        self.hint_bar.set_hints(ui_tv.MENU)
        try:
            menu.exec(position)
        finally:
            self._refresh_hints()

    def recommend_of(self, view) -> tuple[str, str]:
        """A game's page (Phase 98): its typical session, as a pill, and for a waiting game its fit, as a fact."""
        model = self.foryou_model(fresh=False)
        return recommend_module.facts_for(model, view.key) if model is not None else ("", "")

    def show_storage(self) -> None:
        """The same deal as the stats page: worked out on the way in, never cached.

        Free space in particular has to be read now -- a figure from five minutes ago is
        the one number on that page that could mislead someone deciding what to delete.
        """
        self.storage_page.set_storage(
            storage_module.gather(self.views, self.overrides, sort_mode=self.storage_sort)
        )
        self._go(STORAGE_PAGE)
        self.storage_page.ensure_focus()

    def show_reports(self) -> None:
        """The reports, worked out from the database on the way in, as Stats is (Phase 84).

        No cache: the queries are the database's own answer now (39 ms on the user's library), and
        the page rebuilds its cards only when an answer changed. A library that cannot answer -- the
        JSON one after a refused migration, or a database below version 5 -- gets a card saying so.
        """
        source = self.overrides.reports() if hasattr(self.overrides, "reports") else None
        self.reports_page.set_reports(reports_module.build(source) if source is not None else None)
        self._go(REPORTS_PAGE)
        self.reports_page.setFocus(Qt.FocusReason.OtherFocusReason)

    def wishlist_model(self):
        """The Wishlist page's rows (Phase 87), from the database's queries -- or None when the
        library cannot answer (the JSON store, or a database below version 6)."""
        if not getattr(self.overrides, "keeps_wishlist", False):
            return None
        source = self.overrides.reports()
        if source is None:
            return None
        hidden = {int(a) for a in self.config.get(rules.WISHLIST_HIDDEN_SETTING) or [] if str(a).isdigit()}
        online = bool(self.config.get("allow_network", rules.ALLOW_NETWORK_DEFAULT))
        return wishlist.page(source, self.overrides.steam_accounts(), hidden, online,
                             alerts=getattr(self.overrides, "keeps_alerts", False))

    def show_wishlist(self) -> None:
        """The wished games, worked out from the database on the way in, as Reports is (Phase 87).
        The covers already cached show at once; the rest are fetched while the page is looked at."""
        model = self.wishlist_model()
        appids = [] if model is None else [r.appid for r in model.rows + model.removed + model.hidden]
        cache = str(paths.cache_dir())
        cached = {a: steam_web.capsule_path(cache, a) for a in appids}
        choice = self.config.get(rules.WISHLIST_FILTER_SETTING) or wishlist.ALL
        self.wishlist_page.set_page(model, choice, {a: path for a, path in cached.items() if path})
        self._go(WISHLIST_PAGE)
        self.wishlist_page.ensure_focus()
        self._fetch_wishlist_covers([a for a, path in cached.items() if not path])

    def _fetch_wishlist_covers(self, appids: list[int]) -> None:
        if not appids or not self.config.get("allow_network", rules.ALLOW_NETWORK_DEFAULT):
            return
        if self.capsule_worker is not None and self.capsule_worker.isRunning():
            return  # one visit's fetch at a time; the next visit asks for what is still missing
        self.capsule_worker = CapsuleWorker(appids, str(paths.cache_dir()), self)
        self.capsule_worker.ready.connect(self.wishlist_page.set_art)
        self.capsule_worker.start()

    def open_store(self, appid: int) -> bool:
        """A wished game's store page in the Steam client, by the protocol Steam registered (Phase 87,
        checked on this machine); the store's web page in the browser when nothing takes it."""
        if ui_settings.open_in_browser(rules.STEAM_STORE_PAGE_URI.format(appid=int(appid))):
            return True
        log.info("wishlist: steam://store was not taken; the store's web page instead")
        return ui_settings.open_in_browser(rules.STEAM_STORE_WEB_PAGE.format(appid=int(appid)))

    def _wishlist_menu(self, appid: int, position) -> None:
        """X on a wished game, or a right click: Open in Steam; Hide from this page, or show it again --
        a mark kept on this PC, never a change to the Steam list."""
        row = self.wishlist_page.row_for(appid)
        if row is None:
            return
        menu = QMenu(self)
        menu.addAction("Open in Steam", lambda: self.open_store(appid))
        if getattr(self.overrides, "keeps_alerts", False) and not row.removed:  # Phase 101
            words = "Change alert..." if row.target_cents is not None else "Alert me under..."
            menu.addAction(words, lambda: self.set_price_alert(appid))
            if row.target_cents is not None:
                menu.addAction("Remove alert", lambda: self.remove_price_alert(appid))
        if row.hidden:
            menu.addAction("Show on this page again", lambda: self.set_wishlist_hidden(appid, False))
        else:
            menu.addAction("Hide from this page", lambda: self.set_wishlist_hidden(appid, True))
        self.hint_bar.set_hints(ui_tv.MENU)
        try:
            menu.exec(position)
        finally:
            self._refresh_hints()

    def set_wishlist_hidden(self, appid: int, hidden: bool) -> None:
        """A game hidden from the page, or shown again: one key of config.json, never the whole config."""
        marks = {int(a) for a in self.config.get(rules.WISHLIST_HIDDEN_SETTING) or [] if str(a).isdigit()}
        marks = (marks | {int(appid)}) if hidden else (marks - {int(appid)})
        self.config[rules.WISHLIST_HIDDEN_SETTING] = sorted(marks)
        config_io.save_config({rules.WISHLIST_HIDDEN_SETTING: sorted(marks)})
        self.wishlist_page.set_page(self.wishlist_model())

    def set_wishlist_choice(self, choice: str) -> None:
        """Remember the chip, as the library's -- one key."""
        self.config[rules.WISHLIST_FILTER_SETTING] = choice
        config_io.save_config({rules.WISHLIST_FILTER_SETTING: choice})

    def _price_alerts(self, fresh) -> None:
        """After a scan has landed its prices and lists (Phase 101): the alerts the new prices set off, written to
        the log first (logic/alerts.land), then one message for all of them -- the toast while the window is shown,
        the tray's balloon while it is hidden, and a click on the balloon opens the Wishlist tab on its alerts.
        Phase 87's once-a-day "N at their lowest" notice is retired: its count is a line on the Wishlist tab."""
        hidden = {int(a) for a in self.config.get(rules.WISHLIST_HIDDEN_SETTING) or [] if str(a).isdigit()}
        try:
            sent = alerts.land(self.overrides, fresh, hidden)
        except Exception as exc:  # noqa: BLE001 -- an alert must never cost a scan its landing
            log.warning("price alerts: none worked out (%s)", exc)
            return
        if not sent:
            return
        words = alerts.message(sent)
        log.info("price alerts: %s", words)
        if self._in_tray and self.tray is not None:
            self.tray.say(words, clicked=self.open_alerts)
        else:
            self.queue_status(words, STATUS_MS)
        if self.stack.currentWidget() is self.wishlist_page:
            self.wishlist_page.set_page(self.wishlist_model())

    def open_alerts(self) -> None:
        """The price alert's balloon, clicked: the window back, on the Wishlist tab, its Alerts showing -- for
        this visit; the chip remembered stays the user's own."""
        self.bring_forward()
        self.show_wishlist()
        self.wishlist_page.choose(wishlist.ALERTS)

    def set_price_alert(self, appid: int) -> None:
        """Alert me under...: a wished game's target, in its price's currency, from the dialog (Phase 101)."""
        row = self.wishlist_page.row_for(appid)
        if row is None:
            return
        start = next((c for c in (row.target_cents, row.lowest_cents, row.cents) if c), rules.ALERT_TARGET_STEP_CENTS)
        dialog = ui_alert.TargetDialog(self, row.name, row.currency or rules.STEAM_STORE_CURRENCY, start,
                                       today=row.price, lowest=row.lowest)
        if dialog.exec() != int(QDialog.DialogCode.Accepted):
            return
        if self.overrides.set_price_target(appid, dialog.cents(), dialog.currency):
            self.statusBar().showMessage(f"Alert set: {row.name} under {dialog.words()}", BRIEF_STATUS_MS)
        self.wishlist_page.set_page(self.wishlist_model())

    def remove_price_alert(self, appid: int) -> None:
        """Remove alert: the target taken away; the alerts it sent stay in the log and on the Alerts list."""
        row = self.wishlist_page.row_for(appid)
        if self.overrides.remove_price_target(appid) and row is not None:
            self.statusBar().showMessage(f"Alert removed: {row.name}", BRIEF_STATUS_MS)
        self.wishlist_page.set_page(self.wishlist_model())

    def set_storage_sort(self, mode: str) -> None:
        self.storage_sort = mode
        self.config["storage_sort"] = mode
        # This one key, never the whole in-memory config. That copy holds the mode the
        # window is in right now, and saving it wholesale here once turned a visit to the
        # TV shortcut into "always start in TV mode" for the ordinary one.
        config_io.save_config({"storage_sort": mode})
        self.storage_page.set_storage(
            storage_module.gather(self.views, self.overrides, sort_mode=mode)
        )
        self.storage_page.ensure_focus()

    def set_library_filter(self, name: str) -> None:
        """Remember the chosen chip, like the sort -- one key, never the whole config."""
        self.config["library_filter"] = name
        config_io.save_config({"library_filter": name})

    def focus_search(self) -> None:
        """Ctrl+F: straight to the search pill, from any page."""
        self.show_library()
        self.library.filter_box.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.library.filter_box.selectAll()

    def set_library_genre(self, name: str) -> None:
        """The genre pill's pick (Phase 99), by its own key."""
        self.config[ui_rules.LIBRARY_GENRE_KEY] = name
        config_io.save_config({ui_rules.LIBRARY_GENRE_KEY: name})

    def set_library_sort(self, mode: str) -> None:
        """Remember the grid's sort, the way the storage page already remembered its own."""
        self.config["library_sort"] = mode
        config_io.save_config({"library_sort": mode})

    def show_tab(self, name: str) -> None:
        """Move between the pages that share a header: Stats, Storage, Reports, Wishlist."""
        if name == ui_pageshell.TAB_STORAGE:
            self.show_storage()
        elif name == ui_pageshell.TAB_REPORTS:
            self.show_reports()
        elif name == ui_pageshell.TAB_WISHLIST:
            self.show_wishlist()
        elif name == ui_pageshell.TAB_FORYOU:
            self.show_foryou()
        else:
            self.show_stats()

    def _cross(self, direction: int) -> None:
        """The pad's left (-1) or right (+1) on a tab page: the next place along the bar -- Library,
        Stats, Storage, Reports, Wishlist -- and nothing past either end (Phase 84; two tabs simply swapped)."""
        at = TAB_SEQUENCE.index(self.stack.currentIndex()) + direction
        if not 0 <= at < len(TAB_SEQUENCE):
            return
        {LIBRARY_PAGE: self.show_library, STATS_PAGE: self.show_stats, STORAGE_PAGE: self.show_storage,
         REPORTS_PAGE: self.show_reports, WISHLIST_PAGE: self.show_wishlist,
         FORYOU_PAGE: self.show_foryou}[TAB_SEQUENCE[at]]()

    def show_library(self) -> None:
        """Back to the grid -- with the cover flying home into its tile, if both are in view."""
        homing = None
        if (self.stack.currentIndex() == DETAIL_PAGE and self.detail.view is not None
                and self._animated() and self.detail.cover_on_screen()
                and self.detail.view.key in self.library.visible_keys):
            view = self.detail.view
            art = self.detail.cover_art
            homing = (view.key, self.detail.cover_rect_in(self.backdrop),
                      self.covers.cover(view, art.cover_width, art.cover_height, with_name=False),
                      art.radius)
            # Before _go, so the grid's picture has the tile's cover left out.
            self.library.flying_key = view.key
        self.flight.cancel()
        self._go(LIBRARY_PAGE)
        if homing is not None:
            key, start, picture, radius = homing
            target = self.library.tile_cover_rect(key, self.backdrop)
            if target is None:
                self._landed_in_grid()
            else:
                self.flight.fly(picture, start, target, radius, self.metrics.corner_radius,
                                max(2, round(ui_rules.TILE_SHADOW_SPREAD * self.scale)),
                                self._landed_in_grid)
                self.toast.raise_()
        self.library.list.setFocus(Qt.FocusReason.OtherFocusReason)

    def _landed_in_grid(self) -> None:
        self.library.flying_key = ""
        self.library.list.viewport().update()

    def _backdrop_follows(self, key: str) -> None:
        """The library moved to another game; its glow follows, if the library is showing."""
        if self.stack.currentIndex() in GLOWING_PAGES:
            self.backdrop.set_view(self.by_key.get(key))

    def _sync_backdrop(self, index: int | None = None, animate: bool = True) -> None:
        """The glow for the page on screen: the focused game on the library, this game on
        its own page (Phase 33), and the plain colour behind Stats and Storage."""
        index = self.stack.currentIndex() if index is None else index
        if index in GLOWING_PAGES:
            # Stats, Storage and Reports keep the library's glow (Phase 35, 84): tabs of one
            # place, so moving between them never changes the colour of the room.
            view = self.by_key.get(self.library.backdrop_key())
        elif index == DETAIL_PAGE and self.detail.view is not None:
            view = self.by_key.get(self.detail.view.key, self.detail.view)
        else:
            view = None
        self.backdrop.set_view(view, animate)

    TOP_BAR_TABS = {
        LIBRARY_PAGE: ui_topbar.TAB_LIBRARY,
        STATS_PAGE: ui_topbar.TAB_STATS,
        STORAGE_PAGE: ui_topbar.TAB_STORAGE,
        REPORTS_PAGE: ui_topbar.TAB_REPORTS,
        WISHLIST_PAGE: ui_topbar.TAB_WISHLIST,
        FORYOU_PAGE: ui_topbar.TAB_FORYOU,
    }

    # Which way a page arrives: across between the three tabs, from the side the tab is on;
    # up a little into a game's own page; in place for everything else, Back included.
    TAB_ORDER = {page: order for order, page in enumerate(TAB_SEQUENCE)}

    def _arrival(self, previous: int, index: int) -> str:
        if index == DETAIL_PAGE:
            return ui_motion.RISE
        if previous in self.TAB_ORDER and index in self.TAB_ORDER:
            later = self.TAB_ORDER[index] > self.TAB_ORDER[previous]
            return ui_motion.FROM_RIGHT if later else ui_motion.FROM_LEFT
        return ui_motion.FADE

    def _animated(self) -> bool:
        return not self.reduce_animations and self.isVisible()

    def _go(self, index: int, arrive: str | None = None) -> None:
        """Show a page. `arrive` makes even the page already showing arrive again -- the
        next game sliding in from the right, the previous from the left."""
        previous = self.stack.currentIndex()
        moving = (previous != index or arrive is not None) and self._animated()
        # The bar -- or the rail -- follows the page: hidden on a game's own page, the right
        # place lit elsewhere.
        self._show_chrome(index)
        # While a page arrives it is the motion; the glow behind it changes at once rather
        # than crossfading under it -- at the TV's 225% the two together cost half as much
        # again per frame.
        self._sync_backdrop(index, animate=not moving)
        if index in self.TOP_BAR_TABS:
            self.top_bar.set_current(self.TOP_BAR_TABS[index])
            self.rail.set_current(self.TOP_BAR_TABS[index])
        if previous == index and arrive is None:
            return
        if previous != index:
            self.stack.setCurrentIndex(index)
            self._refresh_hints()
        if not moving:
            self.page_motion.cancel()
            return
        # The bar appearing or going changes where the pages sit: settle that first, so the
        # picture is taken of the page where it will actually be.
        ui_motion.settle_layouts(self.centralWidget())
        self.page_motion.scale = self.scale
        self.page_motion.start(self.stack.currentWidget(),
                               arrive or self._arrival(previous, index))
        self.flight.raise_()
        self.toast.raise_()

    def _apply_layout(self) -> None:
        """The side rail at the desk when Settings says so (the default), the top bar
        otherwise and always in TV mode, whose pad paths were built around it (Phase 60)."""
        rail = (not self.tv_mode and self.config.get("library_layout", ui_rules.LIBRARY_LAYOUT_DEFAULT)
                == ui_rules.LAYOUT_RAIL)
        self.library.set_layout(ui_rules.LAYOUT_RAIL if rail else ui_rules.LAYOUT_TOP)
        for page in (self.stats_page, self.storage_page, self.reports_page, self.wishlist_page, self.foryou_page):
            page.set_rail(rail)
        self._show_chrome(self.stack.currentIndex())

    def _show_chrome(self, index: int) -> None:
        rail = self.library.layout_mode == ui_rules.LAYOUT_RAIL
        self.top_bar.setVisible(not rail and index != DETAIL_PAGE)
        self.rail.setVisible(rail and index != DETAIL_PAGE)

    def _step(self, direction: int) -> None:
        """The previous or next game, sliding in from the side it is on (Phase 34)."""
        if self.detail.view is None:
            return
        key = self.library.neighbour(self.detail.view.key, direction)
        if key:
            self.show_detail(key, ui_motion.FROM_RIGHT if direction > 0 else ui_motion.FROM_LEFT)

    # -- actions -------------------------------------------------------------------------

    def _context_menu(self, key: str, position) -> None:
        view = self.by_key.get(key)
        if view is not None:
            self.hint_bar.set_hints(ui_tv.MENU)
            try:
                ui_actions.build_menu(self, view).exec(position)
            finally:
                self._refresh_hints()

    PAGE_HINTS = {
        LIBRARY_PAGE: ui_tv.LIBRARY,
        DETAIL_PAGE: ui_tv.DETAIL,
        STATS_PAGE: ui_tv.STATS,
        STORAGE_PAGE: ui_tv.STORAGE,
        REPORTS_PAGE: ui_tv.REPORTS,
        WISHLIST_PAGE: ui_tv.WISHLIST,
        FORYOU_PAGE: ui_tv.FORYOU,
    }

    def _refresh_hints(self, *_args) -> None:
        """The TV hint bar says what the buttons do here: a dialog, or the page (Phase 35)."""
        hint_bar = getattr(self, "hint_bar", None)
        if hint_bar is None:
            return
        if QApplication.activeModalWidget() is not None:
            hint_bar.set_hints(ui_tv.DIALOG)
        elif getattr(self, "rate_card", None) is not None and self.rate_card.showing:
            hint_bar.set_hints(ui_tv.RATE)  # How was it? (Phase 102)
        elif self.stack.currentIndex() == FORYOU_PAGE and self.foryou_page.on_answer():
            hint_bar.set_hints(ui_tv.FORYOU_ANSWER)  # Left behind: A answers (Phase 103)
        else:
            hint_bar.set_hints(self.PAGE_HINTS.get(self.stack.currentIndex(), ui_tv.LIBRARY))

    def play(self, view) -> None:
        if not self._already_running(view.key):
            ui_actions.play(self, view)

    # -- Starting... (Phase 99) -------------------------------------------------------------------------------

    def begin_starting(self, view) -> None:
        """Play was pressed: every surface says Starting... and Play rests, and -- with the window on screen -- the
        splash covers it, the game's hero and name on it. Ended by `end_starting`, whichever comes first."""
        self.starting_key = view.key
        log.info("starting %s", view.display_name)
        self._withdraw_rating("a game started")
        if self.isVisible() and not self.isMinimized() and not self._in_tray:
            # The game's wide art; with none of its own, the accent's wash under its cover (the splash draws it).
            art = (self.covers.banner(view, self.width(), self.height(), ui_rules.DETAIL_HERO_ANCHOR)
                   if view.banner_source else None)
            cover = self.covers.cover(view, round(ui_rules.LAUNCH_SPLASH_COVER[0] * self.scale),
                                      round(ui_rules.LAUNCH_SPLASH_COVER[1] * self.scale), with_name=False)
            self.splash.begin(view.key, view.display_name, art, cover, self.scale, self.tv_mode, self.reduce_animations)
        self._starting_timer.start(rules.LAUNCH_SPLASH_MAX_S * 1000)
        self._show_starting()

    def end_starting(self, why: str = "") -> None:
        """The game is up, or it is not coming, or they asked: the splash goes, the surfaces say what is true."""
        if self.starting_key is None:
            return
        view = self.by_key.get(self.starting_key)
        log.info("starting %s: ended (%s)", view.display_name if view else self.starting_key, why or "done")
        self.starting_key = None
        self._starting_timer.stop()
        self.splash.end()
        self._show_starting()

    def is_starting(self, key: str) -> bool:
        return self.starting_key is not None and key == self.starting_key

    def _show_starting(self) -> None:
        """Every surface that offers Play: the tile, the game's page, the Continue and Jump back in cards, For you,
        and the tray's tooltip."""
        self.library.update_running()
        self.detail.set_starting(self.detail.view is not None and self.is_starting(self.detail.view.key))
        self.foryou_page.set_starting(self.starting_key)
        if self.tray is not None:
            if self.starting_key is not None:
                view = self.by_key.get(self.starting_key)
                self.tray.set_tooltip(f"Starting {view.display_name if view else 'a game'}\u2026")
            else:
                self._update_tray_tooltip()

    def _on_app_state(self, state) -> None:
        # The game took the screen: the launcher is no longer the window in front.
        if self.starting_key is not None and state != Qt.ApplicationState.ApplicationActive:
            self.end_starting("the game took the screen")

    def run_launch(self, start):
        """`start()` on a thread of its own, the window answering meanwhile -- painting the splash, taking Escape
        and the pad -- and its result handed back as if it had been called here (Phase 99)."""
        worker = LaunchWorker(start, self)
        loop = QEventLoop()
        worker.finished.connect(loop.quit)
        worker.start()
        if not worker.isFinished():
            loop.exec()
        worker.wait()
        if worker.error is not None:
            from logic.launch import LaunchResult
            return LaunchResult(False, error=str(worker.error))
        return worker.result

    def _play_key(self, key: str) -> None:
        view = self.by_key.get(key)
        if view is not None and not self._already_running(key):
            ui_actions.play(self, view)

    def _already_running(self, key: str) -> bool:
        """A game seen running, started outside the launcher, is never started a second time from here --
        the tile, the card, the tray menu and the pad all come through this (Phase 93)."""
        if not self.observed_running(key):
            return False
        view = self.by_key.get(key)
        self.statusBar().showMessage(f"{view.display_name if view else 'It'} is already running "
                                     "(started outside the launcher, timed by watching)", BRIEF_STATUS_MS)
        return True

    def _open_folder_key(self, key: str) -> None:
        view = self.by_key.get(key)
        if view is not None:
            ui_actions.open_folder(self, view)

    def _uninstall_key(self, key: str) -> None:
        view = self.by_key.get(key)
        if view is not None:
            ui_removal.uninstall(self, view)

    def _stop_key(self, key: str) -> None:
        view = self.by_key.get(key)
        if view is not None:
            ui_actions.stop(self, view)

    def refresh_running_state(self) -> None:
        """Tell the detail page whether the game it is showing is up right now."""
        self.library.update_running()
        view = self.detail.view
        self.detail.set_running(view is not None and self.tracker.is_running(view.key))
        self.detail.set_observed(view is not None and self.observed_running(view.key))  # Phase 93
        self.detail.set_starting(view is not None and self.is_starting(view.key))  # Phase 99
        # The uninstall tier depends on the same thing: a running game refuses, so the
        # button has to be relabelled the moment a session starts or ends, not only when
        # the page is opened.
        if view is not None:
            plan = removal.plan(view, self.config, self.tracker)
            self.detail.set_uninstall(
                f"{plan.button}..." if plan.available else "Uninstall...",
                plan.available,
                plan.blocked or plan.explanation,
            )

    def _toggle_favorite_key(self, key: str) -> None:
        view = self.by_key.get(key)
        if view is not None:
            ui_actions.toggle_favorite(self, view)

    def _set_status_key(self, key: str, status: str) -> None:
        view = self.by_key.get(key)
        if view is not None:
            ui_actions.set_status(self, view, status)

    def _edit_notes_key(self, key: str) -> None:
        view = self.by_key.get(key)
        if view is not None:
            ui_actions.edit_notes(self, view)

    # -- the first run (Phase 77) ----------------------------------------------------------

    def _ask_where_games_are(self) -> None:
        """Before the first scan of a fresh install: where are the games? Asked once.

        Whatever comes back is written -- an empty list of folders included, the answer of
        someone whose games all come from stores -- so config.json exists from here on and the
        question is never asked again on the strength of an empty list.
        """
        if self._first_run_asked:
            return
        self._first_run_asked = True
        scale = (float(self.config.get("tv_scale", ui_rules.TV_SCALE_DEFAULT)) if self.tv_mode else self.scale)
        dialog = ui_first_run.FirstRunDialog(first_run.candidates(), first_run.xbox_found(), scale,
                                             tv=self.tv_mode, parent=self)
        dialog.exec()
        roots, xbox = dialog.answer()
        values = {"roots": roots, "enable_xbox": xbox, rules.VERSION_SEEN_KEY: version.APP_VERSION}
        if not config_io.save_config(values):
            QMessageBox.warning(self, "Could not save", "Your answer could not be written to disk; "
                                "the launcher will ask again next time.")
        self.config.update(values)
        self.first_run = False
        log.info("first run answered: %s; Xbox %s", roots or "no folders -- stores only", "on" if xbox else "off")
        self._arm_watcher()
        self.start_scan(trigger="first_run")
        # The second question (Phase 79), while that scan runs behind it: a SteamGridDB key.
        self._ask_for_art_key(scale)

    def _ask_for_art_key(self, scale: float) -> None:
        """After the folders: would they like more cover art? A key of their own, or skip it.

        Skipping writes nothing -- the key is optional, and Settings has the same field.
        A key given is written with its own key alone (never self.config wholesale) and never
        logged.
        """
        dialog = ui_first_run.KeyDialog(scale, tv=self.tv_mode, parent=self)
        dialog.exec()
        key = dialog.answer()
        if not key:
            log.info("first run: no SteamGridDB key (skipped)")
            return
        if not config_io.save_config({"steamgriddb_key": key}):
            QMessageBox.warning(self, "Could not save", "The key could not be written to disk; "
                                "add it again in Settings, under Artwork and the internet.")
            return
        self.config["steamgriddb_key"] = key
        self.detail.steamgriddb_key = key
        log.info("first run: a SteamGridDB key was added")

    # -- is a newer version out (Phase 79) -------------------------------------------------

    def _check_for_updates(self, quiet: bool = False) -> None:
        """A few seconds after the session begins, and with every tick (Phase 92): an installed copy
        asks GitHub, at most once a day (web.updates decides). One run from source -- this PC's --
        never asks. `quiet`: the tick's, logged at debug."""
        allowed, why = updates.should_check(self.config)
        if not allowed:
            (log.debug if quiet else log.info)("update check: not asked (%s)", why)
            return
        if self.update_worker is not None and self.update_worker.isRunning():
            return
        self.update_worker = UpdateWorker(str(paths.cache_dir()), self)
        self.update_worker.answered.connect(self._on_update_answer)
        self.update_worker.start()

    def _on_update_answer(self, answer, asked: bool) -> None:
        """The answer, on the GUI thread. Said once a day at most: when GitHub was just asked."""
        if answer is None:
            return
        self.update_answer = answer
        if asked and answer.newer:
            self.queue_status(f"{version.APP_NAME} {answer.latest} is out. Settings, under About, "
                              "has the download page.", NEW_STATUS_MS)

    def _update_empty_state(self) -> None:
        """The library with nothing in it says why: no folders chosen, the folders not there,
        or nothing found in them -- and, while a scan runs, that it is looking (Phase 77)."""
        if not hasattr(self, "library"):
            return
        if self.entries or (self.first_run and not self._first_run_asked):
            self.library.set_empty(None)
            return
        # A whole drive or a Windows folder is "needs attention", never "missing" (Phase 82).
        roots, refused = drives.split_roots(self.config.get("roots", rules.DEFAULT_ROOTS))
        here, gone = first_run.reachable(roots)
        if self.worker is not None and self.worker.isRunning():
            message = ("Looking for your games...", "This takes a few seconds the first time.", "")
        elif refused:
            others = f" Nor in {', '.join(root for root, _why in refused[1:])}." if refused[1:] else ""
            message = (refused[0][1].rstrip("."),
                       "The launcher does not look in it: every folder there would be taken for a "
                       f"game.{others} Choose the folder that holds your games instead.", "Game folders...")
        elif not roots:
            message = ("No games yet",
                       "The launcher finds games from Steam, GOG, Epic and Xbox by itself, and any "
                       "others in folders you choose. No folder is chosen, and no store has a game "
                       "installed on this PC.", "Choose game folders...")
        elif not here:
            message = ("Your game folders cannot be reached",
                       f"None of these is there right now: {', '.join(gone)}. A drive may be "
                       "unplugged -- plug it in and press Rescan, or choose other folders.", "Game folders...")
        else:
            missing = f" ({', '.join(gone)} cannot be reached)" if gone else ""
            message = ("No games found",
                       f"Nothing that looks like a game in {', '.join(here)}{missing}, and no store "
                       "has a game installed on this PC.", "Game folders...")
        self.library.set_empty(message)

    # -- missing covers, filled in one go (Phase 105) ----------------------------------------

    def missing_covers(self) -> list:
        """The games the grid shows with no cover -- the batch's list, and Settings' count."""
        return fill_covers.missing(self.views)

    def fill_missing_covers(self, parent, key: str) -> None:
        """Settings' Fill missing covers...: the dialog over Settings, the batch it runs, then the grid redrawn and
        a scan held back meanwhile run."""
        games = [(view.key, view.display_name) for view in self.missing_covers()]
        if not games:
            return
        scale = float(self.config.get("tv_scale", ui_rules.TV_SCALE_DEFAULT)) if self.tv_mode else self.scale
        dialog = ui_fill_covers.FillCoversDialog(games, key, self, scale, tv=self.tv_mode, parent=parent)
        self._filling, self._covers_filled = True, 0
        try:
            dialog.exec()
        finally:
            self._filling = False
            self.cover_fill_worker = None
            self._fill_refresh.stop()
            if self._covers_filled:
                self._redraw_filled()
            held, self._held_scan = self._held_scan, None
            if held is not None:
                log.info("the missing covers are filled; the scan held back runs now")
                self.start_scan(**held)

    def scan_running(self) -> bool:
        return self.worker is not None and self.worker.isRunning()

    def fill_backup(self) -> str:
        """The backup before the batch's first write: a snapshot of the library as it is (or the newest, when it
        already holds it), by name -- "" when none could be taken, and then nothing is looked up."""
        taken = backups.snapshot_or_newest(rules.FILL_COVERS_SNAPSHOT_REASON)
        if taken is None:
            log.error("fill covers: no backup could be taken; nothing is looked up")
            return ""
        log.info("fill covers: the library is held in backup %s first", taken.stamp)
        return taken.stamp

    def cover_found(self, key: str, path: str) -> None:
        """One cover the batch found, written at once; the grid redrawn a moment later, for several together."""
        view = self.by_key.get(key)
        if view is None:
            log.info("fill covers: %s is no longer in the library; its cover is not written", key)
            return
        if ui_cover_actions.fill_cover(self, view, path):
            self._covers_filled += 1
            if not self._fill_refresh.isActive():
                self._fill_refresh.start()

    def track_fill(self, worker) -> None:
        self.cover_fill_worker = worker

    def _redraw_filled(self) -> None:
        ui_cover_actions.covers_filled(self, self._covers_filled)

    def open_settings(self, focus: str | None = None) -> None:
        # The catalog's identity keys let an import report which of its games are actually
        # installed here and which are being kept in reserve.
        roots_before = list(self.config.get("roots", rules.DEFAULT_ROOTS))
        before_watch = bool(self.config.get(rules.WATCH_GAMES_KEY, rules.WATCH_GAMES_DEFAULT))
        dialog = SettingsDialog(self.config, self, known_keys={e.identity_key for e in self.entries},
                                store=self.overrides, focus=focus, covers=self)
        accent_before = self.accent
        dialog.accentChosen.connect(self.apply_accent)  # a swatch shows at once, the dialog included (Phase 99)
        result = dialog.exec()
        if result == DATA_REPLACED:
            self.reload_after_restore(dialog.restore_message)
            return
        if result != QDialog.DialogCode.Accepted:
            if self.accent != accent_before:
                self.apply_accent(accent_before)  # Cancel puts the accent back as it was
            return
        values = dialog.values()
        self.config.update(values)
        if not config_io.save_config(values):
            QMessageBox.warning(self, "Could not save", "Settings could not be written to disk.")
        # Whose Steam time counts (Phase 75): only the marks changed, into the library.
        unsaved = [account_id for account_id, mine in dialog.account_marks().items()
                   if not self.overrides.set_account_mark(account_id, mine)]
        if unsaved:
            QMessageBox.warning(self, "Could not save", "Which Steam accounts are yours could not be saved.")
        self._follow_steam_times()  # Phase 76: what counts as mine may have changed

        self.reduce_animations = values["reduce_animations"]
        self.toast.reduce_animations = self.reduce_animations
        if hasattr(self, "rate_card"):
            self.rate_card.reduce_animations = self.reduce_animations
        if values["enable_controller"] and not self.pads.available:
            self.pads.start()
        elif not values["enable_controller"] and self.pads.available:
            self.pads.stop()
        self._arm_watcher()

        # set_tv_mode reapplies the theme and every metric, so it covers a scale change too.
        self.scale = values["ui_scale"]
        self.set_tv_mode(values["tv_mode"])
        self._set_keep_running(bool(values.get(rules.KEEP_RUNNING_KEY, False)))
        if values.get(rules.WATCH_GAMES_KEY) and not before_watch:
            self._keep_watch_since()  # turned on here: the day it began, said under the switch
        self._apply_watch()  # Phase 93: on or off at once, as the switch now says
        # Start with Windows (Phase 92) has no key in config.json: the Run value is its record, so the
        # switch never disagrees with what Windows will do. Only a change is written.
        start = dialog.start_with_windows()
        if start is not None and start != dialog.started_with_windows:
            if not (autostart.enable() if start else autostart.disable()):
                QMessageBox.warning(self, "Could not save", "Start with Windows could not be changed in the "
                                    "registry.")
        self.statusBar().showMessage("Settings saved", BRIEF_STATUS_MS)
        # Game folders changed (Phase 77): the watch already follows them (_arm_watcher above);
        # a folder added and not scanned is the question the user asks next, so scan now. A
        # folder taken out deletes nothing: its games are just not found by this scan.
        if [os.path.normcase(r) for r in values["roots"]] != [os.path.normcase(r) for r in roots_before]:
            log.info("game folders changed: %s -> %s; scanning", roots_before, values["roots"])
            self.start_scan(trigger="manual")
            self._update_empty_state()

    def reload_after_restore(self, message: str) -> None:
        """Pick up replaced files without a restart, after a restore or an import.

        Everything the window holds that came from those two files is rebuilt: the config,
        the overrides object itself (a fresh one, since the file underneath it changed
        wholesale), and every view. Nothing else in the app keeps its own copy -- each
        action reaches them through `window.overrides` -- so replacing it here is enough.
        """
        self.config = config_io.load_config()
        # The store the files were replaced under is let go of, and the library opened
        # afresh -- rebuilt from the JSON, if what came back was a snapshot from before the
        # switch (Phase 69).
        self.overrides.close()
        self.overrides = migration.open_library()
        catalog_io.relocate_artwork(self.overrides)  # a copy from before a move (Phase 37)
        self.reduce_animations = bool(
            self.config.get("reduce_animations", ui_rules.REDUCE_ANIMATIONS_DEFAULT)
        )
        self.scale = float(self.config.get("ui_scale", ui_rules.UI_SCALE_DEFAULT))
        self.accent = ui_theme.use_accent(self.config.get(ui_rules.ACCENT_KEY))  # the theme below repaints in it
        self.library.set_sort(str(self.config.get("library_sort", "")))
        self.library.set_genre(self.config.get(ui_rules.LIBRARY_GENRE_KEY))  # Phase 99: an unknown one is all
        self.library.set_filter(str(self.config.get("library_filter", "")))
        self.toast.reduce_animations = self.reduce_animations
        if hasattr(self, "rate_card"):
            self.rate_card.reduce_animations = self.reduce_animations
        # An import may have brought scan folders with it.
        self._arm_watcher()
        self.covers.clear()
        # set_tv_mode reapplies the theme and every metric, so it covers a scale change too.
        self.set_tv_mode(bool(self.config.get("tv_mode", ui_rules.TV_MODE_DEFAULT)))
        self.reload_views()
        log.info("reloaded after a restore: %s", message)
        self.queue_status("Library data reloaded", STATUS_MS)

    # -- controller ------------------------------------------------------------------------

    def _launcher_in_front(self) -> bool:
        """The pad's gate (Phase 7): is one of the launcher's own windows the active one?

        Not "is this window active" (Phase 52). Settings, a confirmation, the screenshot
        viewer are windows of their own, and Windows makes each the active window while it is
        open -- so asking only about this one dropped every press the moment Settings opened,
        and the pad could not reach the dialog it was meant to work (a menu never showed it:
        the window stays active under a menu). A game in front still answers no: then no
        window of this application is active at all.
        """
        return QApplication.activeWindow() is not None

    def _on_pad_action(self, name: str) -> None:
        """One place mapping pad actions onto whichever page is showing."""
        if (self.rate_card.showing and QApplication.activeModalWidget() is None
                and QApplication.activePopupWidget() is None):
            # How was it? (Phase 102): left and right along the stars, A rates, B skips; nothing else moves.
            if name in (controller.LEFT, controller.RIGHT):
                self.rate_card.step(-1 if name == controller.LEFT else 1)
            elif name == controller.ACTIVATE:
                self.rate_card.press()
            elif name == controller.BACK:
                self.rate_card.skip()
            return
        if self.splash.showing and QApplication.activeModalWidget() is None:
            # Starting... (Phase 99): B or A goes back; nothing behind the splash moves meanwhile.
            if name in (controller.BACK, controller.ACTIVATE):
                self.end_starting("B on the pad")
            return
        popup = QApplication.activePopupWidget()
        if popup is not None:
            # A menu opened with X. Until Phase 27 the pad's keys went to the grid behind
            # it, so the stick moved tiles under a menu nothing could steer or close. The
            # menu is what has the keyboard while it is open, so that is where they go now.
            # Checked before a dialog since Phase 35: a size drop-down opened inside
            # Settings is a popup on top of a modal, and it is the one being worked.
            self._drive_popup(popup, name)
            return

        modal = QApplication.activeModalWidget()
        if modal is not None:
            # A confirmation is up. It owns the pad while it is open, or the buttons behind
            # it would keep responding and the dialog would be unanswerable without a mouse.
            self._drive_dialog(modal, name)
            return

        on_detail = self.stack.currentIndex() == DETAIL_PAGE
        on_stats = self.stack.currentIndex() == STATS_PAGE

        on_storage = self.stack.currentIndex() == STORAGE_PAGE
        on_wishlist = self.stack.currentIndex() == WISHLIST_PAGE
        on_foryou = self.stack.currentIndex() == FORYOU_PAGE
        on_reports = self.stack.currentIndex() == REPORTS_PAGE

        # The stats page has nothing to select and nothing to navigate, so it takes only
        # two answers: leave, or scroll. Everything else would be a control that does
        # nothing, which is worse than one that is not offered. Left and right cross to
        # Storage, which is how that page is reachable at all -- every pad button was
        # already spoken for by Phase 23.
        # Reports (Phase 84) reads like Stats: nothing to select, so up and down scroll.
        if on_stats or on_reports:
            if name in (controller.BACK, controller.STATS):
                self.show_library()
            elif on_stats and name == controller.ACTIVATE:
                self.open_recap()  # the page's one control: the Recap card's Share as image... (Phase 96)
            elif name in (controller.LEFT, controller.RIGHT):
                self._cross(-1 if name == controller.LEFT else 1)
            elif name in (controller.UP, controller.DOWN, controller.PAGE_UP,
                          controller.PAGE_DOWN):
                self._scroll_stats(name, self.reports_page.scroll if on_reports else self.stats_page.scroll)
            elif name == controller.SETTINGS:
                self.open_settings()
            return

        # Storage does have rows, so up and down move the selection rather than scrolling
        # freely, and A opens the game that is selected.
        if on_storage:
            if name in (controller.BACK, controller.STATS):
                self.show_library()
            elif name in (controller.LEFT, controller.RIGHT):
                self._cross(-1 if name == controller.LEFT else 1)
            elif name == controller.ACTIVATE:
                self.storage_page.activate_current()
            elif name == controller.MENU:
                self.storage_page.context_for_current()
            elif name in STORAGE_KEYS:
                self.storage_page.move_focus(STORAGE_KEYS[name])
            elif name == controller.SETTINGS:
                self.open_settings()
            return

        # The Wishlist (Phase 87) has rows, as Storage does: up and down move, A opens the game's
        # store page, X its menu -- and Y, which plays something elsewhere, switches the two chips.
        # For you (Phase 98): its rows up and down, along a row left and right -- past either end, the next
        # place along the bar, as every tab crosses -- A plays, X the game's menu, Y Tonight's choice.
        if on_foryou:
            steps = {controller.UP: (0, -1), controller.DOWN: (0, 1), controller.LEFT: (-1, 0),
                     controller.RIGHT: (1, 0)}
            if name in (controller.BACK, controller.STATS):
                self.show_library()
            elif name in steps:
                if not self.foryou_page.move(*steps[name]) and name in (controller.LEFT, controller.RIGHT):
                    self._cross(-1 if name == controller.LEFT else 1)
                else:
                    self._refresh_hints()  # on an answer, A answers (Phase 103)
            elif name == controller.ACTIVATE:
                self.foryou_page.activate_current()
            elif name == controller.MENU:
                self.foryou_page.context_for_current()
            elif name == controller.SURPRISE:
                self.foryou_page.next_choice()
            elif name in (controller.PAGE_UP, controller.PAGE_DOWN):
                self._scroll_stats(name, self.foryou_page.scroll)
            elif name == controller.SETTINGS:
                self.open_settings()
            return

        if on_wishlist:
            if name in (controller.BACK, controller.STATS):
                self.show_library()
            elif name in (controller.LEFT, controller.RIGHT):
                self._cross(-1 if name == controller.LEFT else 1)
            elif name == controller.ACTIVATE:
                self.wishlist_page.activate_current()
            elif name == controller.MENU:
                self.wishlist_page.context_for_current()
            elif name == controller.SURPRISE:
                self.wishlist_page.toggle_choice()
            elif name in STORAGE_KEYS:
                self.wishlist_page.move_focus(STORAGE_KEYS[name])
            elif name == controller.SETTINGS:
                self.open_settings()
            return

        # The screenshot viewer is modal, so it owns the pad while it is open: Back closes
        # it, left/right move through the shots, and nothing reaches the page behind.
        if on_detail and self.detail.viewer_open:
            if name == controller.BACK:
                self.detail.close_viewer()
            elif name in (controller.LEFT, controller.RIGHT):
                self.detail.viewer_step(-1 if name == controller.LEFT else 1)
            return

        if name == controller.SETTINGS:
            self.open_settings()
        elif name == controller.BACK:
            if on_detail:
                self.show_library()
            elif self.tv_mode:
                self.set_tv_mode(False)
        elif name == controller.MENU:
            if on_detail and self.detail.view is not None:
                # Under the page's "..." button, where the same menu opens for the mouse.
                self._context_menu(self.detail.view.key, self.detail.menu_position())
            else:
                self.library.context_for_current()
        elif name == controller.STATS:
            self.show_stats()
        elif name == controller.SURPRISE:
            self.play_something()
        elif name == controller.ACTIVATE:
            if on_detail:
                self.detail.play_button.click()
            else:
                self.library.activate_current()
        elif on_detail and name in (controller.LEFT, controller.RIGHT):
            self._step(-1 if name == controller.LEFT else 1)
        elif on_detail and name in (controller.UP, controller.DOWN, controller.PAGE_UP,
                                    controller.PAGE_DOWN):
            # The page is longer than the screen now; up and down read down it.
            self.detail.scroll_by(name)
        elif not on_detail:
            self.library.move_focus(name)

    def _scroll_stats(self, name: str, scroll=None) -> None:
        bar = (scroll or self.stats_page.scroll).verticalScrollBar()
        if name == controller.UP:
            bar.setValue(bar.value() - bar.singleStep() * ui_rules.PAD_SCROLL_STEPS)
        elif name == controller.DOWN:
            bar.setValue(bar.value() + bar.singleStep() * ui_rules.PAD_SCROLL_STEPS)
        elif name == controller.PAGE_UP:
            bar.setValue(bar.value() - bar.pageStep())
        else:
            bar.setValue(bar.value() + bar.pageStep())

    # -- TV mode ---------------------------------------------------------------------------

    def apply_accent(self, name) -> str:
        """The accent switched while the launcher runs (Phase 99): ui_rules' accent family set, the stylesheet
        rebuilt, every page's metrics put again -- the icons and pixmaps painted once in the accent are painted
        then -- and everything repainted. A game's own colour and its art's glow are untouched. Saved by
        Settings' OK, not here: a swatch only shows itself until then."""
        used = ui_theme.use_accent(name)
        self.accent = used
        self._apply_theme()
        self.library.apply_metrics(self.metrics, self.reduce_animations)
        for page in (self.detail, self.stats_page, self.storage_page, self.reports_page, self.wishlist_page,
                     self.foryou_page):
            page.apply_metrics(self.metrics)
        self.hint_bar.apply_metrics(self.metrics)
        self.toast.apply_scale(self.scale)
        self.rate_card.apply_scale(self.scale)
        for widget in (self, *self.findChildren(QWidget)):
            widget.update()
        for top in QApplication.topLevelWidgets():  # a dialog open over the window -- Settings itself
            if top is not self and top.isVisible():
                for widget in (top, *top.findChildren(QWidget)):
                    widget.update()
        log.info("accent: %s", used)
        return used

    def set_tv_mode(self, enabled: bool) -> None:
        # Everything is about to be re-sized; nothing in flight survives that sensibly.
        self.page_motion.cancel()
        self.flight.cancel()
        self.end_starting("the window changed size")
        if enabled and not self.isFullScreen():
            self._normal_geometry = self.saveGeometry()
        self.tv_mode = enabled
        self.config["tv_mode"] = enabled
        self.scale = float(
            self.config.get("tv_scale", ui_rules.TV_SCALE_DEFAULT)
            if enabled
            else self.config.get("ui_scale", ui_rules.UI_SCALE_DEFAULT)
        )
        self.metrics = ui_theme.Metrics(self.scale)
        self.library.focus_ring_width = (
            ui_rules.TV_FOCUS_RING_WIDTH if enabled else ui_rules.FOCUS_RING_WIDTH
        )

        self._apply_theme()
        self.covers.clear()
        self.backdrop.cover_size = (self.metrics.cover_width, self.metrics.cover_height)
        self.backdrop.reduce_animations = self.reduce_animations
        self.library.apply_metrics(self.metrics, self.reduce_animations)
        self.detail.apply_metrics(self.metrics)
        self.stats_page.apply_metrics(self.metrics)
        self.storage_page.apply_metrics(self.metrics)
        self.reports_page.apply_metrics(self.metrics)
        self.wishlist_page.apply_metrics(self.metrics)
        self.foryou_page.apply_metrics(self.metrics)
        self.wishlist_page.focus_ring_width = self.library.focus_ring_width
        self.storage_page.focus_ring_width = self.library.focus_ring_width
        self.detail.focus_ring_width = self.library.focus_ring_width
        # The treemap is mouse-only and has no pad path, so it is not shown on a screen
        # being driven from a couch -- where it would only take room from the ranked list.
        self.storage_page.show_treemap = not enabled
        if self.storage_page.storage is not None:
            self.storage_page.set_storage(self.storage_page.storage)
        self._apply_layout()
        self.hint_bar.apply_metrics(self.metrics)
        self.hint_bar.setVisible(enabled)
        # The status bar stays hidden in both modes now; its messages float as a card, which
        # in TV mode sits above the button-hint bar instead of being lost behind it.
        self.toast.apply_scale(self.scale)
        self.toast.set_bottom_reserve(self.hint_bar.sizeHint().height() if enabled else 0)
        self.rate_card.apply_scale(self.scale)
        self.rate_card.set_bottom_reserve(self.hint_bar.sizeHint().height() if enabled else 0)

        # Re-read the level as the bar appears. The background poll is a minute apart, so a
        # pad unplugged in the meantime would otherwise show a stale glyph for that long at
        # the exact moment it becomes visible. Guarded because TV mode can be applied from
        # --tv before the hub is built.
        if enabled and getattr(self, "pads", None) is not None:
            self.pads.refresh_power()

        if enabled and self._in_tray:
            # Settings' OK from the tray menu (Phase 92): the window takes TV mode's state for
            # when it is brought back, and stays where it is -- hidden.
            self.setWindowState(self.windowState() | Qt.WindowState.WindowFullScreen)
        elif enabled:
            self.showFullScreen()
            self.library.ensure_focus()
        elif self.isFullScreen():
            # Back from TV mode to the window as it was before it -- maximised, if it was.
            # showNormal() first: restoring a maximised window's geometry onto a fullscreen
            # one would keep it fullscreen. In the tray, the state alone, not shown.
            if self._in_tray:
                self.setWindowState(self.windowState() & ~Qt.WindowState.WindowFullScreen)
            else:
                self.showNormal()
            if self._normal_geometry is not None:
                self.restoreGeometry(self._normal_geometry)
        # Otherwise the window is left exactly as it is (Phase 72, reported from use):
        # Settings' OK re-applies the mode the window is already in, and showNormal() here
        # unmaximised a maximised window every time.
        log.info("TV mode %s", "on" if enabled else "off")

    # -- scanning ------------------------------------------------------------------------

    def start_scan(self, quiet: bool = False, background: bool = False, trigger: str | None = None) -> bool:
        """Run one discovery pass. Returns False if one was already running.

        `quiet` is for the pass that runs on its own at startup: it says nothing while it
        works, because the status bar belongs to the removed-games notice and the
        controller announcement at that moment. The disabled Rescan button is the visible
        sign that something is happening, and the result goes through the queue.

        `background` is for a pass nobody asked for at all -- the folder watch's. It says
        nothing unless the library actually changed.

        `trigger` says who asked, for the scan's row in the database (Phase 69): the first
        run, the startup pass, the Rescan button, the folder watch, an uninstall.

        While missing covers are being filled (Phase 105) it is held back, as a game holds the
        folder watch's, and runs once they are.
        """
        if self._filling:
            self._held_scan = {"quiet": quiet, "background": background, "trigger": trigger}
            log.info("holding a scan (%s) until the missing covers are filled",
                     trigger or ("watch" if background else "startup" if quiet else "manual"))
            return False
        if self.worker is not None and self.worker.isRunning():
            log.info("a scan is already running; ignoring the request for another")
            return False
        self._scan_trigger = trigger or ("watch" if background else "startup" if quiet else "manual")
        self._last_scan_began = time.time()
        self._steam_played_since_scan = False  # this scan reads Steam's files
        self._scan_started = datetime.now().astimezone().isoformat(timespec="seconds")
        self.scan_was_quiet = quiet or background
        self.scan_was_background = background
        self.library.rescan_button.setEnabled(False)
        if not self.scan_was_quiet:
            self.statusBar().showMessage("Scanning...")
        config = config_io.load_config()
        # The prices due this week, worked out here on the GUI thread and handed to the scan as
        # an argument (Phase 73): the database is never read from the scan thread, and a value
        # that only lives for one scan has no business in config.json.
        online = bool(config.get("allow_network", rules.ALLOW_NETWORK_DEFAULT))
        due = prices.due(self.overrides, online)
        # Steam's own playtime (Phase 75): its files are read with every window scan the library
        # can keep them for -- local files, so with the network off too -- and the records of the
        # accounts marked mine that have none are fetched, a few a scan, only with it on.
        # The wishlists (Phase 86): each account marked mine read once a day, with the network on.
        self.worker = ScanWorker(config, self, prices_due=due, read_steam=steam_time.due(self.overrides),
                                 steam_records=steam_time.wanted(self.overrides, online),
                                 wishlists=wishlist.due(self.overrides, online))
        if not self.scan_was_quiet:
            self.worker.progress.connect(lambda text: self.statusBar().showMessage(text))
        self.worker.scanned.connect(self._on_scanned)
        self.worker.failed.connect(self._on_failed)
        self.worker.finished.connect(self._scan_thread_done)
        self.worker.start()
        self._update_empty_state()  # an empty library says it is looking (Phase 77)
        return True

    def _scan_thread_done(self) -> None:
        # finished() arrives a hair before the thread has actually ended, and a scan the
        # folder watch asked for in the meantime must not be refused as "already running".
        if self.worker is not None:
            self.worker.wait()
        self.library.rescan_button.setEnabled(True)
        self._run_wanted_scan()
        self._update_empty_state()

    # -- the folder watch ------------------------------------------------------------------

    def _arm_watcher(self) -> None:
        if self.config.get("watch_folders", rules.WATCH_FOLDERS_DEFAULT):
            # Only the folders the scan looks in: a whole drive is never watched either (Phase 82).
            self.watcher.watch(drives.split_roots(self.config.get("roots", rules.DEFAULT_ROOTS))[0])
        else:
            self.watcher.watch(())

    def _watch_wants_scan(self, reason: str) -> None:
        log.info("the folder watch asked for a scan (%s)", reason)
        self._scan_wanted = True
        self._run_wanted_scan()

    def _run_wanted_scan(self) -> None:
        """Run a scan the folder watch asked for, as soon as nothing stands in its way.

        Never while a game started from here is running: a scan walks the disk the game is
        streaming from, and a stutter mid-game is not worth a tile appearing a few minutes
        sooner. It runs when the game closes instead, or after a scan already under way,
        since that one may have started before the folder had finished arriving.
        """
        if not self._scan_wanted:
            return
        if self.game_running():
            log.info("holding the folder watch's scan until the game closes")
            return
        if self.worker is not None and self.worker.isRunning():
            return  # _scan_thread_done calls back here
        self._scan_wanted = False
        self.start_scan(background=True)

    def _startup_scan(self) -> None:
        """The pass that runs on its own, once, shortly after the window appears."""
        if self.first_run or self._first_run_asked:
            # Asked, or about to be: the answer's own scan is this session's first look, and a
            # second one a second later would find the same games again.
            log.info("startup scan skipped: the first-run question's own scan stands in for it")
            return
        if not self.config.get("startup_scan", rules.STARTUP_SCAN_DEFAULT):
            log.info("startup scan is switched off")
            return
        if not self.start_scan(quiet=True):
            log.info("startup scan skipped: the no-catalog scan is already running")

    def _on_scanned(self, entries: list) -> None:
        before = len(self.entries)
        # Which games the launcher already knew, taken before this scan's merge stamps the
        # rest. Anything outside it is new, and is named in the message below.
        known = {key for key, seen in self.overrides.values_of("first_seen").items() if seen}
        unchanged = _same_entries(self.entries, entries)
        self.entries = entries
        self.overrides.save_catalog(entries, roots=config_io.load_config().get("roots", ()),
                                    trigger=getattr(self, "_scan_trigger", "manual"),
                                    started_at=getattr(self, "_scan_started", None))
        # The database's Steam tables follow the records the scan may have fetched (Phase 70),
        # and the prices it observed land in the series after them (Phase 73).
        steam_projection.refresh(self.overrides)
        landed_prices = prices.land(self.overrides)
        steam_time.land(self.overrides)  # Phase 75: after the projection, which named any record fetched
        wishlist.land(self.overrides)  # Phase 86: the lists read with this scan
        self._price_alerts(landed_prices.fresh)  # Phase 101: after the prices and the lists have landed
        self._follow_steam_times()  # Phase 76: the hours on the tiles and the page, if they moved
        gamedetails.forget()  # a scan may have fetched records that were missing before
        if not unchanged:
            # Only rebuilt when something changed. A scan the folder watch asked for can
            # land while you are reading a game's page or halfway down the grid, and
            # rebuilding everything for nothing would throw both back to the start.
            self.covers.clear()
            self.reload_views()

        # On a first run nothing is known, and naming every game in the library as "new"
        # would say nothing -- the same rule the NEW tag follows.
        arrivals = [
            view for view in self.views
            if known and view.key not in known and not view.hidden and not view.is_non_game
        ]
        news = _arrivals_text(arrivals)
        if any(self.earlier_offers(view) for view in arrivals):
            news += " -- it looks like a new version of a game you had; its page can carry your progress over"
        if not self.scan_was_quiet:
            found = f"Found {len(entries)} games"
            self.statusBar().showMessage(f"{found}. {news}" if news else found, STATUS_MS)
        elif news:
            self.queue_status(news, NEW_STATUS_MS)
        elif len(entries) != before:
            self.queue_status(f"Library updated: {len(entries)} games, was {before}", STATUS_MS)
        elif not self.scan_was_background:
            self.queue_status(f"Library up to date: {len(entries)} games", STATUS_MS)

    def _on_failed(self, message: str) -> None:
        self.statusBar().showMessage("Scan failed", STATUS_MS)
        QMessageBox.critical(self, "Scan failed", message)

    # -- playtime ------------------------------------------------------------------------

    def _poll_playtime(self) -> None:
        """Collect elapsed time from every running game, and bank it now and then.

        Banked rather than written on every poll: the poll runs every few seconds because
        its other job is noticing that a game has closed, and rewriting overrides.json --
        and repainting the grid -- at that rate for hours would be absurd. A session that
        ends is always written straight away, so only a live session can lose anything,
        and never more than one interval of it.
        """
        ticks = self.tracker.poll()
        if not ticks:
            return
        known = set(self._live_sessions)
        for tick in ticks:
            # What the total still lacks is the session's length, measured from its start,
            # less what is already banked (Phase 53). It used to be a sum of each tick's whole
            # seconds, and every tick dropped its fraction: the timer fires a hair either side
            # of 3 s, so about half the ticks counted 2 -- 15-16% of every session, lost.
            # Now total = total at the session's start + its elapsed time, rounded once -- less
            # any sleep, which the tracker counts as a few seconds at most (Phase 94).
            self._unbanked[tick.key] = tick.total_seconds - self._banked.get(tick.key, 0)
            if tick.started_at is not None:
                # The whole session so far, not the increment: the entry is rewritten in
                # place each time, so it has to carry the running total.
                self._live_sessions[tick.key] = (tick.started_at, tick.total_seconds)

        ended = [tick for tick in ticks if tick.finished]
        due = time.monotonic() - self._last_banked >= rules.PLAYTIME_WRITE_INTERVAL_S
        if ended or due:
            self._bank_playtime()
        finished: list[tuple] = []  # (key, its session's start, minutes): what "How was it?" may ask about
        for tick in ended:
            if self.is_starting(tick.key):
                self.end_starting("the game closed")
            live = self._live_sessions.get(tick.key)
            if live is not None:
                finished.append((tick.key, rate.started_text(live[0]), live[1] // 60))
            self._live_sessions.pop(tick.key, None)
            self._banked.pop(tick.key, None)
            self._queue_after_session(tick)
        if ended or any(tick.key not in known for tick in ticks):
            self._update_tray_tooltip()  # a session began or ended; otherwise once a minute, below
        self.refresh_running_state()
        if ended:
            self._come_back_to_front()
            if not self.game_running():
                self._run_wanted_scan()  # held back while the game was up
                self._run_saves()
            for key, started, minutes in finished[-1:]:  # one question, for the session that ended last
                view = self.by_key.get(key)
                self._ask_rating(key, view.display_name if view else key, started, minutes)

    def _bank_playtime(self) -> None:
        """Add the time collected so far onto each game's total, and save."""
        self._last_banked = time.monotonic()
        pending = {key: seconds for key, seconds in self._unbanked.items() if seconds}
        self._unbanked.clear()
        self._update_tray_tooltip()  # "Playing ... for 1h 12m", on the banking cadence (Phase 92)
        if not pending:
            return
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        for key, seconds in pending.items():
            record = self.overrides.get(key)
            # Added, not set to start + elapsed: anything else that adds to this game's time
            # while it runs -- carrying over an earlier install -- must not be written over.
            total = int(record.get("playtime_seconds", 0)) + seconds
            self._banked[key] = self._banked.get(key, 0) + seconds
            values = {"playtime_seconds": total, "last_played": now}
            values.update(self._session_update(key, record))
            self.overrides.update(key, **values)
            log.info("banked %ds for %s", seconds, key)
        self.reload_views()

    def _session_update(self, key: str, record: dict) -> dict:
        """The `sessions` value to write for this game, or nothing to leave it alone.

        The live session is rewritten in place on every banking pass rather than appended
        once at the end, so a crash costs at most one interval of it -- the same promise
        playtime makes, and the reason both are banked together.
        """
        live = self._live_sessions.get(key)
        if live is None:
            return {}
        started_at, total_seconds = live
        minutes = total_seconds // 60
        if minutes < rules.SESSION_MIN_MINUTES:
            return {}  # too short to be worth a line in the list
        entries = sessions.prune(sessions.upsert(sessions.load(record), started_at, minutes))
        return {rules.SESSIONS_KEY: sessions.dump(entries)}

    DIALOG_KEYS = {
        controller.ACTIVATE: Qt.Key.Key_Return,
        controller.BACK: Qt.Key.Key_Escape,
        controller.LEFT: Qt.Key.Key_Backtab,
        controller.RIGHT: Qt.Key.Key_Tab,
        controller.UP: Qt.Key.Key_Backtab,
        controller.DOWN: Qt.Key.Key_Tab,
    }

    def _drive_dialog(self, dialog, name: str) -> None:
        """Let the pad work a dialog: move between its controls, use them, or cancel."""
        key = self.DIALOG_KEYS.get(name)
        if key is None:
            return
        target = dialog.focusWidget() or dialog
        if isinstance(target, QTextBrowser) and name == controller.ACTIVATE:
            # Words to read (What's new, Phase 106): A presses the dialog's default button, Close.
            target = dialog
        elif isinstance(target, QTextBrowser) and name in (controller.UP, controller.DOWN):
            # Up and down scroll the words; at either end they go on to the control before or after, as a list's do.
            bar = target.verticalScrollBar()
            before = bar.value()
            step = max(bar.singleStep(), bar.pageStep() // 2)
            bar.setValue(before - step if name == controller.UP else before + step)
            if bar.value() != before:
                return
            key = Qt.Key.Key_Backtab if name == controller.UP else Qt.Key.Key_Tab
        elif isinstance(target, QAbstractItemView) and name in (controller.UP, controller.DOWN):
            # A list in a dialog -- which copy of the saves, which backup, which folders -- is
            # chosen by moving through it. Tab would only ever have jumped past it to the buttons.
            # At either end (or in an empty list) the move goes on to the control before or
            # after it (Phase 77): a list the pad could enter and never leave was a trap.
            before = target.currentIndex()
            arrow = Qt.Key.Key_Up if name == controller.UP else Qt.Key.Key_Down
            for event_type in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
                QApplication.sendEvent(target, QKeyEvent(event_type, arrow, Qt.KeyboardModifier.NoModifier))
            if target.currentIndex() != before:
                return
            key = Qt.Key.Key_Backtab if name == controller.UP else Qt.Key.Key_Tab
        elif (name == controller.ACTIVATE and isinstance(target, QAbstractItemView)
              and target.property("padActivate") == "select"):
            # A list of folders (Phase 77): A ticks or unticks the one it is on. Return would
            # have pressed the dialog's default button -- Continue, or OK -- from inside the list.
            key = Qt.Key.Key_Space
        elif name == controller.ACTIVATE and isinstance(target, QComboBox) and target.isEditable():
            # A box you can also type in -- the store, in What I paid (Phase 74): Space would type
            # a space into it, so A opens its list of suggestions instead.
            target.showPopup()
            return
        elif name == controller.ACTIVATE and isinstance(target, (QAbstractButton, QComboBox)):
            # A presses what it is on (Phase 35). Return pressed the dialog's default button
            # instead, so in Settings A closed the dialog rather than flipping the switch
            # under it. Space flips a switch, presses a button, and opens a drop-down.
            key = Qt.Key.Key_Space
        elif isinstance(target, QComboBox) and name in (controller.LEFT, controller.RIGHT):
            # Left and right change a size in place, without opening the list.
            key = Qt.Key.Key_Up if name == controller.LEFT else Qt.Key.Key_Down
        elif isinstance(target, QAbstractSpinBox) and name in (controller.LEFT, controller.RIGHT):
            # An amount or a date (What I paid, Phase 74): left and right step it down and up.
            key = Qt.Key.Key_Down if name == controller.LEFT else Qt.Key.Key_Up
        elif (isinstance(target, QAbstractButton) and target.group() is not None
              and name in (controller.LEFT, controller.RIGHT)):
            # One of a row of choices -- whose a Steam account is, in Settings (Phase 75): left and
            # right move the choice along the row, as they change a size. Tab would leave the row,
            # which Qt treats as one stop.
            key = Qt.Key.Key_Left if name == controller.LEFT else Qt.Key.Key_Right
        for event_type in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            QApplication.sendEvent(
                target, QKeyEvent(event_type, key, Qt.KeyboardModifier.NoModifier)
            )

    # Qt's menus already answer these keys: arrows move and open or close submenus,
    # Return picks, Escape backs out one level. X closes, like pressing it again would.
    POPUP_KEYS = {
        controller.UP: Qt.Key.Key_Up,
        controller.DOWN: Qt.Key.Key_Down,
        controller.LEFT: Qt.Key.Key_Left,
        controller.RIGHT: Qt.Key.Key_Right,
        controller.ACTIVATE: Qt.Key.Key_Return,
        controller.BACK: Qt.Key.Key_Escape,
        controller.MENU: Qt.Key.Key_Escape,
    }

    def _drive_popup(self, popup, name: str) -> None:
        """Let the pad work an open menu, including its submenus -- or a drop-down's list,
        whose keys go to the list inside it rather than the frame around it."""
        popup = popup.focusWidget() or popup
        key = self.POPUP_KEYS.get(name)
        if key is None:
            return
        for event_type in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            QApplication.sendEvent(popup, QKeyEvent(event_type, key, Qt.KeyboardModifier.NoModifier))

    def _come_back_to_front(self) -> None:
        """Return to the foreground after a game we launched has exited.

        In TV mode, always: on a couch there is no mouse to click the taskbar with, and a
        button that only flashes is a dead end. At a desk, only when nothing else has the
        foreground -- the game closed onto the bare desktop -- so a window you moved to
        while the game ran is never snatched from under you. Otherwise the polite request,
        which Windows answers on this machine by flashing the taskbar button.

        Nothing at all while another game started from here is still running.
        See focus.py for why the polite request alone never worked here.
        """
        if self.game_running():
            return  # another game is up, launched or observed: the screen is the game's
        if self._in_tray:
            # Started from the tray menu with the window hidden, or hidden while the game ran
            # (Phase 92): closing the window was the user's word, and the game ending does not
            # take it back. The tooltip has already gone back to "Game Launcher".
            log.info("the game ended with the launcher in the tray; the window stays hidden")
            return
        try:
            if self.tv_mode or focus.foreground_is_empty():
                if self.isMinimized():
                    # Restored into whichever state it was minimised from -- fullscreen,
                    # maximised or a window -- not flattened to a window: Windows keeps that
                    # state under the minimised flag (Phase 72; showNormal() unmaximised).
                    self.setWindowState((self.windowState() & ~Qt.WindowState.WindowMinimized)
                                        | Qt.WindowState.WindowActive)
                    if self.tv_mode and not self.isFullScreen():
                        self.showFullScreen()
                won = focus.bring_to_front(int(self.winId()))
                log.info("back to the front after the game: %s", "yes" if won else "no")
                if won:
                    self.library.ensure_focus()
                    return
            self.raise_()
            self.activateWindow()
            self.library.ensure_focus()
        except Exception as exc:
            log.warning("could not come back to the front: %s", exc)

    def keyPressEvent(self, event) -> None:
        # Escape always leaves fullscreen. Without this, a TV-mode window with no pad
        # attached has no obvious way out.
        if event.key() == Qt.Key.Key_Escape and self.tv_mode:
            self.set_tv_mode(False)
            event.accept()
            return
        super().keyPressEvent(event)

    # -- saves: where each game keeps them, and copies of them (Phase 29) --------------------

    def backups_on(self) -> bool:
        return bool(self.config.get("backup_saves", rules.SAVES_BACKUP_DEFAULT))

    def save_job(self, view, *, reason: str, extra_window=None, back_up=None) -> Job | None:
        """What to look for, for one game -- or None when there is nothing to go on.

        Only exe games: a Steam, Epic or Xbox game's client keeps its saves in the cloud, and the
        search matches writes against the sessions of a game this launcher can start by its exe.
        """
        if view.entry.launch_kind != "exe":
            return None
        record = self.overrides.get(view.key)
        windows = saves_module.session_windows(record)
        if extra_window is not None:
            windows = sorted(windows + [extra_window])
        if not windows:
            return None
        return Job(
            key=view.key,
            name=view.display_name,
            appid=view.matched_appid,
            install_dir=view.entry.install_dir,
            windows=windows,
            known=list(record.get(rules.SAVE_DIRS_KEY) or []),
            ignored=tuple(record.get(rules.SAVE_DIRS_IGNORED_KEY) or []),
            back_up=self.backups_on() if back_up is None else back_up,
            reason=reason,
        )

    def other_game_names(self) -> tuple[str, ...]:
        """Every game the launcher knows by name -- installed or not -- for telling saves apart."""
        names = {view.display_name for view in self.views}
        # Not one carried over: that is an older name of a game that is showing (Phase 36).
        for key, _record in self.overrides.uncarried():
            if key in self.by_key or not os.path.isabs(key):
                continue  # showing already, or a "steam:730"-style key with no folder name
            names.add(naming.clean_folder_name(os.path.basename(key.rstrip("\\/"))))
        return tuple(sorted(n for n in names if n))

    def _queue_after_session(self, tick) -> None:
        view = self.by_key.get(tick.key)
        if view is None:
            return
        window = None
        if tick.started_at is not None:
            # This session may be under a minute and so not in the recorded history.
            window = (tick.started_at.timestamp(), time.time() + rules.SAVES_SESSION_SLACK_S)
        job = self.save_job(view, reason="after playing", extra_window=window)
        if job is not None:
            self._save_jobs.append(job)

    def _startup_saves(self) -> None:
        """Once per game, ever: look through what it wrote in the sessions already recorded."""
        jobs = []
        for view in self.views:
            if self.overrides.get(view.key).get(rules.SAVE_DIRS_CHECKED_KEY):
                continue
            job = self.save_job(view, reason="first look")
            if job is not None:
                jobs.append(job)
        if jobs:
            log.info("looking for the saves of %d game(s) for the first time", len(jobs))
            self._save_jobs.extend(jobs)
            self._run_saves()

    def _run_saves(self) -> None:
        """Start the queued save work, unless a game is running or the work already is."""
        if not self._save_jobs:
            return
        if self.game_running():
            return  # the disk belongs to the game; _poll_playtime or _on_seen calls back when it closes
        if self.save_worker is not None and self.save_worker.isRunning():
            return  # _saves_done calls back
        latest: dict[str, Job] = {}
        for job in self._save_jobs:  # one job per game; the newest request carries most
            latest[job.key] = job
        self._save_jobs = []
        self.save_worker = SaveWorker(list(latest.values()), self.other_game_names(), self)
        self.save_worker.finishedJobs.connect(self._saves_done)
        self.save_worker.start()

    def record_saves(self, outcomes: list) -> None:
        """Write what a save job found into overrides.json -- the one place that happens."""
        stamp = datetime.now().astimezone().isoformat(timespec="seconds")
        for outcome in outcomes:
            record = self.overrides.get(outcome.key)
            values = {rules.SAVE_DIRS_CHECKED_KEY: stamp}
            if (record.get(rules.SAVE_DIRS_KEY) or []) != outcome.folders:
                values[rules.SAVE_DIRS_KEY] = outcome.folders or None
            self.overrides.update(outcome.key, **values)
        showing = self.detail.view
        if showing is not None and any(o.key == showing.key for o in outcomes):
            self.detail.set_view(self.by_key.get(showing.key, showing))

    def _saves_done(self, outcomes: list) -> None:
        if self.save_worker is not None:
            self.save_worker.wait()
        self.record_saves(outcomes)
        copied = [o for o in outcomes if o.backup is not None and o.backup.made]
        failed = [o for o in outcomes if o.backup is not None and o.backup.error]
        if failed:
            names = ", ".join(self.by_key[o.key].display_name for o in failed if o.key in self.by_key)
            self.queue_status(f"Could not copy the saves of {names} -- see launcher.log",
                              NEW_STATUS_MS)
        elif len(copied) == 1 and copied[0].key in self.by_key:
            self.queue_status(f"Saves of {self.by_key[copied[0].key].display_name} copied",
                              BRIEF_STATUS_MS)
        elif copied:
            self.queue_status(f"Saves of {len(copied)} games copied", STATUS_MS)
        self._run_saves()

    def back_up_now(self, view) -> None:
        """The menu's "Back up saves now": done in front of you, with an answer either way."""
        job = self.save_job(view, reason="by hand", back_up=True)
        if job is None:
            self.statusBar().showMessage(
                "Play it from here once first -- that is how the launcher learns where it saves",
                STATUS_MS,
            )
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            outcomes = run_jobs([job], self.other_game_names())
        finally:
            QApplication.restoreOverrideCursor()
        self.record_saves(outcomes)
        outcome = outcomes[0] if outcomes else None
        result = outcome.backup if outcome else None
        if outcome is None or not outcome.folders:
            text = f"No saves found for {view.display_name} yet"
        elif result is not None and result.error:
            text = f"Could not copy the saves: {result.error}"
        elif result is not None and result.skipped_unchanged:
            text = f"{view.display_name}'s saves have not changed since the last copy"
        else:
            text = f"Saves of {view.display_name} copied"
        self.statusBar().showMessage(text, STATUS_MS)

    # -- the window's own size and place ----------------------------------------------------

    def _restore_geometry(self) -> None:
        """Put the window back where it was left, at the size it was left.

        Qt's own saved form rather than four numbers: it carries the maximised state, and
        on the way back in it pulls a window left on a screen that is no longer attached --
        the TV, unplugged -- onto one that is.
        """
        saved = self.config.get("window_geometry")
        if not isinstance(saved, str) or not saved:
            return
        blob = QByteArray.fromBase64(saved.encode("ascii", "ignore"))
        if not self.restoreGeometry(blob):
            log.warning("the saved window position could not be used; opening at the default")

    def _save_geometry(self) -> None:
        """Remember the ordinary window for next time -- never TV mode's fullscreen."""
        if not self._shown:
            return  # never on screen, so there is nothing of the user's to keep
        blob = self._normal_geometry if self.tv_mode else self.saveGeometry()
        if blob is None or blob.isEmpty():
            return
        text = bytes(blob.toBase64()).decode("ascii")
        if text == self.config.get("window_geometry"):
            return  # unchanged: config.json, and the next backup, are left alone
        self.config["window_geometry"] = text
        config_io.save_config({"window_geometry": text})

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        toast = getattr(self, "toast", None)  # a resize can arrive before _build has run
        if toast is not None:
            toast.reposition()
        card = getattr(self, "rate_card", None)
        if card is not None and card.isVisible():
            card.reposition()
        # A picture taken at the old size would slide in wrong: finish any motion at once.
        for motion in (getattr(self, "page_motion", None), getattr(self, "flight", None)):
            if motion is not None:
                motion.cancel()

    def _follow_density(self, *_args) -> None:
        """Make covers at the density of the screen the window is on (Phase 35).

        Called when the window appears and whenever it moves to another screen -- the desk
        monitor at 100%, the TV at 225% -- so what is drawn there is drawn one to one.
        """
        ratio = self.devicePixelRatioF() or 1.0
        if abs(ratio - self.covers.ratio) < 0.01:
            return
        log.info("screen density %.2f; remaking covers for it", ratio)
        self.covers.ratio = ratio
        self.covers.clear()
        self.library.repaint_tiles()
        self.detail.banner.update()
        self.detail.cover_art.update()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._shown = True
        self._follow_density()
        handle = self.windowHandle()
        if handle is not None and not getattr(self, "_density_hooked", False):
            handle.screenChanged.connect(self._follow_density)
            self._density_hooked = True
        if not getattr(self, "_hints_hooked", False):
            # A dialog opening or closing moves the focus: the hints follow it.
            QApplication.instance().focusChanged.connect(self._refresh_hints)
            self._hints_hooked = True
        # Done here rather than once at startup because the handle has to exist, and because
        # anything that makes Qt rebuild the native window would drop the properties.
        if not self._tagged:
            self._tagged = taskbar.tag_window(int(self.winId()))

        # A fresh install asks where the games are first (Phase 77) -- once the window is on
        # screen, so the question sits over the launcher rather than appearing on its own.
        if self.first_run and not self._first_run_asked:
            QTimer.singleShot(0, self._ask_where_games_are)
        if self._whats_new and not self._whats_new_scheduled:
            # An update's notes (Phase 106), a second after the window appears. The tray offer is not queued beside
            # them: their closing queues it, so two dialogs never stand one over the other.
            self._whats_new_scheduled = True
            self._offer_scheduled = True
            QTimer.singleShot(rules.WHATS_NEW_DELAY_MS, self.show_whats_new)
        if not self._offer_scheduled:
            # The one question (Phase 99): a second after the first paint, so the launcher is there behind it.
            self._offer_scheduled = True
            QTimer.singleShot(rules.TRAY_OFFER_DELAY_MS, self.offer_tray)
        self.begin()
        # The library's first appearance: the tiles arrive as a wave (Phase 34), once.
        if not self._entrance_played:
            self._entrance_played = True
            if self.stack.currentIndex() == LIBRARY_PAGE and not self.reduce_animations:
                self.library.play_entrance()

    # -- games started outside the launcher (Phase 93) -------------------------------------------

    def game_running(self) -> bool:
        """A game is up -- one the launcher started, or one it sees running. Scans, the saves search
        and coming back to the front all wait for it."""
        return bool(self.tracker.running) or bool(self.observer.live)

    def observed_running(self, key: str) -> bool:
        """Is this game seen running in the process list now (Phase 93)?"""
        return key in self.observer.running()

    def watch_on(self) -> bool:
        return (bool(self.config.get(rules.WATCH_GAMES_KEY, rules.WATCH_GAMES_DEFAULT))
                and bool(getattr(self.overrides, "keeps_observed", False)))

    def _refresh_watched(self) -> None:
        """The games whose processes are looked for, rebuilt with the views: a game installed today is
        watched from today, a game marked a tool stops being watched at once."""
        roots = self.config.get("roots", rules.DEFAULT_ROOTS)
        games = observe.watched_games(self.views, roots)
        self._watched = {game.key: game for game in games}
        if self.process_worker is not None:
            self.process_worker.set_games(games)

    def _apply_watch(self) -> None:
        """The look at the process list on exactly while it is wanted -- the switch on, a library that
        keeps a session's origin -- and off at once otherwise."""
        if not self.watch_on():
            self._stop_watch()
            return
        if self.process_worker is not None and self.process_worker.isRunning():
            return
        self.process_worker = ProcessWorker(self)
        self.process_worker.set_games(self._watched.values())
        self.process_worker.seen.connect(self._on_seen)
        self.process_worker.start()

    def _stop_watch(self) -> None:
        worker = self.process_worker
        if worker is None:
            return
        self.process_worker = None
        worker.requestInterruption()
        worker.wait((rules.WATCH_PROCESS_POLL_S + 2) * 1000)
        for seen in self.observer.end_all():  # what was seen, kept: it ends at its last sighting
            self._bank_observed(seen, final=True)

    def _on_seen(self, keys: list, now: float) -> None:
        """One look's answer, on the GUI thread: open, extend and end the observed sessions."""
        if self.process_worker is None:
            return  # the watch was stopped after this look was taken
        before = set(self.observer.live)
        ended = self.observer.feed(set(keys), self._watched, self.tracker.active_keys, now,
                                   datetime.now().astimezone())
        for key in sorted(set(self.observer.live) - before):
            log.info("noticed %s running, started outside the launcher", self.observer.live[key].name)
            if self.is_starting(key):
                self.end_starting("seen running")
        for seen in ended:
            self._bank_observed(seen, final=True)
        if now - self._observed_last_bank >= rules.PLAYTIME_WRITE_INTERVAL_S:
            self._observed_last_bank = now
            for seen in self.observer.live.values():
                self._bank_observed(seen)
        if ended or set(self.observer.live) != before:
            self._update_tray_tooltip()
            self.refresh_running_state()
        if ended and not self.game_running():
            self._run_wanted_scan()  # held back while the game was up
            self._run_saves()

    def _keep_watch_since(self) -> None:
        """The day sessions began to be observed -- written once, by its own key, the first time there is
        something to date: the first observed session, or the switch turned on in Settings. Never at a
        start: a first run's config.json is written by its question alone (Phase 77), and nobody's
        file changes because a launcher merely started."""
        if self.config.get(rules.WATCH_SINCE_KEY):
            return
        since = date.today().isoformat()
        self.config[rules.WATCH_SINCE_KEY] = since
        if not config_io.save_config({rules.WATCH_SINCE_KEY: since}):
            log.warning("could not keep the day sessions began to be observed")

    def _bank_observed(self, seen: observe.Seen, final: bool = False) -> None:
        """Write an observed session: the session itself, last played, and -- by the no-double-count
        rule -- its time onto playtime_seconds only when no store keeps the game's hours.

        Nothing under SESSION_MIN_MINUTES leaves a trace: a minute of a crash handler or an updater in
        a game's folder is not play. Written on the banking cadence while it runs, as a launched
        session is (Phase 20), and once more when it ends.
        """
        minutes = seen.minutes
        if minutes < rules.SESSION_MIN_MINUTES:
            if final:
                log.info("%s was seen running for under a minute; not recorded", seen.name)
            return
        self._keep_watch_since()
        record = self.overrides.get(seen.key)
        values = {"last_played": datetime.now().astimezone().isoformat(timespec="seconds")}
        if seen.adds_hours:
            add = int(seen.seconds) - seen.banked
            if add > 0:
                values["playtime_seconds"] = int(record.get("playtime_seconds", 0)) + add
                seen.banked += add
        entries = sessions.upsert(sessions.load(record), seen.started_at, minutes, rules.SESSION_OBSERVED)
        values[rules.SESSIONS_KEY] = sessions.dump(sessions.prune(entries))
        self.overrides.update(seen.key, **values)
        if not final:
            return
        if not seen.adds_hours:
            self._steam_played_since_scan = True  # its store's counter has moved: the next tick reads it
        log.info("%s closed: %d min, observed (each edge within %d s)%s", seen.name, minutes,
                 rules.WATCH_PROCESS_POLL_S, "" if seen.adds_hours else "; its hours stay its store's counter")
        if minutes > rules.SESSION_MAX_HOURS * 60:
            log.warning("%s: an observed session of %d hours, longer than %d -- recorded, and worth a look",
                        seen.name, minutes // 60, rules.SESSION_MAX_HOURS)
        view = self.by_key.get(seen.key)
        if view is not None and seen.launch_kind == "exe":
            # Its saves, as after a launched session (Phase 29) -- exe games only: Steam, Epic and
            # Xbox keep their own cloud saves.
            window = (seen.started_at.timestamp(), time.time() + rules.SAVES_SESSION_SLACK_S)
            job = self.save_job(view, reason="after playing", extra_window=window)
            if job is not None:
                self._save_jobs.append(job)
        if not self._shut_down:
            self.reload_views()
            self._ask_rating(seen.key, seen.name, rate.started_text(seen.started_at), minutes)

    # -- how was it? (Phase 102) ----------------------------------------------------------------

    def _ask_rating(self, key: str, name: str, started_at: str, minutes: int) -> None:
        """A session has ended: ask how it was, if the rules say so (logic/rate.due) -- the card while the window
        is shown, the tray's balloon while it is hidden. Asked or not, said in the log."""
        keeps = bool(getattr(self.overrides, "keeps_ratings", False))
        today = date.today().isoformat()
        view = self.by_key.get(key)
        ok, why = rate.due(minutes, enabled=keeps and bool(self.config.get(rules.RATE_ASK_KEY, rules.RATE_ASK_DEFAULT)),
                           running=self.game_running(), asked_today=self._rate_asked.get(key) == today,
                           rated_today=keeps and self.overrides.rated_on(key, today),
                           is_tool=bool(view is not None and view.is_non_game))
        if not ok:
            log.info("how was it: %s not asked about (%s)", name, why)
            return
        self._rate_asked[key] = today
        self._rate_ask = rate.Ask(key, name, started_at, minutes)
        if self._in_tray and self.tray is not None:
            log.info("how was it: %s asked about in the tray's balloon", name)
            self.tray.say(rate.balloon(self._rate_ask), clicked=self._rate_from_balloon)
            return
        self._rate_tries = 0
        self._show_rating()

    def _show_rating(self) -> None:
        """The card for the session asked about -- never over a dialog, a menu or the splash: it waits and looks
        again (rules.RATE_RETRY_MS, rules.RATE_TRIES), then leaves the session to its page."""
        ask = self._rate_ask
        if ask is None or self._shut_down or self._in_tray:
            return
        if (QApplication.activeModalWidget() is not None or QApplication.activePopupWidget() is not None
                or self.splash.showing):
            self._rate_tries += 1
            if self._rate_tries <= rules.RATE_TRIES:
                QTimer.singleShot(rules.RATE_RETRY_MS, self._show_rating)
            else:
                log.info("how was it: something stayed open; %s can be rated from its page", ask.name)
                self._rate_ask = None
            return
        if self.game_running():
            self._rate_ask = None
            return
        self.rate_card.ask(rate.question(ask))
        self._stack_toast(True)
        self._refresh_hints()
        log.info("how was it: asked about %s (the session of %s, %d min)", ask.name, ask.started_at, ask.minutes)

    def _rate_from_balloon(self) -> None:
        """The balloon clicked: the window back, and the card in it."""
        self.bring_forward()
        self._rate_tries = 0
        QTimer.singleShot(rules.RATE_RETRY_MS // 4, self._show_rating)

    def _rated(self, stars: int) -> None:
        ask, self._rate_ask = self._rate_ask, None
        if ask is not None and self.overrides.rate_session(ask.key, ask.started_at, stars):
            self._after_rating(ask.key)
        self._refresh_hints()
        QTimer.singleShot(ui_rules.RATE_THANKS_MS + 50, lambda: self._stack_toast(False))

    def _rate_done(self, why: str) -> None:
        ask, self._rate_ask = self._rate_ask, None
        if ask is not None:
            log.info("how was it: %s not rated (%s); its page can rate it for %d days", ask.name, why,
                     rules.RATE_LATE_DAYS)
        self._stack_toast(False)
        self._refresh_hints()

    def _withdraw_rating(self, why: str) -> None:
        """A game started, or the window went to the tray: the card goes, nothing written."""
        if self.rate_card.showing:
            self.rate_card.withdraw()
            self._rate_done(why)

    def _stack_toast(self, card_up: bool) -> None:
        """A message that arrives while the card asks floats above it, not under it."""
        reserve = self.hint_bar.sizeHint().height() if self.tv_mode else 0
        if card_up and self.rate_card.isVisible():
            reserve += self.rate_card.height() + round(ui_rules.TOAST_MARGIN * self.scale / 2)
        self.toast.set_bottom_reserve(reserve)

    def _after_rating(self, key: str) -> None:
        """A rating written: the game's page shows it, if it is the one open."""
        view = self.by_key.get(key)
        if view is not None and self.detail.view is not None and self.detail.view.key == key:
            self.detail.refresh_sessions(view)

    def last_unrated(self, view):
        """The game's newest session still to rate (logic/rate.last_unrated), or None -- the menu's offer."""
        if not getattr(self.overrides, "keeps_ratings", False):
            return None
        return rate.last_unrated(sessions.load(view.data), self.overrides.ratings_of(view.key),
                                 key=view.key, name=view.display_name)

    def rate_last_session(self, view) -> None:
        """Rate your last session...: the game's menu (X on the pad), the card for that session."""
        ask = self.last_unrated(view)
        if ask is None:
            return
        self._rate_ask = ask
        self._rate_tries = 0
        QTimer.singleShot(0, self._show_rating)  # after the menu has gone

    def rate_late(self, key: str, started_at: str, stars: int) -> None:
        """A session rated from its game's page, Recent sessions (Phase 102)."""
        if self.overrides.rate_session(key, started_at, stars):
            self._after_rating(key)

    # -- running in the background (Phase 92) ---------------------------------------------------

    def begin(self) -> None:
        """What a session starts, once, however it started: on screen, or hidden in the tray.

        Called by the window's first appearance and by a --background start alike, so both run the
        one sequence: the startup scan, the first look for saves, the update check -- each after
        its delay, each once. Only after the window is actually on screen, when it is shown: a scan
        that begins while the window is still being built makes the first paint feel slow.
        """
        if not self._startup_scan_started:
            self._startup_scan_started = True
            QTimer.singleShot(rules.STARTUP_SCAN_DELAY_MS, self._startup_scan)
        if not self._saves_started:
            self._saves_started = True
            QTimer.singleShot(rules.SAVES_STARTUP_DELAY_MS, self._startup_saves)
        if not self._updates_started:
            self._updates_started = True
            QTimer.singleShot(rules.UPDATE_CHECK_DELAY_MS, self._check_for_updates)
            QTimer.singleShot(rules.RECAP_OFFER_DELAY_MS, self.offer_recap)  # after the start-up messages
        if not self.tick.isActive():
            self.tick.start()
            log.info("the tick: every %d minutes, a look at whether a reading is due",
                     rules.BACKGROUND_TICK_MINUTES)
        self._note_version()
        self._apply_watch()

    def _note_version(self) -> None:
        """The version that ran (Phase 99), by its own key -- never on a first run, whose config.json is the
        question's to write (the answer carries it). After an update (Phase 106) not here: once the notes are
        closed (`show_whats_new`), so a start hidden in the tray, or one that ends before they show, leaves them
        for the next start that is seen -- the tray's tooltip says so meanwhile."""
        if self.first_run or self.config.get(rules.VERSION_SEEN_KEY) == version.APP_VERSION:
            return
        before = self.config.get(rules.VERSION_SEEN_KEY)
        if self._whats_new:
            log.info("updated to %s from %s: what's new waits for the window", version.APP_VERSION, before)
            self._update_tray_tooltip()
            return
        self.config[rules.VERSION_SEEN_KEY] = version.APP_VERSION
        if config_io.save_config({rules.VERSION_SEEN_KEY: version.APP_VERSION}):
            log.info("version seen: %s (before: %s)", version.APP_VERSION, before or "none written")

    def show_whats_new(self) -> None:
        """The first start after an update (Phase 106): the version's notes, once, over a window that is there to be
        seen; then the version seen written, and the tray offer -- if it is due -- a second later."""
        if not self._whats_new or self._shut_down:
            return
        if (not self.isVisible() or self.isMinimized() or self._in_tray
                or QApplication.activeModalWidget() is not None):
            # Not to be seen yet, or another question is up: later, a few times -- then the next start that is seen.
            self._whats_new_tries += 1
            if self._whats_new_tries < rules.WHATS_NEW_TRIES:
                QTimer.singleShot(rules.WHATS_NEW_RETRY_MS, self.show_whats_new)
            else:
                log.info("what's new: the window was not to be seen; the notes wait for the next start")
                self._whats_new_scheduled = self._offer_scheduled = False
                self._whats_new_tries = 0
            return
        notes = whats_new.english()
        if notes:
            scale = float(self.config.get("tv_scale", ui_rules.TV_SCALE_DEFAULT)) if self.tv_mode else self.scale
            dialog = ui_whats_new.WhatsNewDialog(version.APP_VERSION, notes, scale, tv=self.tv_mode, parent=self)
            self.hint_bar.set_hints(ui_tv.DIALOG)
            try:
                dialog.exec()
            finally:
                self._refresh_hints()
            log.info("what's new: the notes of %s shown and closed", version.APP_VERSION)
        else:
            log.warning("what's new: this copy carries no notes for %s; noted as seen", version.APP_VERSION)
        self._whats_new = False
        before = self.config.get(rules.VERSION_SEEN_KEY)
        self.config[rules.VERSION_SEEN_KEY] = version.APP_VERSION
        if config_io.save_config({rules.VERSION_SEEN_KEY: version.APP_VERSION}):
            log.info("version seen: %s (before: %s)", version.APP_VERSION, before)
        self._update_tray_tooltip()
        QTimer.singleShot(rules.TRAY_OFFER_DELAY_MS, self.offer_tray)

    # -- the one question (Phase 99) ---------------------------------------------------------------

    def tray_offer_due(self) -> bool:
        """Asked once: the switch is off, it was never asked, and this start did not ask the first-run questions."""
        return (not self._first_run_start and not self.first_run and not self.keep_running
                and not self.config.get(rules.TRAY_OFFER_KEY) and not self._shut_down)

    def offer_tray(self) -> None:
        """Would they like the launcher to stay in the tray? "Not now" (the default) or "Keep it running";
        the day it was asked is written either way, and on yes the first switch -- nothing else."""
        if not self.tray_offer_due():
            return
        if not self.isVisible() or self.isMinimized() or QApplication.activeModalWidget() is not None:
            # Another question is up, or the window is not to be seen: later, a few times, then not this start.
            self._offer_tries += 1
            if self._offer_tries < rules.TRAY_OFFER_TRIES:
                QTimer.singleShot(rules.TRAY_OFFER_RETRY_MS, self.offer_tray)
            return
        scale = float(self.config.get("tv_scale", ui_rules.TV_SCALE_DEFAULT)) if self.tv_mode else self.scale
        dialog = ui_offer.TrayOfferDialog(scale, tv=self.tv_mode, parent=self)
        self.hint_bar.set_hints(ui_tv.DIALOG)
        try:
            keep = dialog.exec() == QDialog.DialogCode.Accepted
        finally:
            self._refresh_hints()
        values = {rules.TRAY_OFFER_KEY: date.today().isoformat()}
        if keep:
            values[rules.KEEP_RUNNING_KEY] = True
        self.config.update(values)
        if not config_io.save_config(values):
            log.warning("the tray offer's answer could not be written; it may be asked again")
        log.info("tray offer: %s", "keep it running" if keep else "not now")
        if keep:
            self._set_keep_running(True)

    def readings_due(self) -> list[str]:
        """Which readings a scan would take now, by their own rules -- the tick decides nothing else."""
        online = bool(self.config.get("allow_network", rules.ALLOW_NETWORK_DEFAULT))
        due = []
        if prices.due(self.overrides, online, say=False):
            due.append("prices")
        if wishlist.due(self.overrides, online, say=False):
            due.append("wishlists")
        if steam_time.due(self.overrides) and steam_time.files_changed_since(self._last_scan_began):
            # Steam rewrites its files with no play at all: a counter only moves when a game is played,
            # so the files are due after a Steam game was seen, or after STEAM_TIME_TICK_HOURS anyway.
            old = time.time() - self._last_scan_began >= rules.STEAM_TIME_TICK_HOURS * 3600
            if self._steam_played_since_scan or old:
                due.append("Steam's playtime files")
        return due

    def _tick(self) -> None:
        """Every BACKGROUND_TICK_MINUTES while the launcher runs: the readings a day of being open takes.

        The update check keeps its own once-a-day rule. A reading that is due, with no game started
        from here running and no scan under way, starts a quiet scan -- the same scan as the startup
        one, landed the same way. Never while a game is up: a scan walks the disk the game streams from.
        Every beat says what it decided, at info, so launcher.log can answer "did the tick fire" (one
        line in half an hour; at debug the file never held it).
        """
        self._check_for_updates(quiet=True)
        self.offer_recap()
        if self.first_run:
            log.info("tick: the first-run question comes first")
            return
        due = self.readings_due()
        if not due:
            log.info("tick: nothing due")
            return
        if self.game_running():
            log.info("tick: %s due, held while a game is running", ", ".join(due))
            return
        if self.worker is not None and self.worker.isRunning():
            log.info("tick: %s due, but a scan is already running", ", ".join(due))
            return
        log.info("tick: %s due; a quiet scan (recorded as a watch scan)", ", ".join(due))
        self.start_scan(background=True, trigger="watch")

    def start_hidden(self) -> None:
        """A --background start: the tray icon and no window; the session begins all the same."""
        self._in_tray = True
        log.info("started hidden in the tray (%s)", rules.BACKGROUND_ARGUMENT)
        self.begin()
        if self.tray is None and self._tray_wait is None:
            self._wait_for_tray()

    def _wait_for_tray(self) -> None:
        """Windows' tray is not there yet -- at sign-in it comes after the Run entries. Ask again."""
        if self._tray_wait is not None:
            return
        self._tray_wait_began = time.monotonic()
        self._tray_wait = QTimer(self)
        self._tray_wait.setInterval(rules.TRAY_RETRY_MS)
        self._tray_wait.timeout.connect(self._tray_retry)
        self._tray_wait.start()
        log.info("no tray yet; asking again every %d ms for %d s", rules.TRAY_RETRY_MS, rules.TRAY_RETRY_MAX_S)

    def _tray_retry(self) -> None:
        if not self.keep_running or self.tray is not None:
            self._stop_tray_wait()
            return
        if tray_available():
            self._stop_tray_wait()
            log.info("the tray is there now")
            self._apply_keep_running()
            return
        if time.monotonic() - self._tray_wait_began >= rules.TRAY_RETRY_MAX_S:
            self._stop_tray_wait()
            log.warning("no tray after %d s; the window is shown instead", rules.TRAY_RETRY_MAX_S)
            if self._in_tray or not self.isVisible():
                self.bring_forward()

    def _stop_tray_wait(self) -> None:
        if self._tray_wait is not None:
            self._tray_wait.stop()
            self._tray_wait.deleteLater()
            self._tray_wait = None

    def _apply_keep_running(self) -> None:
        """The tray icon there exactly while "Keep running" is on, and closing following it.

        With the window hidden, closing any dialog -- Stop's question, Settings opened from the tray
        -- would be the last window closing, and Qt would quit the program. So while the tray holds
        the launcher, only Quit quits.
        """
        app = QApplication.instance()
        if self.keep_running:
            if self.tray is None:
                if not tray_available():
                    log.warning("keep running is on, but Windows has no tray to put an icon in yet; "
                                "until it has, closing the window quits")
                    app.setQuitOnLastWindowClosed(True)
                    self._wait_for_tray()
                    return
                self.tray = ui_tray.Tray(self)
                self.tray.show()
                self._update_tray_tooltip()
                log.info("tray icon shown: closing the window hides it")
            app.setQuitOnLastWindowClosed(False)
            return
        if self._in_tray:
            self.bring_forward()  # off means off: nothing is left hidden
        if self.tray is not None:
            self.tray.remove()
            self.tray = None
            log.info("tray icon removed: closing the window quits")
        app.setQuitOnLastWindowClosed(True)

    def _set_keep_running(self, on: bool) -> None:
        if on != self.keep_running:
            log.info("keep running when the window is closed: %s", "on" if on else "off")
        self.keep_running = on
        self._apply_keep_running()

    def _update_tray_tooltip(self) -> None:
        if self.tray is None:
            return
        # The name the game was started under, from the tracker: a reload rebuilds the views.
        playing = [(game.name, int(self._live_sessions[game.key][1])) for game in self.tracker.running
                   if game.key in self._live_sessions]
        # And a game seen running, however it was started (Phase 93).
        playing += [(seen.name, int(seen.seconds)) for seen in self.observer.live.values()]
        # Updated, its notes not seen yet (Phase 106): said until the window is shown and they are closed.
        self.tray.set_tooltip(ui_tray.tooltip(playing, version.APP_VERSION if self._whats_new else ""))

    def hide_to_tray(self) -> None:
        """What closing does with "Keep running" on: the window goes, the launcher stays.

        Every timer keeps running, the folder watch keeps watching, a game being timed goes on
        being timed. Its time so far is banked first, exactly as a close banks it. The first time
        ever, the icon says once where the launcher went.
        """
        self._poll_playtime()
        self._bank_playtime()
        self._save_geometry()
        self._withdraw_rating("the window went to the tray")
        self.hide()
        self._in_tray = True
        log.info("window hidden to the tray%s", " -- a game is still being timed" if self.tracker.running else "")
        if self.tray is not None and not self.config.get(rules.TRAY_HINT_KEY):
            self.tray.say(ui_tray.FIRST_HIDE)
            self.config[rules.TRAY_HINT_KEY] = True
            if not config_io.save_config({rules.TRAY_HINT_KEY: True}):
                log.warning("could not remember that the tray's first message was shown")

    def bring_forward(self, tv: bool = False) -> None:
        """Back on screen and in front: from the tray icon, or a second start asking (`tv`: in TV mode)."""
        was_hidden = self._in_tray or not self.isVisible()
        self._in_tray = False
        if not self._shown and self.config.get("tv_mode"):
            tv = True  # a hidden start shown for the first time opens as the plain shortcut would
        if tv and not self.tv_mode:
            self.set_tv_mode(True)  # shows it fullscreen
        elif self.tv_mode:
            self.showFullScreen()
        else:
            self.show()
        if self.isMinimized():
            self.setWindowState((self.windowState() & ~Qt.WindowState.WindowMinimized)
                                | Qt.WindowState.WindowActive)
        self.raise_()
        try:
            # A click on the tray is a click on another program as far as Windows' focus lock is
            # concerned; the same way through it as after a game (Phase 28).
            focus.bring_to_front(int(self.winId()))
        except Exception as exc:
            log.warning("could not bring the window to the front: %s", exc)
        self.activateWindow()
        log.info("window shown%s", " from the tray" if was_hidden else "")

    def quit_launcher(self) -> None:
        """Quit, from the tray icon's menu: what closing did before, then the program ends."""
        log.info("quit chosen from the tray")
        self._quitting = True
        self.shutdown()
        self._exit_application()

    def _exit_application(self) -> None:
        QApplication.instance().quit()

    def closeEvent(self, event) -> None:
        app = QApplication.instance()
        if (not self._quitting and self.keep_running and self.tray is not None and self.tray.visible()
                and not app.isSavingSession()):
            # Windows signing out asks every window to close (isSavingSession): that close is real.
            event.ignore()
            self.hide_to_tray()
            return
        self.shutdown()
        super().closeEvent(event)
        if not app.quitOnLastWindowClosed() and not self._quitting:
            # Keep running is on but there was no tray to hide into, or Windows is signing out:
            # Qt would otherwise go on with no window and no icon -- a process only Task Manager
            # could reach.
            self._exit_application()

    def shutdown(self) -> None:
        """Everything closing the launcher does, once, in this order: let go of the hooks; stop the
        timers, the pad and the folder watch; wait for a save copy in progress; stop the downloads
        and the workers; save the window's place; wait for a scan; bank the playtime; let go of the
        database. One implementation, for a close and for Quit alike (Phase 92)."""
        if self._shut_down:
            return
        self._shut_down = True
        self.tick.stop()
        self._stop_tray_wait()
        self._stop_watch()
        if getattr(self, "_hints_hooked", False):
            # The application's signal, so it is let go of with the window.
            try:
                QApplication.instance().focusChanged.disconnect(self._refresh_hints)
            except (RuntimeError, TypeError) as exc:
                log.debug("hint hook already gone: %s", exc)
            self._hints_hooked = False
        self.timer.stop()
        self.pads.stop()
        self.watcher.stop()  # its measuring thread must not outlive the window either
        if self.save_worker is not None and self.save_worker.isRunning():
            # A zip half written is thrown away, never left looking like a backup, but a
            # large one takes a few seconds -- worth waiting for rather than losing.
            log.info("waiting for a save backup to finish before closing")
            self.save_worker.requestInterruption()
            self.save_worker.wait(30000)
        self.detail.stop_downloads()
        if self.capsule_worker is not None and self.capsule_worker.isRunning():
            self.capsule_worker.requestInterruption()
            self.capsule_worker.wait((rules.STEAM_WEB_TIMEOUT_SECONDS + 2) * 1000)
        if self.cover_fill_worker is not None and self.cover_fill_worker.isRunning():
            # The game under way finishes: at most a request or two, each giving up after its timeout.
            self.cover_fill_worker.requestInterruption()
            self.cover_fill_worker.wait((2 * rules.STEAM_WEB_TIMEOUT_SECONDS + 2) * 1000)
        if self.update_worker is not None and self.update_worker.isRunning():
            # At most one request, and it gives up after UPDATE_TIMEOUT_SECONDS.
            self.update_worker.requestInterruption()
            self.update_worker.wait((rules.UPDATE_TIMEOUT_SECONDS + 1) * 1000)
        self._save_geometry()
        if self.worker is not None and self.worker.isRunning():
            log.info("waiting for the scan thread to finish before closing")
            self.worker.requestInterruption()
            self.worker.wait(5000)
        self._poll_playtime()
        # Timing stops here: the game keeps running, but nothing is left to
        # watch it. Bank what this session earned before the window goes.
        self._bank_playtime()
        for seen in self.observer.end_all():  # and an observed one, at its last sighting (Phase 93)
            self._bank_observed(seen, final=True)
        self.overrides.close()  # the database file let go of (Phase 69); reopened if used again
        if self.tray is not None:
            self.tray.icon.hide()  # gone from the tray with the program, not left as a ghost


def tray_available() -> bool:
    """Has Windows a tray to put an icon in yet? At sign-in, not always (Phase 92)."""
    return QSystemTrayIcon.isSystemTrayAvailable()


def _same_entries(old: list, new: list) -> bool:
    """True if a scan found exactly what was already showing.

    Compared as JSON, because an entry loaded from catalog.json holds lists where a freshly
    scanned one holds tuples, and Python does not consider those equal.
    """
    if len(old) != len(new):
        return False

    def flat(entries: list) -> str:
        return json.dumps([entry.to_dict() for entry in entries], sort_keys=True, default=str)

    return flat(old) == flat(new)


def _arrivals_text(views: list) -> str:
    """'New game: X', or '4 new games: A, B, C and 1 more' -- or nothing at all."""
    if not views:
        return ""
    names = [view.display_name for view in views]
    shown = ", ".join(names[:NEW_NAMES_SHOWN])
    rest = len(names) - NEW_NAMES_SHOWN
    if rest > 0:
        shown += f" and {rest} more"
    if len(names) == 1:
        return f"New game: {shown}"
    return f"{len(names)} new games: {shown}"
