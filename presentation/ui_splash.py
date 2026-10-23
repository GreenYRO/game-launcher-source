"""Starting... (Phase 99): from Play until the game is up, the launcher says so instead of looking frozen.

An overlay over the whole window, drawn Phase 34's way -- one picture made when it begins, never a live page
animated: the game's hero (or its cover on the accent's wash when it has none) under the ground's scrim, the
cover, "STARTING" in the accent, the game's name, three dots that take turns and a line saying what it waits
for, and a quiet "Esc to go back" ("B" on the TV). The window ends it -- `MainWindow.end_starting` -- when the
game takes the screen, the tracker sees it close straight away, the watcher sees it running (a Steam game),
LAUNCH_SPLASH_MAX_S passes, or Escape, B or a click asks; a launch that fails ends it before its dialog.
"Reduce animations": no fade and no moving dots, the picture plain.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from presentation import ui_icons
from presentation import ui_rules

log = logging.getLogger(__name__)

EYEBROW = "STARTING"
WAITING = "Waiting for the game to open its window"
HINT_DESK = "Press Esc to go back"
HINT_TV = "Press B to go back"


class LaunchSplash(QWidget):
    """The overlay. `begin(...)` shows it; `end()` takes it away; `dismissed` says the user asked (Esc, B, a click)."""

    dismissed = Signal(str)  # "escape" or "click"

    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.setObjectName("LaunchSplash")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.key: str | None = None
        self.name = ""
        self.scale = 1.0
        self.tv = False
        self.reduce = False
        self._art: QPixmap | None = None
        self._cover: QPixmap | None = None
        self._picture: QPixmap | None = None
        self._opacity = 1.0
        self._lit = 0
        self._dots = QTimer(self)
        self._dots.setInterval(ui_rules.LAUNCH_SPLASH_DOT_MS)
        self._dots.timeout.connect(self._step_dots)
        self._fade = QVariantAnimation(self)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.valueChanged.connect(self._faded)
        self.hide()

    @property
    def showing(self) -> bool:
        return not self.isHidden()

    def begin(self, key: str, name: str, art: QPixmap | None, cover: QPixmap | None, scale: float, tv: bool,
              reduce: bool) -> None:
        self.key, self.name, self.scale, self.tv, self.reduce = key, name, scale, tv, reduce
        self._art, self._cover = art, cover
        self.setGeometry(self.parentWidget().rect())
        self._compose()
        self._lit = 0
        self.show()
        self.raise_()
        self.setFocus(Qt.FocusReason.OtherFocusReason)
        if reduce:
            self._opacity = 1.0
        else:
            self._opacity = 0.0
            self._fade.setDuration(ui_rules.LAUNCH_SPLASH_FADE_MS)
            self._fade.start()
            self._dots.start()
        self.update()

    def end(self) -> None:
        self._dots.stop()
        self._fade.stop()
        self.key = None
        self.hide()

    # -- the picture --------------------------------------------------------------------------------------

    def _s(self, value: float) -> float:
        return value * self.scale

    def _compose(self) -> None:
        """Everything that does not move, once: the art, the scrim, the cover and the words."""
        w, h = max(1, self.width()), max(1, self.height())
        ratio = self.devicePixelRatioF() or 1.0
        picture = QPixmap(round(w * ratio), round(h * ratio))
        picture.setDevicePixelRatio(ratio)
        picture.fill(QColor(ui_rules.COLOR_BACKGROUND))
        p = QPainter(picture)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        if self._art is not None and not self._art.isNull():
            p.drawPixmap(QRectF(0, 0, w, h), self._art, QRectF(self._art.rect()))
        else:
            # No wide art of its own: the accent's wash, its darkest steps, under the cover.
            wash = QLinearGradient(0, 0, w, h)
            wash.setColorAt(0.0, QColor(ui_rules.COLOR_ACCENT_800))
            wash.setColorAt(1.0, QColor(ui_rules.COLOR_BACKGROUND))
            p.fillRect(QRectF(0, 0, w, h), wash)
        shade = QLinearGradient(0, 0, 0, h)
        for at, alpha in ui_rules.LAUNCH_SPLASH_SCRIM:
            colour = QColor(ui_rules.COLOR_BACKGROUND)
            colour.setAlpha(alpha)
            shade.setColorAt(at, colour)
        p.fillRect(QRectF(0, 0, w, h), shade)

        cover_w, cover_h = self._s(ui_rules.LAUNCH_SPLASH_COVER[0]), self._s(ui_rules.LAUNCH_SPLASH_COVER[1])
        x0 = self._s(ui_rules.LAUNCH_SPLASH_MARGIN)
        y0 = h - cover_h - self._s(ui_rules.LAUNCH_SPLASH_BOTTOM)
        frame = QRectF(x0, y0, cover_w, cover_h)
        path = QPainterPath()
        radius = self._s(ui_rules.DETAIL_COVER_RADIUS)
        path.addRoundedRect(frame, radius, radius)
        if self._cover is not None and not self._cover.isNull():
            p.save()
            p.setClipPath(path)
            p.drawPixmap(frame, self._cover, QRectF(self._cover.rect()))
            p.restore()
        p.setPen(QPen(QColor(ui_rules.COLOR_COVER_EDGE), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)

        tx = x0 + cover_w + self._s(ui_rules.LAUNCH_SPLASH_TEXT_GAP)
        eyebrow = self._font(ui_icons.body_family(), ui_rules.LAUNCH_SPLASH_EYEBROW_PX, QFont.Weight.DemiBold)
        eyebrow.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, self._s(ui_rules.LAUNCH_SPLASH_EYEBROW_TRACKING))
        p.setFont(eyebrow)
        p.setPen(QColor(ui_rules.COLOR_ACCENT))
        self._eyebrow_y = y0 + cover_h * 0.25
        p.drawText(QPointF(tx, self._eyebrow_y), EYEBROW)
        title = self._font(ui_icons.display_family(), ui_rules.LAUNCH_SPLASH_TITLE_PX, QFont.Weight.DemiBold)
        p.setFont(title)
        p.setPen(QColor(ui_rules.COLOR_TEXT))
        title_box = QRectF(tx, self._eyebrow_y + self._s(10), w - tx - x0, self._s(ui_rules.LAUNCH_SPLASH_TITLE_PX * 2.6))
        p.drawText(title_box, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap),
                   self.name)
        lines = max(1, round(p.boundingRect(title_box, int(Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap),
                                            self.name).height() / (self._s(ui_rules.LAUNCH_SPLASH_TITLE_PX) * 1.2)))
        self._dots_at = QPointF(tx, self._eyebrow_y + self._s(10) + lines * self._s(ui_rules.LAUNCH_SPLASH_TITLE_PX) * 1.25
                                + self._s(ui_rules.LAUNCH_SPLASH_DOTS_BELOW))
        body = self._font(ui_icons.body_family(), ui_rules.LAUNCH_SPLASH_LINE_PX)
        p.setFont(body)
        p.setPen(QColor(ui_rules.COLOR_TEXT_SOFT))
        words_x = tx + 3 * self._s(ui_rules.LAUNCH_SPLASH_DOT_GAP) + self._s(12)
        p.drawText(QPointF(words_x, self._dots_at.y() + self._s(ui_rules.LAUNCH_SPLASH_LINE_PX) * 0.35), WAITING)
        hint = self._font(ui_icons.body_family(), ui_rules.LAUNCH_SPLASH_HINT_PX)
        p.setFont(hint)
        p.setPen(QColor(ui_rules.COLOR_TEXT_FAINT))
        p.drawText(QRectF(0, h - self._s(ui_rules.LAUNCH_SPLASH_HINT_BOTTOM), w, self._s(24)),
                   int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop), HINT_TV if self.tv else HINT_DESK)
        p.end()
        self._picture = picture

    def _font(self, family: str, px: float, weight=None) -> QFont:
        font = QFont(family)
        font.setPixelSize(max(8, round(self._s(px))))
        if weight is not None:
            font.setWeight(weight)
        return font

    # -- motion -------------------------------------------------------------------------------------------

    def _step_dots(self) -> None:
        self._lit = (self._lit + 1) % 3
        r = self._s(ui_rules.LAUNCH_SPLASH_DOT_PX) * 2
        self.update(round(self._dots_at.x() - r), round(self._dots_at.y() - r),
                    round(3 * self._s(ui_rules.LAUNCH_SPLASH_DOT_GAP) + 2 * r), round(2 * r))

    def _faded(self, value) -> None:
        self._opacity = float(value)
        self.update()

    # -- painting and answering ---------------------------------------------------------------------------

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.showing:
            self._compose()

    def paintEvent(self, event) -> None:
        if self._picture is None:
            return
        p = QPainter(self)
        p.setOpacity(self._opacity)
        p.drawPixmap(0, 0, self._picture)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(Qt.PenStyle.NoPen)
        r = self._s(ui_rules.LAUNCH_SPLASH_DOT_PX)
        for i in range(3):
            lit = (i == self._lit) and not self.reduce
            p.setBrush(QColor(ui_rules.COLOR_ACCENT if lit or (self.reduce and i == 1) else ui_rules.COLOR_TEXT_FAINT))
            p.drawEllipse(QPointF(self._dots_at.x() + r + i * self._s(ui_rules.LAUNCH_SPLASH_DOT_GAP), self._dots_at.y()), r, r)

    def mousePressEvent(self, event) -> None:
        self.dismissed.emit("click")

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.dismissed.emit("escape")
            return
        super().keyPressEvent(event)
