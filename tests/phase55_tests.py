"""Phase 55: the Nocturne restyle, step 2 of 6 -- the library.

The design (#1a in the handoff's mockup) measured on the live window at 1280x820: the top
bar's sizes, the card, the chips and the first cover on one edge 28 px in, covers 18 px
apart and 22 px between rows, the chosen chip an accent outline with no light fill, the
ring of a focused or hovered tile drawn outside its cover in the accent with the glow
around it, the sort's painted caret, and the backdrop fading into the ground -- no black.
Runs on a throwaway copy of the data; nothing is started.
"""
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))  # the project folder, one up from tests/
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import test_sandbox

box = test_sandbox.start()

import logging

logging.basicConfig(level=logging.ERROR)

from PySide6.QtCore import QEventLoop, QPoint, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

app = QApplication([])

from presentation import ui_rules as _ui_rules, ui_window


class _Rules:
    """ui_rules, with a name that does not exist read as 0 -- so the code before this
    phase can be judged check by check rather than crash at the first new name."""

    def __getattr__(self, name):
        return getattr(_ui_rules, name, 0)


ui_rules = _Rules()

passed = failed = 0
DESIGN_COVER = 137.25  # the mockup's cover width: 8 columns, 18 px apart, in 1224 px


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"   PASS  {name}")
    else:
        failed += 1
        print(f"   FAIL  {name}   {detail}")


def settle(seconds):
    loop = QEventLoop()
    QTimer.singleShot(round(seconds * 1000), loop.quit)
    loop.exec()


def rgb(colour):
    colour = QColor(colour)
    return colour.red(), colour.green(), colour.blue()


def distance(a, b):
    return max(abs(x - y) for x, y in zip(a, b))


def pixel(image, x, y):
    return rgb(image.pixelColor(x, y))


print("\n=== 1. the design's numbers ===")
check("the top bar: 64 high, 28 in, 22 between groups, 15 px tabs 24 apart, a 2 px underline",
      (ui_rules.TOPBAR_HEIGHT, ui_rules.TOPBAR_SIDE_MARGIN, ui_rules.TOPBAR_GAP, ui_rules.TOPBAR_TAB_PX,
       ui_rules.TOPBAR_TAB_GAP, ui_rules.TOPBAR_UNDERLINE) == (64, 28, 22, 15, 24, 2))
check("a 320 x 36 search box and 36 px buttons 6 apart",
      (ui_rules.SEARCH_WIDTH, ui_rules.SEARCH_HEIGHT, ui_rules.ICON_BUTTON_SIZE, ui_rules.ICON_BUTTON_GAP)
      == (320, 36, 36, 6))
check("chips 30 high, 12.5 px words, 11.5 px numbers, 13 px in, 8 apart",
      (ui_rules.CHIP_HEIGHT, ui_rules.CHIP_PX, ui_rules.CHIP_COUNT_PX, ui_rules.CHIP_SIDE_PADDING,
       ui_rules.CHIP_GAP) == (30, 12.5, 11.5, 13, 8))
# The names are SemiBold since Phase 62, one step heavier with every heading.
check("tiles: 8 px corners, 13 px SemiBold names over 11.5 px lines",
      (ui_rules.TILE_CORNER_RADIUS, ui_rules.TILE_NAME_PX, ui_rules.TILE_NAME_WEIGHT, ui_rules.TILE_SUB_PX)
      == (8, 13, "DemiBold", 11.5))
check("a focused tile's glow is 24 px of the accent at 45%, its ring the accent",
      (ui_rules.TILE_GLOW_PX, round(ui_rules.TILE_GLOW_ALPHA / 255, 2), ui_rules.TILE_FOCUS_COLOR)
      == (24, 0.45, ui_rules.COLOR_ACCENT))
marks = {
    "NEW letters 9.5 px": (ui_rules.NEW_BADGE_FONT_FRACTION, 9.5),
    "NEW padding 2 px": (ui_rules.NEW_BADGE_PAD_V_FRACTION, 2),
    "NEW padding 7 px": (ui_rules.NEW_BADGE_PAD_H_FRACTION, 7),
    "NEW corners 4 px": (ui_rules.NEW_BADGE_RADIUS_FRACTION, 4),
    "the star's disc 24 px": (ui_rules.FAVORITE_BADGE_FRACTION, 24),
    "7 px in": (ui_rules.FAVORITE_BADGE_MARGIN_FRACTION, 7),
}
off = {name: round(fraction * DESIGN_COVER, 2) for name, (fraction, px) in marks.items()
       if abs(fraction * DESIGN_COVER - px) > 0.15}
check("the marks are the design's pixels over its cover", not off, off)
check("the NEW tag: accent 800 behind accent 100, an accent 600 edge, letters 0.08 em apart",
      (ui_rules.NEW_BADGE_COLOR, ui_rules.NEW_BADGE_TEXT_COLOR, ui_rules.NEW_BADGE_EDGE, ui_rules.NEW_BADGE_TRACKING)
      == ("#423a6a", "#f5f4ff", "#796cbf", 0.08))
check("the star: accent 300, 12 px on a 24 px disc of the ground at 75%",
      (QColor(ui_rules.FAVORITE_BADGE_COLOR).name(), ui_rules.FAVORITE_STAR_FRACTION * 2,
       round(ui_rules.FAVORITE_BADGE_BACKDROP_ALPHA / 255, 2), QColor(ui_rules.FAVORITE_BADGE_BACKDROP).name())
      == ("#d2cefd", 0.5, 0.75, ui_rules.COLOR_BACKGROUND))
check("the chosen chip's light fill is gone", not hasattr(_ui_rules, "COLOR_CHIP_ON")
      and not hasattr(_ui_rules, "COLOR_CHIP_ON_TEXT"))

w = ui_window.MainWindow()
w.resize(1280, 820)
w.move(app.primaryScreen().availableGeometry().topLeft())
w.show()
settle(2.0)
lib, bar = w.library, w.top_bar
metrics = lib.metrics


def cover_left(row):
    rect = lib.list.visualItemRect(lib.list.item(row))
    width = lib.metrics.cover_width  # the current ones: TV mode changes them
    return lib.list.viewport().mapTo(w, QPoint(rect.x() + (rect.width() - width) // 2, rect.y()))


print("\n=== 2. the top bar ===")
current = bar.tabs["library"]
check("the tabs run the bar's full height", current.height() == bar.height() == 64,
      (current.height(), bar.height()))
shot = w.grab().toImage()
foot = current.mapTo(w, QPoint(current.width() // 2, current.height() - 1))
check("the current tab is underlined in the accent at the bar's foot",
      distance(pixel(shot, foot.x(), foot.y()), rgb(ui_rules.COLOR_ACCENT)) < 12, pixel(shot, foot.x(), foot.y()))
other = bar.tabs["stats"].mapTo(w, QPoint(bar.tabs["stats"].width() // 2, bar.tabs["stats"].height() - 1))
check("and the others are not", distance(pixel(shot, other.x(), other.y()), rgb(ui_rules.COLOR_ACCENT)) > 40)
check("the search box is 320 x 36, the buttons 36 square",
      (bar.search.width(), bar.search.height(), bar.settings.width(), bar.settings.height()) == (320, 36, 36, 36),
      (bar.search.size(), bar.settings.size()))
check("the right-hand buttons end 28 px from the window's edge",
      w.width() - (bar.settings.mapTo(w, QPoint(bar.settings.width(), 0)).x()) == 28)
hint = getattr(bar, "hint", None)
check("'Ctrl F' sits in the empty box", hint is not None and hint.isVisible() and hint.text() == "Ctrl F")
bar.search.setText("slow")
settle(0.2)
check("and gives way to the clear button once something is typed", hint is not None and not hint.isVisible())
bar.search.clear()
settle(0.3)
check("and comes back when it is cleared", hint is not None and hint.isVisible())

print("\n=== 3. one edge, and the design's gaps ===")
card_left = lib.card.mapTo(w, lib.card.card_rect().topLeft().toPoint()).x()
chip_left = lib.chips["all"].mapTo(w, QPoint(0, 0)).x()
check("the card, the chips and the first cover all start 28 px in, under the brand",
      card_left == chip_left == cover_left(0).x() == 28, (card_left, chip_left, cover_left(0).x()))
check("covers stand 18 px apart", cover_left(1).x() - (cover_left(0).x() + metrics.cover_width) == 18,
      cover_left(1).x() - cover_left(0).x() - metrics.cover_width)
columns = sum(1 for row in range(lib.list.count()) if cover_left(row).y() == cover_left(0).y())
first = lib.list.visualItemRect(lib.list.item(0))
words_foot = (first.y() + metrics.tile_padding + metrics.cover_height + ui_rules.TILE_NAME_GAP
              + round(ui_rules.TILE_NAME_PX * ui_rules.TILE_LINE_HEIGHT) + ui_rules.TILE_SUB_GAP
              + round(ui_rules.TILE_SUB_PX * ui_rules.TILE_LINE_HEIGHT))
below = lib.list.visualItemRect(lib.list.item(columns))
check(f"and 22 px from one row's words to the next row's covers ({columns} across)",
      below.y() + metrics.tile_padding - words_foot == 22, below.y() + metrics.tile_padding - words_foot)
chips_foot = lib.chips_bar.mapTo(w, QPoint(0, lib.chips["all"].geometry().bottom() + 1)).y()
check("14 px from the chips to the first covers", cover_left(0).y() + metrics.tile_padding - chips_foot == 14,
      cover_left(0).y() + metrics.tile_padding - chips_foot)

print("\n=== 4. the chips and the sort ===")
lib.set_filter("all")
settle(0.3)
shot = w.grab().toImage()
chosen, plain = lib.chips["all"], lib.chips["favorites"]


def chip_pixels(chip):
    origin = chip.mapTo(w, QPoint(0, 0))
    return [pixel(shot, origin.x() + x, origin.y() + y) for x in range(chip.width()) for y in range(chip.height())]


check("the chosen chip is outlined in the accent",
      min(distance(pixel(shot, chosen.mapTo(w, QPoint(0, chosen.height() // 2)).x() + dx,
                         chosen.mapTo(w, QPoint(0, chosen.height() // 2)).y()), rgb(ui_rules.COLOR_ACCENT))
          for dx in range(3)) < 25)
inside = pixel(shot, chosen.mapTo(w, QPoint(5, chosen.height() // 2)).x(), chosen.mapTo(w, QPoint(5, chosen.height() // 2)).y())
check("with no light fill behind its words (the old chosen chip was filled)", sum(inside) / 3 < 80, inside)
words = sum(1 for p in chip_pixels(chosen) if distance(p, rgb(ui_rules.COLOR_ACCENT_200)) < 10)
check("its word is in accent 200", words >= 15, words)
number_side = [pixel(shot, chosen.mapTo(w, QPoint(x, 0)).x(), chosen.mapTo(w, QPoint(0, y)).y())
               for x in range(chosen.width() * 2 // 3, chosen.width()) for y in range(chosen.height())]
muted = sum(1 for p in number_side if distance(p, rgb(ui_rules.COLOR_TEXT_MUTED)) < 10)
check("and its number muted", muted >= 5, muted)
inside = pixel(shot, plain.mapTo(w, QPoint(5, plain.height() // 2)).x(), plain.mapTo(w, QPoint(5, plain.height() // 2)).y())
check("an unchosen chip has no fill -- what is behind shows through", sum(inside) / 3 < 80, inside)
check("the sort draws its own caret, Qt's arrow hidden", lib.sort_box.property("caret") == "painted")
box_origin = lib.sort_box.mapTo(w, QPoint(0, 0))
caret = [pixel(shot, box_origin.x() + x, box_origin.y() + y)
         for x in range(lib.sort_box.width() - 24, lib.sort_box.width()) for y in range(lib.sort_box.height())]
check("in the muted colour", min(distance(p, rgb(ui_rules.COLOR_TEXT_MUTED)) for p in caret) < 30)

print("\n=== 5. a tile lifted by the pad or the mouse ===")
lib.list.setCurrentRow(3)
settle(0.5)
rest = w.grab().toImage()
lib.list.setCurrentRow(1)
settle(0.6)
lifted = w.grab().toImage()
painted = lib._painted[1]
edge = lib.list.viewport().mapTo(w, QPoint(painted.left() - 1, painted.center().y()))
check("the ring is the accent, outside the cover's edge",
      distance(pixel(lifted, edge.x(), edge.y()), rgb(ui_rules.COLOR_ACCENT)) < 30, pixel(lifted, edge.x(), edge.y()))
halo = lib.list.viewport().mapTo(w, QPoint(painted.left() - 8, painted.center().y()))
before, after = pixel(rest, halo.x(), halo.y()), pixel(lifted, halo.x(), halo.y())
check("and the glow lights the gap beside it", after[2] - before[2] > 6, (before, after))
resting = lib._painted.get(3)
far = lib.list.viewport().mapTo(w, QPoint(resting.left() - 1, resting.center().y()))
check("a tile at rest has only its hairline", distance(pixel(lifted, far.x(), far.y()), rgb(ui_rules.COLOR_ACCENT)) > 40,
      pixel(lifted, far.x(), far.y()))
lib._hover(lib.list.model().index(4, 0))
settle(0.6)
hovered = w.grab().toImage()
under = lib._painted[4]
edge = lib.list.viewport().mapTo(w, QPoint(under.left() - 1, under.center().y()))
check("the mouse lights a tile the same way", distance(pixel(hovered, edge.x(), edge.y()), rgb(ui_rules.COLOR_ACCENT)) < 30,
      pixel(hovered, edge.x(), edge.y()))
lib._hover(None)
settle(0.4)

print("\n=== 6. the backdrop ===")
image = w.backdrop._current.toImage()
ground = rgb(ui_rules.COLOR_BACKGROUND)
low = pixel(image, image.width() // 2, int(image.height() * 0.75))
check("it has faded fully into the ground by two thirds of the way down", distance(low, ground) <= 2, low)
corner = pixel(image, 0, image.height() - 1)
check("and its corners are the ground, never darker -- no black vignette", distance(corner, ground) <= 2, corner)
top = pixel(image, image.width() // 2, 2)
check("while the art shows through at the top", distance(top, ground) > 3, top)

print("\n=== 7. TV mode keeps the one edge ===")
w.set_tv_mode(True)
settle(1.5)
card_left = lib.card.mapTo(w, lib.card.card_rect().topLeft().toPoint()).x()
chip_left = lib.chips["all"].mapTo(w, QPoint(0, 0)).x()
check("the card, the chips and the first cover still share their edge",
      abs(card_left - chip_left) <= 1 and abs(chip_left - cover_left(0).x()) <= 1,
      (card_left, chip_left, cover_left(0).x()))
w.set_tv_mode(False)
w.close()

print("\n=== 8. the real library is exactly as it was found ===")
changed = box.finish()
check("overrides.json, config.json and catalog.json are byte for byte unchanged", not changed, changed)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
