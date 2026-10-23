"""The settings dialog.

Everything here is written back into config.json, merged rather than rewritten, so settings
this dialog does not know about (the exclusions, the window's place) survive being saved.

Redesigned in Phase 35: sections of rows, each a title, a quieter line saying what it
does, and its control on the right -- a switch for anything on or off. It scrolls when a
screen is too short for all of it, and works from a controller: the pad moves between
the controls, A flips a switch or presses a button, left and right change a size (the
window drives this; see MainWindow._drive_dialog).

Since Phase 75 it lists the Steam accounts whose files the launcher reads, each with a mark of
three -- mine, not mine, not decided -- which the window saves into the library on OK only.

Since Phase 77 it edits the game folders (the scan's roots: the window rescans when they
change), saves a diagnostics bundle for support, and ends with the launcher's version.
"""

from __future__ import annotations

import logging

from datetime import date
from pathlib import Path

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, QTimer, QUrl, Signal, qVersion
from PySide6.QtGui import QColor, QDesktopServices, QFont, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from logic import autostart
from shared import humanize
from shared import rules
from shared import version
from presentation import ui_backups
from presentation import ui_folders
from presentation import ui_icons
from presentation import ui_rules
from presentation import ui_transfer
from presentation.ui_cards import FocusRing, ToggleSwitch

log = logging.getLogger(__name__)

START_HINT = "Starts hidden in the tray when you sign in."
WATCH_HINT = ("Records a session when a game you have here is running, however you started it. Only games "
              "the launcher already knows; nothing else is looked at or kept.")
WINDOWS_TURNED_IT_OFF = ("Windows has turned this off in Startup apps. Turn it back on there (Task Manager, "
                         "Startup apps), or switch it off here.")

# Returned instead of Accepted when overrides.json and config.json were replaced underneath
# this dialog -- by a restore or by an import. The window reloads from disk on seeing it,
# rather than saving the now-stale values this dialog is still holding.
DATA_REPLACED = 2


class AccentSwatch(QPushButton):
    """One accent in Settings' row (Phase 99): its colour as a disc, ringed inside its own button when it is the
    one chosen, its name under it. Checkable, one of an exclusive group: the pad moves along the row, and A picks."""

    def __init__(self, name: str, scale: float) -> None:
        super().__init__()
        self.setObjectName("AccentSwatch")
        self.name = name
        self.scale = scale
        self.setCheckable(True)
        # Never the dialog's default: a focused push button becomes it, and OK lost its outline while the dialog
        # opened on a swatch (suite 58 caught it).
        self.setAutoDefault(False)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setToolTip(f"{name} accent")
        self.setAccessibleName(f"{name} accent")
        self.setFixedSize(round(ui_rules.ACCENT_SWATCH_WIDTH * scale), round(ui_rules.ACCENT_SWATCH_HEIGHT * scale))
        self.setProperty("ringRadius", round(ui_rules.CONTROL_RADIUS * scale))

    def paintEvent(self, event) -> None:
        s = self.scale
        colour = QColor(ui_rules.ACCENTS[self.name][500])
        r = ui_rules.ACCENT_SWATCH_PX * s / 2
        reach = r + (ui_rules.ACCENT_SWATCH_RING_GAP + ui_rules.ACCENT_SWATCH_RING) * s
        centre = QPointF(self.width() / 2, reach + 2 * s)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(colour)
        painter.drawEllipse(centre, r, r)
        if self.isChecked() or self.underMouse():
            ring = ui_rules.ACCENT_SWATCH_RING * s
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(colour if self.isChecked() else QColor(ui_rules.COLOR_BORDER), ring))
            painter.drawEllipse(centre, reach - ring / 2, reach - ring / 2)
        font = QFont(self.font())
        font.setPixelSize(max(8, round(ui_rules.ACCENT_SWATCH_NAME_PX * s)))
        painter.setFont(font)
        painter.setPen(QColor(ui_rules.COLOR_TEXT if self.isChecked() else ui_rules.COLOR_TEXT_MUTED))
        top = centre.y() + reach + 3 * s
        painter.drawText(QRectF(0, top, self.width(), self.height() - top), int(Qt.AlignmentFlag.AlignHCenter
                                                                               | Qt.AlignmentFlag.AlignTop), self.name)


class SettingsDialog(QDialog):
    accentChosen = Signal(str)  # a swatch picked: the window shows it at once (Phase 99)

    def __init__(self, config: dict, parent=None, known_keys: set[str] | None = None,
                 store=None, focus: str | None = None, covers=None) -> None:
        super().__init__(parent)
        self._focus = focus  # "roots": open on the Game folders row (the empty library's button)
        self._config = dict(config)
        self._known_keys = known_keys or set()
        self._store = store  # the window's library store, for export and import (Phase 65)
        # The window, for the Missing covers row (Phase 105): missing_covers() and fill_missing_covers(); None
        # leaves the row out.
        self._covers = covers
        self.setObjectName("Settings")
        self.setWindowTitle("Settings")
        self.restore_message = ""
        tv = bool(config.get("tv_mode", ui_rules.TV_MODE_DEFAULT))
        self._tv = tv
        self.scale = float(config.get("tv_scale", ui_rules.TV_SCALE_DEFAULT) if tv
                           else config.get("ui_scale", ui_rules.UI_SCALE_DEFAULT))
        self._animate = not bool(config.get("reduce_animations",
                                            ui_rules.REDUCE_ANIMATIONS_DEFAULT))
        self._pad_first = tv  # on a couch, start with the first control in focus
        # The ring the design draws outside a control (Phase 58): TV mode's is thicker.
        self.focus_ring_width = ui_rules.TV_FOCUS_RING_WIDTH if tv else ui_rules.FOCUS_RING_WIDTH
        self._rows = QVBoxLayout()
        self._build(config)

    # -- construction -----------------------------------------------------------------------

    def _switch(self, checked: bool, tip: str) -> ToggleSwitch:
        switch = ToggleSwitch(scale=self.scale, animate=self._animate)
        switch.setProperty("ringRadius", switch.sizeHint().height() / 2)
        switch.setChecked(checked)
        switch.setToolTip(tip)
        return switch

    def _button(self, text: str, tip: str = "") -> QPushButton:
        button = QPushButton(text)
        button.setToolTip(tip)
        button.setFocusPolicy(Qt.FocusPolicy.TabFocus)  # a click must not leave a ring
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        return button

    def _combo(self, choices, current: float, fallback: float) -> QComboBox:
        box = QComboBox()
        box.setObjectName("SortBox")  # the library's pill
        # A chip's height too: a stylesheet stops rounding a box whose corners are more
        # than half its height, and the first render showed plain rectangles.
        box.setFixedHeight(max(20, round(ui_rules.CHIP_HEIGHT * self.scale)))
        box.setProperty("ringRadius", box.height() / 2)
        box.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        box.setCursor(Qt.CursorShape.PointingHandCursor)
        for value in choices:
            box.addItem(f"{round(value * 100)}%", value)
        index = box.findData(current)
        box.setCurrentIndex(index if index >= 0 else box.findData(fallback))
        return box

    def _section(self, title: str) -> QVBoxLayout:
        """A heading, then a card that the section's rows go into."""
        heading = QLabel(title)
        heading.setObjectName("SettingSection")
        group = QFrame()
        group.setObjectName("SettingGroup")
        rows = QVBoxLayout(group)
        pad = max(8, round(ui_rules.DETAIL_CARD_PADDING * self.scale * 0.75))
        rows.setContentsMargins(pad, pad // 2, pad, pad // 2)
        rows.setSpacing(0)
        self._rows.addWidget(heading)
        self._rows.addWidget(group)
        return rows

    def _row(self, rows: QVBoxLayout, title: str, hint: str, *controls) -> QWidget:
        """One setting: its name and what it does on the left, its control on the right."""
        row = SettingRow(title, hint, controls, self.scale)
        if rows.count():
            line = QFrame()
            line.setObjectName("SettingLine")
            line.setFixedHeight(1)
            rows.addWidget(line)
        rows.addWidget(row)
        return row

    def _build(self, config: dict) -> None:
        # -- look and feel
        rows = self._section("Look and feel")
        # Phase 99: the accent, five swatches; a pick shows at once, OK keeps it, Cancel puts the old one back.
        self.accent_group = QButtonGroup(self)
        self.accent_group.setExclusive(True)
        self.accent_swatches: dict[str, AccentSwatch] = {}
        current = config.get(ui_rules.ACCENT_KEY)
        current = current if current in ui_rules.ACCENTS else ui_rules.ACCENT_DEFAULT
        swatches = QWidget()
        swatches.setObjectName("Clear")
        line = QHBoxLayout(swatches)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(0)
        for name in ui_rules.ACCENTS:
            swatch = AccentSwatch(name, self.scale)
            swatch.setChecked(name == current)
            swatch.toggled.connect(lambda on, n=name: on and self.accentChosen.emit(n))
            self.accent_group.addButton(swatch)
            self.accent_swatches[name] = swatch
            line.addWidget(swatch)
        self._row(rows, "Accent", "The colour of rings, buttons and marks. Shows at once; a game's own colours stay "
                  "its own.", swatches)
        self.reduce_box = self._switch(
            bool(config.get("reduce_animations", ui_rules.REDUCE_ANIMATIONS_DEFAULT)),
            "Turns off tile hover growth, page transitions and smooth scrolling.")
        self._row(rows, "Reduce animations",
                  "Pages appear rather than slide, covers stay put, tiles do not grow.",
                  self.reduce_box)
        self.scale_box = self._combo(ui_rules.UI_SCALE_CHOICES,
                                     float(config.get("ui_scale", ui_rules.UI_SCALE_DEFAULT)),
                                     ui_rules.UI_SCALE_DEFAULT)
        self._row(rows, "Interface size", "How big everything is at your desk. Applies straight away.",
                  self.scale_box)
        # Phase 60: the side rail, or the bar across the top as before.
        self.rail_box = self._switch(
            config.get("library_layout", ui_rules.LIBRARY_LAYOUT_DEFAULT) == ui_rules.LAYOUT_RAIL,
            "Library, Stats and Storage, the filters and the stores in a column on the left.")
        self._row(rows, "Side rail",
                  "The places, filters and stores in a column on the left. Off puts them back "
                  "in a bar across the top. TV mode always uses the bar.",
                  self.rail_box)

        # -- controller and TV
        rows = self._section("Controller and TV")
        self.controller_box = self._switch(
            bool(config.get("enable_controller", rules.CONTROLLER_ENABLED_DEFAULT)),
            "A DualSense or Xbox pad can drive the launcher.\n"
            "Buttons are ignored while a game is in front, so playing never moves the menu.")
        self._row(rows, "Use game controllers",
                  "A DualSense or Xbox pad drives the launcher -- never while a game is in front.",
                  self.controller_box)
        self.tv_box = self._switch(bool(config.get("tv_mode", ui_rules.TV_MODE_DEFAULT)),
                                   "Also available from the 'Game Launcher (TV)' desktop shortcut.")
        self._row(rows, "TV mode",
                  "Fullscreen, bigger, with button hints. The 'Game Launcher (TV)' shortcut opens in it.",
                  self.tv_box)
        self.tv_scale_box = self._combo(ui_rules.TV_SCALE_CHOICES,
                                        float(config.get("tv_scale", ui_rules.TV_SCALE_DEFAULT)),
                                        ui_rules.TV_SCALE_DEFAULT)
        self.tv_scale_box.setToolTip(
            "How big everything is in TV mode only.\n\n"
            "Windows' own display scaling multiplies on top of this, so on a 4K TV set to\n"
            "300% a lower number here is normal. Pick a smaller one to fit more games on\n"
            "screen; it applies the moment you click OK."
        )
        self._row(rows, "TV mode size",
                  "Windows' own scaling adds to this, so on a 4K TV a lower number is normal.",
                  self.tv_scale_box)

        # -- running in the background (Phase 92)
        rows = self._section("Running in the background")
        self.keep_box = self._switch(
            bool(config.get(rules.KEEP_RUNNING_KEY, rules.KEEP_RUNNING_DEFAULT)),
            "Closing the window hides it in the tray instead of quitting.\n"
            "Quit from the tray icon's menu; turning this off puts closing back as it was.")
        self._row(rows, "Keep running when the window is closed",
                  "Stays in the tray: keeps timing a running game, watches your folders, takes its "
                  "daily readings. Quit from the tray icon.",
                  self.keep_box)
        # The Run value is its record, not config.json: what Windows will really do at sign-in.
        startup = autostart.state()
        self.started_with_windows = startup == autostart.ON
        self.start_box = self._switch(self.started_with_windows,
                                      "Starts the launcher hidden in the tray when you sign in to Windows.")
        self.start_row = self._row(rows, "Start with Windows",
                                   WINDOWS_TURNED_IT_OFF if startup == autostart.BLOCKED else START_HINT,
                                   self.start_box)
        # A startup app that quits when its window closes makes no sense: on needs Keep running, and
        # Keep running off takes it off too. Neither hides the other.
        self.start_box.toggled.connect(lambda on: on and self.keep_box.setChecked(True))
        self.keep_box.toggled.connect(lambda on: on or self.start_box.setChecked(False))
        # Phase 93: the watch of the process list, on by default; the day it began under it.
        self.observe_box = self._switch(bool(config.get(rules.WATCH_GAMES_KEY, rules.WATCH_GAMES_DEFAULT)),
                                      "Looks at the names and paths of the programs running on this PC every "
                                      f"{rules.WATCH_PROCESS_POLL_S} seconds, and keeps only the sessions of your games.")
        self.watch_row = self._row(rows, "Notice games started outside the launcher", watch_words(config),
                                   self.observe_box)

        # -- after a game (Phase 102)
        rows = self._section("After a game")
        self.rate_box = self._switch(bool(config.get(rules.RATE_ASK_KEY, rules.RATE_ASK_DEFAULT)),
                                     "After a session: five stars, one tap. Off: no question and no balloon; a "
                                     "session can still be rated from its game's page.")
        self._row(rows, "Ask how a session was",
                  f"Five stars, one tap, after sessions of {rules.RATE_MIN_MINUTES} minutes or more. "
                  "Skip is always one tap away.", self.rate_box)

        # -- finding games
        rows = self._section("Finding games")
        # Phase 77: the scan's roots, which only config.json held before.
        self.roots_editor = ui_folders.FolderList(list(config.get("roots", rules.DEFAULT_ROOTS)),
                                                  checkable=False, scale=self.scale)
        self.roots_row = self._row(rows, "Game folders",
                                   "Where your games are. Steam, GOG, Epic and Xbox games are found "
                                   "without these. Folders to skip inside these are set in config.json.")
        self.roots_row.add_below(self.roots_editor)
        self.startup_scan_box = self._switch(
            bool(config.get("startup_scan", rules.STARTUP_SCAN_DEFAULT)),
            "Looks for games you have installed or deleted since last time, in the\n"
            "background, a moment after the window appears. Takes a second or two.\n"
            "Turn it off if you would rather press Rescan yourself.")
        self._row(rows, "Check for new games when the launcher opens",
                  "A quiet look, a moment after the window appears.", self.startup_scan_box)
        self.watch_box = self._switch(
            bool(config.get("watch_folders", rules.WATCH_FOLDERS_DEFAULT)),
            "Notices a new folder in your game folders and adds the game once it has\n"
            "finished installing -- about a minute after the last file lands.\n"
            "Never scans while a game you started from here is running.")
        self._row(rows, "Add games I install while the launcher is open",
                  "Once the install has finished -- and never while a game is running.",
                  self.watch_box)

        # -- saves
        rows = self._section("Saves")
        self.saves_box = self._switch(
            bool(config.get("backup_saves", rules.SAVES_BACKUP_DEFAULT)),
            "For games you start from here. The launcher learns where each one saves by\n"
            f"watching what it writes while you play, and keeps the newest "
            f"{rules.SAVES_BACKUP_KEEP} copies.\n"
            "Uninstalling a game always copies its saves first, whatever this is set to.")
        self._row(rows, "Keep a copy of a game's saves after each session",
                  f"The newest {rules.SAVES_BACKUP_KEEP} of each. Uninstalling always copies "
                  "them first, whatever this says.", self.saves_box)
        self.open_save_backups = self._button("Open save backups")
        self.open_save_backups.clicked.connect(self._open_save_backups)
        self._row(rows, "Save backups", "Where those copies are kept.", self.open_save_backups)

        # -- artwork and the internet
        rows = self._section("Artwork and the internet")
        self.network_box = self._switch(
            bool(config.get("allow_network", True)),
            "Downloads Steam cover art and asks whether an entry is a game, a demo or a tool.\n"
            "Anonymous requests; no account and nothing about you is sent.")
        self._row(rows, "Allow network lookups",
                  "Steam art, and whether an entry is a game, a demo or a tool; in an installed "
                  "copy, whether a new version is out. Anonymous. Off keeps every game; only "
                  "artwork stops updating.", self.network_box)
        self.sgdb_key = QLineEdit(str(config.get("steamgriddb_key", "") or ""))
        self.sgdb_key.setPlaceholderText("optional — paste your SteamGridDB key")
        self.sgdb_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.sgdb_key.setToolTip(
            "A free key from your own steamgriddb.com account.\n"
            "Only used when you ask for a cover, and only sent to steamgriddb.com."
        )
        self.show_key = self._button("Show")
        self.show_key.setCheckable(True)
        self.show_key.toggled.connect(self._show_key)
        self.sgdb_check = self._button("Test")
        self.sgdb_check.clicked.connect(self._test_key)
        self.sgdb_status = QLabel()
        self.sgdb_status.setObjectName("Meta")
        key_row = self._row(rows, "SteamGridDB key",
                            "Optional: a free key from your own steamgriddb.com account, for "
                            "more artwork. Only ever sent there.")
        key_line = QHBoxLayout()
        key_line.setContentsMargins(0, 0, 0, 0)
        key_line.addWidget(self.sgdb_key, 1)
        key_line.addWidget(self.show_key)
        key_line.addWidget(self.sgdb_check)
        key_row.add_below(key_line)
        key_row.add_below(self.sgdb_status)
        # Phase 105: every game the grid shows without a cover, looked up in one go -- with the key and the
        # switch as they stand in this window, so a key just pasted and tested works at once.
        self.fill_covers_button = None
        if self._covers is not None:
            self.fill_covers_button = self._button("Fill missing covers...")
            self.fill_covers_button.clicked.connect(self._fill_covers)
            self.covers_status = QLabel()
            self.covers_status.setObjectName("Meta")
            self.covers_status.setWordWrap(True)
            covers_row = self._row(rows, "Missing covers",
                                   "Every game without a cover, looked up on SteamGridDB with your key. A cover "
                                   "you set yourself is never replaced.", self.fill_covers_button)
            covers_row.add_below(self.covers_status)
            self.sgdb_key.textChanged.connect(self._update_covers_row)
            self.network_box.toggled.connect(self._update_covers_row)
            self._update_covers_row()

        # -- Steam accounts (Phase 75)
        self._build_accounts()

        # -- your data
        rows = self._section("Your library data")
        self.open_backups = self._button("Open folder")
        self.open_backups.clicked.connect(lambda: ui_backups.open_folder(self))
        self.restore_backup = self._button(
            "Restore...",
            "Put back your settings and library data from an earlier copy.\n"
            "What you have now is saved first, so it can be undone.")
        self.restore_backup.clicked.connect(self._restore)
        self._row(rows, "Backups",
                  "Your settings, playtime and notes, copied each time the launcher opens.",
                  self.open_backups, self.restore_backup)
        self.export_button = self._button(
            "Export...",
            "Save your settings, playtime and chosen artwork as one file,\n"
            "so they can be carried to another PC.")
        self.export_button.clicked.connect(self._export)
        self.import_button = self._button(
            "Import...",
            "Bring in a file exported from another PC. Nothing here is deleted,\n"
            "and a backup is taken first.")
        self.import_button.clicked.connect(self._import)
        self._row(rows, "Another PC",
                  "Carry settings, playtime and chosen artwork across as one file.",
                  self.export_button, self.import_button)
        # Phase 77: one file to send to whoever helps when something is wrong.
        self.diagnostics_button = self._button(
            "Save diagnostics...",
            "The log and what the last scan found, with the folders it looked in.\n"
            "Your play history, notes, purchases and Steam accounts are not in it.")
        self.diagnostics_button.clicked.connect(self._save_diagnostics)
        self.diagnostics_status = StatusLine()
        self.diagnostics_status.setObjectName("SettingHint")
        self.diagnostics_status.setWordWrap(True)
        diagnostics_row = self._row(rows, "Diagnostics",
                                    "One file to send when something is not working: the log and what "
                                    "the last scan found. Nothing of your play history is in it.",
                                    self.diagnostics_button)
        diagnostics_row.add_below(self.diagnostics_status)
        # Where the bundle is saved; a test hands in an answer of its own.
        self.choose_diagnostics_path = self._ask_where_to_save
        # Phase 80: an anonymous copy of the library, for a comparison in a bachelor thesis.
        self.analysis_button = self._button(
            "Anonymous export...",
            "Which games you have and how much you played them, as a file you can read first.\n"
            "No folder paths, no account names; nothing is sent from here.")
        self.analysis_button.clicked.connect(self._save_analysis)
        self.analysis_status = StatusLine()
        self.analysis_status.setObjectName("SettingHint")
        self.analysis_status.setWordWrap(True)
        analysis_row = self._row(rows, "For a thesis",
                                 "An anonymous copy: which games you have and how much you played them. "
                                 "No folder paths, no account names -- and you choose whether to send it.",
                                 self.analysis_button)
        analysis_row.add_below(self.analysis_status)
        # The dialog that shows what is in it, and where it is saved; tests hand in their own.
        self.analysis_dialog = None
        self.choose_analysis_path = self._ask_where_to_save_analysis

        # -- about (Phase 77): the version, one source for it (shared/version.py)
        rows = self._section("About")
        built = version.build_date()
        # What's new (Phase 106): this version's notes, the ones its first start showed, at any time.
        from logic import whats_new

        self.whats_new_button = self._button("What's new")
        self.whats_new_notes = whats_new.english()
        self.whats_new_button.setEnabled(bool(self.whats_new_notes))
        if not self.whats_new_notes:
            self.whats_new_button.setToolTip(f"This copy carries no notes for {version.APP_VERSION}.")
        self.whats_new_button.clicked.connect(
            lambda: self._show_notes(version.APP_VERSION, self.whats_new_notes))
        self.version_row = self._row(
            rows, f"{version.APP_NAME} {version.APP_VERSION}",
            f"Built {humanize.day(built, year=True)}." if built else "Run from source, not an installed copy.",
            self.whats_new_button)
        # Is a newer one out (Phase 79): the last answer GitHub gave the window, and the page the
        # new installer is on -- always that fixed page, opened in the browser.
        from web import updates

        self.update_page = self._button("Open the download page")
        self.update_page.clicked.connect(lambda: open_in_browser(rules.UPDATE_PAGE_URL))
        allowed, why = updates.should_check(config)
        answer = updates.last()
        controls = [self.update_page]
        # A newer one's notes (Phase 106), from the answer the check kept -- what it changes, before it is run.
        self.newer_notes_button = None
        newer_notes = whats_new.section(answer.notes) if answer is not None and answer.newer else ""
        if allowed and newer_notes:
            self.newer_notes_button = self._button(f"See what's new in {answer.latest}")
            self.newer_notes_button.clicked.connect(lambda: self._show_notes(answer.latest, newer_notes))
            controls.insert(0, self.newer_notes_button)
        self.update_row = self._row(rows, "Updates", update_text(answer, allowed, why), *controls)

        # -- the page: a title, the sections scrolling, the buttons fixed at the foot
        title = QLabel("Settings")
        title.setObjectName("SettingsTitle")
        body = QWidget()
        body.setObjectName("SettingsBody")
        self._rows.setContentsMargins(0, 0, 0, 0)
        self._rows.setSpacing(max(6, round(10 * self.scale)))
        body.setLayout(self._rows)
        self._rows.addStretch(1)
        self.scroll = QScrollArea()
        self.scroll.setObjectName("SettingsScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.scroll.setWidget(body)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        for button in buttons.buttons():
            button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        margin = max(12, round(24 * self.scale))
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.setSpacing(max(8, round(14 * self.scale)))
        layout.addWidget(title)
        layout.addWidget(self.scroll, 1)
        layout.addWidget(buttons)

        self.setMinimumWidth(round(ui_rules.SETTINGS_WIDTH * self.scale))
        # The pad moves focus with Tab; keep whatever it lands on in view.
        QApplication.instance().focusChanged.connect(self._follow_focus)
        # One ring over the whole dialog, outside whichever control has the focus.
        self.focus_ring = FocusRing(self, self._ringed, scale=lambda: self.scale)
        self.focus_ring.clip = self.scroll.viewport()

    def _build_accounts(self) -> None:
        """One row per Steam account the launcher has read, each with its mark of three.

        The marks are only held here; the window saves the ones changed when OK is pressed.
        Nothing to show -- no account read yet, or a library that keeps no Steam time -- and
        the section says so in one row rather than vanishing.
        """
        rows = self._section("Steam accounts")
        self.account_groups: dict[int, QButtonGroup] = {}
        self._account_marks_opened: dict[int, bool | None] = {}
        accounts = []
        if self._store is not None and getattr(self._store, "keeps_steam_time", False):
            accounts = self._store.steam_accounts()
        if not accounts:
            self._row(rows, "No account read yet",
                      "Steam's own playtime is read from its files with each scan, for every "
                      "account that has signed in on this PC.")
            return
        self._row(rows, "Whose time counts",
                  "Only accounts marked as yours count on a game's page and in sums. Read from "
                  "Steam's files on this PC; nothing is sent anywhere.")
        for account in accounts:
            name = account["persona"] or f"Account {account['account_id']}"
            hint = (f"{account['apps_with_time'] or 0} games with time on Steam · updated "
                    f"{_when(account['file_modified'])}" if account["read_at"] else "Not read yet")
            if account["is_mine"] and getattr(self._store, "keeps_wishlist", False):
                hint += f"\n{wishlist_words(account)}"
            bar, group = self._marks(account["is_mine"], name)
            self._row(rows, name, hint, bar)
            self.account_groups[account["account_id"]] = group
            mark = account["is_mine"]
            self._account_marks_opened[account["account_id"]] = None if mark is None else bool(mark)

    def _marks(self, current, name: str) -> tuple[QFrame, QButtonGroup]:
        """Mine / Not mine / Not decided, one always chosen: the game page's segmented switch."""
        bar = QFrame()
        bar.setObjectName("SegmentBar")
        line = QHBoxLayout(bar)
        line.setContentsMargins(1, 1, 1, 1)
        line.setSpacing(0)
        group = QButtonGroup(bar)
        group.setExclusive(True)
        inner = max(16, round(ui_rules.SETTINGS_SEGMENT_HEIGHT * self.scale)) - 2
        last = len(ui_rules.STEAM_ACCOUNT_MARKS) - 1
        for index, (mark, words) in enumerate(ui_rules.STEAM_ACCOUNT_MARKS):
            if index:
                divider = QFrame()
                divider.setObjectName("SegmentLine")
                divider.setFixedSize(1, inner)
                line.addWidget(divider)
            button = MarkButton(words)
            button.setObjectName("Segment")
            button.setProperty("edge", "first" if index == 0 else "last" if index == last else "")
            button.setProperty("mark", "" if mark is None else ("mine" if mark else "not_mine"))
            button.setCheckable(True)
            button.setFixedHeight(inner)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
            button.setAccessibleName(f"{name}: {words}")
            group.addButton(button, index)
            line.addWidget(button)
            if (mark is None and current is None) or (mark is not None and current is not None
                                                      and bool(current) == mark):
                button.setChecked(True)
        bar.setFixedHeight(inner + 2)
        return bar, group

    def account_marks(self) -> dict[int, bool | None]:
        """The marks changed since the dialog opened -- the window saves these on OK."""
        changed = {}
        for account_id, group in self.account_groups.items():
            chosen = ui_rules.STEAM_ACCOUNT_MARKS[max(0, group.checkedId())][0]
            if chosen != self._account_marks_opened.get(account_id):
                changed[account_id] = chosen
        return changed

    def _ringed(self, widget) -> bool:
        """Buttons and size boxes always; a switch only when the keyboard or the pad moved
        there -- the dialog hands its first switch the focus on opening, and a ring nobody
        asked for reads as a selection (Phase 35). The key field shows its focus itself, and
        a choice in a segmented switch is ringed inside, as the design rings one (Phase 75)."""
        if isinstance(widget, (ToggleSwitch, AccentSwatch)):
            # A swatch too (Phase 99): the dialog hands the first one the focus on opening, and a ring on Violet
            # while Teal is the one chosen read as two choices.
            return self.testAttribute(Qt.WidgetAttribute.WA_KeyboardFocusChange)
        if widget is not None and widget.objectName() == "Segment":
            return False
        return isinstance(widget, (QPushButton, QComboBox))

    # -- behaviour --------------------------------------------------------------------------

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # Never taller than most of the screen: the sections scroll instead (a TV at 300%
        # hands the app a 1280x720 canvas).
        screen = self.screen().availableGeometry() if self.screen() else None
        if screen is not None:
            wanted = self.sizeHint().height()
            self.resize(self.width(), min(wanted, round(screen.height() * ui_rules.SETTINGS_SCREEN_FRACTION)))
        chosen = self.accent_swatches.get(self.accent())
        if self._focus == "roots":
            # Opened from the empty library's button: straight to the Game folders row.
            QTimer.singleShot(0, self._show_roots)
        elif self._pad_first:
            # Marked as a keyboard move, so the first control wears its ring straight away -- the accent chosen
            # since Phase 99, the first row.
            self.setAttribute(Qt.WidgetAttribute.WA_KeyboardFocusChange, True)
            chosen.setFocus(Qt.FocusReason.OtherFocusReason)
        else:
            # At a desk, the first control too, with no ring (Phase 99). Without this Qt hands a dialog whose first
            # control is a push button -- the swatches are -- to its default button, OK.
            chosen.setFocus(Qt.FocusReason.OtherFocusReason)

    def _show_roots(self) -> None:
        self.scroll.ensureWidgetVisible(self.roots_row, 0, max(20, round(40 * self.scale)))
        self.setAttribute(Qt.WidgetAttribute.WA_KeyboardFocusChange, True)
        self.roots_editor.add_button.setFocus(Qt.FocusReason.TabFocusReason)

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        # getattr: setting the window title sends a change event before __init__ is done.
        if (getattr(self, "_pad_first", False) and event.type() == QEvent.Type.ActivationChange
                and self.isActiveWindow()):
            # Windows making the dialog active clears Qt's "reached by keyboard" mark -- a
            # test caught the ring gone a moment after opening. On a couch the pad is the
            # keyboard, so put it back once the activation has finished.
            QTimer.singleShot(0, self._mark_pad_focus)

    def _mark_pad_focus(self) -> None:
        self.setAttribute(Qt.WidgetAttribute.WA_KeyboardFocusChange, True)
        focused = self.focusWidget()
        if focused is not None:
            focused.update()
        self.focus_ring.refresh()

    def sizeHint(self):
        """Tall enough for every section without scrolling -- showEvent caps it to the screen.

        A scroll area asks for little of its own, so its share of the hint is swapped for
        the full height of what it holds.
        """
        hint = super().sizeHint()
        scroll = getattr(self, "scroll", None)
        if scroll is not None and scroll.widget() is not None:
            body = scroll.widget().sizeHint().height()
            hint.setHeight(hint.height() - scroll.sizeHint().height() + body)
        return hint

    def _follow_focus(self, _old, new) -> None:
        if new is None or not self.scroll.widget().isAncestorOf(new):
            return
        # The margin is kept even for a control already wholly in view. Qt's
        # ensureWidgetVisible keeps it only for one that is not, so a control touching the
        # view's edge kept its ring -- drawn 2 px outside it -- cut off (found in Phase 63).
        margin = max(20, round(40 * self.scale))
        centre = new.mapTo(self.scroll.widget(), new.rect().center())
        self.scroll.ensureVisible(centre.x(), centre.y(), new.width() // 2, new.height() // 2 + margin)

    def _ask_where_to_save(self) -> str:
        default = Path.home() / "Desktop" / f"GameLauncher-diagnostics-{date.today().isoformat()}.zip"
        chosen, _filter = QFileDialog.getSaveFileName(self, "Save diagnostics", str(default), "Zip files (*.zip)")
        return chosen

    def _ask_where_to_save_analysis(self) -> str:
        from logic import analysis

        default = Path.home() / "Desktop" / analysis.default_name()
        chosen, _filter = QFileDialog.getSaveFileName(self, "Save the anonymous export", str(default),
                                                      "JSON files (*.json)")
        return chosen

    def _save_analysis(self) -> None:
        """Show what the anonymous export holds, then save it where the user says (Phase 80).

        The participant's code is read from config.json itself, not from the settings this dialog
        was opened with (the window's copy does not hold it), and written there after the first
        file is saved -- so every export from this PC carries one code.
        """
        from data_access import config_io
        from logic import analysis
        from presentation import ui_analysis

        if self._store is None:
            self.analysis_status.setText("No library is open to describe.")
            return
        code, new = analysis.participant(config_io.load_saved())
        dialog = ui_analysis.AnalysisDialog(analysis.summary(analysis.build(self._store, code), paid_line=False),
                                            self.scale, tv=self._tv, parent=self)
        self.analysis_dialog = dialog
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        include_paid = dialog.include_paid.isChecked()
        self.analysis_dialog = None
        if not accepted:
            return
        chosen = self.choose_analysis_path()
        if not chosen:
            return
        data = analysis.build(self._store, code, include_paid=include_paid)
        try:
            written = analysis.write(Path(chosen), data, self._store.personal_values())
        except analysis.Refused as exc:
            self.analysis_status.setText(f"Not saved: {exc} turned up in it, and nothing personal may leave. "
                                         "Save diagnostics and send that instead, so it can be fixed.")
            return
        except OSError as exc:
            log.error("the anonymous export could not be written to %s: %s", chosen, exc)
            self.analysis_status.setText(f"Could not save it there: {exc}")
            return
        if new and not config_io.save_config({rules.ANALYSIS_ID_SETTING: code}):
            log.warning("the anonymous export's code could not be kept in config.json")
        self.analysis_status.setText(f"Saved as {written}. Open it with Notepad to see everything in it; "
                                     "sending it is up to you.")

    def _save_diagnostics(self) -> None:
        """Write the bundle where the user says, and say where it went -- in the row, not a box."""
        from logic import diagnostics

        if self._store is None:
            self.diagnostics_status.setText("No library is open to describe.")
            return
        chosen = self.choose_diagnostics_path()
        if not chosen:
            return
        try:
            import PySide6

            bundle = diagnostics.write(Path(chosen), self._store,
                                       about_extra={"PySide6": PySide6.__version__, "Qt": qVersion()})
        except OSError as exc:
            log.error("diagnostics could not be written to %s: %s", chosen, exc)
            self.diagnostics_status.setText(f"Could not save it there: {exc}")
            return
        self.diagnostics_status.setText(f"Saved as {bundle.path}. Send that file to whoever is helping you.")

    def done(self, result) -> None:
        # The focus hook is the application's, so it has to be let go of with the dialog.
        try:
            QApplication.instance().focusChanged.disconnect(self._follow_focus)
        except (RuntimeError, TypeError) as exc:
            log.debug("focus hook already gone: %s", exc)
        self.focus_ring.detach()
        super().done(result)

    def _show_key(self, on: bool) -> None:
        self.sgdb_key.setEchoMode(QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password)
        self.show_key.setText("Hide" if on else "Show")

    def _restore(self) -> None:
        """Hand over to the restore dialog, and get out of the way if it succeeds.

        Closing matters as much as restoring: this dialog is still holding the settings it
        was opened with, and clicking OK afterwards would write them back over the ones
        that were just restored.
        """
        dialog = ui_backups.RestoreDialog(self)
        if dialog.exec() == ui_backups.RESTORE_DONE:
            self.restore_message = dialog.message
            self.done(DATA_REPLACED)

    def _export(self) -> None:
        ui_transfer.export_flow(self, self._config, store=self._store)

    def _import(self) -> None:
        """An import rewrites both files, so this dialog has to stand down afterwards."""
        report = ui_transfer.import_flow(self, self._known_keys, store=self._store)
        if report is not None and report.ok:
            self.restore_message = report.message
            self.done(DATA_REPLACED)

    def _open_save_backups(self) -> None:
        import os

        from logic import save_backup

        folder = save_backup.backups_root()
        folder.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(folder))
        except OSError as exc:
            log.error("could not open %s: %s", folder, exc)

    def _test_key(self) -> None:
        """Ask SteamGridDB whether the pasted key works, and say so plainly."""
        from web import steamgriddb

        self.sgdb_status.setText("Checking...")
        QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        QApplication.processEvents()
        try:
            ok, message = steamgriddb.check_key(self.sgdb_key.text())
        finally:
            QGuiApplication.restoreOverrideCursor()
        self.sgdb_status.setText(("✓  " if ok else "✕  ") + message)

    def _show_notes(self, number: str, notes: str) -> None:
        """What's new (Phase 106), over Settings: a version's notes and Close."""
        from presentation import ui_whats_new

        ui_whats_new.WhatsNewDialog(number, notes, self.scale, tv=self._tv, parent=self).exec()

    def _update_covers_row(self, *_args) -> None:
        """Missing covers: the count, and the button pressable only with a key and network lookups on."""
        from logic import fill_covers
        from web import steamgriddb

        words, enabled = fill_covers.row_words(len(self._covers.missing_covers()),
                                               steamgriddb.configured(self.sgdb_key.text()),
                                               self.network_box.isChecked())
        self.covers_status.setText(words)
        self.fill_covers_button.setEnabled(enabled)

    def _fill_covers(self) -> None:
        self._covers.fill_missing_covers(self, self.sgdb_key.text().strip())
        self._update_covers_row()

    def accent(self) -> str:
        """The swatch chosen (Phase 99)."""
        return next((n for n, s in self.accent_swatches.items() if s.isChecked()), ui_rules.ACCENT_DEFAULT)

    def values(self) -> dict:
        return {
            ui_rules.ACCENT_KEY: self.accent(),
            "reduce_animations": self.reduce_box.isChecked(),
            "ui_scale": float(self.scale_box.currentData()),
            "library_layout": ui_rules.LAYOUT_RAIL if self.rail_box.isChecked() else ui_rules.LAYOUT_TOP,
            "enable_controller": self.controller_box.isChecked(),
            "tv_mode": self.tv_box.isChecked(),
            "tv_scale": float(self.tv_scale_box.currentData()),
            "startup_scan": self.startup_scan_box.isChecked(),
            "watch_folders": self.watch_box.isChecked(),
            "backup_saves": self.saves_box.isChecked(),
            "allow_network": self.network_box.isChecked(),
            "steamgriddb_key": self.sgdb_key.text().strip(),
            "roots": self.roots_editor.folders(),
            rules.KEEP_RUNNING_KEY: self.keep_box.isChecked() or self.start_box.isChecked(),
            rules.WATCH_GAMES_KEY: self.observe_box.isChecked(),
            rules.RATE_ASK_KEY: self.rate_box.isChecked(),
        }

    def start_with_windows(self) -> bool:
        """The second switch, as chosen -- never on without the first (the answers hold that too)."""
        return self.start_box.isChecked()


class MarkButton(QPushButton):
    """One choice of a Steam account's mark.

    Qt treats an exclusive group as one stop for Tab, and lands on whichever choice comes
    first or last; this one hands the focus on to the choice that is chosen, so up and down
    land on what the account says now. From there the arrow keys -- the pad's left and right
    -- move the choice along the row and choose it as they go (Qt does that for a group whose
    focused button is the chosen one), as left and right change a size.
    """

    def focusInEvent(self, event) -> None:
        super().focusInEvent(event)
        chosen = self.group().checkedButton() if self.group() is not None else None
        if (chosen is not None and chosen is not self and event.reason() in (
                Qt.FocusReason.TabFocusReason, Qt.FocusReason.BacktabFocusReason)):
            chosen.setFocus(event.reason())


def watch_words(config: dict) -> str:
    """The third switch's quieter line, and since when sessions have been observed (Phase 93)."""
    since = config.get(rules.WATCH_SINCE_KEY)
    if not since:
        return WATCH_HINT
    from datetime import date

    try:
        day = humanize.day(date.fromisoformat(since), year=True)
    except ValueError:
        return WATCH_HINT
    return f"{WATCH_HINT} Sessions seen since {day}."


def _when(stamp: str | None) -> str:
    """'3 days ago' for a stored UTC instant; 'at an unknown time' for none."""
    if not stamp:
        return "at an unknown time"
    from datetime import datetime

    try:
        return humanize.when(datetime.fromisoformat(stamp))
    except ValueError:
        return "at an unknown time"


def wishlist_words(account: dict) -> str:
    """What the account's newest wishlist read found (Phase 86). A private list answers as an empty
    one does, so "nothing to read" says both -- the launcher cannot change a Steam profile setting."""
    if not account.get("wishlist_read_at"):
        return "Wishlist: not read yet (read once a day with a scan, the network on)"
    when = _when(account["wishlist_read_at"])
    if account.get("wishlist_state") == "items":
        items = account.get("wishlist_items") or 0
        return f"Wishlist: {items} game{'s' if items != 1 else ''} · read {when}"
    return f"Wishlist: nothing to read -- private on Steam, or empty · asked {when}"


def open_in_browser(url: str) -> bool:
    """A web page in the user's own browser: the release page, SteamGridDB's key page (Phase 79)."""
    opened = QDesktopServices.openUrl(QUrl(url))
    if not opened:
        log.warning("could not open %s in the browser", url)
    return opened


def update_text(answer, allowed: bool, why: str) -> str:
    """The Updates row's words: what the last check found, or why there is none (Phase 79)."""
    if not allowed and why == "run from source":
        return "This copy runs from source and never asks: it is always the newest."
    if not allowed:
        return "Not checked: Allow network lookups is off."
    if answer is None:
        return "Not checked yet. An installed copy asks GitHub once a day, a few seconds after it starts."
    when = humanize.moment(answer.checked_at.astimezone())
    if not answer.reached:
        return f"GitHub could not be reached ({when}); it is asked again in a few hours."
    if answer.newer:
        published = f", published {humanize.day(answer.published, year=True)}" if answer.published else ""
        return (f"Version {answer.latest} is out{published}. Open the download page and run the new "
                "Setup.exe over this one; everything is kept.")
    return f"You have the newest version. Checked {when[0].lower()}{when[1:]}."


class StatusLine(QLabel):
    """A row's result line -- where a file was saved, or why not: hidden until it has something to
    say. An empty one left a gap under its row (Diagnostics' since Phase 77; seen in Phase 80)."""

    def __init__(self) -> None:
        super().__init__()
        self.hide()

    def setText(self, text: str) -> None:  # noqa: N802 -- Qt's name
        super().setText(text)
        self.setVisible(bool(text))


class SettingRow(QWidget):
    """A setting's name, a quieter line under it, and its controls on the right.

    Clicking anywhere on the words of a row with a switch flips the switch -- the whole
    row is the target, as it is in Windows' own settings.
    """

    def __init__(self, title: str, hint: str, controls, scale: float) -> None:
        super().__init__()
        self.setObjectName("SettingRow")
        self.title = QLabel(title)
        self.title.setObjectName("SettingTitle")
        self.title.setWordWrap(True)
        self.hint = QLabel(hint)
        self.hint.setObjectName("SettingHint")
        self.hint.setWordWrap(True)
        self.controls = list(controls)
        switches = [c for c in self.controls if isinstance(c, ToggleSwitch)]
        self.switch = switches[0] if switches else None
        for control in self.controls:
            control.setAccessibleName(title)

        words = QVBoxLayout()
        words.setContentsMargins(0, 0, 0, 0)
        words.setSpacing(max(1, round(2 * scale)))
        words.addWidget(self.title)
        words.addWidget(self.hint)
        line = QHBoxLayout()
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(max(8, round(12 * scale)))
        line.addLayout(words, 1)
        for control in self.controls:
            line.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
        self._layout = QVBoxLayout(self)
        pad = max(6, round(12 * scale))
        self._layout.setContentsMargins(0, pad, 0, pad)
        self._layout.setSpacing(max(4, round(8 * scale)))
        self._layout.addLayout(line)
        if self.switch is not None:
            self.setCursor(Qt.CursorShape.PointingHandCursor)

    def add_below(self, item) -> None:
        """Something that needs the row's full width, under its words -- the key field."""
        if isinstance(item, QWidget):
            self._layout.addWidget(item)
        else:
            self._layout.addLayout(item)

    def mouseReleaseEvent(self, event) -> None:
        if self.switch is not None and event.button() == Qt.MouseButton.LeftButton:
            self.switch.click()
            return
        super().mouseReleaseEvent(event)


def stylesheet(scale: float, ring: int = ui_rules.CONTINUE_FOCUS_RING) -> str:
    """The settings dialog's look. `ring` is the tiles' focus width, TV's included."""
    s = lambda value: max(1, round(value * scale))  # noqa: E731
    ring = s(max(ring, ui_rules.CONTINUE_FOCUS_RING))
    display = ui_icons.display_family()
    corner = s(ui_rules.SETTINGS_SEGMENT_HEIGHT) // 2  # a Steam account's mark: round ends
    inner = max(1, corner - 1)
    return f"""
    QDialog#Settings {{ background: {ui_rules.COLOR_BACKGROUND}; }}
    QLabel#SettingsTitle {{
        font-family: "{display}";
        font-size: {s(ui_rules.SETTINGS_TITLE_PX)}px;
        font-weight: {ui_rules.HEADING_WEIGHT};
    }}
    QScrollArea#SettingsScroll, QWidget#SettingsBody {{ background: transparent; border: none; }}
    QScrollArea#SettingsScroll > QWidget > QWidget {{ background: transparent; }}
    /* The accent's swatches paint themselves (Phase 99): no box of a button around them. */
    QPushButton#AccentSwatch, QPushButton#AccentSwatch:hover, QPushButton#AccentSwatch:pressed {{
        background: transparent; border: none; padding: 0;
    }}
    QLabel#SettingSection {{
        font-family: "{display}";
        font-size: {s(ui_rules.SETTINGS_SECTION_PX)}px;
        font-weight: {ui_rules.HEADING_WEIGHT};
        color: {ui_rules.COLOR_TEXT_SOFT};
        padding-top: {s(6)}px;
    }}
    QFrame#SettingGroup {{
        background: {ui_rules.COLOR_SURFACE};
        border: 1px solid {ui_rules.COLOR_CARD_BORDER};
        border-radius: {s(ui_rules.DETAIL_CARD_RADIUS)}px;
    }}
    QFrame#SettingLine {{ background: {ui_rules.COLOR_CARD_BORDER}; border: none; }}
    QWidget#SettingRow, QWidget#SettingRow QLabel {{ background: transparent; }}
    QLabel#SettingTitle {{ font-size: {s(ui_rules.SETTINGS_ROW_PX)}px; color: {ui_rules.COLOR_TEXT}; }}
    QLabel#SettingHint {{ font-size: {s(ui_rules.SETTINGS_HINT_PX)}px; color: {ui_rules.COLOR_TEXT_MUTED}; }}
    /* The key field shows its own focus, as the design's inputs do; every other control
       is ringed outside by the dialog's FocusRing (Phase 58). */
    QDialog#Settings QLineEdit:focus {{ border: {ring}px solid {ui_rules.TILE_FOCUS_COLOR}; }}
    /* A Steam account's mark (Phase 75): the game page's segmented switch, at this size. */
    QDialog#Settings QFrame#SegmentBar {{
        background: transparent;
        border: 1px solid {ui_rules.COLOR_DIVIDER};
        border-radius: {corner}px;
    }}
    QDialog#Settings QFrame#SegmentLine {{ background: {ui_rules.COLOR_DIVIDER}; border: none; }}
    QDialog#Settings QPushButton#Segment {{
        background: transparent;
        border: 1px solid transparent;
        border-radius: 0;
        padding: 0 {s(ui_rules.DETAIL_SEGMENT_SIDE_PADDING)}px;
        font-size: {s(ui_rules.DETAIL_SEGMENT_PX)}px;
        font-weight: {ui_rules.BODY_WEIGHT};
        color: {ui_rules.COLOR_TEXT};
    }}
    QDialog#Settings QPushButton#Segment[edge="first"] {{
        border-top-left-radius: {inner}px; border-bottom-left-radius: {inner}px; }}
    QDialog#Settings QPushButton#Segment[edge="last"] {{
        border-top-right-radius: {inner}px; border-bottom-right-radius: {inner}px; }}
    QDialog#Settings QPushButton#Segment:hover {{ background: {ui_rules.COLOR_SECONDARY_HOVER}; }}
    QDialog#Settings QPushButton#Segment:checked, QDialog#Settings QPushButton#Segment:checked:hover {{
        background: transparent;
        border-color: {ui_rules.COLOR_ACCENT};
        color: {ui_rules.COLOR_ACCENT};
    }}
    /* The ring is wider than the 1 px edge, so the sides give up what it takes: the words keep
       their room, and a choice is never squeezed by being focused. */
    QDialog#Settings QPushButton#Segment:focus {{
        border: {ring}px solid {ui_rules.TILE_FOCUS_COLOR};
        padding: 0 {max(0, s(ui_rules.DETAIL_SEGMENT_SIDE_PADDING) - (ring - 1))}px;
    }}
    """
