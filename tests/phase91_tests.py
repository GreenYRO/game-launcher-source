"""Phase 91: three corrections to the analysis; the build log out of CLAUDE.md; the feature freeze.

  1. report 2 on a made-up library: each started app's kind (free by the flag, by the genre, or
     both; paid, games no longer sold among them; no store record), under and over two hours; the
     counts per bucket and kind worked out by hand; the sentence on paid games only, the others
     counted apart; the table by kind; the caveat and the idea's words; no paid game at all;
  2. report 8's games played on suite 89's made-up library worked out by hand (a game with no
     minutes and one whose only genre is Free To Play left out), the three lists of bars in one
     order, the one gap, the CSV's columns; on the real copy, the counts equal to report 3's and to
     a direct count;
  3. report 6 and report 4: the library's list price and today's cost, with a planted sale (both
     figures, and the titles on sale) and with none (one figure); the backlog's two values in both
     reports; the stand-in per hour on the list price;
  4. nothing written and query_only put back; reports.py's Markdown and CSV; docs/ANALIZA.md
     quoting the code and carrying the day's answers and the ideas; the eight reports under 50 ms;
  5. the build log: ISTORIC holding every section the old CLAUDE.md moved, word for word and in order;
     CLAUDE.md holding no phase notes, its nine sections and the lessons; .gitattributes; the freeze
     paragraph and row 91; the friends' documents untouched;
  6. the layers; nothing reached the network; the real library exactly as it was found.

On a throwaway copy of the data; the network is blocked.
"""
import csv
import hashlib
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import test_sandbox

box = test_sandbox.start()
attempts: list[str] = []


def no_network(request, *args, **kwargs):
    attempts.append(getattr(request, "full_url", str(request)))
    raise OSError("the network is blocked in this suite")


urllib.request.urlopen = no_network

from data_access import library_db
from data_access import reports as queries
from logic import reports
from shared import rules

WORK = Path(tempfile.mkdtemp(prefix="phase91_"))
NOW = "2026-10-16T12:00:00+00:00"
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


def fingerprint(path) -> str:
    conn = sqlite3.connect(f"file:{Path(path).resolve().as_posix()}?mode=ro", uri=True)
    try:
        return hashlib.sha256("\n".join(conn.iterdump()).encode()).hexdigest()
    finally:
        conn.close()


class Made:
    """A fresh library with rows put in by hand -- tests may write SQL on a scratch file."""

    def __init__(self, name: str) -> None:
        self.path = WORK / f"{name}.db"
        self.store = library_db.LibraryStore(self.path)
        self.c = self.store._conn
        self.scan = None

    def app(self, appid, name=None, kind="game", record=True, genres=(), free=None):
        self.c.execute("INSERT INTO steam_app (appid, has_record, name, app_type, is_free) VALUES (?, ?, ?, ?, ?)",
                       (appid, int(record), name if record else None, kind if record else None,
                        free if record else None))
        for genre_id, genre_name in genres:
            self.c.execute("INSERT OR IGNORE INTO genre (id, name) VALUES (?, ?)", (genre_id, genre_name))
            self.c.execute("INSERT INTO steam_app_genre (appid, genre_id) VALUES (?, ?)", (appid, genre_id))

    def account(self, account_id, mine):
        self.c.execute("INSERT INTO steam_account (account_id, steam_id64, is_mine, first_seen, last_seen) "
                       "VALUES (?, ?, ?, ?, ?)", (account_id, account_id + 76561197960265728, mine, NOW, NOW))
        self.c.execute("INSERT INTO steam_read (account_id, read_at, file_modified, apps_in_file, apps_with_time) "
                       "VALUES (?, ?, ?, 0, 0)", (account_id, NOW, NOW))

    def steam(self, account_id, appid, minutes, last=None):
        self.c.execute("INSERT INTO steam_playtime (account_id, appid, observed_at, minutes_total, last_played) "
                       "VALUES (?, ?, ?, ?, ?)", (account_id, appid, NOW, minutes, last))

    def game(self, key, name, seconds=None, appid=None, source="folders"):
        cur = self.c.execute(
            "INSERT INTO game (identity_key, source, known_as, name_origin, steam_appid, appid_source, "
            "playtime_seconds, first_seen) VALUES (?, ?, ?, 'scan', ?, ?, ?, ?)",
            (key, source, name, appid, "search" if appid else None, seconds, NOW))
        return cur.lastrowid

    def install(self, game_id, kind="exe", size=10**9):
        if self.scan is None:
            self.scan = self.c.execute("INSERT INTO scan (finished_at, entry_count, trigger) VALUES (?, 0, 'manual')",
                                       (NOW,)).lastrowid
        position = self.c.execute("SELECT COUNT(*) FROM install").fetchone()[0]
        self.c.execute("INSERT INTO install (game_id, position, display_name, install_dir, launch_kind, launch_target, "
                       "working_dir, icon_hint, size_on_disk, detection, scan_id) "
                       "VALUES (?, ?, 'x', ?, ?, 'x', 'x', 'x', ?, 'heuristic', ?)",
                       (game_id, position, f"C:\\made\\{game_id}", kind, size, self.scan))

    def price(self, appid, final, initial=None, kind="priced"):
        if kind == "priced":
            initial = final if initial is None else initial
            discount = round(100 * (initial - final) / initial) if initial else 0
            self.c.execute("INSERT INTO price_snapshot (appid, observed_at, kind, currency, initial_cents, final_cents, "
                           "discount_percent) VALUES (?, ?, 'priced', 'EUR', ?, ?, ?)",
                           (appid, NOW, initial, final, discount))
        else:
            self.c.execute("INSERT INTO price_snapshot (appid, observed_at, kind) VALUES (?, ?, ?)", (appid, NOW, kind))

    def built(self):
        return {r.key: r for r in reports.build(self.store.reports())}


ACTION, STRATEGY, PUZZLE, F2P = (1, "Action"), (2, "Strategy"), (3, "Puzzle"), (37, "Free To Play")

print("=== 1. report 2: each started app's kind ===")
try:
    k = Made("kinds")
    k.account(1, 1)
    # appid, minutes, how it is made: the kind each must come out as
    plan = [(5001, 30, dict(), "paid"), (5002, 300, dict(), "paid"),
            (5003, 5, dict(free=1), "free"), (5004, 700, dict(free=1), "free"),            # the flag
            (5005, 50, dict(genres=(F2P,)), "free"), (5006, 7000, dict(genres=(F2P,)), "free"),  # the genre
            (5012, 20, dict(free=1, genres=(F2P, ACTION)), "free"),                          # both: counted once
            (5007, 90, dict(record=False), "unknown"), (5008, 200, dict(record=False), "unknown"),
            (5009, 100, dict(), "paid"), (5010, 130, dict(), "paid")]                        # 5009-10 no longer sold
    for appid, minutes, how, _kind in plan:
        k.app(appid, f"App {appid}", **how)
        k.steam(1, appid, minutes)
    k.price(5009, None, kind="unavailable")
    k.price(5010, None, kind="unavailable")
    k.app(5050, "A demo", kind="demo")
    k.steam(1, 5050, 5)
    k.app(480, record=False)  # Spacewar, set aside
    k.steam(1, 480, 5)
    rows = {r["bucket"]: r for r in k.store.reports().rows("abandonment")}
    got = {b: (r["apps"], r["paid"], r["free"], r["unknown"]) for b, r in rows.items()}
    # under 10: 5003 free | 10-60: 5001 paid, 5005 free, 5012 free | 60-120: 5007 unknown, 5009 paid
    # 120-600: 5002 paid, 5008 unknown, 5010 paid | 600-6000: 5004 free | 6000+: 5006 free
    want = {1: (1, 0, 1, 0), 2: (3, 1, 2, 0), 3: (2, 1, 0, 1), 4: (3, 2, 0, 1), 5: (1, 0, 1, 0), 6: (1, 0, 1, 0)}
    check("by hand: every bucket's games by kind -- the flag, the genre and both each free once, no record unknown, "
          "no longer sold paid, no demo, no Spacewar", got == want, got)
    report = k.built()["abandonment"]
    check("the sentence on paid games only, the others counted apart",
          report.sentence == "Of the 4 paid games started on Steam, 2 (50%) stayed under two hours, Steam's refund "
                             "window; another 3 free-to-play titles and 1 app with no store record were also left "
                             "under two hours and are counted apart.", report.sentence)
    by_kind = next(p for p in report.parts if p.heading == "Under two hours, by kind")
    check("the table by kind: the refund window's three buckets, under and over two hours, each kind's own share",
          [tuple(r) for r in by_kind.rows] == [("Paid", "0", "1", "1", "2 (50%)", "2"),
                                               ("Free to play", "1", "2", "0", "3 (60%)", "2"),
                                               ("No store record", "0", "0", "1", "1 (50%)", "1")], by_kind.rows)
    bars = next(p for p in report.parts if p.heading == "Games by Steam time")
    check("the bars stay on all games", [b.label.split(" (")[0] for b in bars.bars][:1] == ["Under 10 minutes"]
          and [b.value.split(" ")[0] for b in bars.bars] == ["1", "3", "2", "3", "1", "1"], [b.value for b in bars.bars])
    six = next(p for p in report.parts if p.heading == "By time played")
    check("the six buckets' table (the CSV's) gains paid, free and no record",
          six.columns[-3:] == ("Paid", "Free", "No record") and [r[-3:] for r in six.data]
          == [w[1:] for _b, w in sorted(want.items())], six.data)
    check("the caveat: the window is a threshold of time, no purchase date",
          "threshold of time only" in report.caveat and "no purchase date" in report.caveat, report.caveat)
    check("the idea: the confounding variable, the business model, report 3",
          "Confounding variable" in report.concept and "business model" in report.concept
          and "report 3" in report.concept, report.concept)
    check("rules.py names the three kinds", list(rules.REPORT_APP_KINDS) == ["paid", "free", "unknown"])
    k.store.close()

    f = Made("free only")
    f.account(1, 1)
    f.app(6001, "Free A", free=1)
    f.steam(1, 6001, 30)
    f.app(6002, "Unknown B", record=False)
    f.steam(1, 6002, 300)
    sentence = f.built()["abandonment"].sentence
    check("no paid game started: said so, the others still counted",
          sentence.startswith("No paid game has been started on Steam; 2 games started, 1 of them under two hours"),
          sentence)
    f.store.close()
except Exception as exc:
    unreached("1", exc)

print("\n=== 2. report 8: the games played ===")
try:
    m = Made("report8")
    m.account(1001, 1)
    m.account(1003, 0)
    m.app(900, "Played A", genres=(ACTION, STRATEGY))
    m.app(901, "Played B", genres=(ACTION,))
    m.app(902, "Played C", genres=(PUZZLE,))
    m.app(903, "Never played", genres=(ACTION,))      # no minutes: not played
    m.app(904, "Free To Play only", genres=(F2P,))    # its only genre is not one: out of the count
    for key, appid, minutes in (("a", 900, 600), ("b", 901, 300), ("c", 902, 100), ("d", 903, 0), ("e", 904, 50)):
        m.game(f"c:/games/{key}", f"Game {key}", minutes * 60, appid)
    m.app(10, "Ten", genres=(ACTION, STRATEGY, F2P))
    m.app(20, "Twenty", genres=(PUZZLE,))
    m.app(22, "Twenty-two", genres=(PUZZLE, STRATEGY))
    m.app(30, "Thirty", record=False)
    m.store.land_wishlist({"account_id": 1001, "read_at": NOW,
                           "items": [{"appid": a, "priority": 0, "date_added": NOW} for a in (10, 20, 22, 30)]})
    rows = {r["genre"]: r for r in m.store.reports().rows("stated_revealed")}
    first = next(iter(rows.values()))
    check("by hand: Action on 2 of the 3 played games, Strategy and Puzzle on 1 each; never-played and "
          "Free-To-Play-only games left out",
          {g: r["played_games"] for g, r in rows.items()} == {"Action": 2, "Strategy": 1, "Puzzle": 1}
          and first["played_games_all"] == 3, {g: dict(r) for g, r in rows.items()})
    eight = m.built()["preference"]
    lists = [p for p in eight.parts if p.bars]
    check("three lists of bars, in one order: the wishlist, the games played, the hours",
          [p.heading for p in lists] == ["On your wishlist", "In the games you have played", "In your hours"]
          and len({tuple(b.label for b in p.bars) for p in lists}) == 1, [[b.label for b in p.bars] for p in lists])
    check("the games played bars: 67%, 33%, 33%", [b.value for b in lists[1].bars] == ["67%", "33%", "33%"],
          [b.value for b in lists[1].bars])
    table = next(p for p in eight.parts if p.heading == "Side by side")
    check("one gap, wishlist against hours, said in its heading",
          table.columns == ("Genre", "Wishlist", "Games played", "Hours", "Wishlist − hours")
          and [r[4] for r in table.rows] == ["-57 points", "+57 points", "+7 points"], (table.columns, table.rows))
    check("the CSV's columns: the three shares as numbers",
          table.data_columns == ("genre", "wished_games", "wishlist_share", "played_share", "hours_share", "gap")
          and [r[3] for r in table.data] == [0.6667, 0.3333, 0.3333], table.data)
    check("the sentence names all three for the headline genre",
          eight.sentence.startswith("Puzzle is on 67% of your wished games, in 33% of the games you have played "
                                    "and in 10% of your hours"), eight.sentence)
    check("the caveat: the hours column is steep, report 1's concentration; how long against how often",
          "report 1" in eight.caveat and "how long you stay" in eight.caveat and "how often you try" in eight.caveat,
          eight.caveat)
    check("the idea: the extensive and the intensive margin, the count as the like-for-like comparison",
          "extensive and the intensive margin" in eight.concept and "like-for-like" in eight.concept, eight.concept)
    check("a gap of one point is one point", reports._points(0.01) == "+1 point" and reports._points(-0.22) == "-22 points")
    m.store.close()

    store = test_sandbox.library()
    source = store.reports()
    real = {r["genre"]: r for r in source.rows("stated_revealed")}
    profile = {r["label"]: r["apps"] for r in source.rows("profile_genres")}
    check(f"on the real copy: the games played of each of {len(profile)} genres are report 3's",
          profile and {g: r["played_games"] for g, r in real.items() if r["played_games"]} == profile)
    marks = ",".join("?" * len(rules.STEAM_NOT_GENRES))
    direct = dict(store._conn.execute(
        f"""SELECT genre.name, COUNT(DISTINCT h.appid) FROM v_hours h
            JOIN steam_app_genre sg ON sg.appid = h.appid JOIN genre ON genre.id = sg.genre_id
            WHERE h.minutes > 0 AND sg.genre_id NOT IN ({marks})
              AND h.appid NOT IN ({",".join("?" * len(rules.STEAM_NOT_GAMES))})
              AND COALESCE(h.marked_tool, CASE WHEN h.app_type IS NULL OR h.app_type = 'game' THEN 0 ELSE 1 END) = 0
            GROUP BY genre.id""", (*rules.STEAM_NOT_GENRES, *rules.STEAM_NOT_GAMES)).fetchall())
    check("and equal to a direct count of the apps with minutes and the genre",
          {g: r["played_games"] for g, r in real.items() if r["played_games"]} == direct, (real.keys(), direct))
    store.close()
except Exception as exc:
    unreached("2", exc)

print("\n=== 3. report 6 and report 4: list price and today's cost ===")
try:
    def money_library(name, sale: bool):
        lib = Made(name)
        for appid, gid_name, seconds in ((7001, "Full Price", 7200), (7002, "On Sale", 3600), (7003, "Waiting", None)):
            lib.app(appid, gid_name)
            game_id = lib.game(f"c:/made/{appid}", gid_name, seconds, appid)
            lib.install(game_id)
        lib.price(7001, 2000)
        lib.price(7002, 2000 if sale else 4000, 4000)  # list 40,00 EUR; today 20,00 EUR on sale, else 40,00
        lib.price(7003, 1500 if sale else 3000, 3000)  # never played: the backlog
        return lib

    s = money_library("sale", True)
    one = s.store.reports().one("money_library")
    check("the library: 90,00 EUR at list price, 55,00 EUR today, 2 of 3 titles on sale",
          (one["list_cents"], one["today_cents"], one["on_sale"], one["priced"]) == (9000, 5500, 2, 3), one)
    made = s.built()
    check("report 6's sentence names both, and the titles on sale",
          made["money"].sentence.startswith("Your installed library lists at 90,00\u00a0€ and would cost 55,00\u00a0€ "
                                            "to buy today (2 of 3 titles on sale)"), made["money"].sentence)
    table = made["money"].parts[0]
    check("the library's table shows both", ("At list price", "90,00\u00a0€") in table.rows
          and ("Today's cost (replacement value)", "55,00\u00a0€") in table.rows, table.rows)
    check("the backlog's value in both reports: 30,00 EUR at list price, 15,00 EUR today",
          "30,00\u00a0€ at list price, 15,00\u00a0€ today" in made["backlog"].sentence
          and "30,00\u00a0€ at list price, 15,00\u00a0€ today" in made["money"].parts[1].note,
          (made["backlog"].sentence, made["money"].parts[1].note))
    never = next(p for p in made["backlog"].parts if p.heading == "Never played")
    check("the backlog's table: the list price and today's price, each under its own heading",
          never.columns == ("Game", "Size", "List price", "Today", "From")
          and tuple(never.rows[0][2:4]) == ("30,00\u00a0€", "15,00\u00a0€"), (never.columns, never.rows))
    proxy = s.store.reports().rows("money_proxy")
    check("the stand-in per hour is the list price: 40,00 EUR over 1 hour, not today's 20,00",
          [(r["name"], round(r["cents_per_hour"])) for r in proxy if r["name"] == "On Sale"] == [("On Sale", 4000)],
          proxy)
    s.store.close()

    n = money_library("no sale", False)
    made = n.built()
    check("with nothing on sale, one figure",
          made["money"].sentence.startswith("Your installed library lists at 90,00\u00a0€ and would cost the same to "
                                            "buy today (none of 3 titles on sale)"), made["money"].sentence)
    check("and report 4 one figure for the backlog", "30,00\u00a0€ at list price and today" in made["backlog"].sentence,
          made["backlog"].sentence)
    check("the backlog's value: one price per Steam app, list and today",
          reports._value([{"price_kind": "priced", "steam_appid": 1, "initial_cents": 100, "final_cents": 50,
                           "currency": "EUR"}] * 2) == (100, 50, {"EUR"}))
    n.store.close()
except Exception as exc:
    unreached("3", exc)

print("\n=== 4. nothing written, the command, the document, the time ===")
try:
    path = WORK / "kinds.db"
    before = fingerprint(path)
    again = library_db.LibraryStore(path)
    reports.build(again.reports())
    check("nothing is written by the reports", fingerprint(path) == before)
    check("and the store still writes afterwards (query_only put back)",
          again._conn.execute("UPDATE steam_app SET name = name WHERE appid = 5001").rowcount == 1)
    again.close()

    database = box.folder / rules.LIBRARY_DB_FILE
    run = lambda *args: subprocess.run([sys.executable, str(PROJECT / "reports.py"), *args], capture_output=True,
                                       text=True, encoding="utf-8", errors="replace", cwd=PROJECT)
    out = run("--markdown", "--library", str(database))
    check("--markdown: report 2 on paid games, report 6 both figures, report 8 the games played",
          out.returncode == 0 and "paid games started on Steam" in out.stdout and "### Under two hours, by kind" in out.stdout
          and "Your installed library lists at" in out.stdout and "### In the games you have played" in out.stdout,
          out.stderr[-300:])
    folder = WORK / "csv"
    written = run("--csv", str(folder), "--library", str(database))

    def csv_text(name):
        target = folder / name
        return target.read_text(encoding="utf-8-sig") if target.is_file() else ""

    check("--csv: the kinds, the three shares and today's cost as columns",
          written.returncode == 0 and "share_under_two_hours" in csv_text("2-abandonment.csv")
          and "played_share" in csv_text("8-preference.csv") and "today_cents" in csv_text("6-money.csv"),
          sorted(p.name for p in folder.glob("*.csv")))

    analysis = (PROJECT / "docs" / "ANALIZA.md").read_text(encoding="utf-8")
    quoted = dict(re.findall(r"```sql\n-- (\w+)\n(.*?)\n```", analysis, re.S))
    changed = ("abandonment", "backlog", "money_library", "money_proxy", "stated_revealed")
    check("ANALIZA quotes the five changed queries as the code has them",
          all(quoted.get(n) == queries.QUERIES[n] for n in changed), [n for n in changed if quoted.get(n) != queries.QUERIES[n]])
    check("ANALIZA: reports 2, 4, 6 and 8 answered on 16 October, and the date line says so",
          analysis.count("**Răspunsul (16 octombrie 2026") >= 4 and "ale rapoartelor 2, 4, 6 și 8, din 16 octombrie" in analysis)
    check("ANALIZA: the ideas, each with its English term",
          all(w in analysis for w in ("*confounding variable*", "*extensive and intensive margin*", "*concentration*",
                                      "*replacement value*", "*list price*")))

    store = test_sandbox.library()
    source = store.reports()
    timings = []
    for _ in range(5):
        started = time.perf_counter()
        reports.build(source)
        timings.append(1000 * (time.perf_counter() - started))
    check(f"the reports (eleven since Phase 103) in {min(timings):.0f} ms (best of 5), under 50", min(timings) < 50, timings)
    store.close()
except Exception as exc:
    unreached("4", exc)

print("\n=== 5. the build log out of CLAUDE.md ===")
try:
    import sources

    old = subprocess.run(["git", "show", "before-phase-91:CLAUDE.md"], cwd=PROJECT, capture_output=True,
                         check=True).stdout.decode("utf-8").replace("\r\n", "\n")
    claude = (PROJECT / "CLAUDE.md").read_text(encoding="utf-8").replace("\r\n", "\n")
    history = sources.build_log().replace("\r\n", "\n")
    old_notes = re.findall(r"^## Phase \d+ notes.*$", old, re.M)
    check(f"ISTORIC holds every one of the {len(old_notes)} \"## Phase N notes\" the old CLAUDE.md held, and Phase 91's",
          old_notes and all(h in history for h in old_notes) and "## Phase 91 notes" in history,
          [h for h in old_notes if h not in history])
    keep = ("## What this is", "## Build discipline", "## Architecture", "## Commands", "## Domain rules",
            "## Deliberate departures", "## Constraints", "## Environment")
    heads = [m.start() for m in re.finditer(r"^## .*$", old, re.M)]
    old_sections = [old[a:b] for a, b in zip(heads, heads[1:] + [len(old)])]
    moved = [s for s in old_sections if not s.startswith(keep)]
    check(f"every one of the {len(moved)} sections moved is in ISTORIC word for word, in the same order",
          all(s.rstrip("\n") in history for s in moved)
          and [history.index(s.rstrip("\n")) for s in moved] == sorted(history.index(s.rstrip("\n")) for s in moved))
    check("CLAUDE.md holds no phase notes and keeps its nine sections", not re.search(r"^## Phase \d+ notes", claude, re.M)
          and all(re.search("^" + re.escape(k), claude, re.M) for k in keep), [k for k in keep if k not in claude])
    lessons = claude[claude.index("## Lessons that still bind"):claude.index("## Constraints")]
    lines = [line for line in lessons.splitlines() if line.startswith("- ")]
    check(f"\"Lessons that still bind\": {len(lines)} lessons in {len(lessons.splitlines())} lines, at most 150, each "
          "with the phase or notes it comes from", len(lessons.splitlines()) <= 150 and len(lines) >= 40
          and all(re.search(r"\((after )?Phases? \d|notes\)|reported from use\)", line) for line in lines),
          [line for line in lines if not re.search(r"\((after )?Phases? \d|notes\)|reported from use\)", line)])
    check("the lessons include the ones the brief named",
          all(w in lessons for w in ("Edit tool", "self.config", "run_sandboxed", "deep-copies", "hardcode",
                                     "Photograph state", "rgba(", "unpolish")))
    check("a cross-reference in CLAUDE.md points to ISTORIC, not to notes that are gone",
          "see below |" not in claude and "see Phase 38 notes |" not in claude and claude.count("docs/ISTORIC.md") >= 4)
    check(f"CLAUDE.md weighs {len(claude.encode('utf-8')) // 1024} KB, from {len(old.encode('utf-8')) // 1024}",
          len(claude.encode("utf-8")) < len(old.encode("utf-8")) / 4)
    attributes = (PROJECT / ".gitattributes").read_text(encoding="utf-8")
    check(".gitattributes: * text=auto", "* text=auto" in attributes.splitlines())
    # The freeze as Phase 91 left it: Phase 92 replaced it with the feature window (before-phase-92 is
    # Phase 91's last commit).
    frozen = subprocess.run(["git", "show", "before-phase-92:CLAUDE.md"], cwd=PROJECT, capture_output=True,
                            text=True, encoding="utf-8").stdout
    discipline = frozen[frozen.index("## Build discipline"):frozen.index("| Phase | Deliverable | Status |")]
    check("the freeze in Build discipline, dated, its two exceptions and its one way out",
          "**The feature freeze, 16 October 2026.**" in discipline and "repair reported from use" in discipline
          and "the thesis's own needs" in discipline and '"freeze lifted"' in discipline)
    row = next((line for line in claude.splitlines() if line.startswith("| 91 |")), "")
    check("the phase table's row 91 says it", "feature freeze from 16 October 2026" in row, row[:120])
    readme = subprocess.run(["git", "diff", "--stat", "before-phase-91", "before-phase-92", "--",
                             "docs/CITESTE-MA.md",
                             "docs/DISTRIBUTIE.md"], cwd=PROJECT, capture_output=True, text=True).stdout
    check("CITESTE-MA and DISTRIBUTIE untouched by Phase 91: nothing the friends run changed", readme.strip() == "", readme)
except Exception as exc:
    unreached("5", exc)

print("\n=== 6. the layers, the network, the real data ===")
layers = subprocess.run([sys.executable, str(PROJECT / "tests" / "check_layers.py")], capture_output=True, text=True,
                        encoding="utf-8", errors="replace")
check("no import points up a layer; sqlite3 only in data_access/", layers.returncode == 0, layers.stdout[-300:])
check("nothing in this suite reached the network", attempts == [], attempts)
changed = box.finish()
check("config.json and the library database are unchanged", not changed, changed)
import shutil

shutil.rmtree(WORK, ignore_errors=True)
print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
