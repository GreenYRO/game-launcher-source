"""Phase 59: the Nocturne restyle, step 6 of 6 -- Phosphor icons.

The design's icons in place of Windows' own: the two Phosphor fonts and their MIT licence
shipped in presentation/fonts, byte for byte the files @phosphor-icons/web 2.1.2 publishes;
every icon the app draws mapped to Phosphor's own name and the code point its style.css
gives, present in the font and inking pixels; the filled set for the solid glyphs; Windows'
icon fonts taking over in a copy without the files; and the icons on the live window --
the filled controller in the top bar, the outlined one on a pill, the broom on Storage's
strip. Runs on a throwaway copy of the data; nothing is started.
"""
import base64
import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))  # the project folder, one up from tests/
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import test_sandbox

box = test_sandbox.start()

import logging

logging.basicConfig(level=logging.ERROR)

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtGui import QFont, QFontDatabase, QFontMetrics
from PySide6.QtWidgets import QApplication

app = QApplication([])

from logic import focus
from presentation import ui_icons, ui_rules, ui_window

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


def inked(pixmap) -> int:
    """Every pixel the glyph touches: Phosphor's three dots are its smallest, 16 solid
    pixels and 48 touched at 32 px; a missing glyph touches none."""
    image = pixmap.toImage()
    return sum(1 for y in range(image.height()) for x in range(image.width())
               if image.pixelColor(x, y).alpha() > 0)


FOLDER = PROJECT / "presentation" / "fonts"
# The sizes and sha256 hashes cdn.jsdelivr.net publishes for @phosphor-icons/web 2.1.2.
PUBLISHED = {
    "Phosphor.ttf": (488636, "BrkeAit+6JmmPvzth5OSp08LrL2lTkRn6fZjIg0XOhA="),
    "Phosphor-Fill.ttf": (449252, "pT9dJjDKteO3U27LnWnXFRmiGQKYwisfjXcN03vClAo="),
    "Phosphor-LICENSE.txt": (1076, "aH++UtDrXCNT7KJ6QDfoiRRe4LWE07Gr9nWBxKSk5Hw="),
}
# What the design names, for the icons it shows (README, step 6), and the style it uses.
DESIGN = {
    "brand": ("fill", "game-controller"), "search": ("regular", "magnifying-glass"),
    "shuffle": ("regular", "shuffle"), "refresh": ("regular", "arrows-clockwise"),
    "settings": ("regular", "gear-six"), "chevron_left": ("regular", "caret-left"),
    "chevron_right": ("regular", "caret-right"), "back": ("regular", "arrow-left"),
    "play_solid": ("fill", "play"), "star_full": ("fill", "star"), "clock": ("regular", "clock"),
    "calendar": ("regular", "calendar-blank"), "disk": ("regular", "hard-drive"),
    "save": ("regular", "floppy-disk"), "folder": ("regular", "folder-open"),
    "more": ("regular", "dots-three"), "controller": ("regular", "game-controller"),
    "broom": ("regular", "broom"),
}

print("\n=== 1. the files ===")
for name, (size, digest) in PUBLISHED.items():
    path = FOLDER / name
    data = path.read_bytes() if path.is_file() else b""
    if name.endswith(".txt"):
        # Text: git may hand it back with Windows line endings; the words are what count.
        data = data.replace(b"\r\n", b"\n")
    found = base64.b64encode(hashlib.sha256(data).digest()).decode()
    check(f"{name} is the published file, byte for byte", (len(data), found) == (size, digest),
          (len(data), found))
licence = FOLDER / "Phosphor-LICENSE.txt"
check("the licence is MIT, Phosphor Icons'", licence.is_file()
      and "MIT License" in licence.read_text(encoding="utf-8")
      and "Phosphor Icons" in licence.read_text(encoding="utf-8"))

# The code before this phase has none of this: judged check by check, not crashed.
glyph_for = getattr(ui_icons, "glyph_for", lambda name: ("", ""))

print("\n=== 2. the families ===")
bundled = ui_icons.bundled_families()
check("both register beside Inter", {"Phosphor", "Phosphor-Fill"} <= set(bundled), bundled)
check("Phosphor is the icon font, Windows' own behind it",
      ui_icons.icon_family() == "Phosphor" and ui_rules.ICON_FONT_FAMILIES[1:]
      == ("Segoe Fluent Icons", "Segoe MDL2 Assets"), (ui_icons.icon_family(), ui_rules.ICON_FONT_FAMILIES))

print("\n=== 3. every icon ===")
table = getattr(ui_icons, "PHOSPHOR", {})
check("every icon the app draws has a Phosphor glyph", bool(table) and set(ui_icons.GLYPHS) == set(table),
      sorted(set(ui_icons.GLYPHS) ^ set(table)))
missing, blank = [], []
for name, (style, _phosphor, code) in table.items():
    family = "Phosphor-Fill" if style == "fill" else "Phosphor"
    if not QFontMetrics(QFont(family)).inFontUcs4(code):
        missing.append((name, family, hex(code)))
    if inked(ui_icons.glyph_pixmap(name, "#ffffff", 32)) < 20:
        blank.append(name)
check("each code point is in its font", bool(table) and not missing, missing)
check(f"and every one of the {len(table)} draws something", bool(table) and not blank, blank)
wrong = {name: table.get(name, ("", ""))[:2] for name, want in DESIGN.items() if table.get(name, ("", ""))[:2] != want}
check("each is the glyph the design names, in the design's style", not wrong, wrong)
check("a solid glyph comes from the filled set",
      glyph_for("play_solid")[0] == "Phosphor-Fill" and glyph_for("brand")[0] == "Phosphor-Fill"
      and glyph_for("star")[0] == "Phosphor")
solid = lambda pixmap: sum(1 for y in range(pixmap.toImage().height())  # noqa: E731 -- fully covered only
                          for x in range(pixmap.toImage().width()) if pixmap.toImage().pixelColor(x, y).alpha() > 128)
full, outline = solid(ui_icons.glyph_pixmap("star_full", "#ffffff", 32)), solid(ui_icons.glyph_pixmap("star", "#ffffff", 32))
check("and is filled: the full star covers well over the outline's pixels", full > 1.6 * outline, (full, outline))

print("\n=== 4. a copy without the files ===")
with tempfile.TemporaryDirectory() as scratch:
    for path in FOLDER.glob("Inter-*"):
        shutil.copy(path, scratch)
    fallback = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, sys.argv[1])\n"
         "from PySide6.QtWidgets import QApplication\n"
         "app = QApplication([])\n"
         "from presentation import ui_icons, ui_rules\n"
         "ui_rules.FONTS_FOLDER = (sys.argv[2],)\n"
         "from shared import paths\n"
         "paths.resource_dir = lambda: __import__('pathlib').Path('/')\n"
         "family, char = ui_icons.glyph_for('search')\n"
         "image = ui_icons.glyph_pixmap('broom', '#ffffff', 32).toImage()\n"
         "ink = sum(1 for y in range(32) for x in range(32) if image.pixelColor(x, y).alpha() > 128)\n"
         "print(family, hex(ord(char)) if char else '-', ink, sep='|')",
         str(PROJECT), scratch],
        capture_output=True, text=True, timeout=60)
found = fallback.stdout.strip().split("|")
check("Windows' own icon font takes over, with its own code points",
      len(found) == 3 and found[0] in ("Segoe Fluent Icons", "Segoe MDL2 Assets") and found[1] == "0xe721",
      (fallback.stdout.strip(), fallback.stderr[-300:]))
check("and an icon Windows has no glyph for still draws its stand-in",
      len(found) == 3 and found[2].isdigit() and int(found[2]) >= 20, found)

print("\n=== 5. on the window ===")
w = ui_window.MainWindow()
w.resize(1280, 820)
w.move(app.primaryScreen().availableGeometry().topLeft())
w.show()
settle(2.0)
focus.bring_to_front(int(w.winId()))
settle(0.3)
brand = w.top_bar.brand.pixmap()
check("the top bar's brand is the filled controller",
      brand is not None and not brand.isNull() and glyph_for("brand") == ("Phosphor-Fill", chr(0xE26E)))
from presentation import ui_detail

check("the controller pill is the outlined one", dict(ui_detail.PILLS).get("Controller") == "controller",
      dict(ui_detail.PILLS).get("Controller"))
w.show_storage()
settle(1.0)
strip = w.storage_page.reclaim_icon.pixmap()
px = max(12, round(ui_rules.STORAGE_RECLAIM_ICON_PX * w.scale))
broom = ui_icons.glyph_pixmap("broom", ui_rules.COLOR_TEXT_MUTED, px, w.storage_page.devicePixelRatioF() or 1.0)
check("Storage's strip carries the broom", strip is not None and strip.toImage() == broom.toImage())
w.show_detail(w.library.visible_keys[0])
settle(1.0)
check("the page's Play wears the filled play", not w.detail.play_button.icon().isNull()
      and glyph_for("play_solid")[0] == "Phosphor-Fill")
w.close()

print("\n=== 6. the real library is exactly as it was found ===")
changed = box.finish()
check("overrides.json, config.json and catalog.json are byte for byte unchanged", not changed, changed)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
