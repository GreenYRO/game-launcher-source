"""Putting a copy of a game's saves back: pick one, confirm, restore.

Everything that can destroy anything lives in save_backup.restore, where no caller can skip
it: the zip is checked first, the saves there now are copied, and what is replaced goes to
the Recycle Bin. This file only asks, and refuses while the game is running -- the window
holds the tracker, so the refusal belongs on this side.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QVBoxLayout,
)

from shared import humanize
from shared import rules
from logic import save_backup
from logic import saves

log = logging.getLogger(__name__)


def describe(backup: save_backup.Backup, earlier: bool) -> str:
    reason = backup.manifest.get("reason", "")
    text = f"{humanize.moment(backup.made_at)}   —   {reason}   ({humanize.size(backup.size)})"
    if not earlier:
        return text
    # Named, since Phase 36 offers copies whose name is only like this game's -- GOG's
    # "The Witcher 3: Wild Hunt - Game of the Year Edition" for "The Witcher 3".
    made_for = str(backup.manifest.get("game", "")).strip()
    return text + (f"   · from an earlier install ({made_for})" if made_for
                   else "   · from an earlier install")


def choice_args(window, view) -> tuple:
    """What save_backup.choices needs to know about this game and the library."""
    record = window.overrides.get(view.key)
    return (view.key, view.display_name, tuple(record.get(rules.EARLIER_KEYS_KEY) or ()),
            tuple(window.by_key.keys()))


class SaveRestoreDialog(QDialog):
    def __init__(self, view, parent=None, choices=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Restore saves -- {view.display_name}")
        self.setMinimumWidth(560)
        self.choices = (save_backup.choices(view.key, view.display_name)
                        if choices is None else choices)

        intro = QLabel(
            "Copies of this game's saves, newest first. One is made after each session you "
            "start from here, and always before the game is uninstalled."
        )
        intro.setWordWrap(True)

        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        for number, (backup, earlier) in enumerate(self.choices):
            item = QListWidgetItem(describe(backup, earlier))
            item.setData(Qt.ItemDataRole.UserRole, number)
            self.list.addItem(item)
        if self.choices:
            self.list.setCurrentRow(0)

        note = QLabel(
            "Restoring puts the copy back where the saves live. The saves there now are "
            "copied first and moved to the Recycle Bin, so this can be undone."
        )
        note.setObjectName("Meta")
        note.setWordWrap(True)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        self.ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.ok_button.setText("Restore...")
        self.ok_button.setEnabled(bool(self.choices))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        if not self.choices:
            empty = QLabel("There are no copies of this game's saves yet.")
            empty.setObjectName("Meta")
            layout.addWidget(empty)
        layout.addWidget(self.list, 1)
        layout.addWidget(note)
        layout.addWidget(buttons)
        self.list.setFocus()

    def chosen(self):
        item = self.list.currentItem()
        return None if item is None else self.choices[item.data(Qt.ItemDataRole.UserRole)]


def restore_flow(window, view) -> None:
    """The menu's "Restore saves...": refuse, pick, confirm, restore, and say what happened."""
    if window.tracker.is_running(view.key):
        QMessageBox.information(
            window, "Close the game first",
            f"{view.display_name} is running, and its save files are open. Close it, then "
            "restore.",
        )
        return
    dialog = SaveRestoreDialog(view, window, save_backup.choices(*choice_args(window, view)))
    if dialog.exec() != QDialog.DialogCode.Accepted or dialog.chosen() is None:
        return
    backup, _earlier = dialog.chosen()
    # Only the places a copy really goes back to: a crash report's folder in a copy made
    # before Phase 36 is left out by the restore, so it is not promised here either.
    places = [p for p in save_backup.targets(backup, view.entry.install_dir)
              if saves.could_be_save_folder(p)]

    box = QMessageBox(window)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle("Restore these saves?")
    box.setText(f"Put back {view.display_name}'s saves from {humanize.moment(backup.made_at)}?")
    box.setInformativeText(
        "They go back to:\n" + "\n".join(places)
        + "\n\nThe saves there now are copied first, then moved to the Recycle Bin."
    )
    go = box.addButton("Restore", QMessageBox.ButtonRole.DestructiveRole)
    cancel = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
    # The uninstall rule: Cancel is the default, the escape and the focus -- a stray Return
    # or a stray pad A does nothing.
    box.setDefaultButton(cancel)
    box.setEscapeButton(cancel)
    cancel.setFocus()
    box.exec()
    if box.clickedButton() is not go:
        return

    QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
    try:
        ok, message = save_backup.restore(
            backup, key=view.key, name=view.display_name,
            install_dir=view.entry.install_dir, hwnd=int(window.winId()),
        )
    finally:
        QApplication.restoreOverrideCursor()
    log.info("restore of %s from %s: %s", view.key, backup.path.name, message)
    if ok:
        QMessageBox.information(window, "Saves restored", message)
    else:
        QMessageBox.warning(window, "Saves not restored", message)
    window.reload_views()
