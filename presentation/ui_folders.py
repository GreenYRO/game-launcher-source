"""A list of game folders to edit (Phase 77): the first-run question's and Settings' alike.

The folders, one per line -- with a tick each in the first-run question, where the ones the
launcher found are offered and the user keeps the ones they want -- and Add a folder... and
Remove beside them.

A whole drive is refused (Phase 82; Phase 77 allowed it with a warning, and the first friend to
install 1.2.1 chose C:\\): the sentence under the list says why, and the folders on that drive
the first run would offer are added in its place, ticked -- someone who meant "my games are
somewhere on D:" gets the right answer in one click. One of Windows' own folders is refused the
same way, with nothing in its place. A refused folder already in config.json -- edited by hand,
or chosen before 1.2.2 -- is listed as it is and said to be not scanned; the user takes it out.

Worked by the pad as any list in a dialog is (MainWindow._drive_dialog): up and down move along
the folders and on past either end, A ticks or unticks one (the list says so with its
`padActivate` property), right reaches the buttons. Add a folder... opens Windows' own folder
picker, which a pad cannot work: that one needs the mouse or the keyboard.
"""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from logic import first_run
from presentation import ui_rules
from shared import drives

# What the line under the list says when a folder is refused (Phase 82), after the sentence
# drives.not_a_game_folder gives -- "D:\ is a whole drive, not a game folder."
INSTEAD = " The folders on it that look like game folders are added instead: keep the ones that hold games."
NOTHING_INSTEAD = " No folder on it looks like one: choose the folder that holds the games."
CHOOSE_ANOTHER = " Choose the folder that holds the games."
NOT_SCANNED = "{why} It is not scanned: remove it, and add the folder that holds the games."


class FolderList(QWidget):
    changed = Signal()

    def __init__(self, folders, *, checkable: bool, scale: float, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("FolderList")
        self.checkable = checkable
        self.list = QListWidget()
        self.list.setObjectName("FolderListView")
        self.list.setProperty("padActivate", "select")  # A ticks, never presses the dialog's default
        self.list.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        rows = ui_rules.FOLDER_LIST_ROWS
        self.list.setMinimumHeight(round(rows * ui_rules.FOLDER_LIST_ROW_PX * scale))
        self.list.setMaximumHeight(round((rows + 2) * ui_rules.FOLDER_LIST_ROW_PX * scale))
        self.list.itemChanged.connect(lambda _item: self._changed())

        self.add_button = QPushButton("Add a folder...")
        self.remove_button = QPushButton("Remove")
        for button in (self.add_button, self.remove_button):
            button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_button.clicked.connect(self._browse)
        self.remove_button.clicked.connect(self._remove)
        self.warning = QLabel()
        self.warning.setObjectName("FolderWarning")
        self.warning.setWordWrap(True)
        self.warning.hide()
        self.empty = QLabel("No folder chosen.")
        self.empty.setObjectName("SettingHint")

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.addWidget(self.add_button)
        buttons.addWidget(self.remove_button)
        buttons.addStretch(1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(max(4, round(8 * scale)))
        layout.addWidget(self.list)
        layout.addWidget(self.empty)
        layout.addLayout(buttons)
        layout.addWidget(self.warning)
        # Where Add a folder... asks; a test hands in an answer of its own.
        self.choose_folder = self._ask_windows
        self.refusal = ""  # what the last folder refused was, and what was done instead
        for folder in folders:
            self.add_folder(folder, notify=False)
        # Adding makes each folder current in turn; the pad starts on the first (found by the
        # suite: on the last, its first Down left the list and A opened the folder picker).
        if self.list.count():
            self.list.setCurrentRow(0)
        self._changed(notify=False)

    # -- the list ---------------------------------------------------------------------------

    def add_folder(self, folder: str, checked: bool = True, notify: bool = True) -> bool:
        """Add a folder, ticked; one already listed is ticked again rather than added twice."""
        folder = os.path.normpath(folder)
        for row in range(self.list.count()):
            item = self.list.item(row)
            if os.path.normcase(item.text()) == os.path.normcase(folder):
                if self.checkable:
                    item.setCheckState(Qt.CheckState.Checked)
                self.list.setCurrentItem(item)
                return False
        item = QListWidgetItem(folder)
        if self.checkable:
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self.list.addItem(item)
        self.list.setCurrentItem(item)
        self._changed(notify)
        return True

    def folders(self) -> list[str]:
        """The folders chosen: the ticked ones, or every one where there are no ticks."""
        chosen = []
        for row in range(self.list.count()):
            item = self.list.item(row)
            if not self.checkable or item.checkState() == Qt.CheckState.Checked:
                chosen.append(item.text())
        return chosen

    def all_folders(self) -> list[str]:
        return [self.list.item(row).text() for row in range(self.list.count())]

    def _browse(self) -> None:
        folder = self.choose_folder()
        if folder:
            self.choose(folder)

    def choose(self, folder: str) -> bool:
        """A folder the user picked: added -- or refused, said why, and, for a whole drive, its
        game folders added in its place (Phase 82). True when the folder itself went in."""
        why = drives.not_a_game_folder(folder)
        if not why:
            self.refusal = ""
            return self.add_folder(folder)
        if drives.is_drive_root(folder):
            instead = first_run.instead_of(folder)
            for found in instead:
                self.add_folder(found, notify=False)
            why += INSTEAD if instead else NOTHING_INSTEAD
        else:
            why += CHOOSE_ANOTHER
        self.refusal = why
        self._changed()
        return False

    def _ask_windows(self) -> str:
        current = self.list.currentItem()
        start = current.text() if current is not None else ""
        return QFileDialog.getExistingDirectory(self, "Choose a folder with games", start)

    def _remove(self) -> None:
        row = self.list.currentRow()
        if row >= 0:
            self.list.takeItem(row)
            self.refusal = ""
            self._changed()

    def _changed(self, notify: bool = True) -> None:
        lines = [self.refusal] if self.refusal else []
        lines += [NOT_SCANNED.format(why=why) for _folder, why in drives.split_roots(self.folders())[1]]
        self.warning.setText("\n".join(lines))
        self.warning.setVisible(bool(lines))
        self.empty.setVisible(self.list.count() == 0)
        self.list.setVisible(self.list.count() > 0)
        self.remove_button.setEnabled(self.list.count() > 0)
        if notify:
            self.changed.emit()


def stylesheet(scale: float) -> str:
    s = lambda value: max(1, round(value * scale))  # noqa: E731
    return f"""
    QListWidget#FolderListView {{
        background: {ui_rules.COLOR_SURFACE};
        border: 1px solid {ui_rules.COLOR_CARD_BORDER};
        border-radius: {s(ui_rules.DETAIL_CARD_RADIUS)}px;
        padding: {s(4)}px;
        font-size: {s(ui_rules.SETTINGS_ROW_PX)}px;
    }}
    QListWidget#FolderListView::item {{ padding: {s(4)}px {s(6)}px; border-radius: {s(4)}px; }}
    QListWidget#FolderListView::item:selected {{
        background: {ui_rules.COLOR_MENU_SELECTED}; color: {ui_rules.COLOR_MENU_SELECTED_TEXT};
    }}
    QListWidget#FolderListView:focus {{ border: {s(2)}px solid {ui_rules.TILE_FOCUS_COLOR}; }}
    QLabel#FolderWarning {{ font-size: {s(ui_rules.SETTINGS_HINT_PX)}px; color: {ui_rules.COLOR_ACCENT_200}; }}
    """
