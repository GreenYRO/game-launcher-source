"""Phase 22: the controller's battery in the TV hint bar.

Nothing here writes to overrides.json -- this phase stores nothing -- but the file is
photographed at the start and compared at the end anyway, because the window is
constructed and the window touches data.

The real pad is read where one is attached. Whatever it answers is reported rather than
asserted: "wired" and "unknown" are both legitimate answers from real hardware, and a test
that demanded a charge level would fail on a plugged-in DualSense, which is exactly the
situation this machine is in.
"""
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # the project folder, one up from tests/
os.chdir(Path(__file__).resolve().parents[1])

import logging

logging.basicConfig(level=logging.ERROR)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REAL = Path(__file__).resolve().parents[1] / "data"  # the real data, in its own folder since Phase 48

passed = failed = 0


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"   PASS  {name}")
    else:
        failed += 1
        print(f"   FAIL  {name}   {detail}")


import test_sandbox  # the library helpers (Phase 66); the sandbox itself is run_sandboxed's

test_sandbox.require_sandbox(__file__)  # never on the real data, run bare (Phase 101)

overrides_before = test_sandbox.real_records()
overrides_stamp = test_sandbox.real_stamp()
config_before = json.loads((REAL / "config.json").read_text(encoding="utf-8"))

from shared import rules
from presentation import ui_rules

print("\n=== 1. what this machine's pad actually reports ===")
from adapters import controller

hub_available = controller.pygame is not None
print(f"   pygame present: {hub_available}")
if hub_available:
    controller.pygame.init()
    controller.pygame.joystick.init()
    count = controller.pygame.joystick.get_count()
    print(f"   joysticks attached: {count}")
    for index in range(count):
        stick = controller.pygame.joystick.Joystick(index)
        level = controller._joystick_power(index)
        print(f"     [{index}] {stick.get_name()!r} -> {level!r}")
        check(f"device {index} answers something we know how to draw",
              level == rules.POWER_UNKNOWN
              or level == rules.POWER_WIRED
              or level in rules.POWER_STEPS,
              level)
    if count == 0:
        print("   (no pad attached right now; the glyph would simply never appear)")
    check("reading a device that is not there is not a crash",
          controller._joystick_power(99) == rules.POWER_UNKNOWN)

print("\n=== 2. the glyph shows a level, shows a plug, or shows nothing ===")
from PySide6.QtWidgets import QApplication

from presentation import ui_theme
from presentation import ui_tv

app = QApplication.instance() or QApplication([])
metrics = ui_theme.Metrics(ui_rules.UI_SCALE_DEFAULT)

glyph = ui_tv.BatteryGlyph(metrics)
for level in rules.POWER_STEPS:
    glyph.set_level(level)
    check(f"{level!r} draws a battery", glyph.shows_anything and glyph.width() > 0)

glyph.set_level(rules.POWER_WIRED)
check("'wired' draws a plug", glyph.shows_anything and glyph.width() > 0)
check("and says so in the tooltip", "cable" in glyph.toolTip(), glyph.toolTip())

for level in (rules.POWER_UNKNOWN, "", None, "nonsense"):
    glyph.set_level(level)
    check(f"{level!r} draws nothing at all", not glyph.shows_anything)
    check("   and takes up no room", glyph.width() == 0 and glyph.height() == 0,
          (glyph.width(), glyph.height()))
    check("   and offers no tooltip", glyph.toolTip() == "", glyph.toolTip())

print("\n=== 3. a low battery is a different colour from a healthy one ===")
from PySide6.QtGui import QColor


def drawn_colours(level: str, scale: float = 1.6) -> set:
    g = ui_tv.BatteryGlyph(ui_theme.Metrics(scale))
    g.set_level(level)
    image = g.grab().toImage()
    seen = set()
    for y in range(image.height()):
        for x in range(image.width()):
            pixel = image.pixelColor(x, y)
            if pixel.alpha() > 200:
                seen.add((pixel.red(), pixel.green(), pixel.blue()))
    return seen


warning = QColor(ui_rules.COLOR_WARNING)
warning_rgb = (warning.red(), warning.green(), warning.blue())
muted = QColor(ui_rules.COLOR_TEXT_MUTED)
muted_rgb = (muted.red(), muted.green(), muted.blue())

low = drawn_colours(rules.POWER_STEPS[0])
mid = drawn_colours(rules.POWER_STEPS[-1])
wired_pixels = drawn_colours(rules.POWER_WIRED)
print(f"   warning colour {warning_rgb} in 'empty': {warning_rgb in low}")
print(f"   warning colour {warning_rgb} in 'max':   {warning_rgb in mid}")
check("an all-but-flat battery is drawn in the warning colour", warning_rgb in low)
check("a healthy one is not", warning_rgb not in mid)
check("and is drawn in the ordinary muted colour instead", muted_rgb in mid)
check("a plug never warns -- a cable is not a low battery", warning_rgb not in wired_pixels)

print("\n=== 4. the bar is exactly as tall with the glyph as without it ===")
heights = {}
widths = {}
for scale in (ui_rules.TV_SCALE_CHOICES[0], ui_rules.TV_SCALE_CHOICES[-1]):
    for level in (rules.POWER_UNKNOWN, rules.POWER_WIRED, *rules.POWER_STEPS):
        bar = ui_tv.HintBar(ui_theme.Metrics(scale))
        bar.set_power(level)
        bar.resize(bar.sizeHint())
        heights.setdefault(scale, {})[level] = bar.height()
        widths.setdefault(scale, {})[level] = bar.width()
        bar.deleteLater()
for scale, by_level in heights.items():
    print(f"   tv_scale {scale}: heights {sorted(set(by_level.values()))}, "
          f"widths {sorted(set(widths[scale].values()))}")
    check(f"one height at {scale}x whatever the pad says", len(set(by_level.values())) == 1,
          by_level)
    check(f"the glyph does cost width at {scale}x",
          widths[scale][rules.POWER_WIRED] > widths[scale][rules.POWER_UNKNOWN])

print("\n=== 5. the glyph follows the interface scale like everything else ===")
small = ui_tv.BatteryGlyph(ui_theme.Metrics(ui_rules.TV_SCALE_CHOICES[0]))
large = ui_tv.BatteryGlyph(ui_theme.Metrics(ui_rules.TV_SCALE_CHOICES[-1]))
for g in (small, large):
    g.set_level(rules.POWER_STEPS[-1])
print(f"   {ui_rules.TV_SCALE_CHOICES[0]}x -> {small.width()}x{small.height()}, "
      f"{ui_rules.TV_SCALE_CHOICES[-1]}x -> {large.width()}x{large.height()}")
check("a bigger setting draws a bigger glyph", large.height() > small.height())
check("it stays a battery shape, not a square",
      abs(large.width() / large.height() - ui_rules.BATTERY_ASPECT) < 0.2)
small.set_level(rules.POWER_UNKNOWN)
check("apply_metrics on a hidden glyph keeps it hidden", (small.apply_metrics(
    ui_theme.Metrics(ui_rules.TV_SCALE_CHOICES[-1])), small.width() == 0)[1])

print("\n=== 6. Play something is advertised on the bar ===")
labels = [label for _x, _p, label in ui_tv.HINTS]
glyphs = [x for x, _p, _l in ui_tv.HINTS]
print(f"   hints: {list(zip(glyphs, labels))}")
check("Y / triangle is listed", "Y" in glyphs and "△" in [p for _x, p, _l in ui_tv.HINTS])
check("and it says what it does", any("Play something" in label for label in labels))

print("\n=== 7. the window wires the pad's power to the bar ===")
from presentation import ui_window

win = ui_window.MainWindow()
win.resize(1200, 850)
win.show()
end = time.time() + 1.2
while time.time() < end:
    app.processEvents()
    time.sleep(0.02)

check("the hub reports a level", isinstance(win.pads.power_level(), str))
print(f"   the hub currently reports: {win.pads.power_level()!r}")
check("the bar agrees with the hub",
      win.hint_bar.battery.level == win.pads.power_level(),
      (win.hint_bar.battery.level, win.pads.power_level()))

was_tv = win.tv_mode
win.set_tv_mode(True)
app.processEvents()
check("the bar is visible in TV mode", win.hint_bar.isVisible())
check("and still agrees after the switch",
      win.hint_bar.battery.level == win.pads.power_level())
seen_in_tv = win.hint_bar.battery.shows_anything
print(f"   glyph visible in TV mode right now: {seen_in_tv}")

# Drive it through every state the way the hub would, and confirm the bar follows.
for level in (rules.POWER_STEPS[0], rules.POWER_WIRED, rules.POWER_UNKNOWN):
    win.pads.powerChanged.emit(level)
    app.processEvents()
    check(f"the bar follows the pad to {level!r}", win.hint_bar.battery.level == level)
win.set_tv_mode(was_tv)
app.processEvents()

check("the poll interval is a named constant", isinstance(rules.CONTROLLER_POWER_POLL_MS, int))
check("and is a minute or more -- a battery does not move fast",
      rules.CONTROLLER_POWER_POLL_MS >= 60000, rules.CONTROLLER_POWER_POLL_MS)
check("the hub stops its power timer when it stops",
      hasattr(win.pads, "_power_timer"))

win.close()
app.processEvents()

print("\n=== 8. nothing of the user's was written ===")
check("overrides.json was not touched",
      test_sandbox.real_stamp() == overrides_stamp)
check("and its records are unchanged",
      test_sandbox.real_records() == overrides_before)
after = json.loads((REAL / "config.json").read_text(encoding="utf-8"))
changed = {k for k in set(after) | set(config_before) if after.get(k) != config_before.get(k)}
print(f"   config keys that changed: {sorted(changed) or 'none'}")
check("config.json only ever changed tv_mode, if anything",
      changed <= {"tv_mode"}, sorted(changed))
if config_before.get("tv_mode") != after.get("tv_mode"):
    (REAL / "config.json").write_text(
        json.dumps(config_before, indent=2), encoding="utf-8"
    )
    print("   (put tv_mode back the way it was found)")

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
