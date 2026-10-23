"""The storage page: where the disk went, grouped by drive, biggest first.

**Read only.** Nothing on this page removes anything; it exists so a decision can be made
somewhere else with the facts in front of you.

One list holds both item shapes -- a drive header and the games under it -- rather than one
list per drive. That is deliberate and it is what makes the page work on a controller:
Qt skips items that are not selectable, so the drive headers are simply not flagged
selectable and up/down walks the games alone, wrapping, paging and scrolling into view
exactly as the library grid does. Two lists would have meant re-solving the focus-crossing
problem Phase 17 solved for the shelves, for no gain.

The bar behind each game runs the width of the row with the name painted on top of it, so
a long title is never squeezed by a bar competing for the same space -- which is what the
first draft did to "LEGO Batman: Legacy of the Dark Knight".

Since Phase 58 each drive is a card, as the design's #1f draws it: the delegate paints its
slice of the card behind every item, so the one list keeps both shapes.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QStyle,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

from shared import humanize
from logic import storage as storage_module
from presentation import ui_icons
from presentation import ui_pageshell
from presentation import ui_rules
from presentation import ui_theme

log = logging.getLogger(__name__)

KIND_ROLE = Qt.ItemDataRole.UserRole + 1
PAYLOAD_ROLE = Qt.ItemDataRole.UserRole + 2
KIND_DRIVE, KIND_GAME = "drive", "game"

SORT_LABELS = (
    ("Biggest first", storage_module.SORT_SIZE),
    ("Biggest and coldest first", storage_module.SORT_WEIGHTED),
)


def _bar_gradient(left: float, right: float) -> QLinearGradient:
    """The games' part of a capacity bar: accent 600 to the accent, as the design runs it."""
    gradient = QLinearGradient(left, 0, max(left + 1, right), 0)
    gradient.setColorAt(0.0, QColor(ui_rules.COLOR_STORAGE_GAMES_START))
    gradient.setColorAt(1.0, QColor(ui_rules.COLOR_STORAGE_GAMES))
    return gradient


def stale_tag() -> str:
    """The words on a game past the staleness threshold, in its row."""
    return f"not played in {rules_months()} months"


def _age(game) -> str:
    if game.last_played is not None:
        return humanize.when(game.last_played)
    if game.idle_days is None:
        return "never played"
    # For a game never played, the only honest clock is how long this launcher has known
    # about it -- nothing here knows when it was installed.
    return "never played"


class StorageDelegate(QStyledItemDelegate):
    """Paints both item shapes, and each drive's card behind them (Phase 58).

    `host` supplies metrics, the list and the current drive scale.
    """

    def __init__(self, host) -> None:
        super().__init__(host)
        self.host = host

    # -- geometry ---------------------------------------------------------------------------

    def _s(self, value: float) -> int:
        return max(1, round(value * self.host.metrics.scale))

    def _font(self, px: float, weight: int | None = None, family: str | None = None) -> QFont:
        font = QFont(family) if family else QFont(self.host.font())
        font.setPointSizeF(max(6.0, ui_theme.px_to_pt(px * self.host.metrics.scale)))
        if weight:
            font.setWeight(QFont.Weight(weight))
        return font

    def _drive_font(self) -> QFont:
        return self._font(ui_rules.STORAGE_DRIVE_PX, ui_rules.HEADING_WEIGHT, ui_icons.display_family())

    @staticmethod
    def _last_in_card(index) -> bool:
        following = index.sibling(index.row() + 1, 0)
        return not following.isValid() or following.data(KIND_ROLE) == KIND_DRIVE

    def _card_bottom(self, index) -> int:
        """Below the last row of a card: its padding, then the gap to the next card."""
        return self._s(ui_rules.STORAGE_CARD_PADDING_Y) + self._s(ui_rules.STORAGE_SECTION_SPACING)

    def sizeHint(self, option, index) -> QSize:
        last = self._last_in_card(index)
        if index.data(KIND_ROLE) != KIND_DRIVE:
            height = self._s(ui_rules.STORAGE_ROW_HEIGHT) + (
                self._card_bottom(index) if last else self._s(ui_rules.STORAGE_ROW_GAP))
            return QSize(10, height)
        # A drive Windows will not measure draws no capacity bar and no legend, so it must
        # not reserve their height either -- that left a conspicuous empty band under G:.
        drive = index.data(PAYLOAD_ROLE)
        gap = self._s(ui_rules.STORAGE_CARD_GAP)
        height = self._s(ui_rules.STORAGE_CARD_PADDING_Y) + QFontMetrics(self._drive_font()).height()
        if getattr(drive, "measured", True) and getattr(drive, "total", 0) > 0:
            legend = QFontMetrics(self._font(ui_rules.STORAGE_LEGEND_PX)).height()
            height += gap + self._s(ui_rules.STORAGE_CAPACITY_BAR_HEIGHT) + gap + legend
        height += self._card_bottom(index) if last else gap + self._s(ui_rules.STORAGE_ROWS_TOP)
        return QSize(10, height)

    def _card_rect(self, option, index) -> QRectF:
        """The whole of this item's drive card, from its header to under its last row."""
        view = self.host.list
        first = index
        while first.data(KIND_ROLE) != KIND_DRIVE and first.row() > 0:
            first = first.sibling(first.row() - 1, 0)
        last = index
        while not self._last_in_card(last):
            last = last.sibling(last.row() + 1, 0)
        top = view.visualRect(first).top()
        bottom = view.visualRect(last).bottom() + 1 - self._s(ui_rules.STORAGE_SECTION_SPACING)
        return QRectF(option.rect.left(), top, option.rect.width(), bottom - top)

    # -- painting ---------------------------------------------------------------------------

    def paint(self, painter, option, index) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        # This item's slice of its drive's card, so the cards read whole however the list
        # is scrolled or repainted.
        painter.save()
        painter.setClipRect(option.rect)
        card = self._card_rect(option, index).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = self._s(ui_rules.DETAIL_CARD_RADIUS)
        painter.setPen(QPen(QColor(ui_rules.COLOR_CARD_BORDER), 1))
        painter.setBrush(QColor(ui_rules.COLOR_CARD))
        painter.drawRoundedRect(card, radius, radius)
        painter.restore()
        if index.data(KIND_ROLE) == KIND_DRIVE:
            self._paint_drive(painter, option, index.data(PAYLOAD_ROLE))
        else:
            self._paint_game(painter, option, index)
        painter.restore()

    def _paint_drive(self, painter, option, drive) -> None:
        pad_x = self._s(ui_rules.STORAGE_CARD_PADDING_X)
        left = option.rect.left() + pad_x
        width = option.rect.width() - pad_x * 2
        top = option.rect.top() + self._s(ui_rules.STORAGE_CARD_PADDING_Y)

        # The drive, then its capacity on the same baseline, as the design sets them.
        name_font = self._drive_font()
        name_metrics = QFontMetrics(name_font)
        baseline = top + name_metrics.ascent()
        painter.setFont(name_font)
        painter.setPen(QColor(ui_rules.COLOR_TEXT))
        painter.drawText(QPointF(left, baseline), drive.letter)
        if drive.measured:
            summary = (
                f"{humanize.size(drive.free)} free of {humanize.size(drive.total)}"
                f"   ·   {len(drive.games)} game"
                f"{'s' if len(drive.games) != 1 else ''} here, "
                f"{humanize.size(drive.known_bytes)}"
            )
        else:
            summary = (
                f"{len(drive.games)} game{'s' if len(drive.games) != 1 else ''} here, "
                f"{humanize.size(drive.known_bytes)}   ·   "
                "Windows would not report this drive's capacity"
            )
        after = left + name_metrics.horizontalAdvance(drive.letter) + self._s(ui_rules.STORAGE_CAPACITY_GAP)
        small = self._font(ui_rules.STORAGE_CAPACITY_PX)
        painter.setFont(small)
        painter.setPen(QColor(ui_rules.COLOR_STORAGE_AGE))
        painter.drawText(QPointF(after, baseline), QFontMetrics(small).elidedText(
            summary, Qt.TextElideMode.ElideRight, max(0, round(left + width - after))))

        if not drive.measured or drive.total <= 0:
            return

        # The capacity bar: the games, everything else, and the free space, 2 px apart.
        gap = self._s(ui_rules.STORAGE_CARD_GAP)
        bar_top = top + name_metrics.height() + gap
        bar_h = self._s(ui_rules.STORAGE_CAPACITY_BAR_HEIGHT)
        full = QRectF(left, bar_top, width, bar_h)
        parts = [(drive.known_bytes, None), (drive.other_used, QColor(ui_rules.COLOR_STORAGE_OTHER)),
                 (drive.free, QColor(ui_rules.COLOR_STORAGE_FREE))]
        parts = [(size, colour) for size, colour in parts if size > 0]
        between = self._s(ui_rules.STORAGE_SEGMENT_GAP)
        room = max(0.0, width - between * (len(parts) - 1))
        total = max(1, sum(size for size, _ in parts))
        outline = QPainterPath()
        radius = self._s(ui_rules.STORAGE_BAR_RADIUS)
        outline.addRoundedRect(full, radius, radius)
        painter.save()
        painter.setClipPath(outline)
        painter.setPen(Qt.PenStyle.NoPen)
        x = left
        for size, colour in parts:
            span = room * size / total
            painter.setBrush(_bar_gradient(x, x + span) if colour is None else colour)
            painter.drawRect(QRectF(x, bar_top, span, bar_h))
            x += span + between
        painter.restore()

        # The legend: a small swatch and its words for each part.
        legend_font = self._font(ui_rules.STORAGE_LEGEND_PX)
        legend_metrics = QFontMetrics(legend_font)
        painter.setFont(legend_font)
        line_top = bar_top + bar_h + gap
        swatch = self._s(ui_rules.STORAGE_SWATCH_PX)
        swatch_radius = self._s(ui_rules.STORAGE_SWATCH_RADIUS)
        share = drive.known_bytes / drive.total * 100
        x = left
        for text, fill in (
            (f"These games {humanize.size(drive.known_bytes)} ({share:.1f}% of the drive)",
             ui_rules.COLOR_STORAGE_GAMES),
            (f"Everything else {humanize.size(drive.other_used)}", ui_rules.COLOR_STORAGE_OTHER),
            (f"Free {humanize.size(drive.free)}", ui_rules.COLOR_STORAGE_FREE),
        ):
            box = QRectF(x, line_top + (legend_metrics.height() - swatch) / 2, swatch, swatch)
            painter.setBrush(QColor(fill))
            painter.setPen(QPen(QColor(ui_rules.COLOR_STORAGE_OTHER), 1)
                           if fill == ui_rules.COLOR_STORAGE_FREE else Qt.PenStyle.NoPen)
            painter.drawRoundedRect(box.adjusted(0.5, 0.5, -0.5, -0.5) if fill == ui_rules.COLOR_STORAGE_FREE
                                    else box, swatch_radius, swatch_radius)
            x += swatch + self._s(ui_rules.STORAGE_SWATCH_GAP)
            painter.setPen(QColor(ui_rules.COLOR_STORAGE_AGE))
            painter.drawText(QPointF(x, line_top + legend_metrics.ascent()), text)
            x += legend_metrics.horizontalAdvance(text) + self._s(ui_rules.STORAGE_LEGEND_GAP)

    def row_rect(self, option_rect) -> QRectF:
        """Where a game's row is drawn inside its item: in from the card's sides, at its top."""
        pad_x = self._s(ui_rules.STORAGE_CARD_PADDING_X)
        return QRectF(option_rect.left() + pad_x, option_rect.top(),
                      option_rect.width() - pad_x * 2, self._s(ui_rules.STORAGE_ROW_HEIGHT))

    def _paint_game(self, painter, option, index) -> None:
        game = index.data(PAYLOAD_ROLE)
        row = self.row_rect(option.rect)
        radius = self._s(ui_rules.STORAGE_ROW_RADIUS)

        # The row's glass, and the game's bar from its left edge: as long as the game is
        # big against the drive's biggest, under the words and cut to the row's corners.
        outline = QPainterPath()
        outline.addRoundedRect(row, radius, radius)
        painter.save()
        painter.setClipPath(outline)
        painter.fillRect(row, QColor(ui_rules.COLOR_STORAGE_ROW))
        biggest = max(1, self.host.biggest_on_drive(game))
        fraction = min(1.0, game.bytes / biggest)
        drawn = max(self._s(ui_rules.STORAGE_BAR_MIN_PX), round(row.width() * fraction))
        painter.fillRect(QRectF(row.left(), row.top(), drawn, row.height()),
                         QColor(ui_rules.COLOR_STORAGE_STALE_BAR if game.stale else ui_rules.COLOR_STORAGE_BAR))
        painter.restore()

        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        if selected:
            # The focus colour, as on the tiles and the game page -- what the pad is on
            # reads the same on every page from across a room.
            pen_width = max(1, round(self.host.focus_ring_width * self.host.metrics.scale))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(ui_rules.TILE_FOCUS_COLOR), pen_width))
            painter.drawRoundedRect(row.adjusted(pen_width / 2, pen_width / 2, -pen_width / 2, -pen_width / 2),
                                    radius, radius)

        inner = self._s(ui_rules.STORAGE_ROW_PADDING)
        size_col = self._s(ui_rules.STORAGE_SIZE_COLUMN)
        age_col = self._s(ui_rules.STORAGE_AGE_COLUMN)
        right = row.right() - inner
        name_room = right - size_col - age_col - (row.left() + inner)

        tag_font = self._font(ui_rules.STORAGE_TAG_PX)
        tag_metrics = QFontMetrics(tag_font)
        tag_text = stale_tag() if game.stale else ""
        tag_pad_x = self._s(ui_rules.STORAGE_TAG_PADDING_X)
        tag_w = tag_metrics.horizontalAdvance(tag_text) + tag_pad_x * 2 if tag_text else 0
        tag_gap = self._s(ui_rules.STORAGE_TAG_GAP) if tag_text else 0

        name_font = self._font(ui_rules.STORAGE_NAME_PX, ui_rules.HEADING_WEIGHT if selected else None)
        painter.setFont(name_font)
        painter.setPen(QColor(ui_rules.COLOR_TEXT))
        metrics = QFontMetrics(name_font)
        name = metrics.elidedText(game.name, Qt.TextElideMode.ElideRight,
                                  max(0, round(name_room - tag_w - tag_gap)))
        painter.drawText(QRectF(row.left() + inner, row.top(), max(0.0, name_room), row.height()),
                         int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), name)

        if tag_text:
            tag_h = tag_metrics.height() + self._s(ui_rules.STORAGE_TAG_PADDING_Y) * 2
            tag = QRectF(row.left() + inner + metrics.horizontalAdvance(name) + tag_gap,
                         row.center().y() - tag_h / 2, tag_w, tag_h)
            tag_radius = self._s(ui_rules.STORAGE_TAG_RADIUS)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(ui_rules.COLOR_STORAGE_TAG), 1))
            painter.drawRoundedRect(tag.adjusted(0.5, 0.5, -0.5, -0.5), tag_radius, tag_radius)
            painter.setFont(tag_font)
            painter.drawText(tag, int(Qt.AlignmentFlag.AlignCenter), tag_text)

        painter.setFont(self._font(ui_rules.STORAGE_AGE_PX))
        painter.setPen(QColor(ui_rules.COLOR_STORAGE_AGE))
        painter.drawText(QRectF(right - size_col - age_col, row.top(), age_col, row.height()),
                         int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), _age(game))
        painter.setFont(self._font(ui_rules.STORAGE_NAME_PX))
        painter.setPen(QColor(ui_rules.COLOR_TEXT))
        painter.drawText(QRectF(right - size_col, row.top(), size_col, row.height()),
                         int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                         humanize.size(game.bytes))


class Treemap(QWidget):
    """The library as rectangles, area proportional to size. **Mouse only, by design.**

    It carries no keyboard or pad path and never holds focus: the ranked list below is the
    required way through this page and the only one a controller uses. The map is hidden
    entirely in TV mode, where there is no mouse to drive it and it would only be taking
    room from the list.

    Colours come from `ui_theme.accent_for`, the same name-derived accent the placeholder
    covers use, so a game is the same colour here as its tile is in the grid.
    """

    gameActivated = Signal(str)

    def __init__(self, metrics, parent=None) -> None:
        super().__init__(parent)
        self.metrics = metrics
        self.games: list = []
        self._rects: list[tuple] = []
        self._hover = -1
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._resize()

    def set_games(self, games) -> None:
        self.games = sorted(games, key=lambda g: -g.bytes)
        self._hover = -1
        self._rects = []
        self.update()

    def apply_metrics(self, metrics) -> None:
        self.metrics = metrics
        self._resize()

    def _resize(self) -> None:
        self.setFixedHeight(max(80, round(ui_rules.STORAGE_TREEMAP_HEIGHT * self.metrics.scale)))

    def _layout(self) -> None:
        self._rects = storage_module.squarify(
            [max(1, g.bytes) for g in self.games], 0, 0, self.width(), self.height()
        )

    def _at(self, point) -> int:
        for index, (x, y, w, h) in enumerate(self._rects):
            if x <= point.x() < x + w and y <= point.y() < y + h:
                return index
        return -1

    def resizeEvent(self, event) -> None:
        self._rects = []
        super().resizeEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if not self._rects:
            self._layout()
        index = self._at(event.position())
        if index != self._hover:
            self._hover = index
            game = self.games[index] if 0 <= index < len(self.games) else None
            self.setToolTip(
                f"{game.name}\n{humanize.size(game.bytes)}\nLast played: {_age(game)}"
                if game
                else ""
            )
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = -1
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if not self._rects:
            self._layout()
        index = self._at(event.position())
        if 0 <= index < len(self.games):
            self.gameActivated.emit(self.games[index].key)
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:
        if not self.games:
            return
        if not self._rects:
            self._layout()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        font = QFont(self.font())
        font.setPointSize(max(7, round(ui_rules.STORAGE_TREEMAP_FONT_PT * self.metrics.scale)))
        painter.setFont(font)
        metrics = QFontMetrics(font)
        gap = max(1, round(ui_rules.STORAGE_TREEMAP_TILE_GAP * self.metrics.scale))
        radius = max(2, round(ui_rules.STORAGE_TREEMAP_RADIUS * self.metrics.scale))

        for index, (game, (x, y, w, h)) in enumerate(zip(self.games, self._rects)):
            colour = ui_theme.accent_for(game.name)
            if index == self._hover:
                colour = colour.lighter(ui_rules.STORAGE_TREEMAP_HOVER_LIGHTEN)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(colour)
            tile = QRectF(x, y, max(0.0, w - gap), max(0.0, h - gap))
            painter.drawRoundedRect(tile, min(radius, tile.width() / 2, tile.height() / 2),
                                    min(radius, tile.width() / 2, tile.height() / 2))

            # Anything too small for its own name is left as a coloured block and answers
            # through the tooltip instead. Cramming two characters in would be worse.
            if w < ui_rules.STORAGE_TREEMAP_MIN_LABEL_PX or h < metrics.height() * 2:
                continue
            pad = max(2, round(4 * self.metrics.scale))
            painter.setPen(QColor(ui_rules.COLOR_TEXT))
            painter.drawText(
                QRectF(x + pad, y + pad, w - gap - pad * 2, h - gap - pad * 2),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop),
                metrics.elidedText(game.name, Qt.TextElideMode.ElideRight,
                                   int(w - gap - pad * 2))
                + "\n"
                + humanize.size(game.bytes),
            )
        painter.end()


class StoragePage(QWidget):
    """Read only, by design and by construction: nothing here writes or deletes."""

    backRequested = Signal()
    tabSelected = Signal(str)
    gameActivated = Signal(str)
    contextRequested = Signal(str, object)
    sortChanged = Signal(str)

    def __init__(self, metrics, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("StoragePage")
        self.metrics = metrics
        self.focus_ring_width = ui_rules.FOCUS_RING_WIDTH
        # The map is mouse-only, so it is not shown on a screen being driven from a couch.
        self.show_treemap = True
        self.storage: storage_module.Storage | None = None
        self._biggest: dict[str, int] = {}
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._build()

    # -- construction -----------------------------------------------------------------------

    def _build(self) -> None:
        self.header_row = ui_pageshell.PageHeader(ui_pageshell.TAB_STORAGE, self)
        self.header_row.backRequested.connect(self.backRequested)
        self.header_row.tabSelected.connect(self.tabSelected)

        self.summary = QLabel()
        self.summary.setObjectName("Meta")
        self.summary.setWordWrap(True)

        self.sort_box = QComboBox()
        self.sort_box.setObjectName("SortBox")  # the library's pill (Phase 35)
        self.sort_box.setCursor(Qt.CursorShape.PointingHandCursor)
        for label, _mode in SORT_LABELS:
            self.sort_box.addItem(label)
        self.sort_box.setToolTip(
            "Biggest first ranks purely by size.\n"
            "Biggest and coldest first pushes games you have not played in a long while up."
        )
        self.sort_box.currentIndexChanged.connect(self._sort_picked)

        sort_label = QLabel("Sort by")
        sort_label.setObjectName("SortLabel")
        controls = QHBoxLayout()
        controls.addWidget(self.summary, 1)
        controls.addWidget(sort_label)
        controls.addWidget(self.sort_box)

        # The design's strip: an icon, a line saying what could be reclaimed, and a quieter
        # line naming the games. With nothing to reclaim it is a plain card saying why.
        self.reclaim = QFrame()
        self.reclaim.setObjectName("ReclaimStrip")
        self.reclaim_icon = QLabel()
        self.reclaim_icon.setObjectName("ReclaimIcon")
        self.reclaim_label = QLabel()
        self.reclaim_label.setObjectName("ReclaimTitle")
        self.reclaim_label.setWordWrap(True)
        self.reclaim_line = QLabel()
        self.reclaim_line.setObjectName("ReclaimLine")
        self.reclaim_line.setWordWrap(True)
        words = QVBoxLayout()
        words.setContentsMargins(0, 0, 0, 0)
        words.setSpacing(0)
        words.addWidget(self.reclaim_label)
        words.addWidget(self.reclaim_line)
        reclaim_layout = QHBoxLayout(self.reclaim)
        reclaim_layout.addWidget(self.reclaim_icon, 0, Qt.AlignmentFlag.AlignVCenter)
        reclaim_layout.addLayout(words, 1)

        self.treemap = Treemap(self.metrics, self)
        self.treemap.gameActivated.connect(self.gameActivated)
        self.treemap.setToolTip("Every game by size. Click one to open it.")

        self.list = QListWidget()
        self.list.setObjectName("StorageList")
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.list.setItemDelegate(StorageDelegate(self))
        self.list.setUniformItemSizes(False)  # two item shapes; see the Phase 2 trap
        self.list.itemActivated.connect(self._activate)
        self.list.itemClicked.connect(self._activate)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._context_menu)

        # Shown instead of the list when there is nothing to rank. A page whose whole
        # middle is blank reads as broken; one that says why reads as finished.
        self.empty_label = QLabel(
            "Nothing to measure yet.\n\n"
            "Press Rescan in the library and the games found on your drives appear here, "
            "biggest first."
        )
        self.empty_label.setObjectName("StorageEmpty")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setWordWrap(True)
        self.empty_label.setVisible(False)

        self.footnote = QLabel()
        self.footnote.setObjectName("Meta")
        self.footnote.setWordWrap(True)

        body = QWidget()
        body.setObjectName("Clear")  # the library's glow shows through (Phase 35)
        self.body_layout = QVBoxLayout(body)
        # Beside the side rail (Phase 60) the page carries its own name, as the library does.
        self.page_title = QLabel("Storage")
        self.page_title.setObjectName("PageTitle")
        self.page_title.setVisible(False)
        self.body_layout.addWidget(self.page_title)
        self.rail = False
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.addLayout(controls)
        self.body_layout.addWidget(self.reclaim)
        self.body_layout.addWidget(self.treemap)
        self.body_layout.addWidget(self.list, 1)
        self.body_layout.addWidget(self.empty_label, 1)
        self.body_layout.addWidget(self.footnote)
        self.content = body

        # One column, placed as the design places it: see ui_pageshell.PageColumn.
        self.column = ui_pageshell.PageColumn(body, ui_rules.STORAGE_CONTENT_MAX_WIDTH)
        self.header_column = ui_pageshell.PageColumn(self.header_row, ui_rules.STORAGE_CONTENT_MAX_WIDTH)
        layout = QVBoxLayout(self)
        layout.addWidget(self.header_column)
        layout.addWidget(self.column, 1)
        self.apply_metrics(self.metrics)

    # -- filling it in ----------------------------------------------------------------------

    def set_storage(self, value: storage_module.Storage) -> None:
        self.storage = value
        self._biggest = {d.letter: d.biggest for d in value.drives}

        with_block = self.sort_box.blockSignals(True)
        self.sort_box.setCurrentIndex(
            next((i for i, (_l, m) in enumerate(SORT_LABELS) if m == value.sort_mode), 0)
        )
        self.sort_box.blockSignals(with_block)

        drives = len(value.drives)
        self.summary.setText(
            f"{len(value.games)} games taking {humanize.size(value.known_bytes)} across "
            f"{drives} drive{'s' if drives != 1 else ''}."
            if value.games
            else "No games to measure yet."
        )
        # With nothing to rank, the list, the ordering control and the reclaim strip are
        # all controls over an empty set; showing them would be three pieces of furniture
        # around a hole.
        has_games = bool(value.games)
        self.list.setVisible(has_games)
        self.treemap.set_games(value.games)
        self.treemap.setVisible(has_games and self.show_treemap)
        self.empty_label.setVisible(not has_games)
        self.reclaim.setVisible(has_games)
        self.sort_box.setEnabled(has_games)

        self._fill_reclaim(value)
        self._fill_list(value)
        # Every visit rebuilds the list, so every visit starts at its top with the first game
        # chosen (Phase 62). Left to ensure_focus, a list that still held the focus had a row
        # made current by Qt as it refilled, and kept the old scroll -- reopened scrolled away.
        self.select_first()
        QTimer.singleShot(0, self._fit_map)
        self.footnote.setText(self._footnote(value))

    def _fill_reclaim(self, value: storage_module.Storage) -> None:
        months = rules_months()
        count = len(value.reclaimable)
        if value.reclaimable:
            names = ", ".join(g.name for g in value.reclaimable[:3])
            more = f" and {count - 3} more" if count > 3 else ""
            self.reclaim_label.setText(
                f"{count} game{'s' if count != 1 else ''} not played in over {months} months "
                f"take{'s' if count == 1 else ''} {humanize.size(value.reclaimable_bytes)}"
            )
            self.reclaim_line.setText(f"{names}{more}.")
        else:
            # The normal state on a young library, and it says why rather than showing an
            # empty box that looks like a feature that failed to load.
            self.reclaim_label.setText(f"Nothing has gone {months} months unplayed")
            self.reclaim_line.setText(
                "This fills in as games sit unused; until then, Biggest and coldest first is "
                "the more useful order."
            )
        populated = bool(value.reclaimable)
        px = max(12, round(ui_rules.STORAGE_RECLAIM_ICON_PX * self.metrics.scale))
        self.reclaim_icon.setPixmap(ui_icons.glyph_pixmap(
            "broom", ui_rules.COLOR_RECLAIM_ICON if populated else ui_rules.COLOR_TEXT_MUTED,
            px, self.devicePixelRatioF() or 1.0))
        for widget in (self.reclaim, self.reclaim_label, self.reclaim_line):
            widget.setProperty("populated", populated)
            widget.style().unpolish(widget)
            widget.style().polish(widget)

    def _fill_list(self, value: storage_module.Storage) -> None:
        self.list.clear()
        for drive in value.drives:
            header = QListWidgetItem()
            header.setData(KIND_ROLE, KIND_DRIVE)
            header.setData(PAYLOAD_ROLE, drive)
            # Not selectable and not enabled: Qt's arrow navigation steps straight over it,
            # which is what lets one list carry both shapes and still be pad-navigable.
            header.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list.addItem(header)
            for game in drive.games:
                row = QListWidgetItem()
                row.setData(KIND_ROLE, KIND_GAME)
                row.setData(PAYLOAD_ROLE, game)
                row.setData(Qt.ItemDataRole.UserRole, game.key)
                row.setToolTip(
                    f"{game.name}\n{humanize.size(game.bytes)}\nLast played: {_age(game)}"
                )
                self.list.addItem(row)

    def _footnote(self, value: storage_module.Storage) -> str:
        when = (
            f"measured during the last scan, {humanize.moment(value.scanned_at)}"
            if value.scanned_at
            else "measured during the last scan"
        )
        text = (
            f"Game sizes are {when} — press Rescan in the library to bring them up to date. "
            "Free space is read now."
        )
        if value.missing_sizes:
            text += (
                f" {value.missing_sizes} game"
                f"{'s' if value.missing_sizes != 1 else ''} did not report a size and "
                "counts as nothing here."
            )
        return text

    # -- interaction ------------------------------------------------------------------------

    def biggest_on_drive(self, game) -> int:
        """Bars are scaled against the biggest game on the same drive, not the library's.

        A drive holding one 40 GB game should show it full width; scaling every drive
        against a 142 GB game on another one would make a whole disk look empty.
        """
        for letter, biggest in self._biggest.items():
            if any(g.key == game.key for g in self._games_on(letter)):
                return biggest
        return game.bytes

    def _games_on(self, letter: str):
        if self.storage is None:
            return []
        return next((d.games for d in self.storage.drives if d.letter == letter), [])

    def _sort_picked(self, index: int) -> None:
        self.sortChanged.emit(SORT_LABELS[max(0, index)][1])

    def _activate(self, item: QListWidgetItem) -> None:
        if item is None or item.data(KIND_ROLE) != KIND_GAME:
            return
        key = item.data(Qt.ItemDataRole.UserRole)
        if key:
            self.gameActivated.emit(str(key))

    def _context_menu(self, position) -> None:
        """The same menu the library grid shows, so a row here offers the same actions."""
        item = self.list.itemAt(position)
        if item is None or item.data(KIND_ROLE) != KIND_GAME:
            return
        key = item.data(Qt.ItemDataRole.UserRole)
        if key:
            self.contextRequested.emit(str(key), self.list.viewport().mapToGlobal(position))

    def context_for_current(self) -> None:
        """The pad's Menu button, on whatever row is selected."""
        item = self.list.currentItem()
        if item is None or item.data(KIND_ROLE) != KIND_GAME:
            return
        key = item.data(Qt.ItemDataRole.UserRole)
        rect = self.list.visualItemRect(item)
        if key:
            self.contextRequested.emit(
                str(key), self.list.viewport().mapToGlobal(rect.center())
            )

    def activate_current(self) -> None:
        self._activate(self.list.currentItem())

    def move_focus(self, key: int) -> None:
        """Hand a synthesised key press to the list, exactly as the grid does."""
        if self.list.currentItem() is None:
            self.select_first()
            return
        from PySide6.QtCore import QEvent
        from PySide6.QtGui import QKeyEvent
        from PySide6.QtWidgets import QApplication

        event = QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(self.list, event)

    def select_first(self) -> None:
        for row in range(self.list.count()):
            item = self.list.item(row)
            if item.data(KIND_ROLE) == KIND_GAME:
                # The first game sits right under its drive's card top, so the list's own
                # top shows both (Phase 62). Qt scrolls just far enough to reveal a row it
                # is given -- which hid the drive's name whenever the two did not fit --
                # and, for a list not on screen yet, does it later, as the page appears,
                # undoing any scroll made here. Its auto-scroll is off for this one choice
                # only; the pad's moves still scroll rows into view.
                auto = self.list.hasAutoScroll()
                self.list.setAutoScroll(False)
                self.list.setCurrentItem(item)
                self.list.setAutoScroll(auto)
                self.list.scrollToTop()
                return

    def ensure_focus(self) -> None:
        # Choose before focusing. Taking the focus makes Qt mark the first row current
        # *without selecting it*, and the ring is drawn for the selected row -- so the page
        # opened with nothing ringed until the pad moved (found by rendering, Phase 35).
        if self.list.currentItem() is None:
            self.select_first()
        self.list.setFocus(Qt.FocusReason.OtherFocusReason)
        current = self.list.currentItem()
        if current is not None and not current.isSelected():
            current.setSelected(True)

    # -- chrome -----------------------------------------------------------------------------

    def apply_metrics(self, metrics) -> None:
        self.metrics = metrics
        s = metrics.scale
        top = ui_rules.RAIL_PAGE_TOP if getattr(self, "rail", False) else ui_rules.PAGE_COLUMN_TOP
        self.layout().setContentsMargins(0, max(6, round(top * s)), 0,
                                         max(10, round(ui_rules.STATS_PAGE_MARGIN * s)))
        self.layout().setSpacing(0)
        self.body_layout.setSpacing(max(6, round(ui_rules.STORAGE_SECTION_SPACING * s)))
        reclaim = self.reclaim.layout()
        reclaim.setContentsMargins(*(max(6, round(v * s)) for v in (
            ui_rules.STORAGE_RECLAIM_PADDING_X, ui_rules.STORAGE_RECLAIM_PADDING_Y,
            ui_rules.STORAGE_RECLAIM_PADDING_X, ui_rules.STORAGE_RECLAIM_PADDING_Y)))
        reclaim.setSpacing(max(6, round(ui_rules.STORAGE_RECLAIM_GAP * s)))
        self.treemap.apply_metrics(metrics)
        self.sort_box.setFixedHeight(max(20, round(ui_rules.CHIP_HEIGHT * s)))
        cap = round(ui_rules.STORAGE_CONTENT_MAX_WIDTH * s)
        self.content.setMaximumWidth(cap)
        self.header_row.setMaximumWidth(cap)
        for column in (self.column, self.header_column):
            column.set_scale(s)
        # The delegate reads metrics off this page, so the rows resize with everything else.
        self.list.reset()
        if self.storage is not None:
            self._fill_list(self.storage)
            self._fill_reclaim(self.storage)
        QTimer.singleShot(0, self._fit_map)  # the map was just reset to its full height

    def set_rail(self, rail: bool) -> None:
        """Beside the side rail or under the top bar (Phase 60): the column's place, the top."""
        self.rail = rail
        self.page_title.setVisible(rail)
        for column in (self.column, self.header_column):
            column.set_rail(rail)
        self.apply_metrics(self.metrics)

    # -- the map gives way to the list (Phase 62) -------------------------------------------

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit_map()

    def _list_room(self) -> int:
        """What the list needs to show its first drive's card top and the rows under it."""
        rows = min(self.list.count(), 1 + ui_rules.STORAGE_LIST_MIN_ROWS)
        return sum(self.list.sizeHintForRow(r) for r in range(rows)) + 2 * self.list.frameWidth()

    def _fit_map(self) -> None:
        """Share the height the map and the list have between them: the list keeps its room,
        the map takes up to its full height of what is left, and steps aside when that is
        less than its smallest. Depends only on what the two have together, so running it
        again changes nothing."""
        if self.storage is None or not self.storage.games or not self.show_treemap:
            return
        s = self.metrics.scale
        full = max(80, round(ui_rules.STORAGE_TREEMAP_HEIGHT * s))
        least = round(ui_rules.STORAGE_TREEMAP_MIN_HEIGHT * s)
        gap = self.body_layout.spacing()
        shared = self.list.height() + (self.treemap.height() + gap if self.treemap.isVisibleTo(self) else 0)
        left = shared - gap - self._list_room()
        if left >= least:
            self.treemap.setFixedHeight(min(full, left))
            self.treemap.setVisible(True)
        else:
            self.treemap.setVisible(False)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.backRequested.emit()
            return
        super().keyPressEvent(event)


def rules_months() -> int:
    """The staleness threshold in months, for saying it out loud."""
    from shared import rules

    return max(1, round(rules.RECLAIM_STALE_DAYS / 30.44))


def stylesheet(scale: float) -> str:
    """Appended to the app stylesheet; only affects this page."""
    s = lambda value: max(1, round(value * scale))  # noqa: E731
    pt = lambda px: f"{ui_theme.px_to_pt(px * scale):.2f}pt"  # noqa: E731 -- fractional px
    return f"""
    QFrame#ReclaimStrip {{
        background: {ui_rules.COLOR_CARD};
        border: 1px solid {ui_rules.COLOR_CARD_BORDER};
        border-radius: {s(ui_rules.STORAGE_RECLAIM_RADIUS)}px;
    }}
    QFrame#ReclaimStrip[populated="true"] {{
        background: {ui_rules.COLOR_RECLAIM};
        border-color: {ui_rules.COLOR_RECLAIM_EDGE};
    }}
    QFrame#ReclaimStrip QLabel {{ background: transparent; border: none; }}
    QLabel#ReclaimTitle {{
        font-size: {s(ui_rules.STORAGE_RECLAIM_TITLE_PX)}px;
        font-weight: {ui_rules.HEADING_WEIGHT};
        color: {ui_rules.COLOR_TEXT};
    }}
    QLabel#ReclaimTitle[populated="true"] {{ color: {ui_rules.COLOR_RECLAIM_TITLE}; }}
    QLabel#ReclaimLine {{ font-size: {pt(ui_rules.STORAGE_RECLAIM_LINE_PX)}; color: {ui_rules.COLOR_TEXT_MUTED}; }}
    QLabel#ReclaimLine[populated="true"] {{ color: {ui_rules.COLOR_RECLAIM_LINE}; }}
    QListWidget#StorageList {{ background: transparent; border: none; }}
    QLabel#StorageEmpty {{
        color: {ui_rules.COLOR_TEXT_MUTED};
        font-size: {s(ui_rules.STORAGE_NAME_PX)}px;
    }}
    """
