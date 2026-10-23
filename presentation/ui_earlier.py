"""Carrying an earlier install's history over to a game: the list, the answer, the message.

The deciding and the moving live in lineage.py; this file only asks. The game page's
"Played before?" card and the menu's "Same game as an earlier install..." both end in
carry_flow, which takes a snapshot of the library data first -- the undo, through
Settings' restore, if two games were joined that should not have been.
"""

from __future__ import annotations

import logging

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
from logic import lineage

log = logging.getLogger(__name__)

SNAPSHOT_REASON = "before-carry-over"


def _status_ms() -> int:
    from presentation.ui_window import STATUS_MS  # here, not at the top: the window imports this module

    return STATUS_MS


def describe(earlier: lineage.EarlierInstall) -> str:
    """Two lines: which game (and whether it looks like this one), then what it holds."""
    first = earlier.name + ("   · looks like this one" if earlier.why else "")
    return f"{first}\n{lineage.summary(earlier)}"


class EarlierInstallDialog(QDialog):
    """Every earlier install, the likely ones first; pick the one that was this game."""

    def __init__(self, view, earlier: list, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Same game as an earlier install -- {view.display_name}")
        self.setMinimumWidth(720)
        self.setMinimumHeight(520)  # room for five or six earlier installs before it scrolls
        self.earlier = earlier

        intro = QLabel(
            f"Games you had installed before, which are not installed now. Pick the one that "
            f"was {view.display_name}, and its play time, sessions, note, mark, star and save "
            "copies move over to it."
        )
        intro.setWordWrap(True)

        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        # Rows wrap rather than run off the side: the first render showed a sideways
        # scrollbar and hid "looks like this one" at the end of the line.
        self.list.setWordWrap(True)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setSpacing(4)
        for number, item in enumerate(earlier):
            row = QListWidgetItem(describe(item))
            row.setData(Qt.ItemDataRole.UserRole, number)
            self.list.addItem(row)
        if earlier:
            self.list.setCurrentRow(0)

        note = QLabel(
            "A copy of your library data is kept first, so this can be undone from Settings "
            "-> Backups -> Restore."
        )
        note.setObjectName("Meta")
        note.setWordWrap(True)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        self.ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.ok_button.setText("Carry it over")
        self.ok_button.setEnabled(bool(earlier))
        self.ok_button.setDefault(True)  # the pad's A on the list presses this
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(self.list, 1)
        layout.addWidget(note)
        layout.addWidget(buttons)
        self.list.setFocus()

    def chosen(self) -> lineage.EarlierInstall | None:
        item = self.list.currentItem()
        return None if item is None else self.earlier[item.data(Qt.ItemDataRole.UserRole)]


def message(carried: lineage.Carried) -> str:
    parts = []
    if carried.seconds:
        parts.append(f"{humanize.playtime(carried.seconds)} of play")
    if carried.sessions:
        parts.append(f"{carried.sessions} session{'s' if carried.sessions != 1 else ''}")
    if carried.copies:
        parts.append(f"{carried.copies} cop{'y' if carried.copies == 1 else 'ies'} of its saves")
    parts.extend(carried.fields)
    return f"Carried over from {carried.name}: {', '.join(parts) or 'its record'}"


def carry_flow(window, view, earlier_key: str, earlier_name: str = "") -> bool:
    """Snapshot, carry, refresh, say what moved. Returns whether it happened."""
    backups.snapshot(SNAPSHOT_REASON)
    try:
        carried = lineage.carry_over(
            window.overrides, earlier_key, view.key,
            new_install_dir=view.entry.install_dir, old_name=earlier_name,
        )
    except (LookupError, ValueError) as exc:
        log.warning("could not carry %s over to %s: %s", earlier_key, view.key, exc)
        QMessageBox.warning(window, "Nothing was carried over", str(exc))
        return False
    window.reload_views()
    window.statusBar().showMessage(message(carried), _status_ms())
    return True


def not_same_flow(window, key: str, earlier_key: str) -> None:
    lineage.not_the_same(window.overrides, key, earlier_key)
    view = window.by_key.get(key)
    if view is not None and window.detail.view is not None and window.detail.view.key == key:
        window.detail.set_view(view)
    window.statusBar().showMessage(
        "Kept apart -- it will not be offered again. The ... menu can still join them.",
        _status_ms(),
    )


def pick_flow(window, view) -> None:
    """The menu's "Same game as an earlier install...": every earlier install, pick one."""
    earlier = lineage.everything(view, window.overrides, window.by_key.keys())
    if not earlier:
        QMessageBox.information(
            window, "No earlier installs",
            "Every game the launcher remembers is still installed, so there is nothing to "
            "carry over.",
        )
        return
    dialog = EarlierInstallDialog(view, earlier, window)
    if dialog.exec() != QDialog.DialogCode.Accepted or dialog.chosen() is None:
        return
    chosen = dialog.chosen()
    carry_flow(window, view, chosen.key, chosen.name)
