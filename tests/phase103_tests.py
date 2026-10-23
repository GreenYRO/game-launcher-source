"""Phase 103: Left behind -- a nudge for games marked Playing that nothing has been heard of -- and report 11,
Finishing.

  1. the rule (logic/recommend.left_behind), on rows made by hand: the days since the last counted session --
     or, with none, the last date of play from anywhere -- the mark's and the nudge's moments, the cap, the
     order, nothing for a game with no date at all, nothing when nothing is left behind;
  2. the query on a copy of the real library: every installed, shown, not-tool game marked Playing, its last
     counted session as the sessions hold it;
  3. the row in For you, on the copy: after Tonight, the longest left first, its words; the pad walks to it and
     the TV's hints say A answers; Still playing writes the nudge's moment and nothing else, Finished and
     Dropped the mark with its date; the row goes when it is empty; nothing announces a nudge;
  4. the game's page: "Finished since ..." under the switch when the mark is dated, nothing when it is not,
     in the room above the first card;
  5. a test copy never starts one of the user's games (only a suite's fake game, made in the temp folder);
  6. report 11 on a planted history worked out by hand: the counts, the rate with its size, the median and
     Kaplan-Meier's with the censored, with and without an undated mark, the hours, the caveat's words;
  7. the eleven reports on the copy, every query's answer the same with the hours worked out once, the copies
     gone after, under 50 ms, on a read-only connection too; the Markdown; the Reports page;
  8. the documents and the layers.

On a throwaway copy of the data; the network is blocked; the user's config and library are photographed at
the start and compared at the end.
"""
import sqlite3
import sys
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import sources  # the build log's notes (Phase 91)
import test_sandbox

box = test_sandbox.start({"allow_network": False, "startup_scan": False, "tv_mode": False})
attempts: list[str] = []


def no_network(request, *args, **kwargs):
    attempts.append(getattr(request, "full_url", str(request)))
    raise OSError("the network is blocked in this suite")


urllib.request.urlopen = no_network

from PySide6.QtCore import QEventLoop, QPoint, QTimer
from PySide6.QtWidgets import QApplication

app = QApplication([])

from adapters import controller
from logic import recommend, sessions
from presentation import ui_actions, ui_foryou, ui_rules, ui_tv, ui_window
from shared import humanize, rules

passed = failed = 0
NOW = datetime.now().astimezone().replace(microsecond=0)


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"   PASS  {name}")
    else:
        failed += 1
        print(f"   FAIL  {name}   {detail}")


def unreached(section, exc):
    global failed
    failed += 1
    import traceback
    traceback.print_exc()
    print(f"   FAIL  section {section} runs to its end on this code   {exc!r}")


def settle(seconds):
    loop = QEventLoop()
    QTimer.singleShot(int(seconds * 1000), loop.quit)
    loop.exec()


def press(window, name: str, wait: float = 0.5) -> None:
    """A button as the hub sends it: emitted from inside a timer, queued to the window."""
    QTimer.singleShot(0, lambda: window.pads.action.emit(name))
    settle(wait)


def ago(days: float) -> str:
    return (NOW - timedelta(days=days)).isoformat(timespec="seconds")


def row(name, last=None, marked=None, nudged=None, minutes=0.0, **dates):
    return {"identity_key": name.lower(), "name": name, "steam_appid": None, "status_changed_at": marked,
            "nudged_at": nudged, "last_session": last, "last_played": dates.get("launcher"),
            "store_last_played": dates.get("store"), "steam_last_played": dates.get("steam"), "minutes": minutes}


print("=== 1. the rule ===")
try:
    days = rules.LEFT_BEHIND_DAYS
    check(f"LEFT_BEHIND_DAYS {days}, LEFT_BEHIND_GAMES {rules.LEFT_BEHIND_GAMES}, from rules.py",
          (days, rules.LEFT_BEHIND_GAMES) == (30, 4))
    lb = recommend.left_behind
    check("a session exactly 30 days ago is left behind; 29 days is not", [g.name for g in lb(
        [row("Thirty", ago(days)), row("TwentyNine", ago(days - 1))], NOW)] == ["Thirty"])
    found = lb([row("Townfall", ago(45), minutes=758)], NOW)
    check("its words: 'Left 45 days ago at 12h 38m' -- the hours as the reports count them",
          found and found[0].words == "Left 45 days ago at 12h 38m" and found[0].days == 45, found)
    check("with no hours known: 'Left 45 days ago', no 'at'", lb([row("None", ago(45))], NOW)[0].words
          == "Left 45 days ago")
    check("answered 'Still playing' 10 days ago: left alone", lb([row("Asked", ago(60), nudged=ago(10))], NOW) == ())
    check(f"answered {days + 1} days ago and still not played: asked again, the days counted from the play",
          [(g.name, g.days) for g in lb([row("Again", ago(60), nudged=ago(days + 1))], NOW)] == [("Again", 60)])
    check("a mark set 5 days ago is fresh: not left behind, however old the last session",
          lb([row("Marked", ago(90), marked=ago(5))], NOW) == ())
    check("an undated mark (from before version 8) does not hold it back", len(lb([row("Old", ago(40))], NOW)) == 1)
    check("no counted session: the newest date of play from anywhere -- Steam's 40 days, the store's 50",
          [(g.name, g.days) for g in lb([row("SteamOnly", steam=ago(40), store=ago(50))], NOW)] == [("SteamOnly", 40)])
    check("no date of play at all: never asked about (unknown is not long ago)", lb([row("Never")], NOW) == ())
    many = [row(f"Game {n}", ago(30 + n * 3)) for n in range(6)] + [row("Alpha", ago(45)), row("Beta", ago(45))]
    order = [(g.name, g.days) for g in lb(many, NOW)]
    check(f"at most {rules.LEFT_BEHIND_GAMES}, the longest left first, a tie by name: {order}",
          order == [("Alpha", 45), ("Beta", 45), ("Game 5", 45), ("Game 4", 42)], order)
    check("nothing left behind: nothing at all", lb([], NOW) == () and lb([row("Fresh", ago(2))], NOW) == ())
except Exception as exc:
    unreached("1", exc)

print("\n=== 2. the query, on the copy ===")
window = None
try:
    window = ui_window.MainWindow()
    window.resize(1440, 1000)
    window.show()
    settle(1.5)
    window._stop_watch()
    store = window.overrides
    source = store.recommend()
    rows = source.rows("left_behind")
    raw = sqlite3.connect(f"file:{box.path('library.db').as_posix()}?mode=ro", uri=True)
    wanted = {key for key, in raw.execute(
        "SELECT v.identity_key FROM v_library v WHERE v.status = 'playing' AND v.installed = 1 AND v.hidden = 0 "
        "AND COALESCE(v.is_tool, 0) = 0")}
    last = dict(raw.execute("SELECT g.identity_key, MAX(s.started_at) FROM session s JOIN game g ON g.id = s.game_id "
                            "WHERE COALESCE(g.is_tool, 0) = 0 GROUP BY g.id"))
    raw.close()
    check(f"every installed, shown, not-tool game marked Playing ({len(wanted)}), and no other",
          {r["identity_key"] for r in rows} == wanted, [r["identity_key"] for r in rows])
    check("each with its last counted session as the sessions hold it",
          all(r["last_session"] == last.get(r["identity_key"]) for r in rows))
    check("and its hours as the reports count them (the store's own hours())",
          all(abs((r["minutes"] or 0) - (store.hours().get(r["identity_key"]) or {}).get("minutes", 0)) < 1e-9
              for r in rows))
except Exception as exc:
    unreached("2", exc)

print("\n=== 3. the row in For you ===")
try:
    # Three games marked Playing the old way (undated, as before version 8), their last session planted 52, 40 and
    # 10 days ago -- the third not left behind.
    free = [v for v in window.views if v.entry.launch_kind == "exe" and not v.status and not v.is_non_game
            and not store.ratings_of(v.key)]
    planted = list(zip(free[:3], (52, 40, 10)))
    # The copy's own Playing games answered "Still playing" a moment ago, so the row is the planted ones alone: the
    # user's library grows its own left behind as days pass (BloodBorne and Cinderia on 23 October), and a row of
    # two lines sent the pad's fixed walk past the first (Phase 107).
    answered_now = datetime.now().astimezone().isoformat(timespec="seconds")
    store.update_many({v.key: {rules.NUDGED_KEY: answered_now} for v in window.views
                       if v.status == rules.STATUS_PLAYING})
    for view, days_ago in planted:
        start = (NOW - timedelta(days=days_ago, minutes=90))
        kept = [e for e in sessions.load(store.get(view.key)) if e.start < start - timedelta(days=1)]
        store.update(view.key, **{rules.SESSIONS_KEY: sessions.dump(sessions.upsert(kept, start, 90,
                                                                                     rules.SESSION_LAUNCHED)),
                                  rules.STATUS_KEY: rules.STATUS_PLAYING})
    window.reload_views()
    told = []
    real_show = window.statusBar().showMessage
    window.statusBar().showMessage = lambda text, *a: told.append(text)
    balloons = []
    if getattr(window, "tray", None) is not None:
        window.tray.say = lambda *a, **k: balloons.append(a)
    window.show_foryou()
    settle(1.2)
    page = window.foryou_page
    names = [g.name for g in page.model.left]
    expect = [v.display_name for v, d in sorted(planted, key=lambda p: -p[1]) if d >= rules.LEFT_BEHIND_DAYS]
    check(f"Left behind: {names} -- the two left 30 days or more, the longest first; the one of 10 days not",
          names[:2] == expect and planted[2][0].display_name not in names, (names, expect))
    sections = [w.text() for w in page.findChildren(type(page.page_title)) if w.objectName() == "ForYouSection"]
    check("a section of its own after Tonight", "LEFT BEHIND" in sections
          and sections.index("LEFT BEHIND") > sections.index("TONIGHT"), sections)
    answers = [b for b in page.findChildren(ui_foryou._Answer)]
    check(f"three answers a game ({len(answers)}): Finished, Dropped, Still playing",
          len(answers) == 3 * len(names) and [b.text() for b in answers[:3]] == ["Finished", "Dropped", "Still playing"])
    cards = [w for w in page.findChildren(ui_foryou.QFrame) if w.objectName() == "ForYouLeft"]
    said = [[label.text() for label in card.findChildren(ui_foryou.QLabel)] for card in cards]
    check("each card names its game and says how long ago and at how many hours",
          len(cards) == len(page.model.left) and all(g.name in texts and g.words in texts
                                                      for texts, g in zip(said, page.model.left)), said)
    check("a nudge waits on the page: nothing announced it -- no message, no balloon", told == [] and balloons == [],
          (told, balloons))
    window.statusBar().showMessage = real_show

    # The pad: down to the answers, the TV's hints say A answers.
    window.activateWindow()
    settle(0.3)
    for _ in range(len(page.rows) + 2):  # down until the first answers, never past them
        if page.on_answer():
            break
        press(window, controller.DOWN, 0.25)
    first_row = next(r for r in page.rows if r and isinstance(r[0], ui_foryou._Answer))
    check("the pad walks down to Left behind's answers", page.on_answer() and page.focusWidget() in first_row,
          type(page.focusWidget()).__name__)
    check("and the TV's hints say A answers", window.hint_bar.hints == ui_tv.FORYOU_ANSWER
          and ui_tv.HINT_SETS[ui_tv.FORYOU_ANSWER][0][1] == "Answer", window.hint_bar.hints)

    # Still playing, with the pad: the nudge's moment and nothing else.
    first = page.model.left[0]
    while page.focusWidget().answer != "still":
        press(window, controller.RIGHT, 0.2)
    before = dict(store.get(first.key))
    press(window, controller.ACTIVATE, 0.8)
    after = dict(store.get(first.key))
    stamp = after.get(rules.NUDGED_KEY, "")
    changed = {k for k in set(before) | set(after) if before.get(k) != after.get(k)}
    check(f"A on Still playing: the nudge's moment written ({stamp[:16]}) and nothing else",
          changed == {rules.NUDGED_KEY} and abs((datetime.fromisoformat(stamp) - datetime.now().astimezone())
                                                 .total_seconds()) < 60, changed)
    check("the mark stays Playing, undated as it was", after.get(rules.STATUS_KEY) == rules.STATUS_PLAYING
          and after.get(rules.STATUS_CHANGED_KEY) == before.get(rules.STATUS_CHANGED_KEY))
    check("and the game leaves the row", first.key not in [g.key for g in page.model.left], [g.name for g in page.model.left])

    # Finished, with the mouse: the mark, dated.
    second = page.model.left[0]
    button = next(b for b in page.findChildren(ui_foryou._Answer) if b.key == second.key and b.answer == "finished")
    button.click()
    settle(0.8)
    marked = store.get(second.key)
    check("a click on Finished: the mark set, with its date", marked.get(rules.STATUS_KEY) == rules.STATUS_FINISHED
          and abs((datetime.fromisoformat(marked[rules.STATUS_CHANGED_KEY]) - datetime.now().astimezone())
                  .total_seconds()) < 60 and rules.NUDGED_KEY not in marked, marked)
    sections = [w.text() for w in page.findChildren(type(page.page_title)) if w.objectName() == "ForYouSection"]
    left_now = page.model.left
    check("the row is away when nothing is left to nudge" if not left_now else "the row holds what is left",
          ("LEFT BEHIND" in sections) == bool(left_now), (sections, [g.name for g in left_now]))
    # A nudge answered is kept in the library: the database itself holds it.
    raw = sqlite3.connect(f"file:{box.path('library.db').as_posix()}?mode=ro", uri=True)
    held = raw.execute("SELECT nudged_at FROM game WHERE identity_key = ?", (first.key,)).fetchone()[0]
    raw.close()
    check("the database holds the nudge's moment (game.nudged_at)", held == stamp, (held, stamp))
    # Dropped, from a planted third left behind -- rows of the hand rule, through the window's own answer.
    third = planted[2][0]
    window._answer_left_behind(third.key, rules.STATUS_DROPPED)
    settle(0.5)
    check("Dropped: the mark, dated", store.get(third.key).get(rules.STATUS_KEY) == rules.STATUS_DROPPED
          and store.get(third.key).get(rules.STATUS_CHANGED_KEY))
    window.show_library()
    settle(0.4)
except Exception as exc:
    unreached("3", exc)

print("\n=== 4. the game's page: since when ===")
try:
    dated = planted[1][0]  # Finished above, dated
    window.show_detail(dated.key)
    settle(1.0)
    page = window.detail
    label = page.mark_since
    when = humanize.day(datetime.fromisoformat(store.get(dated.key)[rules.STATUS_CHANGED_KEY]))
    check(f"a dated mark: '{label.text()}' under the switch", label.isVisible()
          and label.text() == f"Finished since {when}", label.text())
    bar = page.segment_bar
    bar_foot = bar.mapTo(page.banner, QPoint(0, bar.height())).y()
    check("below the switch, inside the picture -- above the first card", label.y() >= bar_foot
          and label.geometry().bottom() < page.banner.height(), (label.geometry(), bar_foot, page.banner.height()))
    cover_foot = page.cover_art.mapTo(page.banner, QPoint(0, page.cover_art.height())).y() - page.cover_art.room_bottom
    play_foot = page.play_button.mapTo(page.banner, QPoint(0, page.play_button.height())).y()
    check("and the Play row where it was: its foot DETAIL_INFO_FOOT above the cover's (the line takes no room)",
          abs(cover_foot - play_foot - round(ui_rules.DETAIL_INFO_FOOT * window.metrics.scale)) <= 1,
          (play_foot, cover_foot))
    undated = next(v for v in window.views if v.status and not v.status_since) if any(
        v.status and not v.status_since for v in window.views) else None
    if undated is not None:
        window.show_detail(undated.key)
        settle(0.8)
        check(f"an undated mark ({undated.display_name}, from before version 8): no line", label.isHidden())
    plain = next(v for v in window.views if not v.status)
    window.show_detail(plain.key)
    settle(0.8)
    check("no mark: no line", label.isHidden())
    window.show_library()
    settle(0.4)
except Exception as exc:
    unreached("4", exc)

print("\n=== 5. a test copy never starts a game ===")
try:
    from logic import launch
    refused_file = box.folder / test_sandbox.TEST_COPY_STARTS
    exe_game = next(v for v in window.views if v.entry.launch_kind == "exe")
    uri_game = next((v for v in window.views if v.entry.launch_kind == "uri"), None)
    result = launch.launch_game(exe_game)
    check(f"asked to start {exe_game.display_name} in a test copy: answered as if started, nothing to time",
          result.ok and result.running is None, result)
    if uri_game is not None:
        launch.launch_game(uri_game)
    elevated = launch.launch_elevated(exe_game)
    noted = refused_file.read_text(encoding="utf-8").splitlines() if refused_file.is_file() else []
    check("each refused start written into the copy's folder -- the store game's link and the elevated retry too",
          len(noted) == (3 if uri_game is not None else 2) and noted[0].startswith(exe_game.display_name + "\t")
          and elevated.ok, noted)
    check("and the copy names itself in the launcher's own variable",
          __import__("os").environ.get(rules.TEST_COPY_ENV) == str(box.folder)
          and rules.TEST_COPY_ENV == test_sandbox.TEST_COPY_ENV and rules.TEST_COPY_STARTS == test_sandbox.TEST_COPY_STARTS)
    refused_file.unlink()  # planted on purpose: the end of the suite would report it, as it reports a slip
    import tempfile
    from data_access import catalog_io
    from shared.models import GameEntry
    fake_home = Path(tempfile.mkdtemp(prefix="p103_fake_"))
    fake = catalog_io.GameView(GameEntry(
        source="folders", source_id=str(fake_home / "x.exe"), display_name="p103 fake game",
        install_dir=str(fake_home), launch_kind="exe", launch_target=sys.executable, working_dir=str(fake_home),
        icon_hint="", size_on_disk=0, detection="heuristic"), {})
    check("a suite's own fake game -- its folder in the temp folder -- may still start (28, 92 and 93 time them)",
          launch._refused_in_a_test_copy(fake) is None and not refused_file.is_file())
    check("the user's game beside it may not", launch._refused_in_a_test_copy(exe_game) is not None)
    refused_file.unlink(missing_ok=True)
except Exception as exc:
    unreached("5", exc)

print("\n=== 6. report 11, Finishing, worked out by hand ===")
try:
    from logic import reports as reports_module
    T = "T20:00:00+03:00"

    def mark(name, status, first, marked=None, last=None, gid=None):
        return {"identity_key": name.lower(), "name": name, "appid": None, "game_id": gid, "status": status,
                "installed": 1, "launch_kind": "exe", "status_changed_at": marked + T if marked else None,
                "nudged_at": None, "first_session": first + T, "last_session": (last or first) + T,
                "last_played": None, "store_last_played": None, "steam_last_played": None}

    history = [mark("A", "finished", "2026-08-01", "2026-08-11", gid=1),
               mark("B", "finished", "2026-08-01", "2026-08-31", gid=2),
               mark("C", "finished", "2026-07-01", None, gid=3),
               mark("D", "dropped", "2026-08-01", "2026-08-06", gid=4),
               mark("E", "playing", "2026-08-01", last="2026-08-05", gid=5),
               mark("F", "playing", "2026-08-21", last="2026-09-08", gid=6)]
    hours_rows = [{"appid": None, "game_id": g, "minutes": m, "name": n} for g, m, n in
                  ((1, 1200, "A"), (2, 300, "B"), (3, 480, "C"), (4, 60, "D"), (5, 180, "E"), (6, 120, "F"))]
    when = datetime.fromisoformat("2026-09-10" + T)
    km = reports_module.kaplan_meier_median
    check("Kaplan-Meier by hand: D out at 5, A at 10 (S 0.75), F out at 20, B at 30 (S 0.375): the median 30",
          km([(5, False), (10, True), (20, False), (30, True), (40, False)]) == 30)
    check("fewer than half finished: no median", km([(10, True), (20, False), (30, False)]) is None
          and km([]) is None)
    eleven = reports_module.finishing({"finishing": history, "concentration": hours_rows, "now": when})
    check("report 11: number, key, title", (eleven.number, eleven.key, eleven.title) == (11, "finishing", "Finishing"))
    s = eleven.sentence
    check("the counts: 6 marked, 3 Finished, 1 Dropped, 2 Playing, 1 of them left behind (E, 36 days)",
          s.startswith("6 games carry a mark: 3 Finished, 1 Dropped, 2 still Playing (1 of them left behind);"), s)
    check("the rate with its size: 3 of 4 decided, 75%, a hint on four",
          "3 of 4 decided games finished (75%) — on so few, a hint and not a finding" in s, s)
    check("the median of the two dated finishes 20 days (10 to 30); Kaplan-Meier, the censored counted, 30",
          "a median of 20 days (10 to 30) on 2 dated marks, 30 days counting the 3 not finished as still going" in s, s)
    check("the hours: Finished at a median of 8h (20, 5, 8 -- the undated C counted), Dropped 1h",
          "Finished games had a median of 8h 00m played, Dropped ones 1h 00m" in s, s)
    bars = {b.label: b.value for b in eleven.parts[0].bars}
    check("the marks as bars, and the undated named: 3 of 6", bars == {"Finished": "3", "Dropped": "1",
                                                                       "Still Playing": "2", "of them left behind": "1"}
          and eleven.parts[0].note.startswith("3 of 6 marks undated"), (bars, eleven.parts[0].note))
    done = {r[0]: r for r in next(p for p in eleven.parts if p.heading == "Finished").rows}
    check("Finished: A 10 days, B 30, C undated -- counted, not timed", (done["A"][3], done["B"][3], done["C"][3])
          == ("10", "30", "—"), done)
    censored = {r[0]: r for r in next(p for p in eleven.parts if p.heading.startswith("Not finished")).rows}
    check("the censored: E 40 days so far and left behind, F 20", (censored["E"][2], censored["E"][3],
                                                                   censored["F"][2], censored["F"][3]) == ("40", "yes", "20", ""))
    # With C dated too (finished 20 days after its first session): the timing changes, the counts do not.
    dated = [dict(r, status_changed_at="2026-07-21" + T) if r["name"] == "C" else r for r in history]
    again = reports_module.finishing({"finishing": dated, "concentration": hours_rows, "now": when})
    check("with the undated mark dated: three timed, the median 20 (10, 20, 30), Kaplan-Meier still 30",
          "a median of 20 days (10 to 30) on 3 dated marks, 30 days" in again.sentence
          and again.parts[0].note.startswith("2 of 6 marks undated"), again.sentence)
    early = [dict(r, status_changed_at="2026-07-25" + T) if r["name"] == "A" else r for r in history]
    first_after = reports_module.finishing({"finishing": early, "concentration": hours_rows, "now": when})
    early_row = next(r for r in next(p for p in first_after.parts if p.heading == "Finished").rows if r[0] == "A")
    check("a Finished mark set before the game's first session (A, 25 July; first played 1 August): counted, not "
          "timed -- never a negative time", early_row[3] == "\u2014" and "on 1 dated mark" in first_after.sentence
          and "-" not in first_after.sentence.split("to Finished")[1].split("days")[0], first_after.sentence)
    check("the caveat names undated marks, the late mark, censoring's 'not finished after', today's hours, the size",
          all(w in eleven.caveat for w in ("carries no date", "late by nature", "not finished after its days so far",
                                           "The hours are today's", "a hint")), eleven.caveat)
    check("the idea names the completion rate, time to event, censoring and Kaplan-Meier, the median",
          all(w in eleven.concept for w in ("Completion rate", "Time to event", "Censoring", "Kaplan", "The median")))
    quiet = reports_module.finishing({"finishing": [], "concentration": [], "now": when})
    check("no mark at all: said in words", quiet.empty and quiet.sentence.startswith("No game carries a mark yet"))
except Exception as exc:
    unreached("6", exc)

print("\n=== 7. the eleven on the copy: the hours worked out once ===")
try:
    import time as _time
    from data_access import reports as data_reports
    source = store.reports()
    names = [n for n in data_reports.QUERIES]
    extra = lambda n: {"role": "publisher"} if n == "profile_companies" else {}  # noqa: E731
    plain = {n: source.rows(n, **extra(n)) for n in names}
    with source.worked_out_once():
        once = {n: source.rows(n, **extra(n)) for n in names}
        temp = {r[0] for r in store._conn.execute("SELECT name FROM sqlite_temp_master WHERE type = 'table'")}
    left = store._conn.execute("SELECT COUNT(*) FROM sqlite_temp_master").fetchone()[0]
    check(f"every query ({len(names)}) answers the same with the hours worked out once", all(plain[n] == once[n]
                                                                                             for n in names),
          [n for n in names if plain[n] != once[n]])
    check("the copies stand in for the two views while the build runs, and are gone after",
          temp == set(data_reports.ONCE) and left == 0, (temp, left))
    built = reports_module.build(source)
    check("eleven reports, the eleventh Finishing, last", len(built) == 11 == len(reports_module.BUILDERS)
          and built[-1].key == "finishing")
    total = sum(len(p.rows) for p in built[-1].parts[1:])  # its Finished, Not finished and Dropped tables
    check(f"report 11 on the copy counts its {total} marks: {built[-1].sentence[:90]}", not built[-1].empty
          and (built[-1].sentence.startswith(f"{total} games carry a mark")
               or built[-1].sentence.startswith(f"{total} game carries a mark")), built[-1].sentence)
    timings = []
    for _ in range(5):
        began = _time.perf_counter()
        reports_module.build(source)
        timings.append((_time.perf_counter() - began) * 1000)
    check(f"the eleven reports: best of 5 {min(timings):.1f} ms, under 50", min(timings) < 50, timings)
    raw_ro = sqlite3.connect(f"file:{box.path('library.db').as_posix()}?mode=ro", uri=True)
    try:
        ro = data_reports.Reports(raw_ro)
        check("and on a read-only connection, as reports.py opens the file", len(reports_module.build(ro)) == 11
              and raw_ro.execute("SELECT COUNT(*) FROM sqlite_temp_master").fetchone()[0] == 0)
    finally:
        raw_ro.close()
    md = reports_module.markdown(built, datetime.now(), data_reports.QUERIES)
    check("the Markdown carries ## 11. and its SQL", "## 11. Finishing" in md and data_reports.FINISHING in md)
    window.show_reports()
    settle(1.0)
    cards = [c for c in window.reports_page.cards if getattr(c, "report", None) is not None]
    from presentation import ui_reports
    check("the Reports page: eleven cards, Finishing last; its intro says eleven questions",
          len(cards) == 11 and cards[-1].report.key == "finishing" and ui_reports.INTRO.startswith("Eleven questions"),
          [c.report.key for c in cards])
    window.show_library()
    settle(0.4)
except Exception as exc:
    unreached("7", exc)

print("\n=== 8. the documents, the layers ===")
try:
    import re
    import subprocess

    def doc(rel):
        return (PROJECT / rel).read_text(encoding="utf-8").replace("\r\n", "\n")
    analysis = doc("docs/ANALIZA.md")
    quoted = dict(re.findall(r"```sql\n-- (\w+)\n(.*?)\n```", analysis, re.S))
    check("ANALIZA: unsprezece rapoarte, report 11 in its contents and its section, its query as the code has it",
          analysis.startswith("# Ce poate spune baza de date: unsprezece rapoarte")
          and "(#11-terminarea)" in analysis and "## 11. Terminarea" in analysis
          and quoted.get("finishing") == data_reports.FINISHING)
    flat = " ".join(analysis.split())
    check("ANALIZA works the example by hand (20 days, Kaplan-Meier 30) and names the ideas",
          all(w in flat for w in ("**20 de zile**", "**30 de zile**", "completion rate", "time to event", "censoring",
                                  "Kaplan–Meier", "nudge", "dated mark", "tabel temporar")))
    readme = doc("docs/CITESTE-MA.md")
    check("CITESTE-MA: Left behind and its three answers, unsprezece rapoarte, still one page",
          all(w in readme for w in ("**Left behind**", "**Still playing**", "unsprezece rapoarte"))
          and len(readme.splitlines()) <= 110, len(readme.splitlines()))
    explained = doc("docs/explicatii/faza-103.md")
    check("docs/explicatii/faza-103.md: the shape and the five words", all(w in explained for w in (
        "## Ce s-a construit", "## De ce contează", "## Cum funcționează", "## Cinci cuvinte", "## Trei întrebări",
        "## Ce nu poate face", "completion rate", "time to event", "censoring", "nudge", "dated mark"))
          and "faza 103" in doc("docs/explicatii/CITESTE-MA.md"))
    check("BAZA_DE_DATE: nudged_at is written now", "**`nudged_at` se scrie din faza 103**" in doc("docs/BAZA_DE_DATE.md"))
    claude = doc("CLAUDE.md")
    check("CLAUDE.md: the row, eleven reports, the lesson, under its size", "| 103 |" in claude
          and "the eleven reports from the command line" in claude and "rules.TEST_COPY_ENV" in claude
          and len(claude.encode("utf-8")) < 116581, len(claude.encode("utf-8")))
    check("the build log has the phase's notes", "## Phase 103 notes" in sources.build_log())
    layers = subprocess.run([sys.executable, str(PROJECT / "tests" / "check_layers.py")], capture_output=True,
                            text=True, encoding="utf-8", errors="replace")
    check("check_layers: no import points up a layer", layers.returncode == 0, layers.stdout[-300:])
except Exception as exc:
    unreached("8", exc)

if window is not None:
    window._stop_watch()
    window._shut_down = True
    window.overrides.close()
    settle(0.3)
changed = box.finish()
check("config.json, the library database and the Run key's value are unchanged", not changed, changed)
check("nothing in this suite reached the network", attempts == [], attempts)
print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
