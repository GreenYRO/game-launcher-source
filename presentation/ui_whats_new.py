"""What's new (Phase 106): one version's notes, the English of its release page, in a dialog.

The window opens it once, on the first start after an update; Settings, About opens it for this version at any
time, and the Updates row for a newer one the update check has found, from the notes that answer brought. The
notes are Markdown (logic/whats_new.py finds the English under its heading), drawn by Qt's own reader -- bold,
headings, lists, a link that opens the browser. One button, Close; the text scrolls, by the wheel or by the pad's
up and down. Styled like the first-run questions, worked by the pad as every dialog.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QPalette
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QTextBrowser, QVBoxLayout

from presentation import ui_rules
from presentation.ui_cards import FocusRing

log = logging.getLogger(__name__)

TITLE = "What's new in {version}"
CLOSE = "Close"
NONE = "This copy carries no notes for {version}."


def open_link(url: QUrl) -> bool:
    """A link in the notes, in the user's own browser -- a web page only, never a file or a program."""
    if url.scheme() not in ("http", "https"):
        log.info("what's new: a link that is not a web page was not opened (%s)", url.toString())
        return False
    opened = QDesktopServices.openUrl(url)
    if not opened:
        log.warning("could not open %s in the browser", url.toString())
    return opened


class WhatsNewDialog(QDialog):
    """A version's notes, scrolling, and Close."""

    def __init__(self, number: str, notes: str, scale: float, tv: bool = False, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("FirstRun")  # the first-run questions' ground and words
        self.number = number
        self.setWindowTitle(TITLE.format(version=number))
        self.scale = scale
        self.tv = tv

        title = QLabel(TITLE.format(version=number))
        title.setObjectName("SettingsTitle")
        self.text = QTextBrowser()
        self.text.setObjectName("WhatsNewText")
        self.text.setOpenLinks(False)
        self.text.anchorClicked.connect(open_link)
        self.text.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        # Tab leaves the words, as everywhere else: a text box's own Tab steps between its links first, so the pad's up
        # at the top (sent as Backtab) stopped on a link rather than reaching Close. Links stay the mouse's.
        self.text.setTabChangesFocus(True)
        self.text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse
                                          | Qt.TextInteractionFlag.LinksAccessibleByMouse)
        palette = self.text.palette()
        palette.setColor(QPalette.ColorRole.Link, QColor(ui_rules.COLOR_ACCENT))
        self.text.setPalette(palette)
        self.text.setMarkdown(notes.strip() or NONE.format(version=number))
        self.text.setMinimumHeight(round(ui_rules.WHATS_NEW_TEXT_HEIGHT * scale))

        self.close_button = QPushButton(CLOSE)
        self.close_button.setDefault(True)
        self.close_button.setAutoDefault(True)
        self.close_button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_button.clicked.connect(self.accept)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.close_button)
        layout = QVBoxLayout(self)
        margin = max(12, round(24 * scale))
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.setSpacing(max(8, round(12 * scale)))
        layout.addWidget(title)
        layout.addWidget(self.text, 1)
        layout.addSpacing(max(4, round(6 * scale)))
        layout.addLayout(buttons)
        self.setMinimumWidth(round(ui_rules.WHATS_NEW_WIDTH * scale))
        self.focus_ring = FocusRing(self, lambda widget: isinstance(widget, QPushButton), scale=lambda: self.scale)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # The words first: the pad's up and down scroll them, A or B close.
        self.text.setFocus(Qt.FocusReason.OtherFocusReason)

    def done(self, result) -> None:
        self.focus_ring.detach()
        super().done(result)


def stylesheet(scale: float) -> str:
    s = lambda value: max(1, round(value * scale))  # noqa: E731
    return f"""
    QTextBrowser#WhatsNewText {{
        background: {ui_rules.COLOR_SURFACE}; color: {ui_rules.COLOR_TEXT_SOFT};
        border: 1px solid {ui_rules.COLOR_BORDER}; border-radius: {s(ui_rules.CONTROL_RADIUS)}px;
        padding: {s(ui_rules.WHATS_NEW_PADDING)}px; font-size: {s(ui_rules.FIRST_RUN_TEXT_PX)}px;
    }}
    """
