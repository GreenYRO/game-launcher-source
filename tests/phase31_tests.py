"""Phase 31: the redesign's first step -- type, icons, the top bar, chips, message cards.

Runs against a throwaway copy of the data (test_sandbox). A launcher window is shown for a
few seconds, because layout and message positions only mean something on a real window.
"""
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # the project folder, one up from tests/
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import test_sandbox

box = test_sandbox.start()

import logging

logging.basicConfig(level=logging.ERROR)

from PySide6.QtCore import QEventLoop, QTimer, Qt
from PySide6.QtGui import QFont, QFontMetrics, QKeySequence
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

app = QApplication([])

from shared import rules
from presentation import ui_icons
from presentation import ui_rules
from presentation import ui_theme
from presentation import ui_toast
from presentation import ui_topbar
from presentation import ui_window

SHOTS = Path(tempfile.gettempdir()) / "phase31_renders"
SHOTS.mkdir(exist_ok=True)
passed = failed = 0
windows = []


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"   PASS  {name}")
    else:
        failed += 1
        print(f"   FAIL  {name}   {detail}")


def settle(seconds=0.4):
    """Let a real event loop run -- layouts, deferred deletes and animations need one.

    A local QEventLoop, not app.exec() ended by app.quit(): in Qt 6 quit() closes every
    window first, so the window under test was quietly closing itself mid-test.
    """
    loop = QEventLoop()
    QTimer.singleShot(round(seconds * 1000), loop.quit)
    loop.exec()


def new_window():
    window = ui_window.MainWindow()
    windows.append(window)
    return window


def bold_short(buttons):
    """Switch-style buttons whose words, drawn bold when on, need more room than they have.

    Qt measures a button with the font it has, and `:checked { font-weight }` only changes
    the font it is painted with -- so the room is what the width leaves after the button's
    own padding, and that has to hold the bold words.
    """
    short = []
    for button in buttons:
        text = button.text().replace("&&", "&")
        if not text:
            continue
        font = button.font()
        bold = QFont(font)
        # What `:checked` paints with: the heading weight (SemiBold until Phase 54, Medium since).
        bold.setWeight(QFont.Weight(ui_rules.HEADING_WEIGHT))
        normal = QFontMetrics(font).horizontalAdvance(text)
        room = button.width() - (button.sizeHint().width() - normal)
        if room < QFontMetrics(bold).horizontalAdvance(text):
            short.append((text, room, QFontMetrics(bold).horizontalAdvance(text)))
    return short


print(f"\nsandbox data folder: {box.folder}")
print(f"renders:             {SHOTS}")

try:
    print("\n=== 1. type and icons come from Windows itself ===")
    check("the body face is one of the chosen ones -- Inter since Phase 54, Segoe behind it",
          ui_icons.body_family() in ui_rules.FONT_BODY_FAMILIES, ui_icons.body_family())
    check("so is the display face", ui_icons.display_family() in ui_rules.FONT_DISPLAY_FAMILIES)
    # Windows' own until Phase 59; the design's Phosphor since, Windows' own behind it.
    check("the icon font is the design's Phosphor", ui_icons.icon_family() == "Phosphor"
          and ui_icons.icon_family() in ui_rules.ICON_FONT_FAMILIES, ui_icons.icon_family())
    blank = []
    for name in ui_icons.GLYPHS:
        image = ui_icons.glyph_pixmap(name, "#ffffff", 32).toImage()
        # Every pixel touched, since Phase 59: Phosphor's three dots are 16 solid pixels and
        # 48 touched at 32 px -- drawn, just small. A missing glyph touches none.
        inked = sum(1 for y in range(image.height()) for x in range(image.width())
                    if image.pixelColor(x, y).alpha() > 0)
        if inked < 20:
            blank.append((name, inked))
    check(f"every one of the {len(ui_icons.GLYPHS)} icons actually draws something", not blank, blank)
    crisp = ui_icons.icon("search").pixmap(16, 16)
    check("an icon has sharper copies for scaled screens", ui_icons.PIXEL_RATIOS[-1] >= 3 and not crisp.isNull())

    print("\n=== 2. the top bar ===")
    w = new_window()
    w.resize(1500, 900)
    w.move(20, 20)
    w.show()
    settle()
    bar = w.top_bar
    check("it sits above the pages", bar.parent() is w.centralWidget() and bar.isVisible())
    check("Library is the lit tab on the library", bar.tabs[ui_topbar.TAB_LIBRARY].isChecked())
    w.library.stats_button.click()
    settle(0.3)
    check("the Stats tab opens Stats (and the old stats_button name still works)",
          w.stack.currentIndex() == ui_window.STATS_PAGE and bar.tabs[ui_topbar.TAB_STATS].isChecked())
    check("the old header on that page is out of sight", w.stats_page.header_row.isHidden())
    w._on_pad_action("right")
    settle(0.3)
    check("the pad's right still crosses to Storage, and the bar follows",
          w.stack.currentIndex() == ui_window.STORAGE_PAGE and bar.tabs[ui_topbar.TAB_STORAGE].isChecked())
    bar.tabs[ui_topbar.TAB_LIBRARY].click()
    settle(0.3)
    check("the Library tab comes back", w.stack.currentIndex() == ui_window.LIBRARY_PAGE)
    subject = next(v for v in w.views if not v.hidden and not v.is_non_game)
    w.show_detail(subject.key)
    settle(0.3)
    check("a game's own page hides the bar", not bar.isVisible())
    w.show_library()
    settle(0.3)
    check("and the library shows it again", bar.isVisible())
    check("every icon button has a tooltip and a name for screen readers",
          all(b.toolTip() and b.accessibleName() for b in (bar.surprise, bar.rescan, bar.settings)))
    w.grab().save(str(SHOTS / "library.png"))

    print("\n=== 3. search ===")
    name = subject.display_name
    w.library.filter_box.setText(name)
    settle(0.2)
    check("typing a name narrows the grid to it", subject.key in w.library.visible_keys
          and all(name.casefold() in w.by_key[k].display_name.casefold() for k in w.library.visible_keys))
    w.library.filter_box.clear()
    w.show_stats()
    settle(0.3)
    w.library.filter_box.setText(name[:3])
    settle(0.3)
    check("typing while on Stats goes to the library", w.stack.currentIndex() == ui_window.LIBRARY_PAGE)
    w.library.filter_box.clear()
    w.show_storage()
    settle(0.2)
    # A shortcut only reaches the window in front, and this machine never lets a background
    # window come forward by asking -- so it is brought forward the way Phase 28 does it.
    from logic import focus

    focus.bring_to_front(int(w.winId()))
    settle(0.3)
    QTest.keySequence(w, QKeySequence(QKeySequence.StandardKey.Find))
    settle(0.3)
    check("Ctrl+F from any page lands in the search box, on the library",
          w.stack.currentIndex() == ui_window.LIBRARY_PAGE
          and w.focusWidget() is w.library.filter_box,
          (w.stack.currentIndex(), w.focusWidget(), QApplication.activeWindow()))
    check("the search box counts the games", str(len([v for v in w.views if not v.hidden
                                                       and not v.is_non_game]))
          in w.library.filter_box.placeholderText(), w.library.filter_box.placeholderText())

    print("\n=== 4. the chips ===")
    lib = w.library
    base = [v for v in w.views if not v.hidden and not v.is_non_game]
    expected = {
        "all": len(base),
        "favorites": sum(v.favorite for v in base),
        rules.STATUS_PLAYING: sum(v.status == rules.STATUS_PLAYING for v in base),
        rules.STATUS_FINISHED: sum(v.status == rules.STATUS_FINISHED for v in base),
        rules.STATUS_DROPPED: sum(v.status == rules.STATUS_DROPPED for v in base),
    }
    shown = {name: int(chip.text().split()[-1]) for name, chip in lib.chips.items()}
    check("every chip's number is what clicking it gives", shown == expected, (shown, expected))
    lib.chips["favorites"].click()
    settle(0.2)
    check("Favorites shows the favourites and nothing else",
          len(lib.visible_keys) == expected["favorites"]
          and all(w.by_key[k].favorite for k in lib.visible_keys))
    check("the choice is remembered in config.json", box.read_json("config.json").get("library_filter") == "favorites")
    clipped = []
    for chip in lib.chips.values():
        # Chosen, a chip kept the bold its words were measured for until Phase 55; since then
        # it keeps its weight (the accent marks it) and paints its number a size smaller --
        # so the room it needs is its word, the gap and the number, in its own fonts.
        count = QFont(chip.font())
        count.setPointSizeF(ui_theme.px_to_pt(ui_rules.CHIP_COUNT_PX * w.scale))
        words, number = chip.text().rsplit(" ", 1)
        needed = (QFontMetrics(chip.font()).horizontalAdvance(words.strip())
                  + round(ui_rules.CHIP_COUNT_GAP * w.scale) + QFontMetrics(count).horizontalAdvance(number)
                  + 2 * round(ui_rules.CHIP_SIDE_PADDING * w.scale))
        if chip.width() < needed:
            clipped.append((chip.text(), chip.width(), needed))
    check("no chip is too narrow for its words (the first render clipped the chosen one)",
          not clipped, clipped)
    view = next(v for v in w.views if not v.hidden and not v.is_non_game)
    w.show_detail(view.key)
    settle(0.3)
    # The two switches beside the chips left this list in Phase 55: on, they keep their weight.
    # The game page's three marks left it in Phase 62 for the same reason -- since Phase 57 a
    # lit mark keeps its weight, the accent and its ring marking it -- so what they must hold
    # is their words at their own weight, checked below.
    switches = [*bar.tabs.values(), w.detail.favorite_button]
    check("nor any other switch that turns bold when on -- the tabs, the "
          "game page's (reported from use: the lit 'Library' tab lost the tail of its 'y')",
          not bold_short(switches), bold_short(switches))
    marks_short = []
    for button in w.detail.status_buttons.values():
        words = QFontMetrics(button.font()).horizontalAdvance(button.text())
        if button.width() - (button.sizeHint().width() - words) < words:
            marks_short.append((button.text(), button.width(), button.sizeHint().width()))
    check("and each of the game page's marks holds its words at its own weight",
          len(w.detail.status_buttons) == 3 and not marks_short, marks_short)
    w.show_library()
    settle(0.3)
    w.close()
    w2 = new_window()
    check("a new window opens on the remembered chip", w2.library.current_filter() == "favorites")
    w2.library.chips["all"].click()
    check("the two switches still behave like the tick-boxes they were",
          hasattr(w2.library.extras_box, "setChecked") and not w2.library.hidden_box.isChecked())
    before = len(w2.library.visible_keys)
    w2.library.hidden_box.setChecked(True)
    check("Hidden shows hidden games again", len(w2.library.visible_keys) >= before)
    w2.library.hidden_box.setChecked(False)
    w2.close()

    config = box.read_json("config.json")
    config["library_filter"] = "games I love"
    (box.folder / "config.json").write_text(__import__("json").dumps(config), encoding="utf-8")
    w3 = new_window()
    check("a chip this version does not know falls back to All games", w3.library.current_filter() == "all")
    w3.close()

    print("\n=== 5. messages float as a card ===")
    w = new_window()
    w.resize(1500, 900)
    w.move(20, 20)
    w.show()
    settle(0.5)
    check("the old status bar is gone from view", not w.statusBar().isVisible())
    check("and 'Ready' is never shown as a message", not w.toast.isVisible())
    w.statusBar().showMessage("Saves of Pocket Quest copied", 3000)
    settle(0.5)
    check("a message appears as a card", w.toast.isVisible() and w.toast.text.text() == "Saves of Pocket Quest copied")
    line = w.toast.text.fontMetrics().lineSpacing()
    check("a short message sits on one line (the first render wrapped it)",
          w.toast.text.height() < line * 1.8, (w.toast.text.height(), line))
    geometry = w.toast.geometry()
    shell = w.centralWidget()
    check("in the bottom-right corner",
          geometry.right() > shell.width() * 0.6 and geometry.bottom() > shell.height() * 0.8)
    check("and it never takes a click meant for what is under it",
          w.toast.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents))
    w.grab().save(str(SHOTS / "message.png"))
    settle(3.2)
    check("when the message runs out, the card goes", not w.toast.isVisible())
    w.queue_status("first queued", 600)
    w.queue_status("second queued", 600)
    seen = []
    w.statusBar().messageChanged.connect(lambda t: seen.append(t))
    settle(1.6)
    check("the Phase 14 queue still shows messages one after another",
          "second queued" in seen and w.toast.text.text() in ("second queued", "first queued"), seen)
    w.reduce_animations = True
    w.toast.reduce_animations = True
    w.statusBar().showMessage("no motion please", 2000)
    check("with Reduce animations the card appears at once, without sliding",
          w.toast.isVisible() and w.toast.effect.opacity() == 1.0)

    w.showFullScreen = lambda: None
    w.showNormal = lambda: None
    w.set_tv_mode(True)
    w.resize(1920, 1080)
    settle(0.4)
    w.statusBar().showMessage("New game: Pocket Quest", 3000)
    settle(0.3)
    check("in TV mode the card clears the button-hint bar",
          w.toast.geometry().bottom() < w.hint_bar.geometry().top(),
          (w.toast.geometry().bottom(), w.hint_bar.geometry().top()))
    check("and the status bar stays hidden there too", not w.statusBar().isVisible())
    # The tabs are the switches that still turn heavier when on; the two beside the chips
    # keep their weight since Phase 55, and must simply hold their words.
    tv_tabs = list(w.top_bar.tabs.values())
    check("TV mode's smaller tabs keep room for their heavier words too",
          not bold_short(tv_tabs), bold_short(tv_tabs))
    toggles = [w.library.extras_box, w.library.hidden_box]
    check("and the two switches hold their words",
          all(b.width() >= QFontMetrics(b.font()).horizontalAdvance(b.text().replace("&&", "&")) for b in toggles),
          [(b.text(), b.width()) for b in toggles])
    w.grab().save(str(SHOTS / "tv.png"))
    w.set_tv_mode(False)
    w.close()

finally:
    for window in windows:
        try:
            window.close()
        except RuntimeError:
            pass
    print("\n=== 6. the real library is exactly as it was found ===")
    changed = box.finish()
    check("overrides.json, config.json and catalog.json are byte for byte unchanged", not changed,
          changed)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
