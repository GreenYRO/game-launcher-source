"""Phase 74: prices, step 2 of 2 -- what I paid, and the four facts on a game's page.

The money formatter (one, used everywhere); purchases added, shown and removed through the
store and through the "What I paid..." dialog, with the mouse and with the pad, on a game with
no customisation of its own, touching no other field of its record; purchases in the export
bundle, joined on import and never taken away, an older bundle still importing; and the four
facts -- List price, Lowest seen, Paid, Cost per hour -- each shown exactly when it has
something to say, across every game.

On a throwaway copy of the data (the database at version 2, the Steam caches copied in, read
only). Nothing is fetched.
"""
import json
import sqlite3
import sys
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import test_sandbox

box = test_sandbox.start()  # the library as the launcher runs on it: version 2
SANDBOX = box.folder
box.copy_cache("steam_details", "steam_web.json", "steam_search.json")  # copies, read only

import logging

logging.basicConfig(level=logging.ERROR)

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

app = QApplication([])

from adapters import controller
from data_access import catalog_io, library_db
from logic import gamedetails, transfer
from presentation import ui_actions, ui_window
from shared import humanize, rules

try:
    from presentation import ui_purchases
except ImportError:  # the code before this phase has none; the sections that need it say so
    ui_purchases = None

passed = failed = 0
NB = " "


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"   PASS  {name}")
    else:
        failed += 1
        print(f"   FAIL  {name}   {detail}")


def unreached(section: str, exc: Exception):
    """A section that could not run to its end on this code counts as one failure."""
    check(f"section {section} runs to its end on this code", False, repr(exc))


def settle(seconds: float) -> None:
    loop = QEventLoop()
    QTimer.singleShot(int(seconds * 1000), loop.quit)
    loop.exec()


print("=== 1. one money formatter ===")
try:
    for cents, currency, words in ((5999, "EUR", f"59,99{NB}€"), (0, "EUR", f"0,00{NB}€"),
                                   (129900, "EUR", f"1.299,00{NB}€"), (1250, "RON", f"12,50{NB}lei"),
                                   (500, "USD", f"5,00{NB}USD"), (-150, "EUR", f"-1,50{NB}€"),
                                   (123456789, "EUR", f"1.234.567,89{NB}€")):
        check(f"{cents} {currency} -> {words!r}", humanize.money(cents, currency) == words,
              humanize.money(cents, currency))
    this_year = date.today().year
    check("a date this year has no year; another year has it; a purchase always does",
          humanize.day(date(this_year, 10, 11)) == "11 Oct" and humanize.day(date(2025, 12, 20)) == "20 Dec 2025"
          and humanize.day(date(this_year, 5, 3), year=True) == f"3 May {this_year}")
    late = datetime(this_year, 10, 11, 22, 30, tzinfo=timezone.utc)
    check("a UTC moment is read in local time", humanize.day(late) == humanize.day(late.astimezone().date()))
except Exception as exc:
    unreached("1", exc)

window = ui_window.MainWindow()
window.resize(1280, 820)
window.show()
settle(1.0)
store = window.overrides
plain = next(v for v in window.views if v.entry.source == "folders" and not v.hidden and not v.favorite
             and not v.notes and not v.status and not v.data.get("cover") and not v.data.get("banner")
             and not v.data.get("name") and not v.data.get("exe") and not v.data.get("args")
             and not (store.purchases(v.key) if hasattr(store, "purchases") else []))
print(f"   (the plain game: {plain.display_name} -- a folder game with nothing chosen for it)")

print("\n=== 2. purchases through the store ===")
try:
    record_before = json.dumps(store.get(plain.key), sort_keys=True)
    first = store.add_purchase(plain.key, paid_cents=1250, currency="EUR", store="key reseller",
                               bought_on="2026-05-03", note="a sale")
    second = store.add_purchase(plain.key, paid_cents=0, currency="EUR", store="gift")
    rows = store.purchases(plain.key)
    check("two purchases kept, in their order -- a date unknown last",
          [r["id"] for r in rows] == [first, second] and rows[1]["bought_on"] is None)
    check("0 is a real purchase (a gift), and kept as one", rows[1]["paid_cents"] == 0)
    check("nothing else of the game's record changed", json.dumps(store.get(plain.key), sort_keys=True) == record_before)
    check("a negative amount is refused, nothing kept",
          store.add_purchase(plain.key, paid_cents=-1, currency="EUR", store="Steam") is None
          and len(store.purchases(plain.key)) == 2)
    check("removing one takes it out, and only it", store.remove_purchase(second)
          and [r["id"] for r in store.purchases(plain.key)] == [first])
    store.remove_purchase(first)
    check("and the game is back to unknown", store.purchases(plain.key) == []
          and store.money(plain.key)["purchases"] == [])
except Exception as exc:
    unreached("2", exc)

print("\n=== 3. the dialog, with the mouse ===")
try:
    record_before = json.dumps(store.get(plain.key), sort_keys=True)
    menu = ui_actions.build_menu(window, window.by_key[plain.key])
    entry = next(a for a in menu.actions() if a.text() == "What I paid...")
    check("the game's menu offers What I paid...", entry.isEnabled())
    seen = {}

    def work_it():
        dialog = QApplication.activeModalWidget()
        seen["dialog"] = isinstance(dialog, ui_purchases.PurchaseDialog)
        seen["empty"] = dialog.empty.isVisible() and not dialog.list.isVisible()
        seen["defaults"] = (dialog.currency.currentText(), dialog.bought_on.date().toPython(),
                            dialog.remove_button.isEnabled())
        dialog.amount.setValue(12.5)
        dialog.shop.setCurrentText("key reseller")
        dialog.unknown_date.setChecked(True)
        dialog.note.setText("bundle")
        dialog.add_button.click()
        seen["listed"] = [dialog.list.item(i).text() for i in range(dialog.list.count())]
        seen["empty_after"] = dialog.empty.isVisible()

        def answer_cancel():
            box_ = QApplication.activeModalWidget()
            seen["question"] = isinstance(box_, QMessageBox)
            buttons = {b.text(): b for b in box_.buttons()}
            seen["cancel_safe"] = (box_.defaultButton() is buttons["Cancel"] and box_.escapeButton() is buttons["Cancel"]
                                   and box_.focusWidget() is buttons["Cancel"])
            buttons["Cancel"].click()

        QTimer.singleShot(300, answer_cancel)
        dialog.remove_button.click()
        seen["after_cancel"] = len(store.purchases(plain.key))

        def answer_remove():
            box_ = QApplication.activeModalWidget()
            next(b for b in box_.buttons() if b.text() == "Remove").click()

        QTimer.singleShot(300, answer_remove)
        dialog.remove_button.click()
        seen["after_remove"] = len(store.purchases(plain.key))
        dialog.close_button.click()

    QTimer.singleShot(400, work_it)
    entry.trigger()
    settle(0.3)
    check("it opens the dialog", seen.get("dialog"))
    check("a game with no purchase says unknown, not free, and shows no list", seen.get("empty"))
    check("EUR chosen, today's date, nothing to remove yet",
          seen.get("defaults") == ("EUR", date.today(), False), seen.get("defaults"))
    check("Add puts it in the list, as it reads", seen.get("listed") == [f"12,50{NB}€  ·  key reseller  ·  date unknown  ·  bundle"]
          and seen.get("empty_after") is False, seen.get("listed"))
    check("Remove asks first, Cancel the default, escape and focused button",
          seen.get("question") and seen.get("cancel_safe"))
    check("Cancel keeps it", seen.get("after_cancel") == 1)
    check("Remove, answered, takes it out", seen.get("after_remove") == 0)
    check("nothing else of the game's record changed", json.dumps(store.get(plain.key), sort_keys=True) == record_before)
except Exception as exc:
    unreached("3", exc)

print("\n=== 4. the dialog, with the pad ===")
try:
    window.show_detail(plain.key)
    settle(1.2)
    pressed: list[str] = []
    notes: dict = {}

    def press(name):
        pressed.append(name)
        window.pads.action.emit(name)

    def until(predicate, name, tries=12):
        """Press `name` until `predicate()` holds, one press a step."""
        def step():
            if predicate():
                return True
            if tries_left[0] <= 0:
                return True
            tries_left[0] -= 1
            press(name)
            return False
        tries_left = [tries]
        return step

    def modal():
        return QApplication.activeModalWidget()

    def focused_text():
        widget = modal().focusWidget() if modal() is not None else None
        return widget.text() if hasattr(widget, "text") and callable(widget.text) else ""

    def menu_on_purchases():
        popup = QApplication.activePopupWidget()
        if popup is None:
            return False
        action = next((a for a in popup.actions() if a.text() == "What I paid..."), None)
        popup.setActiveAction(action)
        return True

    steps = [
        lambda: press(controller.MENU) or True,  # X: the page's "..." menu
        menu_on_purchases,
        lambda: press(controller.ACTIVATE) or True,  # A: What I paid...
        lambda: notes.update(gate=window._launcher_in_front(), open=isinstance(modal(), ui_purchases.PurchaseDialog)) or True,
        lambda: press(controller.RIGHT) or True,  # the amount, up by one
        lambda: press(controller.RIGHT) or True,
        lambda: press(controller.RIGHT) or True,
        lambda: notes.update(amount=modal().amount.value()) or True,
        until(lambda: modal().focusWidget() is modal().unknown_date, controller.DOWN),
        lambda: press(controller.ACTIVATE) or True,  # A ticks "Date unknown"
        until(lambda: modal().focusWidget() is modal().add_button, controller.DOWN),
        lambda: press(controller.ACTIVATE) or True,  # A presses Add
        lambda: notes.update(added=store.purchases(plain.key)) or True,
        until(lambda: modal().focusWidget() is getattr(modal(), "remove_button", None), controller.DOWN),
        lambda: press(controller.ACTIVATE) or True,  # A on Remove: the question
        lambda: notes.update(asked=isinstance(modal(), QMessageBox), on=focused_text()) or True,
        lambda: press(controller.ACTIVATE) or True,  # A at once: Cancel
        lambda: notes.update(kept=len(store.purchases(plain.key)), back=isinstance(modal(), ui_purchases.PurchaseDialog)) or True,
        lambda: press(controller.ACTIVATE) or True,  # Remove again
        until(lambda: focused_text() == "Remove", controller.RIGHT),
        lambda: press(controller.ACTIVATE) or True,
        lambda: notes.update(removed=len(store.purchases(plain.key))) or True,
        lambda: press(controller.BACK) or True,  # B closes
        lambda: notes.update(closed=modal() is None) or True,
    ]
    position = [0]
    loop = QEventLoop()

    def advance():
        if position[0] >= len(steps):
            loop.quit()
            return
        QTimer.singleShot(250, advance)  # before running: a step may sit inside a dialog's own loop
        try:
            if steps[position[0]]():
                position[0] += 1
        except Exception as exc:  # noqa: BLE001
            notes.setdefault("errors", []).append(f"step {position[0]}: {exc!r}")
            position[0] += 1

    def watchdog():
        for widget in (QApplication.activePopupWidget(), QApplication.activeModalWidget()):
            if widget is not None:
                widget.close()
        notes["watchdog"] = True
        loop.quit()

    QTimer.singleShot(250, advance)
    QTimer.singleShot(60_000, watchdog)
    loop.exec()
    settle(0.3)
    check("X then A opens What I paid from the game's page", notes.get("open"), notes)
    check("and the pad's gate is open while it is: the launcher's own window is in front", notes.get("gate"))
    check("right steps the amount up", notes.get("amount") == 3.0, notes.get("amount"))
    added = notes.get("added") or []
    check("down to Date unknown, A ticks it, down to Add, A adds it",
          len(added) == 1 and added[0]["paid_cents"] == 300 and added[0]["bought_on"] is None, added)
    check("A on Remove asks, and the button under A is Cancel", notes.get("asked") and notes.get("on") == "Cancel",
          notes.get("on"))
    check("A at once cancels: kept, the dialog back", notes.get("kept") == 1 and notes.get("back"))
    check("moving to Remove and A takes it out", notes.get("removed") == 0)
    check("B closes the dialog", notes.get("closed"))
    check("no watchdog and no error on the way", not notes.get("watchdog") and not notes.get("errors"),
          notes.get("errors"))
except Exception as exc:
    unreached("4", exc)

print("\n=== 5. the four facts, each exactly when it has something to say ===")
try:
    # Plant what the library does not have yet: purchases on a few games, and a price seen lower
    # than today's for one -- added to the copy's series, as an observation would be.
    timed = [v for v in window.views if v.playtime_seconds > 0 and v.entry.extra.get("appid")]
    mixed, double, solo = timed[0], timed[1], timed[2]
    store.add_purchase(solo.key, paid_cents=2999, currency="EUR", store="Steam", bought_on="2026-03-01")
    store.add_purchase(double.key, paid_cents=1000, currency="EUR", store="GOG", bought_on="2026-01-01")
    store.add_purchase(double.key, paid_cents=500, currency="EUR", store="GOG", bought_on="2026-02-01", note="DLC")
    store.add_purchase(mixed.key, paid_cents=1000, currency="EUR", store="Steam")
    store.add_purchase(mixed.key, paid_cents=5000, currency="RON", store="key reseller")
    appid = int(solo.entry.extra["appid"])
    latest = store._conn.execute("SELECT kind, final_cents FROM v_price_latest WHERE appid = ?", (appid,)).fetchone()
    lower_at = "2026-01-15T12:00:00+00:00"
    store.add_observations([{"appid": appid, "observed_at": lower_at, "kind": "priced", "currency": "EUR",
                             "initial_cents": 100, "final_cents": 1, "discount_percent": 99}])

    reader = sqlite3.connect(f"{(SANDBOX / rules.LIBRARY_DB_FILE).resolve().as_uri()}?mode=ro", uri=True)
    wrong: dict[str, list] = {fact: [] for fact in gamedetails.MONEY_FACTS}
    for view in window.views:
        shown = dict(gamedetails.money_facts(window.money_of(view)))
        row = reader.execute("SELECT steam_appid, purchases, paid_cents, playtime_seconds FROM v_game_money "
                             "WHERE identity_key = ?", (view.key,)).fetchone()
        steam, count, paid, playtime = row if row else (None, None, None, None)
        newest = reader.execute("SELECT kind, final_cents FROM v_price_latest WHERE appid = ?", (steam,)).fetchone()
        span = reader.execute("SELECT observations, lowest_cents FROM v_price_range WHERE appid = ?", (steam,)).fetchone()
        expect = {
            "List price": newest is not None,
            "Lowest seen": bool(span and span[0] > 1 and span[1] is not None
                                and not (newest and newest[0] == "priced" and newest[1] == span[1])),
            "Paid": bool(count),
            "Cost per hour": paid is not None and (playtime or 0) > 0,
        }
        for fact, wanted in expect.items():
            if (fact in shown) != wanted:
                wrong[fact].append(view.display_name)
    reader.close()
    print(f"         ({len(window.views)} games looked at)")
    for fact in gamedetails.MONEY_FACTS:
        check(f"{fact}: shown on exactly the games that have it", not wrong[fact], wrong[fact][:5])

    facts = dict(gamedetails.money_facts(window.money_of(window.by_key[solo.key])))
    observed = store._conn.execute("SELECT observed_at FROM v_price_latest WHERE appid = ?", (appid,)).fetchone()[0]
    check("List price reads as the brief has it: amount, on Steam, as of the day",
          latest[0] != "priced" or facts.get("List price", "").startswith(humanize.money(latest[1], "EUR") + " on Steam")
          and facts["List price"].endswith(f", as of {humanize.day(datetime.fromisoformat(observed))}"), facts.get("List price"))
    check("Lowest seen: the lower price and its day", facts.get("Lowest seen") == f"0,01{NB}€ on 15 Jan", facts.get("Lowest seen"))
    check("Paid, one purchase: amount, store, the whole date",
          facts.get("Paid") == f"29,99{NB}€, Steam, 1 Mar 2026", facts.get("Paid"))
    per_hour = round(2999 * 3600 / solo.playtime_seconds)
    check("Cost per hour: what was paid over the launcher's hours",
          facts.get("Cost per hour") == f"{humanize.money(per_hour, 'EUR')} an hour", facts.get("Cost per hour"))
    facts = dict(gamedetails.money_facts(window.money_of(window.by_key[double.key])))
    check("Paid, two purchases: the total and how many", facts.get("Paid") == f"15,00{NB}€ in 2 purchases",
          facts.get("Paid"))
    facts = dict(gamedetails.money_facts(window.money_of(window.by_key[mixed.key])))
    check("in two currencies, never added up -- and no cost per hour from it",
          facts.get("Paid") == "2 purchases, in more than one currency" and "Cost per hour" not in facts, facts)
    free_one = next((v for v in window.views if (window.money_of(v) or {}).get("latest")
                     and window.money_of(v)["latest"]["kind"] == "free"), None)
    if free_one is not None:
        check(f"a free game's list price says so ({free_one.display_name})",
              dict(gamedetails.money_facts(window.money_of(free_one))).get("List price") == "free")
    window.reload_views()
    window.show_detail(solo.key)
    settle(1.0)
    on_page = window.detail.facts()
    check("on the game's own page, in its Details", all(on_page.get(f) for f in gamedetails.MONEY_FACTS),
          {f: on_page.get(f) for f in gamedetails.MONEY_FACTS})
    window.show_library()
    settle(0.5)
except Exception as exc:
    unreached("5", exc)

print("\n=== 6. purchases travel in the bundle; the price series does not ===")
try:
    bundle = SANDBOX / "export.gamelauncher.zip"
    report = transfer.export_bundle(bundle, store=store)
    with zipfile.ZipFile(bundle) as archive:
        names = set(archive.namelist())
        carried = json.loads(archive.read(rules.TRANSFER_PURCHASES_MEMBER))["games"] if rules.TRANSFER_PURCHASES_MEMBER in names else {}
        manifest = json.loads(archive.read(rules.TRANSFER_MANIFEST))
    mine = store.all_purchases()
    # The five this suite planted, and any the user's own library holds -- counted, never assumed
    # (his click-through list left one on Slow Roads on 11 October).
    total = sum(len(rows) for rows in mine.values())
    check(f"the bundle carries every purchase ({total}), by game, without ids",
          total >= 5 and carried == mine and all("id" not in r for rows in carried.values() for r in rows)
          and report.purchases == total)
    check("the manifest counts them; the report says so",
          manifest.get("purchases") == total and f"{total} purchases" in report.message, report.message)
    check("nothing of the price series is in it", not any("price" in n for n in names - {rules.TRANSFER_PURCHASES_MEMBER}))
    other = library_db.LibraryStore(SANDBOX / "other.db")
    other.add_purchase(solo.key, paid_cents=7000, currency="EUR", store="Epic", bought_on="2025-12-24")
    imported = transfer.import_bundle(bundle, store=other)
    check("imported into another library: every purchase, joined to the one already there",
          imported.ok and imported.purchases == total and len(other.purchases(solo.key)) == 2, imported.message)
    again = transfer.import_bundle(bundle, store=other)
    check("imported twice: nothing added -- the same date, amount and store are the same purchase",
          again.ok and again.purchases == 0 and sum(len(r) for r in other.all_purchases().values()) == total + 1)
    check("and nothing taken away: the one only that library had is still there",
          any(r["store"] == "Epic" for r in other.purchases(solo.key)))
    older = SANDBOX / "older.gamelauncher.zip"
    with zipfile.ZipFile(bundle) as source, zipfile.ZipFile(older, "w") as target:
        for name in source.namelist():
            if name != rules.TRANSFER_PURCHASES_MEMBER:
                target.writestr(name, source.read(name))
    old_report = transfer.import_bundle(older, store=other)
    check("a bundle from before purchases still imports, and changes none",
          old_report.ok and old_report.purchases == 0
          and sum(len(r) for r in other.all_purchases().values()) == total + 1)
    other.close()
    json_store = catalog_io.Overrides(path=SANDBOX / "json-library.json")
    skipped = transfer.import_bundle(bundle, store=json_store)
    check("into a library that keeps no purchases: the rest imports, and it says what it could not",
          skipped.ok and skipped.purchases_skipped == total and "not imported" in skipped.message, skipped.message)
except Exception as exc:
    unreached("6", exc)

print("\n=== 7. every scan says how many prices it asks for, none included ===")
try:
    from logic import prices

    heard: list[str] = []

    class Keep(logging.Handler):
        def emit(self, record):
            heard.append(record.getMessage())

    keeper = Keep(level=logging.INFO)
    prices_log = logging.getLogger("logic.prices")
    prices_log.addHandler(keeper)
    prices_log.setLevel(logging.INFO)
    try:
        due = prices.due(store, True)
        prices.due(store, False)
    finally:
        prices_log.removeHandler(keeper)
    check("the network on: the count, zero or not", any(f"prices: {len(due)} app(s) due for a price this scan" in line
                                                        for line in heard), heard)
    check("the network off: says none were asked, and why", any("none asked for this scan -- the network is off" in line
                                                               for line in heard), heard)
except Exception as exc:
    unreached("7", exc)

window.close()
settle(0.3)
store.close()

print("\n=== 8. the real library is exactly as it was found ===")
changed = box.finish()
check("config.json and the library database are unchanged", not changed, changed)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
