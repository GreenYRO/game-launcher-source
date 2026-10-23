"""Producing the artwork the window draws: portrait covers and wide banners.

Covers are cropped to fill a fixed 2:3 tile rather than letterboxed inside it. That is a
deliberate change from the old square-canvas behaviour: the reason that existed was to stop
rows of mixed-shape icons sitting at different heights, and identical tall tiles solve the
same problem without leaving empty space around every image.

Corners are left square here and clipped by whoever draws the pixmap, so rounding stays
crisp when a tile is scaled up on hover.
"""

from __future__ import annotations

import logging
import os

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPixmap,
    QTextOption,
)

from shared import rules
from presentation import ui_rules
from presentation import ui_theme

log = logging.getLogger(__name__)


def is_image(path: str) -> bool:
    return bool(path) and os.path.splitext(path)[1].casefold() in rules.ARTWORK_EXTENSIONS


class CoverFactory:
    """Builds and caches cover and banner pixmaps."""

    def __init__(self, icon_loader) -> None:
        self.icons = icon_loader
        self._covers: dict[tuple, QPixmap] = {}
        self._banners: dict[tuple, QPixmap] = {}
        # The screen's density (Phase 35). Every picture is made at width x height of these
        # *device* pixels and tagged with it, so on the TV at 225% a cover is drawn one to
        # one instead of being made at a fifth of the pixels and stretched -- which is what
        # left covers soft there. The window sets it, and clears the caches when it changes.
        self.ratio = 1.0

    def clear(self) -> None:
        self._covers.clear()
        self._banners.clear()

    # -- covers ---------------------------------------------------------------------------

    def _device(self, width: int, height: int) -> tuple[int, int]:
        return max(1, round(width * self.ratio)), max(1, round(height * self.ratio))

    def _tag(self, pixmap: QPixmap) -> QPixmap:
        if not pixmap.isNull():
            pixmap.setDevicePixelRatio(self.ratio)
        return pixmap

    def cover(self, view, width: int, height: int, with_name: bool = True) -> QPixmap:
        """A cover for the tile. `with_name` is off where a title already sits beside it.

        `width` and `height` are the size it is drawn at; it is made at the screen's density.
        """
        key = (view.key, view.cover_source, view.display_name, width, height, with_name, self.ratio)
        cached = self._covers.get(key)
        if cached is not None:
            return cached
        width, height = self._device(width, height)

        source = view.cover_source
        pixmap = _load(source) if is_image(source) else None
        if pixmap is None:
            result = self._placeholder(view, width, height, with_name)
        elif _is_portrait(pixmap):
            result = _crop_to_fill(pixmap, width, height)
        else:
            # Landscape art cropped to 2:3 loses most of itself; show it whole instead.
            result = self._fit_on_panel(view, pixmap, width, height)

        self._covers[key] = self._tag(result)
        return result

    def _panel(self, view, width: int, height: int) -> tuple[QPixmap, QPainter]:
        """A blank accent panel plus an open painter, shared by both generated looks."""
        accent = ui_theme.accent_for(view.display_name)
        pixmap = QPixmap(width, height)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        gradient = QLinearGradient(0, 0, 0, height)
        gradient.setColorAt(0.0, accent)
        gradient.setColorAt(1.0, ui_theme.darken(accent, ui_rules.PLACEHOLDER_GRADIENT_DARKEN))
        painter.fillRect(0, 0, width, height, QBrush(gradient))
        return pixmap, painter

    def _plain_banner(self, view, width: int, height: int) -> QPixmap:
        """A calm accent wash, for a game with no artwork of any kind."""
        pixmap, painter = self._panel(view, width, height)
        painter.fillRect(
            0, 0, width, height, QColor(0, 0, 0, int(255 * ui_rules.BANNER_FROM_COVER_DARKEN))
        )
        painter.end()
        return pixmap

    def _fit_on_panel(self, view, source: QPixmap, width: int, height: int) -> QPixmap:
        """Whole image, scaled to fit, over a backdrop built from the same art.

        Transparent artwork (a logo PNG) keeps the flat accent panel instead -- blurring
        something that is mostly nothing produces a backdrop of mostly nothing.
        """
        if ui_rules.COVER_FIT_BACKDROP and not source.hasAlphaChannel():
            pixmap = _soften(
                source,
                width,
                height,
                ui_rules.COVER_FIT_BACKDROP_BLUR_DIVISOR,
                ui_rules.COVER_FIT_BACKDROP_DARKEN,
            )
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        else:
            pixmap, painter = self._panel(view, width, height)

        inset = int(min(width, height) * ui_rules.COVER_FIT_MARGIN)
        fitted = source.scaled(
            max(1, width - inset * 2),
            max(1, height - inset * 2),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        painter.drawPixmap(
            QPoint((width - fitted.width()) // 2, (height - fitted.height()) // 2), fitted
        )
        painter.end()
        return pixmap

    def _placeholder(self, view, width: int, height: int, with_name: bool = True) -> QPixmap:
        """A designed cover for a game with no art: accent wash, its icon, its name.

        `with_name` is off when this is only going to be blurred into a banner -- otherwise
        the name appears twice on the detail page, once smeared and once sharp.
        """
        pixmap, painter = self._panel(view, width, height)

        icon_size = max(16, int(width * ui_rules.PLACEHOLDER_ICON_FRACTION))
        icon = self.icons.icon(view.icon_path) if view.icon_path else None
        if icon is not None and not icon.isNull():
            glyph = icon.pixmap(QSize(icon_size, icon_size))
            if not glyph.isNull():
                centre = 0.30 if with_name else 0.5
                painter.drawPixmap(
                    QPoint(
                        (width - glyph.width()) // 2,
                        int(height * centre) - glyph.height() // 2,
                    ),
                    glyph,
                )

        if not with_name:
            painter.end()
            return pixmap

        margin = ui_rules.PLACEHOLDER_NAME_MARGIN
        text_rect = QRect(margin, int(height * 0.46), width - margin * 2, int(height * 0.46))
        font = QFont(painter.font())
        font.setPointSizeF(max(8.0, width / 15.0))
        font.setWeight(QFont.Weight(ui_rules.HEADING_WEIGHT))
        painter.setFont(font)
        painter.setPen(QColor(255, 255, 255, 235))
        options = QTextOption(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        options.setWrapMode(QTextOption.WrapMode.WordWrap)
        painter.drawText(text_rect, view.display_name, options)

        painter.end()
        return pixmap

    # -- banners --------------------------------------------------------------------------

    def image(self, path: str, width: int, height: int, anchor_y: float = 0.5) -> QPixmap:
        """Any image file, cropped to fill a box. Cached, for the cycling banner."""
        key = ("file", path, width, height, self.ratio, anchor_y)
        cached = self._banners.get(key)
        if cached is not None:
            return cached
        pixmap = _load(path) if is_image(path) else None
        width, height = self._device(width, height)
        result = _crop_to_fill(pixmap, width, height, anchor_y) if pixmap is not None else QPixmap()
        self._banners[key] = self._tag(result)
        return result

    def banner(self, view, width: int, height: int, anchor_y: float = 0.5) -> QPixmap:
        """The game's wide art cropped to fill a box, `anchor_y` of the way down; else its
        cover blurred into a backdrop; else its accent wash."""
        key = (view.key, view.banner_source, view.cover_source, width, height, self.ratio, anchor_y)
        cached = self._banners.get(key)
        if cached is not None:
            return cached
        width, height = self._device(width, height)

        source = view.banner_source
        pixmap = _load(source) if is_image(source) else None
        if pixmap is not None:
            result = _crop_to_fill(pixmap, width, height, anchor_y)
        else:
            cover = _load(view.cover_source) if is_image(view.cover_source) else None
            if cover is not None:
                # No wide art, but real cover art: blur it up into a backdrop.
                result = _banner_from_cover(cover, width, height)
            else:
                # Nothing at all. A blurred exe icon reads as a smudged box, so use the
                # game's own accent wash instead -- it looks deliberate.
                result = self._plain_banner(view, width, height)

        self._banners[key] = self._tag(result)
        return result


# -- pixmap helpers ------------------------------------------------------------------------


def _load(path: str) -> QPixmap | None:
    pixmap = QPixmap(path)
    if pixmap.isNull():
        log.warning("could not load image %s", path)
        return None
    return pixmap


def _is_portrait(pixmap: QPixmap) -> bool:
    """Is this shaped enough like a cover that cropping it will not ruin it?"""
    if pixmap.height() <= 0:
        return False
    return pixmap.width() / pixmap.height() <= ui_rules.COVER_CROP_MAX_ASPECT


def _crop_to_fill(pixmap: QPixmap, width: int, height: int, anchor_y: float = 0.5) -> QPixmap:
    """Scale until the image covers the box, then crop the overflow: from the centre across,
    and `anchor_y` of the way down (0.5 the centre, 0.3 nearer the top, as a hero is framed)."""
    if width <= 0 or height <= 0 or pixmap.isNull():
        return QPixmap()
    scaled = pixmap.scaled(
        width,
        height,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    x = max(0, (scaled.width() - width) // 2)
    y = max(0, round((scaled.height() - height) * anchor_y))
    return scaled.copy(QRect(x, y, width, height))


def _soften(source: QPixmap, width: int, height: int, divisor: int, darken: float) -> QPixmap:
    """Fill the box with the image, blurred by a downscale/upscale round trip, then darkened."""
    if source.isNull():
        canvas = QPixmap(max(1, width), max(1, height))
        canvas.fill(QColor(ui_rules.COLOR_SURFACE))
        return canvas

    step = max(2, divisor)
    tiny = source.scaled(
        max(1, width // step),
        max(1, height // step),
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    softened = tiny.scaled(
        width,
        height,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    result = _crop_to_fill(softened, width, height)

    painter = QPainter(result)
    painter.fillRect(result.rect(), QColor(0, 0, 0, int(255 * darken)))
    painter.end()
    return result


def _banner_from_cover(cover: QPixmap, width: int, height: int) -> QPixmap:
    """Fake a wide banner out of a tall cover: fill, soften, darken."""
    return _soften(
        cover,
        width,
        height,
        ui_rules.BANNER_FROM_COVER_BLUR_DIVISOR,
        ui_rules.BANNER_FROM_COVER_DARKEN,
    )
