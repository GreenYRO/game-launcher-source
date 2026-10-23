"""The first-run question (Phase 77): "Where do you keep your games?"

Asked once, before the first scan, on a PC where the launcher has no config.json yet -- a
fresh install. It offers the folders logic/first_run found by itself, ticked; Add a folder...
and Remove; and a second question with its own switch, whether to look for Xbox Game Pass
games, on when an XboxGames folder exists on some drive. Continue scans the ticked folders;
"I only use Steam, GOG, Epic or Xbox" -- or closing it -- goes on with no folders at all,
which is a valid answer. The window writes whatever was answered, so it is never asked again.

Sized and styled like Settings, at TV size in TV mode; worked by the pad (see ui_folders).

Then a second question (Phase 79), `KeyDialog`: would they like more cover art -- a free
SteamGridDB key of their own, pasted here, or Skip. The same field as Settings' "SteamGridDB
key" (Artwork and the internet), so skipping loses nothing. A key is only ever sent to
steamgriddb.com, when they ask for a cover or press Test.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QApplication, QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QVBoxLayout)

from presentation import ui_folders
from presentation import ui_rules
from presentation import ui_settings
from presentation.ui_cards import FocusRing, ToggleSwitch
from presentation.ui_settings import SettingRow
from shared import rules

INTRO = ("The launcher finds games from Steam, GOG, Epic and Xbox by itself. Games you put on "
         "the PC some other way -- copied, unpacked, from their own installer -- it finds in "
         "the folders you choose here. You can change them later in Settings.")
FOUND = "It looked on this PC and these folders seem to hold games. Keep the ticked ones:"
NOTHING_FOUND = ("No folder on this PC looked like a games folder. Add one, or skip this if all "
                 "your games come from a store.")
SKIP = "I only use Steam, GOG, Epic or Xbox"

KEY_TITLE = "Want more cover art?"
KEY_INTRO = ("Steam has covers for its own games. For the rest -- games you put in a folder "
             "yourself, and some from GOG, Epic or Xbox -- the launcher can also look on "
             "SteamGridDB, a free site of covers made by players. For that it needs a free key "
             "from your own SteamGridDB account. It is only used when you choose a cover, and "
             "only ever sent to steamgriddb.com.")
KEY_STEPS = ("1.  Open steamgriddb.com and sign in -- with your Steam account is quickest.\n"
             "2.  In Preferences, open API and generate a key.\n"
             "3.  Copy it and paste it here.")
KEY_LATER = ("No key? Skip this: covers from Steam work without one, and the same field is in "
             "Settings, under Artwork and the internet.")


class FirstRunDialog(QDialog):
    def __init__(self, candidates, xbox_found: bool, scale: float, tv: bool = False, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("FirstRun")
        self.setWindowTitle("Where do you keep your games?")
        self.scale = scale
        self.skipped = True  # until Continue says otherwise: closing it is the same as skipping
        self.focus_ring_width = ui_rules.TV_FOCUS_RING_WIDTH if tv else ui_rules.FOCUS_RING_WIDTH

        title = QLabel("Where do you keep your games?")
        title.setObjectName("SettingsTitle")
        intro = QLabel(INTRO)
        intro.setObjectName("FirstRunText")
        intro.setWordWrap(True)
        found = QLabel(FOUND if candidates else NOTHING_FOUND)
        found.setObjectName("FirstRunText")
        found.setWordWrap(True)
        self.folders = ui_folders.FolderList(candidates, checkable=True, scale=scale)

        self.xbox = ToggleSwitch(scale=scale, animate=False)
        self.xbox.setChecked(bool(xbox_found))
        self.xbox.setProperty("ringRadius", self.xbox.sizeHint().height() / 2)
        xbox_row = SettingRow("Also look for Xbox Game Pass games",
                              "Games the Xbox app installs into an XboxGames folder."
                              + (" One was found on this PC." if xbox_found else ""), [self.xbox], scale)

        self.skip_button = QPushButton(SKIP)
        self.continue_button = QPushButton("Continue")
        self.continue_button.setDefault(True)
        for button in (self.skip_button, self.continue_button):
            button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.skip_button.clicked.connect(self._skip)
        self.continue_button.clicked.connect(self._continue)
        buttons = QHBoxLayout()
        buttons.addWidget(self.skip_button)
        buttons.addStretch(1)
        buttons.addWidget(self.continue_button)

        layout = QVBoxLayout(self)
        margin = max(12, round(24 * scale))
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.setSpacing(max(8, round(12 * scale)))
        layout.addWidget(title)
        layout.addWidget(intro)
        layout.addWidget(found)
        layout.addWidget(self.folders)
        layout.addWidget(xbox_row)
        layout.addLayout(buttons)
        self.setMinimumWidth(round(ui_rules.FIRST_RUN_WIDTH * scale))
        # The ring outside whichever control has the focus, as Settings has it (Phase 58).
        self.focus_ring = FocusRing(self, self._ringed, scale=lambda: self.scale)

    def _ringed(self, widget) -> bool:
        if isinstance(widget, ToggleSwitch):
            return self.testAttribute(Qt.WidgetAttribute.WA_KeyboardFocusChange)
        return isinstance(widget, QPushButton)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # The list first: on a couch the pad starts on the folders, with the first one current.
        self.folders.list.setFocus(Qt.FocusReason.OtherFocusReason)
        if self.folders.list.count() and self.folders.list.currentRow() < 0:
            self.folders.list.setCurrentRow(0)

    def _skip(self) -> None:
        self.skipped = True
        self.accept()

    def _continue(self) -> None:
        self.skipped = False
        self.accept()

    def answer(self) -> tuple[list[str], bool]:
        """The folders to scan -- none when skipped or closed -- and whether to look for Xbox games."""
        roots = [] if self.skipped else self.folders.folders()
        return roots, self.xbox.isChecked()

    def done(self, result) -> None:
        self.focus_ring.detach()
        super().done(result)


class KeyDialog(QDialog):
    """The second first-run question (Phase 79): a SteamGridDB key, or Skip."""

    def __init__(self, scale: float, tv: bool = False, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("FirstRun")
        self.setWindowTitle(KEY_TITLE)
        self.scale = scale
        self.tv = tv
        self.saved = False  # until Save key: closing it is skipping

        title = QLabel(KEY_TITLE)
        title.setObjectName("SettingsTitle")
        intro = QLabel(KEY_INTRO)
        intro.setObjectName("FirstRunText")
        intro.setWordWrap(True)
        steps = QLabel(KEY_STEPS)
        steps.setObjectName("FirstRunText")
        steps.setWordWrap(True)
        self.open_button = QPushButton("Open steamgriddb.com")
        self.open_button.clicked.connect(lambda: ui_settings.open_in_browser(rules.SGDB_KEY_PAGE_URL))
        self.key = QLineEdit()
        self.key.setObjectName("FirstRunKey")
        self.key.setPlaceholderText("paste your SteamGridDB key")
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.test_button = QPushButton("Test")
        self.test_button.clicked.connect(self._test)
        self.status = QLabel()
        self.status.setObjectName("FirstRunText")
        self.status.setWordWrap(True)
        self.status.hide()  # until Test has something to say: an empty line would leave a gap
        later = QLabel(KEY_LATER)
        later.setObjectName("FirstRunText")
        later.setWordWrap(True)

        self.skip_button = QPushButton("Skip")
        self.save_button = QPushButton("Save key")
        self.save_button.setDefault(True)
        self.save_button.setEnabled(False)
        self.key.textChanged.connect(self._key_changed)
        for button in (self.open_button, self.test_button, self.skip_button, self.save_button):
            button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.skip_button.clicked.connect(self.reject)
        self.save_button.clicked.connect(self._save)

        open_line = QHBoxLayout()
        open_line.addWidget(self.open_button)
        open_line.addStretch(1)
        key_line = QHBoxLayout()
        key_line.addWidget(self.key, 1)
        key_line.addWidget(self.test_button)
        buttons = QHBoxLayout()
        buttons.addWidget(self.skip_button)
        buttons.addStretch(1)
        buttons.addWidget(self.save_button)

        layout = QVBoxLayout(self)
        margin = max(12, round(24 * scale))
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.setSpacing(max(8, round(12 * scale)))
        for widget in (title, intro, steps):
            layout.addWidget(widget)
        layout.addLayout(open_line)
        layout.addLayout(key_line)
        layout.addWidget(self.status)
        layout.addWidget(later)
        layout.addLayout(buttons)
        self.setMinimumWidth(round(ui_rules.FIRST_RUN_WIDTH * scale))
        self.focus_ring = FocusRing(self, lambda widget: isinstance(widget, QPushButton),
                                    scale=lambda: self.scale)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # At a desk the field, ready for a paste; on a couch, where nothing can be typed, Skip.
        (self.skip_button if self.tv else self.key).setFocus(Qt.FocusReason.OtherFocusReason)

    def _key_changed(self, text: str) -> None:
        self.save_button.setEnabled(bool(text.strip()))
        self.status.clear()
        self.status.hide()

    def _test(self) -> None:
        """Ask SteamGridDB whether the key works, and say so in plain words -- as Settings' Test does."""
        from web import steamgriddb

        self.status.setText("Checking...")
        self.status.show()
        QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        QApplication.processEvents()
        try:
            ok, message = steamgriddb.check_key(self.key.text().strip())
        finally:
            QGuiApplication.restoreOverrideCursor()
        self.status.setText(("\u2713  " if ok else "\u2715  ") + message)

    def _save(self) -> None:
        if self.key.text().strip():
            self.saved = True
            self.accept()

    def answer(self) -> str:
        """The key, without the spaces a paste brings along -- or "" when skipped or closed."""
        return self.key.text().strip() if self.saved else ""

    def done(self, result) -> None:
        self.focus_ring.detach()
        super().done(result)


def stylesheet(scale: float) -> str:
    s = lambda value: max(1, round(value * scale))  # noqa: E731
    return f"""
    QDialog#FirstRun {{ background: {ui_rules.COLOR_BACKGROUND}; }}
    QLabel#FirstRunText {{ font-size: {s(ui_rules.FIRST_RUN_TEXT_PX)}px; color: {ui_rules.COLOR_TEXT_SOFT}; }}
    QDialog#FirstRun QLabel#SettingsTitle {{
        font-size: {s(ui_rules.SETTINGS_TITLE_PX)}px; font-weight: {ui_rules.HEADING_WEIGHT};
    }}
    /* The key field shows its own focus, as Settings' does (Phase 79). */
    QDialog#FirstRun QLineEdit#FirstRunKey:focus {{
        border: {s(ui_rules.CONTINUE_FOCUS_RING)}px solid {ui_rules.TILE_FOCUS_COLOR};
    }}
    """
