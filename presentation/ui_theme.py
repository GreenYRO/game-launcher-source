"""Colours, sizes at the current interface scale, and the application stylesheet.

Two things live here. `Metrics` multiplies every size in ui_rules by the user's interface
scale, so the rest of the UI never multiplies anything itself. `accent_for` turns a game's
name into a stable colour, which is what stops a library of art-less games looking like a
sheet of identical grey rectangles.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from PySide6.QtCore import QEasingCurve, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QPixmap

from presentation import ui_icons
from presentation import ui_rules


def easing(name: str) -> QEasingCurve.Type:
    """Look up a named curve from ui_rules; fall back to Linear rather than raising."""
    curve = getattr(QEasingCurve.Type, name, None)
    if curve is None:
        import logging

        logging.getLogger(__name__).warning("unknown easing curve %r; using Linear", name)
        return QEasingCurve.Type.Linear
    return curve


def accent_for(name: str) -> QColor:
    """A stable colour for a game with no art.

    Derived from a hash of the name, so it never changes between runs and two games are
    unlikely to collide. Saturation and lightness are fixed, so every generated cover sits
    at the same visual weight and the grid still looks like one set.
    """
    digest = hashlib.sha1(name.strip().casefold().encode("utf-8")).digest()
    hue = (digest[0] << 8 | digest[1]) / 65535.0
    colour = QColor()
    colour.setHslF(
        hue,
        ui_rules.PLACEHOLDER_HUE_SATURATION,
        ui_rules.PLACEHOLDER_HUE_LIGHTNESS,
    )
    return colour


_SOFT_EDGES: dict[tuple, QPixmap] = {}
_SOFT_EDGES_KEPT = 64  # every size ever asked for would otherwise pile up across rescales


def soft_edge(width: int, height: int, radius: float, spread: int, colour: str,
              alpha: int) -> QPixmap:
    """A soft rounded halo -- a shadow, or a glow -- made once per size and kept.

    Stacked translucent rounded rectangles, darkest nearest the shape. The pixmap is the
    shape grown by `spread` on every side; draw it at the shape's rect grown by the same.
    Cheap to make and free to draw, where a blur effect would re-run on every frame of
    every hover. Shared by the tiles, the Continue playing card and the game page's cover.
    """
    key = (width, height, round(radius), spread, colour, alpha)
    cached = _SOFT_EDGES.get(key)
    if cached is not None:
        return cached
    pixmap = QPixmap(max(1, width + spread * 2), max(1, height + spread * 2))
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    body = QRectF(spread, spread, width, height)
    tint = QColor(colour)
    for grow in range(spread, 0, -2):
        tint.setAlpha(round(alpha * (1 - grow / spread) ** 2 / 3))
        painter.setBrush(tint)
        painter.drawRoundedRect(body.adjusted(-grow, -grow, grow, grow), radius + grow, radius + grow)
    painter.end()
    if len(_SOFT_EDGES) >= _SOFT_EDGES_KEPT:
        _SOFT_EDGES.pop(next(iter(_SOFT_EDGES)))
    _SOFT_EDGES[key] = pixmap
    return pixmap


def reserve_bold_width(button) -> None:
    """Give a button whose words turn bold when it is switched on the room bold needs.

    Qt measures a button with the font it has; a stylesheet's `:checked { font-weight }`
    only changes the font it is *painted* with. So the switched-on words came out a few
    pixels wider than the space measured for them and lost their edges -- the chips in
    Phase 31, then the top bar's tabs (reported from use: "Library" lost the tail of its
    "y"), the two switches beside the chips, and the game page's toggles. Call it after
    the stylesheet is applied and whenever the words change. Measured at the heading
    weight, which is what `:checked` asks for (SemiBold until Phase 54, Medium since).
    """
    button.ensurePolished()
    font = button.font()
    bold = QFont(font)
    bold.setWeight(QFont.Weight(ui_rules.HEADING_WEIGHT))
    # What is drawn, not what is typed: "&&" shows one ampersand, a lone "&" none.
    shown = button.text().replace("&&", "\0").replace("&", "").replace("\0", "&")
    extra = QFontMetrics(bold).horizontalAdvance(shown) - QFontMetrics(font).horizontalAdvance(shown)
    button.setMinimumWidth(button.sizeHint().width() + max(0, extra) + 1)


def _rgba(colour: str) -> tuple[float, float, float, float]:
    """A stylesheet colour -- "#rrggbb", "#aarrggbb" or "rgba(r, g, b, a)" -- as numbers."""
    text = colour.replace(" ", "")
    if text.startswith("rgba("):
        red, green, blue, alpha = (float(part) for part in text[5:-1].split(","))
        return red, green, blue, alpha
    qcolor = QColor(colour)
    return qcolor.red(), qcolor.green(), qcolor.blue(), qcolor.alpha()


def qcolor(colour: str) -> QColor:
    """Any of the stylesheet's forms as a QColor -- which cannot read rgba(...) itself (Phase 35)."""
    red, green, blue, alpha = _rgba(colour)
    return QColor(round(red), round(green), round(blue), round(alpha))


def paint_capsule(painter: QPainter, rect, fill: str | None, edge: str | None, width: float = 1.0) -> None:
    """A pill, painted: its ends true half-circles and its edge one even line all round (Phase 99).

    The stylesheet's border-radius drew a pill's ends flattened, with a kink where the curve met the straight
    edge and the 1-px line thicker on the curves than on the sides -- plainest at 125%, reported from use. Here
    the outline is one rounded path, anti-aliased, set half its width inside the box so it falls on whole
    pixels along the straight edges.
    """
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    inset = width / 2
    box = QRectF(rect).adjusted(inset, inset, -inset, -inset)
    radius = box.height() / 2
    path = QPainterPath()
    path.addRoundedRect(box, radius, radius)
    if fill:
        painter.fillPath(path, qcolor(fill))
    if edge:
        painter.setPen(QPen(qcolor(edge), width))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
    painter.restore()


def pill_edge(scale: float) -> float:
    """A pill's edge at this interface scale: PILL_EDGE_WIDTH times it, never under one pixel."""
    return max(1.0, ui_rules.PILL_EDGE_WIDTH * scale)


def accent_names() -> tuple[str, ...]:
    return tuple(ui_rules.ACCENTS)


def use_accent(name) -> str:
    """Every accent colour of ui_rules set to family `name`'s steps (Phase 99); the family used is returned --
    an unknown name is the default's. Read at paint time, the colours follow at once; the stylesheet and the
    icons painted once are rebuilt by the window (MainWindow.apply_accent)."""
    chosen = name if name in ui_rules.ACCENTS else ui_rules.ACCENT_DEFAULT
    steps = ui_rules.ACCENTS[chosen]
    for constant, step in ui_rules.ACCENT_STEPS.items():
        setattr(ui_rules, constant, steps[step])
    for constant, (step, form, alpha) in ui_rules.ACCENT_FORMS.items():
        value = QColor(steps[step])
        setattr(ui_rules, constant, f"rgba({value.red()}, {value.green()}, {value.blue()}, {alpha})" if form == "rgba"
                else f"#{alpha:02x}{steps[step].lstrip('#')}")
    ui_rules.STATUS_COLORS = {**ui_rules.STATUS_COLORS,
                              **{status: steps[step] for status, step in ui_rules.ACCENT_STATUS.items()}}
    return chosen


def layered(*colours: str) -> str:
    """Stylesheet colours painted one over another, as the one rgba(...) a stylesheet takes.

    A button over art keeps the ground under it and lights on top of that under the mouse
    (Phase 56) -- two backgrounds, which a stylesheet cannot stack, so they meet here.
    """
    red = green = blue = alpha = 0.0
    for colour in colours:
        top_r, top_g, top_b, top_a = _rgba(colour)
        top_a /= 255
        out = top_a + alpha * (1 - top_a)
        if out > 0:
            red = (top_r * top_a + red * alpha * (1 - top_a)) / out
            green = (top_g * top_a + green * alpha * (1 - top_a)) / out
            blue = (top_b * top_a + blue * alpha * (1 - top_a)) / out
        alpha = out
    return f"rgba({round(red)}, {round(green)}, {round(blue)}, {round(alpha * 255)})"


def px_to_pt(pixels: float) -> float:
    """The design's sizes are pixels, some of them halves (12.5, 11.5). Qt takes a pixel
    size only as a whole number, but a point size as any number: at Windows' logical
    96 dots per inch -- the same at every display scale -- 72 points are 96 pixels."""
    return pixels * 72 / 96


def tracking(pixels: float) -> float:
    """Letter spacing for a title this many pixels tall, in pixels: tighter as it grows."""
    for from_px, em in ui_rules.TITLE_TRACKING:
        if pixels >= from_px:
            return em * pixels
    return 0.0


def darken(colour: QColor, amount: float) -> QColor:
    """Blend a colour towards black. amount 0 = unchanged, 1 = black."""
    factor = max(0.0, min(1.0, 1.0 - amount))
    return QColor(
        int(colour.red() * factor), int(colour.green() * factor), int(colour.blue() * factor)
    )


@dataclass(frozen=True)
class Metrics:
    """Every pixel size, already multiplied by the interface scale."""

    scale: float = ui_rules.UI_SCALE_DEFAULT

    def _s(self, value: float) -> int:
        return max(1, round(value * self.scale))

    @property
    def cover_width(self) -> int:
        return self._s(ui_rules.COVER_WIDTH)

    @property
    def cover_height(self) -> int:
        return self.cover_width * ui_rules.COVER_ASPECT_H // ui_rules.COVER_ASPECT_W

    @property
    def tile_padding(self) -> int:
        """The room above a cover in its cell."""
        return self._s(ui_rules.TILE_PADDING)

    @property
    def tile_padding_x(self) -> int:
        """The room either side of a cover in its cell (Phase 55)."""
        return self._s(ui_rules.TILE_PADDING_X)

    @property
    def tile_name_height(self) -> int:
        return self._s(ui_rules.TILE_NAME_HEIGHT)

    @property
    def tile_width(self) -> int:
        return self.cover_width + self.tile_padding_x * 2

    @property
    def tile_height(self) -> int:
        return self.tile_padding + self.cover_height + self.tile_name_height

    @property
    def corner_radius(self) -> int:
        return self._s(ui_rules.TILE_CORNER_RADIUS)

    @property
    def grid_spacing(self) -> int:
        return round(ui_rules.GRID_SPACING * self.scale)  # 0 since Phase 55: the cells hold the gaps

    @property
    def grid_inset(self) -> int:
        """How far in from the grid's edge the first cover starts. The card and the chips are
        inset by the same, so all three line up on one edge as the design has them."""
        return self.grid_spacing + self.tile_padding_x

    @property
    def scroll_step(self) -> int:
        return self._s(ui_rules.SCROLL_WHEEL_STEP)


def stylesheet(scale: float) -> str:
    """The whole application's look, in one place."""
    base = max(8, round(ui_rules.BASE_FONT_PT * scale))
    title = max(14, round(ui_rules.TITLE_FONT_PT * scale))
    meta = max(8, round(ui_rules.META_FONT_PT * scale))
    description = max(9, round(ui_rules.DESCRIPTION_FONT_PT * scale))
    radius = max(3, round(ui_rules.CONTROL_RADIUS * scale))
    pad_v = max(4, round(ui_rules.BUTTON_PADDING_Y * scale))
    pad_h = max(8, round(ui_rules.BUTTON_PADDING_X * scale))
    chip_radius = max(8, round(ui_rules.CHIP_HEIGHT * scale) // 2)
    chip_font = f"{px_to_pt(ui_rules.CHIP_PX * scale):.2f}pt"
    body = ui_icons.body_family()
    display = ui_icons.display_family()

    return f"""
    QWidget {{
        background: {ui_rules.COLOR_BACKGROUND};
        color: {ui_rules.COLOR_TEXT};
        font-family: "{body}";
        font-size: {base}pt;
        font-weight: {ui_rules.BODY_WEIGHT};
    }}
    QLabel#Title {{ font-family: "{display}"; font-size: {title}pt; font-weight: {ui_rules.HEADING_WEIGHT}; }}
    QLabel#Meta  {{ color: {ui_rules.COLOR_TEXT_MUTED}; font-size: {meta}pt; }}
    QLabel#SectionLabel {{ color: {ui_rules.COLOR_SECTION_LABEL}; }}
    QLabel#Description {{
        font-size: {description}pt;
        color: {ui_rules.COLOR_TEXT};
        line-height: {int(ui_rules.DESCRIPTION_LINE_HEIGHT * 100)}%;
    }}
    QLineEdit, QComboBox, QSpinBox {{
        background: {ui_rules.COLOR_SURFACE};
        border: 1px solid {ui_rules.COLOR_BORDER};
        border-radius: {radius}px;
        padding: {pad_v}px {max(6, round(8 * scale))}px;
        selection-background-color: {ui_rules.COLOR_ACCENT};
    }}
    QLineEdit:focus, QComboBox:focus {{ border-color: {ui_rules.COLOR_ACCENT}; }}
    QComboBox::drop-down {{ border: none; width: {max(14, round(18 * scale))}px; }}
    QComboBox QAbstractItemView {{
        background: {ui_rules.COLOR_MENU};
        border: 1px solid {ui_rules.COLOR_MENU_EDGE};
        selection-background-color: {ui_rules.COLOR_MENU_SELECTED};
        selection-color: {ui_rules.COLOR_MENU_SELECTED_TEXT};
    }}

    /* Phase 58: every button without a look of its own is the design's quiet one -- an
       outline in the divider, the text colour at 7% under the mouse, 14% pressed -- and a
       dialog's default button its outlined accent one. */
    QPushButton {{
        background: transparent;
        border: 1px solid {ui_rules.COLOR_DIVIDER};
        border-radius: {radius}px;
        padding: {pad_v}px {pad_h}px;
    }}
    QPushButton:hover {{ background: {ui_rules.COLOR_SECONDARY_HOVER}; }}
    QPushButton:pressed {{ background: {ui_rules.COLOR_SECONDARY_PRESSED}; }}
    QPushButton:disabled {{ color: {ui_rules.COLOR_TEXT_MUTED}; }}
    QDialog QPushButton {{ font-weight: {ui_rules.HEADING_WEIGHT}; }}
    QDialog QPushButton:default {{ border-color: {ui_rules.COLOR_ACCENT}; color: {ui_rules.COLOR_ACCENT}; }}
    QDialog QPushButton:default:hover {{ background: {ui_rules.COLOR_PRIMARY_HOVER}; }}
    QDialog QPushButton:default:pressed {{ background: {ui_rules.COLOR_PRIMARY_PRESSED}; }}
    /* A question's buttons have no ring of their own to draw: the one the pad or the
       keyboard is on is edged in the accent, so Cancel-in-focus reads from the couch. */
    QMessageBox QPushButton:focus, QInputDialog QPushButton:focus {{
        border: {max(1, round(ui_rules.FOCUS_RING_WIDTH * scale))}px solid {ui_rules.TILE_FOCUS_COLOR};
    }}
    /* The game page's Play, Stop, star and marks are styled in ui_continue and ui_detail
       (Phase 33); the old flat buttons they replaced are gone. */
    QLabel#NewsTitle {{
        color: {ui_rules.COLOR_TEXT};
        font-size: {max(10, round(ui_rules.NEWS_TITLE_FONT_PT * scale))}pt;
        font-weight: {ui_rules.HEADING_WEIGHT};
    }}
    /* Destructive, and deliberately quiet until you reach for it: it sits on every
       game's page and must not compete with Play. */
    QPushButton#Danger {{
        color: {ui_rules.COLOR_TEXT_MUTED};
        border-color: {ui_rules.COLOR_BORDER};
    }}
    QPushButton#Danger:hover {{
        background: {ui_rules.COLOR_STOP};
        border-color: {ui_rules.COLOR_STOP};
        color: {ui_rules.COLOR_TEXT};
    }}
    QPushButton#Danger[blocked="true"] {{ color: {ui_rules.COLOR_DISABLED}; }}
    QPushButton#Danger[blocked="true"]:hover {{
        background: {ui_rules.COLOR_SURFACE_RAISED};
        border-color: {ui_rules.COLOR_BORDER};
        color: {ui_rules.COLOR_TEXT_MUTED};
    }}
    QPushButton#Nav {{
        background: rgba(0, 0, 0, 110);
        border: 1px solid {ui_rules.COLOR_BORDER};
        font-size: {max(12, round(17 * scale))}pt;
        padding: {max(4, round(6 * scale))}px {max(8, round(12 * scale))}px;
    }}
    QPushButton#Nav:hover {{ background: {ui_rules.COLOR_ACCENT}; border-color: {ui_rules.COLOR_ACCENT}; }}

    QCheckBox {{ spacing: {max(5, round(8 * scale))}px; }}

    /* Phase 31: the chips above the grid, the two switches beside them, and the sort.
       Outlines since Phase 55, as the design draws them; the chosen one in the accent,
       and no heavier -- its words are painted by ui_library.Chip, in two colours. */
    /* Since Phase 99 their box -- outline, hover, the chosen fill -- is painted (ui_theme.paint_capsule): the
       stylesheet's round ends came out flattened and uneven. It keeps their room and their words. */
    QPushButton#Chip, QPushButton#ToggleChip {{
        background: transparent;
        border: 1px solid transparent;
        border-radius: {chip_radius}px;
        padding: 0 {max(6, round(ui_rules.CHIP_SIDE_PADDING * scale))}px;
        font-size: {chip_font};
        color: {ui_rules.COLOR_TEXT_SOFT};
    }}
    QPushButton#ToggleChip {{ color: {ui_rules.COLOR_TEXT_QUIET}; }}
    QPushButton#Chip:checked, QPushButton#ToggleChip:checked {{ color: {ui_rules.COLOR_ACCENT_200}; }}
    QLabel#SortLabel {{ background: transparent; color: {ui_rules.COLOR_TEXT_MUTED}; font-size: {chip_font}; }}
    QComboBox#SortBox {{
        background: transparent;
        border: 1px solid transparent;
        border-radius: {chip_radius}px;
        padding: 0 {max(6, round(12 * scale))}px;
        font-size: {chip_font};
    }}
    /* The library's sort draws its own caret (ui_library.SortBox), the design's thin one. */
    QComboBox#SortBox[caret="painted"]::drop-down {{
        border: none; width: {max(10, round((ui_rules.SORT_CARET_PX + 12) * scale))}px;
    }}
    QComboBox#SortBox[caret="painted"]::down-arrow {{ image: none; width: 0; height: 0; }}

    /* Messages, as a card rather than a status bar (ui_toast). */
    QWidget#Toast {{
        background: {ui_rules.COLOR_TOAST};
        border: 1px solid {ui_rules.COLOR_TOAST_EDGE};
        border-radius: {max(8, round(ui_rules.TOAST_RADIUS * scale))}px;
    }}
    QLabel#ToastText {{
        background: transparent;
        color: {ui_rules.COLOR_TEXT};
        font-size: {max(8, round(ui_rules.TOAST_FONT_PT * scale))}pt;
    }}
    QLabel#ToastGlyph {{ background: transparent; }}
    /* How was it? (Phase 102): the toast's card, taking clicks. */
    QWidget#RateCard {{
        background: {ui_rules.COLOR_TOAST};
        border: 1px solid {ui_rules.COLOR_TOAST_EDGE};
        border-radius: {max(8, round(ui_rules.TOAST_RADIUS * scale))}px;
    }}
    QLabel#RateQuestion {{ background: transparent; color: {ui_rules.COLOR_TEXT}; }}
    QPushButton#RateStar {{ background: transparent; border: none; }}
    QPushButton#RateSkip {{ background: transparent; border: none; color: {ui_rules.COLOR_TEXT_MUTED}; }}
    QPushButton#RateSkip:hover {{ color: {ui_rules.COLOR_TEXT}; }}
    QListWidget, QListView {{ background: {ui_rules.COLOR_BACKGROUND}; border: none; outline: 0; }}
    /* Thin, rounded, and out of the way until reached for. */
    QScrollBar:vertical {{
        background: transparent; width: {max(6, round(10 * scale))}px; margin: 2px;
    }}
    QScrollBar:horizontal {{
        background: transparent; height: {max(6, round(10 * scale))}px; margin: 2px;
    }}
    QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
        background: {ui_rules.COLOR_SCROLL_HANDLE};
        border-radius: {max(2, round(3 * scale))}px;
        min-height: {max(20, round(30 * scale))}px;
        min-width: {max(20, round(30 * scale))}px;
    }}
    QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{
        background: {ui_rules.COLOR_SCROLL_HOVER};
    }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

    QStatusBar {{ color: {ui_rules.COLOR_TEXT_MUTED}; }}
    /* The design's menus: the surface, a hairline edge, and the entry under the mouse or
       the pad a dark accent with near-white words -- not a flood of the accent (Phase 58). */
    QMenu {{
        background: {ui_rules.COLOR_MENU};
        border: 1px solid {ui_rules.COLOR_MENU_EDGE};
        padding: {max(3, round(6 * scale))}px;
    }}
    QMenu::item {{
        padding: {max(5, round(8 * scale))}px {max(12, round(22 * scale))}px;
        border-radius: {radius}px;
        margin: 1px 0;
    }}
    QMenu::item:selected {{ background: {ui_rules.COLOR_MENU_SELECTED}; color: {ui_rules.COLOR_MENU_SELECTED_TEXT}; }}
    QMenu::separator {{ height: 1px; background: {ui_rules.COLOR_BORDER}; margin: {max(3, round(5 * scale))}px {max(4, round(8 * scale))}px; }}
    /* Needed explicitly: the blanket QWidget colour above beats Qt's own disabled palette,
       so a disabled entry looked identical to an enabled one and only failed on click. */
    QMenu::item:disabled {{ color: {ui_rules.COLOR_DISABLED}; }}
    QMenu::item:disabled:selected {{ background: transparent; color: {ui_rules.COLOR_DISABLED}; }}
    QToolTip {{
        background: {ui_rules.COLOR_MENU};
        color: {ui_rules.COLOR_TEXT};
        border: 1px solid {ui_rules.COLOR_MENU_EDGE};
        padding: {max(3, round(6 * scale))}px {max(5, round(9 * scale))}px;
    }}
    """
