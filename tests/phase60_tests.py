"""Phase 60: the side rail -- the design's #1b, at the desk.

The library's places, filters and stores in a column on the left, with three of the games
played last as cards above the grid, measured on the live window at 1280x820 against the
mockup's markup; and everything the top bar's layout did, done from the rail: the places
change the page, a filter filters (and, picked from Stats, goes to the games), the search
searches, the pad climbs from the grid into Jump back in and works it, a card opens its
game, the rail steps aside for a game's page, TV mode keeps the top bar, and Settings turns
it off and on. Runs on a throwaway copy of the data; nothing is started.
"""
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))  # the project folder, one up from tests/
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import test_sandbox

box = test_sandbox.start({"library_layout": "rail"})

import logging

logging.basicConfig(level=logging.ERROR)

from PySide6.QtCore import QEventLoop, QPoint, Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

app = QApplication([])

from adapters import controller
from logic import focus
from presentation import ui_continue, ui_rules as _ui_rules, ui_settings, ui_window


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


def safely(make, fallback=None):
    try:
        return make()
    except Exception as error:  # the code before this phase lacks the names: judge, do not crash
        print(f"         ({type(error).__name__}: {error})")
        return fallback


print("\n=== 1. the design's numbers ===")
check("the rail is the default at the desk, the top bar the other choice",
      (ui_rules.LIBRARY_LAYOUT_DEFAULT, ui_rules.LAYOUT_RAIL, ui_rules.LAYOUT_TOP) == ("rail", "rail", "top"))
check("232 px wide, 22 / 14 / 16 inside",
      (ui_rules.RAIL_WIDTH, ui_rules.RAIL_PADDING_TOP, ui_rules.RAIL_PADDING_X, ui_rules.RAIL_PADDING_BOTTOM)
      == (232, 22, 14, 16))
check("places 36 high and 2 apart, 13.5 px with 17 px icons; filters 32 high, 13 px, 15 px icons, "
      "11.5 px counts; stores 30 high",
      (ui_rules.RAIL_NAV_HEIGHT, ui_rules.RAIL_NAV_GAP, ui_rules.RAIL_NAV_PX, ui_rules.RAIL_NAV_ICON_PX,
       ui_rules.RAIL_FILTER_HEIGHT, ui_rules.RAIL_FILTER_PX, ui_rules.RAIL_FILTER_ICON_PX,
       ui_rules.RAIL_COUNT_PX, ui_rules.RAIL_SOURCE_HEIGHT) == (36, 2, 13.5, 17, 32, 13, 15, 11.5, 30))
check("the chosen place accent 900 with accent-200 words and a 2 px accent mark",
      (ui_rules.COLOR_RAIL_CHOSEN, ui_rules.COLOR_RAIL_CHOSEN_TEXT, ui_rules.RAIL_MARK)
      == ("#2b2741", "#e7e5fe", 2))
check("beside it every page 24 px down and 32 in; the name 26 px; the search 280 x 34",
      (ui_rules.RAIL_PAGE_TOP, ui_rules.RAIL_PAGE_SIDE, ui_rules.PAGE_TITLE_PX, ui_rules.RAIL_SEARCH_WIDTH,
       ui_rules.RAIL_SEARCH_HEIGHT) == (24, 32, 26, 280, 34))
check("Jump back in: 3 cards 178 high, 14 apart, the first 1.35 times as wide, 14 px corners, a 34 px Play",
      (ui_rules.JUMP_COUNT, ui_rules.JUMP_HEIGHT, ui_rules.JUMP_GAP, tuple(ui_rules.JUMP_WEIGHTS or ()),
       ui_rules.JUMP_RADIUS, ui_rules.JUMP_PLAY) == (3, 178, 14, (135, 100, 100), 14, 34))

w = ui_window.MainWindow()
w.resize(1280, 820)
w.move(app.primaryScreen().availableGeometry().topLeft())
w.show()
settle(2.0)
focus.bring_to_front(int(w.winId()))
settle(0.4)
lib = w.library
rail = getattr(w, "rail", None)
check("there is a rail", rail is not None)
if rail is None:  # the code before this phase: nothing further to measure
    w.close()
    changed = box.finish()
    check("overrides.json, config.json and catalog.json are byte for byte unchanged", not changed, changed)
    print(f"\n{passed} passed, {failed} failed; the checks on the rail itself were not reached")
    raise SystemExit(1)

print("\n=== 2. the rail ===")
# 232 wide, or what its rows need where that is more (Phase 62: the cut-off "g").
rail_width = max(232, rail.layout().minimumSize().width())
check("it stands at the window's left, 232 wide or what its rows need, and the top bar is gone",
      rail.isVisible() and rail.mapTo(w, QPoint(0, 0)) == QPoint(0, 0) and rail.width() == rail_width
      and not w.top_bar.isVisible(), (rail.isVisible(), rail.width(), rail_width, w.top_bar.isVisible()))
places = list(rail.places.values())
check("Library, (Phase 98) For you, Stats, Storage, (Phase 84) Reports and (Phase 87) Wishlist, 36 high and 2 apart, "
      "Library chosen", [p.text() for p in places] == ["Library", "For you", "Stats", "Storage", "Reports", "Wishlist"]
      and all(p.height() == 36 for p in places)
      and places[1].y() - places[0].y() - 36 == 2 and places[0].isChecked(), [p.y() for p in places])
shot = w.grab().toImage()
chosen = places[0]
check("the chosen place is accent 900", distance(at(shot, chosen.mapTo(w, QPoint(chosen.width() - 20, 4))),
                                                 rgb("#2b2741")) < 10,
      at(shot, chosen.mapTo(w, QPoint(chosen.width() - 20, 4))))
check("with its accent mark at the left edge", distance(at(shot, chosen.mapTo(w, QPoint(0, chosen.height() // 2))),
                                                        rgb("#9184d9")) < 40,
      at(shot, chosen.mapTo(w, QPoint(0, chosen.height() // 2))))
filters = rail.filters
check("the five filters, 32 high, counting what the chips count",
      list(filters) == list(lib.chips) and all(f.height() == 32 for f in filters.values())
      and all(filters[name].count == int(lib.chips[name].text().split()[-1]) for name in filters),
      {name: (f.count, lib.chips[name].text()) for name, f in filters.items()})
base = [v for v in w.views if not v.hidden and not v.is_non_game]
sources = getattr(rail, "sources", [])
check("Found in names where the games came from, and they add up", sum(n for _, n in sources) == len(base)
      and (not any(v.entry.source == "folders" for v in base) or "Folders" in dict(sources)), sources)

print("\n=== 3. the page beside it ===")
title = lib.page_title.mapTo(w, QPoint(0, 0))
check("the library's name 32 px in from the rail and 24 down", (title.x() - rail.width(), title.y()) == (32, 24),
      (title.x() - rail.width(), title.y()))
check("and what it holds beside it", lib.page_meta.text().startswith(f"{len(base)} games"), lib.page_meta.text())
search = lib.filter_box
check("the search in the page's header, 280 x 34", lib.header.isAncestorOf(search)
      and (search.width(), search.height()) == (280, 34), (search.width(), search.height()))
check("All games over the grid, with the switches and the sort; the chips are the rail's now",
      lib.grid_label.isVisible() and lib.extras_box.isVisible() and lib.sort_box.isVisible()
      and not any(chip.isVisible() for chip in lib.chips.values()))

print("\n=== 4. Jump back in ===")
jump = lib.card
offered = [card.view for card in jump.cards if card.view is not None]
expected = sorted(ui_continue.eligible(w.views), key=lambda v: v.last_played.timestamp(), reverse=True)[:3]
check("three of the games played last, newest first, by the Continue card's rule",
      [v.key for v in offered] == [v.key for v in expected] and jump.shown, [v.display_name for v in offered])
cards = [card for card in jump.cards if card.view is not None]
if len(cards) == 3:
    gap = cards[1].mapTo(w, QPoint(0, 0)).x() - cards[0].mapTo(w, QPoint(cards[0].width(), 0)).x()
    check("178 high, 14 apart, the first the wider", all(c.height() == 178 for c in cards) and gap == 14
          and abs(cards[0].width() / cards[1].width() - 1.35) < 0.03, (gap, cards[0].width(), cards[1].width()))
    check("the first edged in accent 600", distance(at(shot, cards[0].mapTo(w, QPoint(cards[0].width() // 2, 0))),
                                                    rgb("#796cbf")) < 30,
          at(shot, cards[0].mapTo(w, QPoint(cards[0].width() // 2, 0))))
check("each card's Play is round, 34 px", all(c.play_button.size().width() == c.play_button.size().height() == 34
                                              for c in cards))

played, menus = [], []
lib.playRequested.disconnect()
lib.playRequested.connect(played.append)
lib.contextRequested.disconnect()
lib.contextRequested.connect(lambda key, _where: menus.append(key))
lib.select_key(lib.visible_keys[0])
settle(0.3)
w._on_pad_action(controller.UP)
settle(0.4)
check("up from the grid's top row lands on the first card's Play", lib.on_card and cards[0].play_button.hasFocus())
shot = w.grab().toImage()
button = cards[0].play_button
ring_point = button.mapTo(w, QPoint(button.width() // 2, -3))
check("ringed 2 px outside it, in the accent", distance(at(shot, ring_point), rgb("#9184d9")) < 40,
      at(shot, ring_point))
w._on_pad_action(controller.RIGHT)
settle(0.3)
check("right moves to the next card", len(cards) < 2 or cards[1].play_button.hasFocus())
w._on_pad_action(controller.ACTIVATE)
settle(0.3)
check("A plays that game", played[-1:] == [cards[min(1, len(cards) - 1)].view.key], played)
w._on_pad_action(controller.MENU)
settle(0.3)
check("X opens its menu", menus[-1:] == [cards[min(1, len(cards) - 1)].view.key], menus)
w._on_pad_action(controller.DOWN)
settle(0.3)
check("down goes back to the grid", not lib.on_card and lib.current_key() == lib.visible_keys[0])
lib.contextRequested.disconnect()
lib.contextRequested.connect(w._context_menu)

opened = cards[-1].view.key
cards[-1].mouseReleaseEvent(type("Click", (), {"button": lambda self: Qt.MouseButton.LeftButton})())
settle(1.0)
check("a click on a card opens its game's page", w.stack.currentIndex() == ui_window.DETAIL_PAGE
      and w.detail.view is not None and w.detail.view.key == opened)
check("and the rail steps aside for it, as the top bar did", not rail.isVisible() and not w.top_bar.isVisible())
w.show_library()
settle(0.8)
check("back on the library, the rail is back", rail.isVisible())

print("\n=== 5. the places and the filters ===")
rail.places["stats"].click()  # by name: For you sits between Library and Stats since Phase 98
settle(0.9)
column = w.stats_page.content.mapTo(w, QPoint(0, 0))
check("Stats from the rail, its place now the chosen one", w.stack.currentIndex() == ui_window.STATS_PAGE
      and rail.places["stats"].isChecked() and rail.isVisible())
check("its name at the top, on the same 32 px edge",
      w.stats_page.page_title.isVisible() and column.x() - rail.width() == 32, column.x() - rail.width())
filters["favorites"].click()
settle(0.9)
check("a filter picked on Stats goes to the games", w.stack.currentIndex() == ui_window.LIBRARY_PAGE
      and lib.current_filter() == "favorites" and lib.chips["favorites"].isChecked())
check("and filters them", all(w.by_key[key].favorite for key in lib.visible_keys), len(lib.visible_keys))
check("remembered, as a chip is", w.config.get("library_filter") == "favorites")
filters["all"].click()
settle(0.5)
rail.places["storage"].click()
settle(0.9)
check("Storage from the rail", w.stack.currentIndex() == ui_window.STORAGE_PAGE and rail.places["storage"].isChecked()
      and w.storage_page.page_title.isVisible())
places[0].click()
settle(0.8)
check("and back to the library", w.stack.currentIndex() == ui_window.LIBRARY_PAGE and places[0].isChecked())
name = w.by_key[lib.visible_keys[-1]].display_name
search.setText(name)
settle(0.4)
check("the search searches", lib.visible_keys and all(name.casefold() in w.by_key[k].display_name.casefold()
                                                      for k in lib.visible_keys))
search.clear()
settle(0.3)
lib.rescan_button.setEnabled(False)
check("while a scan runs, the rail's rescan is off too", not rail.rescan.isEnabled())
lib.rescan_button.setEnabled(True)

print("\n=== 6. TV mode, and Settings ===")
w.set_tv_mode(True)
settle(1.5)
check("TV mode keeps the top bar and the Continue card", not rail.isVisible() and w.top_bar.isVisible()
      and lib.card is lib.continue_card and w.top_bar.isAncestorOf(search))
w.set_tv_mode(False)
settle(1.2)
check("and back at the desk, the rail", rail.isVisible() and not w.top_bar.isVisible() and lib.card is lib.jump)
dialog = ui_settings.SettingsDialog(dict(w.config), w, known_keys=set())
check("Settings has the switch, on", dialog.rail_box.isChecked() and dialog.values()["library_layout"] == "rail")
dialog.rail_box.setChecked(False)
check("off, it asks for the top bar", dialog.values()["library_layout"] == "top")
dialog.reject()
w.config["library_layout"] = "top"
w._apply_layout()
settle(0.6)
check("which puts the bar and the chips back", w.top_bar.isVisible() and not rail.isVisible()
      and lib.chips["all"].isVisible() and lib.card is lib.continue_card)
w.config.pop("library_layout")
w._apply_layout()
settle(0.6)
check("with nothing chosen, the desk has the rail", rail.isVisible() and lib.layout_mode == "rail")
w.close()

print("\n=== 7. the real library is exactly as it was found ===")
changed = box.finish()
check("overrides.json, config.json and catalog.json are byte for byte unchanged", not changed, changed)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
