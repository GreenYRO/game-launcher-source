"""TV mode chrome: the strip along the bottom telling you what the buttons do.

An Xbox pad's A and a DualSense's Cross are the same button to SDL, but not the same
symbol to the person holding it. Until Phase 50 each chip said both, in text; now each
button is drawn (ui_buttons) the way it looks on the pad in use -- the hub says which
family that is -- and the names below stay as the record of what each hint means.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QWidget

from shared import rules
from presentation import ui_buttons
from presentation import ui_rules

log = logging.getLogger(__name__)

# (xbox glyph, playstation glyph) for each button, then what it does on each page.
A = ("A", "✕")
B = ("B", "○")
X = ("X", "□")
Y = ("Y", "△")
# The two shoulders share one chip. Eight separate hints needed 2007px at the largest TV
# scale, which is wider than a 1080p screen; merging the pair that is obviously a pair
# buys back more room than the Stats hint costs, and nothing is left unadvertised.
SHOULDERS = ("LB·RB", "L1·R1")
# SDL calls this button BACK; no pad has for two console generations.
VIEW = ("View", "Create")
START = ("☰", "☰")
ACROSS = ("◀ ▶", "◀ ▶")
UPDOWN = ("▲ ▼", "▲ ▼")

LIBRARY, DETAIL, STATS, STORAGE, REPORTS, WISHLIST, DIALOG, MENU = (
    "library", "detail", "stats", "storage", "reports", "wishlist", "dialog", "menu")
FORYOU = "foryou"  # Phase 98
FORYOU_ANSWER = "foryou_answer"  # Phase 103: the ring on one of Left behind's answers
RATE = "rate"  # Phase 102: while "How was it?" asks, the pad is the card's

# What the buttons do where you are (Phase 35) -- before, one list served every page, and
# on a game's page it said A was "Select" when A starts the game. The library's set is the
# widest, and phase 23's check that the bar fits a 1080p screen at every TV size uses it.
HINT_SETS = {
    LIBRARY: ((A, "Select"), (B, "Back"), (X, "Menu"), (Y, "Play something"),
              (SHOULDERS, "Page"), (VIEW, "Stats"), (START, "Settings")),
    DETAIL: ((A, "Play"), (B, "Back"), (X, "Menu"), (ACROSS, "Previous / next game"),
             (UPDOWN, "Scroll"), (Y, "Play something")),
    # Left and right walk the tabs in order since Phase 84 -- Library, Stats, Storage, Reports, and
    # since Phase 87 Wishlist; since Phase 98 For you sits between Library and Stats.
    # A shares the month as an image since Phase 96: the Recap card's one button.
    STATS: ((A, "Share as image"), (B, "Back"), (ACROSS, "For you / Storage"), (UPDOWN, "Scroll"),
            (VIEW, "Library"), (START, "Settings")),
    STORAGE: ((A, "Open"), (B, "Back"), (X, "Menu"), (ACROSS, "Stats / Reports"), (START, "Settings")),
    REPORTS: ((B, "Back"), (ACROSS, "Storage / Wishlist"), (UPDOWN, "Scroll"), (VIEW, "Library"),
              (START, "Settings")),
    # The Wishlist (Phase 87): A opens a game's store page in Steam, Y walks the chips -- three since Phase 101.
    WISHLIST: ((A, "Open in Steam"), (B, "Back"), (X, "Menu"), (Y, "Next chip"), (ACROSS, "Reports"),
               (START, "Settings")),
    # For you (Phase 98): A plays the game the ring is on, X its menu (Details first), Y Tonight's choice.
    FORYOU: ((A, "Play"), (B, "Back"), (X, "Menu"), (Y, "Tonight"), (UPDOWN, "Move"), (ACROSS, "Move / Library / Stats"),
             (START, "Settings")),
    # Left behind (Phase 103): A gives the answer the ring is on.
    FORYOU_ANSWER: ((A, "Answer"), (B, "Back"), (X, "Menu"), (Y, "Tonight"), (UPDOWN, "Move"),
                    (ACROSS, "Move / Library / Stats"), (START, "Settings")),
    DIALOG: ((A, "Select"), (B, "Cancel"), (UPDOWN, "Move"), (ACROSS, "Move / change")),
    MENU: ((A, "Select"), (B, "Close"), (UPDOWN, "Move"), (ACROSS, "Submenu")),
    RATE: ((A, "Rate"), (B, "Skip"), (ACROSS, "Stars")),
}
HINTS = tuple((pad[0], pad[1], label) for pad, label in HINT_SETS[LIBRARY])

# The drawn button behind each name pair (Phase 50).
GLYPHS = {A: ui_buttons.FACE_SOUTH, B: ui_buttons.FACE_EAST, X: ui_buttons.FACE_WEST,
          Y: ui_buttons.FACE_NORTH, SHOULDERS: ui_buttons.SHOULDERS, VIEW: ui_buttons.VIEW,
          START: ui_buttons.MENU, ACROSS: ui_buttons.DPAD_ACROSS, UPDOWN: ui_buttons.DPAD_UPDOWN}


class BatteryGlyph(QWidget):
    """The active pad's power, drawn rather than written.

    Three outcomes. A charge level draws a battery. A pad running off the cable draws a
    plug, because "plugged in" is a real answer and showing nothing for it would look like
    the reading had failed -- which matters here, since a DualSense on USB reports exactly
    that. A pad that will not say draws nothing at all: an empty battery outline claiming a
    level nobody knows is worse than a gap.

    The plug is a plug rather than a charging bolt because a bolt at 12px -- the size at
    the smallest TV scale -- is an unreadable blob, which was settled by drawing both and
    magnifying them rather than by preference.

    Sized from the hint bar's height, so the bar is exactly as tall with the glyph as
    without it and the existing hints never move.
    """

    def __init__(self, metrics, parent=None) -> None:
        super().__init__(parent)
        self.metrics = metrics
        self.level = rules.POWER_UNKNOWN
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._resize()

    def set_level(self, level: str) -> None:
        self.level = level or rules.POWER_UNKNOWN
        self.setVisible(self.shows_anything)
        self.setToolTip(self._tooltip())
        self._resize()
        self.update()

    def _tooltip(self) -> str:
        if self.level == rules.POWER_WIRED:
            return "Controller: running off the cable"
        if self.shows_anything:
            return f"Controller battery: {self.level}"
        return ""

    @property
    def shows_anything(self) -> bool:
        return self.level in rules.POWER_STEPS or self.level == rules.POWER_WIRED

    def apply_metrics(self, metrics) -> None:
        self.metrics = metrics
        self._resize()

    def _height(self) -> int:
        bar = max(36, round(ui_rules.TV_HINT_BAR_HEIGHT * self.metrics.scale))
        return max(8, round(bar * ui_rules.BATTERY_HEIGHT_FRACTION))

    def _resize(self) -> None:
        if not self.shows_anything:
            self.setFixedSize(0, 0)
            return
        height = self._height()
        self.setFixedSize(round(height * ui_rules.BATTERY_ASPECT), height)

    def paintEvent(self, event) -> None:
        if not self.shows_anything:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        border = max(1, round(ui_rules.BATTERY_BORDER * self.metrics.scale))
        if self.level == rules.POWER_WIRED:
            self._paint_plug(painter, border)
        else:
            self._paint_battery(painter, border)
        painter.end()

    def _paint_plug(self, painter: QPainter, border: int) -> None:
        """A body with two prongs. Never warns: a cable is not a low battery."""
        width, height = self.width(), self.height()
        colour = QColor(ui_rules.COLOR_TEXT_MUTED)
        painter.setPen(QPen(colour, border))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(
            QRectF(width * 0.34, height * 0.14, width * 0.46, height * 0.72), border, border
        )
        for y in (height * 0.34, height * 0.66):
            painter.drawLine(QPointF(width * 0.06, y), QPointF(width * 0.34, y))

    def _paint_battery(self, painter: QPainter, border: int) -> None:
        steps = rules.POWER_STEPS.index(self.level)
        filled = min(ui_rules.BATTERY_STEPS, max(0, steps))
        colour = QColor(
            ui_rules.COLOR_WARNING
            if steps < rules.POWER_WARNING_BELOW
            else ui_rules.COLOR_TEXT_MUTED
        )

        cap = max(1, round(self.width() * ui_rules.BATTERY_CAP_FRACTION))
        body = QRectF(border / 2, border / 2, self.width() - cap - border, self.height() - border)

        painter.setPen(QPen(colour, border))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(body, border, border)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(colour)
        painter.drawRect(QRectF(body.right(), self.height() * 0.3, cap, self.height() * 0.4))

        if filled:
            pad = max(1, round(ui_rules.BATTERY_PADDING * self.metrics.scale))
            inner = body.adjusted(pad, pad, -pad, -pad)
            gap = max(1, pad // 2)
            width = (inner.width() - gap * (ui_rules.BATTERY_STEPS - 1)) / ui_rules.BATTERY_STEPS
            for step in range(filled):
                painter.drawRect(
                    QRectF(inner.left() + step * (width + gap), inner.top(), width, inner.height())
                )


class HintBar(QWidget):
    """A row of drawn buttons, saying what each does here. Visible only in TV mode."""

    def __init__(self, metrics, parent=None) -> None:
        super().__init__(parent)
        self.metrics = metrics
        self.setObjectName("HintBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.hints = ""
        self.family = rules.PAD_XBOX
        self._chips: list[QWidget] = []
        self._labels: list[QLabel] = []
        self._build()

    def _build(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 6, 20, 6)
        layout.setSpacing(18)
        layout.addStretch(1)
        self.battery = BatteryGlyph(self.metrics, self)
        self.battery.setVisible(False)
        layout.addWidget(self.battery)
        layout.addStretch(1)
        self.set_hints(LIBRARY)
        self.setFixedHeight(self._height())

    def set_family(self, family: str) -> None:
        """Draw the buttons of the pad in use: Xbox's letters or PlayStation's shapes (Phase 50).

        No pad at all ("") keeps the Xbox drawing -- the layout SDL itself names its buttons by.
        """
        family = ui_buttons.family_or_default(family)
        if family != self.family:
            self.family = family
            self._rebuild()

    def set_hints(self, name: str) -> None:
        """Show the hints for a page, a dialog or a menu. The battery stays at the end."""
        if name == self.hints or name not in HINT_SETS:
            return
        self.hints = name
        self._rebuild()

    def _rebuild(self) -> None:
        layout = self.layout()
        for widget in self._chips:
            layout.removeWidget(widget)
            widget.setParent(None)  # not deleteLater alone: the Phase 23 lesson
            widget.deleteLater()
        self._chips, self._labels = [], []
        position = 1  # after the leading stretch
        for pad, label in HINT_SETS[self.hints]:
            # Each button and its words as one item, so the gap between a button and what it
            # does is smaller than the gap to the next button.
            item = QWidget(self)
            item.setObjectName("HintItem")
            row = QHBoxLayout(item)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(max(4, round(8 * self.metrics.scale)))
            glyph = ui_buttons.ButtonGlyph(GLYPHS[pad], self.family, self._glyph_height(), item)
            text = QLabel(label, item)
            text.setObjectName("HintText")
            row.addWidget(glyph)
            row.addWidget(text)
            layout.insertWidget(position, item)
            self._chips.append(item)
            self._labels.append(text)
            position += 1

    @property
    def labels(self) -> list[str]:
        """What the bar says, in order -- for tests and for reading back."""
        return [label.text() for label in self._labels]

    @property
    def glyphs(self) -> list:
        """The drawn buttons, in order."""
        return [item.findChild(ui_buttons.ButtonGlyph) for item in self._chips]

    def _height(self) -> int:
        return max(36, round(ui_rules.TV_HINT_BAR_HEIGHT * self.metrics.scale))

    def _glyph_height(self) -> int:
        return round(self._height() * ui_rules.PAD_GLYPH_HEIGHT_FRACTION)

    def apply_metrics(self, metrics) -> None:
        self.metrics = metrics
        self.battery.apply_metrics(metrics)
        self.setFixedHeight(self._height())
        if self.hints:
            self._rebuild()

    def set_power(self, level: str) -> None:
        self.battery.set_level(level)


def stylesheet(scale: float) -> str:
    """Appended to the app stylesheet; only affects the hint bar."""
    font = max(8, round(ui_rules.TV_HINT_FONT_PT * scale))
    return f"""
    QWidget#HintBar {{
        background: {ui_rules.COLOR_HINT_BAR};
        border-top: 1px solid {ui_rules.COLOR_CARD_BORDER};
    }}
    QWidget#HintItem, QWidget#PadButton {{
        background: transparent;  /* the blanket QWidget background would box each hint */
    }}
    QLabel#HintText {{
        background: transparent;
        color: {ui_rules.COLOR_TEXT_MUTED};
        font-size: {font}pt;
    }}
    """
