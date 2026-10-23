"""The screenshot strip on a game's page, and the viewer it opens.

The strip collapses to nothing when a game has no screenshots, which is every entry with no
Steam record -- so an unmatched game's page simply has one fewer block rather than an empty
frame with a caption.

The viewer is reachable and closable without a mouse: arrows or a controller stick to move,
Escape or the controller Back button to leave.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from presentation import ui_rules
from presentation.ui_cards import FlowLayout

log = logging.getLogger(__name__)

BACK_KEYS = (Qt.Key.Key_Escape, Qt.Key.Key_Backspace)
PREV_KEYS = (Qt.Key.Key_Left, Qt.Key.Key_A)
NEXT_KEYS = (Qt.Key.Key_Right, Qt.Key.Key_D)


class Thumbnail(QLabel):
    clicked = Signal(int)

    def __init__(self, index: int, height: int, parent=None) -> None:
        super().__init__(parent)
        self.index = index
        self.setFixedHeight(height)
        self.setMinimumWidth(int(height * 16 / 9))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("Shot")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setText(" ")

    def set_image(self, path: str) -> None:
        pixmap = QPixmap(path)
        if pixmap.isNull():
            log.warning("screenshot %s would not load", path)
            return
        scaled = pixmap.scaledToHeight(
            self.height(), Qt.TransformationMode.SmoothTransformation
        )
        self.setFixedWidth(scaled.width())
        self.setPixmap(scaled)
        self.setText("")

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.index)
        super().mouseReleaseEvent(event)


class ScreenshotStrip(QWidget):
    """The thumbnails, in rows that wrap. Hidden entirely while a game has none.

    Rows that wrap since Phase 33: eight thumbnails in one line are wider than the card
    they sit in on most windows, and a line that cannot wrap either clips or forces the
    whole page wider than the window.
    """

    opened = Signal(int)

    def __init__(self, metrics, parent=None) -> None:
        super().__init__(parent)
        self.metrics = metrics
        self.thumbs: dict[int, Thumbnail] = {}
        self._layout = FlowLayout(self, ui_rules.SCREENSHOT_STRIP_SPACING)
        self.setVisible(False)

    def _thumb_height(self) -> int:
        return max(48, round(ui_rules.SCREENSHOT_THUMB_HEIGHT * self.metrics.scale))

    def reset(self, count: int) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.thumbs.clear()

        if count <= 0:
            self.setVisible(False)
            return

        height = self._thumb_height()
        for index in range(count):
            thumb = Thumbnail(index, height, self)
            thumb.clicked.connect(self.opened)
            self._layout.addWidget(thumb)
            self.thumbs[index] = thumb
        self.setVisible(True)

    def set_image(self, index: int, path: str) -> None:
        thumb = self.thumbs.get(index)
        if thumb is not None:
            thumb.set_image(path)


class ScreenshotViewer(QDialog):
    """One big screenshot with arrows. Escape or Back closes it."""

    def __init__(self, paths: dict, count: int, start: int, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Screenshot")
        self.paths = paths
        self.count = count
        self.index = start
        self.setModal(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.image = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.image.setMinimumSize(QSize(720, 405))

        self.caption = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.caption.setObjectName("Meta")

        previous = QPushButton("‹")
        previous.setObjectName("Nav")
        previous.clicked.connect(lambda: self.step(-1))
        following = QPushButton("›")
        following.setObjectName("Nav")
        following.clicked.connect(lambda: self.step(1))
        close = QPushButton("Close")
        close.clicked.connect(self.accept)

        row = QHBoxLayout()
        row.addWidget(previous)
        row.addStretch(1)
        row.addWidget(self.caption, 3)
        row.addStretch(1)
        row.addWidget(following)
        row.addWidget(close)

        layout = QVBoxLayout(self)
        layout.addWidget(self.image, 1)
        layout.addLayout(row)
        self.show_current()

    def show_current(self) -> None:
        path = self.paths.get(self.index, "")
        pixmap = QPixmap(path) if path else QPixmap()
        if pixmap.isNull():
            self.image.setText("Loading...")
        else:
            self.image.setPixmap(
                pixmap.scaled(
                    self.image.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        self.caption.setText(f"{self.index + 1} of {self.count}")

    def set_image(self, index: int, path: str) -> None:
        self.paths[index] = path
        if index == self.index:
            self.show_current()

    def step(self, direction: int) -> None:
        if self.count:
            self.index = (self.index + direction) % self.count
            self.show_current()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.show_current()

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key in PREV_KEYS:
            self.step(-1)
        elif key in NEXT_KEYS:
            self.step(1)
        elif key in BACK_KEYS:
            self.accept()
        else:
            super().keyPressEvent(event)
            return
        event.accept()


def stylesheet(scale: float) -> str:
    radius = max(3, round(ui_rules.SCREENSHOT_CORNER_RADIUS * scale))
    return f"""
    /* Two names deep, so it outranks the game page's "every label is see-through" rule:
       a thumbnail still loading must show its box. */
    QWidget#DetailPage QLabel#Shot, QLabel#Shot {{
        background: {ui_rules.COLOR_SURFACE};
        border: 1px solid {ui_rules.COLOR_BORDER};
        border-radius: {radius}px;
    }}
    QWidget#DetailPage QLabel#Shot:hover, QLabel#Shot:hover {{ border-color: {ui_rules.COLOR_ACCENT}; }}
    """
