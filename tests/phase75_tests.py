"""Phase 75: Steam's own playtime -- the database's version 3, the reader, the landing, the marks.

The upgrade from version 2 (and from 1, through both scripts) on a copy of the library; what
the three new tables refuse; the reader of Steam's files on this PC, read only, its counts
measured here independently -- the account whose file says "Apps", the non-Steam shortcut,
the accounts loginusers.vdf does not list -- and on made-up files that are cut short, empty or
without an apps block; the landing, recorded only on change, never updating or deleting a
reading; the two views; the records fetched for the accounts marked mine, at most a handful a
scan, the most played first; the three-way mark in Settings with the mouse and with the pad;
and a window scan that reads on the scan thread and lands on the GUI thread, with the network
off.

On a throwaway copy of the data (the Steam caches copied in, read only). Nothing is fetched:
the network is blocked, and the one fetch is answered by a stand-in for the store.
"""
import builtins
import json
import os
import re
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import datetime, timezone
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

import vdf
from PySide6.QtCore import QEventLoop, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton

app = QApplication([])

from adapters import controller
from data_access import backups, library_db
from logic import migration, steam_projection
from presentation import ui_rules, ui_settings, ui_window
from providers import steam
from shared import paths, rules
from web import steam_web

try:
    from logic import steam_time
    from providers import steam_userdata
except ImportError:  # the code before this phase has neither; the sections that need them say so
    steam_time = steam_userdata = None

CACHE = str(paths.cache_dir())
DATABASE = SANDBOX / rules.LIBRARY_DB_FILE
BASE = 76561197960265728  # an individual account's SteamID64 less its account id, written out here
APPS_PATH = ("UserLocalConfigStore", "Software", "Valve", "Steam", "apps")
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
        sql = re.sub(r"\s+", " ", re.sub(r"--[^\n]*", "", sql)).strip()
        found.append((kind, name, table, sql))
    return found


def schema_at(tag: str) -> str:
    """The schema as it was at a restore point, read out of git."""
    return subprocess.run(["git", "show", f"{tag}:data_access/schema.sql"], cwd=PROJECT,
                          capture_output=True, check=True).stdout.decode("utf-8")


def ci(mapping, name):
    """A key whatever its case -- written here, apart from the reader under test."""
    if not isinstance(mapping, dict):
        return None
    for key, value in mapping.items():
        if key.lower() == name.lower():
            return value
    return None


def independent(path: Path) -> dict:
    """One localconfig.vdf counted here, without the reader."""
    with open(path, encoding="utf-8", errors="replace") as handle:
        data = vdf.load(handle)
    node = data
    for name in APPS_PATH:
        node = ci(node, name)
    apps = node if isinstance(node, dict) else {}
    blocks = {int(k): v for k, v in apps.items() if k.isdigit() and isinstance(v, dict)}
    return {
        "in_file": len(blocks),
        "with_time": sum(1 for v in blocks.values() if ci(v, "Playtime") is not None),
        "minutes": {a: int(ci(v, "Playtime")) for a, v in blocks.items() if str(ci(v, "Playtime") or "").isdigit()},
        "last_only": sum(1 for v in blocks.values() if ci(v, "Playtime") is None and ci(v, "LastPlayed") is not None),
        "shortcuts": sum(1 for k in apps if k.startswith("-") and k[1:].isdigit()),
        "steam_node": ci(ci(ci(ci(data, "UserLocalConfigStore"), "Software"), "Valve"), "Steam"),
    }


def count(conn, table: str) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def refused(conn, sql: str, args=()) -> bool:
    try:
        conn.execute(sql, args)
    except sqlite3.IntegrityError:
        return True
    return False


print("=== 1. the upgrade to version 3, on a copy of the real library ===")
try:
    have = test_sandbox._version(DATABASE)
    if have != 2:
        # The user's own start has upgraded the real database already: a version-2 copy is made
        # from it the way Phase 73 made one -- the schema of the day read out of git, the same rows.
        print(f"         (the real library is at version {have}: a version-2 copy is built from it)")
        source = library_db.LibraryStore(DATABASE)
        records, entries = source.export_records(), source.load_catalog()
        source.close()
        DATABASE.unlink()
        conn = library_db.connect(DATABASE)
        with library_db.transaction(conn):
            conn.executescript(schema_at("before-phase-75"))
            conn.execute("INSERT INTO meta (id, schema_version, created_at) VALUES (1, 2, ?)",
                         (datetime.now().astimezone().isoformat(timespec="seconds"),))
            conn.execute("PRAGMA user_version = 2")
        library_db.load(conn, records, entries, header={}, steam_records={}, steam_summary={}, search_names={})
        conn.close()
    check("the copy starts at version 2", test_sandbox._version(DATABASE) == 2)
    before_print = library_db.file_fingerprint(DATABASE)
    v2 = sqlite3.connect(f"{DATABASE.resolve().as_uri()}?mode=ro", uri=True)
    v2_tables = [r[0] for r in v2.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")]
    v2_rows = {t: sorted(map(repr, v2.execute(f"SELECT * FROM {t}"))) for t in v2_tables}
    v2.close()
    snapshots_before = len(backups.list_snapshots())
    lines.clear()

    store = migration.open_library()
    newest = backups.list_snapshots()[0]
    check("a snapshot is taken first, holding the library as it was",
          len(backups.list_snapshots()) == snapshots_before + 1
          and library_db.file_fingerprint(newest.path / rules.LIBRARY_DB_FILE) == before_print)
    # Since Phase 76 the newest version is 4 (one view replaced), and a version-2 file goes
    # through both scripts; what version 3 added is checked below, by name.
    check(f"the database is at version {library_db.SCHEMA_VERSION}: the store, meta and PRAGMA user_version agree",
          store.version == library_db.SCHEMA_VERSION >= 3
          and store.version == library_db.schema_version(store._conn)
          == store._conn.execute("SELECT schema_version FROM meta").fetchone()[0])
    fresh = sqlite3.connect(":memory:", autocommit=True)
    library_db.create(fresh)
    check("a fresh database and the upgraded one have the same schema (normalised sqlite_master)",
          schema_of(fresh) == schema_of(store._conn),
          [row[:2] for row in schema_of(fresh) if row not in schema_of(store._conn)][:3])
    old = sqlite3.connect(":memory:", autocommit=True)
    old.executescript(schema_at("before-phase-75"))
    added = [row[:2] for row in schema_of(store._conn) if row not in schema_of(old)]
    removed = [row[:2] for row in schema_of(old) if row not in schema_of(store._conn)]
    # Version 7 (Phase 93) adds a column to session, version 8 (Phase 101) two to game: their text is both
    # "added" and "removed".
    check(f"additive only -- expand before contract: {len(added)} objects added, none removed or changed",
          sorted(removed) == [("table", "game"), ("table", "session")] and sorted(added) == sorted([
              ("table", "session"),  # version 7 (Phase 93): a column added
              ("table", "game"), ("table", "price_target"), ("table", "price_alert"),  # version 8 (Phase 101)
              ("table", "rating"),
              ("index", "steam_playtime_by_app"), ("table", "steam_account"), ("table", "steam_playtime"),
              ("table", "steam_read"), ("view", "v_steam_time_latest"), ("view", "v_steam_time_mine"),
              ("view", "v_hours"),  # version 5 (Phase 83), which a version-2 file now reaches too
              # version 6 (Phase 86): the wishlist
              ("table", "wishlist_read"), ("table", "wishlist"), ("view", "v_wishlist_now")]),
          (added, removed))
    # The Steam projection runs after an upgrade (Phase 73's seeding) and may bring a record or a
    # price the cache has and the copy did not; those tables may only have gained rows.
    projected = {"steam_app", "genre", "steam_app_genre", "category", "steam_app_category", "company",
                 "steam_app_company", "price_snapshot"}
    # A session's row gains its origin (version 7, Phase 93), a game's two dates (version 8, Phase 101):
    # every column it had, as it was.
    def rows_now(table):
        return test_sandbox.rows_in_old_columns(store._conn, table)

    check("every row of the user's tables is as it was -- the records, sessions, catalogue, purchases",
          all(rows_now(t) == v2_rows[t] for t in v2_tables if t not in projected | {"meta"})
          and {r[0] for r in store._conn.execute("SELECT DISTINCT origin FROM session")} <= {"launched"})
    check("and the price series and the Steam apps only gained rows, never lost or changed one",
          set(v2_rows["price_snapshot"]) <= set(map(repr, store._conn.execute("SELECT * FROM price_snapshot")))
          and {r[0] for r in store._conn.execute("SELECT appid FROM steam_app")}
          >= {int(r.split(",")[0].strip("(")) for r in v2_rows["steam_app"]})
    check("the three new tables are empty until a scan reads Steam's files",
          count(store._conn, "steam_account") == count(store._conn, "steam_read")
          == count(store._conn, "steam_playtime") == 0)
    check("the new tables are STRICT", all(store._conn.execute(
        "SELECT strict FROM pragma_table_list WHERE name = ?", (t,)).fetchone()[0] == 1
        for t in ("steam_account", "steam_read", "steam_playtime")))
    check("and the log says so", any(f"upgraded from version 2 to {library_db.SCHEMA_VERSION}" in line
                                     for line in lines)
          and any(f"is at version {library_db.SCHEMA_VERSION} now (snapshot" in line for line in lines))
    check("the store says it keeps Steam's time", getattr(store, "keeps_steam_time", False) is True)
    store.close()

    # From version 1, through both scripts in one transaction.
    one = sqlite3.connect(":memory:", autocommit=True)
    one.executescript(schema_at("before-phase-73"))
    one.execute("INSERT INTO meta (id, schema_version, created_at) VALUES (1, 1, '2026-10-01T00:00:00+03:00')")
    one.execute("PRAGMA user_version = 1")
    applied = library_db.upgrade(one)
    check("a version-1 database goes through both scripts, to the same schema as a fresh one",
          applied == list(range(2, library_db.SCHEMA_VERSION + 1)) and schema_of(one) == schema_of(fresh)
          and library_db.schema_version(one) == library_db.SCHEMA_VERSION, applied)
except Exception as exc:
    unreached("1", exc)

print("\n=== 2. what the three tables refuse ===")
try:
    db = sqlite3.connect(":memory:", autocommit=True)
    library_db.create(db)
    db.execute("PRAGMA foreign_keys = ON")
    library_db.ensure_steam_app(db, 730)
    t, utc = "2026-10-11T10:00:00+00:00", "2026-10-11T11:00:00+00:00"
    account = ("INSERT INTO steam_account (account_id, steam_id64, is_mine, most_recent, first_seen, last_seen) "
               "VALUES (?, ?, ?, ?, ?, ?)")
    db.execute(account, (5, 5 + BASE, None, None, t, t))
    check("an account whose SteamID64 is its id plus the base goes in", count(db, "steam_account") == 1)
    for name, args in (("an account id of 0", (0, BASE, None, None, t, t)),
                       ("a SteamID64 that is not the id plus the base", (6, 6 + BASE + 1, None, None, t, t)),
                       ("a mark that is not 0, 1 or nothing", (7, 7 + BASE, 2, None, t, t)),
                       ("a 'most recent' that is not 0 or 1", (8, 8 + BASE, None, 5, t, t)),
                       ("the same account twice", (5, 5 + BASE, None, None, t, t))):
        check(f"steam_account refuses {name}", refused(db, account, args))
    read = ("INSERT INTO steam_read (account_id, read_at, file_modified, apps_in_file, apps_with_time) "
            "VALUES (?, ?, ?, ?, ?)")
    db.execute(read, (5, utc, t, 3, 2))
    for name, args in (("a reading of an account it does not know", (9, utc, t, 3, 2)),
                       ("a moment that is not UTC", (5, "2026-10-11T14:00:00+03:00", t, 3, 2)),
                       ("a moment written with a space", (5, "2026-10-11 12:00:00", t, 3, 2)),
                       ("more apps with time than apps in the file", (5, "2026-10-11T12:00:00+00:00", t, 2, 3)),
                       ("a negative count", (5, "2026-10-11T12:00:00+00:00", t, -1, 0))):
        check(f"steam_read refuses {name}", refused(db, read, args))
    play = ("INSERT INTO steam_playtime (account_id, appid, observed_at, minutes_total, minutes_2wks, "
            "minutes_disconnected, last_played) VALUES (?, ?, ?, ?, ?, ?, ?)")
    db.execute(play, (5, 730, utc, 100, 0, 0, "2026-10-10T21:00:00+03:00"))
    check("a counter dated by its reading goes in", count(db, "steam_playtime") == 1)
    later = "2026-10-11T12:30:00+00:00"  # a second reading, so a refusal below is for its own reason
    db.execute(read, (5, later, t, 3, 2))
    for name, args in (("a counter with no reading at its moment", (5, 730, "2026-10-11T12:00:00+00:00", 1, 0, 0, None)),
                       ("an app the database does not know", (5, 999999999, later, 1, 0, 0, None)),
                       ("negative minutes", (5, 730, later, -1, 0, 0, None)),
                       ("negative minutes in the last two weeks", (5, 730, later, 1, -1, 0, None)),
                       ("the same app at the same moment twice", (5, 730, utc, 101, 0, 0, None))):
        check(f"steam_playtime refuses {name}", refused(db, play, args))
    try:
        db.execute(play, (5, 730, later, "abc", 0, 0, None))
        strict = False
    except sqlite3.Error:
        strict = True
    check("and, being STRICT, minutes that are words", strict)
except Exception as exc:
    unreached("2", exc)

print("\n=== 3. the reader, on this PC's own Steam files, read only ===")
root = steam.find_steam()
reading = None
try:
    check("Steam's folder is found in the registry", root is not None and os.path.isdir(root), root)
    opened: list[tuple[str, str]] = []
    real_open = builtins.open

    def watching_open(file, mode="r", *args, **kwargs):
        if isinstance(file, (str, os.PathLike)) and str(root).lower() in str(file).lower():
            opened.append((str(file), mode))
        return real_open(file, mode, *args, **kwargs)

    builtins.open = watching_open
    try:
        reading = steam_userdata.read_all(root)
    finally:
        builtins.open = real_open
    check(f"every file of Steam's opened for reading only ({len(opened)} opened)",
          opened and all(mode in ("r", "rt") for _, mode in opened), opened[:3])

    folder = Path(root) / "userdata"
    expected = {int(p.name): p / "config" / "localconfig.vdf" for p in folder.iterdir()
                if p.name.isdigit() and int(p.name) > 0 and (p / "config" / "localconfig.vdf").is_file()}
    counted = {a: independent(p) for a, p in expected.items()}
    reads = {r["account_id"]: r for r in reading["reads"]}
    check(f"one reading for each of the {len(expected)} accounts with a localconfig.vdf",
          set(reads) == set(expected), (sorted(reads), sorted(expected)))
    check("one moment for all of them, in UTC", len({r["read_at"] for r in reading["reads"]}) == 1
          and all(r["read_at"].endswith("+00:00") for r in reading["reads"]))
    for account_id, mine in sorted(counted.items()):
        got = reads.get(account_id, {})
        values = {v["appid"]: v for v in got.get("values", [])}
        check(f"account {account_id}: {mine['in_file']} apps in the file, {mine['with_time']} with time, "
              f"every counter the file's", got.get("apps_in_file") == mine["in_file"]
              and got.get("apps_with_time") == mine["with_time"]
              and all(values.get(a, {}).get("minutes_total") == m for a, m in mine["minutes"].items())
              and sum(1 for v in values.values() if v["minutes_total"] is None and v["last_played"]) == mine["last_only"],
              (got.get("apps_in_file"), got.get("apps_with_time")))
        check(f"account {account_id}: its file's time is when Steam last wrote it",
              got.get("file_modified") == datetime.fromtimestamp(
                  os.path.getmtime(expected[account_id]), timezone.utc).isoformat(timespec="seconds"))
    cs2 = {v["appid"]: v["minutes_total"] for v in reads.get(242635243, {}).get("values", [])}.get(730)
    check(f"Counter-Strike 2 on account 242635243: {cs2} minutes, as its file says",
          cs2 is not None and cs2 == counted.get(242635243, {}).get("minutes", {}).get(730))
    if reads.get(242635243, {}).get("file_modified") == "2026-08-15T01:59:18+00:00":
        check("and 135,352, as measured on 11 October -- its file has not changed since", cs2 == 135352, cs2)
    # The casing trap: one file here says "Apps".
    capital = [a for a, c in counted.items() if isinstance(c["steam_node"], dict) and "Apps" in c["steam_node"]]
    for account_id in capital:
        check(f"account {account_id}'s file says \"Apps\": a case-sensitive read finds nothing there, "
              f"and the reader finds its {counted[account_id]['in_file']} apps",
              "apps" not in counted[account_id]["steam_node"] and counted[account_id]["in_file"] > 0
              and reads[account_id]["apps_in_file"] == counted[account_id]["in_file"])
    if not capital:
        print("         (no file here says \"Apps\" today; the made-up files below still check it)")
    shortcuts = sum(c["shortcuts"] for c in counted.values())
    check(f"{shortcuts} non-Steam shortcut(s) -- a negative id, no store app -- skipped and counted",
          sum(r.get("shortcuts_skipped", 0) for r in reading["reads"]) == shortcuts
          and all(v["appid"] > 0 for r in reading["reads"] for v in r["values"]))
    with open(Path(root) / "config" / "loginusers.vdf", encoding="utf-8", errors="replace") as handle:
        users = ci(vdf.load(handle), "users") or {}
    names = {int(sid) - BASE: info for sid, info in users.items()}
    accounts = {a["account_id"]: a for a in reading["accounts"]}
    check("every SteamID64 is the account id plus the base, listed or not",
          all(a["steam_id64"] == a["account_id"] + BASE for a in reading["accounts"]))
    check(f"the {sum(1 for a in accounts if a in names)} account(s) loginusers.vdf lists carry its persona "
          "and their last login (its Timestamp, in UTC)",
          all(accounts[a]["persona"] == ci(names[a], "PersonaName") and accounts[a]["last_login"]
              == datetime.fromtimestamp(int(ci(names[a], "Timestamp")), timezone.utc).isoformat(timespec="seconds")
              for a in accounts if a in names))
    unlisted = [a for a in accounts if a not in names]
    check(f"an account it does not list ({unlisted}) is read all the same, with no name",
          unlisted and all(accounts[a]["persona"] is None for a in unlisted), unlisted)
except Exception as exc:
    unreached("3", exc)

print("\n=== 4. the reader, on made-up files ===")
try:
    fake = SANDBOX / "fake_steam"
    files = {
        111: '"UserLocalConfigStore"\n{\n "Software"\n {\n  "Valve"\n  {\n   "Steam"\n   {\n'
             '    "language" "english"\n   }\n  }\n }\n}\n',
        222: '"UserLocalConfigStore"\n{\n "Software"\n {\n  "Valve"\n  {\n   "Steam"\n   {\n    "apps"\n    {\n'
             '     "730"\n     {\n      "Playtime" "10"\n',  # cut off half way, as a read caught mid-write is
        333: "",
        444: '"userlocalconfigstore"\n{\n "software"\n {\n  "valve"\n  {\n   "steam"\n   {\n    "APPS"\n    {\n'
             '     "730"\n     {\n      "playtime" "12"\n      "LASTPLAYED" "0"\n     }\n'
             '     "40"\n     {\n      "cloud"\n      {\n       "last_sync_state" "synchronized"\n      }\n     }\n'
             '     "-1234"\n     {\n      "Playtime" "5"\n     }\n    }\n   }\n  }\n }\n}\n',
    }
    for account_id, text in files.items():
        target = fake / "userdata" / str(account_id) / "config"
        target.mkdir(parents=True)
        (target / "localconfig.vdf").write_text(text, encoding="utf-8")
    (fake / "userdata" / "0").mkdir()
    (fake / "userdata" / "notanumber").mkdir()
    lines.clear()
    made = steam_userdata.read_all(str(fake))
    got = {r["account_id"]: r for r in made["reads"]}
    check("no apps block at all: a reading with nothing in it, not an error",
          111 in got and got[111]["apps_in_file"] == 0 and got[111]["apps_with_time"] == 0 and got[111]["values"] == [])
    check("a file cut off half way: no reading for that account, and a line in the log",
          222 not in got and any("222" in line and "does not read" in line for line in lines))
    check("an empty file: no reading, and the log says why",
          333 not in got and any("333" in line and "holds no UserLocalConfigStore" in line for line in lines))
    check("every key in any case; a block with no time in it counted but not kept; a shortcut skipped",
          444 in got and got[444]["apps_in_file"] == 2 and got[444]["apps_with_time"] == 1
          and got[444]["values"] == [{"appid": 730, "minutes_total": 12, "minutes_2wks": None,
                                      "minutes_disconnected": None, "last_played": None}]
          and got[444]["shortcuts_skipped"] == 1, got.get(444))
    check("no loginusers.vdf: the accounts are read all the same, with no names, their SteamID64 worked out",
          {a["account_id"] for a in made["accounts"]} == {111, 444}
          and all(a["persona"] is None and a["steam_id64"] == a["account_id"] + BASE for a in made["accounts"]))
    check("no Steam folder, or one that is not there: nothing, quietly",
          steam_userdata.read_all(None) == {"accounts": [], "reads": []}
          == steam_userdata.read_all(str(SANDBOX / "no_such_folder")))
except Exception as exc:
    unreached("4", exc)

print("\n=== 5. landing a reading: recorded only on change, nothing updated or deleted ===")
try:
    store = library_db.LibraryStore(DATABASE)
    conn = store._conn

    def made_up(read_at, values, persona="Tester"):
        return {"accounts": [{"account_id": 999, "steam_id64": 999 + BASE, "account_name": None, "persona": persona,
                              "most_recent": None, "last_login": None}],
                "reads": [{"account_id": 999, "read_at": read_at, "file_modified": read_at,
                           "apps_in_file": len(values), "apps_with_time": len(values),
                           "values": [{"appid": a, "minutes_total": m, "minutes_2wks": 0, "minutes_disconnected": 0,
                                       "last_played": None} for a, m in values]}]}

    first = store.land_steam_time(made_up("2026-10-11T10:00:00+00:00", [(730, 100), (4242424, 5)]))
    check("a first reading: the account, its read row and both counters",
          first == {"accounts": 1, "reads": 1, "observations": 2, "lowered": []}, first)
    check("an app the database did not know gets a row of its own, with no record, so the key holds",
          conn.execute("SELECT has_record FROM steam_app WHERE appid = 4242424").fetchone() == (0,))
    print_before = library_db.fingerprint(conn)
    again = store.land_steam_time(made_up("2026-10-11T10:00:00+00:00", [(730, 100), (4242424, 5)]))
    check("the same reading landed twice changes nothing", again["reads"] == again["observations"] == 0
          and library_db.fingerprint(conn) == print_before, again)
    same = store.land_steam_time(made_up("2026-10-11T11:00:00+00:00", [(730, 100), (4242424, 5)]))
    check("a later reading with the same counters: a read row, and no counter",
          same["reads"] == 1 and same["observations"] == 0, same)
    one_more = store.land_steam_time(made_up("2026-10-11T12:00:00+00:00", [(730, 101), (4242424, 5)]))
    check("one minute more on one game: exactly one counter", one_more["observations"] == 1, one_more)
    check("the newest is the one the view shows, the older one kept beside it",
          conn.execute("SELECT minutes_total FROM v_steam_time_latest WHERE account_id = 999 AND appid = 730")
          .fetchone() == (101,) and conn.execute(
              "SELECT COUNT(*) FROM steam_playtime WHERE account_id = 999 AND appid = 730").fetchone() == (2,))
    lowered_reading = made_up("2026-10-11T13:00:00+00:00", [(730, 90), (4242424, 5)])
    steam_time._keep(CACHE, [lowered_reading])
    lines.clear()
    landed = steam_time.land(store, CACHE)
    check("a counter that went down is kept as read, and the log says so",
          landed.observations == 1 and landed.lowered == [(999, 730, 101, 90)]
          and any("went down, 101 -> 90" in line for line in lines), landed)
    check("and the hand-off is empty once it has landed", not os.path.exists(steam_time.handoff_path(CACHE)))
    store.set_account_mark(999, True)
    store.land_steam_time(made_up("2026-10-11T14:00:00+00:00", [(730, 90), (4242424, 5)], persona=None))
    check("a later reading never touches the mark, and a missing name keeps the one known",
          conn.execute("SELECT is_mine, persona FROM steam_account WHERE account_id = 999").fetchone() == (1, "Tester"))
    print_before = library_db.fingerprint(conn)
    bad = made_up("2026-10-11T15:00:00+00:00", [(730, -5)])
    check("a reading the tables refuse is refused whole: nothing of it written",
          store.land_steam_time(bad) is None and library_db.fingerprint(conn) == print_before)
    steam_time._keep(CACHE, [bad])
    kept = steam_time.land(store, CACHE)
    check("and through the landing it stays in the hand-off for the next scan",
          kept.kept == 1 and len(steam_time.pending(CACHE)) == 1)
    steam_time._keep(CACHE, [])
    # Nothing in the program updates or deletes a reading or a counter.
    app_folders = ("launcher.py", "scanner.py", "presentation", "adapters", "logic", "providers", "web",
                   "data_access", "shared")
    sources = [p for name in app_folders for p in ((PROJECT / name).rglob("*") if (PROJECT / name).is_dir()
                                                    else [PROJECT / name]) if p.suffix in (".py", ".sql")]
    text = "\n".join(p.read_text(encoding="utf-8-sig") for p in sources)
    check(f"no UPDATE and no DELETE of steam_read or steam_playtime anywhere in the program ({len(sources)} files)",
          not re.search(r"(UPDATE|DELETE\s+FROM)\s+steam_(read|playtime)\b", text, re.IGNORECASE))
    check("and the mark is written in one place only, from Settings",
          len(re.findall(r"SET\s+is_mine\b", text)) == 1 and "set_account_mark" in text
          and not re.search(r"INSERT INTO steam_account \([^)]*is_mine", text))
    check("no SQL in the reader or the landing's logic: the store holds it all", not any(
        re.search(r"\b(SELECT|INSERT INTO|UPDATE|DELETE FROM)\b", (PROJECT / f).read_text(encoding="utf-8"))
        for f in ("logic/steam_time.py", "providers/steam_userdata.py")))
    store.close()
except Exception as exc:
    unreached("5", exc)

print("\n=== 6. the two views ===")
try:
    db = sqlite3.connect(":memory:", autocommit=True)
    library_db.create(db)
    for appid in (10, 11, 12):
        library_db.ensure_steam_app(db, appid)
    t = "2026-10-01T00:00:00+00:00"
    for account_id, mark in ((1, 1), (2, 0), (3, None)):
        db.execute("INSERT INTO steam_account (account_id, steam_id64, is_mine, first_seen, last_seen) "
                   "VALUES (?, ?, ?, ?, ?)", (account_id, account_id + BASE, mark, t, t))
    rows = [(1, 10, "2026-10-01T00:00:00+00:00", 50, "2026-09-29T20:00:00+03:00"),
            (1, 10, "2026-10-02T00:00:00+00:00", 60, "2026-10-01T01:00:00+03:00"),  # 30 Sep 22:00 UTC
            (1, 11, "2026-10-02T00:00:00+00:00", None, "2026-09-01T10:00:00+03:00"),
            (2, 10, "2026-10-02T00:00:00+00:00", 1000, "2026-09-30T23:00:00+00:00"),  # an hour later, an earlier text
            (2, 12, "2026-10-02T00:00:00+00:00", 7, None),
            (3, 10, "2026-10-02T00:00:00+00:00", 500, None)]
    for account_id, appid, at, minutes, last in rows:
        db.execute("INSERT OR IGNORE INTO steam_read (account_id, read_at, file_modified, apps_in_file, apps_with_time) "
                   "VALUES (?, ?, ?, 9, 9)", (account_id, at, at))
        db.execute("INSERT INTO steam_playtime (account_id, appid, observed_at, minutes_total, last_played) "
                   "VALUES (?, ?, ?, ?, ?)", (account_id, appid, at, minutes, last))
    latest = db.execute("SELECT account_id, appid, minutes_total FROM v_steam_time_latest ORDER BY 1, 2").fetchall()
    check("v_steam_time_latest: one row for each account and app, the newest",
          latest == [(1, 10, 60), (1, 11, None), (2, 10, 1000), (2, 12, 7), (3, 10, 500)], latest)
    mine = db.execute("SELECT appid, minutes, accounts FROM v_steam_time_mine ORDER BY appid").fetchall()
    check("v_steam_time_mine: only the accounts marked mine -- not 'not mine', not 'not decided'",
          mine == [(10, 60, 1), (11, None, 1)], mine)
    db.execute("UPDATE steam_account SET is_mine = 1 WHERE account_id = 2")
    mine = {r[0]: r[1:] for r in db.execute("SELECT appid, minutes, accounts, last_played FROM v_steam_time_mine")}
    check("two accounts marked mine: their minutes added, and both counted",
          mine.get(10, (None,))[:2] == (1060, 2) and 12 in mine, mine)
    check("the last time played is the latest instant, whatever the offset it was written with",
          mine[10][2] == "2026-09-30T23:00:00+00:00", mine[10])
except Exception as exc:
    unreached("6", exc)

print("\n=== 7. the records of the apps in the history: the accounts marked mine, a few a scan ===")
try:
    store = library_db.LibraryStore(DATABASE)
    conn = store._conn
    store.land_steam_time(reading)  # this PC's own reading, from section 3
    store.set_account_mark(999, None)  # section 5's made-up account: not decided again
    check("the network off: nothing is wanted", steam_time.wanted(store, False) == [])
    check("no account marked mine: nothing is wanted", steam_time.wanted(store, True) == [])
    readings = {r["account_id"]: r for r in reading["reads"]}
    chosen = sorted(readings, key=lambda a: -readings[a]["apps_with_time"])[:2]
    for account_id in chosen:
        store.set_account_mark(account_id, True)
    unrecorded = {r[0] for r in conn.execute("SELECT appid FROM steam_app WHERE has_record = 0")}
    totals: dict[int, int] = {}
    for account_id in chosen:
        for value in readings[account_id]["values"]:
            totals[value["appid"]] = totals.get(value["appid"], 0) + (value["minutes_total"] or 0)
    expected_order = sorted((a for a in totals if a in unrecorded), key=lambda a: (-totals[a], a))
    wanted = steam_time.wanted(store, True)
    check(f"accounts {chosen} marked mine: {len(wanted)} apps with no record, the most played first, "
          "and none from an account not marked", wanted == expected_order, (wanted[:5], expected_order[:5]))
    asked: list[str] = []

    def store_stand_in(url):
        appid = url.split("appids=")[1].split("&")[0]
        asked.append(appid)
        if int(appid) % 3 == 0:  # some are no longer sold: "no store entry"
            return json.dumps({appid: {"success": False}}).encode()
        return json.dumps({appid: {"success": True, "data": {
            "type": "game", "name": f"History app {appid}", "steam_appid": int(appid), "is_free": True}}}).encode()

    # What a scan will really ask for: the wanted apps less those the cache already answers -- a
    # record, or a "no store entry" still fresh -- by the fetch's own rule. The user's scans since
    # this phase have cached such misses in the real cache the copy holds (found 14 October 2026:
    # the check assumed there were none).
    known = steam_web.SteamWebCache(CACHE)
    askable = [a for a in wanted if not (known.fresh(str(a)) is not None and (
        steam_web.has_details(CACHE, str(a)) or known.records[str(a)].get("has_details") is False))]
    real_get, real_gap = steam_web._get, rules.STEAM_WEB_RATE_LIMIT_SECONDS
    steam_web._get, rules.STEAM_WEB_RATE_LIMIT_SECONDS = store_stand_in, 0
    try:
        steam_web.fetch_records(wanted, CACHE, rules.STEAM_HISTORY_RECORDS_PER_SCAN)
        first_round = list(asked)
        asked.clear()
        steam_web.fetch_records(wanted, CACHE, rules.STEAM_HISTORY_RECORDS_PER_SCAN)
        second_round = list(asked)
    finally:
        steam_web._get, rules.STEAM_WEB_RATE_LIMIT_SECONDS = real_get, real_gap
    limit = rules.STEAM_HISTORY_RECORDS_PER_SCAN
    check(f"at most {limit} asked in a scan, in the history's order ({len(askable)} of the {len(wanted)} "
          "not already answered by the cache)",
          [int(a) for a in first_round] == askable[:limit], (first_round[:5], askable[:5]))
    check("the next scan asks none of them again -- not the records, not the ones no longer sold -- "
          "and goes on down the list", not set(first_round) & set(second_round)
          and [int(a) for a in second_round] == askable[limit:2 * limit], (second_round[:5], askable[limit:limit + 5]))
    done = steam_projection.refresh(store)
    found = [int(a) for a in first_round + second_round if int(a) % 3]
    check("after the scan the projection puts the records in the database, named",
          all(conn.execute("SELECT has_record, name FROM steam_app WHERE appid = ?", (a,)).fetchone()
              == (1, f"History app {a}") for a in found), done.stored[:5])
    check("each with its first price observation (free, here), as every record gets",
          all(conn.execute("SELECT kind FROM price_snapshot WHERE appid = ?", (a,)).fetchall() == [("free",)]
              for a in found))
    check("and the list of wanted records is shorter by exactly those",
          steam_time.wanted(store, True) == [a for a in wanted if a not in found])
    check("nothing went to the network", not attempts, attempts[:3])
    store.close()
except Exception as exc:
    unreached("7", exc)

print("\n=== 8. Settings: whose account it is, with the mouse and with the pad ===")
window = None
try:
    window = ui_window.MainWindow()
    window.resize(1280, 820)
    window.show()
    settle(1.0)
    store = window.overrides
    conn = store._conn
    marks = lambda: {r[0]: r[1] for r in conn.execute("SELECT account_id, is_mine FROM steam_account")}  # noqa: E731
    target = next(a for a in sorted(marks()) if a != 999 and marks()[a] is None)
    opened_with = marks()
    notes: dict = {}

    def modal():
        return QApplication.activeModalWidget()

    def press(name):
        window.pads.action.emit(name)

    def until(predicate, name, tries=90):
        left = [tries]

        def step():
            if predicate() or left[0] <= 0:
                return True
            left[0] -= 1
            press(name)
            return False
        return step

    def group_of(account_id):
        return modal().account_groups[account_id] if isinstance(modal(), ui_settings.SettingsDialog) else None

    def on_target():
        group = group_of(target)
        return group is not None and modal().focusWidget() in group.buttons()

    def chosen(account_id):
        return group_of(account_id).checkedButton().text()

    def ok_button():
        return next(b for b in modal().findChildren(QPushButton) if b.text() == "OK")

    def run(steps, limit_ms=90_000):
        position = [0]
        loop = QEventLoop()

        def advance():
            if position[0] >= len(steps):
                loop.quit()
                return
            QTimer.singleShot(200, advance)  # before running: a step may sit inside a dialog's own loop
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

        QTimer.singleShot(200, advance)
        QTimer.singleShot(limit_ms, watchdog)
        loop.exec()
        settle(0.3)

    run([
        lambda: press(controller.SETTINGS) or True,  # Start: Settings
        lambda: notes.update(open=isinstance(modal(), ui_settings.SettingsDialog),
                             listed=set(modal().account_groups) == set(marks()),
                             shown={a: chosen(a) for a in marks()}) or True,
        until(on_target, controller.DOWN),  # down, one stop per account row
        lambda: notes.update(landed=modal().focusWidget().text(), ring=modal()._ringed(modal().focusWidget())) or True,
        lambda: press(controller.LEFT) or True,  # left: Not mine
        lambda: notes.update(left1=(modal().focusWidget().text(), chosen(target))) or True,
        lambda: press(controller.LEFT) or True,  # left again: Mine
        lambda: notes.update(left2=(modal().focusWidget().text(), chosen(target))) or True,
        lambda: press(controller.LEFT) or True,  # at the end: stays
        lambda: notes.update(left3=chosen(target), unsaved=marks()[target]) or True,
        until(lambda: modal().focusWidget() is ok_button(), controller.DOWN),
        lambda: press(controller.ACTIVATE) or True,  # A on OK
        lambda: notes.update(closed=modal() is None) or True,
    ])
    labels = dict(ui_rules.STEAM_ACCOUNT_MARKS)
    check("Start opens Settings, and it lists every account read",
          notes.get("open") and notes.get("listed"), notes)
    check("each with the mark the library holds",
          notes.get("shown") == {a: labels[None if m is None else bool(m)] for a, m in opened_with.items()},
          notes.get("shown"))
    check("down lands on the account's own choice, Not decided, ringed inside it rather than outside",
          notes.get("landed") == "Not decided" and notes.get("ring") is False, notes.get("landed"))
    check("left moves the choice along: Not mine, then Mine, then stays at the end",
          notes.get("left1") == ("Not mine", "Not mine") and notes.get("left2") == ("Mine", "Mine")
          and notes.get("left3") == "Mine", (notes.get("left1"), notes.get("left2")))
    check("nothing is saved while the dialog is open", notes.get("unsaved") is None)
    check("down to OK and A: saved, the account now mine, every other mark as it was",
          notes.get("closed") and marks()[target] == 1
          and all(marks()[a] == m for a, m in opened_with.items() if a != target), marks())

    notes.clear()
    run([
        lambda: press(controller.SETTINGS) or True,
        until(on_target, controller.DOWN),
        lambda: press(controller.RIGHT) or True,
        lambda: press(controller.RIGHT) or True,
        lambda: notes.update(moved=chosen(target)) or True,
        lambda: press(controller.BACK) or True,  # B: Cancel
        lambda: notes.update(closed=modal() is None) or True,
    ])
    check("right moves it back towards Not decided; B cancels and nothing is saved",
          notes.get("moved") == "Not decided" and notes.get("closed") and marks()[target] == 1, notes)

    # The mouse: Not decided on that account, then OK.
    notes.clear()

    def click_through():
        dialog = modal()
        button = next(b for b in group_of(target).buttons() if b.text() == "Not decided")
        dialog.scroll.ensureWidgetVisible(button)
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        notes["changed"] = dialog.account_marks()
        QTest.mouseClick(ok_button(), Qt.MouseButton.LeftButton)
        return True

    run([
        lambda: QTimer.singleShot(0, window.open_settings) or True,
        lambda: isinstance(modal(), ui_settings.SettingsDialog),
        click_through,
        lambda: notes.update(closed=modal() is None) or True,
    ])
    check("with the mouse: a click chooses, OK saves only the mark that changed",
          notes.get("changed") == {target: None} and notes.get("closed") and marks()[target] is None, notes)
    check("no watchdog and no error on the way", not notes.get("watchdog") and not notes.get("errors"),
          notes.get("errors"))

    empty = test_sandbox.separate_store("no_accounts")
    dialogs = [ui_settings.SettingsDialog(window.config, window, store=empty),
               ui_settings.SettingsDialog(window.config, window, store=None)]
    check("a library with no account read, or none at all, says so in one row",
          all(not d.account_groups and any(r.title.text() == "No account read yet"
                                           for r in d.findChildren(ui_settings.SettingRow)) for d in dialogs))
    for dialog in dialogs:
        dialog.done(0)
    empty.close()
except Exception as exc:
    unreached("8", exc)

print("\n=== 9. a window scan: read on the scan thread, landed on the GUI thread, the network off ===")
try:
    store = window.overrides
    conn = store._conn
    threads: dict[str, list] = {"read": [], "land": []}
    handed: list[dict] = []
    real_read_all, real_land = steam_userdata.read_all, store.land_steam_time

    def reading_on(steam_root):
        threads["read"].append(threading.current_thread() is threading.main_thread())
        return real_read_all(steam_root)

    def landing_on(given):
        threads["land"].append(threading.current_thread() is threading.main_thread())
        handed.append(given)
        return real_land(given)

    newest_before = {(r[0], r[1]): r[2:] for r in conn.execute(
        "SELECT account_id, appid, minutes_total, minutes_2wks, minutes_disconnected, last_played "
        "FROM v_steam_time_latest")}
    reads_before, counters_before = count(conn, "steam_read"), count(conn, "steam_playtime")
    steam_userdata.read_all, store.land_steam_time = reading_on, landing_on
    lines.clear()
    attempts.clear()
    try:
        check("the window's scan starts", window.start_scan(trigger="manual"))
        worker = window.worker
        waited = time.monotonic()
        while (worker.isRunning() or not threads["land"]) and time.monotonic() - waited < 120:
            settle(0.25)
    finally:
        steam_userdata.read_all = real_read_all
        del store.land_steam_time
    check("the scan was told to read Steam's files, and -- the network off -- to fetch no record",
          worker.read_steam is True and worker.steam_records == [])
    check("Steam's files were read on the scan thread", threads["read"] == [False], threads["read"])
    check("and the reading landed on the GUI thread, the one writer", threads["land"] == [True], threads["land"])
    accounts_read = len(handed[0]["reads"]) if handed else -1
    changed = sum(1 for r in (handed[0]["reads"] if handed else []) for v in r["values"]
                  if newest_before.get((r["account_id"], v["appid"])) != tuple(
                      v[k] for k in ("minutes_total", "minutes_2wks", "minutes_disconnected", "last_played")))
    check(f"one read row for each of the {accounts_read} accounts, and a counter only where one changed ({changed})",
          count(conn, "steam_read") == reads_before + accounts_read
          and count(conn, "steam_playtime") == counters_before + changed)
    check("the hand-off is gone once it has landed", not os.path.exists(steam_time.handoff_path(CACHE)))
    check("the log names the landing", any("steam time: 1 reading(s) landed" in line for line in lines))
    check("nothing went to the network", not attempts, attempts[:3])
    window.close()
    settle(0.3)
    store.close()
except Exception as exc:
    unreached("9", exc)

print("\n=== 10. the layers ===")
try:
    layers = subprocess.run([sys.executable, str(PROJECT / "tests" / "check_layers.py")], cwd=PROJECT,
                            capture_output=True, text=True, timeout=120)
    check("no import points up a layer, and sqlite3 stays in data_access/",
          "upward imports: 0" in layers.stdout and "sqlite3 outside data_access/: 0" in layers.stdout,
          layers.stdout[-300:])
except Exception as exc:
    unreached("10", exc)

print("\n=== 11. the real library is exactly as it was found ===")
changed = box.finish()
check("config.json and the library database are unchanged", not changed, changed)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
