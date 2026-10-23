"""The Wishlist page (Phase 87): what the user said he wants, against today's price and what he plays.

A fifth place after Reports, in the top bar, the side rail and the pad's left/right walk. Rows like
Storage's, not tiles -- a wished game is a line of facts, not a picture to pick: its cover, its
name, today's price (the one before struck through when it is on sale, and the discount), the
lowest the series has seen and how many prices it holds -- from three prices on, the series as a
small line beside them (Phase 89) -- a tag when today is the lowest, the fit line ("33% like what
you play · Strategy, Action", rarity-weighted since Phase 89), when it was added, whose list it is
on when more than one account is marked mine, and the hours already played on it. Every part is
drawn only when its data exists; logic/wishlist.py puts each in words.

The order is the one ranking on the page, and it is said on every row: on sale first, the deepest
discount first, then the fit. Two chips, All and On sale; the games no longer on any list, and the
ones hidden from the page, under a fold each. A (or a double click) opens the game's store page in
Steam; X a menu -- Open in Steam, Hide from this page (a mark on this PC, never a change to the
Steam list), or Show on this page again. Y switches the chips. Nothing here writes to Steam.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QEvent, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QKeyEvent, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QButtonGroup, QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QStyle, QStyledItemDelegate, QVBoxLayout, QWidget)

from logic import wishlist as wishlist_module
from presentation import ui_icons
from presentation import ui_pageshell
from presentation import ui_rules
from presentation import ui_theme
from presentation.ui_library import Chip

log = logging.getLogger(__name__)

KIND_ROLE = Qt.ItemDataRole.UserRole + 1
PAYLOAD_ROLE = Qt.ItemDataRole.UserRole + 2
KIND_GAME, KIND_GROUP = "game", "group"
GROUP_REMOVED, GROUP_HIDDEN = "removed", "hidden"
GROUP_WORDS = {GROUP_REMOVED: "No longer on your list", GROUP_HIDDEN: "Hidden from this page"}
LOWEST_TAG = "Lowest seen"
UNAVAILABLE = ("The wishlist reads the library database at its newest version. This copy is still on an "
               "older one: start the launcher again and it upgrades the file (a backup is taken first).")
CHOICES = ((wishlist_module.ALL, "All"), (wishlist_module.ON_SALE, "On sale"),
           (wishlist_module.ALERTS, "Alerts"))  # Phase 101: the alerts of the last ALERT_KEEP_DAYS


class WishlistDelegate(QStyledItemDelegate):
    """Paints a wished game's row, and a fold's line. `host` is the page: metrics, covers, ring width."""

    def __init__(self, host) -> None:
        super().__init__(host)
        self.host = host

    def _s(self, value: float) -> int:
        return max(1, round(value * self.host.metrics.scale))

    def _font(self, px: float, weight: int | None = None, strike: bool = False) -> QFont:
        font = QFont(self.host.font())
        font.setPointSizeF(max(6.0, ui_theme.px_to_pt(px * self.host.metrics.scale)))
        font.setWeight(QFont.Weight(weight or ui_rules.BODY_WEIGHT))
        font.setStrikeOut(strike)
        return font

    def sizeHint(self, option, index) -> QSize:
        if index.data(KIND_ROLE) == KIND_GROUP:
            return QSize(10, self._s(ui_rules.WISHLIST_GROUP_HEIGHT))
        return QSize(10, self._s(ui_rules.WISHLIST_ROW_HEIGHT) + self._s(ui_rules.WISHLIST_ROW_GAP))

    def row_rect(self, option_rect) -> QRectF:
        return QRectF(option_rect.left(), option_rect.top(), option_rect.width(),
                      self._s(ui_rules.WISHLIST_ROW_HEIGHT))

    def spark_rect(self, rect: QRectF) -> QRectF:
        """Where a row's price line goes (Phase 89): just left of the price column, centred on the row."""
        right = rect.right() - self._s(ui_rules.WISHLIST_ROW_PADDING)
        width, height = self._s(ui_rules.WISHLIST_SPARK_WIDTH), self._s(ui_rules.WISHLIST_SPARK_HEIGHT)
        left = right - self._s(ui_rules.WISHLIST_PRICE_COLUMN) - self._s(ui_rules.WISHLIST_SPARK_GAP) - width
        return QRectF(left, rect.center().y() - height / 2, width, height)

    def paint(self, painter, option, index) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        if index.data(KIND_ROLE) == KIND_GROUP:
            self._paint_group(painter, option, index)
        else:
            self._paint_row(painter, option, index.data(PAYLOAD_ROLE))
        painter.restore()

    def _ring(self, painter, option, rect: QRectF, radius: float) -> None:
        if option.state & QStyle.StateFlag.State_Selected:
            width = max(1, round(self.host.focus_ring_width * self.host.metrics.scale))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(ui_rules.TILE_FOCUS_COLOR), width))
            painter.drawRoundedRect(rect.adjusted(width / 2, width / 2, -width / 2, -width / 2), radius, radius)

    def _paint_group(self, painter, option, index) -> None:
        group, count = index.data(PAYLOAD_ROLE)
        rect = QRectF(option.rect).adjusted(0, 2, 0, -2)
        radius = self._s(ui_rules.WISHLIST_ROW_RADIUS)
        self._ring(painter, option, rect, radius)
        folded = group not in self.host.unfolded
        words = f"{GROUP_WORDS[group]} · {count} · {'show' if folded else 'hide'}"
        painter.setFont(self._font(ui_rules.WISHLIST_GROUP_PX, ui_rules.HEADING_WEIGHT))
        painter.setPen(QColor(ui_rules.COLOR_WISHLIST_GROUP))
        painter.drawText(rect.adjusted(self._s(ui_rules.WISHLIST_ROW_PADDING), 0, 0, 0),
                         int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), words)

    def _tag(self, painter, x: float, mid: float, text: str, filled: bool) -> float:
        """A small tag -- the discount filled, "Lowest seen" outlined -- from x; answers its width."""
        font = self._font(ui_rules.WISHLIST_TAG_PX, ui_rules.LABEL_WEIGHT if filled else None)
        metrics = QFontMetrics(font)
        width = metrics.horizontalAdvance(text) + self._s(ui_rules.WISHLIST_TAG_PADDING_X) * 2
        height = metrics.height() + self._s(ui_rules.WISHLIST_TAG_PADDING_Y) * 2
        box = QRectF(x, mid - height / 2, width, height)
        radius = self._s(ui_rules.WISHLIST_TAG_RADIUS)
        if filled:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(ui_rules.COLOR_WISHLIST_DISCOUNT))
            painter.drawRoundedRect(box, radius, radius)
            painter.setPen(QColor(ui_rules.COLOR_WISHLIST_DISCOUNT_TEXT))
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(ui_rules.COLOR_WISHLIST_LOWEST), 1))
            painter.drawRoundedRect(box.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
        painter.setFont(font)
        painter.drawText(box, int(Qt.AlignmentFlag.AlignCenter), text)
        return width

    def _paint_row(self, painter, option, row) -> None:
        rect = self.row_rect(option.rect)
        radius = self._s(ui_rules.WISHLIST_ROW_RADIUS)
        outline = QPainterPath()
        outline.addRoundedRect(rect, radius, radius)
        painter.fillPath(outline, QColor(ui_rules.COLOR_WISHLIST_ROW))
        self._ring(painter, option, rect, radius)

        pad = self._s(ui_rules.WISHLIST_ROW_PADDING)
        art_h = self._s(ui_rules.WISHLIST_ART_HEIGHT)
        art = QRectF(rect.left() + pad, rect.center().y() - art_h / 2, round(art_h * 2 / 3), art_h)
        self._paint_art(painter, art, row.appid)

        left = art.right() + self._s(ui_rules.WISHLIST_ART_GAP)
        column = self._s(ui_rules.WISHLIST_PRICE_COLUMN)
        right = rect.right() - pad
        words_right = right - column - self._s(ui_rules.WISHLIST_TAG_GAP)
        if row.series:
            spark = self.spark_rect(rect)
            self._paint_series(painter, spark, row.series)
            words_right = spark.left() - self._s(ui_rules.WISHLIST_SPARK_GAP)
        gap = self._s(ui_rules.WISHLIST_LINE_GAP)

        name_font = self._font(ui_rules.WISHLIST_NAME_PX, ui_rules.HEADING_WEIGHT)
        line_font = self._font(ui_rules.WISHLIST_LINE_PX)
        name_h, line_h = QFontMetrics(name_font).height(), QFontMetrics(line_font).height()
        meta = " · ".join(part for part in (row.added, row.accounts, row.played) if part)
        # On the Alerts list the alert takes the fit line's place, in the accent: the row is the alert (Phase 101).
        first = (row.alert, ui_rules.COLOR_ACCENT_HOVER) if row.alert else (row.fit.words, ui_rules.COLOR_WISHLIST_FIT)
        lines = [first, (meta, ui_rules.COLOR_WISHLIST_META)]
        lines = [(text, colour) for text, colour in lines if text]
        top = rect.center().y() - (name_h + len(lines) * (line_h + gap)) / 2

        # The name, and "Lowest seen" after it when today is the lowest.
        tag_w = 0.0
        if row.lowest_now:
            tag_font = QFontMetrics(self._font(ui_rules.WISHLIST_TAG_PX))
            tag_w = tag_font.horizontalAdvance(LOWEST_TAG) + self._s(ui_rules.WISHLIST_TAG_PADDING_X) * 2
            tag_w += self._s(ui_rules.WISHLIST_TAG_GAP)
        painter.setFont(name_font)
        painter.setPen(QColor(ui_rules.COLOR_TEXT))
        name = QFontMetrics(name_font).elidedText(row.name, Qt.TextElideMode.ElideRight,
                                                  max(0, round(words_right - left - tag_w)))
        painter.drawText(QRectF(left, top, max(0.0, words_right - left), name_h),
                         int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), name)
        if row.lowest_now:
            x = left + QFontMetrics(name_font).horizontalAdvance(name) + self._s(ui_rules.WISHLIST_TAG_GAP)
            self._tag(painter, x, top + name_h / 2, LOWEST_TAG, filled=False)
        y = top + name_h + gap
        painter.setFont(line_font)
        for text, colour in lines:
            painter.setPen(QColor(colour))
            shown = QFontMetrics(line_font).elidedText(text, Qt.TextElideMode.ElideRight, max(0, round(words_right - left)))
            painter.drawText(QRectF(left, y, max(0.0, words_right - left), line_h),
                             int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), shown)
            y += line_h + gap

        # The right-hand words: today's price, with the one before struck through and the discount.
        price_font = self._font(ui_rules.WISHLIST_PRICE_PX, ui_rules.HEADING_WEIGHT)
        price_h = QFontMetrics(price_font).height()
        # A target's words take the place of the count of prices (Phase 101): the row keeps its height.
        series = [text for text in (row.lowest, row.target or row.prices) if text]
        top = rect.center().y() - (price_h + len(series) * (line_h + gap)) / 2
        painter.setFont(price_font)
        painter.setPen(QColor(ui_rules.COLOR_TEXT))
        price_w = QFontMetrics(price_font).horizontalAdvance(row.price)
        painter.drawText(QRectF(right - column, top, column, price_h),
                         int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), row.price)
        x = right - price_w
        if row.discount:
            width = QFontMetrics(self._font(ui_rules.WISHLIST_TAG_PX, ui_rules.LABEL_WEIGHT)).horizontalAdvance(
                row.discount) + self._s(ui_rules.WISHLIST_TAG_PADDING_X) * 2
            x -= self._s(ui_rules.WISHLIST_TAG_GAP) + width
            self._tag(painter, x, top + price_h / 2, row.discount, filled=True)
        if row.was:
            was_font = self._font(ui_rules.WISHLIST_LINE_PX, strike=True)
            painter.setFont(was_font)
            painter.setPen(QColor(ui_rules.COLOR_WISHLIST_WAS))
            was_w = QFontMetrics(was_font).horizontalAdvance(row.was)
            x -= self._s(ui_rules.WISHLIST_TAG_GAP) + was_w
            painter.drawText(QRectF(x, top, was_w + 1, price_h),
                             int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), row.was)
        y = top + price_h + gap
        painter.setFont(line_font)
        painter.setPen(QColor(ui_rules.COLOR_WISHLIST_META))
        for text in series:
            shown = QFontMetrics(line_font).elidedText(text, Qt.TextElideMode.ElideLeft, column)
            painter.drawText(QRectF(right - column, y, column, line_h),
                             int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), shown)
            y += line_h + gap

    def _paint_series(self, painter, box: QRectF, cents: tuple) -> None:
        """The prices seen, oldest on the left, today's the dot on the right; lower is cheaper.
        A price that never moved is a flat line through the middle (Phase 89)."""
        low, high = min(cents), max(cents)
        dot = ui_rules.WISHLIST_SPARK_DOT * self.host.metrics.scale
        inner = box.adjusted(dot, dot, -dot, -dot)
        step = inner.width() / (len(cents) - 1)

        def point(i: int, value: int) -> QPointF:
            share = (value - low) / (high - low) if high > low else 0.5
            return QPointF(inner.left() + i * step, inner.bottom() - share * inner.height())

        line = QPainterPath(point(0, cents[0]))
        for i, value in enumerate(cents[1:], start=1):
            line.lineTo(point(i, value))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        pen = QPen(QColor(ui_rules.COLOR_WISHLIST_SPARK), max(1.0, ui_rules.WISHLIST_SPARK_PEN * self.host.metrics.scale))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.drawPath(line)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(ui_rules.COLOR_WISHLIST_SPARK))
        painter.drawEllipse(point(len(cents) - 1, cents[-1]), dot, dot)

    def _paint_art(self, painter, box: QRectF, appid: int) -> None:
        radius = self._s(ui_rules.WISHLIST_ART_RADIUS)
        clip = QPainterPath()
        clip.addRoundedRect(box, radius, radius)
        picture = self.host.cover(appid, round(box.width()), round(box.height()))
        if picture is None:
            painter.fillPath(clip, QColor(ui_rules.COLOR_WISHLIST_ART))
            return
        painter.save()
        painter.setClipPath(clip)
        painter.drawPixmap(box.toRect(), picture)
        painter.restore()


class WishlistPage(QWidget):
    """The page. B or Escape leaves, as from Stats; nothing on it writes anywhere but this PC's marks."""

    backRequested = Signal()
    tabSelected = Signal(str)
    storeRequested = Signal(int)  # open this game's store page
    menuRequested = Signal(int, object)  # appid, where (global)
    choiceChanged = Signal(str)  # the chip picked: wishlist.ALL or wishlist.ON_SALE

    def __init__(self, metrics, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("WishlistPage")
        self.metrics = metrics
        self.focus_ring_width = ui_rules.FOCUS_RING_WIDTH
        self.model: wishlist_module.Page | None = None
        self.choice = wishlist_module.ALL
        self.unfolded: set[str] = set()
        self.art_paths: dict[int, str] = {}
        self._covers: dict[tuple, QPixmap] = {}
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._build()

    def _build(self) -> None:
        self.header_row = ui_pageshell.PageHeader(ui_pageshell.TAB_WISHLIST, self)
        self.header_row.backRequested.connect(self.backRequested)
        self.header_row.tabSelected.connect(self.tabSelected)

        self.page_title = QLabel("Wishlist")
        self.page_title.setObjectName("PageTitle")
        self.page_title.setVisible(False)
        self.rail = False
        self.summary = QLabel()
        self.summary.setObjectName("Meta")
        self.summary.setWordWrap(True)

        self.chips: dict[str, Chip] = {}
        self._chip_group = QButtonGroup(self)
        self._chip_group.setExclusive(True)
        self.chip_row = QHBoxLayout()
        self.chip_row.setContentsMargins(0, 0, 0, 0)
        for name, label in CHOICES:
            chip = Chip(label)
            chip.setCheckable(True)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # the pad switches them with Y; the arrows stay on the list
            chip.clicked.connect(lambda _checked=False, n=name: self.choose(n, announce=True))
            self._chip_group.addButton(chip)
            self.chips[name] = chip
            self.chip_row.addWidget(chip)
        self.chip_row.addStretch(1)
        self.chips[self.choice].setChecked(True)

        self.empty_label = QLabel()
        self.empty_label.setObjectName("WishlistEmpty")
        self.empty_label.setWordWrap(True)
        self.empty_label.setVisible(False)

        self.list = QListWidget()
        self.list.setObjectName("WishlistList")
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.list.setItemDelegate(WishlistDelegate(self))
        self.list.setUniformItemSizes(False)  # two item shapes; see the Phase 2 trap
        # Activated is Enter and, on Windows, a double click -- so a double click opens the store page
        # once. A fold opens with a single click.
        self.list.itemActivated.connect(self._activate)
        self.list.itemClicked.connect(self._clicked)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._context_menu)

        self.footnote = QLabel()
        self.footnote.setObjectName("Meta")
        self.footnote.setWordWrap(True)

        body = QWidget()
        body.setObjectName("Clear")  # the library's glow shows through, as on every tab
        self.body_layout = QVBoxLayout(body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.addWidget(self.page_title)
        self.body_layout.addWidget(self.summary)
        self.body_layout.addLayout(self.chip_row)
        self.body_layout.addWidget(self.empty_label)
        self.body_layout.addWidget(self.list, 1)
        self.body_layout.addWidget(self.footnote)
        self.content = body
        self.column = ui_pageshell.PageColumn(body, ui_rules.WISHLIST_CONTENT_MAX_WIDTH)
        self.header_column = ui_pageshell.PageColumn(self.header_row, ui_rules.WISHLIST_CONTENT_MAX_WIDTH)
        layout = QVBoxLayout(self)
        layout.addWidget(self.header_column)
        layout.addWidget(self.column, 1)
        self.apply_metrics(self.metrics)

    # -- filling it in ----------------------------------------------------------------------

    def set_page(self, model: wishlist_module.Page | None, choice: str | None = None,
                 art_paths: dict[int, str] | None = None) -> None:
        """The page's rows (logic.wishlist.page), or None when the library cannot answer. The row the
        list was on stays chosen when it is still there."""
        self.model = model
        if choice in dict(CHOICES):
            self.choice = choice
            self.chips[choice].setChecked(True)
        if art_paths is not None:
            self.art_paths = dict(art_paths)
        self._fill()

    def _fill(self) -> None:
        keep = self.current_appid()
        self.list.clear()
        model = self.model
        if model is None:
            self._say(UNAVAILABLE)
            self.summary.setText("")
            self.footnote.setText("")
            for chip in self.chips.values():
                chip.setVisible(False)
            return
        shown = model.shown(self.choice)
        for chip in self.chips.values():
            chip.setVisible(not model.empty)
        self.chips[wishlist_module.ALL].set_count(len(model.rows))
        self.chips[wishlist_module.ON_SALE].set_count(model.on_sale)
        self.chips[wishlist_module.ALERTS].set_count(len(model.alerts))
        if model.empty:
            self._say(model.empty)
        elif not shown:
            self._say({wishlist_module.ON_SALE: wishlist_module.NOTHING_ON_SALE,
                       wishlist_module.ALERTS: wishlist_module.NO_ALERTS}.get(self.choice,
                                                                             wishlist_module.NOTHING_ON_LIST))
        else:
            self._say("")
        rows = len(model.rows)
        self.summary.setText("" if model.empty and not (model.removed or model.hidden) else (
            f"{rows} game{'s' if rows != 1 else ''} on your wishlist · {model.on_sale} on sale today"
            + (f" · {model.lowest_now} at {'its' if model.lowest_now == 1 else 'their'} lowest price seen"
               if model.lowest_now else "")  # Phase 87's daily notice, a line here since Phase 101
            + (f" · {len(model.hidden)} hidden" if model.hidden else "")))
        self.footnote.setText(model.footnote)
        for row in shown:
            self._add_game(row)
        groups = () if self.choice == wishlist_module.ALERTS else ((GROUP_REMOVED, model.removed),
                                                                   (GROUP_HIDDEN, model.hidden))
        for group, rows_in in groups:
            if not rows_in:
                continue
            item = QListWidgetItem()
            item.setData(KIND_ROLE, KIND_GROUP)
            item.setData(PAYLOAD_ROLE, (group, len(rows_in)))
            self.list.addItem(item)
            if group in self.unfolded:
                for row in rows_in:
                    self._add_game(row)
        self.list.setVisible(self.list.count() > 0)
        if keep is not None and self.select_appid(keep):
            return
        self.select_first()

    def _say(self, words: str) -> None:
        self.empty_label.setText(words)
        self.empty_label.setVisible(bool(words))

    def _add_game(self, row) -> None:
        item = QListWidgetItem()
        item.setData(KIND_ROLE, KIND_GAME)
        item.setData(PAYLOAD_ROLE, row)
        item.setData(Qt.ItemDataRole.AccessibleTextRole, row.name)
        self.list.addItem(item)

    def set_art(self, appid: int, path: str) -> None:
        """A cover that has just been fetched: kept, and its row painted again."""
        self.art_paths[appid] = path
        self._covers = {k: v for k, v in self._covers.items() if k[0] != appid}
        self.list.viewport().update()

    def cover(self, appid: int, width: int, height: int) -> QPixmap | None:
        """The game's cover cropped to fill its box, at the screen's density; None when there is none yet."""
        ratio = self.devicePixelRatioF() or 1.0
        key = (appid, width, height, ratio)
        if key in self._covers:
            return self._covers[key]
        path = self.art_paths.get(appid)
        picture = QPixmap(path) if path else QPixmap()
        if picture.isNull():
            return None
        size = QSize(round(width * ratio), round(height * ratio))
        scaled = picture.scaled(size, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                Qt.TransformationMode.SmoothTransformation)
        x, y = (scaled.width() - size.width()) // 2, (scaled.height() - size.height()) // 2
        cropped = scaled.copy(x, y, size.width(), size.height())
        cropped.setDevicePixelRatio(ratio)
        self._covers[key] = cropped
        return cropped

    def appids(self) -> list[int]:
        """Every game the model holds, shown or folded: the covers to fetch."""
        if self.model is None:
            return []
        return [row.appid for row in self.model.rows + self.model.removed + self.model.hidden]

    # -- choosing ---------------------------------------------------------------------------

    def choose(self, choice: str, announce: bool = False) -> None:
        if choice not in dict(CHOICES):
            return
        changed = choice != self.choice
        self.choice = choice
        self.chips[choice].setChecked(True)
        if changed:
            self._fill()
        if announce and changed:
            self.choiceChanged.emit(choice)

    def toggle_choice(self) -> None:
        """The pad's Y: the next chip -- All, On sale, Alerts, and round again."""
        names = [name for name, _label in CHOICES]
        self.choose(names[(names.index(self.choice) + 1) % len(names)], announce=True)

    def toggle_group(self, group: str) -> None:
        self.unfolded ^= {group}
        self._fill()
        self.select_group(group)

    # -- the list ---------------------------------------------------------------------------

    def _row_of(self, item) -> object | None:
        return item.data(PAYLOAD_ROLE) if item is not None and item.data(KIND_ROLE) == KIND_GAME else None

    def current_appid(self) -> int | None:
        row = self._row_of(self.list.currentItem())
        return row.appid if row is not None else None

    def _clicked(self, item) -> None:
        if item is not None and item.data(KIND_ROLE) == KIND_GROUP:
            self.toggle_group(item.data(PAYLOAD_ROLE)[0])

    def _activate(self, item) -> None:
        if item is None:
            return
        if item.data(KIND_ROLE) == KIND_GROUP:
            if QApplication.mouseButtons() == Qt.MouseButton.NoButton:  # a click already folded it
                self.toggle_group(item.data(PAYLOAD_ROLE)[0])
            return
        row = self._row_of(item)
        if row is not None:
            self.storeRequested.emit(row.appid)

    def activate_current(self) -> None:
        """The pad's A: the selected game's store page, or the selected fold opened or closed."""
        item = self.list.currentItem()
        if item is not None and item.data(KIND_ROLE) == KIND_GROUP:
            self.toggle_group(item.data(PAYLOAD_ROLE)[0])
        else:
            self._activate(item)

    def _context_menu(self, position) -> None:
        row = self._row_of(self.list.itemAt(position))
        if row is not None:
            self.menuRequested.emit(row.appid, self.list.viewport().mapToGlobal(position))

    def context_for_current(self) -> None:
        """The pad's X, on the selected game."""
        item = self.list.currentItem()
        row = self._row_of(item)
        if row is not None:
            rect = self.list.visualItemRect(item)
            self.menuRequested.emit(row.appid, self.list.viewport().mapToGlobal(rect.center()))

    def row_for(self, appid: int):
        model = self.model
        if model is None:
            return None
        return next((r for r in model.rows + model.removed + model.hidden if r.appid == appid), None)

    def move_focus(self, key: int) -> None:
        """A synthesised key press to the list, as the grid and Storage do (the Phase 17 rule)."""
        if self.list.currentItem() is None:
            self.select_first()
            return
        QApplication.sendEvent(self.list, QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier))

    def select_first(self) -> None:
        if self.list.count():
            auto = self.list.hasAutoScroll()
            self.list.setAutoScroll(False)  # Storage's Phase 62 lesson: the list's top shows
            self.list.setCurrentRow(0)
            self.list.setAutoScroll(auto)
            self.list.scrollToTop()

    def select_appid(self, appid: int) -> bool:
        for index in range(self.list.count()):
            row = self._row_of(self.list.item(index))
            if row is not None and row.appid == appid:
                self.list.setCurrentRow(index)
                return True
        return False

    def select_group(self, group: str) -> None:
        for index in range(self.list.count()):
            item = self.list.item(index)
            if item.data(KIND_ROLE) == KIND_GROUP and item.data(PAYLOAD_ROLE)[0] == group:
                self.list.setCurrentRow(index)
                return

    def ensure_focus(self) -> None:
        # Choose before focusing, as Storage does: taking the focus marks a row current without
        # selecting it, and the ring is drawn for the selected one.
        if self.list.currentItem() is None:
            self.select_first()
        if self.list.isVisible() or self.list.count():
            self.list.setFocus(Qt.FocusReason.OtherFocusReason)
        else:
            self.setFocus(Qt.FocusReason.OtherFocusReason)
        current = self.list.currentItem()
        if current is not None and not current.isSelected():
            current.setSelected(True)

    # -- chrome -----------------------------------------------------------------------------

    def apply_metrics(self, metrics) -> None:
        self.metrics = metrics
        s = metrics.scale
        top = ui_rules.RAIL_PAGE_TOP if getattr(self, "rail", False) else ui_rules.PAGE_COLUMN_TOP
        self.layout().setContentsMargins(0, max(6, round(top * s)), 0, max(10, round(ui_rules.STATS_PAGE_MARGIN * s)))
        self.layout().setSpacing(0)
        self.body_layout.setSpacing(max(6, round(ui_rules.STORAGE_SECTION_SPACING * s)))
        self.chip_row.setSpacing(max(4, round(ui_rules.WISHLIST_CHIPS_GAP * s)))
        for chip in self.chips.values():
            chip.scale = s
            chip.setFixedHeight(max(20, round(ui_rules.CHIP_HEIGHT * s)))
            chip.updateGeometry()
        cap = round(ui_rules.WISHLIST_CONTENT_MAX_WIDTH * s)
        self.content.setMaximumWidth(cap)
        self.header_row.setMaximumWidth(cap)
        for column in (self.column, self.header_column):
            column.set_scale(s)
        self._covers.clear()
        self.list.reset()  # the delegate reads the metrics off this page
        if self.model is not None:
            self._fill()

    def set_rail(self, rail: bool) -> None:
        """Beside the side rail or under the top bar (Phase 60): the column's place, the top."""
        self.rail = rail
        self.page_title.setVisible(rail)
        for column in (self.column, self.header_column):
            column.set_rail(rail)
        self.apply_metrics(self.metrics)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.backRequested.emit()
            return
        super().keyPressEvent(event)


def stylesheet(scale: float) -> str:
    """Appended to the app stylesheet; only affects this page."""
    s = lambda value: max(1, round(value * scale))  # noqa: E731
    return f"""
    QListWidget#WishlistList {{ background: transparent; border: none; }}
    QLabel#WishlistEmpty {{ color: {ui_rules.COLOR_TEXT_MUTED}; font-size: {s(ui_rules.STORAGE_NAME_PX)}px; }}
    """
