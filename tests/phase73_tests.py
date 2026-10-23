"""Phase 73: prices -- the first schema upgrade, the price series, and its weekly observation.

The database, version 2. A database made by version 1 is brought up to it by the numbered
script in data_access/upgrades/ (schema evolution), additive only (expand before contract), a
snapshot first, in one transaction with the version bump; refused, it is left as it was and
the launcher runs on version 1. Two tables: price_snapshot, an append-only time series of what
the store answered, and purchase, what the user paid (filled from Phase 74). Three views. The
series is seeded from the Steam records already cached, and every window scan asks the store
for the prices that are a week old, the scan thread writing files and the GUI thread the rows.

On throwaway copies of the data, the Steam caches copied in, read only. The network is
blocked outright: the one request this phase made, on 11 October, is kept as a fixture and
handed to the code where a test needs the store to answer.
"""
import ast
import json
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import test_sandbox

box = test_sandbox.start(migrate=False)  # the library as it is: this suite upgrades it itself
SANDBOX = box.folder
box.copy_cache("steam_details", "steam_web.json", "steam_search.json")  # copies, read only

attempts: list[str] = []


def no_network(request, *args, **kwargs):
    attempts.append(getattr(request, "full_url", str(request)))
    raise OSError("the network is blocked in this suite")


urllib.request.urlopen = no_network

import logging

lines: list[str] = []


class Keep(logging.Handler):
    def emit(self, record):
        lines.append(f"{record.name}: {record.getMessage()}")


logging.basicConfig(level=logging.CRITICAL)
logging.getLogger().addHandler(Keep(level=logging.INFO))
logging.getLogger().setLevel(logging.INFO)

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

app = QApplication([])

from data_access import backups, catalog_io, library_db
from logic import migration, steam_projection

try:
    from logic import prices
except ImportError:  # the code before this phase has none; the sections that need it say so
    prices = None
from presentation import ui_window
from shared import paths, rules
from web import steam_web

CACHE = str(paths.cache_dir())
DATABASE = SANDBOX / rules.LIBRARY_DB_FILE
FIXTURE = json.loads((PROJECT / "tests" / "fixtures" / "appdetails_price_batch_2026-10-11.json").read_bytes())
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


def read_only(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)


def schema_of(conn) -> list[tuple]:
    """sqlite_master as normalised SQL: comments and runs of white space dropped."""
    found = []
    for kind, name, table, sql in conn.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type, name"):
        sql = re.sub(r"\s+", " ", re.sub(r"--[^\n]*", "", sql)).strip()
        found.append((kind, name, table, sql))
    return found


def version1_schema() -> str:
    """The schema as Phase 67 wrote it, read out of git at the tag before this phase."""
    return subprocess.run(["git", "show", "before-phase-73:data_access/schema.sql"], cwd=PROJECT,
                          capture_output=True, check=True).stdout.decode("utf-8")


def kind_of(record: dict) -> str:
    """What a cached record says about its price, read here independently of the code under test."""
    if record.get("price_overview"):
        return "priced"
    return "free" if record.get("is_free") is True else "unavailable"


stored = steam_web.stored_detail_ids(CACHE)
moments = steam_web.details_fetched_at(CACHE)
print(f"   ({len(stored)} cached Steam records copied in)")

print("=== 1. the upgrade, on a copy of the real library ===")
try:
    have = test_sandbox._version(DATABASE)
    if have != 1:
        # The user's own start has upgraded the real database already: a version-1 database is
        # made from it the way Phase 67 made one -- the old schema read out of git, the same rows.
        print(f"         (the real library is at version {have} already: a version-1 copy is built from it)")
        source = library_db.LibraryStore(DATABASE)
        records, entries = source.export_records(), source.load_catalog()
        source.close()
        DATABASE.unlink()
        conn = library_db.connect(DATABASE)
        with library_db.transaction(conn):
            conn.executescript(version1_schema())
            conn.execute("INSERT INTO meta (id, schema_version, created_at) VALUES (1, 1, ?)",
                         (datetime.now().astimezone().isoformat(timespec="seconds"),))
            conn.execute("PRAGMA user_version = 1")
        library_db.load(conn, records, entries, header={}, steam_records={}, steam_summary={}, search_names={})
        conn.close()
    check("the copy starts at version 1", test_sandbox._version(DATABASE) == 1)
    before_print = library_db.file_fingerprint(DATABASE)
    v1 = library_db.LibraryStore(DATABASE)
    records_before, entries_before = v1.export_records(), [e.to_dict() for e in v1.load_catalog()]
    v1.close()
    snapshots_before = len(backups.list_snapshots())
    lines.clear()

    store = migration.open_library()
    newest = backups.list_snapshots()[0]
    check("a snapshot is taken first, holding the library as it was",
          len(backups.list_snapshots()) == snapshots_before + 1
          and library_db.file_fingerprint(newest.path / rules.LIBRARY_DB_FILE) == before_print)
    # Since Phase 75 the newest version is 3, and a version-1 file goes through both scripts.
    check(f"the database is at version {library_db.SCHEMA_VERSION}: the store, meta and PRAGMA user_version agree",
          store.version == library_db.SCHEMA_VERSION == library_db.schema_version(store._conn)
          == store._conn.execute("SELECT schema_version FROM meta").fetchone()[0])
    fresh = sqlite3.connect(":memory:", autocommit=True)
    library_db.create(fresh)
    check("a fresh database and the upgraded one have the same schema (normalised sqlite_master)",
          schema_of(fresh) == schema_of(store._conn),
          [row[:2] for row in schema_of(fresh) if row not in schema_of(store._conn)][:3])
    v1_conn = sqlite3.connect(":memory:", autocommit=True)
    v1_conn.executescript(version1_schema())
    added = [row[:2] for row in schema_of(store._conn) if row not in schema_of(v1_conn)]
    removed = [row[:2] for row in schema_of(v1_conn) if row not in schema_of(store._conn)]
    # Version 7 (Phase 93) adds a column to session and version 8 (Phase 101) two to game, so their text is
    # both "added" and "removed": the changes that are not new objects, and additions all the same.
    check(f"additive only -- expand before contract: {len(added)} objects added, none removed or changed",
          sorted(removed) == [("table", "game"), ("table", "session")] and sorted(added) == sorted([
              ("table", "session"),  # version 7 (Phase 93): a column added
              ("table", "game"), ("table", "price_target"), ("table", "price_alert"),  # version 8 (Phase 101)
              ("table", "rating"),
              ("index", "purchase_by_game"), ("table", "price_snapshot"), ("table", "purchase"),
              ("view", "v_game_money"), ("view", "v_price_latest"), ("view", "v_price_range"),
              # version 3 (Phase 75): Steam's own playtime
              ("index", "steam_playtime_by_app"), ("table", "steam_account"), ("table", "steam_read"),
              ("table", "steam_playtime"), ("view", "v_steam_time_latest"), ("view", "v_steam_time_mine"),
              # version 5 (Phase 83): the reports' view
              ("view", "v_hours"),
              # version 6 (Phase 86): the wishlist
              ("table", "wishlist_read"), ("table", "wishlist"), ("view", "v_wishlist_now")]),
          (added, removed))
    check("the library itself is as it was: every record and every catalogue entry",
          store.export_records() == records_before and [e.to_dict() for e in store.load_catalog()] == entries_before)
    check("and the log says so", any(f"upgraded from version 1 to {library_db.SCHEMA_VERSION}" in line
                                     for line in lines)
          and any(f"is at version {library_db.SCHEMA_VERSION} now (snapshot" in line for line in lines))

    print("\n=== 2. the series, seeded from the cached records ===")
    rows = list(store._conn.execute(
        "SELECT appid, observed_at, kind, currency, initial_cents, final_cents, discount_percent FROM price_snapshot"))
    by_app = {}
    for row in rows:
        by_app.setdefault(row[0], []).append(row)
    expected = {int(a): kind_of(steam_web.load_details(CACHE, a)) for a in stored}
    counts = {k: sum(1 for v in expected.values() if v == k) for k in ("priced", "free", "unavailable")}
    print(f"         (the cache holds {counts['priced']} priced, {counts['free']} free, "
          f"{counts['unavailable']} with nothing on sale)")
    check(f"one observation per cached record ({len(stored)})",
          len(rows) == len(stored) and all(len(v) == 1 for v in by_app.values()) and set(by_app) == set(expected))
    check("each dated by the moment its record was fetched",
          all(by_app[int(a)][0][1] == moments[a] for a in stored))
    check("each of the kind its record says", all(by_app[a][0][2] == k for a, k in expected.items()))
    check("a priced one carries the record's price, exactly",
          all(by_app[int(a)][0][3:] == (p["currency"], p["initial"], p["final"], p["discount_percent"])
              for a in stored for p in [steam_web.load_details(CACHE, a).get("price_overview")] if p))
    check("the log names the seeding", any("seeded with %d observation" % len(stored) in line for line in lines))
    print_before = library_db.fingerprint(store._conn)
    again = steam_projection.refresh(store)
    check("the projection run twice changes nothing (an idempotent insert)",
          again.observed == 0 and library_db.fingerprint(store._conn) == print_before)
    store.close()
except Exception as exc:
    unreached("1-2", exc)

print("\n=== 3. a refused upgrade leaves the file as it was ===")
try:
    refused_dir = SANDBOX / "refused"
    refused_dir.mkdir()
    shutil.copyfile(newest.path / rules.LIBRARY_DB_FILE, refused_dir / "v1.db")
    target = refused_dir / "v1.db"
    print_v1 = library_db.file_fingerprint(target)
    broken = refused_dir / "002_broken.sql"
    broken.write_text("CREATE TABLE half_done (x INTEGER) STRICT;\nCREATE TABLE game (x INTEGER);\n", encoding="utf-8")
    real_scripts = library_db.upgrade_scripts
    # The real scripts with 2 broken: since Phase 75 a version-1 file needs 3 as well, and without
    # it the upgrade would be refused for the missing script before the broken one ever ran.
    for name, scripts in (("a script that fails half way", {**real_scripts(), 2: broken}),
                          ("a script that is missing", {})):
        library_db.upgrade_scripts = lambda scripts=scripts: scripts
        try:
            v1 = library_db.LibraryStore(target)
            try:
                v1.upgrade()
                outcome = "upgraded"
            except Exception as exc:  # noqa: BLE001
                outcome = type(exc).__name__
            check(f"{name}: refused, the store still at version 1", outcome != "upgraded" and v1.version == 1, outcome)
            v1.close()
            check("and the file holds exactly what it held", library_db.file_fingerprint(target) == print_v1)
        finally:
            library_db.upgrade_scripts = real_scripts
    # The launcher on a database whose upgrade is refused: it opens, on version 1, and says why.
    shutil.copyfile(target, DATABASE)
    library_db.upgrade_scripts = lambda: {**real_scripts(), 2: broken}
    lines.clear()
    try:
        window = ui_window.MainWindow()
        window.show()
        settle(1.0)
        check("the launcher still opens, on version 1", isinstance(window.overrides, library_db.LibraryStore)
              and window.overrides.version == 1 and len(window.views) > 0)
        check("the reason is in the log", any("stays at version 1" in line and "refused" in line for line in lines))
        check("a library at version 1 has no prices due, and asks nothing",
              prices.due(window.overrides, True) == [] and window.overrides.prices_due(7) is None)
        window.close()
        settle(0.3)
    finally:
        library_db.upgrade_scripts = real_scripts
    window.overrides.close()
    check("the file is still version 1 afterwards", test_sandbox._version(DATABASE) == 1
          and library_db.file_fingerprint(DATABASE) == print_v1)
    store = migration.open_library()  # and with the scripts back, the next start upgrades it
    check("the next start, scripts in place, upgrades it", store.version == library_db.SCHEMA_VERSION)
    store.close()
except Exception as exc:
    unreached("3", exc)

print("\n=== 4. the tables refuse what they declare ===")
try:
    scratch = sqlite3.connect(":memory:", autocommit=True)
    scratch.execute("PRAGMA foreign_keys = ON")
    library_db.create(scratch)
    scratch.execute("INSERT INTO steam_app (appid, has_record) VALUES (550, 1)")
    scratch.execute("INSERT INTO game (identity_key, name_origin) VALUES ('c:\\games\\plain', 'scan')")
    good = "2026-10-11T14:41:41+00:00"

    def refused(sql, args=()):
        try:
            scratch.execute(sql, args)
            return False
        except sqlite3.Error:
            return True

    price = "INSERT INTO price_snapshot VALUES (?, ?, ?, ?, ?, ?, ?)"
    check("a priced observation with all four figures is taken", not refused(price, (550, good, "priced", "EUR", 969, 969, 0)))
    check("so are 'free' and 'unavailable' with none",
          not refused(price, (550, "2026-10-12T00:00:00+00:00", "free", None, None, None, None))
          and not refused(price, (550, "2026-10-13T00:00:00+00:00", "unavailable", None, None, None, None)))
    for what, args in (
            ("a priced one missing its currency", (550, "2026-10-14T00:00:00+00:00", "priced", None, 1, 1, 0)),
            ("a free one carrying a price", (550, "2026-10-15T00:00:00+00:00", "free", "EUR", 1, 1, 0)),
            ("a kind not in the list", (550, "2026-10-16T00:00:00+00:00", "sale", None, None, None, None)),
            ("a moment not in UTC", (550, "2026-10-17T00:00:00+03:00", "free", None, None, None, None)),
            ("a moment that is not one", (550, "next week", "free", None, None, None, None)),
            ("a discount over 100", (550, "2026-10-18T00:00:00+00:00", "priced", "EUR", 1, 1, 120)),
            ("a negative price", (550, "2026-10-19T00:00:00+00:00", "priced", "EUR", -1, 1, 0)),
            ("the same app and moment twice (the primary key)", (550, good, "free", None, None, None, None)),
            ("an app the database does not know (the foreign key)", (999, good, "free", None, None, None, None))):
        check(f"price_snapshot refuses {what}", refused(price, args))
    purchase = "INSERT INTO purchase (game_id, paid_cents, currency, store, bought_on, recorded_at) VALUES (?, ?, ?, ?, ?, ?)"
    check("a purchase with an unknown date is taken, EUR by default",
          not refused("INSERT INTO purchase (game_id, paid_cents, store, recorded_at) VALUES (1, 0, 'gift', ?)", (good,))
          and scratch.execute("SELECT currency FROM purchase").fetchone()[0] == "EUR")
    for what, args in (
            ("a negative amount", (1, -1, "EUR", "Steam", None, good)),
            ("an empty store", (1, 100, "EUR", "  ", None, good)),
            ("a date that is not one", (1, 100, "EUR", "Steam", "2026-13-01", good)),
            ("a currency in lower case", (1, 100, "eur", "Steam", None, good)),
            ("a game the database does not know", (999, 100, "EUR", "Steam", None, good))):
        check(f"purchase refuses {what}", refused(purchase, args))
except Exception as exc:
    unreached("4", exc)

print("\n=== 5. append-only: nothing in the program updates or deletes an observation ===")
try:
    offenders = []
    for path in sorted(PROJECT.rglob("*.py")) + sorted(PROJECT.rglob("*.sql")):
        rel = path.relative_to(PROJECT)
        if rel.parts[0] in (".venv", ".claude", "tests", "build", "dist", "data") or "__pycache__" in rel.parts:
            continue
        text = path.read_text(encoding="utf-8-sig")
        for match in re.finditer(r"(UPDATE|DELETE\s+FROM|REPLACE\s+INTO|INSERT\s+OR\s+REPLACE\s+INTO)\s+price_snapshot",
                                 text, flags=re.IGNORECASE):
            offenders.append(f"{rel}: {match.group(0)}")
    check("no UPDATE, DELETE or REPLACE of price_snapshot anywhere in the program", not offenders, offenders)
    names = [n for n in dir(library_db.LibraryStore) if not n.startswith("__")]
    # keeps_observed (Phase 93) is about sessions seen in the process list, not price observations.
    # The price alerts' target and log (Phase 101) are a setting and a log of their own, not observations.
    priced = [n for n in names if ("observ" in n or "price" in n) and n != "keeps_observed"
              and "target" not in n and "alert" not in n]
    check("the store offers only to add observations, and to read them",
          priced == ["add_observations", "keeps_prices", "observation_keys", "prices_due"], priced)
except Exception as exc:
    unreached("5", exc)

print("\n=== 6. the store's answer, as it came on 11 October ===")
try:
    hint = {"730": steam_web.load_details(CACHE, "730").get("is_free") is True, "550": False, "1": False}
    at = "2026-10-11T14:41:41+00:00"
    parsed = {a: steam_web.price_observation(a, FIXTURE.get(a), at, free_hint=hint[a]) for a in ("730", "550", "1")}
    check("one request answered for three apps: a dict keyed by appid", sorted(FIXTURE) == ["1", "550", "730"])
    check("730 -- data an empty list, a free game by its record: 'free'",
          FIXTURE["730"]["data"] == [] and parsed["730"]["kind"] == "free" and parsed["730"]["currency"] is None)
    check("the same shape without the record's word would read 'unavailable' -- the filter cannot tell",
          steam_web.price_observation("730", FIXTURE["730"], at)["kind"] == "unavailable")
    check("550 -- a price: EUR, 969, 969, 0, as given",
          (parsed["550"]["kind"], parsed["550"]["currency"], parsed["550"]["initial_cents"],
           parsed["550"]["final_cents"], parsed["550"]["discount_percent"]) == ("priced", "EUR", 969, 969, 0))
    check("1 -- success false: 'unavailable', an observation all the same",
          FIXTURE["1"] == {"success": False} and parsed["1"]["kind"] == "unavailable")
    single = {"550": FIXTURE["550"]}  # one app asked for: the same shape, one key
    check("an answer for one app reads the same", steam_web.price_observation("550", single["550"], at) == parsed["550"])
    for what, answer in (("a price missing its final figure", {"success": True, "data": {"price_overview": {
            "currency": "EUR", "initial": 1, "discount_percent": 0}}}),
            ("a figure that is not a whole number", {"success": True, "data": {"price_overview": {
                "currency": "EUR", "initial": "9,69", "final": 969, "discount_percent": 0}}}),
            ("success that is not true or false", {"success": "yes"}),
            ("data that is neither a record nor an empty list", {"success": True, "data": "nothing"}),
            ("no answer for the app at all", None)):
        check(f"no observation from {what}", steam_web.price_observation("550", answer, at) is None)
except Exception as exc:
    unreached("6", exc)

print("\n=== 7. asking the store, on the scan thread: what is written, and what is not ===")
try:
    real_get = steam_web._get
    asked: list[str] = []
    handoff = Path(steam_web.price_handoff_path(CACHE))

    def answers_with(body):
        def fake(url):
            asked.append(url)
            return body(url) if callable(body) else body
        return fake

    def store_like(url):
        apps = url.split("appids=")[1].split("&")[0].split(",")
        payload = {}
        for appid in apps:
            if appid == "730":
                payload[appid] = {"success": True, "data": []}
            elif appid == "1":
                payload[appid] = {"success": False}
            elif appid == "missing":
                continue
            else:
                payload[appid] = {"success": True, "data": {"price_overview": {
                    "currency": "EUR", "initial": 1000, "final": 500, "discount_percent": 50}}}
        return json.dumps(payload).encode()

    steam_web.write_price_handoff(CACHE, [])
    for what, body in (("no answer", None), ("a body that is not JSON", b"<html>busy</html>"),
                       ("JSON that is not a list of apps", b"[1, 2]")):
        steam_web._get = answers_with(body)
        try:
            written = steam_web.observe_prices([550, 730], CACHE)
        finally:
            steam_web._get = real_get
        check(f"a failed request -- {what} -- is no observation: nothing written",
              written == 0 and steam_web.price_handoff(CACHE) == [])
    asked.clear()
    steam_web._get = answers_with(store_like)
    try:
        before = datetime.now(timezone.utc).replace(microsecond=0)
        written = steam_web.observe_prices([550, 730, 1], CACHE)
    finally:
        steam_web._get = real_get
    rows = steam_web.price_handoff(CACHE)
    check("three apps, one request, every URL with the filter and the country",
          len(asked) == 1 and "filters=price_overview" in asked[0] and asked[0].endswith("&cc=RO")
          and "appids=550,730,1" in asked[0], asked)
    check("three observations written to the hand-off, of the three kinds",
          written == 3 and sorted(r["kind"] for r in rows) == ["free", "priced", "unavailable"], rows)
    check("all at the moment of the fetch, in UTC",
          len({r["observed_at"] for r in rows}) == 1
          and datetime.fromisoformat(rows[0]["observed_at"]) >= before and rows[0]["observed_at"].endswith("+00:00"))
    steam_web.write_price_handoff(CACHE, [])
    steam_web._get = answers_with(lambda url: json.dumps({"550": FIXTURE["550"]}).encode())
    try:
        steam_web.observe_prices([550, 4538140], CACHE)
    finally:
        steam_web._get = real_get
    check("an app missing from the answer is skipped, and costs the other nothing",
          [r["appid"] for r in steam_web.price_handoff(CACHE)] == [550])
    steam_web.write_price_handoff(CACHE, [])
    asked.clear()
    real_batch = rules.PRICE_BATCH_SIZE
    rules.PRICE_BATCH_SIZE = 2
    steam_web._get = answers_with(store_like)
    try:
        # More pairs than one scan may ask for, whatever the allowance (2 at first, 8 since Phase 75).
        steam_web.observe_prices([10_000 + i for i in range(2 * rules.PRICE_REQUESTS_PER_SCAN + 3)], CACHE)
    finally:
        steam_web._get = real_get
        rules.PRICE_BATCH_SIZE = real_batch
    check(f"never more than {rules.PRICE_REQUESTS_PER_SCAN} requests in one scan; the rest wait",
          len(asked) == rules.PRICE_REQUESTS_PER_SCAN
          and len(steam_web.price_handoff(CACHE)) == 2 * rules.PRICE_REQUESTS_PER_SCAN, len(asked))
    steam_web.write_price_handoff(CACHE, [])
except Exception as exc:
    unreached("7", exc)

print("\n=== 8. landing them, on the GUI thread ===")
try:
    store = migration.open_library()
    stamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    rows = [{"appid": 550, "observed_at": stamp, "kind": "priced", "currency": "EUR",
             "initial_cents": 969, "final_cents": 969, "discount_percent": 0},
            {"appid": 730, "observed_at": stamp, "kind": "free", "currency": None,
             "initial_cents": None, "final_cents": None, "discount_percent": None},
            {"appid": 424242, "observed_at": stamp, "kind": "unavailable", "currency": None,
             "initial_cents": None, "final_cents": None, "discount_percent": None}]  # no such app here
    steam_web.write_price_handoff(CACHE, rows)
    done = prices.land(store, CACHE)
    left = steam_web.price_handoff(CACHE)
    check("the observations land in the series", done.landed == 2
          and store._conn.execute("SELECT COUNT(*) FROM price_snapshot WHERE observed_at = ?", (stamp,)).fetchone()[0] == 2)
    check("one that could not land stays in the hand-off for the next scan",
          done.kept == 1 and [r["appid"] for r in left] == [424242], left)
    print_before = library_db.fingerprint(store._conn)
    steam_web.write_price_handoff(CACHE, rows[:2])
    again = prices.land(store, CACHE)
    check("landing the same observations again changes nothing, and empties the hand-off",
          again.landed == 2 and library_db.fingerprint(store._conn) == print_before
          and steam_web.price_handoff(CACHE) == [])
    latest = dict(((a, k) for a, k in store._conn.execute("SELECT appid, kind FROM v_price_latest")))
    check("v_price_latest answers with the newest observation", latest.get(550) == "priced"
          and store._conn.execute("SELECT final_cents, observed_at FROM v_price_latest WHERE appid = 550").fetchone()
          == (969, stamp))
    span = store._conn.execute("SELECT observations, lowest_cents, highest_cents, last_observed "
                               "FROM v_price_range WHERE appid = 550").fetchone()
    cached = steam_web.load_details(CACHE, "550")["price_overview"]["final"]
    check("v_price_range sees both observations, lowest and highest",
          span == (2, min(969, cached), max(969, cached), stamp), span)

    print("\n=== 9. which apps are due ===")
    store.close()
    shutil.copyfile(DATABASE, SANDBOX / "nine.db")  # its own copy: the window below needs some apps due
    store = library_db.LibraryStore(SANDBOX / "nine.db")
    every = [a for (a,) in store._conn.execute("SELECT appid FROM steam_app WHERE has_record = 1")]
    now = datetime.now(timezone.utc)
    due_now = store.prices_due(rules.PRICE_REFRESH_DAYS, now)
    newest = dict(store._conn.execute("SELECT appid, MAX(observed_at) FROM price_snapshot GROUP BY appid"))
    week_ago = (now - timedelta(days=rules.PRICE_REFRESH_DAYS)).isoformat(timespec="seconds")
    check("due: every app whose newest observation is a week old, or that has none -- installed or not",
          sorted(due_now) == sorted(a for a in every if newest.get(a) is None or newest[a] < week_ago))
    check("the oldest first", [newest.get(a) or "" for a in due_now] == sorted(newest.get(a) or "" for a in due_now))
    fresh_rows = [{"appid": a, "observed_at": now.replace(microsecond=0).isoformat(), "kind": "unavailable",
                   "currency": None, "initial_cents": None, "final_cents": None, "discount_percent": None}
                  for a in every]
    store.add_observations(fresh_rows)
    check("nothing due once every app was seen today", store.prices_due(rules.PRICE_REFRESH_DAYS) == [])
    check("a week later, all of them", sorted(store.prices_due(rules.PRICE_REFRESH_DAYS, now + timedelta(days=8)))
          == sorted(every))
    check("the network off: nothing is due, whatever the database says",
          prices.due(store, False) == [] and prices.due(store, True) == [])
    blank = library_db.LibraryStore(SANDBOX / "blank.db")
    with library_db.transaction(blank._conn):
        for appid in (550, 730):
            library_db.ensure_steam_app(blank._conn, appid)
        blank._conn.execute("UPDATE steam_app SET has_record = 1")
    check("a new database: everything is due", sorted(blank.prices_due(7)) == [550, 730])
    blank.close()
    check("the JSON store keeps no prices: nothing due",
          prices.due(catalog_io.Overrides(path=SANDBOX / "json.json"), True) == [])
    store.close()
except Exception as exc:
    unreached("8-9", exc)

print("\n=== 10. the window's scan observes them, the GUI thread lands them ===")
try:
    # The network on, for this window only -- every request still stops at the stub above, and the
    # store's answer for the price request is handed to steam_web._get.
    config = json.loads((SANDBOX / "config.json").read_text(encoding="utf-8"))
    config["allow_network"] = True
    (SANDBOX / "config.json").write_text(json.dumps(config), encoding="utf-8")
    real_get = steam_web._get
    price_requests: list[str] = []

    def store_answers(url):
        if "filters=price_overview" in url:
            price_requests.append(url)
            apps = url.split("appids=")[1].split("&")[0].split(",")
            return json.dumps({a: {"success": True, "data": {"price_overview": {
                "currency": "EUR", "initial": 2000, "final": 1500, "discount_percent": 25}}} for a in apps}).encode()
        return None  # art, records: no answer, as with the network down

    writers: list[int] = []
    real_add = library_db.LibraryStore.add_observations

    def watched(self, rows):
        writers.append(threading.get_ident())
        return real_add(self, rows)

    steam_web._get = store_answers
    library_db.LibraryStore.add_observations = watched
    try:
        window = ui_window.MainWindow()
        window.show()
        settle(0.8)
        due = prices.due(window.overrides, True)
        lines.clear()
        window.start_scan(background=True)
        deadline = time.monotonic() + 180
        while window.worker is not None and window.worker.isRunning() and time.monotonic() < deadline:
            settle(0.2)
        settle(0.5)
    finally:
        steam_web._get = real_get
        library_db.LibraryStore.add_observations = real_add
    landed = window.overrides._conn.execute("SELECT COUNT(*) FROM price_snapshot WHERE final_cents = 1500").fetchone()[0]
    expected_requests = min(rules.PRICE_REQUESTS_PER_SCAN, -(-len(due) // rules.PRICE_BATCH_SIZE))
    check(f"the scan asked the store for the {len(due)} app(s) due, in {expected_requests} request(s)",
          due and len(price_requests) == expected_requests, (len(due), len(price_requests)))
    check("and every observation landed in the series", landed == min(len(due), rules.PRICE_REQUESTS_PER_SCAN
                                                                      * rules.PRICE_BATCH_SIZE), landed)
    check("written by the GUI thread -- the one writer", writers and set(writers) == {threading.main_thread().ident})
    check("the log says how many", any("observation(s) recorded for the window" in line for line in lines)
          and any("observation(s) landed in the library" in line for line in lines))
    check("nothing is due any more", prices.due(window.overrides, True) == [])
    check("the hand-off is empty", steam_web.price_handoff(CACHE) == [])
    window.close()
    settle(0.3)
    window.overrides.close()
    config["allow_network"] = False
    (SANDBOX / "config.json").write_text(json.dumps(config), encoding="utf-8")
    price_requests.clear()
    steam_web._get = store_answers
    try:
        window = ui_window.MainWindow()
        store = window.overrides
        rows_before = store._conn.execute("SELECT COUNT(*) FROM price_snapshot").fetchone()[0]
        window.show()
        settle(0.5)
        window.start_scan(background=True)
        deadline = time.monotonic() + 180
        while window.worker is not None and window.worker.isRunning() and time.monotonic() < deadline:
            settle(0.2)
        settle(0.5)
    finally:
        steam_web._get = real_get
    check("allow_network off: no price request at all, and no new row",
          price_requests == [] and store._conn.execute("SELECT COUNT(*) FROM price_snapshot").fetchone()[0] == rows_before)
    window.close()
    settle(0.3)
    window.overrides.close()
except Exception as exc:
    unreached("10", exc)

print("\n=== 11. scanner.py observes no prices ===")
try:
    source = (PROJECT / "scanner.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)} | {
        alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    named = {alias.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) for alias in node.names}
    check("it imports nothing that observes prices", "prices" not in named and "logic.prices" not in imported
          and "observe_prices" not in source)
    check("and its docstring says so", "observes no prices" in (ast.get_docstring(tree) or ""))
    check("and no price request ever reached the network: the one made is the fixture",
          not any("filters=price_overview" in url for url in attempts), attempts[:3])
except Exception as exc:
    unreached("11", exc)

print("\n=== 12. the real library is exactly as it was found ===")
changed = box.finish()
check("config.json and the library database are unchanged", not changed, changed)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
