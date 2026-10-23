"""The library page: Continue playing, the chips, and the wall of covers.

Tiles are painted by a delegate rather than built as widgets, so the list view keeps doing
the reflow, scrolling and keyboard navigation it already does well while every tile still
gets a cropped cover, a name and a hover animation.

Note what is NOT used here: setUniformItemSizes. CLAUDE.md records why -- it copies the
first item's size hint onto every other item and clips longer names. Tiles are all the same
size because the delegate returns one size, which is a different thing.

Since Phase 32 the page is transparent: the window's backdrop (ui_backdrop) glows through
it in the colours of whichever game is in focus.
"""

from __future__ import annotations

import logging
import math

from PySide6.QtCore import (
    QEasingCurve,
    QElapsedTimer,
    QEvent,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QFontMetricsF,
    QKeyEvent,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListView,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStyledItemDelegate,
    QStylePainter,
    QVBoxLayout,
    QWidget,
)

from shared import humanize
from shared import rules
from presentation import ui_continue
from presentation import ui_rules
from presentation import ui_theme
from presentation.ui_continue import ContinueCard
from presentation import ui_jump
from presentation.ui_jump import JumpBackIn
from presentation.ui_rail import SideRail
from presentation.ui_cards import FocusRing
from presentation.ui_topbar import TAB_FORYOU, TAB_LIBRARY, TAB_REPORTS, TAB_STATS, TAB_STORAGE, TAB_WISHLIST, TopBar

log = logging.getLogger(__name__)

KEY_ROLE = Qt.ItemDataRole.UserRole
SORT_MODES = ("Name", "Last played", "Recently added")

# The chips above the grid (Phase 31). The status ones reuse the words the game page uses.
FILTER_ALL, FILTER_FAVORITES = "all", "favorites"
FILTERS = (
    (FILTER_ALL, "All games"),
    (FILTER_FAVORITES, "Favorites"),
    (rules.STATUS_PLAYING, ui_rules.STATUS_LABELS[rules.STATUS_PLAYING]),
    (rules.STATUS_FINISHED, ui_rules.STATUS_LABELS[rules.STATUS_FINISHED]),
    (rules.STATUS_DROPPED, ui_rules.STATUS_LABELS[rules.STATUS_DROPPED]),
)


def _passes(view, name: str) -> bool:
    if name == FILTER_FAVORITES:
        return view.favorite
    if name in rules.STATUSES:
        return view.status == name
    return True


def tile_subtitle(view, steam: dict | None = None, observed: bool = False, starting: bool = False) -> str:
    """The quieter line under a tile's name.

    Time played, for a game this launcher starts and times. For one that Steam, Epic or
    Xbox starts, the store's name instead: the time there is not known, which is different
    from zero, and "never played" under a game played for years would be a lie. Since
    Phase 76 a game Steam starts shows Steam's own hours on the accounts marked mine when
    they are known ("234 hours on Steam", `steam` the store's answer for it), and keeps the
    store's name otherwise -- no time counted, or no account of mine holding it. While a game is
    seen running, started outside the launcher, it says so (Phase 93, `observed`).
    """
    if starting:
        line = ui_rules.STARTING_TEXT  # Play pressed, the game not up yet (Phase 99)
    elif observed:
        line = "Running — timed by watching"
    elif view.entry.launch_kind == "exe":
        line = humanize.playtime(view.playtime_seconds)
    elif view.entry.source == "steam" and steam and (steam.get("minutes") or 0) > 0:
        line = f"{humanize.playtime(int(steam['minutes']) * 60)} on {ui_continue.source_label(view)}"
    else:
        line = ui_continue.source_label(view)
    return f"Hidden  ·  {line}" if view.hidden else line


ANIMATION_TICK_MS = 16
# A little longer than the fold itself, so the last relayout is caught too.
FOLD_SETTLE_MARGIN_MS = 80


class Chip(QPushButton):
    """A filter chip: its word, and its number after it, smaller and quieter (Phase 55).

    A button paints its words in one colour and one size, and the design's number is
    neither, so the box -- outline, hover, the accent when chosen -- comes from the
    stylesheet (QPushButton#Chip) and the words are painted here. text() is still
    "Word   12", which is what everything that reads a chip, tests included, parses.
    """

    def __init__(self, label: str, parent=None) -> None:
        super().__init__(label, parent)
        self.setObjectName("Chip")
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)  # its box is painted: a hover must repaint it
        self.label = label
        self.count = ""
        self.scale = 1.0

    def set_count(self, count: int) -> None:
        self.count = str(count)
        self.setText(f"{self.label}   {count}")
        self.updateGeometry()

    def _count_font(self) -> QFont:
        font = QFont(self.font())
        font.setPointSizeF(ui_theme.px_to_pt(ui_rules.CHIP_COUNT_PX * self.scale))
        return font

    def _parts(self) -> tuple[int, int, int]:
        """Widths of the word, the gap and the number, in this chip's fonts."""
        words = QFontMetrics(self.font()).horizontalAdvance(self.label)
        if not self.count:
            return words, 0, 0
        number = QFontMetrics(self._count_font()).horizontalAdvance(self.count)
        return words, round(ui_rules.CHIP_COUNT_GAP * self.scale), number

    def sizeHint(self) -> QSize:
        pad = max(6, round(ui_rules.CHIP_SIDE_PADDING * self.scale))
        return QSize(sum(self._parts()) + 2 * pad + 2, super().sizeHint().height())

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def paintEvent(self, event) -> None:
        painter = QStylePainter(self)
        paint_pill_box(painter, self)  # the box, painted round (Phase 99); the words follow
        words, gap, number = self._parts()
        x = (self.width() - (words + gap + number)) // 2
        painter.setFont(self.font())
        painter.setPen(QColor(ui_rules.COLOR_ACCENT_200 if self.isChecked() else ui_rules.COLOR_TEXT_SOFT))
        centred = int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        painter.drawText(QRect(x, 0, words + 1, self.height()), centred, self.label)
        if self.count:
            painter.setFont(self._count_font())
            painter.setPen(QColor(ui_rules.COLOR_TEXT_MUTED))
            painter.drawText(QRect(x + words + gap, 0, number + 1, self.height()), centred, self.count)


def paint_pill_box(painter, button) -> None:
    """A chip's or a switch's box above the grid (Phase 99): the divider's outline, the accent's when chosen and
    filled with its darkest step; the quiet hover and press on top -- as the stylesheet had them, painted round."""
    chosen = button.isCheckable() and button.isChecked()
    fill = ui_rules.COLOR_CHIP_CHOSEN if chosen else None
    if button.isDown():
        fill = ui_theme.layered(fill or "rgba(0, 0, 0, 0)", ui_rules.COLOR_SECONDARY_PRESSED)
    elif button.underMouse():
        fill = ui_theme.layered(fill or "rgba(0, 0, 0, 0)",
                                ui_rules.COLOR_PRIMARY_HOVER if chosen else ui_rules.COLOR_SECONDARY_HOVER)
    ui_theme.paint_capsule(painter, button.rect(), fill, ui_rules.COLOR_ACCENT if chosen else ui_rules.COLOR_PILL_EDGE,
                           ui_theme.pill_edge(getattr(button, "scale", 1.0)))


class PillToggle(QPushButton):
    """"Demos & tools", "Hidden": a switch shaped as a chip, its box painted round (Phase 99)."""

    def __init__(self, text: str, parent=None) -> None:
        super().__init__(text, parent)
        self.setObjectName("ToggleChip")
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.scale = 1.0

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        paint_pill_box(painter, self)
        painter.end()
        super().paintEvent(event)  # the words, on the stylesheet's transparent box


class SortBox(QComboBox):
    """The sort, drawn as a chip with the design's thin caret after its words (Phase 55).

    Qt's own arrow is hidden by the stylesheet (the "caret" property) and this one drawn
    in its place in the muted colour -- two strokes, so no icon font is needed for it.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("SortBox")
        self.setProperty("caret", "painted")
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.scale = 1.0

    def paintEvent(self, event) -> None:
        if self.property("variant") != "plain":  # beside the rail it is words alone (Phase 60)
            box = QPainter(self)
            ui_theme.paint_capsule(box, self.rect(), ui_rules.COLOR_SECONDARY_HOVER if self.underMouse() else None,
                                   ui_rules.COLOR_PILL_EDGE, ui_theme.pill_edge(self.scale))
            box.end()
        super().paintEvent(event)
        size = ui_rules.SORT_CARET_PX * self.scale
        room = (ui_rules.SORT_CARET_PX + 12) * self.scale  # the drop-down's width in the stylesheet
        cx, cy = self.width() - room / 2, self.height() / 2
        caret = QPainterPath()
        caret.moveTo(cx - size * 0.33, cy - size * 0.17)
        caret.lineTo(cx, cy + size * 0.17)
        caret.lineTo(cx + size * 0.33, cy - size * 0.17)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(QColor(ui_rules.COLOR_TEXT_MUTED), max(1.0, 1.3 * self.scale))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.drawPath(caret)


GENRE_ROLE = Qt.ItemDataRole.UserRole + 1  # a genre entry's name, as the filter reads it
COUNT_ROLE = Qt.ItemDataRole.UserRole + 2  # and how many games it holds


class GenreCountDelegate(QStyledItemDelegate):
    """An entry of the genre list: its name, and its number after it at the right, quieter (Phase 99)."""

    def paint(self, painter, option, index) -> None:
        count = index.data(COUNT_ROLE)
        if count is None:
            super().paint(painter, option, index)
            return
        super().paint(painter, option, index)
        painter.save()
        painter.setPen(QColor(ui_rules.COLOR_TEXT_MUTED))
        box = option.rect.adjusted(0, 0, -round(10 * getattr(self.parent(), "scale", 1.0)), 0)
        painter.drawText(box, int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), str(count))
        painter.restore()

    def sizeHint(self, option, index) -> QSize:
        size = super().sizeHint(option, index)
        return QSize(size.width() + round(48 * getattr(self.parent(), "scale", 1.0)), size.height())


class GenrePill(SortBox):
    """"All genres", beside the sort (Phase 99): the genres present in the library with how many games each
    holds, and "No genre known" -- picking one narrows the grid together with the chips and the search."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("SortBox")  # the sort pill's look, painted round
        self.setItemDelegate(GenreCountDelegate(self))
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        # The pick -- the user's, or one remembered from an earlier session -- kept apart from what the list holds
        # now: at a start it is put back before the genres are read, and must not be lost to an empty list.
        self._wanted = ui_rules.GENRE_ALL
        self._names: set[str] = set()
        self._unknown = 0
        self.set_entries([], 0, 0)

    def chosen(self) -> str:
        """The genre the grid shows: the pick while the library holds it, all of them otherwise."""
        if self._wanted == ui_rules.GENRE_NONE:
            return ui_rules.GENRE_NONE if self._unknown else ui_rules.GENRE_ALL
        return self._wanted if self._wanted in self._names else ui_rules.GENRE_ALL

    def set_entries(self, counts: list[tuple[str, int]], unknown: int, total: int) -> None:
        """The list as the library is now, the pick shown when it is there -- quietly, no signal."""
        self._names = {name for name, _n in counts}
        self._unknown = unknown
        entries = [(ui_rules.GENRE_ALL, total)] + list(counts) + ([(ui_rules.GENRE_NONE, unknown)] if unknown else [])
        chosen = self.chosen()
        self.blockSignals(True)
        self.clear()
        for name, count in entries:
            self.addItem(name)
            self.setItemData(self.count() - 1, name, GENRE_ROLE)
            self.setItemData(self.count() - 1, count, COUNT_ROLE)
        self.setCurrentIndex(next((i for i, (name, _n) in enumerate(entries) if name == chosen), 0))
        self.setMaxVisibleItems(max(1, len(entries)))  # the whole list, never a scroll bar
        self.blockSignals(False)

    def choose(self, name: str) -> None:
        self._wanted = name


class CoverDelegate(QStyledItemDelegate):
    """Draws one tile: the cover with a hairline, its marks, then the name and a line --
    and, lifted, a shadow, the accent's glow and its ring (flat at rest since Phase 55).

    The host is the library page: it provides `metrics`, `covers`, `focus_ring_width`,
    `flying_key`, `view_for(key)`, `note_cover(row, rect)`, and three progress values per
    row, each already eased and between 0 and 1 -- `hover_progress`, `focus_progress` and
    `appear_progress` (Phase 34). Every movement a tile makes is one of those three running
    from 0 to 1, so a tile under the mouse, a tile the pad has just reached and a tile
    arriving in the grid all move the same way, and "Reduce animations" is simply each of
    them jumping straight to its end.

    The focused tile's glow reaches past its own cell. Qt repaints only the two cells
    involved when the selection moves, which would leave glow behind, so the page repaints
    the whole view on every selection change instead.
    """

    def __init__(self, host) -> None:
        super().__init__(host)
        self.host = host

    def sizeHint(self, option, index) -> QSize:
        metrics = self.host.metrics
        return QSize(metrics.tile_width, metrics.tile_height)

    @staticmethod
    def cover_geometry(cell: QRect, metrics, hover: float, focus: float,
                       appear: float = 1.0) -> QRect:
        """Where a tile's cover is drawn: grown and lifted by hover or focus, and lower while
        it is still arriving. One place for the arithmetic, so the cover flight (ui_motion)
        takes off from, and lands on, exactly the rectangle the tile paints."""
        grow = max(1.0 + (ui_rules.HOVER_SCALE - 1.0) * hover,
                   1.0 + (ui_rules.FOCUS_SCALE - 1.0) * focus)
        raised = max(hover, focus)
        base_w, base_h = metrics.cover_width, metrics.cover_height
        width, height = round(base_w * grow), round(base_h * grow)
        lift = round(ui_rules.TILE_LIFT * metrics.scale * raised)
        drop = round(ui_rules.TILE_ENTRANCE_RISE * metrics.scale * (1.0 - appear))
        return QRect(
            cell.x() + (cell.width() - width) // 2,
            cell.y() + metrics.tile_padding + (base_h - height) // 2 - lift + drop,
            width,
            height,
        )

    def paint(self, painter: QPainter, option, index) -> None:
        view = self.host.view_for(index.data(KEY_ROLE))
        if view is None:
            return

        metrics = self.host.metrics
        scale = metrics.scale
        row = index.row()
        hover = self.host.hover_progress(row)
        # The focused tile grows, rises, rings and glows even without the mouse, so a
        # controller user can see where they are from across the room -- and since
        # Phase 34 it does so over FOCUS_DURATION_MS rather than in one jump.
        focus = self.host.focus_progress(row)
        appear = self.host.appear_progress(row)
        if appear <= 0.0:
            # Not arrived yet, so nothing is drawn -- but its cover is loaded now, in the
            # paint before the wave starts, so the wave never stops for a disk read.
            self.host.covers.cover(view, self.host.metrics.cover_width,
                                   self.host.metrics.cover_height)
            return
        cell = option.rect
        cover_rect = self.cover_geometry(cell, metrics, hover, focus, appear)
        self.host.note_cover(row, cover_rect)
        drop = round(ui_rules.TILE_ENTRANCE_RISE * scale * (1.0 - appear))

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.setOpacity(appear)
        radius = metrics.corner_radius
        base_w, base_h = metrics.cover_width, metrics.cover_height

        # The cover of a game whose cover is in flight is left out: the flight draws it.
        if view.key != self.host.flying_key:
            # Flat at rest, as the design draws a tile. Under the mouse or the pad it lifts,
            # and only then casts a shadow -- falling further as it rises, which is what
            # makes it read as lifted -- and takes the design's glow: 24 px of the accent.
            raised = max(hover, focus)
            if raised > 0.0:
                lift = round(ui_rules.TILE_LIFT * scale * raised)
                spread = max(2, round(ui_rules.TILE_SHADOW_SPREAD * scale))
                fall = round(ui_rules.TILE_SHADOW_DY * scale) + lift
                shadow = ui_theme.soft_edge(base_w, base_h, radius, spread, "#000000",
                                            ui_rules.TILE_SHADOW_ALPHA)
                reach = max(2, round(ui_rules.TILE_GLOW_PX * scale))
                glow = ui_theme.soft_edge(base_w, base_h, radius, reach, ui_rules.COLOR_ACCENT,
                                          ui_rules.TILE_GLOW_ALPHA)
                painter.setOpacity(appear * raised)
                painter.drawPixmap(cover_rect.adjusted(-spread, fall - spread, spread, fall + spread),
                                   shadow)
                painter.drawPixmap(cover_rect.adjusted(-reach, -reach, reach, reach), glow)
                painter.setOpacity(appear)

            path = QPainterPath()
            path.addRoundedRect(QRectF(cover_rect), radius, radius)
            painter.save()
            painter.setClipPath(path)
            pixmap = self.host.covers.cover(view, base_w, base_h)
            if not pixmap.isNull():
                painter.drawPixmap(cover_rect, pixmap)
            else:
                painter.fillRect(cover_rect, QColor(ui_rules.COLOR_SURFACE))
            if view.hidden:
                veil = QColor(ui_rules.COLOR_BACKGROUND)
                veil.setAlpha(ui_rules.TILE_HIDDEN_ALPHA)
                painter.fillRect(cover_rect, veil)
            painter.restore()

            # Outside the cover, as the design's rings are: a 1 px hairline, and the
            # accent ring over it as the tile lifts. The gaps between tiles hold them.
            self._outline(painter, cover_rect, radius, QColor(ui_rules.COLOR_BORDER), 1)
            if raised > 0.0:
                ring = QColor(ui_rules.TILE_FOCUS_COLOR)
                ring.setAlphaF(raised)
                self._outline(painter, cover_rect, radius, ring,
                              max(1, round(self.host.focus_ring_width * scale)))

            if view.favorite:
                paint_star_badge(painter, cover_rect)
            if view.is_new:
                paint_new_badge(painter, cover_rect)
            if view.status:
                paint_status_badge(painter, cover_rect, view.status)

        self._paint_name(painter, view, cell, metrics, drop)
        painter.restore()

    @staticmethod
    def _outline(painter: QPainter, rect: QRect, radius: float, colour: QColor, width: int) -> None:
        """A line drawn just outside a rounded rectangle, its inner edge on the rectangle's."""
        half = width / 2
        painter.setPen(QPen(colour, width))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(QRectF(rect).adjusted(-half, -half, half, half),
                                radius + half, radius + half)

    def _paint_name(self, painter: QPainter, view, cell: QRect, metrics, drop: int = 0) -> None:
        """The name on one line, and a quieter line under it, both left-aligned to the art.

        `drop` moves them down with the cover while a tile is still arriving. Each line sits
        in a box 1.55 times its type's size, as the design's text does.
        """
        s = metrics.scale
        left = cell.x() + (cell.width() - metrics.cover_width) // 2
        width = metrics.cover_width
        top = (cell.y() + metrics.tile_padding + metrics.cover_height
               + round(ui_rules.TILE_NAME_GAP * s) + drop)
        name_h = round(ui_rules.TILE_NAME_PX * ui_rules.TILE_LINE_HEIGHT * s)
        sub_h = round(ui_rules.TILE_SUB_PX * ui_rules.TILE_LINE_HEIGHT * s)

        name_font = QFont(painter.font())
        name_font.setPointSizeF(ui_theme.px_to_pt(ui_rules.TILE_NAME_PX * s))
        name_font.setWeight(getattr(QFont.Weight, ui_rules.TILE_NAME_WEIGHT))
        name_metrics = QFontMetrics(name_font)
        painter.setFont(name_font)
        painter.setPen(QColor(ui_rules.COLOR_TEXT if not view.hidden else ui_rules.COLOR_TEXT_MUTED))
        painter.drawText(
            QRect(left, top, width, name_h),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            name_metrics.elidedText(view.display_name, Qt.TextElideMode.ElideRight, width),
        )

        sub_font = QFont(name_font)
        sub_font.setPointSizeF(ui_theme.px_to_pt(ui_rules.TILE_SUB_PX * s))
        sub_font.setWeight(QFont.Weight(ui_rules.BODY_WEIGHT))
        sub_metrics = QFontMetrics(sub_font)
        painter.setFont(sub_font)
        painter.setPen(QColor(ui_rules.COLOR_TEXT_MUTED))
        painter.drawText(
            QRect(left, top + name_h + round(ui_rules.TILE_SUB_GAP * s), width, sub_h),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            sub_metrics.elidedText(tile_subtitle(view, getattr(self.host, "steam_times", {}).get(view.key),
                                                 getattr(self.host, "is_observed", lambda _key: False)(view.key),
                                                 getattr(self.host, "is_starting", lambda _key: False)(view.key)),
                                   Qt.TextElideMode.ElideRight, width),
        )


def star_path(centre_x: float, centre_y: float, radius: float) -> QPainterPath:
    """A five-pointed star, points up, drawn from ten alternating radii."""
    path = QPainterPath()
    for step in range(10):
        angle = math.pi / 2 + step * math.pi / 5  # start at the top, then every 36 degrees
        length = radius if step % 2 == 0 else radius * 0.42
        x = centre_x + math.cos(angle) * length
        y = centre_y - math.sin(angle) * length
        path.lineTo(x, y) if step else path.moveTo(x, y)
    path.closeSubpath()
    return path


def paint_star_badge(painter: QPainter, cover: QRect) -> None:
    """Mark a favorite, in the top-right corner of the artwork.

    On a dark disc, because a plain star disappears into pale cover art -- Battlefield 6's
    orange and PowerWash Simulator's sky both swallow it whole without one.
    """
    size = cover.width() * ui_rules.FAVORITE_BADGE_FRACTION
    margin = cover.width() * ui_rules.FAVORITE_BADGE_MARGIN_FRACTION
    centre_x = cover.right() - margin - size / 2
    centre_y = cover.top() + margin + size / 2

    backdrop = QColor(ui_rules.FAVORITE_BADGE_BACKDROP)
    backdrop.setAlpha(ui_rules.FAVORITE_BADGE_BACKDROP_ALPHA)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(backdrop)
    painter.drawEllipse(QRectF(centre_x - size / 2, centre_y - size / 2, size, size))

    painter.setBrush(QColor(ui_rules.FAVORITE_BADGE_COLOR))
    painter.drawPath(star_path(centre_x, centre_y, size * ui_rules.FAVORITE_STAR_FRACTION))


def paint_new_badge(painter: QPainter, cover: QRect) -> None:
    """Mark a game the launcher has only just found, in the top-left corner of the artwork.

    Sized from the cover's width, like the star opposite it, so the same proportions hold
    on the grid at any interface size and on a television -- every size is the design's
    pixels over its 137 px cover (Phase 55): a tag rather than a pill, a 1 px edge.
    """
    cover_w = cover.width()
    margin = cover_w * ui_rules.NEW_BADGE_MARGIN_FRACTION
    font_px = cover_w * ui_rules.NEW_BADGE_FONT_FRACTION

    painter.save()  # the font change must not leak into the name drawn after this
    font = QFont(painter.font())
    font.setWeight(QFont.Weight(ui_rules.LABEL_WEIGHT))
    font.setPointSizeF(ui_theme.px_to_pt(font_px))
    font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, font_px * ui_rules.NEW_BADGE_TRACKING)
    painter.setFont(font)
    width = (QFontMetricsF(font).horizontalAdvance(ui_rules.NEW_BADGE_TEXT)
             + 2 * cover_w * ui_rules.NEW_BADGE_PAD_H_FRACTION)
    height = font_px * ui_rules.TILE_LINE_HEIGHT + 2 * cover_w * ui_rules.NEW_BADGE_PAD_V_FRACTION
    tag = QRectF(cover.left() + margin, cover.top() + margin, width, height)
    radius = cover_w * ui_rules.NEW_BADGE_RADIUS_FRACTION

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(ui_rules.NEW_BADGE_COLOR))
    painter.drawRoundedRect(tag, radius, radius)
    painter.setPen(QPen(QColor(ui_rules.NEW_BADGE_EDGE), 1))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(tag.adjusted(-0.5, -0.5, 0.5, 0.5), radius + 0.5, radius + 0.5)
    painter.setPen(QColor(ui_rules.NEW_BADGE_TEXT_COLOR))
    painter.drawText(tag, int(Qt.AlignmentFlag.AlignCenter), ui_rules.NEW_BADGE_TEXT)
    painter.restore()


def paint_status_badge(painter: QPainter, cover: QRect, status: str) -> None:
    """Mark where the user is with a game, in the bottom-right corner of the artwork.

    The star's dark disc, so it reads on any art. The glyph is a path, not a character:
    a triangle for playing, a tick for finished, a cross for dropped.
    """
    size = cover.width() * ui_rules.STATUS_BADGE_FRACTION
    margin = cover.width() * ui_rules.STATUS_BADGE_MARGIN_FRACTION
    cx = cover.right() - margin - size / 2
    cy = cover.bottom() - margin - size / 2
    r = size / 2

    painter.save()
    backdrop = QColor(ui_rules.FAVORITE_BADGE_BACKDROP)
    backdrop.setAlpha(ui_rules.FAVORITE_BADGE_BACKDROP_ALPHA)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(backdrop)
    painter.drawEllipse(QRectF(cx - r, cy - r, size, size))

    colour = QColor(ui_rules.STATUS_COLORS.get(status, ui_rules.COLOR_TEXT_MUTED))
    if status == rules.STATUS_PLAYING:
        path = QPainterPath()
        path.moveTo(cx - r * 0.30, cy - r * 0.45)
        path.lineTo(cx + r * 0.50, cy)
        path.lineTo(cx - r * 0.30, cy + r * 0.45)
        path.closeSubpath()
        painter.setBrush(colour)
        painter.drawPath(path)
    else:
        pen = QPen(colour, max(1.0, size * ui_rules.STATUS_GLYPH_STROKE_FRACTION))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        path = QPainterPath()
        if status == rules.STATUS_FINISHED:
            path.moveTo(cx - r * 0.45, cy + r * 0.02)
            path.lineTo(cx - r * 0.12, cy + r * 0.35)
            path.lineTo(cx + r * 0.48, cy - r * 0.32)
        else:
            path.moveTo(cx - r * 0.35, cy - r * 0.35)
            path.lineTo(cx + r * 0.35, cy + r * 0.35)
            path.moveTo(cx + r * 0.35, cy - r * 0.35)
            path.lineTo(cx - r * 0.35, cy + r * 0.35)
        painter.drawPath(path)
    painter.restore()


class GameListView(QListWidget):
    """Adds hover tracking and animated wheel scrolling to the plain list view."""

    hoverLeft = Signal()

    def __init__(self, page: "LibraryPage") -> None:
        super().__init__(page)
        self.page = page
        self.setMouseTracking(True)
        self.viewportEntered.connect(self.hoverLeft)

    def leaveEvent(self, event) -> None:
        self.hoverLeft.emit()
        super().leaveEvent(event)

    def wheelEvent(self, event) -> None:
        if self.page.reduce_animations:
            super().wheelEvent(event)
            return
        bar = self.verticalScrollBar()
        notches = event.angleDelta().y() / 120.0
        if not notches:
            super().wheelEvent(event)
            return
        target = bar.value() - round(notches * self.page.metrics.scroll_step)
        self.page.scroll_to(max(bar.minimum(), min(bar.maximum(), target)))
        event.accept()


class LibraryPage(QWidget):
    gameActivated = Signal(str)
    gameSelected = Signal(str)
    contextRequested = Signal(str, object)
    rescanRequested = Signal()
    surpriseRequested = Signal()
    settingsRequested = Signal()
    statsRequested = Signal()
    storageRequested = Signal()
    reportsRequested = Signal()  # Phase 84
    wishlistRequested = Signal()  # Phase 87
    foryouRequested = Signal()  # Phase 98
    libraryRequested = Signal()
    sortChanged = Signal(str)  # only when the user picks one; set_sort stays quiet
    genreChanged = Signal(str)  # Phase 99: only when the user picks one; set_genre stays quiet
    filterChanged = Signal(str)  # the same, for the chips
    playRequested = Signal(str)  # the Continue playing card's two buttons
    stopRequested = Signal(str)
    backdropChanged = Signal(str)  # whose art the window's backdrop should glow with
    foldersRequested = Signal()  # the empty library's button: Settings, on the Game folders row

    def __init__(self, covers, metrics, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("LibraryPage")
        self.covers = covers
        self.metrics = metrics
        self._reduce_animations = ui_rules.REDUCE_ANIMATIONS_DEFAULT
        self.focus_ring_width = ui_rules.FOCUS_RING_WIDTH
        # The top bar's layout or the side rail's (Phase 60); the window chooses.
        self.layout_mode = ui_rules.LAYOUT_TOP
        self.views: list = []
        self.by_key: dict = {}
        self.steam_times: dict = {}  # Steam's own hours by game, the window's (Phase 76)
        self.visible_keys: list[str] = []
        # Whether a game is up right now; the window points this at its tracker.
        self.is_running = lambda _key: False
        # And whether one is seen running, started outside the launcher (Phase 93).
        self.is_observed = lambda _key: False
        self.is_starting = lambda _key: False  # Phase 99: Play pressed, the game not up yet
        # True while the pad or keyboard is on the Continue playing card rather than a tile,
        # and the tile to go back to when it comes down again.
        self._on_card = False
        self._row_before_card = -1
        self._on_controls = False  # Phase 99: the pad on the row above the grid -- chips, switches, genre, sort
        self._control_at = 0
        self.genres: dict[str, tuple[str, ...]] = {}  # each game's genres, by key: the window's, once a reload
        self._fold_settling = False
        self._scroll_anchor = 0
        self._backdrop_key = ""
        self._backdrop_pending = ""
        self._backdrop_timer = QTimer(self)
        self._backdrop_timer.setSingleShot(True)
        self._backdrop_timer.setInterval(ui_rules.BACKDROP_HOVER_SETTLE_MS)
        self._backdrop_timer.timeout.connect(lambda: self._set_backdrop(self._backdrop_pending))

        self._progress: dict[int, float] = {}
        self._hover_row = -1
        self._ticker = QTimer(self)
        self._ticker.setInterval(ANIMATION_TICK_MS)
        self._ticker.timeout.connect(self._tick)
        self._scroll_anim = None

        # Phase 34: what else a tile animates, besides the hover above. Rows whose focus is
        # on its way in or out; the row that has it; whether a rebuild is putting the
        # selection back (settle, do not animate); the wave the tiles arrive in.
        self._focus: dict[int, float] = {}
        self._focused_row = -1
        self._restoring = False
        self._entrance = QElapsedTimer()
        self._entrance_on = False
        # The wave's clock starts on the first tick after it is asked for, which comes after
        # the first paint: at the window's first appearance that paint loads every cover
        # from disk and can take longer than the whole wave (found by rendering it).
        self._entrance_started = False
        # Steps are measured in time, not ticks: at the TV's 225% a frame can take longer
        # than a tick, and counting ticks would make every motion there run slow.
        self._clock = QElapsedTimer()
        self._hover_curve = QEasingCurve(ui_theme.easing(ui_rules.HOVER_EASING))
        self._focus_curve = QEasingCurve(ui_theme.easing(ui_rules.FOCUS_EASING))
        self._entrance_curve = QEasingCurve(ui_theme.easing(ui_rules.TILE_ENTRANCE_EASING))
        # For the cover flight: where each tile last drew its cover, the cover a tile was
        # just opened from, and a game whose cover is in the air (its tile leaves it out).
        self._painted: dict[int, QRect] = {}
        self._launch: QRect | None = None
        self.flying_key = ""

        self._build()

    @property
    def reduce_animations(self) -> bool:
        return self._reduce_animations

    @reduce_animations.setter
    def reduce_animations(self, value: bool) -> None:
        self._reduce_animations = value
        for card in (getattr(self, "continue_card", None), getattr(self, "jump", None)):
            if card is not None:
                card.reduce_animations = value

    # -- construction ---------------------------------------------------------------------

    def _build(self) -> None:
        # The top bar is the window's to place (above every page but a game's own), but its
        # controls are the library's, so they keep the names everything already used.
        self.top_bar = TopBar()
        self.top_bar.tabSelected.connect(self._tab_picked)
        self.filter_box = self.top_bar.search
        self.filter_box.textChanged.connect(self._searched)
        self.surprise_button = self.top_bar.surprise
        self.surprise_button.clicked.connect(self.surpriseRequested)
        self.rescan_button = self.top_bar.rescan
        self.rescan_button.clicked.connect(self.rescanRequested)
        self.settings_button = self.top_bar.settings
        self.settings_button.clicked.connect(self.settingsRequested)
        self.stats_button = self.top_bar.tabs[TAB_STATS]
        self.stats_button.setToolTip("Hours played, a year of months, and what is not counted.")
        self.storage_button = self.top_bar.tabs[TAB_STORAGE]
        self.storage_button.setToolTip("Where the disk went: every game by size, grouped by drive.")

        # The side rail (Phase 60): the same places, filters and buttons in a column, which
        # the window shows instead of the top bar at the desk. Its filters only mirror the
        # chips below, which stay the one place the choice is kept.
        self.rail = SideRail(FILTERS)
        self.rail.tabSelected.connect(self._tab_picked)
        self.rail.filterPicked.connect(self._rail_filter)
        self.rail.surpriseRequested.connect(self.surpriseRequested)
        self.rail.rescanRequested.connect(self.rescanRequested)
        self.rail.settingsRequested.connect(self.settingsRequested)
        # The window turns Rescan off while a scan runs; the rail's follows it.
        self.rescan_button.installEventFilter(self)

        # Beside the rail the page carries its own name and what it holds, and the search.
        self.header = QWidget()
        self.header.setObjectName("Clear")
        self.page_title = QLabel("Library")
        self.page_title.setObjectName("PageTitle")
        self.page_meta = QLabel()
        self.page_meta.setObjectName("PageMeta")
        header_row = QHBoxLayout(self.header)
        header_row.addWidget(self.page_title)
        header_row.addWidget(self.page_meta)
        header_row.addStretch(1)
        self.header.setVisible(False)

        # Filter chips: one of them is always on, and "All games" is where everything is.
        # Held in a widget of their own so the gap under them scales with everything else.
        self.chips: dict[str, QPushButton] = {}
        self._chip_group = QButtonGroup(self)
        self._chip_group.setExclusive(True)
        self.chips_bar = QWidget()
        self.chips_bar.setObjectName("ChipsBar")
        chips_row = QHBoxLayout(self.chips_bar)
        chips_row.setSpacing(ui_rules.CHIP_GAP)
        # Beside the rail the filters are the rail's, and this row says what follows.
        self.grid_label = QLabel("ALL GAMES")
        self.grid_label.setObjectName("SectionLabel")
        self.grid_label.setVisible(False)
        chips_row.addWidget(self.grid_label)
        for name, label in FILTERS:
            chip = Chip(label)
            chip.setCheckable(True)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.clicked.connect(lambda _checked=False, n=name: self._chip_picked(n))
            self._chip_group.addButton(chip)
            self.chips[name] = chip
            chips_row.addWidget(chip)
        self.chips[FILTER_ALL].setChecked(True)
        chips_row.addStretch(1)

        # Two switches that were tick-boxes in the old toolbar. Checkable buttons keep the
        # same isChecked/setChecked/toggled a tick-box had, so nothing that used them changes.
        self.extras_box = PillToggle("Demos && tools")
        self.extras_box.setCheckable(True)
        self.extras_box.setToolTip(
            "Show Steam entries classified as a demo, tool, soundtrack or similar."
        )
        self.extras_box.toggled.connect(self.refresh)
        self.extras_box.toggled.connect(lambda _on: self.play_entrance())
        self.hidden_box = PillToggle("Hidden")
        self.hidden_box.setCheckable(True)
        self.hidden_box.setToolTip("Show games you have hidden.")
        self.hidden_box.toggled.connect(self.refresh)
        self.hidden_box.toggled.connect(lambda _on: self.play_entrance())
        chips_row.addWidget(self.extras_box)
        chips_row.addWidget(self.hidden_box)
        # The design's 14 px before "Sort by", on top of the row's own gap.
        chips_row.addSpacing(ui_rules.SORT_LABEL_GAP)

        sort_label = QLabel("Sort by")
        sort_label.setObjectName("SortLabel")
        self.sort_label = sort_label
        self.sort_box = SortBox()
        self.sort_box.addItems(SORT_MODES)
        self.sort_box.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sort_box.currentIndexChanged.connect(self.refresh)
        self.sort_box.currentTextChanged.connect(self.sortChanged)
        # Only a sort the user picks: set_sort puts one back with its signals held.
        self.sort_box.currentTextChanged.connect(lambda _mode: self.play_entrance())
        # Phase 99: the genre pill, beside the sort -- no new row: the library stays as uncluttered as it was.
        self.genre_pill = GenrePill()
        self.genre_pill.setCursor(Qt.CursorShape.PointingHandCursor)
        self.genre_pill.activated.connect(self._genre_picked)  # a pick only: a refresh never fires it
        chips_row.addWidget(self.genre_pill)
        chips_row.addSpacing(ui_rules.SORT_LABEL_GAP)
        chips_row.addWidget(sort_label)
        chips_row.addWidget(self.sort_box)
        # One ring for the pad on that row (Phase 99), outside whichever control it is on.
        self.controls_ring = FocusRing(self, lambda widget: self._on_controls and widget in self._controls())

        self.list = GameListView(self)
        self.list.setObjectName("Grid")
        self.list.setViewMode(QListView.ViewMode.IconMode)
        self.list.setResizeMode(QListView.ResizeMode.Adjust)
        self.list.setMovement(QListView.Movement.Static)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.list.setSpacing(self.metrics.grid_spacing)
        self.delegate = CoverDelegate(self)
        self.list.setItemDelegate(self.delegate)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._context_menu)
        self.list.itemActivated.connect(self._activate)
        self.list.itemClicked.connect(self._activate)
        self.list.entered.connect(self._hover)
        self.list.hoverLeft.connect(lambda: self._hover(None))
        self.list.currentItemChanged.connect(self._selection_changed)
        self.list.pressed.connect(self._off_controls)  # a click on a tile takes the pad off the row above (Phase 99)
        self.list.verticalScrollBar().valueChanged.connect(self._fold_follow_scroll)

        # Continue playing (Phase 32), where the two shelves used to be -- and beside the
        # rail, Jump back in (Phase 60): three games where the card offers one. The page
        # speaks to whichever is in use through `card`; the two answer it alike.
        self.continue_card = ContinueCard(self.covers, self.metrics, self)
        self.jump = JumpBackIn(self.covers, self.metrics, self)
        for card in (self.continue_card, self.jump):
            card.reduce_animations = self._reduce_animations
            card.playRequested.connect(self.playRequested)
            card.stopRequested.connect(self.stopRequested)
            card.detailsRequested.connect(self.gameActivated)
            card.contextRequested.connect(self.contextRequested)

        self.count_label = QLabel()
        self.count_label.setObjectName("Meta")

        # The library with nothing in it says why (Phase 77): the window decides the words.
        self.empty = QFrame()
        self.empty.setObjectName("EmptyLibrary")
        self.empty_title = QLabel()
        self.empty_title.setObjectName("EmptyTitle")
        self.empty_text = QLabel()
        self.empty_text.setObjectName("EmptyText")
        self.empty_text.setWordWrap(True)
        self.empty_button = QPushButton()
        self.empty_button.setObjectName("EmptyButton")
        self.empty_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.empty_button.clicked.connect(self.foldersRequested)
        empty_layout = QVBoxLayout(self.empty)
        empty_layout.addStretch(2)
        for widget in (self.empty_title, self.empty_text, self.empty_button):
            empty_layout.addWidget(widget, 0, Qt.AlignmentFlag.AlignHCenter)
        empty_layout.addStretch(3)
        self.empty.hide()

        # No spacing in this layout: the card carries the gap beneath itself, so folding
        # it away leaves nothing behind to jump when it finally hides.
        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.addWidget(self.header)
        layout.addWidget(self.continue_card)
        layout.addWidget(self.jump)
        layout.addWidget(self.chips_bar)
        layout.addWidget(self.list, 1)
        layout.addWidget(self.empty, 1)
        layout.addWidget(self.count_label)
        self._apply_margins()
        self._size_controls()

    def _apply_margins(self) -> None:
        """The page's edges. The grid's first cover starts `grid_inset` into the list, so
        the list sits that much further out and the card, the chips and the count line
        come that much in: all four line up with the top bar, as in the design."""
        s = self.metrics.scale
        inset = self.metrics.grid_inset
        if self.layout_mode == ui_rules.LAYOUT_RAIL:
            # Beside the rail: 32 px in and 24 down, the design's #1b.
            side = round(ui_rules.RAIL_PAGE_SIDE * s) - inset
            top = round(ui_rules.RAIL_PAGE_TOP * s)
        else:
            side = round(ui_rules.TOPBAR_SIDE_MARGIN * s) - inset
            top = round(ui_rules.LIBRARY_TOP_GAP * s)
        self.layout().setContentsMargins(side, top, side, round(8 * s))
        self.header.layout().setContentsMargins(inset, 0, inset, round(ui_rules.RAIL_PAGE_GAP * s))
        self.header.layout().setSpacing(round(ui_rules.PAGE_HEADER_GAP * s))
        self.chips_bar.layout().setContentsMargins(inset, 0, inset, 0)
        self.count_label.setContentsMargins(inset, 0, inset, 0)

    @property
    def card(self):
        """Whichever offer of recent games is in use: the Continue card, or Jump back in."""
        return self.jump if self.layout_mode == ui_rules.LAYOUT_RAIL else self.continue_card

    def set_layout(self, mode: str) -> None:
        """The top bar's layout or the side rail's (Phase 60).

        Beside the rail the page shows its name and the search above Jump back in, and the
        chips' row becomes "All games" with the switches and the sort; the filters are
        the rail's. The chips themselves stay -- hidden -- as the one place the choice is
        kept, so everything that reads or remembers it is unchanged.
        """
        rail = mode == ui_rules.LAYOUT_RAIL
        leaving = self.card
        if self._on_card:
            self._on_card = False
            leaving.clear_focus()
        self.layout_mode = ui_rules.LAYOUT_RAIL if rail else ui_rules.LAYOUT_TOP
        if leaving is not self.card:
            leaving.set_present(False)
        self.header.setVisible(rail)
        self.grid_label.setVisible(rail)
        for chip in self.chips.values():
            chip.setVisible(not rail)
        for widget in (self.sort_box, self.sort_label, self.genre_pill):
            widget.setProperty("variant", "plain" if rail else "")
            widget.style().unpolish(widget)
            widget.style().polish(widget)
        # One search box: in the header beside the rail, in the top bar otherwise.
        if rail:
            self.header.layout().addWidget(self.filter_box)
        else:
            self.top_bar.restore_search()
        self._size_search()
        self._apply_margins()
        self.refresh()

    def _size_search(self) -> None:
        s = self.metrics.scale
        if self.layout_mode == ui_rules.LAYOUT_RAIL:
            self.filter_box.setFixedSize(max(80, round(ui_rules.RAIL_SEARCH_WIDTH * s)),
                                         max(20, round(ui_rules.RAIL_SEARCH_HEIGHT * s)))
        else:
            self.top_bar.apply_scale(s)

    def _rail_filter(self, name: str) -> None:
        """A filter picked on the rail: the chip it mirrors is chosen, as a click on it would.

        Picked while Stats or Storage is showing, it means "show me those games": go to them,
        as typing in the search does.
        """
        if not self.isVisible():
            self.libraryRequested.emit()
        chip = self.chips.get(name)
        if chip is not None and not chip.isChecked():
            chip.setChecked(True)
            self._chip_picked(name)

    def eventFilter(self, watched, event) -> bool:
        if watched is self.rescan_button and event.type() == QEvent.Type.EnabledChange:
            self.rail.rescan.setEnabled(self.rescan_button.isEnabled())
        return super().eventFilter(watched, event)

    def _fold_follow_scroll(self, value: int) -> None:
        """Fold the card away once the grid is scrolled, and bring it back at the top.

        Two thresholds, far apart. Folding hands the card's height to the grid, which
        shortens the grid's scrollbar and can drag the scroll value back down; with one
        threshold that lands on the other side of it and the card flickers. Folding late
        and restoring early leaves a gap far wider than any such correction.
        """
        if self._fold_settling:
            # A folding card hands its height to the grid, and QListView resets its scroll
            # position whenever it re-lays out -- which threw the view back to the top
            # halfway through the fold, and that in turn brought the card back. Putting
            # the position straight back on every frame means it is never drawn.
            self._hold_scroll_anchor()
            return

        if value >= round(ui_rules.CONTINUE_FOLD_AT * self.metrics.scale):
            collapsed = True
        elif value <= round(ui_rules.CONTINUE_RESTORE_AT * self.metrics.scale):
            collapsed = False
        else:
            return  # inside the gap: leave things as they are
        if self.card.collapsed == collapsed:
            return
        if not self.card.present:
            # Nothing on screen to fold, so nothing to hold the scroll still for.
            self.card.set_collapsed(collapsed, animate=False)
            return

        self._fold_settling = True
        self._scroll_anchor = value
        self.card.set_collapsed(collapsed)
        QTimer.singleShot(ui_rules.CONTINUE_FOLD_MS + FOLD_SETTLE_MARGIN_MS, self._settled)

    def _hold_scroll_anchor(self) -> None:
        bar = self.list.verticalScrollBar()
        wanted = min(self._scroll_anchor, bar.maximum())
        if bar.value() != wanted:
            bar.setValue(wanted)

    def _settled(self) -> None:
        self._hold_scroll_anchor()
        self._fold_settling = False
        # The grid can be rebuilt or rescaled while a fold is running -- a rescan finishing,
        # or TV mode being switched on -- and those changes were ignored while settling.
        # Decide again from where the grid actually ended up.
        self._fold_follow_scroll(self.list.verticalScrollBar().value())

    # -- data -----------------------------------------------------------------------------

    def set_views(self, views: list) -> None:
        self.views = views
        self.by_key = {v.key: v for v in views}
        self.refresh()

    def view_for(self, key):
        return self.by_key.get(key)

    def set_empty(self, message: tuple[str, str, str] | None) -> None:
        """Say why the library is empty -- (title, line, button words; none for no button) --
        or, with None, show the grid again (Phase 77)."""
        showing = message is not None
        if showing:
            title, line, button = message
            self.empty_title.setText(title)
            self.empty_text.setText(line)
            # A wrapped line has no width of its own to insist on, and a centred one is never
            # asked its height for that width: both were cut short (found by rendering). It
            # gets the column's width, and the height its words need at that width.
            width = round(ui_rules.EMPTY_TEXT_WIDTH * self.metrics.scale)
            self.empty_text.setFixedWidth(width)
            self.empty_text.ensurePolished()
            self.empty_text.setFixedHeight(self.empty_text.heightForWidth(width))
            self.empty_button.setText(button)
            self.empty_button.setVisible(bool(button))
        self.empty.setVisible(showing)
        self.list.setVisible(not showing)
        self.count_label.setVisible(not showing)

    def refresh(self) -> None:
        needle = self.filter_box.text().strip().casefold()
        show_hidden = self.hidden_box.isChecked()
        show_extras = self.extras_box.isChecked()

        # The chips count what the two switches allow, before the search narrows it, so a
        # chip's number is what you get by clicking it.
        base = [
            v
            for v in self.views
            if (show_hidden or not v.hidden) and (show_extras or not v.is_non_game)
        ]
        self._fill_genres(base)
        counts = {}
        for name, chip in self.chips.items():
            # Chosen, a chip keeps its weight since Phase 55 (the accent marks it), so it
            # needs no room for bold -- Chip sizes itself for its word and number.
            counts[name] = sum(1 for v in base if _passes(v, name))
            chip.set_count(counts[name])
        self.top_bar.set_count(len(base))

        chosen = self.current_filter()
        # The rail mirrors the chips, and says where the games came from (Phase 60).
        self.rail.set_counts(counts)
        self.rail.set_filter(chosen)
        found: dict[str, int] = {}
        for view in base:
            label = ui_rules.RAIL_SOURCE_LABELS.get(view.entry.source) or ui_continue.source_label(view)
            found[label] = found.get(label, 0) + 1
        self.rail.set_sources(sorted(found.items(), key=lambda pair: (-pair[1], pair[0])))
        places = len(found)
        self.page_meta.setText(f"{len(base)} games · {places} "
                               f"{'stores and folders' if places != 1 else 'store or folder'}")
        visible = [
            v for v in base
            if _passes(v, chosen) and (not needle or needle in v.display_name.casefold())
            and self._genre_passes(v)
        ]
        visible = self._sorted(visible)

        current = self.current_key()
        self._progress.clear()
        self._hover_row = -1
        self._painted.clear()
        # A rebuild -- the background one every minute while a game runs included -- puts
        # the selection back without animating it, or the focused tile would drop and rise
        # again each time.
        self._restoring = True
        self.list.clear()
        for view in visible:
            item = QListWidgetItem()
            item.setData(KEY_ROLE, view.key)
            item.setSizeHint(QSize(self.metrics.tile_width, self.metrics.tile_height))
            item.setToolTip(_tooltip(view))
            self.list.addItem(item)

        self.visible_keys = [v.key for v in visible]
        if current in self.visible_keys:
            self.list.setCurrentRow(self.visible_keys.index(current))
        self._restoring = False

        notes = []
        hidden_count = sum(1 for v in self.views if v.hidden)
        if hidden_count and not show_hidden:
            notes.append(f"{hidden_count} hidden")
        extras = sum(1 for v in self.views if v.is_non_game and not v.hidden)
        if extras and not show_extras:
            notes.append(f"{extras} demo/tool")
        suffix = f"   ({', '.join(notes)} not shown)" if notes else ""
        genre = self.genre_pill.chosen()
        shown = f" · {genre}" if genre != ui_rules.GENRE_ALL else ""  # what the genre pill is showing (Phase 99)
        self.count_label.setText(f"{len(visible)} of {len(self.views)} games{shown}{suffix}")
        self._refresh_continue(searching=bool(needle))
        if self._backdrop_key not in self.by_key:
            self._set_backdrop(self._default_backdrop())

    def _refresh_continue(self, searching: bool) -> None:
        """Offer the game to continue, or take the card away.

        It belongs to the whole library, so a search or any chip but All games takes it
        off the page: those mean the grid is what is wanted, and the card would only push
        the results down.
        """
        wanted = not searching and self.current_filter() == FILTER_ALL
        if self.layout_mode == ui_rules.LAYOUT_RAIL:
            games = ui_jump.recent(self.views)
            self.jump.set_games(games)
            self.jump.set_running(self.is_running)
            self.jump.set_present(bool(games) and wanted)
        else:
            view = ui_continue.pick(self.views)
            self.continue_card.set_game(view)
            self.continue_card.set_running(view is not None and self.is_running(view.key))
            self.continue_card.set_present(view is not None and wanted)
        # Re-read the fold from where the grid actually is. Rebuilding the list, or
        # changing scale for TV mode, resets the scroll without necessarily emitting
        # valueChanged -- and a card folded before that would otherwise stay folded at
        # the top of the list with no way back.
        self._fold_follow_scroll(self.list.verticalScrollBar().value())
        if self._on_card and not self.card.shown:
            self._on_card = False
            self.card.clear_focus()

    def update_running(self) -> None:
        """Play becomes Stop on the card while its game is up; a tile seen running says so."""
        self.list.viewport().update()  # the tiles' second line (Phase 93: "Running — timed by watching")
        if self.layout_mode == ui_rules.LAYOUT_RAIL:
            self.jump.set_running(self.is_running)
            self.jump.set_starting(self.is_starting)
            return
        view = self.continue_card.view
        self.continue_card.set_running(view is not None and self.is_running(view.key))
        self.continue_card.set_starting(view is not None and self.is_starting(view.key))

    # -- the backdrop -----------------------------------------------------------------------

    def backdrop_key(self) -> str:
        """Whose art the window's backdrop should show while this page is up."""
        return self._backdrop_key if self._backdrop_key in self.by_key else self._default_backdrop()

    def _default_backdrop(self) -> str:
        """Before anything has been pointed at: the card's game, the selection, the first."""
        if self.card.view is not None and self.card.present:
            return self.card.view.key
        return self.current_key() or (self.visible_keys[0] if self.visible_keys else "")

    def _want_backdrop(self, key: str, settle: bool = False) -> None:
        """Follow the pad and the keyboard at once; the mouse only once it has rested."""
        self._backdrop_timer.stop()
        if settle:
            self._backdrop_pending = key
            self._backdrop_timer.start()
        else:
            self._set_backdrop(key)

    def _set_backdrop(self, key: str) -> None:
        if key and key != self._backdrop_key:
            self._backdrop_key = key
            self.backdropChanged.emit(key)

    def _size_controls(self) -> None:
        """Every chip, switch and the sort box one height, at the current scale."""
        height = max(20, round(ui_rules.CHIP_HEIGHT * self.metrics.scale))
        for control in (*self.chips.values(), self.extras_box, self.hidden_box, self.genre_pill, self.sort_box):
            control.setFixedHeight(height)
            control.setProperty("ringRadius", height / 2)  # the pad's ring round the pill's own ends (Phase 99)
        for control in (*self.chips.values(), self.extras_box, self.hidden_box, self.genre_pill, self.sort_box):
            control.scale = self.metrics.scale
            control.updateGeometry()

    def current_filter(self) -> str:
        return next((name for name, chip in self.chips.items() if chip.isChecked()), FILTER_ALL)

    def set_filter(self, name: str) -> None:
        """Put back a chip chosen in an earlier session, quietly, like set_sort."""
        chip = self.chips.get(name)
        if chip is None or chip.isChecked():
            return
        chip.setChecked(True)
        self.refresh()

    def _chip_picked(self, name: str) -> None:
        self.refresh()
        self.filterChanged.emit(name)
        self.play_entrance()

    def _tab_picked(self, name: str) -> None:
        {TAB_LIBRARY: self.libraryRequested, TAB_STATS: self.statsRequested,
         TAB_STORAGE: self.storageRequested, TAB_REPORTS: self.reportsRequested,
         TAB_WISHLIST: self.wishlistRequested, TAB_FORYOU: self.foryouRequested}[name].emit()

    def _searched(self) -> None:
        # Typing a name while Stats or Storage is showing means "find this game": go to it.
        if not self.isVisible() and self.filter_box.text():
            self.libraryRequested.emit()
        self.refresh()

    # -- the genre pill (Phase 99) ----------------------------------------------------------------------------

    def _genre_passes(self, view) -> bool:
        chosen = self.genre_pill.chosen()
        if chosen == ui_rules.GENRE_ALL:
            return True
        found = self.genres.get(view.key, ())
        return not found if chosen == ui_rules.GENRE_NONE else chosen in found

    def _fill_genres(self, base) -> None:
        """The list from the games the switches allow, before the chips and the search narrow them -- so a genre's
        number is what you get by picking it from All games."""
        counts: dict[str, int] = {}
        unknown = 0
        for view in base:
            found = self.genres.get(view.key, ())
            if not found:
                unknown += 1
            for name in found:
                counts[name] = counts.get(name, 0) + 1
        self.genre_pill.set_entries(sorted(counts.items(), key=lambda pair: (-pair[1], pair[0])), unknown, len(base))

    def _genre_picked(self, index: int) -> None:
        name = self.genre_pill.itemData(index, GENRE_ROLE) or ui_rules.GENRE_ALL
        if name == self.genre_pill.chosen() and name == self.genre_pill._wanted:
            return
        self.genre_pill.choose(name)
        self.refresh()
        self.genreChanged.emit(name)
        self.play_entrance()  # a pick brings the tiles in; a refresh never does (Phase 34)

    def set_genre(self, name) -> None:
        """Put back a genre chosen in an earlier session, quietly; anything unknown is all of them."""
        name = name if isinstance(name, str) and name else ui_rules.GENRE_ALL
        self.genre_pill.choose(name)
        self.refresh()

    def set_genres(self, genres: dict) -> None:
        """Each game's genres, from the window's store, once a reload."""
        self.genres = dict(genres)

    # -- the pad on the row above the grid (Phase 99) -------------------------------------------------------

    def _controls(self) -> list:
        row = [*self.chips.values(), self.extras_box, self.hidden_box, self.genre_pill, self.sort_box]
        return [w for w in row if w.isVisibleTo(self) and not w.isHidden()]

    def _enter_controls(self) -> None:
        """Up past the card, or past the top row with no card: onto the row of controls, the chosen chip first."""
        controls = self._controls()
        if not controls:
            return
        if self._on_card:
            self._on_card = False
            self.card.clear_focus()
        self._on_controls = True
        chosen = next((i for i, w in enumerate(controls) if w in self.chips.values() and w.isChecked()), 0)
        self._control_at = chosen
        window = self.window()
        window.setAttribute(Qt.WidgetAttribute.WA_KeyboardFocusChange, True)
        controls[chosen].setFocus(Qt.FocusReason.OtherFocusReason)
        self.list.viewport().update()

    def _off_controls(self, *_args) -> None:
        """A tile chosen another way -- a click, or the window choosing one: the pad's place is the grid again."""
        if self._on_controls:
            self._on_controls = False
            self.controls_ring.refresh()

    def _leave_controls(self) -> None:
        self._on_controls = False
        if self.card.shown:
            self._enter_card(self._row_before_card if self._row_before_card >= 0 else 0)
            return
        if self.list.count():
            row = self._row_before_card if 0 <= self._row_before_card < self.list.count() else 0
            self.list.setCurrentRow(row)
            self.list.setFocus(Qt.FocusReason.OtherFocusReason)

    @property
    def on_controls(self) -> bool:
        return self._on_controls

    def _press_control(self) -> None:
        controls = self._controls()
        if not controls:
            return
        control = controls[min(self._control_at, len(controls) - 1)]
        if isinstance(control, QComboBox):
            control.showPopup()  # the pad works the list as any popup (MainWindow._drive_popup)
        else:
            control.click()

    def set_sort(self, mode: str) -> None:
        """Put back a sort chosen in an earlier session. Anything unrecognised is ignored.

        Signals are held while it changes, so restoring a choice is not mistaken for making
        one and written straight back to config.json.
        """
        if mode not in SORT_MODES or mode == self.sort_box.currentText():
            return
        self.sort_box.blockSignals(True)
        self.sort_box.setCurrentText(mode)
        self.sort_box.blockSignals(False)
        self.refresh()

    def repaint_tiles(self) -> None:
        """Redraw every tile in place, after something only the painting depends on."""
        self.list.viewport().update()
        self.card.update()

    def _sorted(self, views: list) -> list:
        mode = self.sort_box.currentText()
        if mode == "Last played":
            return sorted(views, key=lambda v: _stamp(v.last_played), reverse=True)
        if mode == "Recently added":
            return sorted(views, key=lambda v: _stamp(v.first_seen), reverse=True)
        return sorted(views, key=lambda v: v.display_name.casefold())

    def current_key(self) -> str:
        item = self.list.currentItem()
        return item.data(KEY_ROLE) if item is not None else ""

    def select_key(self, key: str) -> None:
        if key in self.visible_keys:
            self._on_card = False
            self._off_controls()
            self.card.clear_focus()
            self.list.setCurrentRow(self.visible_keys.index(key))
            self.list.scrollToItem(self.list.currentItem())

    # -- controller-driven focus ----------------------------------------------------------

    NAV_KEYS = {
        "up": Qt.Key.Key_Up,
        "down": Qt.Key.Key_Down,
        "left": Qt.Key.Key_Left,
        "right": Qt.Key.Key_Right,
        "page_up": Qt.Key.Key_PageUp,
        "page_down": Qt.Key.Key_PageDown,
    }

    def move_focus(self, direction: str) -> None:
        """Move the selection by handing Qt the equivalent key press.

        Synthesising the key rather than computing rows and columns means grid wrapping,
        page jumps and scrolling-into-view all behave exactly as they do for the keyboard.

        The Continue playing card sits above the grid. Crossing to it is detected rather
        than calculated, the way the shelves' crossing was: send "up", and if the selection
        did not move, the top row was already reached and focus belongs to the card. On the
        card, left and right move between Play and Details, and down comes back to the tile
        you left.
        """
        key = self.NAV_KEYS.get(direction)
        if key is None:
            log.debug("no navigation key for %r", direction)
            return
        if self._on_controls:
            controls = self._controls()
            if direction in ("left", "right") and controls:
                self._control_at = max(0, min(len(controls) - 1, self._control_at + (-1 if direction == "left" else 1)))
                controls[self._control_at].setFocus(Qt.FocusReason.OtherFocusReason)
            elif direction in ("down", "page_down"):
                self._leave_controls()
            return
        if not self.ensure_focus():
            return

        if self._on_card:
            if direction in ("left", "right"):
                self.card.focus_step(-1 if direction == "left" else 1)
            elif direction in ("down", "page_down"):
                self._leave_card()
            elif direction == "up":
                self._enter_controls()  # Phase 99: on up to the chips, the switches, the genre and the sort
            return

        before = self.list.currentRow()
        for event_type in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            QApplication.sendEvent(
                self.list, QKeyEvent(event_type, key, Qt.KeyboardModifier.NoModifier)
            )
        if self.list.currentRow() == before and direction == "up" and self.card.shown:
            self._enter_card(before)
            return
        if self.list.currentRow() == before and direction == "up":
            self._row_before_card = before
            self._enter_controls()  # no card above the grid: straight to the row of controls (Phase 99)
            return
        item = self.list.currentItem()
        if item is not None:
            self.list.scrollToItem(item)

    @property
    def on_card(self) -> bool:
        return self._on_card

    def _enter_card(self, row: int) -> None:
        """Up from the top row: onto the card's Play button, with one ring on screen."""
        self._row_before_card = row
        self._on_card = True
        self.list.setCurrentRow(-1)
        self.list.clearSelection()
        self.list.viewport().update()
        self.card.focus_button(ui_continue.PLAY)
        self._want_backdrop(self.card.view.key)
        log.debug("focus moved up to the Continue playing card")

    def _leave_card(self) -> None:
        """Down from the card: back to the tile the pad came up from."""
        self._on_card = False
        self.card.clear_focus()
        if not self.list.count():
            return
        row = self._row_before_card if 0 <= self._row_before_card < self.list.count() else 0
        self.list.setCurrentRow(row)
        self.list.scrollToItem(self.list.currentItem())
        self.list.setFocus(Qt.FocusReason.OtherFocusReason)

    def ensure_focus(self) -> bool:
        """Make sure something is selected, so the first press has somewhere to move from."""
        if self._on_card:
            if self.card.shown:
                return True
            self._on_card = False  # the card went away underneath us
            self.card.clear_focus()
        if not self.list.count():
            return False
        if self.list.currentRow() < 0:
            row = self._row_before_card if 0 <= self._row_before_card < self.list.count() else 0
            self.list.setCurrentRow(row)
        return True

    def focused_key(self) -> str:
        """Whichever game the pad is on: the card's, or the selected tile's."""
        if self._on_card and self.card.view is not None:
            return self.card.view.key
        return self.current_key()

    def activate_current(self) -> None:
        """A on the card presses the button it is on; A on a tile opens that game."""
        if self._on_controls:
            self._press_control()  # Phase 99: a chip, a switch, or a pill's list
            return
        if self._on_card:
            self.card.activate_focused()
            return
        key = self.current_key()
        if key:
            self._remember_launch(self.list.currentRow())
            self.gameActivated.emit(key)

    def context_for_current(self) -> None:
        """Open the right-click menu at whatever the pad is on, for a pad with no mouse."""
        if self._on_card and self.card.view is not None:
            button = self.card.buttons[self.card.focused_index]
            self.contextRequested.emit(self.card.view.key,
                                       button.mapToGlobal(button.rect().center()))
            return
        item = self.list.currentItem()
        if item is None:
            return
        position = self.list.viewport().mapToGlobal(self.list.visualItemRect(item).center())
        self.contextRequested.emit(item.data(KEY_ROLE), position)

    def neighbour(self, key: str, step: int) -> str:
        """The next or previous game in the order currently on screen."""
        if key not in self.visible_keys:
            return ""
        index = (self.visible_keys.index(key) + step) % len(self.visible_keys)
        return self.visible_keys[index]

    # -- interaction ------------------------------------------------------------------------

    def _activate(self, item: QListWidgetItem) -> None:
        if item is not None:
            self._remember_launch(self.list.row(item))
            self.gameActivated.emit(item.data(KEY_ROLE))

    def _selection_changed(self, current, _previous) -> None:
        # The whole view, not just the two cells Qt would repaint: the focus glow reaches
        # past its own cell and would otherwise be left behind.
        self.list.viewport().update()
        self._focus_moved(self.list.currentRow())
        if current is not None:
            key = current.data(KEY_ROLE)
            if self._on_card:  # a click on a tile while the pad was on the card
                self._on_card = False
                self.card.clear_focus()
            self._want_backdrop(key)
            self.gameSelected.emit(key)

    def _context_menu(self, position) -> None:
        item = self.list.itemAt(position)
        if item is not None:
            self.contextRequested.emit(
                item.data(KEY_ROLE), self.list.viewport().mapToGlobal(position)
            )

    # -- animation ----------------------------------------------------------------------------

    def hover_progress(self, row: int) -> float:
        return self._hover_curve.valueForProgress(self._progress.get(row, 0.0))

    def focus_progress(self, row: int) -> float:
        """How far the pad's (or the keyboard's) focus has reached this tile, eased."""
        if row in self._focus:
            return self._focus_curve.valueForProgress(self._focus[row])
        return 1.0 if row >= 0 and row == self._focused_row else 0.0

    def appear_progress(self, row: int) -> float:
        """How far this tile has arrived: a wave, left to right and down, when it plays."""
        if not self._entrance_on:
            return 1.0
        if not self._entrance_started:
            return 0.0
        delay = min(row, ui_rules.TILE_ENTRANCE_STAGGERED) * ui_rules.TILE_ENTRANCE_STAGGER_MS
        elapsed = (self._entrance.elapsed() - delay) / max(1, ui_rules.TILE_ENTRANCE_MS)
        if elapsed >= 1.0:
            return 1.0
        if elapsed <= 0.0:
            return 0.0
        return self._entrance_curve.valueForProgress(elapsed)

    @property
    def entrance_running(self) -> bool:
        return self._entrance_on

    def play_entrance(self) -> None:
        """Bring the tiles in as a quick wave: first sight of the library, or a new set.

        Only ever asked for by the window's first show and by the user changing what the
        grid holds -- never by a refresh, which also runs in the background.
        """
        if self.reduce_animations or not self.list.count():
            return
        self._entrance_on = True
        self._entrance_started = False
        self._start_ticking()
        self.list.viewport().update()

    def _entrance_length_ms(self) -> int:
        return (ui_rules.TILE_ENTRANCE_STAGGERED * ui_rules.TILE_ENTRANCE_STAGGER_MS
                + ui_rules.TILE_ENTRANCE_MS)

    def _focus_moved(self, row: int) -> None:
        """The selection moved: the new tile grows in and the old one settles back."""
        old = self._focused_row
        self._focused_row = row
        if self._restoring or self.reduce_animations or not self.isVisible():
            # Put back by a rebuild, or moved while nobody can see the grid: settled at once.
            self._focus.clear()
            return
        if old >= 0 and old != row:
            self._focus[old] = self._focus.get(old, 1.0)
        if row >= 0 and row != old:
            self._focus[row] = self._focus.get(row, 0.0)
        self._start_ticking()

    def _start_ticking(self) -> None:
        if not self._ticker.isActive():
            self._clock.start()
            self._ticker.start()

    # -- the cover flight's two ends -------------------------------------------------------

    def note_cover(self, row: int, rect: QRect) -> None:
        """Where a tile has just drawn its cover. The delegate calls this as it paints."""
        self._painted[row] = QRect(rect)

    def _remember_launch(self, row: int) -> None:
        rect = self._painted.get(row)
        if rect is None:
            self._launch = None
            return
        self._launch = QRect(self.list.viewport().mapToGlobal(rect.topLeft()), rect.size())

    def take_launch_rect(self, into: QWidget) -> QRect | None:
        """The cover a tile was opened from, in `into`'s coordinates -- once, then forgotten.

        Only a tile sets it. Opening a game from the Continue playing card, the Storage page
        or Play something leaves it empty, and the page arrives without a flight.
        """
        rect, self._launch = self._launch, None
        if rect is None:
            return None
        return QRect(into.mapFromGlobal(rect.topLeft()), rect.size())

    def tile_cover_rect(self, key: str, into: QWidget) -> QRect | None:
        """Where `key`'s tile draws its cover, in `into`'s coordinates -- if it is in view."""
        if key not in self.visible_keys:
            return None
        row = self.visible_keys.index(key)
        cell = self.list.visualItemRect(self.list.item(row))
        viewport = self.list.viewport()
        rect = self.delegate.cover_geometry(cell, self.metrics, 0.0,
                                            1.0 if row == self.list.currentRow() else 0.0)
        if not viewport.rect().contains(rect.center()):
            return None
        return QRect(viewport.mapTo(into, rect.topLeft()), rect.size())

    def _hover(self, index) -> None:
        row = index.row() if index is not None and index.isValid() else -1
        if row == self._hover_row:
            return
        self._hover_row = row
        if row >= 0:
            self._want_backdrop(self.list.item(row).data(KEY_ROLE), settle=True)
        else:
            self._backdrop_timer.stop()  # the mouse left; keep whatever is showing
        if self.reduce_animations:
            self._progress = {row: 1.0} if row >= 0 else {}
            self.list.viewport().update()
            return
        self._start_ticking()

    def _tick(self) -> None:
        elapsed = self._clock.restart() if self._clock.isValid() else ANIMATION_TICK_MS
        busy = False

        step = elapsed / max(1, ui_rules.HOVER_DURATION_MS)
        rows = set(self._progress) | ({self._hover_row} if self._hover_row >= 0 else set())
        for row in rows:
            target = 1.0 if row == self._hover_row else 0.0
            value = self._progress.get(row, 0.0)
            if abs(value - target) <= step:
                value = target
            else:
                value += step if target > value else -step
                busy = True
            if value <= 0.0:
                self._progress.pop(row, None)
            else:
                self._progress[row] = value

        step = elapsed / max(1, ui_rules.FOCUS_DURATION_MS)
        for row in list(self._focus):
            target = 1.0 if row == self._focused_row else 0.0
            value = self._focus[row]
            if abs(value - target) <= step:
                del self._focus[row]  # arrived: focus_progress reads it from _focused_row
            else:
                self._focus[row] = value + (step if target > value else -step)
                busy = True

        if self._entrance_on:
            if not self._entrance_started:
                self._entrance_started = True
                self._entrance.start()
                busy = True
            elif self._entrance.elapsed() >= self._entrance_length_ms():
                self._entrance_on = False
            else:
                busy = True

        self.list.viewport().update()
        if not busy:
            self._ticker.stop()

    def scroll_to(self, value: int) -> None:
        from PySide6.QtCore import QPropertyAnimation

        bar = self.list.verticalScrollBar()
        if self.reduce_animations:
            bar.setValue(value)
            return
        if self._scroll_anim is not None:
            self._scroll_anim.stop()
        animation = QPropertyAnimation(bar, b"value", self)
        animation.setDuration(ui_rules.SCROLL_DURATION_MS)
        animation.setEasingCurve(ui_theme.easing(ui_rules.SCROLL_EASING))
        animation.setStartValue(bar.value())
        animation.setEndValue(value)
        animation.start()
        self._scroll_anim = animation

    def apply_metrics(self, metrics, reduce_animations: bool) -> None:
        self.metrics = metrics
        self.reduce_animations = reduce_animations
        self.list.setSpacing(metrics.grid_spacing)
        self.top_bar.apply_scale(metrics.scale)
        self.rail.apply_scale(metrics.scale)
        self._size_search()
        self._apply_margins()
        self._size_controls()
        self.continue_card.apply_metrics(metrics)
        self.jump.apply_metrics(metrics)
        self.covers.clear()
        self._painted.clear()
        self.refresh()


def _stamp(moment) -> float:
    return moment.timestamp() if moment is not None else -1.0


def _tooltip(view) -> str:
    from shared.humanize import size as human_size

    details = [view.display_name, view.launch_target]
    found = f"found by: {view.entry.source}/{view.entry.detection}"
    if view.entry.size_on_disk:
        found += f"    size: {human_size(view.entry.size_on_disk)}"
    details.append(found)
    if view.app_type:
        details.append(f"Steam calls this a {view.app_type}")
    if view.args:
        details.append(f"arguments: {view.args}")
    if view.status:
        details.append(f"You marked this: {ui_rules.STATUS_LABELS[view.status]}")
    if view.notes:
        first = view.notes.splitlines()[0]
        details.append("Note: " + (first if len(first) <= 80 else first[:79] + "…"))
    return "\n".join(details)


def stylesheet(scale: float) -> str:
    """The empty library's words (Phase 77); everything else of the page is ui_theme's."""
    s = lambda value: max(1, round(value * scale))  # noqa: E731
    return f"""
    QFrame#EmptyLibrary {{ background: transparent; border: none; }}
    QLabel#EmptyTitle {{
        font-size: {s(ui_rules.EMPTY_TITLE_PX)}px; font-weight: {ui_rules.HEADING_WEIGHT};
        color: {ui_rules.COLOR_TEXT}; background: transparent;
    }}
    QLabel#EmptyText {{
        font-size: {s(ui_rules.EMPTY_TEXT_PX)}px; color: {ui_rules.COLOR_TEXT_SOFT}; background: transparent;
        qproperty-alignment: AlignCenter;
    }}
    """
