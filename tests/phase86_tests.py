"""Phase 86: the Steam wishlist, step 1 of 2 -- read, kept, priced, set against what is played.

  1. the parser on the real answers of 15 October (the public list, the "nothing" all three others
     gave) and on what Steam could send instead;
  2. the request: the address, a GET with nothing in it, no key -- and the account's number never
     in the log;
  3. schema version 6 on a copy of the real library: a snapshot first, the user's tables row for
     row, three objects added and nothing changed, fresh = upgraded, 1 -> 6 through every script;
  4. the read and the landing on made-up accounts: only the accounts marked mine are asked, none
     with the network off, once a day; the hand-off; landing twice is one set of rows; last_seen
     moves; a game gone gets removed_at and is never deleted; one that comes back clears it; an
     answer with nothing in it takes nothing off; an older answer is not applied; a refused one
     stays for the next scan;
  5. v_wishlist_now on made-up series: one row for a game on two lists; "at its lowest" needs two
     prices and a higher one seen; removed from one list or from all; the hours already played;
     the accounts not marked mine left out;
  6. the fit line on made-up profiles (rarity-weighted since Phase 89): cosines worked out by hand,
     a common genre counting for little, no record / no genre / nothing played said in words, Free
     To Play never named;
  7. prices and records: a wishlist game's price asked for daily, another weekly; the records of
     the wishlist after the played ones;
  8. Settings: each account marked mine says what its wishlist read found;
  9. the window's scan, the network on: the lists read on the scan thread, landed on the GUI
     thread, the real answers in the copy; the next scan asks nothing;
 10. report 6's two wishlist lines, on the copy;
 11. nothing writes to Steam; the network only in web/; the documents; the layers;
 12. the real library exactly as it was found.

On a throwaway copy of the data; every request stops at a stand-in.
"""
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import sources  # the build log's notes (Phase 91)
import test_sandbox

box = test_sandbox.start(migrate=False)  # the library as it is: section 3 upgrades it itself
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
from PySide6.QtWidgets import QApplication, QLabel

app = QApplication([])

from data_access import library_db
from logic import migration, prices
from presentation import ui_settings, ui_window
from shared import paths, rules
from web import steam_web

try:
    from logic import reports as logic_reports
    from logic import wishlist
    from web import steam_wishlist
except ImportError:  # the code before this phase has neither; the sections that need them say so
    wishlist = steam_wishlist = logic_reports = None

FIXTURES = PROJECT / "tests" / "fixtures"
PUBLIC = (FIXTURES / "steam_wishlist_public_2026-10-15.json").read_bytes()
NOTHING = (FIXTURES / "steam_wishlist_nothing_2026-10-15.json").read_bytes()
CACHE = str(paths.cache_dir())
DATABASE = SANDBOX / rules.LIBRARY_DB_FILE
BASE = 76561197960265728  # an individual account's SteamID64 less its account id, written out here
WORK = Path(tempfile.mkdtemp(prefix="phase86_"))
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


def schema_of(conn) -> list[tuple]:
    """sqlite_master as normalised SQL: comments and runs of white space dropped."""
    found = []
    for kind, name, table, sql in conn.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type, name"):
        found.append((kind, name, table, re.sub(r"\s+", " ", re.sub(r"--[^\n]*", "", sql)).strip()))
    return found


def schema_at(tag: str) -> str:
    return subprocess.run(["git", "show", f"{tag}:data_access/schema.sql"], cwd=PROJECT,
                          capture_output=True, check=True).stdout.decode("utf-8")


def count(conn, table: str) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def utc(**ago) -> str:
    return (datetime.now(timezone.utc) - timedelta(**ago)).isoformat(timespec="seconds")


def at(day: int, hour: int = 12) -> str:
    return datetime(2026, 10, day, hour, tzinfo=timezone.utc).isoformat(timespec="seconds")


def made_store(name: str):
    """A library of its own, made up here: four accounts -- two mine, one not mine, one not decided."""
    store = library_db.LibraryStore(WORK / f"{name}.db")
    c = store._conn
    for account_id, persona, mine in ((1001, "Alpha", 1), (1002, "Bravo", 1), (1003, "Charlie", 0), (1004, "Delta", None)):
        c.execute("INSERT INTO steam_account (account_id, steam_id64, persona, is_mine, first_seen, last_seen) "
                  "VALUES (?, ?, ?, ?, ?, ?)", (account_id, account_id + BASE, persona, mine, at(1), at(1)))
    for gid, gname in ((1, "Action"), (2, "Strategy"), (3, "Puzzle"), (37, "Free To Play")):
        c.execute("INSERT INTO genre (id, name) VALUES (?, ?)", (gid, gname))
    return store


def app_row(store, appid: int, name: str, genres=(), record=True):
    c = store._conn
    c.execute("INSERT INTO steam_app (appid, has_record, name, app_type) VALUES (?, ?, ?, ?) "
              "ON CONFLICT (appid) DO UPDATE SET has_record = excluded.has_record, name = excluded.name, "
              "app_type = excluded.app_type", (appid, 1 if record else 0, name if record else None,
                                                "game" if record else None))
    for gid in genres:
        c.execute("INSERT INTO steam_app_genre (appid, genre_id) VALUES (?, ?)", (appid, gid))


def price(store, appid: int, when: str, final: int, initial: int | None = None):
    initial = final if initial is None else initial
    discount = round(100 * (initial - final) / initial) if initial else 0
    landed, refused = store.add_observations([{"appid": appid, "observed_at": when, "kind": "priced",
                                               "currency": "EUR", "initial_cents": initial, "final_cents": final,
                                               "discount_percent": discount}])
    assert not refused, refused


def reading(account_id: int, when: str, *appids, priority=0):
    return {"account_id": account_id, "read_at": when,
            "items": [{"appid": a, "priority": priority, "date_added": at(1, a % 20)} for a in appids]}


def now_rows(store) -> dict[int, dict]:
    return {r["appid"]: r for r in store.reports().rows("wishlist_now")}


print("=== 1. the parser, on the real answers of 15 October ===")
try:
    public = steam_wishlist.parse(PUBLIC)
    raw = json.loads(PUBLIC)["response"]["items"]
    check(f"the public list: {len(public.items)} games, every one Steam named, in its order",
          public.state == steam_wishlist.ITEMS and [i["appid"] for i in public.items] == [i["appid"] for i in raw]
          and len(public.items) == 16, public.detail)
    first = public.items[0]
    check("its first: appid, priority, and when it was added, as UTC text",
          first == {"appid": raw[0]["appid"], "priority": raw[0]["priority"],
                    "date_added": datetime.fromtimestamp(raw[0]["date_added"], timezone.utc).isoformat(timespec="seconds")},
          first)
    check("what the three other accounts answered is nothing to read -- a private list, or an empty one",
          steam_wishlist.parse(NOTHING).state == steam_wishlist.NOTHING and NOTHING == b'{"response":{}}')
    check("an empty items list is nothing to read too",
          steam_wishlist.parse(b'{"response":{"items":[]}}').state == steam_wishlist.NOTHING)
    failing = [b"", b"not json", b"[]", b'{"response": []}', b'{"error": 1}', b'{"response":{"items":5}}',
               b'{"response":{"items":[{"appid":"x"},{"priority":1},7,{"appid":true}]}}', None]
    check("no answer, not JSON, no response object, items not a list, no item readable: no reading at all",
          all(steam_wishlist.parse(b).state == steam_wishlist.FAILED for b in failing),
          [steam_wishlist.parse(b).state for b in failing])
    mixed = steam_wishlist.parse(json.dumps({"response": {"items": [
        {"appid": 10, "priority": 2, "date_added": 1760000000}, {"appid": -3}, {"appid": 10, "priority": 9},
        {"appid": 20, "priority": -1, "date_added": 0}, {"appid": 30}]}}))
    check("a list with an unreadable item: the rest read, a repeated game once, a bad priority or date left empty",
          mixed.state == steam_wishlist.ITEMS and [i["appid"] for i in mixed.items] == [10, 20, 30]
          and mixed.items[1] == {"appid": 20, "priority": None, "date_added": None}, mixed.items)
except Exception as exc:
    unreached("1", exc)

print("\n=== 2. the request ===")
try:
    asked: list = []

    class Answer:
        def __init__(self, body):
            self.body, self.status = body, 200

        def read(self):
            return self.body

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def stand_in(request, *args, timeout=None, **kwargs):
        asked.append((request, timeout))
        return Answer(PUBLIC)

    urllib.request.urlopen = stand_in
    lines.clear()
    try:
        answer = steam_wishlist.fetch(1001 + BASE)
    finally:
        urllib.request.urlopen = no_network
    request, timeout = asked[0] if asked else (None, None)
    check("one request, to the wishlist service on api.steampowered.com, naming the account",
          len(asked) == 1 and request.full_url == rules.STEAM_WISHLIST_URL.format(steamid=1001 + BASE)
          and request.full_url.startswith("https://api.steampowered.com/IWishlistService/GetWishlist/v1/?steamid="),
          request.full_url if request else None)
    check("a GET with nothing sent, a plain User-Agent, no key and no account header",
          request.get_method() == "GET" and request.data is None
          and request.get_header("User-agent") == rules.STEAM_USER_AGENT
          and "key=" not in request.full_url and not request.has_header("Authorization"))
    check("with the store's timeout", timeout == rules.STEAM_WEB_TIMEOUT_SECONDS, timeout)
    check("and its answer read", answer.state == steam_wishlist.ITEMS and len(answer.items) == 16)

    def refused(request, *args, **kwargs):
        raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", {}, None)

    urllib.request.urlopen = refused
    try:
        failed_answer = steam_wishlist.fetch(1002 + BASE)
    finally:
        urllib.request.urlopen = no_network
    check("an HTTP error is no reading", failed_answer.state == steam_wishlist.FAILED)
    check("the account's number is in no line of the log", not any(str(n + BASE) in line for line in lines
                                                                    for n in (1001, 1002)), lines[-3:])
except Exception as exc:
    unreached("2", exc)

print("\n=== 3. schema version 6 on a copy of the real library ===")
try:
    raw = sqlite3.connect(DATABASE, isolation_level=None)
    if library_db.schema_version(raw) >= 6:  # the user's own start already upgraded it: undo 6 in the copy
        test_sandbox.undo_upgrades(raw, 5)
    check("the copy starts at version 5", library_db.schema_version(raw) == 5, library_db.schema_version(raw))
    tables = [r[0] for r in raw.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name != 'meta'")]
    before_rows = {t: sorted(map(repr, raw.execute(f"SELECT * FROM {t}"))) for t in tables}
    before_meta = raw.execute("SELECT id, created_at, migrated_from, migrated_at FROM meta").fetchall()
    before_schema = schema_of(raw)
    raw.close()
    snapshots_before = {p.name for p in (SANDBOX / "backups").glob("*")} if (SANDBOX / "backups").is_dir() else set()
    lines.clear()
    store = migration.open_library()
    check(f"the copy opens at the current version, {library_db.SCHEMA_VERSION}",
          store.version == library_db.SCHEMA_VERSION >= 6, store.version)
    store.close()
    raw = sqlite3.connect(DATABASE, isolation_level=None)
    held = []
    for folder in (SANDBOX / "backups").glob("*") if (SANDBOX / "backups").is_dir() else []:
        if folder.name not in snapshots_before and (folder / "library.db").is_file():
            snap = sqlite3.connect(f"file:{(folder / 'library.db').as_posix()}?mode=ro", uri=True)
            held.append(library_db.schema_version(snap))
            snap.close()
    check("a snapshot first, holding the library at version 5", 5 in held, held)
    # The projection runs after an upgrade (Phase 73's seeding) and may refresh a Steam record the
    # cache has fetched since (suite 76's lesson): those tables keep every row's key; the rest exactly.
    projected = {"steam_app", "genre", "steam_app_genre", "category", "steam_app_category", "company",
                 "steam_app_company", "price_snapshot"}
    # In the columns each table had: session gains its origin in version 7 (Phase 93).
    check("every row of the user's own tables as it was",
          all(test_sandbox.rows_in_old_columns(raw, t) == before_rows[t] for t in tables if t not in projected))
    check("the Steam apps and the price series kept every row they had",
          set(before_rows["price_snapshot"]) <= set(map(repr, raw.execute("SELECT * FROM price_snapshot")))
          and len(before_rows["steam_app"]) <= count(raw, "steam_app"))
    check("meta: only the version moved",
          raw.execute("SELECT id, created_at, migrated_from, migrated_at FROM meta").fetchall() == before_meta
          and raw.execute("SELECT schema_version FROM meta").fetchone()[0] == library_db.SCHEMA_VERSION)
    # Version 7 (Phase 93) adds a column to session, version 8 (Phase 101) two to game and three tables: the
    # upgrade from 5 goes through them too.
    later = {("table", "session"), ("table", "game"), ("table", "price_target"), ("table", "price_alert"),
             ("table", "rating")}
    added = [row[:2] for row in schema_of(raw) if row not in before_schema and row[:2] not in later]
    gone = [row[:2] for row in before_schema if row not in schema_of(raw) and row[:2] not in later]
    check("additive only: the two tables and the view added, nothing removed or changed",
          not gone and sorted(added) == [("table", "wishlist"), ("table", "wishlist_read"), ("view", "v_wishlist_now")],
          (added, gone))
    check("both new tables STRICT, and empty until a scan reads a list",
          all(raw.execute("SELECT strict FROM pragma_table_list WHERE name = ?", (t,)).fetchone()[0] == 1
              for t in ("wishlist", "wishlist_read")) and count(raw, "wishlist") == count(raw, "wishlist_read") == 0)
    fresh = sqlite3.connect(":memory:", autocommit=True)
    library_db.create(fresh)
    check("a fresh database and the upgraded copy have the same schema", schema_of(fresh) == schema_of(raw),
          set(schema_of(fresh)) ^ set(schema_of(raw)))
    newest = library_db.SCHEMA_VERSION
    check("the log says so", any(f"upgraded from version 5 to {newest}" in line for line in lines)
          and any(f"is at version {newest} now (snapshot" in line for line in lines))
    raw.close()
    one = sqlite3.connect(":memory:", autocommit=True)
    one.executescript(schema_at("before-phase-73"))
    one.execute("INSERT INTO meta (id, schema_version, created_at) VALUES (1, 1, '2026-10-01T00:00:00+03:00')")
    one.execute("PRAGMA user_version = 1")
    applied = library_db.upgrade(one)
    check(f"a version-1 database goes through every script, 2 to {newest}, to the schema of a fresh one",
          applied == list(range(2, newest + 1)) and schema_of(one) == schema_of(fresh), applied)
except Exception as exc:
    unreached("3", exc)

print("\n=== 4. the read and the landing, on made-up accounts ===")
try:
    store = made_store("landing")
    c = store._conn
    hand = str(WORK / "cache")
    check("the network off: no account is read", wishlist.due(store, False) == [])
    due = wishlist.due(store, True)
    check("the network on: the two accounts marked mine, never the one not mine or the one not decided",
          due == [{"account_id": 1001, "steam_id64": 1001 + BASE}, {"account_id": 1002, "steam_id64": 1002 + BASE}], due)
    answers = {1001 + BASE: steam_wishlist.Answer(steam_wishlist.ITEMS, tuple(reading(1001, "", 10, 20, 30)["items"])),
               1002 + BASE: steam_wishlist.parse(NOTHING),
               1003 + BASE: steam_wishlist.Answer(steam_wishlist.FAILED, detail="no answer")}
    asked_ids: list[int] = []
    real_fetch = steam_wishlist.fetch

    def answering(steam_id64):
        asked_ids.append(steam_id64)
        return answers[steam_id64]

    steam_wishlist.fetch = answering
    try:
        kept = wishlist.read(due + [{"account_id": 1003, "steam_id64": 1003 + BASE}], hand)
    finally:
        steam_wishlist.fetch = real_fetch
    handed = wishlist.pending(hand)
    check("read: one request per account named; the answer with no reading kept out of the hand-off",
          asked_ids == [1001 + BASE, 1002 + BASE, 1003 + BASE] and kept == 2
          and [r["account_id"] for r in handed] == [1001, 1002], (asked_ids, kept, handed))
    check("each answer with its moment, in UTC", all(re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+00:00", r["read_at"])
                                                     for r in handed))
    done = wishlist.land(store, hand)
    check("landed: two read rows, three games on Alpha's list, none on Bravo's, the hand-off gone",
          done.readings == 2 and done.added == 3 and count(c, "wishlist_read") == 2 and count(c, "wishlist") == 3
          and not os.path.exists(wishlist.handoff_path(hand)), done)
    check("Bravo's read says nothing to read", c.execute("SELECT state, items FROM wishlist_read WHERE account_id = 1002")
          .fetchall() == [("nothing", 0)])
    check("a game the library had never heard of gets a steam_app row, no record yet (the foreign key holds)",
          c.execute("SELECT has_record, name FROM steam_app WHERE appid = 30").fetchone() == (0, None))
    check("both accounts read within the day: none due", wishlist.due(store, True) == [])
    wishlist._keep(hand, handed)  # the same answers, handed over a second time
    again = wishlist.land(store, hand)
    check("landing the same answers twice: one set of rows", again.readings == 0 and count(c, "wishlist") == 3
          and count(c, "wishlist_read") == 2, again)

    # Every later read is dated after the real one just landed (16 October: fixed dates of the 16th to
    # the 18th had become older than a read made on the day, which the store rightly does not apply).
    first_read = datetime.fromisoformat(max(r["read_at"] for r in handed))

    def after(days: int, hours: int = 0) -> str:
        return (first_read + timedelta(days=days, hours=hours)).isoformat(timespec="seconds")

    later = after(1)
    store.land_wishlist(reading(1001, later, 10, 20))
    seen = dict(c.execute("SELECT appid, last_seen FROM wishlist WHERE account_id = 1001"))
    gone_row = c.execute("SELECT removed_at FROM wishlist WHERE appid = 30").fetchone()
    check("a later read: last_seen moves on the games still there", seen[10] == seen[20] == later, seen)
    check("a game no longer on the list gets removed_at, that read's moment -- and is not deleted",
          gone_row == (later,) and count(c, "wishlist") == 3)
    store.land_wishlist(reading(1002, after(1), 40))
    store.land_wishlist({"account_id": 1002, "read_at": after(2), "items": []})
    check("an answer with nothing in it takes nothing off: Bravo's game stays",
          c.execute("SELECT removed_at, last_seen FROM wishlist WHERE account_id = 1002 AND appid = 40").fetchone()
          == (None, after(1)))
    back = store.land_wishlist(reading(1001, after(3), 10, 20, 30))
    check("a game that comes back clears removed_at", back["returned"] == 1
          and c.execute("SELECT removed_at, last_seen FROM wishlist WHERE appid = 30").fetchone() == (None, after(3)))
    stale = store.land_wishlist(reading(1001, after(0, -6), 99))
    check("an answer older than the newest landed for its account is not applied",
          stale["read"] == 0 and c.execute("SELECT COUNT(*) FROM wishlist WHERE appid = 99").fetchone()[0] == 0)
    check("nothing anywhere deletes a wishlist row", not re.search(
        r"DELETE\s+FROM\s+wishlist", "\n".join(p.read_text(encoding="utf-8") for p in (PROJECT / "data_access").glob("*.py"))
        + (PROJECT / "logic" / "wishlist.py").read_text(encoding="utf-8"), re.I))
    wishlist._keep(hand, [reading(4242, at(19), 10)])  # an account the library does not know: refused
    refused_done = wishlist.land(store, hand)
    check("an answer the database refuses stays in the hand-off for the next scan",
          refused_done.kept == 1 and len(wishlist.pending(hand)) == 1, refused_done)
    wishlist._keep(hand, [])
    old_reads = [(1001, utc(hours=rules.WISHLIST_READ_HOURS + 1))]
    fresh_store = made_store("due")
    fresh_store.land_wishlist(reading(1001, old_reads[0][1], 10))
    fresh_store.land_wishlist(reading(1002, utc(hours=1), 10))
    check(f"a list read more than {rules.WISHLIST_READ_HOURS} hours ago is due again, one read an hour ago is not",
          [a["account_id"] for a in fresh_store.wishlist_due(rules.WISHLIST_READ_HOURS)] == [1001])
    fresh_store.close()
    store.close()
except Exception as exc:
    unreached("4", exc)

print("\n=== 5. v_wishlist_now, on made-up series ===")
try:
    store = made_store("view")
    c = store._conn
    for appid, name, genres in ((10, "Ten", (1, 2)), (20, "Twenty", (3,)), (50, "Fifty", (1,)), (60, "Sixty", (2,))):
        app_row(store, appid, name, genres)
    store.land_wishlist(reading(1001, at(10), 10, 20, 50))
    store.land_wishlist(reading(1002, at(10), 10, 60))
    store.land_wishlist(reading(1003, at(10), 70))  # not mine: never on the page
    price(store, 10, at(10), 1999)
    price(store, 20, at(10), 2999)
    price(store, 20, at(11), 1499, 2999)
    price(store, 50, at(10), 1000)
    price(store, 50, at(11), 500, 1000)
    price(store, 50, at(12), 800, 1000)
    price(store, 60, at(10), 999)
    price(store, 60, at(11), 999)
    rows = now_rows(store)
    check("one row per game on the lists of the accounts marked mine; the one not mine left out",
          sorted(rows) == [10, 20, 50, 60], sorted(rows))
    check("a game on two lists is one row, both accounts named", rows[10]["accounts"] == "Alpha, Bravo"
          and rows[10]["lists"] == 2, rows[10])
    check("one price: not 'at its lowest'", rows[10]["observations"] == 1 and rows[10]["is_lowest_now"] == 0)
    check("two prices, the newest the lowest and a higher one seen: at its lowest",
          rows[20]["is_lowest_now"] == 1 and rows[20]["lowest_cents"] == 1499 and rows[20]["lowest_on"] == at(11)
          and rows[20]["highest_cents"] == 2999 and rows[20]["discount_percent"] == 50)
    check("a price that never moved, seen twice, is not at its lowest", rows[60]["observations"] == 2
          and rows[60]["is_lowest_now"] == 0)
    check("seen cheaper before: not at its lowest; the lowest and its day said", rows[50]["is_lowest_now"] == 0
          and rows[50]["lowest_cents"] == 500 and rows[50]["lowest_on"] == at(11) and rows[50]["final_cents"] == 800
          and rows[50]["observations"] == 3)
    store.land_wishlist(reading(1002, at(12), 60))  # Bravo lets 10 go; Alpha still has it
    store.land_wishlist(reading(1001, at(12), 10, 20))  # Alpha lets 50 go: on no list now
    rows = now_rows(store)
    check("let go by one of its two lists: still on the page, one list, no removed_at",
          rows[10]["lists"] == 1 and rows[10]["removed_at"] is None and rows[10]["accounts"] == "Alpha")
    check("let go by every list: no list, removed_at the moment", rows[50]["lists"] == 0
          and rows[50]["removed_at"] == at(12))
    c.execute("INSERT INTO game (identity_key, name_origin, steam_appid, appid_source, playtime_seconds) "
              "VALUES ('c:/games/ten', 'scan', 10, 'search', 3600)")
    c.execute("INSERT INTO steam_read (account_id, read_at, file_modified, apps_in_file, apps_with_time) "
              "VALUES (1001, ?, ?, 1, 1), (1003, ?, ?, 1, 1)", (at(9), at(9), at(9), at(9)))
    c.execute("INSERT INTO steam_playtime (account_id, appid, observed_at, minutes_total) VALUES "
              "(1001, 10, ?, 120), (1003, 10, ?, 999)", (at(9), at(9)))
    rows = now_rows(store)
    check("the hours already played: the launcher's 60 minutes and Steam's 120 on an account marked mine, "
          "not the 999 of one that is not", rows[10]["minutes_played"] == 180 and rows[20]["minutes_played"] is None,
          (rows[10]["minutes_played"], rows[20]["minutes_played"]))
    check("v_wishlist_now and v_price_range agree on every game", all(
        (rows[a]["lowest_cents"], rows[a]["observations"]) == c.execute(
            "SELECT lowest_cents, observations FROM v_price_range WHERE appid = ?", (a,)).fetchone() for a in rows))
    store.close()
except Exception as exc:
    unreached("5", exc)

print("\n=== 6. the fit line (rarity-weighted since Phase 89) ===")
try:
    import math

    def cosine(genres, weights, profile):
        """The definition, written out here: each genre its weight, both vectors of length 1, their dot."""
        def unit(gs):
            v = {g: weights.get(g, 0.0) for g in gs}
            n = math.sqrt(sum(x * x for x in v.values()))
            return {g: x / n for g, x in v.items()} if n else {}
        played = {}
        for minutes, gs in profile.values():
            for g, x in unit(gs).items():
                played[g] = played.get(g, 0.0) + minutes * x
        n = math.sqrt(sum(x * x for x in played.values()))
        return sum(x * played.get(g, 0.0) / n for g, x in unit(genres).items())

    even = {1: 1.0, 2: 1.0, 3: 1.0, 9: 1.0}
    alone = {101: (100.0, frozenset({1}))}
    half = wishlist.fit([(1, "Action"), (2, "Strategy")], alone, True, even)
    check("by hand: Action and Strategy against hours all in Action is 1/sqrt(2), 71%, Action named",
          abs(half.share - 1 / math.sqrt(2)) < 1e-9 and half.words == "71% like what you play · Action", half)
    three_one = {101: (300.0, frozenset({1})), 102: (100.0, frozenset({2}))}
    check("by hand: hours 3 to 1, a game of the smaller genre is 1/sqrt(10), 32%",
          wishlist.fit([(2, "Strategy")], three_one, True, even).words == "32% like what you play · Strategy")
    both = wishlist.fit([(1, "Action"), (2, "Strategy")], three_one, True, even)
    check("by hand: both genres, 4/sqrt(20) = 89%, the genres named by how much each adds",
          abs(both.share - 4 / math.sqrt(20)) < 1e-9 and both.words == "89% like what you play · Action, Strategy", both)
    common = {1: 0.1, 2: 2.0, 3: 2.0}
    nine_one = {101: (900.0, frozenset({1})), 102: (100.0, frozenset({2}))}
    rare = wishlist.fit([(1, "Action"), (3, "Puzzle")], nine_one, True, common)
    check("a genre most apps have counts for little: Action (90% of the hours) with Puzzle reads 5%, where the "
          "share of the hours said 90%", abs(rare.share - cosine({1, 3}, common, nine_one)) < 1e-9
          and rare.words == "5% like what you play · Action", rare)
    check("the weights from the query: ln(apps with any genre / apps with this one), nothing for a genre all have",
          wishlist.weights_of([{"genre_id": 1, "apps": 2, "corpus": 4}, {"genre_id": 2, "apps": 4, "corpus": 4}])
          == {1: math.log(2), 2: 0.0})
    check("a game whose genres every app has: nothing to tell it apart by, said so",
          wishlist.fit([(2, "Strategy")], three_one, True, {1: 1.0, 2: 0.0}).words == "no genre to compare")
    check("a game whose record is not fetched yet: no share, and it says so",
          wishlist.fit([], three_one, False, even) == wishlist.Fit(None, "not fetched yet"))
    check("a record with no genre to compare: said in words", wishlist.fit([], three_one, True, even).words
          == "no genre to compare")
    check("nothing played yet: said in words",
          wishlist.fit([(1, "Action")], {}, True, even).words == "nothing played to compare with")
    check("no genre in common: unlike what you play, its own genres named",
          wishlist.fit([(9, "Racing")], three_one, True, even).words == "unlike what you play · Racing")
    tiny = {101: (1.0, frozenset({1})), 102: (999.0, frozenset({2}))}
    check("a sliver: under 1%", wishlist.fit([(1, "Action")], tiny, True, even).words
          == "under 1% like what you play · Action")
    store = made_store("fit")
    app_row(store, 10, "Ten", (1, 2, 37))
    app_row(store, 20, "Twenty", (3,))
    app_row(store, 900, "Played A", (1, 2))
    app_row(store, 901, "Played B", (1,))
    app_row(store, 902, "Played C", (3,))
    app_row(store, 30, "Thirty", record=False)
    c = store._conn
    for key, appid, minutes in (("a", 900, 600), ("b", 901, 300), ("c", 902, 100)):
        c.execute("INSERT INTO game (identity_key, name_origin, steam_appid, appid_source, playtime_seconds) "
                  "VALUES (?, 'scan', ?, 'manifest', ?)", (f"c:/games/{key}", appid, minutes * 60))
    store.land_wishlist(reading(1001, at(10), 10, 20, 30))
    found = wishlist.fits(store.reports())
    # Five apps with a record and a genre (Free To Play not one): Action on 3, Strategy on 2, Puzzle on 2.
    weights = {1: math.log(5 / 3), 2: math.log(5 / 2), 3: math.log(5 / 2)}
    played = {900: (600.0, frozenset({1, 2})), 901: (300.0, frozenset({1})), 902: (100.0, frozenset({3}))}
    ten, twenty = cosine({1, 2}, weights, played), cosine({3}, weights, played)
    check(f"from the queries: {ten:.0%} and {twenty:.0%}, worked out here; Strategy, the rarer, named first; "
          "Free To Play never named",
          abs(found[10].share - ten) < 1e-9 and found[10].words == f"{round(ten * 100)}% like what you play · "
          "Strategy, Action" and abs(found[20].share - twenty) < 1e-9
          and found[20].words == f"{round(twenty * 100)}% like what you play · Puzzle"
          and found[30].words == "not fetched yet", {a: f.words for a, f in found.items()})
    store.close()
except Exception as exc:
    unreached("6", exc)

print("\n=== 7. prices and records ===")
try:
    store = made_store("prices")
    for appid in (10, 20, 60):
        app_row(store, appid, f"App {appid}")
    store.land_wishlist(reading(1001, utc(hours=30), 10, 20))
    store.land_wishlist(reading(1001, utc(hours=2), 10))  # 20 let go
    for appid in (10, 20, 60):
        price(store, appid, utc(hours=rules.WISHLIST_PRICE_HOURS + 1), 1000)
    due = prices.due(store, True)
    check(f"a game on a wishlist, priced {rules.WISHLIST_PRICE_HOURS + 1} hours ago, is due; one let go and one "
          "never wished are not", due == [10], due)
    store._conn.execute("INSERT INTO steam_app (appid, has_record, name) VALUES (61, 1, 'App 61')")
    price(store, 61, utc(days=rules.PRICE_REFRESH_DAYS + 1), 900)
    check("an app seen a week ago is due as before", 61 in prices.due(store, True))
    check("the log says how often each", any(f"or {rules.WISHLIST_PRICE_HOURS} hours for a wishlist game" in line
                                              for line in lines))
    check("the weekly rule alone, without the wishlist's", store.prices_due(rules.PRICE_REFRESH_DAYS) == [61])
    c = store._conn
    c.execute("INSERT INTO steam_app (appid, has_record) VALUES (500, 0), (501, 0)")
    c.execute("INSERT INTO steam_read (account_id, read_at, file_modified, apps_in_file, apps_with_time) "
              "VALUES (1001, ?, ?, 2, 2)", (at(9), at(9)))
    c.execute("INSERT INTO steam_playtime (account_id, appid, observed_at, minutes_total) VALUES "
              "(1001, 500, ?, 10), (1001, 501, ?, 900)", (at(9), at(9)))
    store.land_wishlist(reading(1002, utc(hours=1), 700, 701, 501))
    wanted = store.steam_records_wanted()
    check("the records wanted: the played ones first, the most played first, then the wishlist's, each once",
          wanted == [501, 500, 700, 701], wanted)
    check("a limit cuts the list where it would have", store.steam_records_wanted(3) == [501, 500, 700])
    store.close()
except Exception as exc:
    unreached("7", exc)

print("\n=== 8. Settings: what each account's wishlist read found ===")
try:
    check("never read", ui_settings.wishlist_words({"wishlist_read_at": None}).startswith("Wishlist: not read yet"))
    check("a list read", ui_settings.wishlist_words({"wishlist_read_at": utc(hours=1), "wishlist_state": "items",
                                                     "wishlist_items": 16}).startswith("Wishlist: 16 games · read "))
    nothing_words = ui_settings.wishlist_words({"wishlist_read_at": utc(hours=1), "wishlist_state": "nothing",
                                                "wishlist_items": 0})
    check("nothing to read: private on Steam, or empty -- both said", "private on Steam, or empty" in nothing_words,
          nothing_words)
    store = made_store("settings")
    store.land_wishlist(reading(1001, utc(hours=1), 10, 20, 30))
    store.land_wishlist({"account_id": 1002, "read_at": utc(hours=1), "items": []})
    dialog = ui_settings.SettingsDialog({}, None, store=store)
    texts = [label.text() for label in dialog.findChildren(QLabel)]
    check("Alpha's row: three games on its wishlist", any("Wishlist: 3 games" in t for t in texts))
    check("Bravo's row: nothing to read", any("private on Steam, or empty" in t for t in texts))
    check("the accounts not marked mine say nothing about a wishlist",
          sum("Wishlist:" in t for t in texts) == 2, [t for t in texts if "Wishlist" in t])
    dialog.reject()
    store.close()
except Exception as exc:
    unreached("8", exc)

print("\n=== 9. the window's scan, the network on ===")
try:
    config = json.loads((SANDBOX / "config.json").read_text(encoding="utf-8"))
    config["allow_network"] = True
    (SANDBOX / "config.json").write_text(json.dumps(config), encoding="utf-8")
    real_get, real_web_get = steam_wishlist._get, steam_web._get
    threads: dict[str, list] = {"read": [], "land": []}
    asked_urls: list[str] = []

    def wishlist_answers(url):
        threads["read"].append(threading.current_thread() is threading.main_thread())
        asked_urls.append(url)
        return PUBLIC if not asked_urls[:-1] else NOTHING  # the first account public, the rest nothing

    real_land = library_db.LibraryStore.land_wishlist

    def landing(self, given):
        threads["land"].append(threading.current_thread() is threading.main_thread())
        return real_land(self, given)

    steam_wishlist._get, steam_web._get = wishlist_answers, (lambda url: None)
    library_db.LibraryStore.land_wishlist = landing
    raw = sqlite3.connect(f"file:{DATABASE.as_posix()}?mode=ro", uri=True)
    mine = raw.execute("SELECT account_id, steam_id64 FROM steam_account WHERE is_mine = 1 ORDER BY account_id").fetchall()
    reads_before = count(raw, "wishlist_read")
    raw.close()
    lines.clear()
    try:
        # The sandbox switches the startup scan off (QUIET_CONFIG): the window is asked for one.
        window = ui_window.MainWindow()
        window.show()
        settle(0.8)
        deadline = time.monotonic() + 180
        window.start_scan(trigger="manual")
        while not threads["land"] and time.monotonic() < deadline:
            settle(0.25)
        while window.worker is not None and window.worker.isRunning() and time.monotonic() < deadline:
            settle(0.25)
        settle(0.5)
        asked_first = len(asked_urls)
        window.start_scan(trigger="manual")  # a second scan the same day
        while window.worker is not None and window.worker.isRunning() and time.monotonic() < deadline:
            settle(0.25)
        settle(0.5)
        second_due = wishlist.due(window.overrides, True)
    finally:
        steam_wishlist._get, steam_web._get = real_get, real_web_get
        library_db.LibraryStore.land_wishlist = real_land
    c = window.overrides._conn
    check(f"the {len(mine)} accounts marked mine asked for, each once, by its own number",
          reads_before == 0 and asked_first == len(mine)
          and [rules.STEAM_WISHLIST_URL.format(steamid=n) for _a, n in mine] == asked_urls[:asked_first],
          (reads_before, asked_first))
    check("on the scan thread", threads["read"] and not any(threads["read"]), threads["read"])
    check("and landed on the GUI thread, the one writer", threads["land"] and all(threads["land"]), threads["land"])
    check("a read row for each account, the public list's 16 games in the wishlist",
          count(c, "wishlist_read") == len(mine) and count(c, "wishlist") == 16)
    check("the hand-off is gone once it has landed", not os.path.exists(wishlist.handoff_path(CACHE)))
    check("the log names the landing", any("wishlist: " in line and "answer(s) landed" in line for line in lines))
    check("the next scan the same day asks for no list", second_due == [] and len(asked_urls) == asked_first,
          (second_due, len(asked_urls)))
    window.close()
    settle(0.3)
except Exception as exc:
    unreached("9", exc)

print("\n=== 10. report 6: the wishlist at today's prices ===")
try:
    store = library_db.LibraryStore(DATABASE)
    source = store.reports()
    money = next(r for r in logic_reports.build(source) if r.key == "money")
    part = next((p for p in money.parts if p.heading == "Your wishlist at today's prices"), None)
    current = [r for r in source.rows("wishlist_now") if r["lists"] > 0]
    priced_rows = [r for r in current if r["kind"] == "priced"]
    from shared import humanize

    listed = humanize.money(sum(r["initial_cents"] for r in priced_rows), "EUR")
    today = humanize.money(sum(r["final_cents"] for r in priced_rows), "EUR")
    check("the report names the wishlist at list price and at today's prices, summed from the view itself",
          part is not None and part.rows[0] == ("At list price", listed) and part.rows[1] == ("At today's prices", today),
          part.rows if part else None)
    check("and says how many have a price, and how young the series is",
          part is not None and f"{len(current)} games on your wishlist, {len(priced_rows)} with a price" in part.note
          and "a sale before that is not in the series" in part.note, part.note if part else None)
    check("report 6 lists the query it reads", "money_wishlist" in money.queries)
    empty = logic_reports.wishlist_part({})
    check("no wishlist read: said in words, private and empty both", "private" in empty.note and not empty.rows)
    store.close()
except Exception as exc:
    unreached("10", exc)

print("\n=== 11. nothing writes to Steam; the network only in web/; the documents; the layers ===")
try:
    source = (PROJECT / "web" / "steam_wishlist.py").read_text(encoding="utf-8")
    check("the wishlist module asks with a plain GET: no data sent, no other method, no key",
          "data=" not in source and "method=" not in source and "key" not in source.split('"""', 2)[2].lower())
    outside = []  # suite 79's search, with the wishlist's service
    for path in PROJECT.rglob("*.py"):
        part = path.relative_to(PROJECT).parts[0]
        if part in ("web", "tests", ".venv", ".claude", "build", "dist", "docs", "packaging"):
            continue
        text = path.read_text(encoding="utf-8-sig")
        if "urlopen" in text or "urllib.request" in text or ("IWishlistService" in text and part != "shared"):
            outside.append(str(path.relative_to(PROJECT)))
    check("nothing outside web/ reaches the internet", not outside, outside)
    claude = (PROJECT / "CLAUDE.md").read_text(encoding="utf-8")
    check("CLAUDE.md names the eighth address and has the phase", "8. **The Steam wishlist**" in claude
          and "IWishlistService" in claude and "| 86 |" in claude and "## Phase 86 notes" in sources.build_log())
    baza = (PROJECT / "docs" / "BAZA_DE_DATE.md").read_text(encoding="utf-8")
    check("BAZA_DE_DATE: version 6, the tables and the view, section 8's last place taken",
          "### Versiunea 6 (faza 86)" in baza and "v_wishlist_now" in baza and "wishlist_read" in baza
          and "`wishlist`, experimental" not in baza)
    analysis = (PROJECT / "docs" / "ANALIZA.md").read_text(encoding="utf-8")
    quoted = dict(re.findall(r"```sql\n-- (\w+)\n(.*?)\n```", analysis, re.S))
    from data_access import reports as queries

    check("ANALIZA: stated and revealed preference, and the wishlist's queries as the code has them",
          "preferința declarată" in analysis and "preferința dezvăluită" in analysis and all(quoted.get(n) == queries.QUERIES[n] for n in
                                                     ("money_wishlist", "wishlist_now", "wishlist_profile", "wishlist_genres")),
          [n for n in ("money_wishlist", "wishlist_now", "wishlist_profile", "wishlist_genres")
           if quoted.get(n) != queries.QUERIES[n]])
    readme = (PROJECT / "docs" / "CITESTE-MA.md").read_text(encoding="utf-8")
    distribution = (PROJECT / "docs" / "DISTRIBUTIE.md").read_text(encoding="utf-8")
    check("CITESTE-MA: it reads a public list and never changes it; a private one shows nothing",
          "lista de dorințe" in readme and "nu o schimbă" in readme and "privată" in readme)
    check("DISTRIBUTIE: the wishlist in a sentence", "lista de dorințe" in distribution.lower())
    layers = subprocess.run([sys.executable, str(PROJECT / "tests" / "check_layers.py")], capture_output=True,
                            text=True, encoding="utf-8", errors="replace")
    check("no import points up a layer; sqlite3 only in data_access/", layers.returncode == 0, layers.stdout[-300:])
    check("nothing in this suite reached the network", attempts == [], attempts[:3])
except Exception as exc:
    unreached("11", exc)

print("\n=== 12. the real library is exactly as it was found ===")
changed = box.finish()
check("config.json and the library database are unchanged", not changed, changed)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
