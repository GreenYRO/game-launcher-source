"""Phase 89: the three extensions to the wishlist -- a sharper fit, report 8, a price line per game.

  1. the fit on the real copy: each genre's weight is ln(apps with a genre / apps with it), worked
     out here by a query of the test's own; the vectors are of length 1; every wished game's fit
     is between 0 and 1, said in the page's words, naming at most two of its own genres;
  2. report 8 on a made-up library, worked out by hand: the wishlist's shares and the hours',
     the gap, the sentence; an account not mine, a game taken off the list and Free To Play left
     out; a genre on one wished game never the headline; no wishlist and no genre said in words;
     the CSV's columns; the Markdown's "## 8.";
  3. report 8 on the real copy against two other roads: the hours of each genre are report 3's,
     the wished games of each are v_wishlist_now's;
  4. the Reports page: eight cards, the eighth with its two lists of bars and its table, at 100%
     and in TV mode;
  5. the price line: kept from the third price on, only in today's currency, never for a game
     free or not sold; on a made-up library through the page's own function; on the live window,
     the line drawn in the accent where a row has prices and nothing where it has not;
  6. the time: the eight reports under 50 ms on the real copy;
  7. the documents and the layers; nothing reached the network;
  8. the real library exactly as it was found.

On a throwaway copy of the data; every request stops at a stand-in.
"""
import csv
import math
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import sources  # the build log's notes (Phase 91)
import test_sandbox

box = test_sandbox.start()
box.copy_cache("steam_details", "steam_web.json", "steam_search.json")  # copies, read only
attempts: list[str] = []


def no_network(request, *args, **kwargs):
    attempts.append(getattr(request, "full_url", str(request)))
    raise OSError("the network is blocked in this suite")


urllib.request.urlopen = no_network

import logging

logging.basicConfig(level=logging.CRITICAL)

from PySide6.QtCore import QEventLoop, QPoint, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)

from data_access import library_db
from data_access import reports as queries
from logic import reports, wishlist
from presentation import ui_reports, ui_rules, ui_window, ui_wishlist
from shared import rules

BASE = 76561197960265728
WORK = Path(tempfile.mkdtemp(prefix="phase89_"))
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


def at(day: int, hour: int = 12) -> str:
    return datetime(2026, 10, day, hour, tzinfo=timezone.utc).isoformat(timespec="seconds")


def made_store(name: str):
    """A library of its own: Alpha mine, Charlie not; Action, Strategy, Puzzle and Free To Play."""
    store = library_db.LibraryStore(WORK / f"{name}.db")
    c = store._conn
    for account_id, persona, mine in ((1001, "Alpha", 1), (1003, "Charlie", 0)):
        c.execute("INSERT INTO steam_account (account_id, steam_id64, persona, is_mine, first_seen, last_seen) "
                  "VALUES (?, ?, ?, ?, ?, ?)", (account_id, account_id + BASE, persona, mine, at(1), at(1)))
    for gid, gname in ((1, "Action"), (2, "Strategy"), (3, "Puzzle"), (37, "Free To Play")):
        c.execute("INSERT INTO genre (id, name) VALUES (?, ?)", (gid, gname))
    return store


def app_row(store, appid: int, name: str, genres=(), record=True):
    store._conn.execute("INSERT INTO steam_app (appid, has_record, name, app_type) VALUES (?, ?, ?, ?)",
                        (appid, 1 if record else 0, name if record else None, "game" if record else None))
    for gid in genres:
        store._conn.execute("INSERT INTO steam_app_genre (appid, genre_id) VALUES (?, ?)", (appid, gid))


def played(store, key: str, appid: int, minutes: int):
    store._conn.execute("INSERT INTO game (identity_key, name_origin, steam_appid, appid_source, playtime_seconds) "
                        "VALUES (?, 'scan', ?, 'manifest', ?)", (f"c:/games/{key}", appid, minutes * 60))


def reading(account_id: int, when: str, *appids):
    return {"account_id": account_id, "read_at": when,
            "items": [{"appid": a, "priority": 0, "date_added": at(1)} for a in appids]}


def accent_pixels(image, box) -> int:
    """How many pixels in the box are near the accent colour (the price line and its dot)."""
    accent = QColor(ui_rules.COLOR_WISHLIST_SPARK)
    count = 0
    for x in range(int(box.left()), int(box.right())):
        for y in range(int(box.top()), int(box.bottom())):
            p = image.pixelColor(x, y)
            if abs(p.red() - accent.red()) + abs(p.green() - accent.green()) + abs(p.blue() - accent.blue()) < 60:
                count += 1
    return count


window = ui_window.MainWindow()
window.resize(1280, 820)
window.show()
settle(1.5)
store = window.overrides
source = store.reports()

print("=== 1. the fit on the real copy ===")
try:
    weights = wishlist.weights_of(source.rows("wishlist_idf"))
    not_genres = tuple(rules.STEAM_NOT_GENRES)
    marks = ",".join("?" * len(not_genres))
    corpus = store._conn.execute(
        f"SELECT COUNT(DISTINCT g.appid) FROM steam_app_genre g JOIN steam_app s ON s.appid = g.appid "
        f"WHERE s.has_record = 1 AND g.genre_id NOT IN ({marks})", not_genres).fetchone()[0]
    counted = dict(store._conn.execute(
        f"SELECT g.genre_id, COUNT(DISTINCT g.appid) FROM steam_app_genre g JOIN steam_app s ON s.appid = g.appid "
        f"WHERE s.has_record = 1 AND g.genre_id NOT IN ({marks}) GROUP BY g.genre_id", not_genres).fetchall())
    check(f"{len(weights)} genres weighed over {corpus} apps with a record, each ln(apps / apps with it)",
          weights and set(weights) == set(counted)
          and all(abs(weights[g] - math.log(corpus / n)) < 1e-12 for g, n in counted.items()), (corpus, counted))
    check("Free To Play and the content descriptors weigh nothing: they are not genres here",
          not set(weights) & set(rules.STEAM_NOT_GENRES))
    profile = wishlist.profile_of(source.rows("wishlist_profile"))
    taste = wishlist.taste(profile, weights)
    check("what is played is one vector of length 1", abs(math.sqrt(sum(x * x for x in taste.values())) - 1) < 1e-9)
    genres: dict[int, dict] = {}
    for row in source.rows("wishlist_genres"):
        genres.setdefault(row["appid"], {})[row["genre_id"]] = row["name"]
    lengths = [math.sqrt(sum(x * x for x in wishlist.vector(g, weights).values())) for g in genres.values()]
    check("every wished game's genres a vector of length 1", lengths and all(abs(n - 1) < 1e-9 for n in lengths))
    found = wishlist.fits(source)
    words = re.compile(r"^(\d{1,3}% like what you play|under 1% like what you play|unlike what you play) · (.+)$")
    scored = {a: f for a, f in found.items() if f.share is not None}
    check(f"{len(scored)} of {len(found)} wished games scored, each between 0 and 1",
          all(0 <= f.share <= 1 for f in scored.values()))
    bad = [(a, f.words) for a, f in scored.items()
           if not words.match(f.words) or len(words.match(f.words).group(2).split(", ")) > rules.WISHLIST_FIT_GENRES_NAMED
           or not set(words.match(f.words).group(2).split(", ")) <= set(genres.get(a, {}).values())]
    check("said in the page's words, naming at most two of the game's own genres", not bad, bad)
    others = [f.words for f in found.values() if f.share is None]
    check("a game it cannot score says why", all(w in (wishlist.NOT_FETCHED, wishlist.NO_GENRE, wishlist.NOTHING_PLAYED)
                                                for w in others), others)
    for appid, fit in sorted(scored.items(), key=lambda kv: -kv[1].share)[:5]:
        print(f"      {appid}: {fit.words}")
except Exception as exc:
    unreached("1", exc)

print("\n=== 2. report 8 on a made-up library ===")
try:
    m = made_store("report8")
    app_row(m, 900, "Played A", (1, 2))
    app_row(m, 901, "Played B", (1,))
    app_row(m, 902, "Played C", (3,))
    played(m, "a", 900, 600)
    played(m, "b", 901, 300)
    played(m, "c", 902, 100)
    app_row(m, 10, "Ten", (1, 2, 37))
    app_row(m, 20, "Twenty", (3,))
    app_row(m, 21, "Twenty-one", (3,))
    app_row(m, 22, "Twenty-two", (3, 2))
    app_row(m, 30, "Thirty", record=False)
    app_row(m, 40, "Forty", (1,))
    m.land_wishlist(reading(1001, at(10), 10, 20, 21, 22, 30))
    m.land_wishlist(reading(1001, at(11), 10, 20, 22, 30))  # 21 taken off the list
    m.land_wishlist(reading(1003, at(11), 40))  # on Charlie's list, not mine
    rows = {r["genre"]: r for r in m.reports().rows("stated_revealed")}
    first = next(iter(rows.values()))
    check("four games on the list, three with a genre; 21 (taken off) and Charlie's 40 not among them",
          first["wished_games"] == 4 and first["wished_with_genre"] == 3, dict(first))
    check("wished: Action on 1, Strategy on 2, Puzzle on 2; Free To Play never a genre here",
          {g: r["wished"] for g, r in rows.items()} == {"Action": 1, "Strategy": 2, "Puzzle": 2}, rows.keys())
    check("hours: Action 900, Strategy 600, Puzzle 100 of the 1000 minutes on games with a genre",
          {g: r["minutes"] for g, r in rows.items()} == {"Action": 900, "Strategy": 600, "Puzzle": 100}
          and first["minutes_all"] == 1000)
    eight = reports.build(m.reports())[7]  # the eighth; a ninth follows it since Phase 98
    check("the eighth report: Stated and revealed", (eight.number, eight.key, eight.title)
          == (8, "preference", "Stated and revealed"), (eight.number, eight.key))
    # Since Phase 91 the games played are the third measure: 900 and 901 have Action (2 of 3), 900 Strategy,
    # 902 Puzzle (1 of 3 each).
    check("by hand: Puzzle 67% of the wishes, 33% of the games played, 10% of the hours; Action the other way",
          eight.sentence == "Puzzle is on 67% of your wished games, in 33% of the games you have played and in 10% of "
                            "your hours; Action the other way: in 90% of your hours and 67% of the games you have "
                            "played, on 33% of your wishes.", eight.sentence)
    table = eight.parts[3]
    check("side by side: the three shares, one gap (wishlist against hours), the genres by their largest share",
          [tuple(r) for r in table.rows] == [("Action", "33%", "67%", "90%", "-57 points"),
                                             ("Puzzle", "67%", "33%", "10%", "+57 points"),
                                             ("Strategy", "67%", "33%", "60%", "+7 points")], table.rows)
    check("three lists of bars, each bar its share", [p.heading for p in eight.parts[:3]]
          == ["On your wishlist", "In the games you have played", "In your hours"]
          and [round(b.fraction, 4) for b in eight.parts[0].bars] == [0.3333, 0.6667, 0.6667]
          and [round(b.fraction, 4) for b in eight.parts[1].bars] == [0.6667, 0.3333, 0.3333]
          and [b.fraction for b in eight.parts[2].bars] == [0.9, 0.1, 0.6]
          and [b.value for b in eight.parts[2].bars] == ["90%", "10%", "60%"], [p.bars for p in eight.parts[:3]])
    check("the note says how many have a genre and how many wait for their record",
          eight.parts[0].note == "3 of 4 wished games have a genre; 1 not fetched yet.", eight.parts[0].note)
    check("the CSV's columns: genre, wished games, the three shares, the gap",
          table.data_columns == ("genre", "wished_games", "wishlist_share", "played_share", "hours_share", "gap")
          and table.data[1] == ("Puzzle", 2, 0.6667, 0.3333, 0.1, 0.5667), table.data)
    m.close()

    def built(rows):
        return reports.preference({"stated_revealed": rows})

    def row(genre, wished, minutes, with_genre=3, minutes_all=100, games=None):
        return {"genre": genre, "wished": wished, "minutes": minutes, "minutes_all": minutes_all,
                "wished_with_genre": with_genre, "wished_games": with_genre if games is None else games,
                "played_games": 1 if minutes else 0, "played_games_all": 2}

    one = built([row("Racing", 1, 0), row("Puzzle", 2, 50), row("Action", 0, 90)])
    check("a genre on one wished game is never the headline: Puzzle (+17) named, not Racing (+33)",
          one.sentence.startswith("Puzzle is on 67%"), one.sentence)
    check("no wishlist: said in words, nothing drawn", built([]).empty and "No wishlist" in built([]).sentence)
    none = reports.preference({"stated_revealed": [row("Action", 0, 90, with_genre=0, games=2)]})
    check("wished games with no genre yet: said in words", none.empty and "no genres yet" in none.sentence, none.sentence)
    empty_store = library_db.LibraryStore(WORK / "empty.db")
    check("an empty library answers all eleven (since Phase 103) in words",
          [r.empty for r in reports.build(empty_store.reports())] == [True] * 11)
    empty_store.close()
    md = reports.markdown(reports.build(source), datetime.now(), queries.QUERIES)
    check("the Markdown carries ## 8. and its SQL as the code has it",
          "## 8. Stated and revealed" in md and queries.STATED_REVEALED in md)
except Exception as exc:
    unreached("2", exc)

print("\n=== 3. report 8 on the real copy, by two other roads ===")
try:
    real = {r["genre"]: r for r in source.rows("stated_revealed")}
    genres3 = {r["label"]: r["minutes"] for r in source.rows("profile_genres")}
    check(f"the hours of each of {len(genres3)} genres are report 3's", genres3
          and {g: r["minutes"] for g, r in real.items() if r["minutes"]} == genres3)
    view_rows = [r for r in source.rows("wishlist_now") if r["lists"] > 0]
    by_view: dict[str, int] = {}
    with_genre = set()
    for r in source.rows("wishlist_genres"):
        if any(v["appid"] == r["appid"] for v in view_rows):
            by_view[r["name"]] = by_view.get(r["name"], 0) + 1
            with_genre.add(r["appid"])
    check(f"the wished games of each genre are v_wishlist_now's ({len(view_rows)} on the lists)",
          {g: r["wished"] for g, r in real.items() if r["wished"]} == by_view
          and (not real or next(iter(real.values()))["wished_games"] == len(view_rows)
               and next(iter(real.values()))["wished_with_genre"] == len(with_genre)), (real, by_view))
    eighth = reports.build(source)[7]  # a ninth follows it since Phase 98, a tenth since 102
    print(f"      {eighth.sentence}")
except Exception as exc:
    unreached("3", exc)

print("\n=== 4. the Reports page ===")
try:
    for label, tv in (("100%", False), ("TV", True)):
        window.set_tv_mode(tv)
        settle(1.0)
        window.show_reports()
        settle(1.0)
        page = window.reports_page
        card = page.card("preference")
        check(f"{label}: eleven cards (since Phase 103), the eighth Stated and revealed with three lists of bars (since "
              "Phase 91) and a table", len(page.cards) == 11 and card is not None and len(card.bars) == 3 and len(card.tables) == 1,
              (len(page.cards), card and (len(card.bars), len(card.tables))))
        inside = card.mapTo(window, card.rect().topRight()).x() <= window.width()
        check(f"{label}: the card within the window", inside)
        check(f"{label}: the intro says eleven questions (since Phase 103)", ui_reports.INTRO.startswith("Eleven questions"))
    window.set_tv_mode(False)
    settle(0.8)
    window.show_library()
    settle(0.4)
except Exception as exc:
    unreached("4", exc)

print("\n=== 5. the price line ===")
try:
    def view(appid, **fields) -> dict:
        row = {"appid": appid, "name": f"Game {appid}", "has_record": 1, "accounts": "Alpha", "lists": 1,
               "date_added": at(1), "first_seen": at(10), "removed_at": None, "kind": "priced", "currency": "EUR",
               "initial_cents": 1000, "final_cents": 1000, "discount_percent": 0, "observations": 3,
               "first_observed": at(1), "lowest_cents": 800, "lowest_on": at(2), "is_lowest_now": 0}
        row.update(fields)
        return row

    fit = wishlist.Fit(0.5, "50% like what you play · Action")
    three = (("EUR", 1000), ("EUR", 800), ("EUR", 1000))
    check("three prices make a line, oldest first", wishlist.row_of(view(1), fit, False, False, three).series
          == (1000, 800, 1000))
    check("two do not", wishlist.row_of(view(1), fit, False, False, three[:2]).series == ())
    check("only today's currency: a price in zloty is left out, and with it the third",
          wishlist.row_of(view(1), fit, False, False, (("PLN", 4000),) + three[:2]).series == ())
    check("a game free or not sold has no line", all(
        wishlist.row_of(view(1, kind=k), fit, False, False, three).series == () for k in ("free", "unavailable")))
    m = made_store("series")
    for appid in (50, 51):
        app_row(m, appid, f"App {appid}", (1,))
    m.land_wishlist(reading(1001, at(10), 50, 51))
    obs = [{"appid": 50, "observed_at": at(day), "kind": "priced", "currency": "EUR", "initial_cents": 2000,
            "final_cents": cents, "discount_percent": round(100 - cents / 20)}
           for day, cents in ((1, 2000), (2, 1500), (3, 1000), (4, 1200))]
    obs.append({"appid": 51, "observed_at": at(1), "kind": "priced", "currency": "EUR", "initial_cents": 900,
                "final_cents": 900, "discount_percent": 0})
    m.add_observations(obs)
    model = wishlist.page(m.reports(), m.steam_accounts(), set(), True)
    lines = {r.appid: r.series for r in model.rows}
    check("through the page's own function: four prices for one, none drawn for the one priced once",
          lines == {50: (2000, 1500, 1000, 1200), 51: ()}, lines)
    m.close()

    planted = []
    # The first priced game the page shows, so its row is on screen.
    priced = {r["appid"]: r for r in source.rows("wishlist_now") if r["kind"] == "priced" and r["lists"] > 0}
    shown_first = window.wishlist_model()
    target = next((priced[r.appid] for r in (shown_first.rows if shown_first else ()) if r.appid in priced), None)
    if target is not None:
        for day, share in ((1, 1.0), (2, 0.8), (3, 0.6)):
            planted.append({"appid": target["appid"], "observed_at": at(day), "kind": "priced",
                            "currency": target["currency"], "initial_cents": target["initial_cents"],
                            "final_cents": round(target["initial_cents"] * share),
                            "discount_percent": round(100 - 100 * share)})
        store.add_observations(planted)  # in the copy only
    for label, tv in (("100%", False), ("TV", True)):
        window.set_tv_mode(tv)
        settle(1.0)
        window.show_wishlist()
        settle(1.2)
        shown = window.wishlist_page.list
        delegate = shown.itemDelegate()
        picture = window.grab().toImage()
        with_line = without = None
        for i in range(shown.count()):
            payload = shown.item(i).data(ui_wishlist.PAYLOAD_ROLE)
            if not isinstance(payload, wishlist.Row):
                continue
            rect = shown.visualItemRect(shown.item(i))
            if rect.bottom() > shown.viewport().height():
                continue
            spark = delegate.spark_rect(delegate.row_rect(rect))
            corner = shown.viewport().mapTo(window, QPoint(int(spark.left()), int(spark.top())))
            box_ = spark.translated(corner.x() - spark.left(), corner.y() - spark.top())
            if payload.series and with_line is None:
                with_line = accent_pixels(picture, box_)
            elif not payload.series and without is None:
                without = accent_pixels(picture, box_)
        check(f"{label}: a row with prices draws its line in the accent", (with_line or 0) > 20, with_line)
        check(f"{label}: a row without draws nothing there", without == 0, without)
        window.grab().save(str(Path(tempfile.gettempdir()) / f"phase89_{label.replace('%', '')}.png"))
    window.set_tv_mode(False)
    settle(0.8)
    window.show_library()
    settle(0.4)
except Exception as exc:
    unreached("5", exc)

print("\n=== 6. the time ===")
try:
    timings = []
    for _ in range(3):
        started = time.perf_counter()
        reports.build(source)
        timings.append(1000 * (time.perf_counter() - started))
    check(f"the reports (eleven since Phase 103) in {min(timings):.0f} ms (best of 3), under 50", min(timings) < 50, timings)
    started = time.perf_counter()
    source.rows("stated_revealed")
    print(f"      stated_revealed alone: {1000 * (time.perf_counter() - started):.1f} ms")
except Exception as exc:
    unreached("6", exc)

print("\n=== 7. the documents, the layers ===")
try:
    analysis = (PROJECT / "docs" / "ANALIZA.md").read_text(encoding="utf-8")
    quoted = dict(re.findall(r"```sql\n-- (\w+)\n(.*?)\n```", analysis, re.S))
    names = ("wishlist_idf", "wishlist_series", "stated_revealed")
    check("ANALIZA: unsprezece rapoarte (since Phase 103), the three new queries as the code has them",
          analysis.startswith("# Ce poate spune baza de date: unsprezece rapoarte")
          and all(quoted.get(n) == queries.QUERIES[n] for n in names), [n for n in names if quoted.get(n) != queries.QUERIES[n]])
    check("ANALIZA: TF-IDF, the cosine, the sparkline and report 8, each with its idea",
          all(w in analysis for w in ("TF-IDF", "cosine similarity", "sparkline", "## 8. Declarat și dezvăluit",
                                      "intention–behaviour gap")))
    claude = (PROJECT / "CLAUDE.md").read_text(encoding="utf-8")
    check("CLAUDE.md has the phase and its notes", "| 89 |" in claude and "## Phase 89 notes" in sources.build_log())
    layers = subprocess.run([sys.executable, str(PROJECT / "tests" / "check_layers.py")], capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    check("no import points up a layer; sqlite3 only in data_access/", layers.returncode == 0, layers.stdout[-300:])
    check("nothing in this suite reached the network", attempts == [], attempts)
except Exception as exc:
    unreached("7", exc)

window.close()
settle(0.3)
window.overrides.close()
print("\n=== 8. the real library is exactly as it was found ===")
changed = box.finish()
check("config.json and the library database are unchanged", not changed, changed)
import shutil

shutil.rmtree(WORK, ignore_errors=True)
print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
