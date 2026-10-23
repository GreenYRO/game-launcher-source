"""Phase 98: For you -- what to play next and why; what fits tonight.

  1. the shared maths: logic/fit.py holds the fit, the wishlist reads the very same functions, its words
     unchanged on a case worked out by hand;
  2. the queries: read-only (`query_only`), answered by every reports runner; on a planted library the
     waiting games are report 4's own rows -- its 'never' and 'under', installed, not hidden, not a tool,
     not Finished or Dropped, Playing kept -- and an Epic game with no time ('unknown') is not one;
  3. the ranking: by the fit, ties to the name; the words Phase 89's, the same function's; three large,
     the rest a line each, and how many more;
  4. honest words: a game with no genres, no record or no Steam app is named apart, never scored 0;
     nothing played to compare with says so; the games played in the last 7 days are left out and named;
     an empty page says why;
  5. Tonight: the median of each game's sessions, both origins, a tool's never; judged only with 3 or
     more; a game's records joined by its name; a game uninstalled or Dropped never offered; ranked by
     the share that fits, then the one played last; the four choices and the default; the empty words;
  6. a game's page: "Usually N a session" only for a game judged; the Fit fact only for a waiting game,
     in the page's own words;
  7. the place: in the side rail and the top bar after Library, a sparkle of its own; opening it from
     each, lit; the page header's tab; Tonight's choice remembered by its own key, nothing else written;
  8. the pad: View, then left from Stats; up and down between rows, left and right along one and past
     its ends to the next place; A plays (the play captured), X the game's menu with Details first, Y
     Tonight's choice, B back; the hints;
  9. rendered with the rail, the top bar and in TV mode: nothing to scroll sideways, the ring on the
     first game;
 10. on the copy of the user's library: its counts add up, in time; the layers;
 11. report 9, Recommendation, on the planted library: the ranking, the typical sessions, the look back
     worked out by hand -- a rank on the evening before each first play, the cold and the same-day ones,
     the one played before it was first seen, a game Steam counts left out; an empty library in words;
     the taste from report 1's rows the very profile the wishlist reads; report 3 the same in one run;
 12. the nine reports under 50 ms on the copy, together; the Reports page's ninth card; the Markdown;
 13. the documents; the real data, config and Run key unchanged.

On a throwaway copy of the data; the network is blocked; no game is started.
"""
import json
import re
import sys
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import sources  # the build log's notes (Phase 91)
import test_sandbox

box = test_sandbox.start({"allow_network": False, "startup_scan": False, "tv_mode": False})
box.copy_cache("steam_details", "steam_web.json", "steam_search.json")  # copies, read only
attempts: list[str] = []


def no_network(request, *args, **kwargs):
    attempts.append(getattr(request, "full_url", str(request)))
    raise OSError("the network is blocked in this suite")


urllib.request.urlopen = no_network

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication, QPushButton

app = QApplication([])

from adapters import controller
from data_access import library_db
from data_access import recommend as recommend_queries
from data_access import reports as data_reports
from logic import fit as fit_module
from logic import recommend
from logic import reports as reports_module
from logic import wishlist
from presentation import ui_actions, ui_detail, ui_foryou, ui_icons, ui_pageshell, ui_rail, ui_topbar, ui_tv, ui_window
from shared import rules

passed = failed = 0
WORK = Path(box.folder) / "p98"
WORK.mkdir(exist_ok=True)
NOW = datetime(2026, 10, 18, 20, 0).astimezone()  # a fixed moment for the planted library


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"   PASS  {name}")
    else:
        failed += 1
        print(f"   FAIL  {name}   {detail}")


def unreached(section, exc):
    import traceback
    traceback.print_exc()
    check(f"section {section} ran to its end", False, repr(exc))


def settle(seconds):
    loop = QEventLoop()
    QTimer.singleShot(int(seconds * 1000), loop.quit)
    loop.exec()


def press(window, name: str, wait: float = 0.6) -> None:
    """A button as the hub sends it: emitted from inside a timer, queued to the window."""
    QTimer.singleShot(0, lambda: window.pads.action.emit(name))
    settle(wait)


def ago(days: float) -> str:
    return (NOW - timedelta(days=days)).isoformat(timespec="seconds")


class Made:
    """A fresh library database (the current version) with rows put in by hand, on a scratch file."""

    def __init__(self, name: str) -> None:
        self.path = WORK / f"{name}.db"
        self.path.unlink(missing_ok=True)
        self.store = library_db.LibraryStore(self.path)
        self.c = self.store._conn
        self.scan = None
        for gid, words in ((1, "Action"), (2, "Strategy"), (3, "RPG"), (37, "Free To Play")):
            self.c.execute("INSERT INTO genre (id, name) VALUES (?, ?)", (gid, words))

    def app(self, appid, name, genres=(), record=1):
        self.c.execute("INSERT OR IGNORE INTO steam_app (appid, has_record, name, app_type) VALUES (?, ?, ?, 'game')",
                       (appid, record, name))
        for genre in genres:
            self.c.execute("INSERT INTO steam_app_genre (appid, genre_id) VALUES (?, ?)", (appid, genre))

    def game(self, name, appid=None, genres=(), minutes=0, last=None, installed=True, source="folders", kind="exe",
             hidden=0, status=None, tool=None, record=1, seen=None):
        if appid is not None:
            self.app(appid, name, genres, record)
        gid = self.c.execute(
            "INSERT INTO game (identity_key, source, known_as, name_origin, steam_appid, appid_source, is_tool, "
            "first_seen, hidden, status, playtime_seconds, last_played) VALUES (?, ?, ?, 'scan', ?, ?, ?, ?, ?, ?, ?, ?)",
            (f"k:{name}:{installed}", source, name, appid, "search" if appid else None, tool, seen or ago(90), hidden, status,
             minutes * 60 if minutes else None, last)).lastrowid
        if installed:
            if self.scan is None:
                self.scan = self.c.execute("INSERT INTO scan (finished_at, entry_count, trigger) VALUES (?, 0, 'manual')",
                                           (ago(1),)).lastrowid
            position = self.c.execute("SELECT COUNT(*) FROM install").fetchone()[0]
            self.c.execute("INSERT INTO install (game_id, position, display_name, install_dir, launch_kind, "
                           "launch_target, working_dir, icon_hint, size_on_disk, detection, scan_id) "
                           "VALUES (?, ?, ?, ?, ?, 'x', 'x', 'x', 1000, 'heuristic', ?)",
                           (gid, position, name, f"C:\\made\\{gid}", kind, self.scan))
        return gid

    def session_at(self, gid, started, minutes):
        self.c.execute("INSERT INTO session (game_id, started_at, minutes, origin) VALUES (?, ?, ?, 'launched')",
                       (gid, started, minutes))

    def sessions(self, gid, minutes, start_days=40, origin="launched"):
        for i, m in enumerate(minutes):
            self.c.execute("INSERT INTO session (game_id, started_at, minutes, origin) VALUES (?, ?, ?, ?)",
                           (gid, ago(start_days - i), m, origin))

    def done(self):
        self.c.commit()
        return self.store


def key_of(store, name, installed=True):
    return f"k:{name}:{installed}"


# The planted library. Played (the taste): a 600-minute Action/RPG game, a 200-minute Strategy one.
# Waiting: two Action/RPG games of the same fit (a tie to the name), a Strategy one played 30 minutes, a
# Playing Action one, and the ones that are not waiting or cannot be scored.
planted = Made("planted")
P1 = planted.game("Hollow Deep", 101, (1, 3), minutes=600, last=ago(20))
P2 = planted.game("Empire Lines", 102, (2,), minutes=200, last=ago(15))
planted.game("Zeta Quest", 201, (1, 3))
planted.game("Alpha Quest", 203, (1, 3))
C2 = planted.game("Siege Plans", 202, (2,), minutes=30, last=ago(30))
planted.game("Brawler", 208, (1,), minutes=10, last=ago(25), status=rules.STATUS_PLAYING)
planted.game("Folder Thing")  # no Steam app: the cold start
planted.game("Unfetched", 205, record=0)  # its record not fetched yet
planted.game("No Genres", 206)  # a record with no genres
planted.game("Lately", 207, (1,), minutes=20, last=ago(2))  # played two days ago
planted.game("Hidden One", 209, (1, 3), hidden=1)
planted.game("Finished One", 210, (1, 3), status=rules.STATUS_FINISHED)
D = planted.game("Dropped One", 211, (1, 3), status=rules.STATUS_DROPPED)
T = planted.game("A Tool", 212, (1, 3), tool=1)
U = planted.game("Gone Game", 213, (1, 3), installed=False)
planted.game("Epic Thing", source="epic", kind="uri")  # an Epic game with no time seen: 'unknown'
for appid in (301, 302):
    planted.app(appid, f"Other {appid}", (1,))  # records that only make Action common
# Sessions: Hollow Deep five (median 25), Empire Lines four, one of them seen running (median 105), Siege
# Plans two (not judged), the uninstalled, the Dropped and the tool's never offered, and one game in two
# records -- an old uninstalled one and the installed one -- that only together has three.
planted.sessions(P1, (20, 25, 30, 22, 28), start_days=40)
planted.sessions(P2, (90, 100, 110), start_days=30)
planted.sessions(P2, (200,), start_days=26, origin="observed")
planted.sessions(C2, (15, 15), start_days=35)
planted.sessions(U, (10, 10, 10, 10), start_days=50)
planted.sessions(D, (10, 10, 10), start_days=45)
planted.sessions(T, (5, 5, 5), start_days=44)
S_OLD = planted.game("Split Game", minutes=80, last=ago(11), installed=False)
S_NEW = planted.game("Split Game", minutes=130, last=ago(5))  # its history carried over (Phase 36): played
planted.sessions(S_OLD, (40, 40), start_days=12)
planted.sessions(S_NEW, (50,), start_days=5)
# For report 9's look back: a game first played the day it arrived, and one played before it was first seen
# (no Steam app, so neither moves the taste or the weights).
ARRIVED = (NOW - timedelta(days=20)).replace(hour=10, minute=0, second=0)
SAME = planted.game("Same Day", installed=False, seen=ARRIVED.isoformat(timespec="seconds"))
planted.session_at(SAME, ARRIVED.replace(hour=12).isoformat(timespec="seconds"), 30)
EARLY = planted.game("Early Bird", installed=False, seen=ago(10))
planted.session_at(EARLY, ago(15), 20)
planted.done()

print("=== 1. the shared maths ===")
try:
    names = ("Fit", "NOT_FETCHED", "NO_GENRE", "NOTHING_PLAYED", "profile_of", "weights_of", "vector", "taste", "fit")
    check("the wishlist reads the very same objects as logic/fit.py",
          all(getattr(wishlist, n) is getattr(fit_module, n) for n in names),
          [n for n in names if getattr(wishlist, n, None) is not getattr(fit_module, n)])
    source = (PROJECT / "logic" / "wishlist.py").read_text(encoding="utf-8")
    check("and keeps no copy of its own: no def of them, no math", not re.search(
        r"^def (fit|taste|vector|weights_of|profile_of)\(|^import math", source, re.M))
    # By hand: Action in 6 of 8 apps, RPG in 3: weights ln(8/6), ln(8/3); one game played, both genres.
    weights = fit_module.weights_of([{"genre_id": 1, "apps": 6, "corpus": 8}, {"genre_id": 3, "apps": 3, "corpus": 8}])
    profile = {101: (600.0, frozenset({1, 3}))}
    same = fit_module.fit([(1, "Action"), (3, "RPG")], profile, True, weights)
    rpg = fit_module.fit([(3, "RPG")], profile, True, weights)
    expected = 0.981 / (0.2877 ** 2 + 0.981 ** 2) ** 0.5
    check("the same mix reads 100%; RPG alone its cosine, worked out by hand",
          same.words == "100% like what you play · RPG, Action" and abs(rpg.share - expected) < 0.001
          and rpg.words == f"{round(expected * 100)}% like what you play · RPG", (same, rpg, expected))
    check("unknown is not zero: no record, no genre, nothing played each say so",
          fit_module.fit([], profile, False, weights) == fit_module.Fit(None, fit_module.NOT_FETCHED)
          and fit_module.fit([], profile, True, weights) == fit_module.Fit(None, fit_module.NO_GENRE)
          and fit_module.fit([(1, "Action")], {}, True, weights) == fit_module.Fit(None, fit_module.NOTHING_PLAYED))
except Exception as exc:
    unreached("1", exc)

print("\n=== 2. the queries ===")
try:
    source = planted.store.recommend()
    check("the store hands its recommend queries and the reports' own on one runner",
          isinstance(source, recommend_queries.Recommend)
          and set(recommend_queries.QUERIES) <= set(source.queries) and "wishlist_profile" in source.queries)
    check("and every reports runner answers them -- report 9 is built from them",
          set(recommend_queries.QUERIES) <= set(planted.store.reports().queries)
          and set(recommend_queries.QUERIES) <= set(data_reports.QUERIES))
    check("every query is a WITH or a SELECT", all(q.lstrip().upper().startswith(("WITH", "SELECT"))
                                                    for q in recommend_queries.QUERIES.values()))
    planted.c.execute("PRAGMA query_only = ON")  # what Reports.rows sets
    try:
        planted.c.execute("UPDATE game SET hidden = 0")
        refused = False
    except Exception:
        refused = True
    planted.c.execute("PRAGMA query_only = OFF")
    backlog_rows = source.rows("backlog")
    rows, lately = recommend.waiting(backlog_rows, recommend.recent_since(NOW))
    found = sorted(r["name"] for r in rows)
    check("a write is refused while they run", refused)
    want = sorted(["Zeta Quest", "Alpha Quest", "Siege Plans", "Brawler", "Folder Thing", "Unfetched", "No Genres"])
    check("the waiting games: installed, 'never' or 'under', not hidden, not a tool, not Finished or Dropped",
          found == want, found)
    backlog = {r["name"]: r["state"] for r in backlog_rows}
    check("they are report 4's own rows: its query, its 'never' or 'under' (BACKLOG_STATE), no second copy",
          all(backlog.get(r["name"]) == r["state"] and r["state"] in ("never", "under") for r in rows)
          and backlog.get("Epic Thing") == "unknown" and backlog.get("Hollow Deep") == "played"
          and not any("BACKLOG_STATE" in q or "CASE WHEN i.launch_kind" in q for q in recommend_queries.QUERIES.values())
          and 'source.rows("backlog")' in (PROJECT / "logic" / "recommend.py").read_text(encoding="utf-8"),
          {r["name"]: (r["state"], backlog.get(r["name"])) for r in rows})
    check("played in the last 7 days come apart, by the launcher's own date", lately == ("Lately",), lately)
    lengths = source.rows("session_lengths_by_game")
    by = {}
    for r in lengths:
        by.setdefault(r["name"], []).append(r["minutes"])
    check("the sessions: both origins, a tool's never, an uninstalled game's still there",
          sorted(by.get("Empire Lines", [])) == [90, 100, 110, 200] and "A Tool" not in by and "Gone Game" in by, by)
except Exception as exc:
    unreached("2", exc)

print("\n=== 3. the ranking ===")
try:
    built = recommend.page(planted.store.recommend(), 60, now=NOW)
    order = [s.name for s in built.picks + built.more]
    check("ranked by the fit, a tie to the name: Alpha before Zeta, then Strategy, then Action alone",
          order == ["Alpha Quest", "Zeta Quest", "Siege Plans", "Brawler"], order)
    shares = [round(s.share, 3) for s in built.picks + built.more]
    check(f"the shares, worked out by hand: 93%, 93%, 35%, 29% ({shares})",
          [round(s * 100) for s in shares] == [93, 93, 35, 29], shares)
    src = planted.store.recommend()
    profile = fit_module.profile_of(src.rows("wishlist_profile"))
    check("report 9's taste from report 1's rows is the very profile the wishlist reads",
          fit_module.profile_from(src.rows("concentration"), src.rows("recommend_genres")) == profile and profile,
          (len(profile),))
    weights = fit_module.weights_of(src.rows("wishlist_idf"))
    again = fit_module.fit([(1, "Action"), (3, "RPG")], profile, True, weights)
    check("the words are the fit's own, Phase 89's", built.picks[0].reason == again.words
          and built.picks[0].reason.startswith("93% like what you play · "), (built.picks[0].reason, again.words))
    check("three large, the rest a line each", len(built.picks) == rules.FORYOU_GAMES and len(built.more) == 1
          and built.beyond == 0)
    check("each says what was played: never, or the time", [s.played for s in built.picks + built.more]
          == ["never played", "never played", "30 min played", "10 min played"])
    saved = rules.FORYOU_MORE
    rules.FORYOU_MORE = 0
    try:
        fewer = recommend.page(planted.store.recommend(), 60, now=NOW)
    finally:
        rules.FORYOU_MORE = saved
    check("past the lines, how many more", fewer.more == () and fewer.beyond == 1)
except Exception as exc:
    unreached("3", exc)

print("\n=== 4. honest words ===")
try:
    check("no Steam app, no record, no genres: named apart, never ranked",
          sorted(built.cold) == ["Folder Thing", "No Genres", "Unfetched"]
          and not any(s.name in built.cold for s in built.picks + built.more), built.cold)
    check("and said so in one sentence", built.cold_line ==
          "3 waiting games have no genres to compare by: Folder Thing, No Genres, Unfetched.", built.cold_line)
    check("the game played lately is left out, and named", built.recent == ("Lately",)
          and built.recent_line == "Played in the last 7 days, so not offered here: Lately.", built.recent_line)
    later = recommend.page(planted.store.recommend(), 60, now=NOW + timedelta(days=8))
    check("a week later it is waiting again", "Lately" in [s.name for s in later.picks + later.more])
    first = Made("first")
    first.game("Fresh A", 401, (1,))
    first.game("Fresh B", 402, (2,))
    first.done()
    fresh = recommend.page(first.store.recommend(), 60, now=NOW)
    check("nothing played yet: nothing ranked, every waiting game named, the reason the real one",
          fresh.picks == () and fresh.compared is False and fresh.cold_line ==
          "Nothing you have played has genres to compare by yet, so 2 waiting games cannot be ranked: Fresh A, Fresh B.",
          fresh.cold_line)
    check("and Tonight learns as you play", fresh.tonight.games == () and fresh.tonight.empty ==
          "No game has 3 sessions yet: Tonight learns how long you play as you play.", fresh.tonight.empty)
    empty = Made("empty")
    empty.game("Long Played", 501, (1,), minutes=300, last=ago(40))
    empty.game("All Done", 502, (1,), status=rules.STATUS_FINISHED)
    empty.done()
    nothing = recommend.page(empty.store.recommend(), 60, now=NOW)
    check("nothing waiting says why", nothing.empty == recommend.NOTHING_WAITING and nothing.picks == ())
    recent_only = Made("recent_only")
    recent_only.game("Long Played", 501, (1,), minutes=300, last=ago(40))
    recent_only.game("Just Now", 503, (1,), minutes=5, last=ago(1))
    recent_only.done()
    only = recommend.page(recent_only.store.recommend(), 60, now=NOW)
    check("everything waiting played lately says so too", only.empty == recommend.ALL_RECENT, only.empty)
    for store in (first, empty, recent_only):
        store.store.close()
except Exception as exc:
    unreached("4", exc)

print("\n=== 5. Tonight ===")
try:
    typical = built.typical
    hollow = typical["hollow deep"]
    check("the median of the sessions: 25 min of 20, 22, 25, 28, 30", hollow.median == 25 and hollow.judged
          and hollow.usual == "usually 25 min a session", (hollow.median, hollow.usual))
    check("Empire Lines' median counts the session seen running: 105 of 90, 100, 110, 200",
          typical["empire lines"].median == 105)
    check("two sessions are not enough to judge", not typical["siege plans"].judged)
    split = typical["split game"]
    check("a game's two records joined by its name: three sessions, played from the installed one",
          split.sessions == 3 and split.judged and split.offered and split.key == key_of(planted, "Split Game"))
    check("an uninstalled game and a Dropped one are never offered", not typical["gone game"].offered
          and not typical["dropped one"].offered)
    tonight = {m: recommend.tonight(typical, m) for m, *_ in rules.TONIGHT_CHOICES}
    names = {m: [t.name for t, _w in t30.games] for m, t30 in tonight.items()}
    check("30 min: only Hollow Deep (median 25)", names[30] == ["Hollow Deep"], names[30])
    check("an hour: both fit every time; the one played last first", names[60] == ["Split Game", "Hollow Deep"],
          names[60])
    check("two hours: Empire Lines too, last -- 3 of its 4 fit", names[120] == ["Split Game", "Hollow Deep",
                                                                            "Empire Lines"], names[120])
    check("the words: how many sessions, how many fit", [w for _t, w in tonight[120].games] ==
          ["3 sessions, all within two hours", "5 sessions, all within two hours", "4 sessions, 3 within two hours"],
          [w for _t, w in tonight[120].games])
    check("at most three", all(len(t.games) <= rules.FORYOU_TONIGHT for t in tonight.values()))
    check("judged on three games, said once", tonight[60].judged == 3
          and tonight[60].note == "Judged on 3 games you have played 3 times or more", tonight[60].note)
    long = {"x": recommend.Typical("Long One", "k", (100, 100, 100), "2026-10-01", True)}
    check("nothing fits says so", recommend.tonight(long, 30).empty ==
          "Nothing you have played 3 times or more usually fits within 30 minutes.", recommend.tonight(long, 30).empty)
    check("the four choices, and anything else the default hour",
          [c[1] for c in rules.TONIGHT_CHOICES] == ["30 min", "1 h", "2 h", "An evening"]
          and recommend.choice_of(999)[0] == rules.TONIGHT_DEFAULT == 60 and recommend.choice_of(None)[0] == 60
          and recommend.choice_of(180)[1] == "An evening")
except Exception as exc:
    unreached("5", exc)

print("\n=== 6. a game's page: the pill and the fact ===")
try:
    pill, fact = recommend.facts_for(built, key_of(planted, "Hollow Deep"))
    check("a game judged: its pill; played two hours and more, no fit", pill == "Usually 25 min a session"
          and fact == "", (pill, fact))
    pill, fact = recommend.facts_for(built, key_of(planted, "Alpha Quest"))
    check("a waiting game: its fit in the page's own words; no sessions, no pill",
          pill == "" and fact == built.picks[0].reason, (pill, fact))
    pill, _fact = recommend.facts_for(built, key_of(planted, "Siege Plans"))
    check("two sessions: no pill", pill == "")
    order = [f for f, _g in ui_detail.PILLS]
    check("the pill sits after the size (since the Phase 102 extension: Last played, Played, Installed side by "
          "side), with the history icon", order[1:5] == ["Last played", "Played", "Installed", "Usually"]
          and dict(ui_detail.PILLS)["Usually"] == "history", order)
except Exception as exc:
    unreached("6", exc)

planted.store.close()

print("\n=== 7. the place ===")
try:
    window = ui_window.MainWindow()
    window.detail.allow_network = False
    window.resize(1440, 900)
    window.show()
    window.raise_()
    window.activateWindow()
    settle(1.2)
    window._stop_watch()
    FOR = getattr(ui_window, "FORYOU_PAGE", -1)
    check("the top bar: For you after Library", [n for n, _l in ui_topbar.TABS][:2] == ["library", "foryou"]
          and window.top_bar.tabs["foryou"].text() == "For you")
    check("the rail: under Library, a sparkle of its own", [n for n, _l, _g in ui_rail.NAV][:2] == ["library", "foryou"]
          and ui_icons.PHOSPHOR["foryou"][1:] == ("sparkle", 0xE6A2))
    check("the page header's tabs start with it", [n for n, _l in ui_pageshell.TABS][0] == "foryou")
    check("and the pad's walk: Library, For you, Stats, ...", ui_window.TAB_SEQUENCE[:3] ==
          (ui_window.LIBRARY_PAGE, FOR, ui_window.STATS_PAGE))
    window.rail.places["foryou"].click()
    settle(0.8)
    check("the rail's place opens the page, lit", window.stack.currentIndex() == FOR
          and window.rail.places["foryou"].isChecked())
    window.show_library()
    settle(0.6)
    window.top_bar.tabs["foryou"].click()
    settle(0.8)
    check("so does the bar's tab", window.stack.currentIndex() == FOR and window.top_bar.tabs["foryou"].isChecked())
    model = window.foryou_page.model
    check("the page is For you's own answer, from the window's store", model is not None
          and window.foryou_page.page_title.text() == "For you")
    before = box.read_json("config.json")
    chip = window.foryou_page.chips[120]
    chip.click()
    settle(0.4)
    after = box.read_json("config.json")
    check("a chip: Tonight's choice remembered by its own key, nothing else in config.json changed",
          after.get(rules.FORYOU_TONIGHT_KEY) == 120
          and {k: v for k, v in after.items() if k != rules.FORYOU_TONIGHT_KEY}
          == {k: v for k, v in before.items() if k != rules.FORYOU_TONIGHT_KEY}
          and window.foryou_page.model.tonight.minutes == 120)
    window.show_library()
    settle(0.4)
    window.show_foryou()
    settle(0.6)
    check("and the next visit opens on it", window.foryou_page.model.tonight.minutes == 120
          and window.foryou_page.chips[120].isChecked())
    window.foryou_page.chips[60].click()
    settle(0.4)
except Exception as exc:
    unreached("7", exc)

print("\n=== 8. the pad ===")
try:
    window.show_library()
    settle(0.6)
    press(window, controller.STATS)
    walk = [window.stack.currentIndex()]
    press(window, controller.LEFT)
    walk.append(window.stack.currentIndex())
    check("View opens Stats, left walks to For you", walk == [ui_window.STATS_PAGE, FOR], walk)
    page = window.foryou_page
    check("the ring starts on the first game", page.rows and page.focusWidget() is page.rows[0][0]
          and page.focus_ring.target is page.rows[0][0])
    check("the hints are For you's", window.hint_bar.labels == [label for _p, label in ui_tv.HINT_SETS[ui_tv.FORYOU]]
          if hasattr(window.hint_bar, "labels") else True)
    if len(page.rows[0]) > 1:
        press(window, controller.RIGHT, 0.3)
        check("right moves along the row", page.focusWidget() is page.rows[0][1])
        press(window, controller.LEFT, 0.3)
    press(window, controller.DOWN, 0.3)
    check("down moves to the next row", page.focusWidget() is page.rows[1][0], page.focusWidget())
    press(window, controller.UP, 0.3)
    check("up back", page.focusWidget() is page.rows[0][0])
    played: list[str] = []
    real_play = ui_actions.play
    ui_actions.play = lambda win, view: played.append(view.key)
    try:
        press(window, controller.ACTIVATE)
    finally:
        ui_actions.play = real_play
    check("A plays the game the ring is on -- the play captured, nothing started",
          played == [page.current_key()] and played[0] == model.picks[0].key, played)
    menus: list = []

    def close_menu():
        popup = QApplication.activePopupWidget()
        menus.append([a.text() for a in popup.actions() if a.text()] if popup is not None else None)
        if popup is not None:
            window.pads.action.emit(controller.BACK)

    QTimer.singleShot(700, close_menu)
    press(window, controller.MENU, 1.4)
    check("X opens the game's menu, Details first, Play next; B closes it",
          menus and menus[0] and menus[0][:2] == ["Details", "Play"] and QApplication.activePopupWidget() is None
          and window.stack.currentIndex() == FOR, menus)
    now = page.model.tonight.minutes
    press(window, controller.SURPRISE, 0.4)
    check("Y moves Tonight's choice along, the ring kept on its game", page.model.tonight.minutes == 120 and now == 60
          and page.focusWidget() is page.rows[0][0], (now, page.model.tonight.minutes, page.focusWidget()))
    for _ in range(3):
        press(window, controller.SURPRISE, 0.3)
    check("and round to the first and on", page.model.tonight.minutes == 60)
    chips_row = next(i for i, row in enumerate(page.rows) if row and row[0] in page.chips.values())
    for _ in range(chips_row):
        press(window, controller.DOWN, 0.2)
    check("down to the chooser lands on the chosen chip", page.focusWidget() is page.chips[60], page.focusWidget())
    press(window, controller.RIGHT, 0.4)
    check("right on the chooser chooses the next", page.model.tonight.minutes == 120
          and page.focusWidget() is page.chips[120])
    press(window, controller.LEFT, 0.4)
    press(window, controller.LEFT, 0.4)
    press(window, controller.LEFT, 0.6)
    check("past the first chip, left walks to the library", window.stack.currentIndex() == ui_window.LIBRARY_PAGE)
    window.show_foryou()
    settle(0.6)
    last = page.rows[0][-1]
    last.setFocus()
    press(window, controller.RIGHT, 0.6)
    check("past the end of a row, right walks to Stats", window.stack.currentIndex() == ui_window.STATS_PAGE)
    window.show_foryou()
    settle(0.6)
    press(window, controller.BACK)
    check("B goes back to the library", window.stack.currentIndex() == ui_window.LIBRARY_PAGE)
    window.show_foryou()
    settle(0.6)
    details = [b for b in page.rows[0][0].findChildren(QPushButton) if b.objectName() == "ForYouDetails"]
    details[0].click()
    settle(1.2)
    check("Details opens the game's page", window.stack.currentIndex() == ui_window.DETAIL_PAGE
          and window.detail.view.key == model.picks[0].key)
    check("which carries its fit, in For you's words", window.detail._fact_values.get(ui_detail.FIT_FACT)
          == model.picks[0].reason, window.detail._fact_values.get(ui_detail.FIT_FACT))
    judged = next((t for t in model.typical.values() if t.judged and t.offered and t.key in window.by_key), None)
    if judged is not None:
        window.show_detail(judged.key)
        settle(1.0)
        pill = window.detail.pills["Usually"]
        check(f"a game played often carries its pill: {judged.pill!r}", not pill.isHidden() and pill.value == judged.pill,
              (pill.isHidden(), getattr(pill, "value", None)))
    rare = next((k for k, v in window.by_key.items()
                 if model.typical.get(model.keys.get(k, "")) is None and k != model.picks[0].key), None)
    if rare is not None:
        window.show_detail(rare)
        settle(1.0)
        check("one with no sessions does not", window.detail.pills["Usually"].isHidden())
    window.show_library()
    settle(0.6)
except Exception as exc:
    unreached("8", exc)

print("\n=== 9. rendered ===")
try:
    for label, layout, tv in (("rail", "rail", False), ("top bar", "top", False), ("TV", "top", True)):
        window.config["library_layout"] = layout
        window.set_tv_mode(tv)
        settle(1.2)
        window._apply_layout()
        window.show_foryou()
        settle(1.0)
        page = window.foryou_page
        bar = page.scroll.horizontalScrollBar()
        column = page.content
        right = column.mapTo(window, column.rect().topRight()).x()
        check(f"{label}: nothing to scroll sideways, the column inside the window",
              bar.maximum() == 0 and right <= window.width(), (bar.maximum(), right, window.width()))
        ring = page.focus_ring
        check(f"{label}: the ring on the first game, drawn", ring.target is page.rows[0][0] and ring.isVisible())
        if tv:
            check("TV: the hint bar says what For you's buttons do",
                  getattr(window.hint_bar, "labels", None) == [w for _p, w in ui_tv.HINT_SETS[ui_tv.FORYOU]],
                  getattr(window.hint_bar, "labels", None))
        window.grab().save(str(WORK / f"foryou_{label.replace(' ', '_')}.png"))
    window.set_tv_mode(False)
    window.config["library_layout"] = "rail"
    settle(1.0)
    window._apply_layout()
    widest = 0
    from presentation import ui_theme
    from presentation import ui_rules
    for scale in ui_rules.TV_SCALE_CHOICES:
        app.setStyleSheet(ui_theme.stylesheet(scale) + ui_tv.stylesheet(scale))
        hints = ui_tv.HintBar(ui_theme.Metrics(scale))
        hints.set_power(rules.POWER_WIRED)
        hints.set_hints(ui_tv.FORYOU)
        widest = max(widest, hints.sizeHint().width())
    check(f"For you's hints fit 1920 at every TV size (widest {widest})", widest <= 1920, widest)
    check("Stats says For you is on its left now", (ui_tv.ACROSS, "For you / Storage") in ui_tv.HINT_SETS[ui_tv.STATS])
    # The sixth place made the rail taller than a short window: "Found in" folds away rather than push it.
    window.show_library()
    settle(0.5)
    rail = window.rail
    full = rail.minimumHeight() + rail._height_of(rail._found_in())
    window.resize(1280, 600)
    settle(0.8)
    foot = rail.settings.mapTo(window, rail.settings.rect().bottomLeft()).y()
    check(f"a short window keeps its height ({window.height()} px, the whole rail {full}): Found in folds away, "
          "the places, the filters and the foot all there", window.height() < full
          and all(w.isHidden() for w in rail._found_in()) and not rail.places["foryou"].isHidden()
          and not rail.filters["all"].isHidden() and foot <= window.height(), (window.height(), full, foot))
    window.resize(1280, full + 140)
    settle(0.8)
    if window.height() >= full:
        check(f"a tall one shows it again ({window.height()} px)", not any(w.isHidden() for w in rail._found_in()))
    window.resize(1440, 900)
    settle(0.5)
except Exception as exc:
    unreached("9", exc)

print("\n=== 10. on the copy of the user's library ===")
try:
    source = window.overrides.recommend()
    started = time.perf_counter()
    real = recommend.page(source, 60)
    spent = (time.perf_counter() - started) * 1000
    kept, lately = recommend.waiting(source.rows("backlog"), recommend.recent_since())
    candidates = kept + list(lately)
    shown = len(real.picks) + len(real.more) + real.beyond + len(real.cold) + len(real.recent)
    check(f"every waiting game is ranked, named apart or named as played lately ({shown} of {len(candidates)})",
          shown == len(candidates), (shown, len(candidates)))
    check("no waiting game is scored zero for want of genres", all(s.share is not None for s in real.picks + real.more))
    check(f"worked out in {spent:.1f} ms (under 40)", spent < 40, spent)
    judged = [t for t in real.typical.values() if t.offered and t.judged]
    check(f"Tonight judged on {len(judged)} games, every one with 3 sessions or more",
          real.tonight.judged == len(judged) and all(t.sessions >= rules.SESSION_MEDIAN_MIN for t in judged))
    check("the anonymous export knows nothing of it", "recommend" not in (PROJECT / "logic" / "analysis.py")
          .read_text(encoding="utf-8"))
    import subprocess
    result = subprocess.run([sys.executable, str(PROJECT / "tests" / "check_layers.py")], capture_output=True,
                            text=True, encoding="utf-8", errors="replace", cwd=str(PROJECT))
    check("no import points up a layer, sqlite3 only in data_access/",
          "upward imports: 0" in result.stdout and "sqlite3 outside data_access/: 0" in result.stdout, result.stdout[-300:])
    check("nothing on the page or in its logic reaches the network", not any(
        re.search(r"^\s*(from|import) (web|urllib|requests|http)\b", (PROJECT / rel).read_text(encoding="utf-8"), re.M)
        for rel in ("logic/recommend.py", "logic/fit.py", "presentation/ui_foryou.py", "data_access/recommend.py")))
except Exception as exc:
    unreached("10", exc)

print("\n=== 11. report 9, Recommendation, on the planted library ===")
try:
    store = library_db.LibraryStore(planted.path)
    nine = reports_module.build(store.reports())
    report = nine[8]  # a tenth follows it since Phase 102
    check("eleven reports (since Phase 103), the ninth Recommendation", len(nine) == 11 and len(reports_module.BUILDERS) == 11
          and (report.number, report.key, report.title) == (9, "recommendation", "Recommendation"))
    check(f"its sentence names the first two, tied: {report.sentence[:90]!r}...",
          report.sentence.startswith("Of 4 waiting games that can be compared, Alpha Quest and Zeta Quest come "
                                     "first, 93% like what you play; "), report.sentence)
    ranking = report.parts[0]
    check("the ranking: rank, game, fit, genres, played", [r[:3] for r in ranking.rows] ==
          [("1", "Alpha Quest", "93%"), ("2", "Zeta Quest", "93%"), ("3", "Siege Plans", "35%"),
           ("4", "Brawler", "29%")] and "no genres to compare by" in ranking.note and "Lately" in ranking.note,
          ranking.rows)
    typical = report.parts[1]
    check("the typical sessions: every game judged, by its median, the uninstalled and the Dropped not offered",
          [(r[0], r[2], r[5]) for r in typical.rows] == [("Dropped One", "10 min", "no"), ("Gone Game", "10 min", "no"),
                                                         ("Hollow Deep", "25 min", "yes"), ("Split Game", "40 min", "yes"),
                                                         ("Empire Lines", "1h 45m", "yes")]
          and typical.note.startswith("Judged on 5 games with 3 sessions or more; 3 more have fewer."),
          (typical.rows, typical.note))
    back = report.parts[2]
    by = {r[0]: r for r in back.data}
    check("the look back, by hand: Dropped One 2nd of 10, Hollow Deep 4th of 9, Empire Lines 7th of 7, "
          "Siege Plans 8th of 8", [(by[n][2], by[n][3]) for n in ("Dropped One", "Hollow Deep", "Empire Lines",
                                                                    "Siege Plans")] == [(2, 10), (4, 9), (7, 7), (8, 8)],
          {n: by[n][2:4] for n in by})
    check("each in the fit's own words, never 0%: Siege Plans unlike what you had played",
          by["Siege Plans"][4] == "unlike what you had played" and by["Dropped One"][4] == "100% like what you had played")
    check("the first game played has nothing before it to compare with; Split Game has no genres",
          by["Gone Game"][4] == recommend.NO_PAST and by["Split Game"][4] == recommend.NO_GENRES)
    check("one played the day it arrived was never waiting, and said so", by["Same Day"][4] == recommend.SAME_DAY
          and by["Same Day"][2] is None)
    check("one played before it was first seen is left out, and counted", "Early Bird" not in by
          and "played before it was first seen, 1" in back.note, back.note)
    check("the sentence's look back: 1 of 4 evenings among the first three, its mean rank 5.2, too few",
          "among the first 3 on 1 of 4 evenings it could be ranked, its mean rank 5.2 — too few to say whether "
          "the fit foretells anything." in report.sentence, report.sentence)
    games = [{"game_id": 1, "name": "Counted", "steam_appid": 900, "first_seen_local": "2026-08-01T10:00:00",
              "first_played": "2026-09-01T10:00:00", "steam_counted": 1}]
    looked = recommend.retrospective(games, [], [{"appid": 900, "genre_id": 1, "name": "Action"}],
                                     [{"genre_id": 1, "apps": 1, "corpus": 2}])
    check("a game Steam counts hours for is left out: its first play may come before the launcher's",
          looked.cases == () and looked.left_out == (("Steam counts its hours", 1),), looked)
    empty_store = library_db.LibraryStore(WORK / "empty9.db")
    lonely = reports_module.build(empty_store.reports())
    check("an empty library answers all eleven (since Phase 103) in words", [r.empty for r in lonely] == [True] * 11
          and lonely[8].sentence.startswith("Nothing is installed and nothing has been played yet"),
          [r.empty for r in lonely])
    empty_store.close()
    data = reports_module.fetch(store.reports())
    pubs = [r["label"] for r in data["profile_publishers"]]
    check("report 3's two lists come from one run of its query, split by the role",
          data_reports.QUERIES["profile_companies"].count("SELECT c.role") == 1
          and all(r["role"] == "publisher" for r in data["profile_publishers"])
          and all(r["role"] == "developer" for r in data["profile_developers"]), pubs)
    store.close()
except Exception as exc:
    unreached("11", exc)

print("\n=== 12. the nine together, on the copy; the Reports page ===")
try:
    copy_reports = window.overrides.reports()
    timings = []
    for _ in range(5):
        began = time.perf_counter()
        built_nine = reports_module.build(copy_reports)
        timings.append((time.perf_counter() - began) * 1000)
    check(f"the eleven reports (since Phase 103): best of 5 {min(timings):.1f} ms, under 50", min(timings) < 50, timings)
    check("report 9 on the copy says what is waiting and looks back", built_nine[8].key == "recommendation"
          and not built_nine[8].empty and len(built_nine[8].parts) == 3, built_nine[8].sentence)
    md = reports_module.markdown(built_nine, datetime.now(), data_reports.QUERIES)
    check("the Markdown carries ## 9. and every query report 9 is built from, as the code has them",
          "## 9. Recommendation" in md and all(data_reports.QUERIES[n] in md for n in built_nine[8].queries))
    from presentation import ui_reports
    check("the Reports page says eleven questions (since Phase 103)", ui_reports.INTRO.startswith("Eleven questions"))
    window.config["library_layout"] = "rail"
    window._apply_layout()
    window.show_reports()
    settle(1.2)
    cards =[c for c in window.reports_page.cards if getattr(c, "report", None) is not None]
    check("and shows a ninth card, Recommendation, before the tenth (Phase 102)",
          len(cards) == 11 and cards[8].report.key == "recommendation", [c.report.key for c in cards])
    window.reports_page.scroll.ensureWidgetVisible(cards[8])
    settle(0.6)
    window.grab().save(str(WORK / "reports_nine.png"))
    window.show_library()
    settle(0.4)
except Exception as exc:
    unreached("12", exc)

print("\n=== 13. the documents ===")
try:
    def doc(rel):
        return (PROJECT / rel).read_text(encoding="utf-8")
    claude = doc("CLAUDE.md")
    check("CLAUDE.md has the phase and its modules", "| 98 |" in claude and "ui_foryou.py" in claude
          and "  fit.py" in claude and claude.count("recommend.py") >= 2)
    arch = doc("docs/ARHITECTURA.md")
    check("ARHITECTURA has For you in its maps, and report 9 in 5.5", "ui_foryou.py" in arch and "logic/fit.py" in arch
          and "recommend.py" in arch and "Raportul 9, Recomandarea" in arch)
    analysis = doc("docs/ANALIZA.md")
    quoted = dict(re.findall(r"```sql\n-- (\w+)\n(.*?)\n```", analysis, re.S))
    nine = ("backlog", "concentration", "recommend_genres", "wishlist_idf", "session_lengths_by_game",
            "recommend_history", "money_lowest", "profile_companies")
    check("ANALIZA: unsprezece rapoarte (since Phase 103), its ninth section, every query report 9 reads quoted as "
          "the code has it", analysis.startswith("# Ce poate spune baza de date: unsprezece rapoarte") and "## 9. Recomandarea" in analysis
          and "(#9-recomandarea)" in analysis and all(quoted.get(n) == data_reports.QUERIES[n] for n in nine),
          [n for n in nine if quoted.get(n) != data_reports.QUERIES[n]])
    check("ANALIZA names the ideas: content-based and collaborative filtering, the cold start, the median, "
          "offline evaluation", all(w in analysis for w in ("content-based filtering", "collaborative filtering",
                                                             "cold-start problem", "*median*", "offline evaluation",
                                                             "hit rate at 3", "mean rank")))
    readme = doc("docs/CITESTE-MA.md")
    check("CITESTE-MA: For you and the reports (unsprezece since Phase 103), still on its one page",
          "**For you** (sub Library)" in readme and "unsprezece rapoarte" in readme and " zece rapoarte" not in readme
          and len(readme.splitlines()) <= 110, len(readme.splitlines()))
    explained = doc("docs/explicatii/faza-98.md")
    check("docs/explicatii/faza-98.md, the same shape, the median beside the five words, the three questions",
          all(w in explained for w in ("## Ce s-a construit", "## De ce contează", "## Cum funcționează",
                                       "## Cinci cuvinte", "## Trei întrebări", "## Ce nu poate face", "**Mediana**",
                                       "De ce nu filtrare colaborativă?", "De unde știți că merge?",
                                       "Ce faceți cu jocurile fără genuri?"))
          and "faza 98" in doc("docs/explicatii/CITESTE-MA.md"))
    check("CLAUDE.md keeps the lesson of the 50 ms", "a new report reuses rows already fetched" in claude)
    check("nothing in this suite reached the network", attempts == [], attempts)
except Exception as exc:
    unreached("13", exc)

if "window" in globals():
    window._shut_down = True
    window.overrides.close()
changed = box.finish()
check("config.json, the library database and the Run key's value are unchanged", not changed, changed)
print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
