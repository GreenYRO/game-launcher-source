"""Motion (Phase 34, step 4 of 5 of the redesign): pages that arrive, a cover that flies.

Both are drawn on overlays from pictures taken once, never by animating the real widgets.
Measured at the TV's 225% (3840x2160 pixels, drawn in software): one frame of the real
library costs about 24 ms, and the same page under an opacity effect -- how pages faded in
until now -- about 40 ms, so a fade ran at 25 frames a second there. A picture of the page
blitted over the backdrop costs about 19 ms, and the flying cover repaints only the small
area it passes through. At 100% on a desk monitor every one of these is a few milliseconds.

Neither overlay ever takes a click: while one is up, the real page underneath is already
the current page, and the mouse reaches it.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, QRectF, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap, QRegion
from PySide6.QtWidgets import QApplication, QWidget

from presentation import ui_rules
from presentation import ui_theme

log = logging.getLogger(__name__)

# How a page arrives.
FROM_RIGHT, FROM_LEFT, RISE, FADE = "from_right", "from_left", "rise", "fade"


def snapshot(widget: QWidget) -> QPixmap:
    """The widget as it draws right now, on a transparent picture at the screen's density.

    `render` with DrawChildren alone, onto a pixmap filled transparent: `grab` would paint a
    background under a see-through page (the Phase 32 lesson), and the backdrop has to show
    through the picture exactly as it shows through the live page.
    """
    ratio = widget.devicePixelRatioF() or 1.0
    pixmap = QPixmap(max(1, round(widget.width() * ratio)), max(1, round(widget.height() * ratio)))
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.GlobalColor.transparent)
    widget.render(pixmap, QPoint(), QRegion(), QWidget.RenderFlag.DrawChildren)
    return pixmap


def settle_layouts(widget: QWidget) -> None:
    """Lay a page out now rather than on the next pass, so a picture of it is the real one.

    A page that has just become the current one still has layout requests waiting in the
    event queue; a picture taken before they run shows the page as it was last laid out.
    """
    QApplication.sendPostedEvents(None, QEvent.Type.LayoutRequest)
    layout = widget.layout()
    if layout is not None:
        layout.activate()


class PageTransition(QWidget):
    """Covers the pages while one arrives: the backdrop, then a picture of the new page.

    Opaque, so Qt paints neither the real page nor the backdrop beneath it while it is up;
    a frame is the backdrop's pixels for this rectangle and one blit of the picture.
    """

    def __init__(self, backdrop) -> None:
        super().__init__(backdrop)
        self.backdrop = backdrop
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.kind = FADE
        self.scale = 1.0
        self.progress = 1.0
        self._picture: QPixmap | None = None
        self._animation = QVariantAnimation(self)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.valueChanged.connect(self._moved)
        self._animation.finished.connect(self._done)
        self.hide()

    @property
    def running(self) -> bool:
        return not self.isHidden()

    def start(self, page: QWidget, kind: str) -> None:
        """Take a picture of `page` -- already the current page -- and bring it in."""
        self.cancel()
        settle_layouts(page)
        self._picture = snapshot(page)
        self.kind = kind
        self.progress = 0.0
        self.setGeometry(QRect(page.mapTo(self.backdrop, QPoint(0, 0)), page.size()))
        self.show()
        self.raise_()
        self._animation.setDuration(ui_rules.PAGE_TRANSITION_MS)
        self._animation.setEasingCurve(ui_theme.easing(ui_rules.PAGE_TRANSITION_EASING))
        self._animation.start()

    def cancel(self) -> None:
        """Finish at once -- a resize, TV mode, or another page arriving on top of this one."""
        if self._animation.state() != QVariantAnimation.State.Stopped:
            self._animation.stop()
        self._done()

    def offset(self) -> QPointF:
        """Where the picture is now: all of its travel still ahead at the start, none at the end."""
        ahead = 1.0 - self.progress
        if self.kind == FROM_RIGHT:
            return QPointF(self.width() * ui_rules.PAGE_SLIDE_FRACTION * ahead, 0.0)
        if self.kind == FROM_LEFT:
            return QPointF(-self.width() * ui_rules.PAGE_SLIDE_FRACTION * ahead, 0.0)
        if self.kind == RISE:
            return QPointF(0.0, ui_rules.PAGE_RISE_PX * self.scale * ahead)
        return QPointF(0.0, 0.0)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        self.backdrop.paint_onto(painter, self.geometry())
        if self._picture is not None:
            painter.setOpacity(self.progress)
            painter.drawPixmap(self.offset(), self._picture)

    def _moved(self, value) -> None:
        self.progress = float(value)
        self.update()

    def _done(self) -> None:
        # Also reached through stop(), which can report the animation finished (Phase 17):
        # it only ever settles to the end state, so running twice changes nothing.
        self.progress = 1.0
        self._picture = None
        self.hide()


class CoverFlight(QWidget):
    """A cover on its way between a tile and its place on the game's page.

    Spans the whole window but paints only the cover and its shadow, and each frame asks
    for no more than the ground it has just covered to be repainted.
    """

    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.progress = 1.0
        self._pixmap: QPixmap | None = None
        self._shadow: QPixmap | None = None
        self._from = QRectF()
        self._to = QRectF()
        self._radii = (0.0, 0.0)
        self._spread = 0
        self._drop = 0.0
        self._on_land = None
        self._last = QRect()
        self._animation = QVariantAnimation(self)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.valueChanged.connect(self._moved)
        self._animation.finished.connect(self._land)
        self.hide()

    @property
    def flying(self) -> bool:
        return not self.isHidden()

    def fly(self, pixmap: QPixmap, start: QRect, end: QRect, start_radius: float,
            end_radius: float, spread: int, on_land, drop: int | None = None) -> None:
        """Carry `pixmap` from `start` to `end` (both in the parent's coordinates).

        `drop` is how far below the cover its shadow falls: half the spread unless said.
        """
        self.cancel()
        self._drop = spread / 2 if drop is None else drop
        self._pixmap = pixmap
        self._from, self._to = QRectF(start), QRectF(end)
        self._radii = (float(start_radius), float(end_radius))
        self._spread = max(2, int(spread))
        self._shadow = ui_theme.soft_edge(end.width(), end.height(), end_radius, self._spread,
                                          "#000000", ui_rules.DETAIL_COVER_SHADOW_ALPHA)
        self._on_land = on_land
        self.progress = 0.0
        self.setGeometry(self.parentWidget().rect())
        self.show()
        self.raise_()
        self._last = self._bounds()
        self.update(self._last)
        self._animation.setDuration(ui_rules.COVER_FLIGHT_MS)
        self._animation.setEasingCurve(ui_theme.easing(ui_rules.COVER_FLIGHT_EASING))
        self._animation.start()

    def cancel(self) -> None:
        """Land at once, wherever it was going; whoever was waiting for it is told."""
        if self._animation.state() != QVariantAnimation.State.Stopped:
            self._animation.stop()
        self._land()

    def current(self) -> QRectF:
        p = self.progress
        a, b = self._from, self._to
        return QRectF(a.x() + (b.x() - a.x()) * p, a.y() + (b.y() - a.y()) * p,
                      a.width() + (b.width() - a.width()) * p,
                      a.height() + (b.height() - a.height()) * p)

    def _bounds(self) -> QRect:
        """The cover now, with room for its shadow, which falls a little below it."""
        rect = self.current().toAlignedRect()
        grow = round(self._spread * max(1.0, rect.width() / max(1.0, self._to.width()))) + 2
        return rect.adjusted(-grow, -grow, grow, grow + self._spread)

    def _moved(self, value) -> None:
        self.progress = float(value)
        now = self._bounds()
        self.update(self._last.united(now))
        self._last = now

    def paintEvent(self, event) -> None:
        if self._pixmap is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        rect = self.current()
        radius = self._radii[0] + (self._radii[1] - self._radii[0]) * self.progress
        if self._shadow is not None:
            # One shadow, made for the landing size, stretched to the size in flight.
            size = rect.width() / max(1.0, self._to.width())
            spread, drop = self._spread * size, self._drop * size
            painter.drawPixmap(rect.adjusted(-spread, -spread + drop, spread, spread + drop),
                               self._shadow, QRectF(self._shadow.rect()))
        outline = QPainterPath()
        outline.addRoundedRect(rect, radius, radius)
        painter.save()
        painter.setClipPath(outline)
        painter.drawPixmap(rect, self._pixmap, QRectF(self._pixmap.rect()))
        painter.restore()
        # The game page's cover edge (Phase 57), just outside it, as the cover lands with.
        painter.setPen(QPen(QColor(ui_rules.COLOR_COVER_EDGE), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect.adjusted(-0.5, -0.5, 0.5, 0.5), radius + 0.5, radius + 0.5)

    def _land(self) -> None:
        callback, self._on_land = self._on_land, None
        self.progress = 1.0
        self._pixmap = None
        self.hide()
        if callback is not None:
            callback()
