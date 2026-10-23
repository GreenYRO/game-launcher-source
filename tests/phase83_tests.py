"""Phase 83: the reports -- what the library database can say, one query at a time.

  1. schema version 5 on a copy of the real library: a snapshot first, v_hours added and nothing
     else, every row of every table as it was, fresh = upgraded;
  2. v_hours on made-up data: one row per app, Steam's minutes once however many games link to it,
     the launcher's added up, an account not marked mine left out, a game with no app its own row;
  3. the seven reports on made-up data with answers worked out by hand -- Gini (equal shares 0, one
     app with everything (n - 1)/n, and against its definition), the concentration figures, the
     abandonment buckets, two genres counting twice, Free To Play apart, the coverage, the set-aside
     apps and the non-games kept out, the backlog's states, the sessions' median and 90th
     percentile, the local hour of a summer and a winter session (never strftime's UTC hour), the
     money; an empty library answering in words; nothing written;
  4. the Stats page as the oracle: its lifetime time, most played, months and sources equal the SQL;
  5. reports.py: the Markdown with the day, --sql, the CSV files, a version-4 file and a missing one
     refused, nothing written;
  6. the comparison of the friends' exports sets Spacewar and the SDK aside too;
  7. the time on the real library, docs/ANALIZA.md quoting the code's SQL exactly, the layers.

On a throwaway copy of the data; the network is blocked.
"""
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import date, datetime
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from sources import build_log  # the build log's notes (Phase 91); `sources` is a table here
import test_sandbox

box = test_sandbox.start(migrate=False)  # the copy as it is: section 1 upgrades it itself
SANDBOX = box.folder
DATABASE = SANDBOX / "library.db"

attempts: list[str] = []


def no_network(request, *args, **kwargs):
    attempts.append(getattr(request, "full_url", str(request)))
    raise OSError("the network is blocked in this suite")


urllib.request.urlopen = no_network

import logging

logging.basicConfig(level=logging.CRITICAL)

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)

from data_access import library_db
from logic import comparison, comparison_report, migration, stats
from shared import rules

try:
    from data_access import reports as queries
    from logic import reports
except ImportError:  # the code before this phase has neither: each section then says it could not run
    queries = reports = None

passed = failed = 0
WORK = Path(tempfile.mkdtemp(prefix="phase83_"))
NOW = "2026-10-14T10:00:00+00:00"


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


def settle(seconds: float = 0.3) -> None:
    loop = QEventLoop()
    QTimer.singleShot(int(seconds * 1000), loop.quit)
    loop.exec()


def schema_of(conn) -> list:
    return sorted((t, n, re.sub(r"\s+", " ", s or "").strip())
                  for t, n, s in conn.execute("SELECT type, name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"))


# The upgrade's seeding runs the Steam projection, which refreshes a store record fetched since the last
# scan (suite 76's lesson, 12 October): those tables keep every app they knew; the rest stay exactly.
PROJECTED = {"steam_app", "genre", "steam_app_genre", "category", "steam_app_category", "company",
             "steam_app_company", "price_snapshot"}


def rows_hash(conn) -> dict:
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name != 'meta' "
                                         "AND name NOT LIKE 'sqlite_%'") if r[0] not in PROJECTED]
    # In the columns each table had: session gains its origin in version 7 (Phase 93).
    return {t: hashlib.sha256(repr(test_sandbox.rows_in_old_columns(conn, t)).encode()).hexdigest()
            for t in tables}


def fingerprint(path) -> str:
    conn = sqlite3.connect(f"file:{Path(path).resolve().as_posix()}?mode=ro", uri=True)
    try:
        return hashlib.sha256("\n".join(conn.iterdump()).encode()).hexdigest()
    finally:
        conn.close()


class Made:
    """A fresh version-5 library with rows put in by hand -- tests may write SQL on a scratch file."""

    def __init__(self, name: str) -> None:
        self.path = WORK / f"{name}.db"
        self.store = library_db.LibraryStore(self.path)
        self.c = self.store._conn
        self.scan = None

    def app(self, appid, name=None, kind="game", record=True, release=None, genres=(), publisher=None, developer=None):
        self.c.execute("INSERT INTO steam_app (appid, has_record, name, app_type, release_date) VALUES (?, ?, ?, ?, ?)",
                       (appid, int(record), name if record else None, kind if record else None, release))
        for genre_id, genre_name in genres:
            self.c.execute("INSERT OR IGNORE INTO genre (id, name) VALUES (?, ?)", (genre_id, genre_name))
            self.c.execute("INSERT INTO steam_app_genre (appid, genre_id) VALUES (?, ?)", (appid, genre_id))
        for role, company in (("publisher", publisher), ("developer", developer)):
            if company:
                self.c.execute("INSERT OR IGNORE INTO company (name) VALUES (?)", (company,))
                cid = self.c.execute("SELECT id FROM company WHERE name = ?", (company,)).fetchone()[0]
                self.c.execute("INSERT INTO steam_app_company (appid, company_id, role) VALUES (?, ?, ?)",
                               (appid, cid, role))

    def account(self, account_id, mine):
        self.c.execute("INSERT INTO steam_account (account_id, steam_id64, is_mine, first_seen, last_seen) "
                       "VALUES (?, ?, ?, ?, ?)", (account_id, account_id + 76561197960265728, mine, NOW, NOW))
        self.c.execute("INSERT INTO steam_read (account_id, read_at, file_modified, apps_in_file, apps_with_time) "
                       "VALUES (?, ?, ?, 0, 0)", (account_id, NOW, NOW))

    def steam(self, account_id, appid, minutes, last=None):
        self.c.execute("INSERT INTO steam_playtime (account_id, appid, observed_at, minutes_total, last_played) "
                       "VALUES (?, ?, ?, ?, ?)", (account_id, appid, NOW, minutes, last))

    def game(self, key, name, seconds=None, appid=None, source="folders", tool=None, how="search"):
        cur = self.c.execute(
            "INSERT INTO game (identity_key, source, known_as, name_origin, steam_appid, appid_source, is_tool, "
            "playtime_seconds, first_seen) VALUES (?, ?, ?, 'scan', ?, ?, ?, ?, ?)",
            (key, source, name, appid, how if appid else None, tool, seconds, NOW))
        return cur.lastrowid

    def install(self, game_id, kind="exe", size=10**9, store_last_played=None):
        if self.scan is None:
            self.scan = self.c.execute("INSERT INTO scan (finished_at, entry_count, trigger) VALUES (?, 0, 'manual')",
                                       (NOW,)).lastrowid
        position = self.c.execute("SELECT COUNT(*) FROM install").fetchone()[0]
        self.c.execute("INSERT INTO install (game_id, position, display_name, install_dir, launch_kind, launch_target, "
                       "working_dir, icon_hint, size_on_disk, detection, store_last_played, scan_id) "
                       "VALUES (?, ?, 'x', ?, ?, 'x', 'x', 'x', ?, 'heuristic', ?, ?)",
                       (game_id, position, f"C:\\made\\{game_id}", kind, size, store_last_played, self.scan))

    def session(self, game_id, started, minutes):
        self.c.execute("INSERT INTO session (game_id, started_at, minutes) VALUES (?, ?, ?)", (game_id, started, minutes))

    def price(self, appid, observed, final, initial=None, discount=0, kind="priced"):
        if kind == "priced":
            self.c.execute("INSERT INTO price_snapshot (appid, observed_at, kind, currency, initial_cents, final_cents, "
                           "discount_percent) VALUES (?, ?, 'priced', 'EUR', ?, ?, ?)",
                           (appid, observed, initial if initial is not None else final, final, discount))
        else:
            self.c.execute("INSERT INTO price_snapshot (appid, observed_at, kind) VALUES (?, ?, ?)", (appid, observed, kind))

    def built(self):
        return {r.key: r for r in reports.build(self.store.reports())}


def by_key(rows, key="appid"):
    return {r[key]: r for r in rows}


print("=== 1. schema version 5 on a copy of the real library ===")
try:
    raw = sqlite3.connect(DATABASE, isolation_level=None)
    if library_db.schema_version(raw) >= 5:  # the user's own start already upgraded it: undo 5 and later in the copy
        test_sandbox.undo_upgrades(raw, 4)
    before_rows = rows_hash(raw)
    before_apps = {r[0] for r in raw.execute("SELECT appid FROM steam_app")}
    before_prices = set(raw.execute("SELECT * FROM price_snapshot"))
    before_meta = raw.execute("SELECT id, created_at, migrated_from, migrated_at FROM meta").fetchall()
    raw.close()
    snapshots_before = {p.name for p in (SANDBOX / "backups").glob("*")} if (SANDBOX / "backups").is_dir() else set()
    started = time.time()
    store = migration.open_library()
    check(f"the copy opens at version {library_db.SCHEMA_VERSION}", store.version == library_db.SCHEMA_VERSION >= 5,
          store.version)
    store.close()
    raw = sqlite3.connect(DATABASE, isolation_level=None)
    held = []
    for folder in (SANDBOX / "backups").glob("*") if (SANDBOX / "backups").is_dir() else []:
        copy = folder / "library.db"
        if folder.name not in snapshots_before and copy.is_file():
            snap = sqlite3.connect(f"file:{copy.as_posix()}?mode=ro", uri=True)
            held.append(library_db.schema_version(snap))
            snap.close()
    check("a snapshot first, holding the library as it was at version 4", 4 in held, held)
    after_rows = rows_hash(raw)  # a later version's tables, dropped to go back to 4, come back empty (Phase 86)
    check("every row of the user's tables as it was", set(before_rows) <= set(after_rows)
          and {t: after_rows[t] for t in before_rows} == before_rows)
    check("the Steam tables keep every app and every price they had",
          before_apps <= {r[0] for r in raw.execute("SELECT appid FROM steam_app")}
          and before_prices <= set(raw.execute("SELECT * FROM price_snapshot")))
    check("meta: only the version moved", raw.execute("SELECT id, created_at, migrated_from, migrated_at FROM meta")
          .fetchall() == before_meta
          and raw.execute("SELECT schema_version FROM meta").fetchone()[0] == library_db.SCHEMA_VERSION)
    fresh_path = WORK / "fresh.db"
    fresh = library_db.connect(fresh_path)
    library_db.create(fresh)
    check("a fresh database and the upgraded copy have the same schema", schema_of(fresh) == schema_of(raw),
          set(schema_of(fresh)) ^ set(schema_of(raw)))
    added = {n for t, n, _s in schema_of(raw) if t == "view"} - {"v_library", "v_playtime_check", "v_price_latest",
                                                                  "v_price_range", "v_game_money", "v_steam_time_latest",
                                                                  "v_steam_time_mine"}
    check("the views added are v_hours and, since Phase 86, v_wishlist_now", added == {"v_hours", "v_wishlist_now"},
          added)
    fresh.close()
    raw.close()
except Exception as exc:
    unreached("1", exc)

print("\n=== 2. v_hours: every hour once ===")
try:
    m = Made("hours")
    m.account(1, 1)
    m.account(2, 0)  # not mine: its time counts nowhere
    m.app(1001, "Shared Game", genres=((1, "Action"), (3, "RPG")), publisher="Pub A", developer="Dev A",
          release="2015-05-01")
    m.app(1002, "Big Game", genres=((1, "Action"), (37, "Free To Play")), publisher="Pub B", developer="Dev B",
          release="2008-01-01")
    m.app(1003, "Demo App", kind="demo")
    m.app(1005, record=False)
    m.app(480, record=False)
    m.steam(1, 1001, 120)
    m.steam(2, 1001, 999)
    m.steam(1, 1002, 600)
    m.steam(1, 1003, 50)
    m.steam(1, 1005, 40)
    m.steam(1, 480, 5000)
    one = m.game("c:\\made\\shared", "Shared Game", 3600, 1001)
    two = m.game("c:\\made\\shared copy", "Shared Game Copy", 1800, 1001)
    folder = m.game("c:\\made\\folder", "Folder Only", 600)
    tool = m.game("c:\\made\\tool", "A Tool", 6000, tool=1)
    hours = m.c.execute("SELECT * FROM v_hours").fetchall()
    names = [d[0] for d in m.c.execute("SELECT * FROM v_hours").description]
    rows = [dict(zip(names, r)) for r in hours]
    apps = by_key([r for r in rows if r["appid"] is not None])
    games = by_key([r for r in rows if r["appid"] is None], "game_id")
    check("one row per app, one per game with no app", sorted(apps) == [480, 1001, 1002, 1003, 1005]
          and sorted(games) == [folder, tool], (sorted(apps), sorted(games)))
    shared = apps[1001]
    check("two games on one app: the launcher's 60 + 30 minutes added, Steam's 120 once, never the other account's",
          (shared["minutes_launcher"], shared["minutes_steam"], shared["minutes"], shared["games"], shared["source"])
          == (90.0, 120, 210.0, 2, "both"), shared)
    check("Steam's minutes in v_hours add up to the marked accounts' total, exactly",
          sum(r["minutes_steam"] or 0 for r in rows) == m.c.execute("SELECT SUM(minutes) FROM v_steam_time_mine").fetchone()[0])
    check("the launcher's minutes add up to every game's playtime, exactly",
          sum(r["minutes_launcher"] or 0 for r in rows) * 60 == m.c.execute("SELECT SUM(playtime_seconds) FROM game").fetchone()[0])
    check("Steam only, launcher only, and the user's tool mark carried",
          apps[1002]["source"] == "steam" and games[folder]["source"] == "launcher" and games[tool]["marked_tool"] == 1)
except Exception as exc:
    unreached("2", exc)

print("\n=== 3. the seven reports on made-up data ===")
try:
    check("Gini: equal shares give 0", abs(reports.gini([5, 5, 5, 5])) < 1e-12, reports.gini([5, 5, 5, 5]))
    for n in (2, 4, 10):
        check(f"Gini: one of {n} with everything gives (n - 1)/n", abs(reports.gini([7] + [0] * (n - 1)) - (n - 1) / n) < 1e-12)

    def by_definition(xs):  # half the relative mean absolute difference
        mean = sum(xs) / len(xs)
        return sum(abs(a - b) for a in xs for b in xs) / (2 * len(xs) ** 2 * mean)

    sample = [10, 40, 210, 600, 3, 77]
    check("Gini: the sorted-sum formula equals the definition", abs(reports.gini(sample) - by_definition(sample)) < 1e-12)
    curve = reports.lorenz([1, 1, 2])
    check("the Lorenz curve runs from (0, 0) to (1, 1) under the diagonal",
          curve[0] == (0.0, 0.0) and curve[-1] == (1.0, 1.0) and all(y <= x + 1e-12 for x, y in curve))

    built = m.built()
    rows = m.store.reports().rows("concentration")
    check("concentration: the games only -- not Spacewar, not the demo, not the tool",
          [r["name"] for r in rows] == ["Big Game", "Shared Game", "app 1005", "Folder Only"], [r["name"] for r in rows])
    total = 600 + 210 + 40 + 10
    check("its shares and running sums", [round(r["cumulative"], 6) for r in rows]
          == [round(x / total, 6) for x in (600, 810, 850, 860)])
    con = built["concentration"]
    figures = dict(con.parts[1].data)
    check("half the hours in 1 game, 80% in 2, the Gini of the four",
          (figures["games_to_half"], figures["games_to_80"]) == (1, 2)
          and abs(figures["gini"] - round(by_definition([600, 210, 40, 10]), 4)) < 1e-9, figures)

    pro = built["profiles"]
    cover = m.store.reports().one("profile_coverage")
    check("profiles: the played hours, the hours with a genre, Free To Play's",
          (cover["played"], cover["with_genre"], cover["free_to_play"]) == (860.0, 810.0, 600), cover)
    genres = {r["label"]: r["minutes"] for r in m.store.reports().rows("profile_genres")}
    check("a game with two genres counts in both; Free To Play is not among the genres",
          genres == {"Action": 810.0, "RPG": 210.0}, genres)
    check("so the genres' shares add up to more than 100%", sum(genres.values()) / cover["with_genre"] > 1)
    check("Free To Play has its own line, as a share of all the hours",
          any(p.heading == "Free to play" and "70%" in p.note for p in pro.parts), [p.note for p in pro.parts])
    check("the coverage line says how much has a genre", "810" not in pro.sentence and "of 14 hours" in pro.sentence,
          pro.sentence)
    # Both roles come from one run since Phase 98, each row saying which it is.
    publishers = {r["label"]: r["minutes"] for r in m.store.reports().rows("profile_companies") if r["role"] == "publisher"}
    decades = {r["label"]: r["minutes"] for r in m.store.reports().rows("profile_decades")}
    check("publishers and release decades", publishers == {"Pub B": 600, "Pub A": 210.0}
          and decades == {"2000s": 600, "2010s": 210.0}, (publishers, decades))

    quality = built["quality"]
    aside = m.store.reports().rows("quality_set_aside")
    check("Spacewar's 5,000 minutes are set aside, and shown in the data-quality report",
          [(r["appid"], r["minutes"]) for r in aside] == [(480, 5000)]
          and any("Spacewar" in str(row) for p in quality.parts for row in p.rows))
    kinds = {r["kind"]: r["minutes"] for r in m.store.reports().rows("quality_types")}
    check("the demo and the tool are in the data-quality report, apart", kinds.get("demo") == 50
          and kinds.get("tool (no Steam app)") == 100.0 and kinds.get("unknown (no store record)") == 40, kinds)
    links = m.store.reports().rows("quality_links")
    check("the game with time from both sources, and how it was linked",
          [(r["name"], r["games"], r["linked_by"]) for r in links] == [("Shared Game", 2, "search")], links)

    b = Made("abandon")
    b.account(1, 1)
    for appid, minutes in zip(range(2001, 2007), (5, 30, 90, 300, 3000, 7000)):
        b.app(appid, f"Game {appid}")
        b.steam(1, appid, minutes)
    b.app(2007, "Started once")
    b.steam(1, 2007, None, last="2026-09-01T20:00:00+03:00")
    b.app(2008, "A demo", kind="demo")
    b.steam(1, 2008, 5)
    b.app(480, record=False)
    b.steam(1, 480, 5)
    buckets = {r["bucket"]: r["apps"] for r in b.store.reports().rows("abandonment")}
    check("abandonment: the six buckets, a game with a start and no minutes under ten minutes, no demo, no Spacewar",
          buckets == {1: 2, 2: 1, 3: 1, 4: 1, 5: 1, 6: 1}, buckets)
    sentence = b.built()["abandonment"].sentence
    # Since Phase 91 the sentence counts paid games on their own; every app here has a record and no free mark.
    check("4 of the 7 paid games under the refund window, said so",
          "Of the 7 paid games started on Steam, 4 (57%) stayed under two hours" in sentence, sentence)

    s = Made("sessions")
    played = s.game("c:\\made\\played", "Played Game", 3600)
    tool_game = s.game("c:\\made\\toolgame", "A Tool", 6000, tool=1)
    s.session(played, "2026-08-14T05:53:32+03:00", 10)   # summer time: 02 by strftime, 05 on the clock
    s.session(played, "2026-11-03T21:15:00+02:00", 9)    # winter time: 19 by strftime, 21 on the clock
    for day, minutes in zip(range(1, 9), range(1, 9)):
        s.session(played, f"2026-09-0{day}T12:00:00+03:00", minutes)
    s.session(tool_game, "2026-09-10T03:00:00+03:00", 100)
    summary = s.store.reports().one("session_summary")
    check("sessions: 10, the median 5.5, the mean 5.5, the 90th percentile 9 -- the tool's left out",
          (summary["sessions"], summary["median"], summary["mean"], summary["p90"]) == (10, 5.5, 5.5, 9), summary)
    hours = {r["hour"]: r["minutes"] for r in s.store.reports().rows("session_hours")}
    utc = {row[0]: row[1] for row in s.c.execute(
        "SELECT minutes, CAST(strftime('%H', started_at) AS INTEGER) FROM session WHERE minutes IN (9, 10)")}
    check("the local hour of a summer and a winter session, 5 and 21 -- where strftime says 2 and 19",
          hours.get(5) == 10 and hours.get(21) == 9 and utc == {10: 2, 9: 19}, (hours, utc))
    weekdays = {r["weekday"]: r["minutes"] for r in s.store.reports().rows("session_weekdays")}
    expected_days = {}
    for started, minutes in [("2026-08-14", 10), ("2026-11-03", 9)] + [(f"2026-09-0{d}", d) for d in range(1, 9)]:
        wd = (date.fromisoformat(started).weekday() + 1) % 7
        expected_days[wd] = expected_days.get(wd, 0) + minutes
    check("the weekdays, from the date on the clock", weekdays == expected_days, (weekdays, expected_days))
    check("the night's share: 10 of 55 minutes began before six", "18% of the minutes" in s.built()["sessions"].sentence,
          s.built()["sessions"].sentence)

    k = Made("backlog")
    for appid in (3001, 3002, 3003, 3005):
        k.app(appid, f"App {appid}")
    never = k.game("c:\\made\\never", "Never Game", None, 3001)
    short = k.game("c:\\made\\short", "Short Game", 1800, 3002)
    long_ = k.game("c:\\made\\long", "Long Game", 36000, 3003)
    xbox = k.game("xbox:made", "Xbox Game", None, source="xbox")
    steam_unplayed = k.game("steam:3005", "Steam Unplayed", None, 3005, source="steam", how="manifest")
    tool = k.game("c:\\made\\tool", "A Tool", None, tool=1)
    for game_id, kind in ((never, "exe"), (short, "exe"), (long_, "exe"), (xbox, "uri"), (steam_unplayed, "uri"),
                          (tool, "exe")):
        k.install(game_id, kind)
    k.price(3001, "2026-10-10T00:00:00+00:00", 1999)
    k.price(3002, "2026-10-10T00:00:00+00:00", 999)
    k.price(3003, "2026-09-01T00:00:00+00:00", 1499, 2999, 50)
    k.price(3003, "2026-10-10T00:00:00+00:00", 2999, 5998, 50)
    k.price(3005, "2026-10-10T00:00:00+00:00", None, kind="free")
    k.c.execute("INSERT INTO purchase (game_id, paid_cents, store, recorded_at) VALUES (?, 500, 'Steam', ?)", (short, NOW))
    states = {r["name"]: r["state"] for r in k.store.reports().rows("backlog")}
    check("backlog: never played, under two hours, played, cannot tell -- and no tool",
          states == {"Never Game": "never", "Short Game": "under", "Long Game": "played", "Xbox Game": "unknown",
                     "Steam Unplayed": "never"}, states)
    lib = k.store.reports().one("money_library")
    # Phase 91: list_cents is the price before any discount, today_cents today's (App 3003 at -50%).
    check("money: 5 installed, 4 Steam titles, 3 priced, 1 free, 89,96 EUR at list price, 59,97 EUR today, 1 on sale",
          (lib["games"], lib["titles"], lib["priced"], lib["free"], lib["list_cents"], lib["today_cents"],
           lib["on_sale"]) == (5, 4, 3, 1, 8996, 5997, 1), lib)
    paid = k.store.reports().rows("money_paid")
    check("10,00 EUR an hour for 5,00 EUR over 30 minutes",
          [(r["name"], round(r["cents_per_hour"])) for r in paid] == [("Short Game", 1000)], paid)
    proxy = k.store.reports().rows("money_proxy")
    check("the list price per hour only where nothing was paid and the game was played an hour or more "
          "(the list price since Phase 91: 59,98 EUR over 10 hours)",
          [(r["name"], round(r["cents_per_hour"], 1)) for r in proxy] == [("App 3003", 599.8)], proxy)
    sales = k.store.reports().rows("money_sales")
    lowest = k.store.reports().rows("money_lowest")
    check("on sale today, and seen cheaper than today",
          [(r["name"], r["discount_percent"], r["installed"]) for r in sales] == [("App 3003", 50, 1)]
          and [(r["name"], r["now_cents"], r["lowest_cents"]) for r in lowest if r["lowest_cents"] < r["now_cents"]]
          == [("Long Game", 2999, 1499)], (sales, lowest))
    made = k.built()
    check("the backlog's sentence: 2 never played, worth 19,99 EUR, 1 under two hours",
          made["backlog"].sentence.startswith("2 installed games have never been played anywhere")
          and "19,99" in made["backlog"].sentence and "1 more was played under two hours" in made["backlog"].sentence,
          made["backlog"].sentence)
    untimed = k.store.reports().rows("quality_untimed")
    check("the installed games no source times: the Xbox one, and the Steam one no marked account holds",
          sorted(r["name"] for r in untimed) == ["Steam Unplayed", "Xbox Game"], untimed)

    before = fingerprint(m.path)
    m.built()
    check("nothing is written by any report", fingerprint(m.path) == before)
    check("and the store still writes afterwards (query_only was put back)",
          m.c.execute("UPDATE game SET favorite = 1 WHERE id = ?", (folder,)).rowcount == 1)

    empty = Made("empty")
    nothing = empty.built()
    check("an empty library: every report (eight since Phase 89, nine since 98, ten since 102, eleven since 103), "
          "each saying so in words",
          len(nothing) == len(reports.BUILDERS) == 11 and all(r.empty and r.sentence for r in nothing.values()), [r.key for r in nothing.values()])
    for made_store in (m, b, s, k, empty):
        made_store.store.close()
except Exception as exc:
    unreached("3", exc)

print("\n=== 4. the Stats page as the oracle ===")
window = None
try:
    from presentation import ui_window
    window = ui_window.MainWindow()
    settle(0.3)
    oracle = stats.gather(window.views, window.overrides)
    source = window.overrides.reports()
    check("the window's library answers the reports", source is not None)
    life = source.one("stats_lifetime")
    check(f"lifetime time timed here: {oracle.lifetime_seconds} s both ways", life["seconds"] == oracle.lifetime_seconds,
          (life, oracle.lifetime_seconds))
    top = source.rows("stats_top")
    check("most played: the same games and seconds, in order",
          [(r["name"], r["seconds"]) for r in top] == [(t.label, t.value) for t in oracle.top_games],
          ([(r["name"], r["seconds"]) for r in top], oracle.top_games))
    months = {(r["year"], r["month"]): r["minutes"] for r in source.rows("stats_months")}
    chart = {(m_.year, m_.month): m_.minutes for m_ in oracle.months if m_.minutes}
    check(f"the months: {len(chart)} with time, the same minutes each", months == chart, (months, chart))
    sources = sorted((rules.SOURCE_LABELS.get(r["source"], r["source"]), r["games"]) for r in source.rows("stats_sources"))
    check("where they came from: the same counts", sources == sorted((t.label, t.value) for t in oracle.sources),
          (sources, oracle.sources))
    timings = []
    for _ in range(3):
        started = time.perf_counter()
        built_real = reports.build(source)
        timings.append(1000 * (time.perf_counter() - started))
    check(f"all of them (eleven since Phase 103) on this library in {min(timings):.0f} ms (best of 3), under 50",
          min(timings) < 50, timings)
    slow = []
    for name in queries.QUERIES:
        started = time.perf_counter()
        source.rows(name, **({"role": "publisher"} if name == "profile_companies" else {}))
        slow.append((1000 * (time.perf_counter() - started), name))
    print("      slowest queries: " + ", ".join(f"{n} {ms:.1f} ms" for ms, n in sorted(slow, reverse=True)[:3]))
    wished = window.overrides._conn.execute(
        "SELECT COUNT(*) FROM wishlist w JOIN steam_account a ON a.account_id = w.account_id "
        "WHERE a.is_mine = 1 AND w.removed_at IS NULL").fetchone()[0]
    rated = window.overrides._conn.execute("SELECT COUNT(*) FROM rating").fetchone()[0]
    marked = window.overrides._conn.execute(
        "SELECT COUNT(*) FROM game WHERE status IS NOT NULL AND COALESCE(is_tool, 0) = 0").fetchone()[0]
    # The copy went back to version 4 in section 1 and came up again: its wishlist starts empty, and
    # the eighth report (Phase 89) says so -- empty exactly when no list is there; the tenth (Phase 102)
    # exactly when nothing is rated; the eleventh (Phase 103) when nothing is marked.
    check(f"eleven reports (since Phase 103), the first seven and the ninth none empty on the real library; the eighth "
          f"{'empty, with no wishlist in the copy' if not wished else 'answering ' + str(wished) + ' wished games'}; "
          f"the tenth {'empty, nothing rated yet' if not rated else 'answering ' + str(rated) + ' ratings'}; "
          f"the eleventh {'empty, nothing marked' if not marked else 'answering ' + str(marked) + ' marks'}",
          len(built_real) == 11 and not any(r.empty for r in built_real[:7]) and built_real[7].empty == (not wished)
          and not built_real[8].empty and built_real[9].empty == (not rated) and built_real[10].empty == (not marked),
          [r.key for r in built_real if r.empty])
    while window.worker is not None and window.worker.isRunning():
        settle(0.2)
    window.close()
    settle(0.3)
    window.overrides.close()
except Exception as exc:
    unreached("4", exc)

print("\n=== 5. reports.py ===")
try:
    before = fingerprint(DATABASE)
    run = lambda *args: subprocess.run([sys.executable, str(PROJECT / "reports.py"), *args], capture_output=True,
                                       text=True, encoding="utf-8", errors="replace", cwd=PROJECT)
    out = run("--markdown", "--library", str(DATABASE))
    check("--markdown: every report, with the day", out.returncode == 0
          and all(f"## {n}." in out.stdout for n in range(1, 9)) and f"Made on {date.today():%Y-%m-%d}" in out.stdout,
          (out.returncode, out.stderr[-300:]))
    with_sql = run("--markdown", "--sql", "--library", str(DATABASE))
    check("--sql: each report followed by its SQL, as the code has it",
          with_sql.returncode == 0 and queries.CONCENTRATION in with_sql.stdout and queries.QUALITY_TYPES in with_sql.stdout)
    folder = WORK / "csv"
    written = run("--csv", str(folder), "--library", str(DATABASE))
    files = sorted(p.name for p in folder.glob("*.csv"))
    first = (folder / "1-concentration.csv").read_bytes() if (folder / "1-concentration.csv").is_file() else b""
    check("--csv: one file per report, for Excel in Romanian (a byte-order mark, semicolons, decimal commas)",
          written.returncode == 0 and len(files) == len(reports.BUILDERS) and first.startswith(b"\xef\xbb\xbf") and b";" in first
          and re.search(rb"0,\d", first) is not None, (files, first[:80]))
    check("nothing written to the library by the command", fingerprint(DATABASE) == before)
    old = WORK / "old.db"
    src = sqlite3.connect(f"file:{DATABASE.as_posix()}?mode=ro", uri=True)
    dst = sqlite3.connect(old, isolation_level=None)
    src.backup(dst)
    src.close()
    dst.execute("DROP VIEW v_hours")
    dst.execute("PRAGMA user_version = 4")
    dst.close()
    refused = run("--markdown", "--library", str(old))
    check("a version-4 file is refused, with what to do", refused.returncode == 1
          and "start the launcher once" in refused.stderr, refused.stderr)
    missing = WORK / "not-there.db"
    gone = run("--markdown", "--library", str(missing))
    check("a missing file is refused and not created", gone.returncode == 1 and not missing.exists(), gone.stderr)
    check("with nothing asked, the help, and 2", run().returncode == 2)
except Exception as exc:
    unreached("5", exc)

print("\n=== 6. the friends' comparison sets Spacewar and the SDK aside too ===")
try:
    def export(code, history):
        return {"format": rules.ANALYSIS_FORMAT, "version": 1, "participant": code, "made_on": "2026-10-14",
                "games": [], "steam": {"history": history, "accounts": [{"label": "A"}]},
                "sessions": {"count": 0, "minutes": 0, "by_hour": {}, "by_weekday": {}}}
    one = comparison._measure("P1", "a.json", export("p-1", [{"steam_appid": 480, "minutes": 5000},
                                                             {"steam_appid": 218, "minutes": 300},
                                                             {"steam_appid": 730, "minutes": 100, "name": "CS"}]))
    two = comparison._measure("P2", "b.json", export("p-2", [{"steam_appid": 480, "minutes": 50},
                                                             {"steam_appid": 730, "minutes": 10, "name": "CS"}]))
    check("their minutes are not Steam's in a participant's figures, and kept apart",
          (one.steam_minutes, one.set_aside_minutes, one.steam_apps_played) == (100, 5300, 1), vars(one).get("steam_minutes"))
    check("nor do they make two people alike, or a game in common", one.played == {730} and two.played == {730}
          and [g["steam_appid"] for g in comparison.common_games([one, two])] == [730])
    line = comparison_report._set_aside_line([one, two])
    check("the page says what was left out, for whom", "Spacewar" in line and "P1 88,3 ore" in line
          and "P2 0,8 ore" in line, line)
except Exception as exc:
    unreached("6", exc)

print("\n=== 7. the document, the layers ===")
try:
    analysis = (PROJECT / "docs" / "ANALIZA.md").read_text(encoding="utf-8")
    quoted = dict(re.findall(r"```sql\n-- (\w+)\n(.*?)\n```", analysis, re.S))
    wanted = {n for n in queries.QUERIES if not n.startswith("stats_") or n == "stats_lifetime"}
    check(f"docs/ANALIZA.md quotes {len(quoted)} queries, each exactly as the code has it",
          quoted and all(queries.QUERIES.get(n) == sql for n, sql in quoted.items()),
          [n for n, sql in quoted.items() if queries.QUERIES.get(n) != sql])
    check("and every query a report is built from", wanted <= set(quoted), wanted - set(quoted))
    check("BAZA_DE_DATE points to it", "ANALIZA.md" in (PROJECT / "docs" / "BAZA_DE_DATE.md").read_text(encoding="utf-8"))
    claude = (PROJECT / "CLAUDE.md").read_text(encoding="utf-8")
    check("CLAUDE.md has the phase and its notes", "| 83 |" in claude and "## Phase 83 notes" in build_log())
    layers = subprocess.run([sys.executable, str(PROJECT / "tests" / "check_layers.py")], capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    check("no import points up a layer; sqlite3 only in data_access/", layers.returncode == 0, layers.stdout[-300:])
    check("nothing in this suite reached the network", attempts == [], attempts)
except Exception as exc:
    unreached("7", exc)

print("\n=== 8. the real library is exactly as it was found ===")
changed = box.finish()
check("config.json and the library database are unchanged", not changed, changed)
import shutil
shutil.rmtree(WORK, ignore_errors=True)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
