"""The "find cover online" picker: Steam search results with their thumbnails.

Shown whenever the automatic match declined or got it wrong. The point is that the choice
is yours and visible -- you look at the pictures and pick, rather than trusting a score.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)

from shared.models import ROLE_COVER, ROLE_LABELS

log = logging.getLogger(__name__)

APPID_ROLE = Qt.ItemDataRole.UserRole
THUMBNAIL_SIZE = QSize(184, 69)


class CoverPickerDialog(QDialog):
    def __init__(
        self,
        game_name: str,
        candidates: list,
        thumbnails: dict,
        parent=None,
        role: str = ROLE_COVER,
    ) -> None:
        super().__init__(parent)
        label = ROLE_LABELS.get(role, role)
        self.role = role
        self.setWindowTitle(f"{label.capitalize()} for {game_name}")
        self.setMinimumSize(560, 460)

        shape = "tall cover" if role == ROLE_COVER else "wide banner"
        heading = QLabel(
            f"Results for <b>{game_name}</b>. Pick the one to use as its {shape}:"
        )
        heading.setWordWrap(True)

        self.list = QListWidget()
        self.list.setIconSize(THUMBNAIL_SIZE)
        self.list.setSpacing(2)
        self.list.itemDoubleClicked.connect(lambda _item: self.accept())

        for candidate in candidates:
            item = QListWidgetItem(candidate.label)
            item.setData(APPID_ROLE, candidate)
            blob = thumbnails.get((candidate.source, candidate.ident))
            if blob:
                pixmap = QPixmap()
                if pixmap.loadFromData(blob):
                    item.setIcon(QIcon(pixmap))
                else:
                    log.warning("thumbnail for %s %s would not decode", candidate.source, candidate.ident)
            item.setToolTip(
                f"{candidate.source} id {candidate.ident} · name match {candidate.ratio:.0%}"
            )
            self.list.addItem(item)

        if self.list.count():
            self.list.setCurrentRow(0)

        note = QLabel(
            f"Nothing here? Close this and set a {label} from a file instead. "
            f"A {label} you dislike can always be removed, and this does not touch the "
            f"{'banner' if role == ROLE_COVER else 'cover'}."
        )
        note.setObjectName("Meta")
        note.setWordWrap(True)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Use this cover")

        layout = QVBoxLayout(self)
        layout.addWidget(heading)
        layout.addWidget(self.list, 1)
        layout.addWidget(note)
        layout.addWidget(buttons)

    def chosen(self):
        """The selected ArtCandidate, or None."""
        item = self.list.currentItem()
        return item.data(APPID_ROLE) if item is not None else None
