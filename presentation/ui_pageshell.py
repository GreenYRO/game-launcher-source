"""The chrome Stats, Storage and Reports share: their one column and a header with tabs.

The three pages answer "what is my library doing" rather than "what shall I play", so they
are tabs of one place rather than unrelated screens. That is also what makes the second and
third reachable on a controller: **every pad button was already spoken for** by Phase 23 --
A select, B back, X menu, Y play something, the shoulders page, View stats, Start settings
-- so Storage, Reports (Phase 84) and Wishlist (Phase 87) get no button of their own. Left and
right move along the tabs instead -- Library, Stats, Storage, Reports, Wishlist -- and the tabs
are drawn on screen so that is visible rather than a secret.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QSizePolicy, QWidget

from presentation import ui_rules

TAB_STATS = "stats"
TAB_STORAGE = "storage"
TAB_REPORTS = "reports"  # Phase 84: the third page of this place
TAB_WISHLIST = "wishlist"  # Phase 87: the fourth
TAB_FORYOU = "foryou"  # Phase 98: first of them, as it is under Library
TABS = ((TAB_FORYOU, "For you"), (TAB_STATS, "Stats"), (TAB_STORAGE, "Storage"), (TAB_REPORTS, "Reports"),
        (TAB_WISHLIST, "Wishlist"))


class PageColumn(QWidget):
    """A page's one column: where the design puts it, and fairly placed on a wider window.

    64 px in from the left and never wider than the design's column (Phase 58). At the
    1280 px the design was drawn at, that is exactly its place; every pixel a window grows
    beyond that is shared equally between the two sides, so a maximised window or the TV
    does not leave the page hugging one edge. Replaced the 1 / 100 / 1 stretches, which
    handed each side a share of the window at every width (the game page's Phase 57 lesson).
    """

    def __init__(self, widget: QWidget, cap: int) -> None:
        super().__init__()
        self.setObjectName("Clear")  # see-through, so the glow behind the page shows (Phase 35)
        self.widget = widget
        self.cap = cap
        self.scale = 1.0
        # Beside the side rail (Phase 60) the page starts 32 px in, and its frame is the
        # design's 1280 less the rail.
        self.side = ui_rules.PAGE_COLUMN_SIDE
        self.frame = ui_rules.PAGE_COLUMN_FRAME
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(widget)

    def set_scale(self, scale: float) -> None:
        self.scale = scale
        self._place()

    def set_rail(self, rail: bool) -> None:
        self.side = ui_rules.RAIL_PAGE_SIDE if rail else ui_rules.PAGE_COLUMN_SIDE
        self.frame = ui_rules.PAGE_COLUMN_FRAME - (ui_rules.RAIL_WIDTH if rail else 0)
        self._place()

    def column(self) -> tuple[int, int]:
        """Where the column starts and how wide it is, for this width and scale."""
        side = round(self.side * self.scale)
        width = self.width()
        left = side + max(0, (width - round(self.frame * self.scale)) // 2)
        return left, max(0, min(round(self.cap * self.scale), width - left - side))

    def _place(self) -> None:
        left, width = self.column()
        self.layout().setContentsMargins(left, 0, max(0, self.width() - left - width), 0)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._place()


class PageHeader(QWidget):
    """Back to library, then the tab for each page in this pair."""

    backRequested = Signal()
    tabSelected = Signal(str)

    def __init__(self, current: str, parent=None) -> None:
        super().__init__(parent)
        self.current = current
        self.back_button = QPushButton("Back to library")
        self.back_button.clicked.connect(self.backRequested)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.back_button)
        row.addSpacing(ui_rules.TAB_GROUP_GAP)

        self.tabs: dict[str, QPushButton] = {}
        for name, label in TABS:
            button = QPushButton(label)
            button.setObjectName("Tab")
            button.setCheckable(True)
            button.setChecked(name == current)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked, n=name: self._pick(n))
            self.tabs[name] = button
            row.addWidget(button)
        row.addStretch(1)

    def _pick(self, name: str) -> None:
        # A tab is never toggled off by clicking it: one of the pair is always current.
        self.set_current(self.current if name == self.current else name)
        self.tabSelected.emit(name)

    def set_current(self, name: str) -> None:
        self.current = name
        for tab, button in self.tabs.items():
            button.setChecked(tab == name)

    def other(self) -> str:
        """The next tab along, round to the first -- what clicking through the header does."""
        names = [name for name, _label in TABS]
        return names[(names.index(self.current) + 1) % len(names)]

    def step(self, direction: int) -> str | None:
        """The tab to the left (-1) or right (+1) of this one, or None past either end -- what the
        pad's left and right move to since there are three (Phase 84). Past Stats, on the left, is
        the library, which is the window's to know."""
        names = [name for name, _label in TABS]
        at = names.index(self.current) + direction
        return names[at] if 0 <= at < len(names) else None


def stylesheet(scale: float) -> str:
    """Appended to the app stylesheet; only affects the tabs."""
    font = max(10, round(ui_rules.TAB_FONT_PT * scale))
    pad_v = max(5, round(8 * scale))
    pad_h = max(10, round(18 * scale))
    radius = max(4, round(7 * scale))
    return f"""
    QPushButton#Tab {{
        background: transparent;
        border: 1px solid transparent;
        border-radius: {radius}px;
        color: {ui_rules.COLOR_TEXT_MUTED};
        font-size: {font}pt;
        font-weight: {ui_rules.HEADING_WEIGHT};
        padding: {pad_v}px {pad_h}px;
    }}
    QPushButton#Tab:hover {{ color: {ui_rules.COLOR_TEXT}; }}
    /* Qt's :checked is invisible once a stylesheet owns the button -- the same trap as
       #Favorite:checked and QMenu::item:disabled. The current tab has to say so itself. */
    QPushButton#Tab:checked {{
        background: {ui_rules.COLOR_SURFACE_RAISED};
        border-color: {ui_rules.COLOR_BORDER};
        color: {ui_rules.COLOR_TEXT};
    }}
    """
