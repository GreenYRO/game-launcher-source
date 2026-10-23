"""Phase 54: the Nocturne restyle, step 1 of 6 -- the palette, Inter, the weights, the radii.

The design handoff's token table is the specification, and it is copied into TABLE below so
this suite does not depend on the handoff folder being present. Inter is shipped in
presentation/fonts and must be the face in use -- a real Medium, not a synthesised one --
with Windows' Segoe taking over when the folder is missing. Runs on a throwaway copy of
the data; the window is built but nothing is started.
"""
import inspect
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))  # the project folder, one up from tests/
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import test_sandbox

box = test_sandbox.start()

import logging

logging.basicConfig(level=logging.ERROR)

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontInfo
from PySide6.QtWidgets import QApplication, QLabel

app = QApplication([])

from presentation import (ui_continue, ui_detail, ui_icons, ui_pageshell, ui_rules, ui_settings,
                          ui_stats, ui_theme, ui_topbar, ui_window)

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


# The handoff's table: role -> (value, the constants that take it).
DIVIDER = "rgba(233, 233, 237, 41)"
TABLE = {
    "ground": ("#161826", ("COLOR_BACKGROUND", "COLOR_SCRIM")),
    "surface": ("#232532", ("COLOR_SURFACE", "COLOR_CARD")),
    # The chart's quiet-month stub left the raised surface for accent 700 in Phase 58.
    "raised surface": ("#292b31", ("COLOR_SURFACE_RAISED", "COLOR_STORAGE_FREE")),
    "hairline edge": ("#3f424d", ("COLOR_BORDER", "COLOR_CARD_BORDER", "COLOR_SWITCH_OFF",
                                  "COLOR_CHART_UNRECORDED")),
    "divider on glass": (DIVIDER, ("COLOR_CHIP_BORDER", "COLOR_PILL_BORDER", "COLOR_GHOST_BORDER",
                                   "COLOR_NAV_BORDER")),
    "text": ("#e9e9ed", ("COLOR_TEXT",)),
    "soft text": ("#cfd3e5", ("COLOR_TEXT_SOFT",)),
    "muted text": ("#9397ab", ("COLOR_TEXT_MUTED",)),
    "disabled": ("#595d6c", ("COLOR_DISABLED", "COLOR_STORAGE_OTHER")),
    # The focus ring joined the accent in Phase 55 -- the mockup's library ring and the brief's
    # "the colour is the accent" -- where the table had it at accent 200.
    "accent": ("#9184d9", ("COLOR_ACCENT", "COLOR_CHART_BAR", "COLOR_STORAGE_GAMES", "COLOR_SESSION_BAR_END",
                           "TILE_FOCUS_COLOR")),
    "accent hover": ("#b5abfc", ("COLOR_ACCENT_HOVER",)),
    "accent 300": ("#d2cefd", ("FAVORITE_BADGE_COLOR",)),
    "accent 200": ("#e7e5fe", ("COLOR_ACCENT_200",)),
    "accent 100": ("#f5f4ff", ("NEW_BADGE_TEXT_COLOR",)),
    "accent 700": ("#5d5294", ("COLOR_SESSION_BAR_START", "COLOR_CHART_BASELINE")),
    "accent 800": ("#423a6a", ("NEW_BADGE_COLOR",)),
}
STATUS = {"playing": "#b5abfc", "finished": "#d2cefd", "dropped": "#9397ab"}
RADII = {"TILE_CORNER_RADIUS": 8, "CONTINUE_RADIUS": 14, "DETAIL_COVER_RADIUS": 14,
         "DETAIL_CARD_RADIUS": 8, "STORAGE_ROW_RADIUS": 8}
FONT_FILES = ("Inter-Regular.ttf", "Inter-Medium.ttf", "Inter-SemiBold.ttf", "Inter-Italic.ttf",
              "Inter-MediumItalic.ttf", "Inter-LICENSE.txt")

print("\n=== 1. the token table is in ui_rules ===")
wrong = []
for role, (value, names) in TABLE.items():
    for name in names:
        have = getattr(ui_rules, name, None)
        same = have == value if value.startswith("rgba") else (
            isinstance(have, str) and QColor(have).isValid() and QColor(have).name() == value)
        if not same:
            wrong.append(f"{name}={have!r} (want {role} {value})")
check(f"every constant the table names has its value ({sum(len(n) for _, n in TABLE.values())} constants)",
      not wrong, wrong)
check("the three marks share the accent's ramp and the muted text",
      {k: QColor(v).name() for k, v in ui_rules.STATUS_COLORS.items()} == STATUS, ui_rules.STATUS_COLORS)
check("the radii are the design's", {k: getattr(ui_rules, k) for k in RADII} == RADII,
      {k: getattr(ui_rules, k) for k in RADII})
pure = []
for name, value in vars(ui_rules).items():
    if not name.isupper() or not isinstance(value, str):
        continue
    text = value.replace(" ", "").lower()
    if text.startswith(("rgba(255,255,255", "rgba(0,0,0")) or (
            QColor(value).isValid() and value.startswith("#")
            and QColor(value).name() in ("#ffffff", "#000000")):
        pure.append(f"{name}={value}")
check("no pure white or black left among the appearance constants", not pure, pure)

print("\n=== 2. Inter is shipped, loaded and in use ===")
# getattr, here and below: so the code before this phase can be judged rather than crash.
folder = PROJECT.joinpath(*getattr(ui_rules, "FONTS_FOLDER", ("presentation", "fonts")))
bundled = getattr(ui_icons, "bundled_families", lambda: ())()
HEADING = getattr(ui_rules, "HEADING_WEIGHT", None)
LABEL = getattr(ui_rules, "LABEL_WEIGHT", None)
BODY = getattr(ui_rules, "BODY_WEIGHT", None)
tracking = getattr(ui_theme, "tracking", lambda pixels: 0.0)
check("presentation/fonts holds the five faces and the licence",
      all((folder / name).is_file() for name in FONT_FILES), sorted(p.name for p in folder.glob("*")))
licence = folder / "Inter-LICENSE.txt"
check("the licence is the SIL Open Font License",
      licence.is_file() and "SIL Open Font License" in licence.read_text(encoding="utf-8"))
# Windows also lists a static file under a legacy per-weight name ("Inter Medium",
# "Inter SemiBold"); the weights below prove they are all faces of the one family.
# Phosphor's two icon fonts joined them in Phase 59; every other family is an Inter one.
check("they register as Inter, every family name an Inter one",
      bundled[:1] == ("Inter",)
      and all(name.startswith("Inter") or name in ("Phosphor", "Phosphor-Fill") for name in bundled), bundled)
# Titles are in Inter Display since Phase 62, Inter's own cut for large text.
check("the body face is Inter, the display face Inter Display",
      (ui_icons.body_family(), ui_icons.display_family()) == ("Inter", "Inter Display"),
      (ui_icons.body_family(), ui_icons.display_family()))
styles = set(QFontDatabase.styles("Inter"))
check("with a real face for every weight and style used",
      {"Regular", "Medium", "SemiBold", "Bold", "Italic", "Medium Italic"} <= styles, sorted(styles))
# One step heavier since Phase 62: ordinary text Medium, headings SemiBold, the labels Bold.
for weight, style in ((BODY or 400, "Medium"), (HEADING or 500, "SemiBold"), (LABEL or 600, "Bold")):
    font = QFont("Inter")
    font.setPixelSize(20)
    font.setWeight(QFont.Weight(weight))
    info = QFontInfo(font)
    check(f"weight {weight} draws Inter's own {style} face, not a faked one",
          info.family() == "Inter" and info.styleName() == style, (info.family(), info.styleName()))

fallback = subprocess.run(
    [sys.executable, "-c",
     "import sys; sys.path.insert(0, sys.argv[1])\n"
     "from PySide6.QtWidgets import QApplication\n"
     "app = QApplication([])\n"
     "from presentation import ui_icons, ui_rules\n"
     "ui_rules.FONTS_FOLDER = ('no such folder',)\n"
     "print(ui_icons.bundled_families(), ui_icons.body_family(), ui_icons.display_family(), sep='|')",
     str(PROJECT)],
    capture_output=True, text=True, timeout=60)
found = fallback.stdout.strip().split("|")
check("with the folder missing, Windows' own faces take over",
      len(found) == 3 and found[0] == "()" and found[1] in ui_rules.FONT_BODY_FAMILIES[1:]
      and found[2] in ui_rules.FONT_DISPLAY_FAMILIES[1:], (fallback.stdout.strip(), fallback.stderr[-200:]))

print("\n=== 3. titles and headings are SemiBold (Medium until Phase 62) ===")
check("ordinary text 500, the heading weight 600, the two small labels 700, tile names DemiBold",
      (BODY, HEADING, LABEL, ui_rules.TILE_NAME_WEIGHT) == (500, 600, 700, "DemiBold"),
      (BODY, HEADING, LABEL, ui_rules.TILE_NAME_WEIGHT))
weights = {}
for module in (ui_theme, ui_detail, ui_continue, ui_pageshell, ui_settings, ui_stats, ui_topbar):
    for name, function in inspect.getmembers(module, inspect.isfunction):
        if "stylesheet" in name and function.__module__ == module.__name__:
            text = function(*([1.0] if inspect.signature(function).parameters else []))
            weights[f"{module.__name__}.{name}"] = sorted(
                {part.split(";")[0].strip() for part in text.split("font-weight:")[1:]})
# Since Phase 62 every stylesheet asks for the heading weight, 600, and nothing heavier;
# ordinary text, 500, is asked for in three places only -- the window's own rule, the game
# page's three marks, which the design sets as ordinary text, and (Phase 75) the same
# segmented switch in Settings, a Steam account's mark.
ordinary = ("presentation.ui_theme.stylesheet", "presentation.ui_detail.stylesheet",
            "presentation.ui_settings.stylesheet")
check(f"every one of the {len(weights)} stylesheets asks for 600 and nothing heavier, 500 only for ordinary text",
      len(weights) == 7 and all(found == (["500", "600"] if name in ordinary else ["600"])
                                for name, found in weights.items()), weights)

print("\n=== 4. big titles are set tighter ===")
check("tracking: none under 40 px, -0.02 em from 40, -0.025 em from 46",
      (tracking(30), round(tracking(40), 3), round(tracking(48), 3))
      == (0.0, -0.8, -1.2), (tracking(30), tracking(40), tracking(48)))
sheet = ui_detail.stylesheet(1.0)
# The title was 48 px until Phase 57 (-1.20 px); the design's 46 px carries -1.15.
spacing = f"letter-spacing: {tracking(ui_rules.DETAIL_TITLE_PX):.2f}px"
check("the game page's title carries it", ui_rules.DETAIL_TITLE_PX == 46 and spacing in sheet, spacing)
plain, tight = QLabel("The Witcher 3: Wild Hunt"), QLabel("The Witcher 3: Wild Hunt")
plain.setObjectName("HeroTitle")
tight.setObjectName("HeroTitle")
plain.setStyleSheet(sheet.replace(spacing + ";", ""))
tight.setStyleSheet(sheet)
for label in (plain, tight):
    label.ensurePolished()
check("and Qt draws it narrower for it", tight.sizeHint().width() < plain.sizeHint().width() - 15,
      (plain.sizeHint().width(), tight.sizeHint().width()))

print("\n=== 5. the window itself ===")
w = ui_window.MainWindow()
w.resize(1280, 820)
w.move(app.primaryScreen().availableGeometry().topLeft())
w.show()
settle(1.5)
check("the window's text is Inter", QFontInfo(w.font()).family() == "Inter", QFontInfo(w.font()).family())
w.show_detail(w.library.visible_keys[0])
settle(1.5)
title = QFontInfo(w.detail.title_label.font())
check("a game's title is Inter Display SemiBold",
      (title.family(), title.styleName()) == ("Inter Display", "SemiBold"),
      (title.family(), title.styleName()))
w.close()

print("\n=== 6. the real library is exactly as it was found ===")
changed = box.finish()
check("overrides.json, config.json and catalog.json are byte for byte unchanged", not changed, changed)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
