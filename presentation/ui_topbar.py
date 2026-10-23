"""The bar across the top of Library, Stats and Storage.

Tabs on the left, a search box and three square icon buttons on the right -- in place of
the old strip of ten controls, two of them tick-boxes. It belongs to the window, not to one
page, which is what lets the tabs mean the same thing wherever you are. A game's own page
hides it: that page is about the game, and has its own way back.

The controls here are the library's (LibraryPage keeps its names for them -- filter_box,
surprise_button, rescan_button, settings_button, stats_button, storage_button), so
everything that already used them, tests included, still does.

Since Phase 55 it is drawn to the Nocturne design: the tabs run the bar's full height with
the current one underlined at its foot, the search box is a rounded rectangle with its
shortcut written faintly at the right, and the three buttons are quiet squares.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QLabel, QLineEdit, QPushButton, QWidget

from presentation import ui_icons
from presentation import ui_rules
from presentation import ui_theme

TAB_LIBRARY, TAB_STATS, TAB_STORAGE, TAB_REPORTS = "library", "stats", "storage", "reports"
TAB_WISHLIST = "wishlist"  # Phase 87
TAB_FORYOU = "foryou"  # Phase 98: under Library, a place of its own
TABS = ((TAB_LIBRARY, "Library"), (TAB_FORYOU, "For you"), (TAB_STATS, "Stats"), (TAB_STORAGE, "Storage"),
        (TAB_REPORTS, "Reports"), (TAB_WISHLIST, "Wishlist"))  # Reports: Phase 84; Wishlist: 87; For you: 98


class TopBar(QWidget):
    tabSelected = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("TopBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.scale = 1.0

        self.brand = QLabel()
        self.brand.setObjectName("Brand")

        self.tabs: dict[str, QPushButton] = {}
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        for name, label in TABS:
            tab = QPushButton(label)
            tab.setObjectName("TopTab")
            tab.setCheckable(True)
            tab.setCursor(Qt.CursorShape.PointingHandCursor)
            tab.clicked.connect(lambda _checked=False, n=name: self._picked(n))
            self._group.addButton(tab)
            self.tabs[name] = tab
        self.tabs[TAB_LIBRARY].setChecked(True)

        self.search = QLineEdit()
        self.search.setObjectName("Search")
        self.search.setClearButtonEnabled(True)
        self.search.setPlaceholderText("Search games")
        self._search_icon = self.search.addAction(
            ui_icons.icon("search", ui_rules.COLOR_TEXT_MUTED, px=ui_rules.SEARCH_ICON_PX),
            QLineEdit.ActionPosition.LeadingPosition)
        # The shortcut, written faintly at the box's right end while it is empty: the clear
        # button takes that place once there is something to clear.
        self.hint = QLabel(ui_rules.SEARCH_HINT, self.search)
        self.hint.setObjectName("SearchHint")
        self.hint.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.search.textChanged.connect(self._place_hint)
        self.search.installEventFilter(self)

        self.surprise = self._icon_button("shuffle", "Play something -- pick a game for me.\n"
                                          "Leans towards things you have not played lately.")
        self.rescan = self._icon_button("refresh", "Rescan -- look for games installed or "
                                        "removed since the last look")
        self.settings = self._icon_button("settings", "Settings")

        self._tab_row = QHBoxLayout()
        self._tab_row.setContentsMargins(0, 0, 0, 0)
        for name, _label in TABS:
            self._tab_row.addWidget(self.tabs[name])
        self._button_row = QHBoxLayout()
        self._button_row.setContentsMargins(0, 0, 0, 0)
        for button in (self.surprise, self.rescan, self.settings):
            self._button_row.addWidget(button)

        row = QHBoxLayout(self)
        row.addWidget(self.brand)
        row.addLayout(self._tab_row)
        row.addStretch(1)
        row.addWidget(self.search)
        row.addLayout(self._button_row)
        self.apply_scale(1.0)

    def _icon_button(self, glyph: str, tip: str) -> QPushButton:
        button = QPushButton()
        button.setObjectName("IconButton")
        button.setToolTip(tip)
        button.setAccessibleName(tip.split(" -- ")[0].split("\n")[0])
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setProperty("glyph", glyph)
        return button

    def apply_scale(self, scale: float) -> None:
        self.scale = scale
        s = lambda value: max(1, round(value * scale))  # noqa: E731 -- a local shorthand
        ratio = self.devicePixelRatioF() or 1.0
        row = self.layout()
        row.setContentsMargins(s(ui_rules.TOPBAR_SIDE_MARGIN), 0, s(ui_rules.TOPBAR_SIDE_MARGIN), 0)
        row.setSpacing(s(ui_rules.TOPBAR_GAP))
        self._tab_row.setSpacing(s(ui_rules.TOPBAR_TAB_GAP))
        self._button_row.setSpacing(s(ui_rules.ICON_BUTTON_GAP))
        self.setFixedHeight(s(ui_rules.TOPBAR_HEIGHT))
        self.brand.setPixmap(ui_icons.glyph_pixmap("brand", ui_rules.COLOR_ACCENT,
                                                   s(ui_rules.TOPBAR_BRAND_PX), ratio))
        self.brand.setContentsMargins(0, 0, s(ui_rules.TOPBAR_BRAND_GAP), 0)
        # The tabs run the bar's full height, so the underline sits at its foot.
        for tab in self.tabs.values():
            tab.setFixedHeight(s(ui_rules.TOPBAR_HEIGHT))
        self.search.setFixedSize(s(ui_rules.SEARCH_WIDTH), s(ui_rules.SEARCH_HEIGHT))
        self._search_icon.setIcon(ui_icons.icon("search", ui_rules.COLOR_TEXT_MUTED,
                                                px=s(ui_rules.SEARCH_ICON_PX)))
        glyph_px = s(ui_rules.TOPBAR_GLYPH_PX)
        for button in (self.surprise, self.rescan, self.settings):
            button.setIcon(ui_icons.icon(button.property("glyph"), px=glyph_px))
            button.setIconSize(QSize(glyph_px, glyph_px))
            button.setFixedSize(s(ui_rules.ICON_BUTTON_SIZE), s(ui_rules.ICON_BUTTON_SIZE))
        # The current tab is drawn at the heading weight, wider than it was measured at.
        for tab in self.tabs.values():
            ui_theme.reserve_bold_width(tab)
        self._place_hint()

    def eventFilter(self, watched, event) -> bool:
        if watched is self.search and event.type() in (QEvent.Type.Resize, QEvent.Type.Polish):
            self._place_hint()
        return super().eventFilter(watched, event)

    def _place_hint(self) -> None:
        """Keep the shortcut at the box's right end, and the typed words clear of it."""
        if self.search.text():
            self.hint.hide()
            self.search.setTextMargins(0, 0, 0, 0)
            return
        # The placeholder is the box's own colour; the stylesheet would otherwise use the text's.
        palette = self.search.palette()
        palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(ui_rules.COLOR_TEXT_MUTED))
        self.search.setPalette(palette)
        self.hint.adjustSize()
        pad = max(1, round(ui_rules.SEARCH_PADDING * self.scale))
        self.hint.move(self.search.width() - pad - self.hint.width(),
                       (self.search.height() - self.hint.height()) // 2)
        self.search.setTextMargins(0, 0, self.hint.width() + pad, 0)
        self.hint.show()

    def restore_search(self) -> None:
        """Take the search box back, after the side rail's library has had it (Phase 60)."""
        if self.search.parentWidget() is not self:
            self.layout().insertWidget(3, self.search)  # after the brand, the tabs, the stretch
            self._place_hint()

    def set_current(self, name: str) -> None:
        """Mark a tab as the current one without announcing it -- the window already moved."""
        tab = self.tabs.get(name)
        if tab is not None and not tab.isChecked():
            tab.setChecked(True)

    def set_count(self, games: int) -> None:
        self.search.setPlaceholderText(f"Search {games} games" if games else "Search games")

    def _picked(self, name: str) -> None:
        self.tabSelected.emit(name)


def stylesheet(scale: float) -> str:
    s = lambda value: max(1, round(value * scale))  # noqa: E731
    pt = lambda pixels: f"{ui_theme.px_to_pt(pixels * scale):.2f}pt"  # noqa: E731
    return f"""
    QWidget#TopBar {{ background: transparent; }}
    QLabel#Brand {{ background: transparent; }}
    QPushButton#TopTab {{
        background: transparent;
        border: none;
        border-bottom: {s(ui_rules.TOPBAR_UNDERLINE)}px solid transparent;
        border-radius: 0;
        color: {ui_rules.COLOR_TEXT_MUTED};
        font-family: "{ui_icons.display_family()}";
        font-size: {pt(ui_rules.TOPBAR_TAB_PX)};
        padding: 0;
    }}
    QPushButton#TopTab:hover {{ color: {ui_rules.COLOR_TEXT}; background: transparent; }}
    /* :checked has to be styled or it cannot be seen -- the Favorite lesson, again. */
    QPushButton#TopTab:checked {{
        color: {ui_rules.COLOR_TEXT};
        font-weight: {ui_rules.HEADING_WEIGHT};
        border-bottom-color: {ui_rules.COLOR_ACCENT};
    }}
    QLineEdit#Search {{
        background: {ui_rules.COLOR_SEARCH};
        border: 1px solid {ui_rules.COLOR_DIVIDER};
        border-radius: {s(ui_rules.CONTROL_RADIUS)}px;
        padding: 0 {s(ui_rules.SEARCH_PADDING)}px 0 {s(4)}px;
        color: {ui_rules.COLOR_TEXT};
        font-size: {pt(ui_rules.SEARCH_PX)};
    }}
    QLineEdit#Search:focus {{ border-color: {ui_rules.COLOR_ACCENT}; }}
    QLabel#SearchHint {{
        background: transparent;
        color: {ui_rules.COLOR_TEXT_FAINT};
        font-size: {pt(ui_rules.SEARCH_HINT_PX)};
    }}
    QPushButton#IconButton {{
        background: transparent;
        border: 1px solid {ui_rules.COLOR_DIVIDER};
        border-radius: {s(ui_rules.CONTROL_RADIUS)}px;
        padding: 0;
    }}
    QPushButton#IconButton:hover {{ background: {ui_rules.COLOR_SECONDARY_HOVER}; }}
    QPushButton#IconButton:pressed {{ background: {ui_rules.COLOR_SECONDARY_PRESSED}; }}
    QPushButton#IconButton:disabled {{ background: transparent; }}
    """
