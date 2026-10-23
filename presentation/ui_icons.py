"""Icons drawn from an icon font, and the typefaces the interface uses.

Phosphor since Phase 59 (the design's set, MIT), shipped beside Inter in presentation/fonts:
its regular icons, and its filled ones for the few solid glyphs. Every code point below was
read from the package's own style.css (@phosphor-icons/web 2.1.2), never guessed -- the
CLAUDE.md rule about formats. Windows' own icon fonts stay behind it: Windows 11 ships
Segoe Fluent Icons, Windows 10 Segoe MDL2 Assets, and every glyph in SEGOE but the two
filled ones has the same code point in both. If no icon font is present an icon is simply
empty, and every button that carries one also has a label or a tooltip. Each set was
rendered on this machine and looked at before it was used -- phase31_tests draws the whole
set onto one sheet for exactly that.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPixmap

from presentation import ui_rules
from shared import paths

log = logging.getLogger(__name__)

REGULAR, FILL = "regular", "fill"

# name -> (Phosphor's style, Phosphor's own name for it, its code point in that style.css).
PHOSPHOR = {
    "search": (REGULAR, "magnifying-glass", 0xE30C),
    "settings": (REGULAR, "gear-six", 0xE272),
    "refresh": (REGULAR, "arrows-clockwise", 0xE094),
    "shuffle": (REGULAR, "shuffle", 0xE422),
    "play": (REGULAR, "play", 0xE3D0),
    "star": (REGULAR, "star", 0xE46A),
    "star_full": (FILL, "star", 0xE46A),
    "folder": (REGULAR, "folder-open", 0xE256),
    "more": (REGULAR, "dots-three", 0xE1FE),
    "back": (REGULAR, "arrow-left", 0xE058),
    "check": (REGULAR, "check", 0xE182),
    "info": (REGULAR, "info", 0xE2CE),
    "save": (REGULAR, "floppy-disk", 0xE248),
    "sort": (REGULAR, "arrows-down-up", 0xE098),
    "brand": (FILL, "game-controller", 0xE26E),  # the top bar's, filled as the design has it
    "controller": (REGULAR, "game-controller", 0xE26E),  # a pill's or a figure's, outlined
    "play_solid": (FILL, "play", 0xE3D0),
    "stop_solid": (FILL, "stop", 0xE46C),
    "chevron_left": (REGULAR, "caret-left", 0xE138),
    "chevron_right": (REGULAR, "caret-right", 0xE13A),
    "clock": (REGULAR, "clock", 0xE19A),
    "calendar": (REGULAR, "calendar-blank", 0xE10A),
    "disk": (REGULAR, "hard-drive", 0xE29E),
    "edit": (REGULAR, "pencil-simple", 0xE3B4),
    "history": (REGULAR, "clock-counter-clockwise", 0xE1A0),
    "broom": (REGULAR, "broom", 0xEC54),  # Storage's reclaim strip, as the design has it
    # The side rail (Phase 60): its three places and its five filters.
    "grid": (REGULAR, "squares-four", 0xE464),
    "chart": (REGULAR, "chart-bar", 0xE150),
    "drives": (REGULAR, "hard-drives", 0xE2A0),
    "reports": (REGULAR, "presentation-chart", 0xE656),  # the Reports tab (Phase 84), from 2.1.2's CSS
    "wishlist": (REGULAR, "heart", 0xE2A8),  # the Wishlist tab (Phase 87), from the same CSS
    "foryou": (REGULAR, "sparkle", 0xE6A2),  # the For you place (Phase 98): 2.1.2's CSS, its font the same file
    "playing": (REGULAR, "play-circle", 0xE3D2),
    "finished": (REGULAR, "check-circle", 0xE184),
    "dropped": (REGULAR, "x-circle", 0xE4F8),
}

# The same names in Windows' icon fonts, for a copy without Phosphor's files. The two the
# Windows fonts have no glyph of their own for borrow the nearest one.
SEGOE = {
    "search": 0xE721,
    "settings": 0xE713,
    "refresh": 0xE72C,
    "shuffle": 0xE8B1,
    "play": 0xE768,
    "star": 0xE734,
    "star_full": 0xE735,
    "folder": 0xE8B7,
    "more": 0xE712,
    "back": 0xE72B,
    "check": 0xE73E,
    "info": 0xE946,
    "save": 0xE74E,
    "sort": 0xE8CB,
    "brand": 0xE7FC,  # a game controller
    "controller": 0xE7FC,
    # Filled, for the solid Play and Stop (Phase 32). These two are Fluent-only: on
    # Windows 10 they draw nothing, and both buttons carry their word anyway.
    "play_solid": 0xF5B0,
    "stop_solid": 0xEE95,
    "chevron_left": 0xE76B,
    "chevron_right": 0xE76C,
    "clock": 0xE823,
    "calendar": 0xE787,
    "disk": 0xEDA2,
    "edit": 0xE70F,
    "history": 0xE81C,
    "broom": 0xE81C,  # no broom in Windows' fonts: the clock with its arrow, as before
    # The rail's, borrowed from glyphs above whose code points are known; every one of
    # these sits beside its words, so a stand-in only has to look like an icon.
    "grid": 0xE7FC,
    "chart": 0xE823,
    "drives": 0xEDA2,
    "reports": 0xE823,  # Windows has no "presentation chart": Stats' chart lends its glyph
    "wishlist": 0xE734,  # no heart whose code point is known here: the outlined star lends its glyph
    "foryou": 0xE734,  # no sparkle in Windows' fonts: the outlined star again
    "playing": 0xE768,
    "finished": 0xE73E,
    "dropped": 0xE712,
}

# Every icon the app draws, by name.
GLYPHS = tuple(PHOSPHOR)

# Rendered at each of these device pixel ratios, so a 300%-scaled TV gets a crisp glyph
# rather than a 16-pixel one stretched three times over.
PIXEL_RATIOS = (1.0, 1.5, 2.0, 3.0)


@lru_cache(maxsize=None)
def bundled_families() -> tuple[str, ...]:
    """Register the fonts shipped in presentation/fonts (Inter, Phase 54), once.

    Done before any family is chosen, which is before the first stylesheet is built. A
    missing folder or a file Qt refuses is logged, and the families after Inter in
    ui_rules -- Windows' own -- take over.
    """
    folder = paths.resource_dir().joinpath(*ui_rules.FONTS_FOLDER)
    loaded: list[str] = []
    for path in sorted(folder.glob("*.ttf")):
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id < 0:
            log.warning("could not load the font %s", path.name)
            continue
        loaded.extend(QFontDatabase.applicationFontFamilies(font_id))
    if not loaded:
        log.warning("no bundled fonts in %s; using Windows' own", folder)
    families = tuple(dict.fromkeys(loaded))
    log.info("bundled fonts: %s", ", ".join(families) or "none")
    return families


def _first_installed(families: tuple[str, ...]) -> str:
    bundled_families()
    installed = set(QFontDatabase.families())
    for family in families:
        if family in installed:
            return family
    return ""


@lru_cache(maxsize=None)
def icon_family() -> str:
    """Phosphor when its files are there (Phase 59), else Windows' own icon font."""
    family = _first_installed(ui_rules.ICON_FONT_FAMILIES)
    if not family:
        log.warning("no icon font found (%s); icons will be blank",
                    ", ".join(ui_rules.ICON_FONT_FAMILIES))
    return family


@lru_cache(maxsize=None)
def _fill_family() -> str:
    return _first_installed((ui_rules.ICON_FILL_FAMILY,))


def glyph_for(name: str) -> tuple[str, str]:
    """The family and the character that draw icon `name`, or ("", "") for none."""
    family = icon_family()
    if not family or name not in PHOSPHOR:
        return "", ""
    if family == ui_rules.ICON_FONT_FAMILIES[0]:
        style, _phosphor_name, code = PHOSPHOR[name]
        if style == FILL:
            # The filled set is its own file; without it the outlined glyph still reads.
            return (_fill_family() or family), chr(code)
        return family, chr(code)
    return family, chr(SEGOE[name])


@lru_cache(maxsize=None)
def body_family() -> str:
    return _first_installed(ui_rules.FONT_BODY_FAMILIES) or "Segoe UI"


@lru_cache(maxsize=None)
def display_family() -> str:
    return _first_installed(ui_rules.FONT_DISPLAY_FAMILIES) or "Segoe UI"


def glyph_pixmap(name: str, color: str, px: int, ratio: float = 1.0) -> QPixmap:
    """One glyph, centred in a px-by-px square, at the given device pixel ratio."""
    size = max(1, round(px * ratio))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    family, character = glyph_for(name)
    if family:
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        font = QFont(family)
        font.setPixelSize(size)
        painter.setFont(font)
        painter.setPen(QColor(color))
        painter.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, character)
        painter.end()
    pixmap.setDevicePixelRatio(ratio)
    return pixmap


def icon(name: str, color: str = ui_rules.COLOR_TEXT, px: int = ui_rules.ICON_GLYPH_PX,
         disabled: str = ui_rules.COLOR_DISABLED) -> QIcon:
    """A QIcon for a button, crisp at every scale, dimmed properly when disabled.

    The disabled state is drawn explicitly: Qt's automatic greying of a white glyph on a
    dark background barely changes it -- the same lesson as QMenu::item:disabled.
    """
    result = QIcon()
    for ratio in PIXEL_RATIOS:
        result.addPixmap(glyph_pixmap(name, color, px, ratio), QIcon.Mode.Normal)
        result.addPixmap(glyph_pixmap(name, disabled, px, ratio), QIcon.Mode.Disabled)
    return result
