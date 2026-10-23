"""Phase 50: the TV hint bar draws the pad's real buttons, in the family of the pad in use.

Asked for from use: the bar's letters and symbols ("A / ✕", "LB·RB / L1·R1") broke the
experience; it should show actual buttons. Now each button is painted (ui_buttons) -- an
Xbox-layout pad, like the 8BitDo Ultimate 2C plugged in here, gets A B X Y in their
colours; a DualSense gets ✕ ○ □ △ in theirs -- and the bar follows whichever pad is in use.
Runs on a throwaway copy of the data; nothing is started.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # the project folder, one up from tests/
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import test_sandbox

box = test_sandbox.start()

import logging

logging.basicConfig(level=logging.ERROR)

from PySide6.QtCore import QEventLoop, QPoint, QTimer
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication, QLabel

app = QApplication([])

from adapters import controller
from presentation import ui_buttons
from presentation import ui_rules
from presentation import ui_theme
from presentation import ui_tv
from presentation import ui_window
from shared import rules

passed = failed = 0


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"   PASS  {name}")
    else:
        failed += 1
        print(f"   FAIL  {name}   {detail}")


def settle(seconds=0.4):
    """A local event loop -- never app.exec() ended by app.quit() (the Phase 31 lesson)."""
    loop = QEventLoop()
    QTimer.singleShot(round(seconds * 1000), loop.quit)
    loop.exec()


def drawn(button, family, height=48) -> QImage:
    glyph = ui_buttons.ButtonGlyph(button, family, height)
    image = QImage(glyph.size(), QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    glyph.render(painter, QPoint(0, 0))
    painter.end()
    return image


def pixels(image, near=None, tolerance=40):
    """How many pixels are inked -- or, given a colour, close to that colour."""
    count = 0
    for y in range(image.height()):
        for x in range(image.width()):
            c = image.pixelColor(x, y)
            if c.alpha() < 128:
                continue
            if near is None:
                count += 1
            elif abs(c.red() - near.red()) + abs(c.green() - near.green()) + abs(c.blue() - near.blue()) < tolerance:
                count += 1
    return count


print("\n=== 1. which buttons a pad has, from its name ===")
for name, family in (("(8BitDo Ultimate 2C Wireless Controller)", rules.PAD_XBOX),
                     ("Xbox Series X Controller", rules.PAD_XBOX),
                     ("PS5 Controller", rules.PAD_PLAYSTATION),
                     ("DualSense Wireless Controller", rules.PAD_PLAYSTATION),
                     ("PS4 Controller", rules.PAD_PLAYSTATION),
                     ("Sony Interactive Entertainment Wireless Controller", rules.PAD_PLAYSTATION)):
    check(f"{name} -> {family}", controller.family_of(name) == family, controller.family_of(name))
check("\"wireless controller\" alone is not PlayStation (it is in the 8BitDo's name)",
      controller.family_of("Wireless Controller") == rules.PAD_XBOX)


class FakePad:
    def __init__(self, name):
        self.name = name


hub = controller.ControllerHub(lambda: True)
heard = []
hub.familyChanged.connect(heard.append)
check("no pad: no family", hub.family() == "")
hub._pads = {1: FakePad("(8BitDo Ultimate 2C Wireless Controller)")}
hub._note_family()
hub._note_family()
check("the 8BitDo makes the hub say xbox, once", heard == [rules.PAD_XBOX], heard)
hub._pads[2] = FakePad("DualSense Wireless Controller")
hub._active_id = 2
hub._note_family()
check("picking up the DualSense makes it say playstation", heard[-1:] == [rules.PAD_PLAYSTATION], heard)

print("\n=== 2. every button is drawn, in its own colours ===")
kinds = [ui_buttons.FACE_SOUTH, ui_buttons.FACE_EAST, ui_buttons.FACE_WEST, ui_buttons.FACE_NORTH,
         ui_buttons.SHOULDERS, ui_buttons.VIEW, ui_buttons.MENU, ui_buttons.DPAD_ACROSS, ui_buttons.DPAD_UPDOWN]
for family in (rules.PAD_XBOX, rules.PAD_PLAYSTATION):
    empty = [k for k in kinds if pixels(drawn(k, family)) < 200]
    check(f"{family}: all nine buttons ink pixels", not empty, empty)
faces = {ui_buttons.FACE_SOUTH: (ui_rules.COLOR_PAD_A, ui_rules.COLOR_PAD_CROSS),
         ui_buttons.FACE_EAST: (ui_rules.COLOR_PAD_B, ui_rules.COLOR_PAD_CIRCLE),
         ui_buttons.FACE_WEST: (ui_rules.COLOR_PAD_X, ui_rules.COLOR_PAD_SQUARE),
         ui_buttons.FACE_NORTH: (ui_rules.COLOR_PAD_Y, ui_rules.COLOR_PAD_TRIANGLE)}
for face, (xbox_colour, ps_colour) in faces.items():
    on_xbox = pixels(drawn(face, rules.PAD_XBOX), QColor(xbox_colour))
    on_ps = pixels(drawn(face, rules.PAD_PLAYSTATION), QColor(ps_colour))
    check(f"the {face} button carries Xbox's colour on an Xbox pad and PlayStation's on a DualSense",
          on_xbox > 20 and on_ps > 20, (on_xbox, on_ps))
different = [k for k in kinds if drawn(k, rules.PAD_XBOX) == drawn(k, rules.PAD_PLAYSTATION)]
check("the face buttons, bumpers and middle buttons differ between the families",
      set(different) <= {ui_buttons.DPAD_ACROSS, ui_buttons.DPAD_UPDOWN}, different)
across, updown = drawn(ui_buttons.DPAD_ACROSS, rules.PAD_XBOX), drawn(ui_buttons.DPAD_UPDOWN, rules.PAD_XBOX)
check("the d-pad says left/right and up/down differently", across != updown)
names = [n for n in dir(ui_rules) if n.startswith("COLOR_PAD_")]
check(f"every pad colour is one QColor can read ({len(names)})",
      all(QColor(getattr(ui_rules, n)).isValid() for n in names), names)

print("\n=== 3. the real window's bar, in TV mode ===")
w = ui_window.MainWindow()
w.resize(1400, 900)
w.move(app.primaryScreen().availableGeometry().topLeft())
w.show()
settle(1.0)
w.set_tv_mode(True)
settle(1.5)
bar = w.hint_bar
text_chips = [label.text() for label in bar.findChildren(QLabel) if " / " in label.text() and label.objectName() != "HintText"]
check("no text chip is left (\"A / ✕\" and the like)", not text_chips, text_chips)
check("a drawn button for every hint", len(bar.glyphs) == len(ui_tv.HINT_SETS[bar.hints])
      and all(isinstance(g, ui_buttons.ButtonGlyph) for g in bar.glyphs), len(bar.glyphs))
check("and the words are the same as before", bar.labels == [label for _p, label in ui_tv.HINT_SETS[bar.hints]],
      bar.labels)

w.pads.familyChanged.emit(rules.PAD_PLAYSTATION)
settle(0.3)
check("a DualSense picked up: the bar draws PlayStation's buttons",
      bar.family == rules.PAD_PLAYSTATION and all(g.family == rules.PAD_PLAYSTATION for g in bar.glyphs))
w.pads.familyChanged.emit(rules.PAD_XBOX)
settle(0.3)
check("the 8BitDo again: Xbox's", all(g.family == rules.PAD_XBOX for g in bar.glyphs))
w.pads.familyChanged.emit("")
settle(0.3)
check("no pad at all keeps the Xbox drawing", bar.family == rules.PAD_XBOX)

# No dark box around a hint: the gap between a button and its words is the bar's own colour.
shot = w.grab().toImage()
item = bar._chips[0]
glyph = bar.glyphs[0]
inside = item.mapTo(w, QPoint(glyph.geometry().right() + 2, item.height() // 2))
outside = item.mapTo(w, QPoint(-6, item.height() // 2))
a, b = shot.pixelColor(inside), shot.pixelColor(outside)
gap = abs(a.red() - b.red()) + abs(a.green() - b.green()) + abs(a.blue() - b.blue())
check("no dark box behind a hint (the blanket QWidget background, the Phase 32 trap)", gap < 6,
      (a.name(), b.name()))

print("\n=== 4. every TV size, both families, every set ===")
heights, widest, worst = set(), 0, ""
was = w.config.get("tv_scale")
for scale in ui_rules.TV_SCALE_CHOICES:
    w.config["tv_scale"] = scale
    w.set_tv_mode(False)
    w.set_tv_mode(True)
    settle(0.3)
    for family in (rules.PAD_XBOX, rules.PAD_PLAYSTATION):
        bar.set_family(family)
        for name in ui_tv.HINT_SETS:
            bar.set_hints(name)
            app.processEvents()
            heights.add((scale, bar.height()))
            if bar.sizeHint().width() > widest:
                widest, worst = bar.sizeHint().width(), f"{name} at {scale}x, {family}"
by_scale = {}
for scale, height in heights:
    by_scale.setdefault(scale, set()).add(height)
check("the bar is one height per TV size, whatever it shows", all(len(h) == 1 for h in by_scale.values()),
      by_scale)
check(f"every set fits a 1080p screen at every TV size (widest {widest}px: {worst})", widest <= 1920, widest)
w.config["tv_scale"] = was
bar.set_hints(ui_tv.LIBRARY)
w.set_tv_mode(False)
w.close()

print("\n=== 5. the real library is exactly as it was found ===")
changed = box.finish()
check("overrides.json, config.json and catalog.json are byte for byte unchanged", not changed, changed)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
