"""The pieces the pages are built from: cards, bars, a layout that wraps, and a switch.

First made for the game page below its art (Phase 33); Stats and Settings use them too
since Phase 35.

A card is a rounded glass panel with a title; everything under the art is one. The play
history is drawn as bars rather than listed as text. And the flow layout lays things out in
rows that wrap -- the pills under the title and the screenshots both need that, because a
row that cannot wrap either clips or forces the whole page wider than the window.
"""

from __future__ import annotations

import logging
from math import ceil

from PySide6.QtCore import QEvent, QPoint, QRect, QRectF, QSize, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QVBoxLayout,
    QWidget,
)

from presentation import ui_icons
from presentation import ui_rules
from presentation import ui_theme
from shared import rules

log = logging.getLogger(__name__)


class FlowLayout(QLayout):
    """Items left to right, wrapping onto a new row when the width runs out.

    The classic Qt flow layout. It answers heightForWidth, which is what lets a box layout
    around it grow a second row instead of pushing everything sideways.
    """

    def __init__(self, parent=None, spacing: int = 8) -> None:
        super().__init__(parent)
        self._items: list = []
        self._spacing = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def set_spacing(self, spacing: int) -> None:
        self._spacing = spacing
        self.invalidate()

    def addItem(self, item) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._arrange(QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._arrange(rect, apply=True)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            if not item.isEmpty():
                size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        return size + QSize(margins.left() + margins.right(), margins.top() + margins.bottom())

    def _arrange(self, rect: QRect, apply: bool) -> int:
        margins = self.contentsMargins()
        area = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        x, y, line = area.x(), area.y(), 0
        for item in self._items:
            if item.isEmpty():  # a hidden widget takes no room
                continue
            hint = item.sizeHint()
            if x > area.x() and x + hint.width() > area.right() + 1:
                x, y, line = area.x(), y + line + self._spacing, 0
            if apply:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + self._spacing
            line = max(line, hint.height())
        return y + line - rect.y() + margins.bottom()


def clear_widget(name: str = "Clear") -> QWidget:
    """A plain holder that paints nothing, so the backdrop shows through it.

    A plain QWidget otherwise picks up the blanket background rule and paints an opaque
    rectangle -- the Phase 32 lesson.
    """
    widget = QWidget()
    widget.setObjectName(name)
    return widget


class Card(QFrame):
    """A rounded panel with a title, and room on the title's line for one control.

    `padding` -- (sides, top and bottom), or (sides, top, bottom) -- and `title_gap` are at a
    scale of 1. The game page's cards (Phase 57) and Stats' (Phase 58) pass the design's.
    """

    def __init__(self, title: str, parent=None, padding: tuple[float, ...] | None = None,
                 title_gap: float | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.padding = padding or (ui_rules.DETAIL_CARD_PADDING, ui_rules.DETAIL_CARD_PADDING)
        self.title_gap = ui_rules.DETAIL_CARD_TITLE_GAP if title_gap is None else title_gap
        self.title = QLabel(title)
        self.title.setObjectName("CardTitle")
        self.header = QHBoxLayout()
        self.header.setContentsMargins(0, 0, 0, 0)
        self.header.addWidget(self.title)
        self.header.addStretch(1)
        self.body = QVBoxLayout()
        self.body.setContentsMargins(0, 0, 0, 0)
        layout = QVBoxLayout(self)
        layout.addLayout(self.header)
        layout.addLayout(self.body)
        self.apply_scale(1.0)

    def add_to_header(self, widget: QWidget) -> None:
        self.header.addWidget(widget)

    def apply_scale(self, scale: float) -> None:
        side = max(10, round(self.padding[0] * scale))
        top = max(8, round(self.padding[1] * scale))
        bottom = max(8, round(self.padding[-1] * scale))
        self.layout().setContentsMargins(side, top, side, bottom)
        self.layout().setSpacing(max(4, round(self.title_gap * scale)))
        self.body.setSpacing(max(4, round(ui_rules.DETAIL_CARD_BODY_GAP * scale)))


class ShareBars(QWidget):
    """A list of shares, one row each: what, a bar as long as its share, and the figure (Phase 84).

    The Reports page's bar lists: each row's `fraction` (0 to 1) is its bar's length on a track the
    room's width, in the session bars' colours. A zero draws the track alone -- no sliver, since
    a share of nothing is nothing -- and a label longer than its column is cut with an ellipsis,
    its full words in the tooltip of the row's line.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.rows: list[tuple[str, float, str]] = []  # (label, fraction, figure)
        self.scale = 1.0
        self.setMouseTracking(True)

    def set_rows(self, rows) -> None:
        self.rows = [(str(label), max(0.0, min(1.0, float(fraction))), str(value)) for label, fraction, value in rows]
        self.updateGeometry()
        self.update()

    def apply_scale(self, scale: float) -> None:
        self.scale = scale
        self.updateGeometry()
        self.update()

    def _font(self) -> QFont:
        font = QFont(ui_icons.body_family())
        font.setPointSizeF(max(7.0, ui_theme.px_to_pt(ui_rules.SESSION_TEXT_PX * self.scale)))
        return font

    def _columns(self) -> tuple[int, int, int]:
        metrics = QFontMetrics(self._font())
        label = max((metrics.horizontalAdvance(row[0]) for row in self.rows), default=0)
        value = max((metrics.horizontalAdvance(row[2]) for row in self.rows), default=0)
        # One width for every list's words (REPORT_BAR_LABEL_MAX), so the bars of every card start in
        # one place; a label longer than that is cut, its words in the tooltip.
        return (round(ui_rules.REPORT_BAR_LABEL_MAX * self.scale),
                max(value, round(ui_rules.SESSION_LENGTH_WIDTH * self.scale)),
                round(ui_rules.SESSION_COLUMN_GAP * self.scale))

    def sizeHint(self) -> QSize:
        label, value, gap = self._columns()
        height = round(len(self.rows) * ui_rules.REPORT_BAR_ROW_HEIGHT * self.scale)
        return QSize(label + value + gap * 2 + round(ui_rules.SESSION_BAR_ROOM * self.scale), height)

    def minimumSizeHint(self) -> QSize:
        label, value, gap = self._columns()
        height = round(len(self.rows) * ui_rules.REPORT_BAR_ROW_HEIGHT * self.scale)
        return QSize(label + value + gap * 2 + round(ui_rules.SESSION_BAR_MIN_ROOM * self.scale), height)

    def bar_box(self) -> QRectF:
        label_w, value_w, gap = self._columns()
        left = label_w + gap
        return QRectF(left, 0, max(0.0, self.width() - value_w - gap - left), self.height())

    def bar_width(self, index: int) -> float:
        """How long row `index`'s bar is drawn -- its share of the room."""
        return self.bar_box().width() * self.rows[index][1]

    def mouseMoveEvent(self, event) -> None:
        row = int(event.position().y() // max(1.0, ui_rules.REPORT_BAR_ROW_HEIGHT * self.scale))
        self.setToolTip(f"{self.rows[row][0]}: {self.rows[row][2]}" if 0 <= row < len(self.rows) else "")
        super().mouseMoveEvent(event)

    def paintEvent(self, event) -> None:
        if not self.rows:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setFont(self._font())
        metrics = QFontMetrics(self._font())
        label_w, value_w, gap = self._columns()
        row_h = ui_rules.REPORT_BAR_ROW_HEIGHT * self.scale
        bar_h = max(3.0, ui_rules.SESSION_BAR_HEIGHT * self.scale)
        box = self.bar_box()
        gradient = QLinearGradient(box.left(), 0, box.left() + box.width(), 0)
        gradient.setColorAt(0.0, QColor(ui_rules.COLOR_SESSION_BAR_START))
        gradient.setColorAt(1.0, QColor(ui_rules.COLOR_SESSION_BAR_END))
        for index, (label, fraction, value) in enumerate(self.rows):
            top = index * row_h
            middle = top + row_h / 2
            painter.setPen(QColor(ui_rules.COLOR_SESSION_DAY))
            painter.drawText(QRectF(0, top, label_w + 1, row_h),
                             int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                             metrics.elidedText(label, Qt.TextElideMode.ElideRight, label_w))
            track = QRectF(box.left(), middle - bar_h / 2, box.width(), bar_h)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(ui_rules.COLOR_SESSION_TRACK))
            painter.drawRoundedRect(track, bar_h / 2, bar_h / 2)
            if fraction > 0:
                track.setWidth(max(bar_h, box.width() * fraction))
                painter.setBrush(gradient)
                painter.drawRoundedRect(track, bar_h / 2, bar_h / 2)
            painter.setPen(QColor(ui_rules.COLOR_SESSION_LENGTH))
            painter.drawText(QRectF(self.width() - value_w - 1, top, value_w + 1, row_h),
                             int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), value)


class SessionBars(QWidget):
    """The last few sessions, one row each: when, a bar as long as it was, and for how long.

    The longest session fills the room; every other bar is in proportion to it, never
    shorter than SESSION_MIN_BAR_PX -- a two-minute session beside a three-hour one would
    otherwise round to nothing, and "I played and it is not there" is the wrong answer.
    Each bar lies on a track the width of the room, as the design draws it (Phase 57).
    """

    # A star in a session's row was clicked (Phase 102): the row and the stars given.
    rateClicked = Signal(int, int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.rows: list[tuple[str, int, str]] = []  # (when, minutes, how long)
        # Phase 102: each row's stars -- (stars or None, whether a click may rate it) -- or none at all, as before.
        self.stars: list[tuple[int | None, bool]] = []
        self.scale = 1.0
        self.setMouseTracking(True)
        self._hover: tuple[int, int] | None = None  # (row, star) under the mouse

    def set_rows(self, rows: list[tuple[str, int, str]], stars: list[tuple[int | None, bool]] | None = None) -> None:
        self.rows = rows
        self.stars = list(stars or [])
        self._hover = None
        self.updateGeometry()
        self.update()

    def _stars_width(self) -> int:
        """The room a row's five stars take, after its length -- none when no row has any."""
        if not any(stars is not None or rateable for stars, rateable in self.stars):
            return 0
        star = ui_rules.RATE_SESSION_STAR_PX * self.scale
        gap = ui_rules.RATE_SESSION_STAR_GAP * self.scale
        return round(ui_rules.RATE_SESSION_STARS_GAP * self.scale + rules.RATE_STARS * star + (rules.RATE_STARS - 1) * gap)

    def _star_at(self, x: float, y: float) -> tuple[int, int] | None:
        """The (row, star) a point is on -- only on a row a click may rate."""
        width = self._stars_width()
        if not width or not self.rows:
            return None
        row = int(y // (ui_rules.SESSION_ROW_HEIGHT * self.scale))
        if not (0 <= row < len(self.stars)) or not self.stars[row][1]:
            return None
        star = ui_rules.RATE_SESSION_STAR_PX * self.scale
        gap = ui_rules.RATE_SESSION_STAR_GAP * self.scale
        left = self.width() - (rules.RATE_STARS * star + (rules.RATE_STARS - 1) * gap)
        if x < left:
            return None
        number = int((x - left) // (star + gap)) + 1
        return (row, number) if 1 <= number <= rules.RATE_STARS else None

    def mouseMoveEvent(self, event) -> None:
        hover = self._star_at(event.position().x(), event.position().y())
        if hover != self._hover:
            self._hover = hover
            self.setCursor(Qt.CursorShape.PointingHandCursor if hover else Qt.CursorShape.ArrowCursor)
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        if self._hover is not None:
            self._hover = None
            self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        hit = self._star_at(event.position().x(), event.position().y())
        if hit is not None and event.button() == Qt.MouseButton.LeftButton:
            self.rateClicked.emit(*hit)
            return
        super().mousePressEvent(event)

    def apply_scale(self, scale: float) -> None:
        self.scale = scale
        self.updateGeometry()
        self.update()

    def _font(self) -> QFont:
        font = QFont(ui_icons.body_family())
        font.setPointSizeF(max(7.0, ui_theme.px_to_pt(ui_rules.SESSION_TEXT_PX * self.scale)))
        return font

    def _columns(self) -> tuple[int, int, int]:
        """The day's and the length's columns: the design's widths, or their words' if wider."""
        metrics = QFontMetrics(self._font())
        when = max((metrics.horizontalAdvance(row[0]) for row in self.rows), default=0)
        length = max((metrics.horizontalAdvance(row[2]) for row in self.rows), default=0)
        return (max(when, round(ui_rules.SESSION_DAY_WIDTH * self.scale)),
                max(length, round(ui_rules.SESSION_LENGTH_WIDTH * self.scale)),
                round(ui_rules.SESSION_COLUMN_GAP * self.scale))

    def sizeHint(self) -> QSize:
        when, length, gap = self._columns()
        height = round(len(self.rows) * ui_rules.SESSION_ROW_HEIGHT * self.scale)
        return QSize(when + length + gap * 2 + round(ui_rules.SESSION_BAR_ROOM * self.scale) + self._stars_width(), height)

    def minimumSizeHint(self) -> QSize:
        when, length, gap = self._columns()
        height = round(len(self.rows) * ui_rules.SESSION_ROW_HEIGHT * self.scale)
        return QSize(when + length + gap * 2 + round(ui_rules.SESSION_BAR_MIN_ROOM * self.scale) + self._stars_width(),
                     height)

    def bar_box(self) -> QRectF:
        """Where the bars lie, left to right: between the day's column and the length's."""
        when_w, length_w, gap = self._columns()
        left = when_w + gap
        return QRectF(left, 0, max(0.0, self.width() - self._stars_width() - length_w - gap - left), self.height())

    def paintEvent(self, event) -> None:
        if not self.rows:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setFont(self._font())
        when_w, length_w, gap = self._columns()
        row_h = ui_rules.SESSION_ROW_HEIGHT * self.scale
        bar_h = max(3.0, ui_rules.SESSION_BAR_HEIGHT * self.scale)
        box = self.bar_box()
        bar_left, room = box.left(), box.width()
        longest = max(row[1] for row in self.rows) or 1
        gradient = QLinearGradient(bar_left, 0, bar_left + room, 0)
        gradient.setColorAt(0.0, QColor(ui_rules.COLOR_SESSION_BAR_START))
        gradient.setColorAt(1.0, QColor(ui_rules.COLOR_SESSION_BAR_END))
        shortest = max(ui_rules.SESSION_MIN_BAR_PX * self.scale, room * ui_rules.SESSION_MIN_BAR_FRACTION)

        for index, (when, minutes, length) in enumerate(self.rows):
            top = index * row_h
            middle = top + row_h / 2
            painter.setPen(QColor(ui_rules.COLOR_SESSION_DAY))
            painter.drawText(QRectF(0, top, when_w + 1, row_h),
                             int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), when)
            bar = QRectF(bar_left, middle - bar_h / 2, room, bar_h)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(ui_rules.COLOR_SESSION_TRACK))
            painter.drawRoundedRect(bar, bar_h / 2, bar_h / 2)
            bar.setWidth(min(room, max(shortest, room * minutes / longest)))
            painter.setBrush(gradient)
            painter.drawRoundedRect(bar, bar_h / 2, bar_h / 2)
            painter.setPen(QColor(ui_rules.COLOR_SESSION_LENGTH))
            stars_w = self._stars_width()
            painter.drawText(QRectF(self.width() - stars_w - length_w - 1, top, length_w + 1, row_h),
                             int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), length)
            if stars_w and index < len(self.stars):
                self._paint_stars(painter, index, middle)

    def _paint_stars(self, painter, index: int, middle: float) -> None:
        """A row's stars: filled as many as it was rated, the rest quiet; a rateable row lights under the mouse."""
        stars, rateable = self.stars[index]
        if stars is None and not rateable:
            return
        size = ui_rules.RATE_SESSION_STAR_PX * self.scale
        gap = ui_rules.RATE_SESSION_STAR_GAP * self.scale
        lit = self._hover[1] if self._hover is not None and self._hover[0] == index else (stars or 0)
        left = self.width() - (rules.RATE_STARS * size + (rules.RATE_STARS - 1) * gap)
        for number in range(1, rules.RATE_STARS + 1):
            full = number <= lit
            pixmap = ui_icons.glyph_pixmap("star_full" if full else "star",
                                           ui_rules.COLOR_ACCENT_HOVER if full else ui_rules.COLOR_TEXT_MUTED,
                                           max(1, round(size)))
            x = left + (number - 1) * (size + gap)
            painter.drawPixmap(QRectF(x, middle - size / 2, size, size), pixmap, QRectF(pixmap.rect()))


class FocusRing(QWidget):
    """The design's focus ring -- 2 px of the accent, 2 px out -- around whatever has focus.

    A stylesheet can only ring a button from inside its own edge, which on an outlined
    button (Play's accent edge) reads as a thicker edge rather than as "you are here". The
    Continue card draws the ring around its two buttons itself (Phase 56); the game page,
    whose buttons sit in a dozen places, lays this one over itself instead and moves it to
    whichever of them the keyboard or the pad is on (Phase 57). It takes no clicks.

    `ringed(widget)` says which controls get it. A control with other corners than
    CONTROL_RADIUS says so with a `ringRadius` property, in pixels at the current scale.
    `clip` is the scroll area's viewport, if there is one: a control scrolled half out of
    it is ringed only where it can be seen.
    """

    def __init__(self, page: QWidget, ringed, scale=None) -> None:
        super().__init__(page)
        self.page = page
        self.ringed = ringed
        # The page's scale -- a page has metrics; a dialog (Settings, Phase 58) passes its own.
        self.scale = scale or (lambda: page.metrics.scale)
        self.clip: QWidget | None = None
        self.target: QWidget | None = None
        self._watched: list[QWidget] = []
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.hide()
        QApplication.instance().focusChanged.connect(self._focus_moved)

    def ring_width(self) -> int:
        """The tiles' width (TV mode's thicker one included), at the page's scale."""
        width = getattr(self.page, "focus_ring_width", ui_rules.FOCUS_RING_WIDTH)
        return max(1, round(width * self.scale()))

    def _out(self) -> float:
        """From the control's edge to the middle of the ring."""
        return ui_rules.FOCUS_RING_GAP * self.scale() + self.ring_width() / 2

    def _focus_moved(self, _old, new) -> None:
        for widget in self._watched:
            widget.removeEventFilter(self)
        self._watched = []
        self.target = None
        if new is not None and self.page.isAncestorOf(new) and self.ringed(new):
            self.target = new
            # The control and everything it sits in, up to the page: when any of them
            # moves -- a scroll, a card appearing above it -- the ring goes with it.
            widget = new
            while widget is not None and widget is not self.page:
                widget.installEventFilter(self)
                self._watched.append(widget)
                widget = widget.parentWidget()
        self.place()

    def eventFilter(self, watched, event) -> bool:
        if event.type() in (QEvent.Type.Move, QEvent.Type.Resize, QEvent.Type.Show,
                            QEvent.Type.Hide):
            self.place()
        return super().eventFilter(watched, event)

    def refresh(self) -> None:
        """Ask again about whatever has the focus now -- when what decides it has changed."""
        self._focus_moved(None, QApplication.focusWidget())

    def follow(self, widget: QWidget) -> None:
        """A control with the focus says it is being drawn: ring it if that has changed --
        a switch is ringed only once a keyboard or pad move is marked, which can happen
        while it keeps the focus it was given on opening."""
        if widget.hasFocus() and bool(self.ringed(widget)) != (self.target is widget):
            self.refresh()

    def detach(self) -> None:
        """Stop following the application's focus: the dialog it rings is closing."""
        try:
            QApplication.instance().focusChanged.disconnect(self._focus_moved)
        except (RuntimeError, TypeError) as exc:
            log.debug("focus ring already detached: %s", exc)
        self._focus_moved(None, None)

    def place(self) -> None:
        target = self.target
        if target is None or not target.isVisibleTo(self.page) or not target.hasFocus():
            self.hide()
            return
        grow = ceil(self._out() + self.ring_width() / 2) + 1
        box = QRect(target.mapTo(self.page, QPoint(0, 0)), target.size())
        self.setGeometry(box.adjusted(-grow, -grow, grow, grow))
        self.show()
        self.raise_()
        self.update()

    def paintEvent(self, event) -> None:
        target = self.target
        if target is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if self.clip is not None and self.clip.isAncestorOf(target):
            painter.setClipRect(QRect(self.clip.mapTo(self.page, QPoint(0, 0)) - self.pos(),
                                      self.clip.size()))
        ring, out = self.ring_width(), self._out()
        radius = target.property("ringRadius")
        if radius is None:
            radius = ui_rules.CONTROL_RADIUS * self.scale()
        # Through the page: the ring is the control's cousin, not its parent.
        box = QRectF(QRect(target.mapTo(self.page, QPoint(0, 0)) - self.pos(), target.size()))
        painter.setPen(QPen(QColor(ui_rules.TILE_FOCUS_COLOR), ring))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(box.adjusted(-out, -out, out, out), float(radius) + out,
                                float(radius) + out)


class ToggleSwitch(QCheckBox):
    """An on/off switch that is still a QCheckBox underneath (Phase 35).

    isChecked, setChecked and toggled behave exactly as a tick-box's did, so everything
    that reads the settings -- the window, the tests -- is unchanged. It draws itself: a
    track that fills with the accent colour, a knob that slides across (at once when
    animations are reduced). Its ring, when the keyboard or the pad is on it, is the one the
    Settings dialog lays over itself for every control (Phase 58): the accent, 2 px outside
    the track, where it painted one inside the track before.
    """

    def __init__(self, parent=None, scale: float = 1.0, animate: bool = True) -> None:
        super().__init__(parent)
        self.scale = scale
        self.animate = animate
        self._position = 0.0
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)  # a click must not leave a ring
        self._slide = QVariantAnimation(self)
        self._slide.setDuration(ui_rules.SWITCH_MS)
        self._slide.valueChanged.connect(self._moved)
        self.toggled.connect(self._toggled)

    def setChecked(self, checked: bool) -> None:  # noqa: N802 -- Qt's name
        super().setChecked(checked)
        self._slide.stop()
        self._position = 1.0 if checked else 0.0
        self.update()

    def _toggled(self, checked: bool) -> None:
        if not self.animate:
            self._position = 1.0 if checked else 0.0
            self.update()
            return
        self._slide.stop()
        self._slide.setStartValue(self._position)
        self._slide.setEndValue(1.0 if checked else 0.0)
        self._slide.start()

    def _moved(self, value) -> None:
        self._position = float(value)
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(max(24, round(ui_rules.SWITCH_WIDTH * self.scale)),
                     max(14, round(ui_rules.SWITCH_HEIGHT * self.scale)))

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def hitButton(self, pos) -> bool:  # noqa: N802 -- Qt's name
        return self.rect().contains(pos)

    def paintEvent(self, event) -> None:
        ring = getattr(self.window(), "focus_ring", None)
        if ring is not None:
            ring.follow(self)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        size = self.sizeHint()
        track = QRectF(0, (self.height() - size.height()) / 2, size.width(), size.height())
        off, on = QColor(ui_rules.COLOR_SWITCH_OFF), QColor(ui_rules.COLOR_ACCENT)
        mix = self._position
        colour = QColor(round(off.red() + (on.red() - off.red()) * mix),
                        round(off.green() + (on.green() - off.green()) * mix),
                        round(off.blue() + (on.blue() - off.blue()) * mix))
        if not self.isEnabled():
            colour.setAlpha(110)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(colour)
        painter.drawRoundedRect(track, track.height() / 2, track.height() / 2)
        margin = ui_rules.SWITCH_KNOB_MARGIN * self.scale
        knob = track.height() - margin * 2
        x = track.left() + margin + (track.width() - margin * 2 - knob) * mix
        painter.setBrush(QColor(ui_rules.COLOR_TEXT))
        painter.drawEllipse(QRectF(x, track.top() + margin, knob, knob))
