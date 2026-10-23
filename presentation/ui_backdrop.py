"""The backdrop behind the library: the art of the game you are on, blurred to a glow.

It is the window's central widget, so it sits behind the top bar, the Continue playing
card, the chips and the grid alike -- all of which are transparent on the library page --
and, since Phase 33, behind a game's own page, which glows in that game's colours. Since
Phase 35 Stats and Storage carry on with the library's glow, so moving between the three
tabs never changes the colour of the room.

The blur costs nothing. The cover the grid has already drawn is shrunk to a few pixels and
stretched back up, and the result -- shading and vignette included -- is rendered once per
game and window size, so a repaint is one blit of whatever area needs it. Changing game
crossfades between two such renders.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QPointF, QRect, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPixmap, QRadialGradient
from PySide6.QtWidgets import QWidget

from presentation import ui_rules
from presentation import ui_theme

log = logging.getLogger(__name__)


class Backdrop(QWidget):
    """Paints the ambient art, and fades from one game's to the next."""

    def __init__(self, covers, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Backdrop")
        self.covers = covers
        # The size the grid draws covers at, so the cover asked for here is the one the
        # grid has already made and cached -- nothing is decoded twice.
        self.cover_size = (ui_rules.COVER_WIDTH, ui_rules.COVER_HEIGHT)
        self.reduce_animations = ui_rules.REDUCE_ANIMATIONS_DEFAULT
        self.key = ""  # whose art is showing; "" is the plain background
        self._view = None
        self._tiny: dict[tuple, QImage] = {}
        self._current: QPixmap | None = None
        self._previous: QPixmap | None = None  # the render fading out
        self._fade = 1.0

        self._animation = QVariantAnimation(self)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.setDuration(ui_rules.BACKDROP_FADE_MS)
        self._animation.setEasingCurve(ui_theme.easing(ui_rules.BACKDROP_FADE_EASING))
        self._animation.valueChanged.connect(self._faded)
        self._animation.finished.connect(self._fade_done)

    # -- what to show ---------------------------------------------------------------------

    def set_view(self, view, animate: bool = True) -> None:
        """Show this game's glow, or the plain background for None.

        `animate` is off while a page slides in (Phase 34): the page is the motion then, and
        at the TV's 225% a crossfade under a sliding page costs a third of each frame again.
        """
        key = view.key if view is not None else ""
        if key == self.key and _signature(view) == _signature(self._view):
            return
        self._view = view
        self.key = key
        incoming = self._render(view)
        if (not animate or self.reduce_animations or not self.isVisible()
                or self._current is None):
            self._animation.stop()
            self._current, self._previous, self._fade = incoming, None, 1.0
            self.update()
            return
        # A change mid-fade starts from what is on screen at that instant, not from either
        # end of the fade, or the backdrop would jump before it moved. Taken before the
        # animation is stopped, because stopping one can report it finished (Phase 17),
        # and that handler clears the outgoing render.
        start_from = self._composite() if self._previous is not None else self._current
        self._animation.stop()
        self._previous, self._current, self._fade = start_from, incoming, 0.0
        self._animation.start()

    @property
    def fading(self) -> bool:
        return self._previous is not None

    # -- rendering ------------------------------------------------------------------------

    def _tiny_for(self, view) -> QImage | None:
        """The art reduced to a handful of pixels. Cached per game and cover."""
        cache_key = (view.key, view.cover_source, view.display_name)
        cached = self._tiny.get(cache_key)
        if cached is not None:
            return cached
        width, height = self.cover_size
        cover = self.covers.cover(view, width, height)
        if cover.isNull():
            return None
        image = cover.toImage()
        for step_w, step_h in ui_rules.BACKDROP_TINY:
            image = image.scaled(step_w, step_h, Qt.AspectRatioMode.IgnoreAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
        # The design's colour at 70% (Phase 55): a few dozen pixels, so done one by one.
        image = image.convertToFormat(QImage.Format.Format_ARGB32)
        for y in range(image.height()):
            for x in range(image.width()):
                colour = image.pixelColor(x, y)
                hue, saturation, lightness, alpha = colour.getHslF()
                colour.setHslF(max(0.0, hue), saturation * ui_rules.BACKDROP_SATURATION, lightness, alpha)
                image.setPixelColor(x, y, colour)
        self._tiny[cache_key] = image
        return image

    def _render(self, view) -> QPixmap:
        """The whole backdrop at the current size: plain colour, art, shading, vignette."""
        width, height = max(1, self.width()), max(1, self.height())
        pixmap = QPixmap(width, height)
        pixmap.fill(QColor(ui_rules.COLOR_BACKGROUND))
        tiny = self._tiny_for(view) if view is not None else None
        if tiny is None:
            return pixmap

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.setOpacity(ui_rules.BACKDROP_STRENGTH)
        painter.drawImage(QRect(0, 0, width, height), tiny)
        painter.setOpacity(1.0)

        dark = QColor(ui_rules.COLOR_BACKGROUND)
        shade = QLinearGradient(0, 0, 0, height)
        for stop, alpha in ui_rules.BACKDROP_SHADE:
            dark.setAlpha(alpha)
            shade.setColorAt(stop, dark)
        painter.fillRect(0, 0, width, height, shade)

        # In the ground colour since Phase 55, like the shading: no black anywhere.
        edge = QColor(ui_rules.COLOR_BACKGROUND)
        vignette = QRadialGradient(QPointF(width * 0.5, height * 0.35), width * 0.8)
        edge.setAlpha(0)
        vignette.setColorAt(0.6, QColor(edge))
        edge.setAlpha(ui_rules.BACKDROP_VIGNETTE_ALPHA)
        vignette.setColorAt(1.0, QColor(edge))
        painter.fillRect(0, 0, width, height, vignette)
        painter.end()
        return pixmap

    def _composite(self) -> QPixmap:
        """What is on screen right now, mid-fade, as one pixmap."""
        pixmap = QPixmap(self._current.size())
        painter = QPainter(pixmap)
        painter.drawPixmap(0, 0, self._previous)
        painter.setOpacity(self._fade)
        painter.drawPixmap(0, 0, self._current)
        painter.end()
        return pixmap

    # -- painting -------------------------------------------------------------------------

    def _ensure_current(self) -> None:
        if self._current is None or self._current.size() != self.size():
            # A resize: redraw at the new size, and drop a fade in progress rather than
            # stretch a render made for a different window.
            self._animation.stop()
            self._current, self._previous, self._fade = self._render(self._view), None, 1.0

    def paintEvent(self, event) -> None:
        self._ensure_current()
        painter = QPainter(self)
        area = event.rect()
        if self._previous is not None:
            painter.drawPixmap(area, self._previous, area)
            painter.setOpacity(self._fade)
        painter.drawPixmap(area, self._current, area)

    def paint_onto(self, painter: QPainter, area: QRect) -> None:
        """Paint what the backdrop shows over `area` (its own coordinates) at the origin.

        For an overlay that covers part of the window and must look, underneath whatever
        it draws, exactly like the backdrop it hides -- the page transition in ui_motion.
        """
        self._ensure_current()
        target = QRect(0, 0, area.width(), area.height())
        if self._previous is not None:
            painter.drawPixmap(target, self._previous, area)
            painter.setOpacity(self._fade)
        painter.drawPixmap(target, self._current, area)
        painter.setOpacity(1.0)

    def _faded(self, value) -> None:
        self._fade = float(value)
        self.update()

    def _fade_done(self) -> None:
        self._previous = None
        self._fade = 1.0
        self.update()


def _signature(view) -> tuple:
    """What the backdrop depends on, so new art for the same game is noticed."""
    return (view.key, view.cover_source, view.display_name) if view is not None else ()


def stylesheet(scale: float) -> str:
    """Everything between the backdrop and the tiles, made see-through.

    The blanket `QWidget { background }` rule paints every plain widget, label and frame
    in the background colour, which is right everywhere else and would hide the backdrop
    here behind a stack of opaque rectangles.
    """
    return """
    QStackedWidget#Pages { background: transparent; }
    QWidget#LibraryPage QLabel, QWidget#ChipsBar { background: transparent; }
    QListWidget#Grid { background: transparent; }
    QScrollArea#DetailScroll { background: transparent; border: none; }
    QWidget#DetailViewport, QWidget#DetailContent, QWidget#DetailBody, QWidget#Clear {
        background: transparent;
    }
    QWidget#DetailPage QLabel { background: transparent; }
    QScrollArea#StatsScroll { background: transparent; border: none; }
    QWidget#StatsViewport { background: transparent; }
    QWidget#StatsPage QLabel, QWidget#StoragePage QLabel { background: transparent; }
    QScrollArea#ReportsScroll { background: transparent; border: none; }
    QWidget#ReportsViewport { background: transparent; }
    QWidget#ReportsPage QLabel { background: transparent; }
    QWidget#WishlistPage QLabel { background: transparent; }
    QListWidget#WishlistList { background: transparent; border: none; }
    """
