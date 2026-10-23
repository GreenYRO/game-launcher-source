"""Phase 87: the Steam wishlist, step 2 of 2 -- the Wishlist tab.

  1. the tab: in the top bar and the side rail after Reports, with its icon; opening it from each,
     lit, the library's glow kept;
  2. the pad across five tabs: View opens Stats, right walks Storage, Reports, Wishlist and stops
     there, left walks back to the library; on the page down moves the selection, A opens the store
     page, X its menu, Y switches the chips, B goes back -- pressed the way the hub sends them;
  3. the hints: a set for the page, Reports saying where right goes, every set inside 1920 at every
     TV size;
  4. each row's parts present exactly when their data exists, on made-up rows;
  5. the order and the chips; what an empty page says, every case;
  6. the notice: at most once a day, only when a game is new to it, never for a hidden or removed
     game; the window posting it through the status queue and keeping one key;
  7. the store page (the opener stood in for: captured, never run), and the web page when no client
     takes it; hiding a game and showing it again, one key of config.json;
  8. the covers: fetched one request each, into the cache as every cover is, only with the network on;
  9. rendered at 100% and in TV mode on the real wishlist: the rows on the window, nothing to scroll
     sideways, a row's glass and the ring painted; Escape back;
 10. the documents, the layers; 11. the real library exactly as it was found.

On a throwaway copy of the data; every request stops at a stand-in.
"""
import json
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import sources  # the build log's notes (Phase 91)
import test_sandbox

box = test_sandbox.start()
SANDBOX = box.folder
box.copy_cache("steam_details", "steam_web.json", "steam_search.json")  # copies, read only
attempts: list[str] = []


def no_network(request, *args, **kwargs):
    attempts.append(getattr(request, "full_url", str(request)))
    raise OSError("the network is blocked in this suite")


urllib.request.urlopen = no_network

import logging

logging.basicConfig(level=logging.CRITICAL)

from PySide6.QtCore import QEvent, QEventLoop, QPoint, Qt, QTimer
from PySide6.QtGui import QColor, QKeyEvent
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)

from adapters import controller
from data_access import library_db
from presentation import ui_icons, ui_rail, ui_rules, ui_settings, ui_topbar, ui_tv, ui_window
from shared import paths, rules
from web import steam_web

try:
    from adapters.screenshot_worker import CapsuleWorker
    from logic import wishlist
    from presentation import ui_wishlist
except ImportError:  # the code before this phase has neither the page nor its words
    CapsuleWorker = ui_wishlist = None
    from logic import wishlist

BASE = 76561197960265728
WORK = Path(tempfile.mkdtemp(prefix="phase87_"))
CACHE = str(paths.cache_dir())
passed = failed = 0


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"   PASS  {name}")
    else:
        failed += 1
        print(f"   FAIL  {name}   {detail}")


def unreached(section: str, exc: Exception):
    check(f"section {section} runs to its end on this code", False, repr(exc))


def settle(seconds: float = 0.4) -> None:
    loop = QEventLoop()
    QTimer.singleShot(int(seconds * 1000), loop.quit)
    loop.exec()


def press(window, name: str, wait: float = 0.6) -> None:
    """A button as the hub sends it: emitted from inside a timer, queued to the window."""
    QTimer.singleShot(0, lambda: window.pads.action.emit(name))
    settle(wait)


def page(window) -> int:
    return window.stack.currentIndex()


def at(day: int, hour: int = 12) -> str:
    return datetime(2026, 10, day, hour, tzinfo=timezone.utc).isoformat(timespec="seconds")


def view(appid, **fields) -> dict:
    """A row of v_wishlist_now, made up: a game on one list, priced once, 10 euros, nothing more."""
    row = {"appid": appid, "name": f"Game {appid}", "has_record": 1, "app_type": "game", "accounts": "Alpha",
           "lists": 1, "priority": 0, "date_added": at(1), "first_seen": at(10), "last_seen": at(10),
           "removed_at": None, "kind": "priced", "currency": "EUR", "initial_cents": 1000, "final_cents": 1000,
           "discount_percent": 0, "observed_at": at(10), "observations": 1, "first_observed": at(10),
           "lowest_cents": 1000, "lowest_on": at(10), "highest_cents": 1000, "is_lowest_now": 0, "minutes_played": None}
    row.update(fields)
    return row


FIT = wishlist.Fit(0.5, "Action: 50% of your hours")


def made_store(name: str, mine=((1001, "Alpha"), (1002, "Bravo"))):
    store = library_db.LibraryStore(WORK / f"{name}.db")
    for account_id, persona in mine:
        store._conn.execute("INSERT INTO steam_account (account_id, steam_id64, persona, is_mine, first_seen, last_seen) "
                            "VALUES (?, ?, ?, 1, ?, ?)", (account_id, account_id + BASE, persona, at(1), at(1)))
    return store


window = ui_window.MainWindow()
window.resize(1280, 820)
window.show()
settle(1.0)
WISH = getattr(ui_window, "WISHLIST_PAGE", -1)

print("=== 1. the tab ===")
try:
    names = [n for n, _l in ui_topbar.TABS]
    check("the top bar has Wishlist after Reports, the last place", names[-2:] == ["reports", "wishlist"]
          and window.top_bar.tabs["wishlist"].text() == "Wishlist")
    check("and so has the side rail, with a heart of its own",
          [n for n, _l, _g in ui_rail.NAV][-1] == "wishlist" and ui_icons.PHOSPHOR.get("wishlist", (0, ""))[1] == "heart"
          and "wishlist" in ui_icons.SEGOE)
    window.top_bar.tabs["wishlist"].click()
    settle(0.8)
    check("the bar's tab opens the page, lit", page(window) == WISH and window.top_bar.tabs["wishlist"].isChecked())
    check("the page keeps the library's glow, as every tab does", WISH in ui_window.GLOWING_PAGES)
    window.show_library()
    settle(0.5)
    window.config["library_layout"] = ui_rules.LAYOUT_RAIL
    window._apply_layout()
    settle(0.4)
    window.rail.places["wishlist"].click()
    settle(0.8)
    check("the rail's place opens it too, lit, the page carrying its name",
          page(window) == WISH and window.rail.places["wishlist"].isChecked()
          and window.wishlist_page.page_title.isVisible() and window.wishlist_page.page_title.text() == "Wishlist")
    window.config["library_layout"] = ui_rules.LAYOUT_TOP
    window._apply_layout()
    window.show_library()
    settle(0.5)
except Exception as exc:
    unreached("1", exc)

print("\n=== 2. the pad, across five tabs ===")
try:
    walk = []
    press(window, controller.STATS)
    walk.append(page(window))
    for _ in range(4):
        press(window, controller.RIGHT)
        walk.append(page(window))
    check("View opens Stats; right walks Storage, Reports, Wishlist, and stops there",
          walk == [ui_window.STATS_PAGE, ui_window.STORAGE_PAGE, ui_window.REPORTS_PAGE, WISH, WISH], walk)
    shown = window.wishlist_page.list
    first = window.wishlist_page.current_appid()
    press(window, controller.DOWN, 0.3)
    check("on the Wishlist down moves to the next row", shown.currentRow() == 1
          and window.wishlist_page.current_appid() != first, shown.currentRow())
    press(window, controller.UP, 0.3)
    opened: list[str] = []
    real_open = ui_settings.open_in_browser
    ui_settings.open_in_browser = lambda url: opened.append(url) or True
    try:
        press(window, controller.ACTIVATE)
    finally:
        ui_settings.open_in_browser = real_open
    check("A opens the selected game's store page in Steam -- the opener captured, nothing run",
          opened == [rules.STEAM_STORE_PAGE_URI.format(appid=first)], opened)
    choice = window.wishlist_page.choice
    press(window, controller.SURPRISE)
    check("Y switches the chips: On sale", window.wishlist_page.choice == wishlist.ON_SALE != choice
          and window.config.get(rules.WISHLIST_FILTER_SETTING) == wishlist.ON_SALE)
    press(window, controller.SURPRISE)
    check("then Alerts (Phase 101: a third chip)", window.wishlist_page.choice == wishlist.ALERTS)
    press(window, controller.SURPRISE)
    check("and back to All", window.wishlist_page.choice == wishlist.ALL)
    menus: list = []

    def close_menu():
        popup = QApplication.activePopupWidget()
        menus.append([a.text() for a in popup.actions()] if popup is not None else None)
        if popup is not None:
            window.pads.action.emit(controller.BACK)

    QTimer.singleShot(700, close_menu)
    press(window, controller.MENU, 1.4)
    check("X opens its menu: Open in Steam, Alert me under... (Phase 101), Hide from this page; B closes it, "
          "nothing chosen", menus == [["Open in Steam", "Alert me under...", "Hide from this page"]]
          and QApplication.activePopupWidget() is None
          and page(window) == WISH, menus)
    back = []
    for _ in range(5):  # For you between Stats and the library since Phase 98
        press(window, controller.LEFT)
        back.append(page(window))
    check("left walks back: Reports, Storage, Stats, For you, the library",
          back == [ui_window.REPORTS_PAGE, ui_window.STORAGE_PAGE, ui_window.STATS_PAGE,
                   getattr(ui_window, "FORYOU_PAGE", -1), ui_window.LIBRARY_PAGE], back)
    window.show_wishlist()
    settle(0.6)
    press(window, controller.BACK)
    check("B goes back to the library", page(window) == ui_window.LIBRARY_PAGE)
except Exception as exc:
    unreached("2", exc)

print("\n=== 3. the hints ===")
try:
    check("a set of its own: open in Steam, back, the menu, the chips, the tab walk, settings",
          [label for _pad, label in ui_tv.HINT_SETS[ui_tv.WISHLIST]]
          == ["Open in Steam", "Back", "Menu", "Next chip", "Reports", "Settings"])  # three chips since Phase 101
    check("Reports says where right goes now", (ui_tv.ACROSS, "Storage / Wishlist") in ui_tv.HINT_SETS[ui_tv.REPORTS])
    window.set_tv_mode(True)
    settle(1.0)
    window.show_wishlist()
    settle(0.6)
    check("in TV mode, on the page, the bar shows the Wishlist set", window.hint_bar.hints == ui_tv.WISHLIST,
          window.hint_bar.hints)
    widest, worst = 0, ""
    was = window.config.get("tv_scale")
    for scale in ui_rules.TV_SCALE_CHOICES:
        window.config["tv_scale"] = scale
        window.set_tv_mode(False)
        window.set_tv_mode(True)
        settle(0.2)
        for name in ui_tv.HINT_SETS:
            window.hint_bar.set_hints(name)
            app.processEvents()
            if window.hint_bar.sizeHint().width() > widest:
                widest, worst = window.hint_bar.sizeHint().width(), f"{name} at {scale}x"
    check(f"every set fits 1920 at every TV size (widest {widest} px: {worst})", widest <= 1920, widest)
    if was is None:
        window.config.pop("tv_scale", None)
    else:
        window.config["tv_scale"] = was
    window.set_tv_mode(False)
    settle(0.6)
except Exception as exc:
    unreached("3", exc)

print("\n=== 4. each row's parts, exactly when their data exists ===")
try:
    plain = wishlist.row_of(view(1), FIT, False, False)
    check("a priced game, seen once: its price, '1 price so far', no struck price, no discount, no lowest, no tag",
          plain.price == "10,00 €" and plain.prices == "1 price so far, 10 Oct" and not plain.was
          and not plain.discount and not plain.lowest and not plain.lowest_now and not plain.on_sale, plain)
    sale = wishlist.row_of(view(2, final_cents=250, discount_percent=75, observations=3, first_observed=at(2),
                                lowest_cents=250, lowest_on=at(12), highest_cents=1000, is_lowest_now=1), FIT, False, False)
    check("on sale: today's price, the one before struck through, the discount, the count, the tag -- and no "
          "'lowest seen' line, today being the lowest",
          sale.price == "2,50 €" and sale.was == "10,00 €" and sale.discount == "-75%" and sale.on_sale
          and sale.prices == "3 prices since 2 Oct" and sale.lowest == "" and sale.lowest_now, sale)
    cheaper = wishlist.row_of(view(3, final_cents=900, observations=4, first_observed=at(2), lowest_cents=500,
                                   lowest_on=at(5)), FIT, False, False)
    check("seen cheaper before: 'lowest seen 5,00 € on 5 Oct'", cheaper.lowest == "lowest seen 5,00 € on 5 Oct"
          and cheaper.prices == "4 prices since 2 Oct", cheaper)
    flat = wishlist.row_of(view(4, observations=2), FIT, False, False)
    check("a price that never moved, seen twice: the count, no lowest line, no tag",
          flat.prices.startswith("2 prices") and not flat.lowest and not flat.lowest_now)
    free = wishlist.row_of(view(5, kind="free", currency=None, initial_cents=None, final_cents=None,
                                discount_percent=None), FIT, False, False)
    gone = wishlist.row_of(view(6, kind="unavailable", currency=None, initial_cents=None, final_cents=None,
                                discount_percent=None), FIT, False, False)
    check("free and not sold: said in words, with no count of prices", free.price == "Free" and gone.price == "Not sold"
          and not free.prices and not gone.prices and not gone.was, (free.prices, gone.prices))
    unknown = wishlist.row_of(view(7, name=None, has_record=0, kind=None, currency=None, initial_cents=None,
                                   final_cents=None, discount_percent=None, observations=None),
                              wishlist.Fit(None, wishlist.NOT_FETCHED), False, False)
    check("not fetched yet: its number for a name, no price yet, the fit line saying so",
          unknown.name == "App 7" and unknown.price == "No price yet" and not unknown.prices
          and unknown.fit.words == "not fetched yet")
    played = wishlist.row_of(view(8, minutes_played=42.4), FIT, False, False)
    check("the hours already played, only when there are some", played.played == "Already played: 42 min"
          and not plain.played and not wishlist.row_of(view(9, minutes_played=0.4), FIT, False, False).played)
    check("when it was added, as Steam says; first seen when Steam did not say",
          plain.added == "Added 1 Oct 2026" and wishlist.row_of(view(10, date_added=None), FIT, False, False).added
          == "First seen 10 Oct 2026")
    one = wishlist.row_of(view(11, accounts="Alpha, Bravo", lists=2), FIT, False, True)
    check("whose list it is on, only when more than one account is marked mine",
          not plain.accounts and wishlist.row_of(view(12), FIT, False, True).accounts == "On Alpha's list"
          and one.accounts == "On the lists of Alpha and Bravo")
    check("a game no list holds now is a removed one", wishlist.row_of(view(13, lists=0, removed_at=at(12)), FIT,
                                                                       False, False).removed)
except Exception as exc:
    unreached("4", exc)

print("\n=== 5. the order, the chips, and what an empty page says ===")
try:
    rows = [wishlist.row_of(v, f, False, False) for v, f in (
        (view(1, name="Low fit"), wishlist.Fit(0.2, "x")), (view(2, name="High fit"), wishlist.Fit(0.9, "x")),
        (view(3, name="Small sale", discount_percent=10, final_cents=900), wishlist.Fit(0.1, "x")),
        (view(4, name="Big sale", discount_percent=80, final_cents=200), wishlist.Fit(0.0, "x")),
        (view(5, name="No fit"), wishlist.Fit(None, "not fetched yet")),
        (view(6, name="Big sale too", discount_percent=80, final_cents=200), wishlist.Fit(0.5, "x")))]
    check("on sale first, the deepest first (the fit between two alike), then the fit, the unknown last",
          [r.name for r in wishlist.order(rows)] == ["Big sale too", "Big sale", "Small sale", "High fit", "Low fit",
                                                     "No fit"], [r.name for r in wishlist.order(rows)])
    model = wishlist.Page(rows=wishlist.order(rows))
    check("the chips: All every row, On sale the three", len(model.shown(wishlist.ALL)) == 6
          and [r.name for r in model.shown(wishlist.ON_SALE)] == ["Big sale too", "Big sale", "Small sale"]
          and model.on_sale == 3)
    store = made_store("none", mine=())
    check("no account marked mine: says so, and where to mark one",
          wishlist.page(store.reports(), store.steam_accounts(), set(), True).empty == wishlist.NO_ACCOUNT)
    store.close()
    store = made_store("unread")
    check("marked but never read: once a day, with a scan -- or the network is off",
          wishlist.page(store.reports(), store.steam_accounts(), set(), True).empty == wishlist.NOT_READ
          and wishlist.page(store.reports(), store.steam_accounts(), set(), False).empty == wishlist.NETWORK_OFF)
    for account in (1001, 1002):
        store.land_wishlist({"account_id": account, "read_at": at(10), "items": []})
    nothing = wishlist.page(store.reports(), store.steam_accounts(), set(), True)
    check("read, and nothing to read: private on Steam, or empty -- both said", nothing.empty == wishlist.NOTHING_TO_READ
          and "private on Steam, or empty" in nothing.footnote)
    store.land_wishlist({"account_id": 1001, "read_at": at(11), "items": [{"appid": 70, "priority": 0, "date_added": None}]})
    store._conn.execute("UPDATE steam_app SET has_record = 1, name = 'Seventy' WHERE appid = 70")
    store.land_wishlist({"account_id": 1001, "read_at": at(12), "items": [{"appid": 71, "priority": 0, "date_added": None}]})
    store.land_wishlist({"account_id": 1001, "read_at": at(13), "items": [{"appid": 71, "priority": 0, "date_added": None}]})
    some = wishlist.page(store.reports(), store.steam_accounts(), {71}, True)
    check("everything let go or hidden: nothing on the list now, the rest under their folds",
          some.empty == wishlist.NOTHING_ON_LIST and [r.name for r in some.removed] == ["Seventy"]
          and [r.appid for r in some.hidden] == [71] and not some.rows, some)
    check("the footnote names the read, the account with items, and the one with nothing",
          some.footnote.startswith("Read ") and "from Alpha" in some.footnote and "nothing to read from Bravo" in some.footnote,
          some.footnote)
    store.close()
    page_widget = window.wishlist_page
    page_widget.set_page(wishlist.Page(rows=tuple(r for r in wishlist.order(rows) if not r.on_sale)), wishlist.ON_SALE)
    check("On sale with nothing on sale: said in words", page_widget.empty_label.isVisibleTo(window.wishlist_page)
          and page_widget.empty_label.text() == wishlist.NOTHING_ON_SALE)
    page_widget.set_page(None)
    check("a library that cannot answer: one sentence saying what to do", ui_wishlist.UNAVAILABLE ==
          page_widget.empty_label.text() and not page_widget.list.count())
except Exception as exc:
    unreached("5", exc)

print("\n=== 6. the notice, retired in Phase 101: a line on the page ===")
try:
    # The once-a-day "N wishlist games at their lowest price seen" toast is gone: the price alerts (Phase 101)
    # tell each drop as it comes, in the window or the tray. The count stays, as a line on the page.
    low = [wishlist.row_of(view(1, is_lowest_now=1), FIT, False, False),
           wishlist.row_of(view(2, is_lowest_now=1), FIT, False, False),
           wishlist.row_of(view(3), FIT, False, False)]
    check("no daily notice any more, in the logic or the window",
          not hasattr(wishlist, "notice") and not hasattr(window, "_wishlist_notice")
          and not hasattr(rules, "WISHLIST_NOTICE_SETTING"))
    page_widget.set_page(wishlist.Page(rows=tuple(low)))
    check("its count is a line on the page: '2 at their lowest price seen'",
          "· 2 at their lowest price seen" in page_widget.summary.text(), page_widget.summary.text())
    page_widget.set_page(wishlist.Page(rows=tuple(low[:1])))
    check("one alone: 'at its lowest'", "· 1 at its lowest price seen" in page_widget.summary.text(),
          page_widget.summary.text())
    page_widget.set_page(wishlist.Page(rows=tuple(low[2:])))
    check("none at its lowest: no such words", "lowest" not in page_widget.summary.text(), page_widget.summary.text())
except Exception as exc:
    unreached("6", exc)

print("\n=== 7. the store page; hiding from the page ===")
try:
    asked: list[str] = []
    answers = iter([True])
    real_open = ui_settings.open_in_browser
    ui_settings.open_in_browser = lambda url: asked.append(url) or next(answers, False)
    try:
        window.open_store(1144200)
        answers = iter([False, True])
        window.open_store(1144200)
    finally:
        ui_settings.open_in_browser = real_open
    check("the client's store page by the protocol Steam registered", asked[0] == "steam://store/1144200", asked)
    check("and the store's web page when no client takes it", asked[1:] == ["steam://store/1144200",
                                                                             "https://store.steampowered.com/app/1144200/"],
          asked)
    window.show_wishlist()
    settle(0.6)
    model = window.wishlist_page.model
    target = model.rows[0].appid
    before = json.loads((SANDBOX / "config.json").read_text(encoding="utf-8"))
    window.set_wishlist_hidden(target, True)
    after = json.loads((SANDBOX / "config.json").read_text(encoding="utf-8"))
    hidden_model = window.wishlist_page.model
    check("hidden: off the page's list, under the 'Hidden from this page' fold",
          target not in [r.appid for r in hidden_model.rows] and [r.appid for r in hidden_model.hidden] == [target])
    check("kept in config.json as one key, nothing else of it changed",
          after.get(rules.WISHLIST_HIDDEN_SETTING) == [target]
          and {k: v for k, v in after.items() if k != rules.WISHLIST_HIDDEN_SETTING}
          == {k: v for k, v in before.items() if k != rules.WISHLIST_HIDDEN_SETTING})
    window.set_wishlist_hidden(target, False)
    check("shown again: back on the list, the key empty",
          target in [r.appid for r in window.wishlist_page.model.rows]
          and json.loads((SANDBOX / "config.json").read_text(encoding="utf-8")).get(rules.WISHLIST_HIDDEN_SETTING) == [])
    check("nothing about a wishlist is written to Steam: the page opens pages and keeps marks, no request",
          not attempts, attempts[:3])
except Exception as exc:
    unreached("7", exc)

print("\n=== 8. the covers ===")
try:
    cache = str(WORK / "cache")
    fetched: list[str] = []
    real_get = steam_web._get
    steam_web._get = lambda url: fetched.append(url) or (b"\xff\xd8" + b"x" * (rules.STEAM_ARTWORK_MIN_BYTES + 10))
    try:
        worker = CapsuleWorker([111, 222], cache)
        landed: list = []
        worker.ready.connect(lambda appid, path: landed.append((appid, path)))
        worker.start()
        deadline = time.monotonic() + 15
        while worker.isRunning() and time.monotonic() < deadline:
            settle(0.2)
        settle(0.3)
        again = steam_web.fetch_capsule(111, cache)
    finally:
        steam_web._get = real_get
    check("one request a cover, to the appid-keyed CDN, each landing as it arrives",
          fetched == [rules.STEAM_CAPSULE_URL.format(appid=a) for a in (111, 222)]
          and [a for a, _p in landed] == [111, 222], (fetched, landed))
    check("into the cache's steam_art, as a scanned game's cover", all(Path(p).parent.name == "steam_art"
                                                                       and Path(p).name == f"{a}.jpg" for a, p in landed))
    check("a cover already there is not asked again", again == landed[0][1] and len(fetched) == 2)
    check("never more than a visit's share", len(CapsuleWorker(list(range(100)), cache).appids)
          == rules.WISHLIST_ART_PER_VISIT)
    window.config["allow_network"] = False
    window.capsule_worker = None
    window._fetch_wishlist_covers([333])
    check("with the network off, no cover is fetched", window.capsule_worker is None)
except Exception as exc:
    unreached("8", exc)

print("\n=== 9. rendered, at 100% and in TV mode ===")
try:
    for label, tv in (("100%", False), ("TV", True)):
        window.set_tv_mode(tv)
        settle(1.0)
        window.show_wishlist()
        settle(0.8)
        shown = window.wishlist_page.list
        bar = shown.horizontalScrollBar()
        rect = shown.visualItemRect(shown.item(0))
        inside = shown.mapTo(window, rect.topRight()).x() <= window.width()
        check(f"{label}: the rows on the window, nothing to scroll sideways", inside and bar.maximum() == 0
              and shown.count() > 0, (bar.maximum(), rect))
        picture = window.grab().toImage()
        second = shown.visualItemRect(shown.item(1))
        middle = shown.viewport().mapTo(window, QPoint(second.center().x(), second.top() + 12))
        ground = picture.pixelColor(shown.viewport().mapTo(window, QPoint(second.center().x(),
                                                                          second.bottom() - 2)))
        glass = picture.pixelColor(middle)
        check(f"{label}: a row's glass painted, lighter than the gap under it", glass.lightness() > ground.lightness(),
              (glass.name(), ground.name()))
        top = shown.viewport().mapTo(window, QPoint(rect.center().x(), rect.top() + 1))
        ring = picture.pixelColor(top)
        focus = QColor(ui_rules.TILE_FOCUS_COLOR)
        check(f"{label}: the selected row ringed in the focus colour",
              abs(ring.red() - focus.red()) + abs(ring.green() - focus.green()) + abs(ring.blue() - focus.blue()) < 90,
              (ring.name(), focus.name()))
        window.grab().save(str(Path(tempfile.gettempdir()) / f"phase87_{label.replace('%', '')}.png"))
    window.set_tv_mode(False)
    settle(0.8)
    window.show_wishlist()
    settle(0.5)
    QApplication.sendEvent(window.wishlist_page,
                           QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
    settle(0.6)
    check("Escape goes back to the library", page(window) == ui_window.LIBRARY_PAGE)
except Exception as exc:
    unreached("9", exc)

print("\n=== 10. the documents, the layers ===")
try:
    claude = (PROJECT / "CLAUDE.md").read_text(encoding="utf-8")
    check("CLAUDE.md has the phase and its notes", "| 87 |" in claude and "## Phase 87 notes" in sources.build_log())
    baza = (PROJECT / "docs" / "BAZA_DE_DATE.md").read_text(encoding="utf-8")
    check("BAZA_DE_DATE gives the two queries to look with", "SELECT * FROM v_wishlist_now ORDER BY discount_percent DESC"
          in baza and "SELECT * FROM wishlist" in baza)
    readme = (PROJECT / "docs" / "CITESTE-MA.md").read_text(encoding="utf-8")
    check("CITESTE-MA names the Wishlist page", "**Wishlist**" in readme)
    layers = subprocess.run([sys.executable, str(PROJECT / "tests" / "check_layers.py")], capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    check("no import points up a layer; sqlite3 only in data_access/", layers.returncode == 0, layers.stdout[-300:])
    check("nothing in this suite reached the network", attempts == [], attempts[:3])
except Exception as exc:
    unreached("10", exc)

while window.worker is not None and window.worker.isRunning():
    settle(0.2)
window.close()
settle(0.3)
window.overrides.close()

print("\n=== 11. the real library is exactly as it was found ===")
changed = box.finish()
check("config.json and the library database are unchanged", not changed, changed)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
