"""Phase 70: the Steam projection after every scan.

The database, step 7 of 8. steam_app and its satellites are a projection of the Steam records
cached on disk (cache/steam_details/<appid>.json). The migration made it once; from this phase
every scan brings it up to date with what is on disk, on the GUI thread, after the scan's own
findings are written -- so the database's Steam tables say what the cache says. And the cache
now says when each record was fetched: the summary's `fetched_at` moves whenever a picture is
cached, so it could not.

On a throwaway copy of the data (the database the launcher runs on, the Steam caches copied in,
read only), with nothing fetched: where a test needs Steam to answer, `steam_web._get` is
handed the answer.
"""
import json
import os
import sqlite3
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import test_sandbox

box = test_sandbox.start()  # the database, as the launcher runs on it
SANDBOX = box.folder
box.copy_cache("steam_details", "steam_web.json", "steam_search.json")  # copies, read only

import logging

lines: list[str] = []


class Keep(logging.Handler):
    def emit(self, record):
        lines.append(record.getMessage())


logging.basicConfig(level=logging.CRITICAL)
logging.getLogger().addHandler(Keep(level=logging.INFO))
logging.getLogger().setLevel(logging.INFO)

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

app = QApplication([])

from data_access import catalog_io, library_db
from logic import migration
from presentation import ui_window

try:
    from logic import steam_projection
except ImportError:  # the code before this phase has none; the sections that need it say so
    steam_projection = None
from shared import paths, rules
from web import steam_web

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
    """A section that could not run to its end on this code counts as one failure."""
    check(f"section {section} runs to its end on this code", False, repr(exc))


def settle(seconds: float) -> None:
    loop = QEventLoop()
    QTimer.singleShot(int(seconds * 1000), loop.quit)
    loop.exec()


def steam_tables(path: Path) -> dict[str, list]:
    """What a database's Steam tables hold, by name rather than by surrogate id, read only."""
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        return {
            "steam_app": list(conn.execute("SELECT * FROM steam_app WHERE has_record = 1 ORDER BY appid")),
            "genres": list(conn.execute("SELECT a.appid, g.name FROM steam_app_genre a JOIN genre g "
                                        "ON g.id = a.genre_id ORDER BY 1, 2")),
            "categories": list(conn.execute("SELECT a.appid, c.id, c.name FROM steam_app_category a "
                                            "JOIN category c ON c.id = a.category_id ORDER BY 1, 2")),
            "companies": list(conn.execute("SELECT a.appid, c.name, a.role FROM steam_app_company a "
                                           "JOIN company c ON c.id = a.company_id ORDER BY 1, 2, 3")),
        }
    finally:
        conn.close()


def as_the_cache_says(target: Path) -> dict[str, list]:
    """A database made from nothing but the cache: every stored record, at the moment it was fetched."""
    target.unlink(missing_ok=True)
    conn = library_db.connect(target)
    try:
        library_db.create(conn)
        moments = steam_web.details_fetched_at(CACHE)
        with library_db.transaction(conn):
            for appid in steam_web.stored_detail_ids(CACHE):
                library_db.store_steam_app(conn, int(appid), steam_web.load_details(CACHE, appid), moments.get(appid))
    finally:
        conn.close()
    return steam_tables(target)


def as_fetched_before(appids, keys=("details_at", "details_cc")) -> None:
    """Make records look as ones fetched before Phase 70 did: no fetch moment, no country.

    The user's own scans fetch records with both since Phase 70 -- Phase 75's Steam history
    brought 18 on 11 October -- so a subject picked from the copy may carry them, and sections 3
    and 6 are about records that do not: one whose moment is its file's, and one priced in
    another currency before the store was asked for Romania. Only the copy's summary changes.
    """
    cache = steam_web.SteamWebCache(CACHE)
    for appid in appids:
        for key in keys:
            cache.records.get(appid, {}).pop(key, None)
    cache._dirty = True  # save() writes only what put() changed; these were changed by hand
    cache.save()


def summary() -> dict:
    return json.loads((Path(CACHE) / steam_web.CACHE_FILE).read_text(encoding="utf-8"))["apps"]


DATABASE = SANDBOX / rules.LIBRARY_DB_FILE
stored = steam_web.stored_detail_ids(CACHE)
print(f"   ({len(stored)} Steam records copied into the test's cache)")

print("=== 1. the cache says when a record was fetched ===")
try:
    # A record of the copy's, answered again by "Steam" with a different price: what a scan
    # fetching a stale record would get. Nothing leaves the machine.
    subject = next(a for a in stored if (steam_web.load_details(CACHE, a).get("price_overview") or {}).get("final"))
    answer = dict(steam_web.load_details(CACHE, subject))
    answer["price_overview"] = dict(answer["price_overview"], final=1234, initial=1234, discount_percent=0)
    real_get = steam_web._get
    steam_web._get = lambda url: json.dumps({subject: {"success": True, "data": answer}}).encode()
    try:
        before = datetime.now(timezone.utc).replace(microsecond=0)
        got = steam_web._fetch_details(subject, steam_web.make_budget(), CACHE)
    finally:
        steam_web._get = real_get
    check("a record fetched now says when, beside the two fields it always gave",
          got and got.get("details_at") and datetime.fromisoformat(got["details_at"]) >= before, got)
    check("its file holds what Steam answered", steam_web.load_details(CACHE, subject) == answer)
    cache = steam_web.SteamWebCache(CACHE)
    cache.put(subject, **got)  # as enrich() files it
    cache.save()
    check("the moment the cache gives for it is that one",
          steam_web.details_fetched_at(CACHE)[subject] == got["details_at"])
    older = [a for a in stored if a != subject and "details_at" not in summary().get(a, {})]
    moments = steam_web.details_fetched_at(CACHE)
    by_file = {a: datetime.fromtimestamp(os.path.getmtime(steam_web.details_path(CACHE, a)), timezone.utc)
               .isoformat(timespec="seconds") for a in older}
    check(f"a record fetched before this phase ({len(older)}): the time its file was written",
          older and all(moments[a] == by_file[a] for a in older))
    moved = [a for a in older if summary().get(a, {}).get("fetched_at") not in (None, by_file[a])]
    check(f"not the summary's fetched_at, which a cached picture moves ({len(moved)} differ)",
          all(moments[a] != summary()[a]["fetched_at"] for a in moved))
    news = {subject: got}
except Exception as exc:
    unreached("1", exc)
    news = {}

print("\n=== 2. after a scan, the database's Steam tables say what the cache says ===")
try:
    window = ui_window.MainWindow()
    window.show()
    settle(0.5)
    check("the window runs on the database", isinstance(window.overrides, library_db.LibraryStore))
    old_row = window.overrides.steam_fetched().get(int(subject))
    writers: list[int] = []
    real_store = library_db.store_steam_app

    def watched(conn, appid, record, fetched_at):
        writers.append((threading.get_ident(), appid))
        return real_store(conn, appid, record, fetched_at)

    library_db.store_steam_app = watched
    try:
        started = window.start_scan(background=True)
        deadline = time.monotonic() + 180
        while window.worker is not None and window.worker.isRunning() and time.monotonic() < deadline:
            settle(0.2)
        settle(0.5)
    finally:
        library_db.store_steam_app = real_store
    check("a scan ran", started)
    reference = as_the_cache_says(SANDBOX / "as-the-cache-says.db")
    there = steam_tables(DATABASE)
    for table in ("steam_app", "genres", "categories", "companies"):
        check(f"{table}: the database holds exactly what the cache says ({len(reference[table])} rows)",
              there[table] == reference[table] and reference[table],
              [row for row in there[table] if row not in reference[table]][:3])
    check("the record fetched again shows its new price", any(r[0] == int(subject) and 1234 in r for r in there["steam_app"]))
    check("and the moment it was fetched", window.overrides.steam_fetched()[int(subject)] == news[subject]["details_at"]
          != old_row, (old_row, window.overrides.steam_fetched()[int(subject)]))
    check("written by the GUI thread, after the scan -- the one writer",
          writers and {ident for ident, _ in writers} == {threading.main_thread().ident})
    first_pass = len(writers)
    writers.clear()
    library_db.store_steam_app = watched
    try:
        window.start_scan(background=True)
        deadline = time.monotonic() + 180
        while window.worker is not None and window.worker.isRunning() and time.monotonic() < deadline:
            settle(0.2)
        settle(0.5)
    finally:
        library_db.store_steam_app = real_store
    check(f"a second scan, with nothing fetched, projects nothing again (the first: {first_pass})",
          writers == [] and steam_tables(DATABASE) == reference, writers[:5])
except Exception as exc:
    unreached("2", exc)

print("\n=== 3. a record that does not fit is left out; the others still land ===")
try:
    broken = next(a for a in stored if a != subject and steam_web.load_details(CACHE, a).get("genres"))
    other = next(a for a in stored if a not in (subject, broken))
    as_fetched_before([broken, other])  # their moments are their files' from here on
    kept_row = [r for r in steam_tables(DATABASE)["steam_app"] if r[0] == int(broken)]
    original_broken = steam_web.load_details(CACHE, broken)
    bad = dict(original_broken)
    bad["genres"] = [{"description": "a genre with no id"}]
    steam_web._store_details(CACHE, broken, bad)
    original_other = steam_web.load_details(CACHE, other)
    good = dict(original_other, name="Renamed by the test")
    steam_web._store_details(CACHE, other, good)
    lines.clear()
    done = steam_projection.refresh(window.overrides)
    check("the one that does not fit is refused, and named", list(done.refused) == [int(broken)], done.refused)
    check("its row is as it was", [r for r in steam_tables(DATABASE)["steam_app"] if r[0] == int(broken)] == kept_row)
    check("the other, changed in the same pass, lands",
          int(other) in done.stored and any(r[0] == int(other) and "Renamed by the test" in r
                                            for r in steam_tables(DATABASE)["steam_app"]))
    check("and the log says which and why",
          any(f"record for {broken} does not fit" in line and "KeyError" in line for line in lines), lines[-3:])
    # A fetch moment is kept to the second, as every time in the library is; the same record
    # written twice within one second would look unchanged. A fetch never does that -- one
    # request a second at most, and a record is fetched again after 30 days -- so the test
    # waits, as a real fetch would.
    time.sleep(1.1)
    steam_web._store_details(CACHE, broken, original_broken)  # the two records as they were
    steam_web._store_details(CACHE, other, original_other)
    done = steam_projection.refresh(window.overrides)
    check("put right, the next pass takes both in -- the database what the cache says again",
          {int(broken), int(other)} <= set(done.stored) and not done.refused
          and steam_tables(DATABASE) == as_the_cache_says(SANDBOX / "as-the-cache-says.db"), done.refused)
    window.close()
except Exception as exc:
    unreached("3", exc)

print("\n=== 4. the JSON store, after a refused migration, keeps no projection ===")
try:
    json_store = catalog_io.Overrides(path=SANDBOX / "a-json-library.json")
    done = steam_projection.refresh(json_store)
    check("nothing is read or written, and nothing fails", not done.stored and not done.refused
          and not (SANDBOX / "a-json-library.json").exists())
except Exception as exc:
    unreached("4", exc)

print("\n=== 5. a migration records the same moments ===")
try:
    records = window.overrides.export_records()
    entries = window.overrides.load_catalog()
    built = migration.build(SANDBOX / "migrated-again.db", records, entries)
    conn = sqlite3.connect(f"{(SANDBOX / 'migrated-again.db').as_uri()}?mode=ro", uri=True)
    try:
        theirs = dict(conn.execute("SELECT appid, fetched_at FROM steam_app WHERE has_record = 1"))
    finally:
        conn.close()
    moments = steam_web.details_fetched_at(CACHE)
    check("a database the migration builds says each record's fetch moment, as a scan's does",
          built.good and theirs and all(theirs[int(a)] == m for a, m in moments.items() if int(a) in theirs),
          [a for a, m in moments.items() if theirs.get(int(a)) != m][:3])
except Exception as exc:
    unreached("5", exc)

print("\n=== 6. the store is asked for Romania, and a record in another currency is fetched again once ===")
# Approved separately ("yes to both"): the address names the country, and the two records that
# came back in Polish zloty are fetched again. Steam's answers are handed to steam_web._get here.
try:
    check("the appdetails address asks for the store's country",
          rules.STEAM_APPDETAILS_URL.format(appid="550").endswith("&l=english&cc=RO"), rules.STEAM_APPDETAILS_URL)
    check("as the storefront search always has", rules.STEAM_SEARCH_URL.endswith("&cc=RO"), rules.STEAM_SEARCH_URL)

    def priced(appid):
        return (steam_web.load_details(CACHE, appid).get("price_overview") or {}).get("currency")

    in_euros = [a for a in stored if priced(a) == rules.STEAM_STORE_CURRENCY]
    planted = [a for a in in_euros if a != subject][:3]  # three records, made to look as the zloty ones did
    as_fetched_before(planted, keys=("details_cc",))  # fetched before the store was asked for Romania
    for appid in planted:
        record = steam_web.load_details(CACHE, appid)
        record["price_overview"] = dict(record["price_overview"], currency="PLN", final=22999)
        steam_web._store_details(CACHE, appid, record)
    foreign = sorted(a for a in stored if priced(a) not in (None, rules.STEAM_STORE_CURRENCY))
    print(f"   (priced in another currency in the test's cache: {foreign})")
    lost, gone, euro = planted  # Steam: no answer at all / no longer sold there / an answer in euros
    asked: list[str] = []

    def store_answers(url):
        asked.append(url)
        appid = url.split("appids=")[1].split("&")[0]
        if appid == lost:
            return None
        if appid == gone:
            return json.dumps({appid: {"success": False}}).encode()
        record = steam_web.load_details(CACHE, appid)
        record["price_overview"] = dict(record["price_overview"], currency="EUR", final=4999)
        return json.dumps({appid: {"success": True, "data": record}}).encode()

    real_get = steam_web._get
    steam_web._get = store_answers
    try:
        steam_web.enrich([], CACHE)  # what a scan with the network on runs; no entry needs anything
        first = list(asked)
        asked.clear()
        steam_web.enrich([], CACHE)
        second = list(asked)
    finally:
        steam_web._get = real_get
    fetched_for = sorted(url.split("appids=")[1].split("&")[0] for url in first)
    check("only the records in another currency are asked for, each once",
          fetched_for == foreign and len(first) == len(foreign), fetched_for)
    check("every request names the country", first and all(url.endswith("&cc=RO") for url in first))
    check("the one answered comes back in euros", priced(euro) == "EUR"
          and summary()[euro].get("details_cc") == "RO")
    check("one the store no longer sells there keeps its record, and is not asked for again",
          priced(gone) == "PLN" and summary()[gone].get("details_cc") == "RO" and summary()[gone].get("app_type"))
    check("one that got no answer is asked for at the next scan -- and only it", second == [
        url for url in first if f"appids={lost}&" in url], second)
    store = test_sandbox.library()
    done = steam_projection.refresh(store)
    check("and the next projection carries the euro price into the database",
          int(euro) in done.stored and any(r[0] == int(euro) and "EUR" in r and 4999 in r
                                          for r in steam_tables(DATABASE)["steam_app"]))
    store.close()
except Exception as exc:
    unreached("6", exc)

print("\n=== 7. the real library is exactly as it was found ===")
changed = box.finish()
check("config.json and the library database are unchanged", not changed, changed)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
