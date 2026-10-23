"""Phase 62: Inter one step heavier, titles in Inter Display -- and two things found in use.

The user found the type too thin and asked for San Francisco, whose licence allows it only
for Apple Watch apps; Inter is the free match, and its Display cut the nearest to SF's.
Ordinary text is Medium, headings SemiBold, the two small labels Bold, big titles Inter
Display SemiBold -- every one a real face shipped in presentation/fonts, never one Qt fakes.

Found in use: the rail's "Play something" was 10 px narrower than its words, cutting off
the end of its "g"; the rail now widens when its rows need it. Found by rendering at the
user's 125%: Storage opened scrolled past its drive's name whenever the list was shorter
than the drive's card top and a row; the list now opens at its top, and the map of tiles
gives up height -- or steps aside -- before the list does. Runs on a throwaway copy of the
data; nothing is started.
"""
import hashlib
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))  # the project folder, one up from tests/
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import test_sandbox

box = test_sandbox.start({"library_layout": "rail"})
shots = test_sandbox.REAL / "cache" / "screenshots"

import logging

logging.basicConfig(level=logging.ERROR)

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtGui import QFont, QFontDatabase, QFontInfo
from PySide6.QtWidgets import QApplication, QLabel

app = QApplication([])

from logic import focus
from presentation import ui_icons, ui_rules as _ui_rules, ui_storage, ui_window


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


def face(family, weight):
    font = QFont(family)
    font.setPixelSize(20)
    font.setWeight(QFont.Weight(weight))
    info = QFontInfo(font)
    return info.family(), info.styleName()


print("\n=== 1. the weights, and the faces that draw them ===")
check("ordinary text Medium, headings SemiBold, the two small labels Bold, tile names SemiBold",
      (ui_rules.BODY_WEIGHT, ui_rules.HEADING_WEIGHT, ui_rules.LABEL_WEIGHT, ui_rules.TILE_NAME_WEIGHT)
      == (500, 600, 700, "DemiBold"),
      (ui_rules.BODY_WEIGHT, ui_rules.HEADING_WEIGHT, ui_rules.LABEL_WEIGHT, ui_rules.TILE_NAME_WEIGHT))
check("titles take Inter Display first, Inter behind it",
      tuple(ui_rules.FONT_DISPLAY_FAMILIES or ())[:2] == ("Inter Display", "Inter"), ui_rules.FONT_DISPLAY_FAMILIES)
# The two files this phase adds, byte for byte the official Inter 4.1 release's
# (Inter-4.1.zip from github.com/rsms/inter, sha256 9883fdd4...; the same download as
# Phase 54). Their licence is Inter's OFL, already in the folder.
SHIPPED = {
    "Inter-Bold.ttf": "288316099b1e0a47a4716d159098005eef7c0066921f34e3200393dbdb01947f",
    "InterDisplay-SemiBold.ttf": "0310d7a325896129730c6c8cf9a6e0f81ee258bedf77b1ff059b2a7b75f74e02",
}
fonts = PROJECT / "presentation" / "fonts"
for name, digest in SHIPPED.items():
    path = fonts / name
    got = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "missing"
    check(f"{name} is shipped, identical to the release", got == digest, got[:16])
licence = (fonts / "Inter-LICENSE.txt").read_text(encoding="utf-8") if (fonts / "Inter-LICENSE.txt").is_file() else ""
check("under the Inter Project's OFL, which is in the folder",
      "The Inter Project Authors" in licence and "SIL Open Font License" in licence)
ui_icons.bundled_families()
check("they register as Inter and Inter Display", {"Inter", "Inter Display"} <= set(QFontDatabase.families()))
for weight, style in ((500, "Medium"), (600, "SemiBold"), (700, "Bold")):
    check(f"weight {weight} draws Inter's own {style}, not a faked one",
          face("Inter", weight) == ("Inter", style), face("Inter", weight))
check("a title draws Inter Display's own SemiBold",
      face(ui_icons.display_family(), ui_rules.HEADING_WEIGHT) == ("Inter Display", "SemiBold"),
      face(ui_icons.display_family(), ui_rules.HEADING_WEIGHT))

print("\n=== 2. on the live window ===")
w = ui_window.MainWindow()
w.resize(1280, 820)
w.move(app.primaryScreen().availableGeometry().topLeft())
w.show()
settle(2.0)
focus.bring_to_front(int(w.winId()))
settle(0.4)
plain = QLabel("Where you left off, the settings that worked", w.library)
plain.ensurePolished()
info = QFontInfo(plain.font())
check("ordinary text in the window is Inter Medium", (info.family(), info.styleName()) == ("Inter", "Medium"),
      (info.family(), info.styleName()))
plain.deleteLater()
key = next(k for k in w.library.visible_keys if not w.by_key[k].is_non_game)
w.show_detail(key)
settle(1.6)
title = QFontInfo(w.detail.title_label.font())
check("a game's title is Inter Display SemiBold", (title.family(), title.styleName()) == ("Inter Display", "SemiBold"),
      (title.family(), title.styleName()))
marks = list(w.detail.status_buttons.values())
mark = QFontInfo(marks[0].font()) if marks else None
check("the Playing / Finished / Dropped words are ordinary text, Medium",
      mark is not None and mark.styleName() == "Medium", mark and mark.styleName())
w.show_library()
settle(1.2)

print("\n=== 3. the rail's foot keeps its words whole ===")
rail = w.rail
play = rail.surprise


def whole():
    return play.width() >= play.sizeHint().width()


check("Play something gets all the width its words need (the cut-off g)", whole(),
      (play.width(), play.sizeHint().width()))
check("the rail is the design's 232 px or what its rows need, never less",
      rail.width() >= 232 and rail.width() >= rail.layout().minimumSize().width(),
      (rail.width(), rail.layout().minimumSize().width()))
words = play.text()
play.setText(words + " now, please")  # words far wider than the design's foot
rail.apply_scale(w.scale)
settle(0.3)
check("longer words widen the rail rather than being cut", whole() and rail.width() > 232,
      (play.width(), play.sizeHint().width(), rail.width()))
play.setText(words)
rail.apply_scale(w.scale)
settle(0.3)
check("and it comes back when they shrink", whole() and rail.width() == max(232, rail.layout().minimumSize().width()),
      rail.width())

print("\n=== 4. Storage opens on its drive's name, and the map gives way ===")


def open_storage(size):
    w.show_library()
    settle(0.5)
    w.resize(*size)
    settle(0.7)
    w.show_storage()
    settle(1.0)
    page = w.storage_page
    lst = page.list
    first_game = next(i for i in range(lst.count())
                      if lst.item(i).data(ui_storage.KIND_ROLE) == ui_storage.KIND_GAME)
    rows = [lst.visualItemRect(lst.item(i)) for i in range(first_game + 2)]
    return page, lst, rows


def full_map():
    return max(80, round(_ui_rules.STORAGE_TREEMAP_HEIGHT * w.scale))


w.config["ui_scale"] = 1.25  # the user's own size, through the path Settings takes
w.set_tv_mode(False)
settle(0.8)
page, lst, rows = open_storage((1280, 820))
view_h = lst.viewport().height()
check("at 125% in a 1280 x 820 window the list opens at its top",
      lst.verticalScrollBar().value() == 0 and rows[0].top() == 0, (lst.verticalScrollBar().value(), rows[0].top()))
check("the drive's card top and two rows are all in view", rows[-1].bottom() < view_h,
      (rows[-1].bottom(), view_h))
check("the map shrank to make that room, and is still there",
      page.treemap.isVisible() and page.treemap.height() < full_map(), (page.treemap.isVisible(), page.treemap.height()))
lst.verticalScrollBar().setValue(lst.verticalScrollBar().maximum())  # scrolled away, then reopened
page, lst, rows = open_storage((2560, 1392))
check("in a window the size of the user's it opens at its top too",
      lst.verticalScrollBar().value() == 0 and rows[0].top() == 0, lst.verticalScrollBar().value())
check("with the map at its full height", page.treemap.isVisible() and page.treemap.height() == full_map(),
      (page.treemap.height(), full_map()))
# At 125% the window will not go below 784 px, so the page itself is held short -- as a
# larger interface size would leave it -- to reach the case where both cannot fit.
w.storage_page.setMaximumHeight(round(520 * w.scale))
page, lst, rows = open_storage((1280, 820))
check("on a page too short for both, the map steps aside", not page.treemap.isVisible(),
      (page.height(), page.treemap.height()))
check("and the list still shows the drive's card top and two rows",
      lst.verticalScrollBar().value() == 0 and rows[-1].bottom() < lst.viewport().height(),
      (lst.verticalScrollBar().value(), rows[-1].bottom(), lst.viewport().height()))
w.storage_page.setMaximumHeight(16777215)
settle(0.6)
check("given its height back, the map comes back", w.storage_page.treemap.isVisible())
w.config["ui_scale"] = 1.0
w.set_tv_mode(True)
settle(0.8)
w.show_storage()
settle(0.8)
check("TV mode still has no map", not w.storage_page.treemap.isVisible())
w.set_tv_mode(False)
settle(0.6)
w.close()
settle(0.3)

print("\n=== 5. the real library is exactly as it was found ===")
changed = box.finish()
check("overrides.json, config.json and catalog.json are byte for byte unchanged", not changed, changed)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
