"""Looking at backups, and putting one back.

Kept out of ui_settings.py because a restore is not a setting: it is a destructive action
with its own list, its own confirmation and its own aftermath, and the settings dialog is
already the length it should be.

The aftermath is the awkward part. A restore replaces config.json underneath a settings
dialog that is still holding the values it was opened with, so clicking OK afterwards would
write the old settings straight back over the restored ones. The dialog therefore closes
itself with RESTORE_DONE the moment a restore succeeds, and the window reloads from disk.
"""

from __future__ import annotations

import logging
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QVBoxLayout,
)

from data_access import backups
from shared import humanize

log = logging.getLogger(__name__)

# QDialog uses 0 for Rejected and 1 for Accepted; this is a third outcome, meaning "a
# restore happened, so throw away whatever this dialog was holding".
RESTORE_DONE = 2


def open_folder(parent) -> None:
    """Show the backups folder in Explorer, creating it if nothing has been saved yet."""
    folder = backups.backup_dir()
    try:
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(str(folder))
    except OSError as exc:
        log.error("could not open %s: %s", folder, exc)
        QMessageBox.warning(parent, "Could not open folder", f"{folder}\n\n{exc}")


def describe(snap: backups.Snapshot) -> str:
    files = ", ".join(name.replace(".json", "") for name in snap.files) or "empty"
    return f"{humanize.moment(snap.taken)}   —   {files}   ({humanize.size(snap.size)})"


class RestoreDialog(QDialog):
    """Pick a snapshot, confirm, restore."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Restore a backup")
        self.setMinimumWidth(460)
        self.message = ""

        self.snapshots = backups.list_snapshots()

        intro = QLabel(
            "These are copies of your settings and your library data — playtime, the "
            "artwork you picked, renamed games. One is saved each time the launcher "
            "starts, if anything has changed since the last one."
        )
        intro.setWordWrap(True)

        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        for snap in self.snapshots:
            item = QListWidgetItem(describe(snap))
            item.setData(Qt.ItemDataRole.UserRole, snap.stamp)
            self.list.addItem(item)
        if self.snapshots:
            self.list.setCurrentRow(0)

        note = QLabel(
            "Restoring replaces your current settings and library data with the copy you "
            "pick. Your current ones are saved as a new backup first, so this can be undone."
        )
        note.setObjectName("Meta")
        note.setWordWrap(True)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        self.ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.ok_button.setText("Restore")
        self.ok_button.setEnabled(bool(self.snapshots))
        buttons.accepted.connect(self._restore)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        if not self.snapshots:
            empty = QLabel("There are no backups yet. One is saved the next time anything changes.")
            empty.setObjectName("Meta")
            empty.setWordWrap(True)
            layout.addWidget(empty)
        layout.addWidget(self.list, 1)
        layout.addWidget(note)
        layout.addSpacing(6)
        layout.addWidget(buttons)

    def selected(self) -> backups.Snapshot | None:
        item = self.list.currentItem()
        if item is None:
            return None
        stamp = item.data(Qt.ItemDataRole.UserRole)
        return next((s for s in self.snapshots if s.stamp == stamp), None)

    def _restore(self) -> None:
        snap = self.selected()
        if snap is None:
            return
        confirm = QMessageBox.question(
            self,
            "Restore this backup?",
            f"Your settings and library data will be replaced with the copy from\n"
            f"{humanize.moment(snap.taken)}.\n\n"
            "What you have now is saved as a new backup first, so you can change your mind.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        ok, message = backups.restore(snap)
        self.message = message
        if not ok:
            QMessageBox.warning(self, "Could not restore", message)
            return
        # Reported here rather than by the window, so that each flow that replaces these
        # files -- restore, import -- owns its own account of what it did.
        QMessageBox.information(self, "Restored", message)
        self.done(RESTORE_DONE)
