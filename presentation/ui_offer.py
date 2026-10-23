"""The one question (Phase 99): would they like the launcher to stay in the tray when its window closes?

1.2.6 and 1.2.7 reached the friends with "Keep running when the window is closed" off, so on their PCs the
watcher only notices games while the window is open and the daily readings are not taken. Asked once, a
second after the window first appears, by the window (`MainWindow.offer_tray`) -- never on a first run's
start, never to someone whose switch is on, never twice. "Not now" is the default and Escape: nothing
changes but the mark that it was asked. "Keep it running" turns the first switch on and nothing else;
Start with Windows is only mentioned.

Sized and styled like the first-run questions, at TV size in TV mode, worked by the pad as every dialog.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from presentation import ui_rules
from presentation.ui_cards import FocusRing

TITLE = "Keep Game Launcher running?"
TEXT = ("Game Launcher can stay in the tray when you close the window. It keeps timing a running game, "
        "notices games you start from Steam or a shortcut, and takes its daily price readings. You can "
        "quit it from the tray icon, and change this any time in Settings.")
LATER = "Settings can also start it with Windows, hidden in the tray -- under Running in the background."
KEEP = "Keep it running"
NOT_NOW = "Not now"


class TrayOfferDialog(QDialog):
    """Two answers: Keep it running (accept), Not now (reject -- the default, Escape, the close button)."""

    def __init__(self, scale: float, tv: bool = False, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("FirstRun")  # the first-run questions' ground and words
        self.setWindowTitle(TITLE)
        self.scale = scale
        self.tv = tv

        title = QLabel(TITLE)
        title.setObjectName("SettingsTitle")
        text = QLabel(TEXT)
        text.setObjectName("FirstRunText")
        text.setWordWrap(True)
        later = QLabel(LATER)
        later.setObjectName("FirstRunText")
        later.setWordWrap(True)

        self.not_now_button = QPushButton(NOT_NOW)
        self.keep_button = QPushButton(KEEP)
        self.not_now_button.setDefault(True)
        self.not_now_button.setAutoDefault(True)
        self.keep_button.setAutoDefault(False)
        for button in (self.not_now_button, self.keep_button):
            button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.not_now_button.clicked.connect(self.reject)
        self.keep_button.clicked.connect(self.accept)

        buttons = QHBoxLayout()
        buttons.addWidget(self.not_now_button)
        buttons.addStretch(1)
        buttons.addWidget(self.keep_button)
        layout = QVBoxLayout(self)
        margin = max(12, round(24 * scale))
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.setSpacing(max(8, round(12 * scale)))
        for widget in (title, text, later):
            layout.addWidget(widget)
        layout.addSpacing(max(4, round(6 * scale)))
        layout.addLayout(buttons)
        self.setMinimumWidth(round(ui_rules.TRAY_OFFER_WIDTH * scale))
        self.focus_ring = FocusRing(self, lambda widget: isinstance(widget, QPushButton), scale=lambda: self.scale)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.not_now_button.setFocus(Qt.FocusReason.OtherFocusReason)  # the default, at the desk and on the couch

    def done(self, result) -> None:
        self.focus_ring.detach()
        super().done(result)
