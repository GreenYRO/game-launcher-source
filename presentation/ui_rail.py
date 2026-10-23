"""The side rail (Phase 60): the library's places, its filters and its stores in a column.

The design's #1b. At the desk it takes the place of the top bar and the chips above the
grid: Library, Stats and Storage at the top; the five filters with their counts; where the
games were found, with theirs; and at its foot Play something, rescan and settings. TV mode
keeps the top bar (ui_topbar), whose paths the pad was built around.

It owns no state. The filters are the library's chips (ui_library), which stay the one
place the choice is kept, remembered and read; the rail mirrors them and asks the page to
change them. Its buttons are wired to the same signals the top bar's are. Nothing in it
takes the keyboard's focus, so a click on a filter leaves the arrow keys on the grid.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QLinearGradient, QPainter, QPainterPath
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from presentation import ui_icons
from presentation import ui_rules
from presentation import ui_theme
from presentation.ui_topbar import TAB_FORYOU, TAB_LIBRARY, TAB_REPORTS, TAB_STATS, TAB_STORAGE, TAB_WISHLIST

NAV = ((TAB_LIBRARY, "Library", "grid"), (TAB_FORYOU, "For you", "foryou"), (TAB_STATS, "Stats", "chart"),
       (TAB_STORAGE, "Storage", "drives"), (TAB_REPORTS, "Reports", "reports"),
       (TAB_WISHLIST, "Wishlist", "wishlist"))  # Reports: 84; Wishlist: 87; For you, under Library: 98
# The filters' icons, by the library's filter names (ui_library.FILTERS).
FILTER_GLYPHS = {"all": "grid", "favorites": "star", "playing": "playing", "finished": "finished",
                 "dropped": "dropped"}


def _font(px: float, scale: float, weight: int | None = None, family: str | None = None) -> QFont:
    font = QFont(family or ui_icons.body_family())
    font.setPointSizeF(max(6.0, ui_theme.px_to_pt(px * scale)))
    if weight:
        font.setWeight(QFont.Weight(weight))
    return font


class RailItem(QPushButton):
    """A place or a filter: an icon, its words, and -- for a filter -- a count at the right.

    Painted, not styled: the chosen place carries a 2 px mark at its left edge and a filter
    a number in a quieter size and colour, neither of which a stylesheet can draw.
    """

    def __init__(self, text: str, glyph: str, kind: str, parent=None) -> None:
        super().__init__(text, parent)
        self.setObjectName("RailItem")
        self.kind = kind  # "nav" or "filter"
        self.glyph = glyph
        self.count: int | None = None
        self.scale = 1.0
        self.setCheckable(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setAccessibleName(text)

    def set_count(self, count: int) -> None:
        if count != self.count:
            self.count = count
            self.update()

    def apply_scale(self, scale: float) -> None:
        self.scale = scale
        height = ui_rules.RAIL_NAV_HEIGHT if self.kind == "nav" else ui_rules.RAIL_FILTER_HEIGHT
        self.setFixedHeight(max(16, round(height * scale)))
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(round(120 * self.scale), self.height())

    def enterEvent(self, event) -> None:
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:
        s = self.scale
        nav = self.kind == "nav"
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        box = QRectF(self.rect())
        radius = ui_rules.CONTROL_RADIUS * s
        shape = QPainterPath()
        shape.addRoundedRect(box, radius, radius)
        chosen = self.isChecked()
        ground = None
        if chosen:
            ground = ui_rules.COLOR_RAIL_CHOSEN if nav else ui_rules.COLOR_RAIL_FILTER_CHOSEN
        elif self.underMouse():
            ground = ui_rules.COLOR_RAIL_HOVER
        if ground is not None:
            painter.fillPath(shape, QColor(ground))
        if chosen and nav:
            # The design's inset mark: 2 px of the accent down the item's left edge.
            painter.save()
            painter.setClipPath(shape)
            painter.fillRect(QRectF(0, 0, max(1.0, ui_rules.RAIL_MARK * s), box.height()),
                             QColor(ui_rules.COLOR_ACCENT))
            painter.restore()

        if chosen:
            colour = ui_rules.COLOR_RAIL_CHOSEN_TEXT if nav else ui_rules.COLOR_TEXT
        else:
            colour = ui_rules.COLOR_RAIL_ITEM
        icon_px = max(8, round((ui_rules.RAIL_NAV_ICON_PX if nav else ui_rules.RAIL_FILTER_ICON_PX) * s))
        left = ui_rules.RAIL_ITEM_PADDING * s
        ratio = self.devicePixelRatioF() or 1.0
        painter.drawPixmap(QPointF(left, (box.height() - icon_px) / 2),
                           ui_icons.glyph_pixmap(self.glyph, colour, icon_px, ratio))
        words_left = left + icon_px + ui_rules.RAIL_ICON_GAP * s
        right = box.width() - ui_rules.RAIL_ITEM_PADDING * s
        if self.count is not None:
            count_font = _font(ui_rules.RAIL_COUNT_PX, s)
            painter.setFont(count_font)
            painter.setPen(QColor(ui_rules.COLOR_RAIL_LABEL))
            count = str(self.count)
            painter.drawText(QRectF(words_left, 0, right - words_left, box.height()),
                             int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), count)
            right -= QFontMetricsF(count_font).horizontalAdvance(count) + ui_rules.RAIL_ITEM_PADDING * s
        font = _font(ui_rules.RAIL_NAV_PX if nav else ui_rules.RAIL_FILTER_PX, s)
        painter.setFont(font)
        painter.setPen(QColor(colour))
        painter.drawText(QRectF(words_left, 0, max(0.0, right - words_left), box.height()),
                         int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                         QFontMetricsF(font).elidedText(self.text(), Qt.TextElideMode.ElideRight,
                                                        max(0.0, right - words_left)))


class RailSource(QWidget):
    """One place the games were found: a small dot, its name, how many came from it."""

    def __init__(self, label: str, count: int, scale: float, parent=None) -> None:
        super().__init__(parent)
        self.label = label
        self.count = count
        self.scale = scale
        self.setFixedHeight(max(14, round(ui_rules.RAIL_SOURCE_HEIGHT * scale)))
        self.setAccessibleName(f"{label}: {count}")

    def paintEvent(self, event) -> None:
        s = self.scale
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        height = self.height()
        left = ui_rules.RAIL_ITEM_PADDING * s
        dot = max(3.0, ui_rules.RAIL_SOURCE_DOT * s)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(ui_rules.COLOR_RAIL_DOT))
        painter.drawEllipse(QRectF(left, (height - dot) / 2, dot, dot))
        words_left = left + dot + ui_rules.RAIL_ICON_GAP * s
        right = self.width() - ui_rules.RAIL_ITEM_PADDING * s
        painter.setFont(_font(ui_rules.RAIL_COUNT_PX, s))
        painter.setPen(QColor(ui_rules.COLOR_RAIL_LABEL))
        painter.drawText(QRectF(words_left, 0, right - words_left, height),
                         int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), str(self.count))
        painter.setFont(_font(ui_rules.RAIL_FILTER_PX, s))
        painter.setPen(QColor(ui_rules.COLOR_RAIL_ITEM))
        painter.drawText(QRectF(words_left, 0, right - words_left, height),
                         int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), self.label)


class RailDivider(QWidget):
    """A hairline between the rail's groups, fading in and out at its two ends."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.scale = 1.0

    def apply_scale(self, scale: float) -> None:
        self.scale = scale
        self.setFixedHeight(round(ui_rules.RAIL_DIVIDER_MARGIN * scale) * 2 + 1)

    def paintEvent(self, event) -> None:
        s = self.scale
        side = ui_rules.RAIL_DIVIDER_SIDE * s
        width = self.width() - side * 2
        if width <= 0:
            return
        painter = QPainter(self)
        line = QLinearGradient(side, 0, side + width, 0)
        fade = min(0.5, ui_rules.RAIL_DIVIDER_FADE * s / width)
        clear, colour = QColor(ui_rules.COLOR_RAIL_DIVIDER), QColor(ui_rules.COLOR_RAIL_DIVIDER)
        clear.setAlpha(0)
        line.setColorAt(0.0, clear)
        line.setColorAt(fade, colour)
        line.setColorAt(1.0 - fade, colour)
        line.setColorAt(1.0, clear)
        painter.fillRect(QRectF(side, round(ui_rules.RAIL_DIVIDER_MARGIN * s), width, 1), line)


class SideRail(QWidget):
    """The column itself. The library page builds it and the window places it."""

    tabSelected = Signal(str)
    filterPicked = Signal(str)
    surpriseRequested = Signal()
    rescanRequested = Signal()
    settingsRequested = Signal()

    def __init__(self, filters, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("SideRail")
        self.scale = 1.0
        self.sources: list[tuple[str, int]] = []

        self.brand = QLabel()
        self.brand.setObjectName("RailBrandGlyph")
        self.brand_text = QLabel("Game Launcher")
        self.brand_text.setObjectName("RailBrand")
        brand = QHBoxLayout()
        brand.setContentsMargins(0, 0, 0, 0)
        brand.addWidget(self.brand)
        brand.addWidget(self.brand_text)
        brand.addStretch(1)
        self._brand_row = brand

        self.places: dict[str, RailItem] = {}
        nav = QVBoxLayout()
        nav.setContentsMargins(0, 0, 0, 0)
        for name, label, glyph in NAV:
            item = RailItem(label, glyph, "nav")
            item.clicked.connect(lambda _checked=False, n=name: self._place_picked(n))
            self.places[name] = item
            nav.addWidget(item)
        self._nav = nav
        self.places[TAB_LIBRARY].setChecked(True)

        self.filters: dict[str, RailItem] = {}
        shown = QVBoxLayout()
        shown.setContentsMargins(0, 0, 0, 0)
        for name, label in filters:
            item = RailItem(label, FILTER_GLYPHS.get(name, "grid"), "filter")
            item.clicked.connect(lambda _checked=False, n=name: self._filter_picked(n))
            self.filters[name] = item
            shown.addWidget(item)
        self._filters = shown

        self.source_list = QVBoxLayout()
        self.source_list.setContentsMargins(0, 0, 0, 0)

        # At its foot: Play something, then rescan and settings.
        self.surprise = QPushButton(" Play something")  # Qt leaves 4 px after an icon; the space makes 7
        self.surprise.setObjectName("RailPlay")
        self.surprise.setToolTip("Pick a game for me. Leans towards things you have not played lately.")
        self.rescan = self._button("refresh", "Rescan -- look for games installed or removed since the last look")
        self.settings = self._button("settings", "Settings")
        for button in (self.surprise, self.rescan, self.settings):
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.surprise.clicked.connect(self.surpriseRequested)
        self.rescan.clicked.connect(self.rescanRequested)
        self.settings.clicked.connect(self.settingsRequested)
        foot = QHBoxLayout()
        foot.addWidget(self.surprise)
        foot.addStretch(1)
        foot.addWidget(self.rescan)
        foot.addWidget(self.settings)
        self._foot = foot

        self.dividers = [RailDivider(), RailDivider()]
        self.labels = [QLabel("SHOW"), QLabel("FOUND IN")]
        for label in self.labels:
            label.setObjectName("RailLabel")

        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.addLayout(brand)
        layout.addLayout(nav)
        layout.addWidget(self.dividers[0])
        layout.addWidget(self.labels[0])
        layout.addLayout(shown)
        layout.addWidget(self.dividers[1])
        layout.addWidget(self.labels[1])
        layout.addLayout(self.source_list)
        layout.addStretch(1)
        layout.addLayout(foot)
        self.apply_scale(1.0)

    def _button(self, glyph: str, tip: str) -> QPushButton:
        button = QPushButton()
        button.setObjectName("RailButton")
        button.setToolTip(tip)
        button.setAccessibleName(tip.split(" -- ")[0])
        button.setProperty("glyph", glyph)
        return button

    # -- what it shows --------------------------------------------------------------------

    def set_current(self, name: str) -> None:
        """Mark a place as the current one without announcing it -- the window already moved."""
        for place, item in self.places.items():
            item.setChecked(place == name)

    def set_filter(self, name: str) -> None:
        for filter_name, item in self.filters.items():
            item.setChecked(filter_name == name)

    def set_counts(self, counts: dict[str, int]) -> None:
        for name, item in self.filters.items():
            item.set_count(counts.get(name, 0))

    def set_sources(self, sources: list[tuple[str, int]]) -> None:
        """Where the games were found and how many from each, biggest first."""
        if sources == self.sources:
            return
        self.sources = list(sources)
        self._fill_sources()

    def _fill_sources(self) -> None:
        while self.source_list.count():
            widget = self.source_list.takeAt(0).widget()
            if widget is not None:
                widget.setParent(None)  # not deleteLater alone: the Phase 23 lesson
                widget.deleteLater()
        for label, count in self.sources:
            self.source_list.addWidget(RailSource(label, count, self.scale))
        self._fold()

    # -- room ---------------------------------------------------------------------------

    def _found_in(self) -> list[QWidget]:
        """What folds away when the window is too short: "Found in", its divider and its rows."""
        rows = [self.source_list.itemAt(i).widget() for i in range(self.source_list.count())]
        return [self.dividers[1], self.labels[1], *[w for w in rows if w is not None]]

    def _height_of(self, widgets) -> int:
        """What these of "Found in"'s widgets take up the rail: their fixed heights, the label's own, the gaps."""
        rows = [w for w in widgets if isinstance(w, RailSource)]
        return (sum(w.sizeHint().height() if w is self.labels[1] else w.height() for w in widgets)
                + max(0, len(rows) - 1) * self.source_list.spacing())

    def _fold(self) -> None:
        """Where the games came from shows only when the window has room for it; the places, the filters and the
        foot always do. Phase 98's sixth place made the rail as a whole taller than a 768-pixel laptop screen at
        100% (925 px at 125%), and a rail that will not shrink makes the window taller than asked -- so its
        minimum is the rail without "Found in", and "Found in" folds away rather than push. Whatever shows now
        is taken off the layout's minimum, so rows refilled while folded are measured right too."""
        widgets = self._found_in()
        layout = self.layout()
        layout.invalidate()
        base = layout.minimumSize().height() - self._height_of([w for w in widgets if not w.isHidden()])
        self.setMinimumHeight(base)
        show = self.height() >= base + self._height_of(widgets)
        for widget in widgets:
            # Every one told, not only those that differ: rows a scan has just added are shown by Qt a moment
            # later unless they were hidden explicitly, and would stand under a folded "Found in".
            widget.setVisible(show)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fold()

    # -- choosing -------------------------------------------------------------------------

    def _place_picked(self, name: str) -> None:
        # A place is never toggled off by clicking it again: one is always current.
        self.set_current(name)
        self.tabSelected.emit(name)

    def _filter_picked(self, name: str) -> None:
        self.set_filter(name)
        self.filterPicked.emit(name)

    # -- scale and paint ------------------------------------------------------------------

    def apply_scale(self, scale: float) -> None:
        self.scale = scale
        s = lambda value: max(1, round(value * scale))  # noqa: E731
        ratio = self.devicePixelRatioF() or 1.0
        self.setFixedWidth(s(ui_rules.RAIL_WIDTH))
        self.layout().setContentsMargins(s(ui_rules.RAIL_PADDING_X), s(ui_rules.RAIL_PADDING_TOP),
                                         s(ui_rules.RAIL_PADDING_X), s(ui_rules.RAIL_PADDING_BOTTOM))
        self._brand_row.setContentsMargins(s(ui_rules.RAIL_ITEM_PADDING), 0, s(ui_rules.RAIL_ITEM_PADDING),
                                           s(ui_rules.RAIL_BRAND_BELOW))
        self._brand_row.setSpacing(s(ui_rules.RAIL_BRAND_GAP))
        self.brand.setPixmap(ui_icons.glyph_pixmap("brand", ui_rules.COLOR_ACCENT, s(ui_rules.RAIL_BRAND_PX), ratio))
        self._nav.setSpacing(s(ui_rules.RAIL_NAV_GAP))
        self._filters.setSpacing(s(ui_rules.RAIL_FILTER_GAP))
        self.source_list.setSpacing(s(ui_rules.RAIL_FILTER_GAP))
        for item in (*self.places.values(), *self.filters.values()):
            item.apply_scale(scale)
        for divider in self.dividers:
            divider.apply_scale(scale)
        for label in self.labels:
            label.setContentsMargins(s(ui_rules.RAIL_ITEM_PADDING), 0, 0, s(ui_rules.RAIL_LABEL_BELOW))
        self._foot.setContentsMargins(s(ui_rules.RAIL_FOOT_SIDE), 0, s(ui_rules.RAIL_FOOT_SIDE), 0)
        self._foot.setSpacing(s(ui_rules.RAIL_FOOT_GAP))
        play_px = s(ui_rules.RAIL_PLAY_ICON_PX)
        self.surprise.setIcon(ui_icons.icon("shuffle", ui_rules.COLOR_ACCENT, play_px))
        self.surprise.setIconSize(QSize(play_px, play_px))
        icon_px = s(ui_rules.RAIL_BUTTON_ICON_PX)
        for button in (self.rescan, self.settings):
            button.setFixedSize(s(ui_rules.RAIL_BUTTON), s(ui_rules.RAIL_BUTTON))
            button.setIcon(ui_icons.icon(button.property("glyph"), ui_rules.COLOR_RAIL_BUTTON_ICON, icon_px))
            button.setIconSize(QSize(icon_px, icon_px))
        self._fill_sources()
        # The design's 232 px holds its foot only just: measured, Play something wanted
        # 134 px and was given 124, and the end of its "g" was cut off (reported from use).
        # So the rail is the design's width or what its rows need, whichever is more
        # (Phase 62) -- a wider typeface simply widens it.
        layout = self.layout()
        layout.invalidate()
        self.setFixedWidth(max(s(ui_rules.RAIL_WIDTH), layout.minimumSize().width()))
        self._fold()
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        # The surface at 60% at the top, fading to nothing, over the window's glow.
        ground = QLinearGradient(0, 0, 0, self.height())
        top = QColor(ui_rules.COLOR_RAIL_TOP)
        clear = QColor(top)
        clear.setAlpha(0)
        ground.setColorAt(0.0, top)
        ground.setColorAt(1.0, clear)
        painter.fillRect(self.rect(), ground)
        painter.fillRect(QRectF(self.width() - 1, 0, 1, self.height()), QColor(ui_rules.COLOR_RAIL_EDGE))


def stylesheet(scale: float) -> str:
    s = lambda value: max(1, round(value * scale))  # noqa: E731
    pt = lambda px: f"{ui_theme.px_to_pt(px * scale):.2f}pt"  # noqa: E731 -- fractional px
    return f"""
    QWidget#SideRail, QLabel#RailBrandGlyph, QPushButton#RailItem {{ background: transparent; border: none; }}
    QLabel#RailBrand {{
        background: transparent;
        font-family: "{ui_icons.display_family()}";
        font-size: {s(ui_rules.RAIL_BRAND_TEXT_PX)}px;
        font-weight: {ui_rules.HEADING_WEIGHT};
        color: {ui_rules.COLOR_TEXT};
    }}
    QLabel#RailLabel {{
        background: transparent;
        color: {ui_rules.COLOR_SECTION_LABEL};
        font-size: {pt(ui_rules.RAIL_LABEL_PX)};
        letter-spacing: {ui_rules.RAIL_LABEL_PX * ui_rules.RAIL_LABEL_TRACKING * scale:.2f}px;
    }}
    QPushButton#RailPlay {{
        background: transparent;
        border: 1px solid transparent;
        border-radius: {s(ui_rules.CONTROL_RADIUS)}px;
        color: {ui_rules.COLOR_ACCENT};
        font-size: {pt(ui_rules.RAIL_PLAY_PX)};
        font-weight: {ui_rules.HEADING_WEIGHT};
        padding: {s(6)}px {s(8)}px;
    }}
    QPushButton#RailPlay:hover {{ background: {ui_rules.COLOR_TEXT_BUTTON_HOVER}; }}
    QPushButton#RailButton {{
        background: transparent;
        border: 1px solid transparent;
        border-radius: {s(ui_rules.CONTROL_RADIUS)}px;
        padding: 0;
    }}
    QPushButton#RailButton:hover {{ background: {ui_rules.COLOR_SECONDARY_HOVER}; }}
    QPushButton#RailButton:pressed {{ background: {ui_rules.COLOR_SECONDARY_PRESSED}; }}
    QPushButton#RailButton:disabled {{ background: transparent; }}
    /* The library beside the rail: its name and what it holds, and the sort as quiet words. */
    QLabel#PageTitle {{
        background: transparent;
        font-family: "{ui_icons.display_family()}";
        font-size: {s(ui_rules.PAGE_TITLE_PX)}px;
        font-weight: {ui_rules.HEADING_WEIGHT};
        letter-spacing: {ui_rules.PAGE_TITLE_TRACKING * ui_rules.PAGE_TITLE_PX * scale:.2f}px;
        color: {ui_rules.COLOR_TEXT};
    }}
    QLabel#PageMeta {{ background: transparent; font-size: {s(ui_rules.PAGE_META_PX)}px; color: {ui_rules.COLOR_TEXT_MUTED}; }}
    QLabel#SortLabel[variant="plain"] {{ font-size: {s(ui_rules.SORT_PLAIN_PX)}px; color: {ui_rules.COLOR_TEXT_QUIET}; }}
    QComboBox#SortBox[variant="plain"] {{
        background: transparent;
        border: none;
        padding: 0 {s(14)}px 0 0;
        font-size: {s(ui_rules.SORT_PLAIN_PX)}px;
        color: {ui_rules.COLOR_TEXT};
    }}
    QComboBox#SortBox[variant="plain"]:hover {{ background: transparent; color: {ui_rules.COLOR_ACCENT_HOVER}; }}
    """
