"""The controller's buttons, drawn -- for the TV hint bar (Phase 50).

Until Phase 50 every hint was a text chip saying both families at once ("A / ✕",
"LB·RB / L1·R1"). Now each button is painted the way it looks on the pad in your hands:
an Xbox-layout pad (an 8BitDo Ultimate 2C included) gets A B X Y in their colours, a
DualSense gets ✕ ○ □ △ in theirs, and the bumpers, the two small middle buttons and the
d-pad are drawn as shapes too.

Painted rather than loaded from pictures: sharp at every TV scale and screen density (the
4K TV runs at 225%), no downloads, no image licences, and the colours live in ui_rules
with every other colour. The geometry below is in fractions of the button's height, the
way BatteryGlyph is drawn.
"""

from __future__ import annotations

from PySide6.QtCore import QLineF, QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from presentation import ui_icons
from presentation import ui_rules
from shared import rules

# What a hint's button is. ui_tv names its buttons by what is printed on them; these are
# what gets drawn.
FACE_SOUTH, FACE_EAST, FACE_WEST, FACE_NORTH = "south", "east", "west", "north"
SHOULDERS, VIEW, MENU, DPAD_ACROSS, DPAD_UPDOWN = "shoulders", "view", "menu", "across", "updown"

# Which mark each face button carries in each family, and its colour.
XBOX_FACES = {
    FACE_SOUTH: ("A", ui_rules.COLOR_PAD_A),
    FACE_EAST: ("B", ui_rules.COLOR_PAD_B),
    FACE_WEST: ("X", ui_rules.COLOR_PAD_X),
    FACE_NORTH: ("Y", ui_rules.COLOR_PAD_Y),
}
PLAYSTATION_FACES = {
    FACE_SOUTH: ("cross", ui_rules.COLOR_PAD_CROSS),
    FACE_EAST: ("circle", ui_rules.COLOR_PAD_CIRCLE),
    FACE_WEST: ("square", ui_rules.COLOR_PAD_SQUARE),
    FACE_NORTH: ("triangle", ui_rules.COLOR_PAD_TRIANGLE),
}
# The words a person would use for each button, per family -- the glyph's tooltip, and what
# a screen reader is told.
NAMES = {
    rules.PAD_XBOX: {FACE_SOUTH: "A", FACE_EAST: "B", FACE_WEST: "X", FACE_NORTH: "Y",
                     SHOULDERS: "LB / RB", VIEW: "View", MENU: "Menu",
                     DPAD_ACROSS: "D-pad left / right", DPAD_UPDOWN: "D-pad up / down"},
    rules.PAD_PLAYSTATION: {FACE_SOUTH: "Cross", FACE_EAST: "Circle", FACE_WEST: "Square",
                            FACE_NORTH: "Triangle", SHOULDERS: "L1 / R1", VIEW: "Create",
                            MENU: "Options", DPAD_ACROSS: "D-pad left / right",
                            DPAD_UPDOWN: "D-pad up / down"},
}
# Width as a multiple of height: the bumpers are a pair side by side; the rest are square.
ASPECT = {SHOULDERS: 2.6}


def family_or_default(family: str) -> str:
    return family if family in NAMES else rules.PAD_XBOX


class ButtonGlyph(QWidget):
    """One button, drawn as it looks on the pad -- or a pair, for the bumpers."""

    def __init__(self, button: str, family: str, height: int, parent=None) -> None:
        super().__init__(parent)
        self.button = button
        self.family = family_or_default(family)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setObjectName("PadButton")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.set_height(height)
        self.setToolTip(NAMES[self.family][button])
        self.setAccessibleName(NAMES[self.family][button])

    def set_height(self, height: int) -> None:
        self.glyph_height = max(8, height)
        self.setFixedSize(self.sizeHint())
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(round(self.glyph_height * ASPECT.get(self.button, 1.0)), self.glyph_height)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        h = float(self.glyph_height)
        if self.button in (FACE_SOUTH, FACE_EAST, FACE_WEST, FACE_NORTH):
            self._face(painter, h)
        elif self.button == SHOULDERS:
            self._shoulders(painter, h)
        elif self.button == VIEW:
            self._view(painter, h)
        elif self.button == MENU:
            self._menu(painter, h)
        else:
            self._dpad(painter, h)
        painter.end()

    # -- the parts ----------------------------------------------------------------------

    def _body(self, painter: QPainter, rect: QRectF, radius: float) -> None:
        painter.setPen(QPen(QColor(ui_rules.COLOR_PAD_EDGE), max(1.0, rect.height() * 0.045)))
        painter.setBrush(QColor(ui_rules.COLOR_PAD_BODY))
        painter.drawRoundedRect(rect, radius, radius)

    def _face(self, painter: QPainter, h: float) -> None:
        edge = max(1.0, h * 0.045)
        disc = QRectF(edge / 2, edge / 2, h - edge, h - edge)
        self._body(painter, disc, disc.width() / 2)
        if self.family == rules.PAD_PLAYSTATION:
            shape, colour = PLAYSTATION_FACES[self.button]
            self._shape(painter, shape, QColor(colour), h)
        else:
            letter, colour = XBOX_FACES[self.button]
            self._letter(painter, letter, QColor(colour), QRectF(0, 0, h, h), h * 0.52)

    def _letter(self, painter: QPainter, text: str, colour: QColor, rect: QRectF, px: float) -> None:
        font = QFont(ui_icons.body_family())
        font.setPixelSize(max(6, round(px)))
        font.setWeight(QFont.Weight(ui_rules.LABEL_WEIGHT))
        painter.setFont(font)
        painter.setPen(colour)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)

    def _shape(self, painter: QPainter, shape: str, colour: QColor, h: float) -> None:
        pen = QPen(colour, max(1.4, h * 0.085))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        c, r = h / 2, h * 0.2
        if shape == "cross":
            painter.drawLine(QPointF(c - r, c - r), QPointF(c + r, c + r))
            painter.drawLine(QPointF(c - r, c + r), QPointF(c + r, c - r))
        elif shape == "circle":
            painter.drawEllipse(QPointF(c, c), r * 1.05, r * 1.05)
        elif shape == "square":
            painter.drawRect(QRectF(c - r * 0.95, c - r * 0.95, r * 1.9, r * 1.9))
        else:  # triangle, pointing up, sitting a touch low so it looks centred
            path = QPainterPath()
            path.moveTo(c, c - r * 1.15)
            path.lineTo(c + r * 1.15, c + r * 0.85)
            path.lineTo(c - r * 1.15, c + r * 0.85)
            path.closeSubpath()
            painter.drawPath(path)

    def _shoulders(self, painter: QPainter, h: float) -> None:
        left, right = ("L1", "R1") if self.family == rules.PAD_PLAYSTATION else ("LB", "RB")
        gap = h * 0.16
        width = (self.width() - gap) / 2
        bump = QRectF(0, h * 0.2, width, h * 0.6)
        for index, text in enumerate((left, right)):
            rect = bump.translated(index * (width + gap), 0).adjusted(0.5, 0.5, -0.5, -0.5)
            self._body(painter, rect, rect.height() * 0.42)
            self._letter(painter, text, QColor(ui_rules.COLOR_PAD_MARK), rect, h * 0.34)

    def _small_button(self, painter: QPainter, h: float) -> QRectF:
        """The two small middle buttons: round on an Xbox pad, an upright pill on a DualSense."""
        if self.family == rules.PAD_PLAYSTATION:
            rect = QRectF(h * 0.3, h * 0.08, h * 0.4, h * 0.84)
            self._body(painter, rect, rect.width() / 2)
        else:
            edge = max(1.0, h * 0.045)
            rect = QRectF(h * 0.1, h * 0.1, h * 0.8, h * 0.8).adjusted(edge / 2, edge / 2, -edge / 2, -edge / 2)
            self._body(painter, rect, rect.width() / 2)
        return rect

    def _mark_pen(self, h: float) -> QPen:
        pen = QPen(QColor(ui_rules.COLOR_PAD_MARK), max(1.0, h * 0.06))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        return pen

    def _view(self, painter: QPainter, h: float) -> None:
        body = self._small_button(painter, h)
        painter.setPen(self._mark_pen(h))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        c = body.center()
        if self.family == rules.PAD_PLAYSTATION:
            # Create: three short rays fanning up from one point, as printed beside the touchpad.
            origin = QPointF(c.x(), c.y() + h * 0.17)
            for angle in (-26.0, 0.0, 26.0):
                ray = QLineF.fromPolar(h * 0.3, 90.0 + angle)
                ray.translate(origin)
                start = ray.pointAt(0.18)
                painter.drawLine(start, ray.p2())
        else:
            # View: two overlapping windows.
            s = h * 0.19
            painter.drawRoundedRect(QRectF(c.x() - s * 1.05, c.y() - s * 0.75, s * 1.5, s * 1.1), 1, 1)
            painter.drawRoundedRect(QRectF(c.x() - s * 0.45, c.y() - s * 0.35, s * 1.5, s * 1.1), 1, 1)

    def _menu(self, painter: QPainter, h: float) -> None:
        body = self._small_button(painter, h)
        painter.setPen(self._mark_pen(h))
        c = body.center()
        half = h * (0.1 if self.family == rules.PAD_PLAYSTATION else 0.17)
        step = h * 0.11
        for dy in (-step, 0.0, step):
            painter.drawLine(QPointF(c.x() - half, c.y() + dy), QPointF(c.x() + half, c.y() + dy))

    def _dpad(self, painter: QPainter, h: float) -> None:
        arm = h * 0.34
        c = h / 2
        meant = {"left", "right"} if self.button == DPAD_ACROSS else {"up", "down"}
        arms = {
            "up": QRectF(c - arm / 2, 0.5, arm, c - arm / 2),
            "down": QRectF(c - arm / 2, c + arm / 2, arm, c - arm / 2 - 0.5),
            "left": QRectF(0.5, c - arm / 2, c - arm / 2, arm),
            "right": QRectF(c + arm / 2, c - arm / 2, c - arm / 2 - 0.5, arm),
        }
        cross = QPainterPath()
        cross.setFillRule(Qt.FillRule.WindingFill)
        cross.addRoundedRect(QRectF(c - arm / 2, 0.5, arm, h - 1), arm * 0.22, arm * 0.22)
        cross.addRoundedRect(QRectF(0.5, c - arm / 2, h - 1, arm), arm * 0.22, arm * 0.22)
        painter.setPen(QPen(QColor(ui_rules.COLOR_PAD_EDGE), max(1.0, h * 0.045)))
        painter.setBrush(QColor(ui_rules.COLOR_PAD_BODY))
        painter.drawPath(cross.simplified())
        # An arrowhead in each arm that is meant, pointing out along it; the others stay plain.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(ui_rules.COLOR_PAD_MARK))
        for name in meant:
            rect = arms[name]
            depth, half = rect.width() if name in ("left", "right") else rect.height(), arm * 0.4
            tip_gap, base_gap = depth * 0.12, depth * 0.8
            outward = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}[name]
            edge = {"up": rect.top(), "down": rect.bottom(), "left": rect.left(), "right": rect.right()}[name]
            if outward[0]:
                tip = QPointF(edge - outward[0] * tip_gap, c)
                base_x = edge - outward[0] * base_gap
                points = [tip, QPointF(base_x, c - half), QPointF(base_x, c + half)]
            else:
                tip = QPointF(c, edge - outward[1] * tip_gap)
                base_y = edge - outward[1] * base_gap
                points = [tip, QPointF(c - half, base_y), QPointF(c + half, base_y)]
            head = QPainterPath()
            head.moveTo(points[0])
            head.lineTo(points[1])
            head.lineTo(points[2])
            head.closeSubpath()
            painter.drawPath(head)
