"""Getting a usable tile icon out of a Windows executable.

QFileIconProvider hands back the icon embedded in the binary, which is what we want, but
the sizes it advertises cannot be taken at face value. Windows will happily report a
256x256 variant for an exe whose largest real icon is 48x48, and deliver it as a 256 canvas
with the small image sitting in the top-left corner. Scaling that to tile size renders a
speck. So the largest advertised size is only used once its content is shown to fill it.
"""

from __future__ import annotations

import logging
import os

from PySide6.QtCore import QFileInfo, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QFileIconProvider

log = logging.getLogger(__name__)

ALPHA_THRESHOLD = 8
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".bmp", ".webp")

# Points sampled to decide whether a canvas is really filled, as fractions of width and
# height. All sit outside the top-left corner where Windows parks a padded small icon.
PROBE_POINTS = ((0.60, 0.50), (0.50, 0.60), (0.66, 0.66), (0.60, 0.40), (0.40, 0.60))


class IconLoader:
    def __init__(self, size: QSize) -> None:
        self.size = size
        self.provider = QFileIconProvider()
        self._cache: dict[str, QIcon] = {}

    def icon(self, path: str) -> QIcon:
        cached = self._cache.get(path)
        if cached is not None:
            return cached

        # Steam entries point at cover art, not an executable. Asking the shell for the
        # icon of a .jpg returns the generic "JPEG file" glyph, so load the image itself.
        if os.path.splitext(path)[1].casefold() in IMAGE_EXTENSIONS:
            icon = self._image_icon(path)
            if icon is not None:
                self._cache[path] = icon
                return icon

        base = self.provider.icon(QFileInfo(path))
        pixmap = self._best_pixmap(base)
        if pixmap.isNull():
            log.debug("no usable pixmap for %s; using the shell icon as-is", path)
            icon = base
        else:
            icon = QIcon(self._fit(pixmap))

        self._cache[path] = icon
        return icon

    def _image_icon(self, path: str) -> QIcon | None:
        pixmap = QPixmap(path)
        if pixmap.isNull():
            log.warning("could not load artwork %s; falling back to the shell icon", path)
            return None
        return QIcon(self._fit(pixmap))

    def _fit(self, pixmap: QPixmap) -> QPixmap:
        """Scale to fit, then centre on a square canvas.

        Cover art comes in portrait (600x900 capsules), landscape (460x215 headers) and
        square (exe icons). Without a common canvas the tiles in a row start at different
        heights and the grid looks broken.
        """
        scaled = pixmap.scaled(
            self.size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        if scaled.size() == self.size:
            return scaled
        canvas = QPixmap(self.size)
        canvas.fill(Qt.GlobalColor.transparent)
        painter = QPainter(canvas)
        painter.drawPixmap(
            (self.size.width() - scaled.width()) // 2,
            (self.size.height() - scaled.height()) // 2,
            scaled,
        )
        painter.end()
        return canvas

    def clear(self) -> None:
        self._cache.clear()

    def _best_pixmap(self, base: QIcon) -> QPixmap:
        """Largest advertised size whose content actually fills the canvas."""
        sizes = sorted(base.availableSizes(), key=lambda s: s.width(), reverse=True)
        if not sizes:
            return base.pixmap(self.size)

        for size in sizes:
            pixmap = base.pixmap(size)
            if pixmap.isNull():
                continue
            # Judge the pixmap we were handed, never the size we asked for: Qt returns the
            # same cached 256 canvas for a 256, 48 and 32 request alike, and only produces
            # the genuine small bitmap when asked for 16.
            if pixmap.width() <= self.size.width() or _content_fills(pixmap):
                return pixmap
            log.debug("ignoring padded %dpx canvas (asked for %d)", pixmap.width(), size.width())

        return base.pixmap(sizes[-1])


def _content_fills(pixmap: QPixmap) -> bool:
    """Cheap check for a mostly-empty canvas: sample a few points away from the corner."""
    image = pixmap.toImage()
    width, height = image.width(), image.height()
    if width <= 0 or height <= 0:
        return False
    for fraction_x, fraction_y in PROBE_POINTS:
        x = min(width - 1, int(width * fraction_x))
        y = min(height - 1, int(height * fraction_y))
        if image.pixelColor(x, y).alpha() > ALPHA_THRESHOLD:
            return True
    return False
