"""Phase 56: the Nocturne restyle, step 3 of 6 -- the Continue playing card.

The design (#1a's card, read from the mockup's markup) measured on the live window: 250 px
high, 8 px under the top bar, edged with a hairline and no shadow; its words standing on
its foot; an outlined Play and a quiet Details sized to their words, 36 px in, 34 px up,
10 apart; the design's focus ring drawn 2 px outside the button the pad is on, TV mode's
thicker; Stop outlined in red; and no green anywhere -- the game page's Play included.
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

from adapters import controller
from logic import focus
from presentation import ui_rules as _ui_rules, ui_window


class _Rules:
    """ui_rules, with a name that does not exist read as 0 -- so the code before this
    phase can be judged check by check rather than crash at the first new name."""

    def __getattr__(self, name):
        return getattr(_ui_rules, name, 0)


ui_rules = _Rules()
passed = failed = 0


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


def at(image, point):
    return rgb(image.pixelColor(point.x(), point.y()))


def greenish(p):
    return p[1] > p[0] + 25 and p[1] > p[2] + 25


print("\n=== 1. the design's numbers ===")
check("250 high, corners 14, 36 px in from the sides and 34 from top and bottom",
      (ui_rules.CONTINUE_HEIGHT, ui_rules.CONTINUE_RADIUS, ui_rules.CONTINUE_PADDING_X, ui_rules.CONTINUE_PADDING_Y)
      == (250, 14, 36, 34))
check("an eyebrow of 10 px spaced 0.18 em, a 40 px title on a 1.1 line, 14 px under it, a 13 px note",
      (ui_rules.CONTINUE_EYEBROW_PX, ui_rules.CONTINUE_EYEBROW_TRACKING, ui_rules.CONTINUE_TITLE_PX,
       ui_rules.CONTINUE_TITLE_LINE, ui_rules.CONTINUE_META_PX, ui_rules.CONTINUE_NOTE_PX)
      == (10, 0.18, 40, 1.1, 14, 13))
check("buttons 42 high, 15 px words, 24 and 20 px either side, 10 apart",
      (ui_rules.CONTINUE_BUTTON_HEIGHT, ui_rules.CONTINUE_BUTTON_PX, ui_rules.CONTINUE_PLAY_PADDING,
       ui_rules.CONTINUE_DETAILS_PADDING, ui_rules.CONTINUE_BUTTON_GAP) == (42, 15, 24, 20, 10))
check("the scrim: the ground, 70% of it by 42%, gone by 85%",
      tuple(ui_rules.CONTINUE_SCRIM or ()) == ((0.0, 255), (0.42, 179), (0.85, 0)), ui_rules.CONTINUE_SCRIM)
check("the buttons sit on the ground at 60% (Play) and 50% (Details)",
      (ui_rules.COLOR_ON_ART_PRIMARY, ui_rules.COLOR_ON_ART_SECONDARY)
      == ("rgba(22, 24, 38, 153)", "rgba(22, 24, 38, 128)"))
green = [name for name in vars(_ui_rules) if name.startswith("COLOR_PLAY")]
check("no green is left among the constants", not green, green)

w = ui_window.MainWindow()
w.resize(1280, 820)
w.move(app.primaryScreen().availableGeometry().topLeft())
w.show()
settle(2.0)
focus.bring_to_front(int(w.winId()))
settle(0.4)
lib, card = w.library, w.library.card
play, details = card.play_button, card.details_button


def card_box():
    rect = card.card_rect()
    origin = card.mapTo(w, rect.topLeft().toPoint())
    return origin.x(), origin.y(), round(rect.width()), round(rect.height())


print("\n=== 2. the card ===")
check("the card is up, offering a game", card.shown and card.view is not None)
left, top, width, height = card_box()
bar_foot = w.top_bar.mapTo(w, QPoint(0, w.top_bar.height())).y()
check("250 high, 8 px under the top bar", (height, top - bar_foot) == (250, 8), (height, top - bar_foot))
shot = w.grab().toImage()
under = QPoint(left + width // 2, top + height + 6)
glow = rgb(w.backdrop._current.toImage().pixelColor(w.backdrop.mapFrom(w, under)))
check("no shadow under it: just below, the window is the backdrop", distance(at(shot, under), glow) <= 4,
      (at(shot, under), glow))
edge = at(shot, QPoint(left + 2, top + height // 2))
check("at its left edge the scrim is the ground", distance(edge, rgb(ui_rules.COLOR_BACKGROUND)) <= 8, edge)
# By its right end the scrim is gone: the window shows the card's own art there, pixel for
# pixel. Read where the art stands out from the ground, or a scrim over it could not be told
# from none -- the card offers the game played last, and CULTIC's banner is nearly the
# ground's colour across the middle of that column (Phase 63; the check used to read the
# middle row against the ground, and failed on dark art that was showing unshaded).
art = card._art(width, height).toImage()
ratio = art.devicePixelRatio()
column = int(width * 0.92)
readable = []
for y in range(4, height - 4, 6):
    own = rgb(art.pixelColor(int(column * ratio), int(y * ratio)))
    if distance(own, rgb(ui_rules.COLOR_BACKGROUND)) > 25:
        readable.append((own, at(shot, QPoint(left + column, top + y))))
check("and by its right end the art shows, unshaded",
      readable and all(distance(own, seen) <= 4 for own, seen in readable),
      (len(readable), [pair for pair in readable if distance(*pair) > 4][:3]))

print("\n=== 3. the buttons ===")
play_box = play.geometry()
check("Play and Details are 42 high and as wide as their words",
      play.height() == details.height() == 42 and play.width() == play.sizeHint().width()
      and details.width() == details.sizeHint().width(), (play.size(), details.size()))
check("Play stands 36 px in and 34 px up from the card's corner",
      (play.mapTo(w, QPoint(0, 0)).x() - left, top + height - play.mapTo(w, QPoint(0, play.height())).y())
      == (36, 34), (play.mapTo(w, QPoint(0, 0)).x() - left,
                    top + height - play.mapTo(w, QPoint(0, play.height())).y()))
check("Details 10 px after it", details.x() - (play.x() + play.width()) == 10, details.x() - play.x() - play.width())
pixels = [at(shot, play.mapTo(w, QPoint(x, y))) for x in range(play.width()) for y in range(play.height())]
check("Play is not green", not any(greenish(p) for p in pixels))
check("but outlined in the accent", distance(at(shot, play.mapTo(w, QPoint(0, play.height() // 2))),
                                             rgb(ui_rules.COLOR_ACCENT)) < 30)
check("its words in the accent too", sum(1 for p in pixels if distance(p, rgb(ui_rules.COLOR_ACCENT)) < 12) > 20)
check("Details has no icon, only its word", details.icon().isNull() and details.text() == "Details")

print("\n=== 4. the words stand on the card's foot ===")
column = range(left + 36, left + 360)
rows = lambda colour, band: [y for y in band if any(distance(at(shot, QPoint(x, y)), rgb(colour)) < 14 for x in column)]
meta = rows(ui_rules.COLOR_TEXT_SOFT, range(top, play.mapTo(w, QPoint(0, 0)).y()))
play_top = play.mapTo(w, QPoint(0, 0)).y()
check("the line under the title ends 18 px or more above the buttons, as the design's gaps put it",
      bool(meta) and play_top - 18 - 22 <= max(meta) <= play_top - 18, (max(meta) if meta else None, play_top))
kicker = rows(ui_rules.COLOR_ACCENT, range(top, top + 120))
check("the eyebrow is 10 px type: its capitals about 7 px tall",
      bool(kicker) and 6 <= max(kicker) - min(kicker) + 1 <= 8, (min(kicker), max(kicker)) if kicker else None)

print("\n=== 5. the pad's ring, outside the button ===")
lib.select_key(lib.visible_keys[0])
settle(0.3)
w._on_pad_action(controller.UP)
settle(0.5)
shot = w.grab().toImage()
# The design's ring, written as the design gives it rather than read from the code: 2 px
# wide and 2 px out, so its middle is 3 px from the button's edge.
out = 3
mid = play.height() // 2
check("up from the grid lands on Play", lib.on_card and play.hasFocus())
check("ringed in the accent, 2 px out from its edge",
      distance(at(shot, play.mapTo(w, QPoint(-out, mid))), rgb(ui_rules.TILE_FOCUS_COLOR)) < 30,
      at(shot, play.mapTo(w, QPoint(-out, mid))))
check("with the gap between them not ringed",
      distance(at(shot, play.mapTo(w, QPoint(-1, mid))), rgb(ui_rules.TILE_FOCUS_COLOR)) > 30,
      at(shot, play.mapTo(w, QPoint(-1, mid))))
w._on_pad_action(controller.RIGHT)
settle(0.4)
shot = w.grab().toImage()
check("right moves the ring to Details",
      distance(at(shot, details.mapTo(w, QPoint(details.width() - 1 + out, mid))), rgb(ui_rules.TILE_FOCUS_COLOR)) < 30
      and distance(at(shot, play.mapTo(w, QPoint(-out, mid))), rgb(ui_rules.TILE_FOCUS_COLOR)) > 30)
w._on_pad_action(controller.DOWN)
settle(0.3)
shot = w.grab().toImage()
check("and down takes it away", not play.hasFocus() and not details.hasFocus()
      and distance(at(shot, details.mapTo(w, QPoint(details.width() - 1 + out, mid))),
                   rgb(ui_rules.TILE_FOCUS_COLOR)) > 30)

print("\n=== 6. Stop ===")
card.set_running(True)
settle(0.4)
shot = w.grab().toImage()
stop = card.play_button
check("Play becomes Stop", stop.objectName() == "HeroStop" and "Stop" in stop.text())
check("outlined in red", distance(at(shot, stop.mapTo(w, QPoint(0, stop.height() // 2))), rgb(ui_rules.COLOR_STOP)) < 30)
inside = at(shot, stop.mapTo(w, QPoint(4, 4)))
check("without a red fill until the mouse is on it", inside[0] < inside[2] + 40, inside)
card.set_running(False)
settle(0.3)

print("\n=== 7. TV mode's thicker ring ===")
w.set_tv_mode(True)
settle(1.5)
lib.select_key(lib.visible_keys[0])
settle(0.3)
w._on_pad_action(controller.UP)
settle(0.5)
tv = float(w.config.get("tv_scale", ui_rules.TV_SCALE_DEFAULT))
check("the card's ring is TV mode's width", card.ring_width() == max(1, round(ui_rules.TV_FOCUS_RING_WIDTH * tv))
      if hasattr(card, "ring_width") else False)
w._on_pad_action(controller.DOWN)
settle(0.3)
w.set_tv_mode(False)
settle(1.0)

print("\n=== 8. the game page's Play ===")
w.show_detail(lib.visible_keys[0])
settle(1.2)
page_play = w.detail.play_button
shot = w.grab().toImage()
pixels = [at(shot, page_play.mapTo(w, QPoint(x, y))) for x in range(0, page_play.width(), 2)
          for y in range(0, page_play.height(), 2)]
check("is outlined too, not green", not any(greenish(p) for p in pixels)
      and sum(1 for p in pixels if distance(p, rgb(ui_rules.COLOR_ACCENT)) < 12) > 10)
# A stylesheet rule until Phase 57; since then the page draws the design's ring outside it.
w.detail.focus_play()
settle(0.4)
shot = w.grab().toImage()
check("and the pad still rings it, outside it as on the card",
      distance(at(shot, page_play.mapTo(w, QPoint(-out, page_play.height() // 2))),
               rgb(ui_rules.TILE_FOCUS_COLOR)) < 30,
      at(shot, page_play.mapTo(w, QPoint(-out, page_play.height() // 2))))
w.close()

print("\n=== 9. the real library is exactly as it was found ===")
changed = box.finish()
check("overrides.json, config.json and catalog.json are byte for byte unchanged", not changed, changed)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
