"""The anonymous export's dialog (Phase 80): what the file holds, read before it is saved.

Opened from Settings, Your library data, "Anonymous export...". It says, in the library's own
numbers, what the file will hold (logic/analysis.summary) and what it never holds; one switch
adds what was paid (off); Save asks where. Nothing is sent from here -- the file is the friend's,
to read in Notepad and to send or not. Worked by the pad like every dialog: down and up between
the switch and the buttons, A flips or presses, B cancels.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from presentation import ui_rules
from presentation.ui_cards import FocusRing, ToggleSwitch
from presentation.ui_settings import SettingRow

TITLE = "An anonymous copy of your library"
INTRO = ("For a comparison of game libraries in a bachelor thesis. Nothing is sent from here: you save "
         "a file, you can open it with Notepad to read every word of it, and you choose whether to send it.")
NEVER = ("Folder paths and exe names, the names of games found only in folders, Steam account names "
         "and numbers, your notes, chosen covers, settings, the SteamGridDB key, the log, and the times "
         "of day you played.")


class AnalysisDialog(QDialog):
    def __init__(self, lines: list[str], scale: float, tv: bool = False, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Analysis")
        self.setWindowTitle(TITLE)
        self.scale = scale
        self.focus_ring_width = ui_rules.TV_FOCUS_RING_WIDTH if tv else ui_rules.FOCUS_RING_WIDTH

        title = QLabel(TITLE)
        title.setObjectName("SettingsTitle")
        intro = self._text(INTRO)
        in_it = QLabel("In it")
        in_it.setObjectName("AnalysisHeading")
        self.lines = [self._text("•  " + line) for line in lines]
        never_heading = QLabel("Never in it")
        never_heading.setObjectName("AnalysisHeading")
        never = self._text(NEVER)

        self.include_paid = ToggleSwitch(scale=scale, animate=False)
        self.include_paid.setChecked(False)
        self.include_paid.setProperty("ringRadius", self.include_paid.sizeHint().height() / 2)
        paid_row = SettingRow("Include what I paid",
                              "The amounts from What I paid, with the store and the month -- not the notes.",
                              [self.include_paid], scale)

        self.cancel_button = QPushButton("Cancel")
        self.save_button = QPushButton("Save...")
        self.save_button.setDefault(True)
        for button in (self.cancel_button, self.save_button):
            button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_button.clicked.connect(self.reject)
        self.save_button.clicked.connect(self.accept)
        buttons = QHBoxLayout()
        buttons.addWidget(self.cancel_button)
        buttons.addStretch(1)
        buttons.addWidget(self.save_button)

        layout = QVBoxLayout(self)
        margin = max(12, round(24 * scale))
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.setSpacing(max(6, round(10 * scale)))
        for widget in [title, intro, in_it, *self.lines, never_heading, never, paid_row]:
            layout.addWidget(widget)
        layout.addLayout(buttons)
        self.setMinimumWidth(round(ui_rules.ANALYSIS_WIDTH * scale))
        self.focus_ring = FocusRing(self, self._ringed, scale=lambda: self.scale)

    def _text(self, words: str) -> QLabel:
        label = QLabel(words)
        label.setObjectName("AnalysisText")
        label.setWordWrap(True)
        label.setTextFormat(Qt.TextFormat.PlainText)  # game counts and names, never markup
        return label

    def _ringed(self, widget) -> bool:
        if isinstance(widget, ToggleSwitch):
            return self.testAttribute(Qt.WidgetAttribute.WA_KeyboardFocusChange)
        return isinstance(widget, QPushButton)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # The switch first: the one choice there is; down from it, the buttons.
        self.include_paid.setFocus(Qt.FocusReason.OtherFocusReason)

    def done(self, result) -> None:
        self.focus_ring.detach()
        super().done(result)


def stylesheet(scale: float) -> str:
    s = lambda value: max(1, round(value * scale))  # noqa: E731
    return f"""
    QDialog#Analysis {{ background: {ui_rules.COLOR_BACKGROUND}; }}
    QLabel#AnalysisText {{ font-size: {s(ui_rules.ANALYSIS_TEXT_PX)}px; color: {ui_rules.COLOR_TEXT_SOFT}; }}
    QLabel#AnalysisHeading {{
        font-size: {s(ui_rules.ANALYSIS_HEADING_PX)}px; font-weight: {ui_rules.HEADING_WEIGHT};
        color: {ui_rules.COLOR_TEXT}; padding-top: {s(4)}px;
    }}
    QDialog#Analysis QLabel#SettingsTitle {{
        font-size: {s(ui_rules.SETTINGS_TITLE_PX)}px; font-weight: {ui_rules.HEADING_WEIGHT};
    }}
    """
