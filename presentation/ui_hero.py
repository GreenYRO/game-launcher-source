"""The top of a game's page (Phase 33): its art, edge to edge, and the cover laid over it.

The art runs the full width of the page and fades out into the window's backdrop, which on
this page glows in the same game's colours -- so the picture has no frame and no edge, and
the page reads as one surface. What sits on it (the cover, the title, the facts and the
Play row) is laid out by DetailPage; this module draws the picture, cycles it, and draws
the cover with its shadow.

Frame 0 is whatever the banner would otherwise be -- the hero, a custom image, or, for a game
with no wide art of its own, a stand-in: its cover blurred into a backdrop, or its colour.
Screenshots are appended as they finish downloading, so the cycle grows rather than waiting
for a complete set. **A stand-in gives way to the first real image** (Phase 72, reported from
use): a cover chosen by hand was otherwise stretched across the page as its banner too, in
front of the screenshots. The dots that move between them belong to this
picture; moving between *games* is the labelled pair of buttons in the page's top corner,
never a second set of arrows in here (the Phase 11 lesson).
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QEvent, QRect, QRectF, QSize, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QPushButton, QSizePolicy, QToolTip, QWidget

from presentation import ui_icons
from presentation import ui_rules
from presentation import ui_theme

log = logging.getLogger(__name__)


class Banner(QWidget):
    """The picture across the top of a game's page, cycling through its images."""

    def __init__(self, covers, metrics, parent=None) -> None:
        super().__init__(parent)
        self.covers = covers
        self.metrics = metrics
        self.view = None
        self.reduce_animations = False
        self.dots_right = 0  # set by the page, so the dots end on the cards' right edge
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)

        self.frames: list[str] = []  # "" means "whatever covers.banner produces"
        self._stand_in = False  # frame 0 is built from the cover: no wide art of the game's own
        self._replacing = False  # fading from the stand-in to the first image, then dropping it
        self._stand_in_seen = False  # the stand-in has been on screen, so it leaves by a fade
        self.index = 0
        self._next_index = 0
        self._fade = 0.0
        self._hovered = False
        self._active = False
        self._finished: dict[tuple, QPixmap] = {}

        self._dwell = QTimer(self)
        self._dwell.setSingleShot(True)
        self._dwell.timeout.connect(self._advance)
        self._animation = QVariantAnimation(self)
        self._animation.setDuration(ui_rules.BANNER_CYCLE_FADE_MS)
        self._animation.valueChanged.connect(self._on_fade)
        self._animation.finished.connect(self._on_faded)

    def apply_metrics(self, metrics) -> None:
        self.metrics = metrics
        self.update()

    # -- frames -------------------------------------------------------------------------

    def set_view(self, view) -> None:
        # Before the animation is stopped: stopping it ends the fade, and a stand-in still
        # marked as leaving would be dropped from the new game's frames.
        self._replacing = False
        self._stand_in = not view.banner_source
        self._stand_in_seen = False
        self.view = view
        self.frames = [""]
        self.index = 0
        self._next_index = 0
        self._fade = 0.0
        self._finished.clear()
        self._animation.stop()
        self._dwell.stop()
        self.update()
        self._maybe_start()

    def add_frame(self, path: str) -> None:
        """Append a downloaded screenshot to the cycle.

        Refused outright when the user picked this banner by hand: no extra frames means no
        dots, so nothing invites them to cycle away from the image they chose.
        """
        if not self.cycling_allowed:
            return
        if not path or path in self.frames:
            return
        if self._stand_in and self.frames == [""]:
            # The first real image takes the stand-in's place: the cover stays the cover.
            self._stand_in = False
            if self._stand_in_seen and self._active and not self.reduce_animations:
                self.frames.append(path)
                self._replacing = True
                self.show_frame(1)
                return
            self.frames = [path]  # not on screen yet (an image already on disk): no fade
            self.index = self._next_index = 0
            self.update()
            self._maybe_start()
            return
        self.frames.append(path)
        self._maybe_start()
        self.update()

    @property
    def cycling_allowed(self) -> bool:
        """A banner the user chose by hand is theirs; it never gets cycled away."""
        if self.view is None:
            return False
        return not self.view.data.get("banner")

    def set_active(self, active: bool) -> None:
        """The page is (or is not) the one on screen. Off means the timer stops entirely."""
        self._active = active
        if active:
            self._maybe_start()
        else:
            self._dwell.stop()
            self._animation.stop()

    def _maybe_start(self) -> None:
        if (
            self._active
            and not self.reduce_animations
            and self.cycling_allowed
            and len(self.frames) > 1
            and not self._hovered
            and not self._dwell.isActive()
            and self._animation.state() != QVariantAnimation.State.Running
        ):
            self._dwell.start(ui_rules.BANNER_CYCLE_DWELL_MS)

    # -- cycling ------------------------------------------------------------------------

    def _advance(self) -> None:
        if len(self.frames) < 2 or self._hovered or not self._active:
            return
        self.show_frame((self.index + 1) % len(self.frames))

    def show_frame(self, index: int, animate: bool = True) -> None:
        if not self.frames or index == self.index:
            return
        index %= len(self.frames)
        if not animate or self.reduce_animations:
            self.index = index
            self._fade = 0.0
            self.update()
            self._maybe_start()
            return

        # Finished before the fade begins, so the incoming image never pops in half-drawn.
        self._pixmap_for(index)
        self._next_index = index
        self._animation.stop()
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.setEasingCurve(ui_theme.easing(ui_rules.BANNER_CYCLE_EASING))
        self._animation.start()

    def _on_fade(self, value) -> None:
        self._fade = float(value)
        self.update()

    def _on_faded(self) -> None:
        self.index = self._next_index
        if self._replacing:
            self._replacing = False
            self.frames.pop(0)  # the stand-in has faded out; it is not one of the images
            self.index = self._next_index = max(0, self.index - 1)
        self._fade = 0.0
        self.update()
        self._maybe_start()

    # -- the picture ----------------------------------------------------------------------

    def _pixmap_for(self, index: int) -> QPixmap | None:
        """A frame as it is drawn: the art, darker on the left, fading out below.

        Made once per frame and size. The fade is baked in with DestinationIn, so the foot
        of the picture is genuinely transparent and the backdrop shows through it -- a
        fade to a flat colour would leave a seam wherever the backdrop is not that colour.
        """
        if not self.frames or self.view is None:
            return None
        path = self.frames[index % len(self.frames)]
        width, height = max(1, self.width()), max(1, self.height())
        key = (path, self.view.key, self.view.banner_source, self.view.cover_source, width, height,
               self.covers.ratio)
        cached = self._finished.get(key)
        if cached is not None:
            return cached

        anchor = ui_rules.DETAIL_HERO_ANCHOR
        art = (self.covers.image(path, width, height, anchor) if path
               else self.covers.banner(self.view, width, height, anchor))
        # At the screen's density, like the art inside it (Phase 35); drawn in logical units.
        ratio = self.covers.ratio
        pixmap = QPixmap(max(1, round(width * ratio)), max(1, round(height * ratio)))
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        if art is not None and not art.isNull():
            painter.drawPixmap(0, 0, art)
        else:
            painter.fillRect(0, 0, width, height, QColor(ui_rules.COLOR_SURFACE))
        side = QLinearGradient(0, 0, width, 0)
        dark = QColor(ui_rules.COLOR_SCRIM)
        for stop, alpha in ui_rules.DETAIL_HERO_SIDE_SCRIM:
            dark.setAlpha(alpha)
            side.setColorAt(stop, dark)
        painter.fillRect(0, 0, width, height, side)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        fade = QLinearGradient(0, 0, 0, height)
        fade.setColorAt(0.0, QColor(0, 0, 0, 255))
        fade.setColorAt(ui_rules.DETAIL_HERO_FADE_FROM, QColor(0, 0, 0, 255))
        fade.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(0, 0, width, height, fade)
        painter.end()

        if len(self._finished) >= ui_rules.DETAIL_HERO_CACHE:
            self._finished.pop(next(iter(self._finished)))
        self._finished[key] = pixmap
        return pixmap

    # -- interaction ----------------------------------------------------------------------

    def enterEvent(self, event) -> None:
        self._hovered = True
        self._dwell.stop()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self._maybe_start()
        super().leaveEvent(event)

    def _dot_rects(self) -> list[QRect]:
        """Bottom right, level with the Play row, ending on the cards' right edge."""
        if self._replacing:
            return []  # the stand-in leaving is not an image to choose
        count = len(self.frames)
        if count < 2:
            return []
        scale = self.metrics.scale
        size = max(6, round(ui_rules.BANNER_DOT_SIZE * scale))
        gap = max(4, round(ui_rules.BANNER_DOT_SPACING * scale))
        total = count * size + (count - 1) * gap
        right = self.dots_right or round(ui_rules.DETAIL_PAGE_MARGIN * scale)
        x = self.width() - right - total
        middle = (round((ui_rules.DETAIL_HERO_BOTTOM + ui_rules.DETAIL_INFO_FOOT) * scale)
                  + round(ui_rules.DETAIL_ACTION_HEIGHT * scale) // 2)
        y = self.height() - middle - size // 2
        return [QRect(x + i * (size + gap), y, size, size) for i in range(count)]

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            pad = round(ui_rules.BANNER_DOT_HIT_PADDING * self.metrics.scale)
            for index, rect in enumerate(self._dot_rects()):
                if rect.adjusted(-pad, -pad, pad, pad).contains(event.position().toPoint()):
                    self._dwell.stop()
                    self.show_frame(index)
                    return
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:
        if self.view is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        current = self._pixmap_for(self.index)
        if current is not None:
            painter.drawPixmap(0, 0, current)
            if self.frames[self.index % len(self.frames)] == "" and self._stand_in:
                self._stand_in_seen = True
        # The crossfade: the incoming frame over the outgoing one at rising opacity, so
        # there is never a blank moment between them.
        if self._fade > 0.0:
            incoming = self._pixmap_for(self._next_index)
            if incoming is not None:
                painter.setOpacity(self._fade)
                painter.drawPixmap(0, 0, incoming)
                painter.setOpacity(1.0)
        self._paint_dots(painter)

    def _paint_dots(self, painter: QPainter) -> None:
        rects = self._dot_rects()
        if not rects:
            return
        painter.setPen(Qt.PenStyle.NoPen)
        for index, rect in enumerate(rects):
            active = index == (self._next_index if self._fade > 0.5 else self.index)
            colour = QColor(ui_rules.COLOR_TEXT if active else ui_rules.COLOR_TEXT_MUTED)
            colour.setAlpha(255 if active else 120)
            painter.setBrush(colour)
            painter.drawEllipse(rect)


class CoverArt(QWidget):
    """The game's cover beside its title: rounded, edged, with a deep shadow under it.

    The design's large shadow (Phase 57): a 1 px edge in neutral 500 just outside the cover,
    and a soft shadow 40 px wide dropped 16 px. The widget has room for it on the left and
    above; at the foot the room ends at the first card, and on the right at the title --
    by then it has all but faded, and in the design the card and the words cover the rest.
    """

    def __init__(self, covers, metrics, parent=None) -> None:
        super().__init__(parent)
        self.covers = covers
        self.view = None
        # While its twin is flying in from the tile (Phase 34), this one keeps its place in
        # the layout and draws nothing, so the flight lands in an empty slot.
        self.in_flight = False
        self.apply_metrics(metrics)

    def set_in_flight(self, flying: bool) -> None:
        self.in_flight = flying
        self.update()

    @property
    def radius(self) -> float:
        return ui_rules.DETAIL_COVER_RADIUS * self.metrics.scale

    def apply_metrics(self, metrics) -> None:
        self.metrics = metrics
        scale = metrics.scale
        self.cover_width = max(40, round(ui_rules.DETAIL_COVER_WIDTH * scale))
        self.cover_height = self.cover_width * ui_rules.COVER_ASPECT_H // ui_rules.COVER_ASPECT_W
        self.spread = max(4, round(ui_rules.DETAIL_COVER_SHADOW * scale))
        self.drop = round(ui_rules.DETAIL_COVER_SHADOW_DROP * scale)
        self.room_top = max(1, self.spread - self.drop)  # the shadow falls, so less above
        self.room_bottom = round(ui_rules.DETAIL_HERO_BOTTOM * scale)
        # On the right, only the gap to the title: the shadow has all but gone by then, and
        # more room would push the words that much further from the cover.
        self.room_right = min(self.spread, round(ui_rules.DETAIL_COVER_GAP * scale))
        self.setFixedSize(self.spread + self.cover_width + self.room_right,
                          self.room_top + self.cover_height + self.room_bottom)
        self.update()

    def set_view(self, view) -> None:
        self.view = view
        self.update()

    def cover_rect(self) -> QRect:
        return QRect(self.spread, self.room_top, self.cover_width, self.cover_height)

    def paintEvent(self, event) -> None:
        if self.view is None or self.in_flight:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        radius = self.radius
        body = self.cover_rect()
        shadow = ui_theme.soft_edge(body.width(), body.height(), radius, self.spread, "#000000",
                                    ui_rules.DETAIL_COVER_SHADOW_ALPHA)
        painter.drawPixmap(body.x() - self.spread, body.y() - self.spread + self.drop, shadow)
        outline = QPainterPath()
        outline.addRoundedRect(QRectF(body), radius, radius)
        painter.save()
        painter.setClipPath(outline)
        # No name baked into this one: the title is right beside it.
        cover = self.covers.cover(self.view, body.width(), body.height(), with_name=False)
        if not cover.isNull():
            painter.drawPixmap(body, cover)
        else:
            painter.fillRect(body, QColor(ui_rules.COLOR_SURFACE))
        painter.restore()
        painter.setPen(QPen(QColor(ui_rules.COLOR_COVER_EDGE), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(QRectF(body).adjusted(-0.5, -0.5, 0.5, 0.5), radius + 0.5, radius + 0.5)


class PillRow(QWidget):
    """The row of pills under the title, painting nothing (the backdrop shows through, as clear_widget's does).

    A pill lets the mouse through -- it is no button -- so a hover lands on the row, which shows the words of the
    pill under the mouse (Phase 102 extension: where a game's hours came from). The row answers its own hover:
    nothing outside it watches it.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Clear")

    def pill_at(self, pos):
        """The pill shown at `pos`, or None."""
        return next((p for p in self.findChildren(Pill) if not p.isHidden() and p.geometry().contains(pos)), None)

    def event(self, event) -> bool:
        if event.type() == QEvent.Type.ToolTip:
            pill = self.pill_at(event.pos())
            if pill is not None and pill.toolTip():
                QToolTip.showText(event.globalPos(), pill.toolTip(), self)
            else:
                QToolTip.hideText()
                event.ignore()
            return True
        return super().event(event)


class Pill(QPushButton):
    """One fact under the title, with its icon. Shaped like a button, but not one.

    A QPushButton because it can carry an icon beside its words; transparent to the mouse
    and out of the focus chain, because pressing a fact should do nothing and look it.
    """

    def __init__(self, fact: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Pill")
        self.fact = fact  # the label this fact has in gamedetails.metadata
        self.value = ""  # and its value there, for DetailPage.facts()
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.scale = 1.0

    def paintEvent(self, event) -> None:
        # The glass and its hairline, painted round (Phase 99): the stylesheet's ends came out flattened.
        painter = QPainter(self)
        ui_theme.paint_capsule(painter, self.rect(), ui_rules.COLOR_ON_ART_FAINT, ui_rules.COLOR_PILL_EDGE,
                               ui_theme.pill_edge(self.scale))
        painter.end()
        super().paintEvent(event)  # the icon and the words

    def show_fact(self, text: str, value: str, glyph: str, tone: str, scale: float) -> None:
        """`tone` "saved" puts the words in the accent ("Saves copied ..."); "" is neutral."""
        px = max(10, round(ui_rules.DETAIL_PILL_ICON_PX * scale))
        # Qt leaves 4 px between an icon and the words; one space makes the design's 7.
        self.setText(f" {text}")
        self.value = value
        self.setIcon(ui_icons.icon(glyph, ui_rules.COLOR_PILL_ICON, px))
        self.setIconSize(QSize(px, px))
        self.setFixedHeight(max(20, round(ui_rules.DETAIL_PILL_HEIGHT * scale)))
        self.scale = scale
        if self.property("tone") != tone:
            self.setProperty("tone", tone)
            self.style().unpolish(self)
            self.style().polish(self)


class TopFade(QWidget):
    """A dark fade across the top of the game page, under its floating buttons.

    Invisible at the top of the page, where the picture is and the buttons sit on it by
    design; it comes in as the page scrolls and cards start to slide under them.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.strength = 0.0
        self.hide()  # until the page is scrolled -- found by a test, not by eye

    def set_strength(self, strength: float) -> None:
        strength = max(0.0, min(1.0, strength))
        if strength == self.strength:
            return
        self.strength = strength
        self.setVisible(strength > 0.0)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setOpacity(self.strength)
        fade = QLinearGradient(0, 0, 0, self.height())
        dark = QColor(ui_rules.COLOR_SCRIM)
        dark.setAlpha(ui_rules.DETAIL_TOP_FADE_ALPHA)
        fade.setColorAt(0.0, dark)
        dark.setAlpha(0)
        fade.setColorAt(1.0, dark)
        painter.fillRect(self.rect(), fade)
