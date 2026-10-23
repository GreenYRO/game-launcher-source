"""Phase 76: Steam's own hours on a game's page and on its tile; the view that sums them, in one pass.

The upgrade to version 4 on a copy of the real library -- one view replaced, nothing else: every
row of every table as it was, the schema the same as a fresh one and as one brought up from
version 1 or 2, the view's answer the same as version 3's under four different sets of marks,
and many times faster; a refused upgrade leaving the launcher on version 3, still answering. The
store's answer by game, computed again here from the raw rows. The "On Steam" fact on a game's
page and the tile's quieter line, each present exactly when an account marked mine holds the
game, across every game and every set of marks; the money facts as Phase 74 left them. A new
answer reaching the tiles and the page on screen -- after Settings' OK and after a scan --
without rebuilding the grid. And nothing else reading it: not Stats, not Play something, not the
Continue card.

On a throwaway copy of the data (the Steam caches copied in, read only). Nothing is fetched.
"""
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
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

from PySide6.QtCore import QEventLoop, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton

app = QApplication([])

from data_access import backups, library_db
from logic import gamedetails, migration
from presentation import ui_continue, ui_library, ui_settings, ui_window
from shared import humanize, paths, rules

try:
    from logic import steam_time
except ImportError:
    steam_time = None

CACHE = str(paths.cache_dir())
DATABASE = SANDBOX / rules.LIBRARY_DB_FILE
NEW_VERSION = 4
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


def at_tag(tag: str, file: str) -> str:
    return subprocess.run(["git", "show", f"{tag}:{file}"], cwd=PROJECT, capture_output=True,
                          check=True).stdout.decode("utf-8")


def version3_view() -> str:
    """Version 3's v_steam_time_mine, word for word, out of its upgrade script in git."""
    text = at_tag("before-phase-76", "data_access/upgrades/003_steam_time.sql")
    start = text.index("CREATE VIEW v_steam_time_mine")
    return text[start:text.index(";", start) + 1]


def rows_of(conn, table: str) -> list[str]:
    # In the columns each table had: session gains its origin in version 7 (Phase 93).
    return test_sandbox.rows_in_old_columns(conn, table)


def raw(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(path, isolation_level=None)


MINE_VIEW = "SELECT appid, minutes, accounts, last_played FROM v_steam_time_mine"


def under_marks(conn, marks: dict, sql: str) -> list:
    """`sql`'s answer with the accounts marked as `marks`, then every mark put back."""
    conn.execute("BEGIN")
    try:
        for account_id, mark in marks.items():
            conn.execute("UPDATE steam_account SET is_mine = ? WHERE account_id = ?", (mark, account_id))
        return sorted(conn.execute(sql).fetchall(), key=repr)
    finally:
        conn.execute("ROLLBACK")


def expected_times(conn) -> dict[str, dict]:
    """Steam's hours on the accounts marked mine, by game -- from the raw rows, without a view."""
    newest: dict[tuple, tuple] = {}
    for account_id, appid, observed, minutes, last in conn.execute(
            "SELECT account_id, appid, observed_at, minutes_total, last_played FROM steam_playtime"):
        if (account_id, appid) not in newest or observed > newest[(account_id, appid)][0]:
            newest[(account_id, appid)] = (observed, minutes, last)
    mine = {a for a, m in conn.execute("SELECT account_id, is_mine FROM steam_account") if m == 1}
    by_app: dict[int, dict] = {}
    for (account_id, appid), (_observed, minutes, last) in newest.items():
        if account_id not in mine:
            continue
        held = by_app.setdefault(appid, {"minutes": None, "accounts": 0, "last_played": None})
        held["accounts"] += 1
        if minutes is not None:
            held["minutes"] = (held["minutes"] or 0) + minutes
        if last and (held["last_played"] is None
                     or datetime.fromisoformat(last) > datetime.fromisoformat(held["last_played"])):
            held["last_played"] = last
    return {key: by_app[appid] for key, appid in conn.execute(
        "SELECT identity_key, steam_appid FROM game WHERE steam_appid IS NOT NULL") if appid in by_app}


def expected_words(held: dict | None) -> str | None:
    """The page's words for one game, as the brief writes them."""
    if not held:
        return None
    parts = []
    if held["minutes"] is not None:
        if held["minutes"] > 0:
            time_ = humanize.playtime(held["minutes"] * 60)
        else:
            time_ = "under a minute" if held["last_played"] else "never played"
        parts.append(f"{time_} on {held['accounts']} accounts" if held["accounts"] > 1 else time_)
    if held["last_played"]:
        parts.append("last played " + humanize.day(datetime.fromisoformat(held["last_played"])))
    return ", ".join(parts) or None


def expected_tile(view, held: dict | None) -> str:
    if view.entry.launch_kind == "exe":
        line = humanize.playtime(view.playtime_seconds)
    elif view.entry.source == "steam" and held and (held["minutes"] or 0) > 0:
        line = humanize.playtime(held["minutes"] * 60) + " on Steam"
    else:
        line = rules.SOURCE_LABELS.get(view.entry.source, view.entry.source.capitalize())
    return f"Hidden  ·  {line}" if view.hidden else line


accounts = []
print("=== 1. version 4: one view replaced, on a copy of the real library ===")
try:
    if test_sandbox._version(DATABASE) >= NEW_VERSION:
        # The user's own start has upgraded the real database already: version 3 is put back in
        # the copy -- version 3's view out of git, the version numbers -- with every row kept.
        print("         (the real library is at version 4 already: version 3's view is put back in the copy)")
        conn = raw(DATABASE)
        conn.execute("BEGIN")
        test_sandbox.undo_upgrades(conn, 4)  # versions 5 and 6 (Phases 83, 86): out first, made again
        conn.execute("DROP VIEW v_steam_time_mine")
        conn.execute(version3_view())
        conn.execute("UPDATE meta SET schema_version = 3")
        conn.execute("PRAGMA user_version = 3")
        conn.execute("COMMIT")
        conn.close()
    check("the copy starts at version 3", test_sandbox._version(DATABASE) == 3)
    conn = raw(DATABASE)
    accounts = [r[0] for r in conn.execute("SELECT account_id FROM steam_account ORDER BY account_id")]
    held = {r[0] for r in conn.execute("SELECT DISTINCT account_id FROM steam_playtime")}
    print(f"         ({len(accounts)} accounts, {conn.execute('SELECT COUNT(*) FROM steam_playtime').fetchone()[0]} "
          "counters in the copy)")
    # Four sets of marks: as the user left them, and three that use every value.
    mark_sets = [{}, {a: (1 if i % 2 == 0 else 0) for i, a in enumerate(accounts)},
                 {a: (None if i % 2 == 0 else 1) for i, a in enumerate(accounts)},
                 {a: None for a in accounts}]
    before_answers = [under_marks(conn, marks, MINE_VIEW) for marks in mark_sets]
    started = time.perf_counter()
    for _ in range(3):
        conn.execute(MINE_VIEW).fetchall()
    old_ms = (time.perf_counter() - started) / 3 * 1000
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")]
    rows_before = {t: rows_of(conn, t) for t in tables}
    schema_before = schema_of(conn)
    conn.close()
    before_print = library_db.file_fingerprint(DATABASE)
    refused_copy = SANDBOX / "v3-refused.db"
    shutil.copyfile(DATABASE, refused_copy)
    snapshots_before = len(backups.list_snapshots())
    lines.clear()

    store = migration.open_library()
    newest = backups.list_snapshots()[0]
    check("a snapshot is taken first, holding the library as it was",
          len(backups.list_snapshots()) == snapshots_before + 1
          and library_db.file_fingerprint(newest.path / rules.LIBRARY_DB_FILE) == before_print)
    # Since Phase 83 the newest version is 5, and a version-3 file goes through scripts 4 and 5.
    check(f"the database is at version {library_db.SCHEMA_VERSION}: the store, meta and PRAGMA user_version agree",
          store.version == library_db.SCHEMA_VERSION >= NEW_VERSION
          and store.version == library_db.schema_version(store._conn)
          == store._conn.execute("SELECT schema_version FROM meta").fetchone()[0])
    check("and the log says so", any(f"upgraded from version 3 to {library_db.SCHEMA_VERSION}" in line for line in lines)
          and any(f"is at version {library_db.SCHEMA_VERSION} now (snapshot" in line for line in lines))
    store.close()
    conn = raw(DATABASE)
    changed = [row[:2] for row in schema_of(conn) if row not in schema_before]
    gone = [row[:2] for row in schema_before if row not in schema_of(conn)]
    later = [("view", "v_hours"),  # version 5 (Phase 83) adds one view, nothing else
             ("table", "wishlist_read"), ("table", "wishlist"), ("view", "v_wishlist_now"),  # 6 (Phase 86)
             ("table", "session"),  # 7 (Phase 93): a column added, so its text changes
             ("table", "game"), ("table", "price_target"), ("table", "price_alert"), ("table", "rating")]  # 8 (101)
    check("the one change to the schema: v_steam_time_mine, replaced (and the later versions' own)",
          sorted(changed) == sorted([("view", "v_steam_time_mine")] + later)
          and sorted(gone) == sorted([("view", "v_steam_time_mine"), ("table", "session"), ("table", "game")]),
          (changed, gone))
    # The projection runs after an upgrade (Phase 73's seeding) and brings the Steam tables up to the
    # cache: a record fetched since the last projection -- a scan cut short by closing the launcher
    # leaves exactly that -- is refreshed in place, its genres, categories and companies replaced. So
    # those tables keep every app they knew; the names they point at and the price series only gain.
    by_app = {"steam_app", "steam_app_genre", "steam_app_category", "steam_app_company"}
    only_gain = {"genre", "category", "company", "price_snapshot"}

    def apps(rows: list[str]) -> set:
        return {eval(r)[0] for r in rows}

    moved = [t for t in tables if t not in by_app | only_gain | {"meta"} and rows_of(conn, t) != rows_before[t]]
    lost = ([t for t in sorted(by_app) if not apps(rows_before[t]) <= apps(rows_of(conn, t))]
            + [t for t in sorted(only_gain) if not set(rows_before[t]) <= set(rows_of(conn, t))])
    check("every row of every other table as it was: nothing of the data touched", not moved and not lost,
          {"changed": moved, "lost rows": lost})
    check("meta: only the version moved", conn.execute("SELECT id, created_at, migrated_from, migrated_at FROM meta")
          .fetchall() == [tuple(eval(r)[i] for i in (0, 2, 3, 4)) for r in rows_before["meta"]])
    after_answers = [under_marks(conn, marks, MINE_VIEW) for marks in mark_sets]
    check(f"the view answers as version 3's did, app for app, under {len(mark_sets)} sets of marks "
          f"({', '.join(str(len(a)) for a in after_answers)} apps)",
          after_answers == before_answers and any(after_answers))
    started = time.perf_counter()
    for _ in range(3):
        conn.execute(MINE_VIEW).fetchall()
    new_ms = (time.perf_counter() - started) / 3 * 1000
    check(f"and many times faster: {old_ms:.1f} ms in version 3, {new_ms:.1f} ms now", new_ms * 5 < old_ms)
    fresh = sqlite3.connect(":memory:", autocommit=True)
    library_db.create(fresh)
    check("a fresh version-4 database has the same schema as the upgraded one", schema_of(fresh) == schema_of(conn),
          [r[:2] for r in schema_of(fresh) if r not in schema_of(conn)][:3])
    conn.close()
    for tag, version in (("before-phase-75", 2), ("before-phase-73", 1)):
        older = sqlite3.connect(":memory:", autocommit=True)
        older.executescript(at_tag(tag, "data_access/schema.sql"))
        older.execute("INSERT INTO meta (id, schema_version, created_at) VALUES (1, ?, '2026-10-01T00:00:00+03:00')",
                      (version,))
        older.execute(f"PRAGMA user_version = {version}")
        applied = library_db.upgrade(older)
        check(f"version {version} goes through every script after it, to the same schema",
              applied == list(range(version + 1, library_db.SCHEMA_VERSION + 1))
              and schema_of(older) == schema_of(fresh), applied)
    # A refused upgrade: the launcher stays on version 3, and the old view still answers. The
    # script fails half way -- after the view is dropped -- so the rollback has something to put
    # back. (A view naming a table that does not exist would not do: SQLite creates it, and
    # complains only when it is read.)
    broken = SANDBOX / "004_broken.sql"
    broken.write_text("DROP VIEW v_steam_time_mine;\nCREATE TABLE game (x INTEGER);\n", encoding="utf-8")
    real_scripts = library_db.upgrade_scripts
    library_db.upgrade_scripts = lambda: {**real_scripts(), 4: broken}
    try:
        v3 = library_db.LibraryStore(refused_copy)
        try:
            v3.upgrade()
            outcome = "upgraded"
        except Exception as exc:  # noqa: BLE001
            outcome = type(exc).__name__
        check("a broken script 4 is refused: the file stays at version 3, its view whole",
              outcome != "upgraded" and v3.version == 3
              and v3._conn.execute("SELECT COUNT(*) FROM v_steam_time_mine").fetchone()[0] == len(before_answers[0]),
              outcome)
        check("and version 3 still answers Steam's hours by game, as version 4 does",
              v3.steam_times() == expected_times(v3._conn) and bool(v3.steam_times()))
        v3.close()
    finally:
        library_db.upgrade_scripts = real_scripts
except Exception as exc:
    unreached("1", exc)

print("\n=== 2. the store's answer: by game, through its Steam link, the accounts marked mine ===")
try:
    store = library_db.LibraryStore(DATABASE)
    real_marks = {a: m for a, m in store._conn.execute("SELECT account_id, is_mine FROM steam_account")}
    answers = []
    for marks in mark_sets:
        for account_id, mark in marks.items():
            store.set_account_mark(account_id, None if mark is None else bool(mark))
        got, want = store.steam_times(), expected_times(store._conn)
        answers.append(len(got))
        check(f"marks {[marks.get(a, real_marks.get(a)) for a in accounts]}: {len(got)} games, each as the raw "
              "rows say", got == want, sorted(set(got) ^ set(want))[:3])
        for account_id, mark in real_marks.items():
            store.set_account_mark(account_id, None if mark is None else bool(mark))
    check("no account marked mine: no game at all", answers[-1] == 0)
    started = time.perf_counter()
    store.steam_times()
    check(f"asked in {(time.perf_counter() - started) * 1000:.1f} ms -- fit for every reload",
          time.perf_counter() - started < 0.05)
    overwatch = store.steam_times().get("steam:2357570")
    if overwatch and overwatch["minutes"] == 6820:
        check("Overwatch, as read on 11 October: 6,820 minutes on 2 accounts, last played 1 September",
              overwatch["accounts"] == 2 and overwatch["last_played"].startswith("2026-09-01"), overwatch)
    store.close()
except Exception as exc:
    unreached("2", exc)

print("\n=== 3. the page's fact and the tile's line, across every game and every set of marks ===")
window = None
try:
    window = ui_window.MainWindow()
    window.resize(1280, 820)
    window.show()
    settle(1.2)
    store = window.overrides
    real_marks = {a: m for a, m in store._conn.execute("SELECT account_id, is_mine FROM steam_account")}
    painted: list[tuple[str, str]] = []
    real_subtitle = ui_library.tile_subtitle

    def watching_subtitle(view, *args, **kwargs):  # observed: Phase 93's third argument; starting: Phase 99's
        line = real_subtitle(view, *args, **kwargs)
        painted.append((view.key, line))
        return line

    ui_library.tile_subtitle = watching_subtitle
    seen_fact = seen_tile = 0
    for number, marks in enumerate(mark_sets):
        for account_id, mark in marks.items():
            store.set_account_mark(account_id, None if mark is None else bool(mark))
        window._follow_steam_times()
        want = expected_times(store._conn)
        wrong_fact, wrong_place, wrong_money, wrong_tile = [], [], [], []
        for view in window.views:
            record = gamedetails.record_for(view)
            money = window.money_of(view)
            rows = gamedetails.metadata(record, view, money, window.steam_time_of(view))
            facts = dict(rows)
            words = expected_words(want.get(view.key))
            if facts.get("On Steam") != words:
                wrong_fact.append((view.display_name, facts.get("On Steam"), words))
            labels = [label for label, _ in rows]
            if "On Steam" in labels and labels[labels.index("On Steam") - 1] != "Source":
                wrong_place.append(view.display_name)
            if [r for r in rows if r[0] != "On Steam"] != gamedetails.metadata(record, view, money):
                wrong_money.append(view.display_name)
            line = ui_library.tile_subtitle(view, window.library.steam_times.get(view.key))
            if line != expected_tile(view, want.get(view.key)):
                wrong_tile.append((view.display_name, line))
            seen_fact += words is not None
            seen_tile += line.endswith(" on Steam")
        check(f"marks set {number + 1}: the fact exactly on the {sum(1 for v in window.views if v.key in want)} games "
              "an account of mine holds, in the brief's words", not wrong_fact, wrong_fact[:3])
        check(f"marks set {number + 1}: right after the source", not wrong_place, wrong_place[:3])
        check(f"marks set {number + 1}: every other fact -- the money's among them -- as without it",
              not wrong_money, wrong_money[:3])
        check(f"marks set {number + 1}: each tile's line, Steam's hours only on a Steam game with time on my accounts",
              not wrong_tile, wrong_tile[:3])
        painted.clear()
        window.library.list.viewport().repaint()
        drawn = dict(painted)
        check(f"marks set {number + 1}: and the tiles on screen are painted with it",
              drawn and all(line == expected_tile(window.by_key[key], want.get(key)) for key, line in drawn.items()),
              list(drawn.items())[:3])
    check(f"seen across the sets: {seen_fact} facts and {seen_tile} Steam tiles", seen_fact > 0 and seen_tile > 0)
    ui_library.tile_subtitle = real_subtitle
    for account_id, mark in real_marks.items():
        store.set_account_mark(account_id, None if mark is None else bool(mark))
    window._follow_steam_times()
    window.show_detail("steam:2357570")
    settle(1.2)
    on_page = window.detail.facts()
    check("on Overwatch's own page, in its Details", on_page.get("On Steam") == expected_words(
        expected_times(store._conn).get("steam:2357570")) and on_page.get("On Steam"), on_page.get("On Steam"))
except Exception as exc:
    ui_library.tile_subtitle = real_subtitle if "real_subtitle" in dir() else ui_library.tile_subtitle
    unreached("3", exc)

print("\n=== 4. a new answer reaches the tiles and the page on screen, without rebuilding the grid ===")
try:
    store = window.overrides
    rebuilt: list[int] = []
    real_set_views = window.library.set_views
    window.library.set_views = lambda views: (rebuilt.append(1), real_set_views(views))[1]
    others = {a: m for a, m in store._conn.execute("SELECT account_id, is_mine FROM steam_account")}
    notes: dict = {}

    def modal():
        return QApplication.activeModalWidget()

    def through_settings():
        dialog = modal()
        if not isinstance(dialog, ui_settings.SettingsDialog):
            return False
        for account_id, group in dialog.account_groups.items():
            button = next(b for b in group.buttons() if b.text() == "Not mine")
            QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        QTest.mouseClick(next(b for b in dialog.findChildren(QPushButton) if b.text() == "OK"),
                         Qt.MouseButton.LeftButton)
        return True

    steps = [lambda: QTimer.singleShot(0, window.open_settings) or True, through_settings,
             lambda: notes.update(closed=modal() is None) or True]
    position = [0]
    loop = QEventLoop()

    def advance():
        if position[0] >= len(steps):
            loop.quit()
            return
        QTimer.singleShot(200, advance)
        if steps[position[0]]():
            position[0] += 1

    QTimer.singleShot(200, advance)
    QTimer.singleShot(30_000, loop.quit)
    loop.exec()
    settle(0.3)
    check("Settings' OK with every account Not mine: no game has Steam's hours now",
          notes.get("closed") and window.steam_times == {} and window.library.steam_times == {})
    check("the page on screen lost its fact at once", "On Steam" not in window.detail.facts())
    check("the grid was not rebuilt for it", not rebuilt)
    for account_id, mark in others.items():
        store.set_account_mark(account_id, None if mark is None else bool(mark))
    window._follow_steam_times()
    # A reading in which Overwatch was played an hour more on one account, landed by a scan's end.
    before = window.steam_time_of(window.by_key["steam:2357570"])
    account = store._conn.execute("SELECT account_id FROM v_steam_time_latest WHERE appid = 2357570 AND is_mine = 1 "
                                  "ORDER BY account_id LIMIT 1").fetchone()
    if before and account:
        account = account[0]
        latest = store._conn.execute("SELECT minutes_total, minutes_2wks, minutes_disconnected, last_played FROM "
                                     "v_steam_time_latest WHERE account_id = ? AND appid = 2357570", (account,)).fetchone()
        later = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(timespec="seconds")
        played = (datetime.now().astimezone() + timedelta(days=1)).isoformat(timespec="seconds")
        reading = {"accounts": [{"account_id": account, "steam_id64": account + rules.STEAM_ID64_BASE,
                                 "account_name": None, "persona": None, "most_recent": None, "last_login": None}],
                   "reads": [{"account_id": account, "read_at": later, "file_modified": later, "apps_in_file": 1,
                              "apps_with_time": 1, "values": [{"appid": 2357570, "minutes_total": (latest[0] or 0) + 60,
                                                               "minutes_2wks": latest[1], "minutes_disconnected": latest[2],
                                                               "last_played": played}]}]}
        steam_time._keep(CACHE, [reading])
        rebuilt.clear()
        window._on_scanned(list(window.entries))
        settle(0.5)
        after = window.steam_time_of(window.by_key["steam:2357570"])
        check("a scan lands an hour more on Overwatch: the window's answer has it",
              after and after["minutes"] == before["minutes"] + 60 and after["last_played"] == played, after)
        check("the page on screen says so", window.detail.facts().get("On Steam") == expected_words(after),
              window.detail.facts().get("On Steam"))
        check("and the grid was not rebuilt for it (the scan found the same games)", not rebuilt)
    else:
        check("Overwatch is held by an account of mine in the copy", False, before)
    window.library.set_views = real_set_views
except Exception as exc:
    unreached("4", exc)

print("\n=== 5. nothing else reads it; a library without it falls back ===")
try:
    sources = {path.relative_to(PROJECT).as_posix(): path.read_text(encoding="utf-8-sig")
               for folder in ("presentation", "adapters", "logic", "providers", "web", "data_access", "shared")
               for path in (PROJECT / folder).rglob("*.py")}
    readers = sorted(name for name, text in sources.items()
                     if re.search(r"\bsteam_times\b|steam_time_of|steam_time_for|steam_time_facts", text))
    check(f"Steam's hours are read only by the store, the page's facts, the window, the page and the tile: {readers}",
          set(readers) <= {"data_access/library_db.py", "logic/gamedetails.py", "logic/steam_time.py",
                           "presentation/ui_window.py", "presentation/ui_detail.py", "presentation/ui_library.py"}
          and {"presentation/ui_detail.py", "presentation/ui_library.py"} <= set(readers))
    check("not Stats, not Play something, not the Continue card or Jump back in",
          not {"logic/stats.py", "logic/pick.py", "presentation/ui_continue.py", "presentation/ui_jump.py",
               "presentation/ui_stats.py"} & set(readers))
    overwatch = window.by_key["steam:2357570"]
    check("the Continue card's line for a Steam game still names the store",
          ui_continue.meta_line(overwatch).startswith("Steam"), ui_continue.meta_line(overwatch))
    check("no fact and the store's name with nothing to go on",
          gamedetails.steam_time_facts(None) == [] and ui_library.tile_subtitle(overwatch, None) == "Steam")
    check("held with no minutes: the last played alone; with none at all, no fact",
          gamedetails.steam_time_facts({"minutes": None, "accounts": 1, "last_played": "2026-09-10T02:22:23+03:00"})
          == [("On Steam", "last played " + humanize.day(datetime.fromisoformat("2026-09-10T02:22:23+03:00")))]
          and gamedetails.steam_time_facts({"minutes": None, "accounts": 2, "last_played": None}) == [])
    check("0 minutes with a last played is under a minute; without one, never played",
          gamedetails.steam_time_facts({"minutes": 0, "accounts": 1, "last_played": "2026-09-10T02:22:23+03:00"})[0][1]
          .startswith("under a minute, last played")
          and gamedetails.steam_time_facts({"minutes": 0, "accounts": 1, "last_played": None})
          == [("On Steam", "never played")])
    check("a tile with 0 minutes on Steam keeps the store's name",
          ui_library.tile_subtitle(overwatch, {"minutes": 0, "accounts": 1, "last_played": None}) == "Steam")
    json_store = test_sandbox.separate_store("json76", kind="json")
    real_store = window.overrides
    window.overrides = json_store
    try:
        window._read_steam_times()
        check("a library on the JSON (a refused migration) has no Steam hours, and nothing breaks",
              window.steam_times == {} and window.library.steam_times == {})
    finally:
        window.overrides = real_store
        window._read_steam_times()
    check("nothing went to the network", not attempts, attempts[:3])
    window.close()
    settle(0.3)
    window.overrides.close()
except Exception as exc:
    unreached("5", exc)

print("\n=== 6. the layers ===")
try:
    layers = subprocess.run([sys.executable, str(PROJECT / "tests" / "check_layers.py")], cwd=PROJECT,
                            capture_output=True, text=True, timeout=120)
    check("no import points up a layer, and sqlite3 stays in data_access/",
          "upward imports: 0" in layers.stdout and "sqlite3 outside data_access/: 0" in layers.stdout,
          layers.stdout[-300:])
except Exception as exc:
    unreached("6", exc)

print("\n=== 7. the real library is exactly as it was found ===")
changed = box.finish()
check("config.json and the library database are unchanged", not changed, changed)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
