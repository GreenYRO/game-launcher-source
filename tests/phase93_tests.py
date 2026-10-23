"""Phase 93: sessions for games started outside the launcher.

  1. the path rule: a folder claims what is inside it and nothing beside it (Doom against Doom2,
     WARDOGS against WARDOGS Playtest), a scan root and a drive claim nothing, a loose exe only itself;
     tools never watched (the user's mark, Steam's type when certain), demos, mods and hidden games are;
  2. the session rules on a clock the test turns: opens at the first look, survives a shim's gap,
     closes after WATCH_GONE_POLLS looks without the game, a gap counted at most WATCH_GAP_MAX_S (a
     night's sleep counts seconds), the tracker's game never observed;
  3. a real game, not started by the launcher: a made-up game folder with a starter (a copy of cmd)
     that hands over to the game (a copy of ping) and exits, as Phase 16's shims do -- seen by the
     window's own process watch, banked live on the cadence, written as 'observed' with its minutes,
     last played moved; the same game started from the launcher is never observed;
  4. the minimum, the warning for a very long one, the switch off stopping the looks at once;
  5. no hour counted twice, through v_hours: a Steam game's observed session leaves minutes_launcher
     and its hours as Steam's counter; a folder game's grows by the session;
  6. the upgrade on a copy of the user's library: version 7, every old session 'launched', the
     column refusing anything else, the migration net green; a session's origin through a record,
     a merge and the store;
  7. Settings' third switch, on by default, and since when;
  8. while a game is seen running: its page ("Running — timed by watching", Play resting, no Stop),
     its tile, Play refused everywhere; an observed session marked approximate; the Continue card;
  9. the anonymous export carries how sessions were measured, and an old export reads as launched;
 10. the old words are gone where they used to be, and the new ones say what is true;
 11. the eight reports' time; one look's time; the layers; the real data, config and Run key unchanged.

On a throwaway copy of the data; the network is blocked.
"""
import logging
import os
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import test_sandbox

# The desk, and the watch on as it is by default; nothing else of the user's tray life copied.
box = test_sandbox.start({"allow_network": False, "startup_scan": False, "tv_mode": False, "watch_games": True},
                         migrate=False)
# The upgrade is proven on the user's library as version 6 had it: since his start of 18 October the real
# one is at 7 and holds observed sessions of his own, so the copy is taken back first, as suite 86 does.
_raw = sqlite3.connect(box.path("library.db"), isolation_level=None)
if _raw.execute("PRAGMA user_version").fetchone()[0] >= 7:
    test_sandbox.undo_upgrades(_raw, 6)
COPY_SESSIONS = _raw.execute("SELECT COUNT(*) FROM session").fetchone()[0]
_raw.close()
attempts: list[str] = []


def no_network(request, *args, **kwargs):
    attempts.append(getattr(request, "full_url", str(request)))
    raise OSError("the network is blocked in this suite")


urllib.request.urlopen = no_network


class Lines(logging.Handler):
    def __init__(self):
        super().__init__(logging.INFO)
        self.lines: list[str] = []

    def emit(self, record):
        self.lines.append(record.getMessage())


lines = Lines()
logging.getLogger().addHandler(lines)
logging.getLogger().setLevel(logging.INFO)

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

app = QApplication([])

from data_access import catalog_io, config_io, library_db
from logic import observe, sessions
from shared import rules
from shared.models import GameEntry
from presentation import ui_actions, ui_window

passed = failed = 0
WINDOWS = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"


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


def settle(seconds: float) -> None:
    loop = QEventLoop()
    QTimer.singleShot(int(seconds * 1000), loop.quit)
    loop.exec()


class View:
    """A made-up game view: what observe asks of one."""

    def __init__(self, key, folder, source="folders", detection="heuristic", exe="", is_tool=None, app_type="",
                 appid_source="manifest", hidden=False):
        self.key, self.display_name = key, key
        self.entry = GameEntry(source=source, source_id=key, display_name=key, install_dir=folder,
                               launch_kind="exe" if source in ("folders", "gog") else "uri",
                               launch_target=exe, working_dir=folder, icon_hint="", size_on_disk=0,
                               detection=detection, extra={"appid_source": appid_source})
        self.data = {} if is_tool is None else {"is_tool": is_tool}
        self.app_type, self.launch_target, self.hidden = app_type, exe, hidden


print("=== 1. the path rule; which games are watched ===")
try:
    games = observe.watched_games([
        View("doom", r"C:\games\Doom"), View("doom2", r"C:\games\Doom2"),
        View("wardogs", r"C:\Steam\steamapps\common\WARDOGS", source="steam"),
        View("playtest", r"C:\Steam\steamapps\common\WARDOGS Playtest", source="steam", hidden=True),
        View("loose", r"C:\games", detection="loose_exe", exe=r"C:\games\Tetris.exe"),
        View("root", r"C:\games"), View("drive", "D:\\"),
        View("ds4", r"C:\games\DS4", is_tool=True), View("marked game", r"C:\games\Marked", is_tool=False,
                                                         app_type="tool"),
        View("tool", r"C:\Steam\steamapps\common\Tool", source="steam", app_type="tool"),
        View("guessed", r"C:\games\Guessed", app_type="tool", appid_source=rules.APPID_SOURCE_SEARCH),
        View("demo", r"C:\Steam\steamapps\common\Demo", source="steam", app_type="demo"),
        View("mod", r"C:\Steam\steamapps\common\Mod", source="steam", app_type="mod"),
    ], roots=[r"C:\games"])
    keys = {g.key for g in games}
    owner = lambda path: observe.owners([path], games)  # noqa: E731
    check("a process in C:\\games\\Doom2 belongs to Doom2, never to Doom", owner(r"C:\games\Doom2\doom2.exe") == {"doom2"})
    check("and one in C:\\games\\Doom to Doom", owner(r"c:\GAMES\doom\bin\doom.exe") == {"doom"})
    check("this PC's real case: WARDOGS Playtest's process is the Playtest's, not WARDOGS'",
          owner(r"C:\Steam\steamapps\common\WARDOGS Playtest\WARDOGS.exe") == {"playtest"})
    check("a loose exe matches its own path and nothing else",
          owner(r"C:\games\Tetris.exe") == {"loose"} and owner(r"C:\games\Other.exe") == set())
    check("a scan root and a drive are never a game's folder", "root" not in keys and "drive" not in keys
          and owner(r"C:\games\Anything\x.exe") == set())
    check("tools are not watched: the user's mark, and Steam's type when the appid is certain",
          "ds4" not in keys and "tool" not in keys)
    check("the user's 'a game' mark wins over Steam's type; a guessed appid's type decides nothing",
          "marked game" in keys and "guessed" in keys)
    check("demos and mods are games; a hidden game is watched", {"demo", "mod", "playtest"} <= keys)
    by = {g.key: g for g in games}
    check("the rule for hours: a Steam game's are its store's, a folder game's are its own",
          not by["wardogs"].adds_hours and by["doom"].adds_hours and by["loose"].adds_hours)
except Exception as exc:
    unreached("1", exc)

print("\n=== 2. the session rules, on a clock the test turns ===")
try:
    games = {g.key: g for g in observe.watched_games([View("g", r"C:\games\G"), View("h", r"C:\games\H")])}
    obs = observe.Observer()
    t0, wall = 1000.0, datetime(2026, 10, 18, 21, 0, 5, 123456).astimezone()
    ended = obs.feed({"g"}, games, set(), t0, wall)
    check("a session opens at the first look that sees the game, at that second",
          "g" in obs.live and obs.live["g"].started_at == wall.replace(microsecond=0) and obs.live["g"].seconds == 0)
    obs.feed({"g"}, games, set(), t0 + 5, wall)
    obs.feed(set(), games, set(), t0 + 10, wall)  # a shim exits before the real exe is up: one empty look
    check("one look without it (a shim's gap) does not end it", "g" in obs.live and obs.live["g"].absent == 1)
    obs.feed({"g"}, games, set(), t0 + 15, wall)
    check("seen again: the same session, the gap counted", obs.live["g"].seconds == 15 and obs.live["g"].absent == 0)
    obs.feed({"g"}, games, set(), t0 + 15 + 8 * 3600, wall)  # the PC slept with the game open
    check(f"a night's sleep between two looks counts {rules.WATCH_GAP_MAX_S} s, not eight hours",
          obs.live["g"].seconds == 15 + rules.WATCH_GAP_MAX_S, obs.live["g"].seconds)
    last = t0 + 15 + 8 * 3600
    gone = [obs.feed(set(), games, set(), last + 5 * (i + 1), wall) for i in range(rules.WATCH_GONE_POLLS)]
    check(f"it ends after {rules.WATCH_GONE_POLLS} looks without it, at its last sighting",
          gone[-1] and gone[-1][0].key == "g" and gone[-1][0].seconds == 30 and "g" not in obs.live
          and not any(gone[:-1]), gone)
    obs.feed({"h"}, games, {"h"}, t0, wall)
    check("a game the launcher's tracker times is never observed", "h" not in obs.live)
    obs.feed({"g"}, games, set(), t0, wall)
    ended = obs.feed({"g"}, games, {"g"}, t0 + 5, wall)
    check("one seen before the launcher took it over ends there, not counted twice",
          ended and ended[0].key == "g" and "g" not in obs.live)
    check("rules: a look every 5 s, gone after 2 empty looks, a gap at most 15 s (three looks)",
          (rules.WATCH_PROCESS_POLL_S, rules.WATCH_GONE_POLLS, rules.WATCH_GAP_MAX_S) == (5, 2, 15))
except Exception as exc:
    unreached("2", exc)

# -- a made-up game folder, with a starter and a game in it ----------------------------------------
FOLDER = Path(box.folder) / "p93 game"
FOLDER.mkdir(exist_ok=True)
shutil.copyfile(WINDOWS / "cmd.exe", FOLDER / "p93starter.exe")
shutil.copyfile(WINDOWS / "PING.EXE", FOLDER / "p93game.exe")
ENTRY = GameEntry(source="folders", source_id=str(FOLDER), display_name="p93 outside game",
                  install_dir=str(FOLDER), launch_kind="exe", launch_target=str(FOLDER / "p93game.exe"),
                  working_dir=str(FOLDER), icon_hint="", size_on_disk=0, detection="heuristic")


def start_outside(seconds: int) -> subprocess.Popen:
    """The game started the way a desktop shortcut starts it: not through the launcher. The starter
    hands over to the game and exits, as a shim does."""
    return subprocess.Popen([str(FOLDER / "p93starter.exe"), "/c", "start", "", "/b", str(FOLDER / "p93game.exe"),
                             "-n", str(seconds + 1), "127.0.0.1"], cwd=str(FOLDER), stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)


def kill_game() -> None:
    subprocess.run(["taskkill", "/f", "/im", "p93game.exe"], capture_output=True)  # this suite's own copy only


window = ui_window.MainWindow()
window.detail.allow_network = False
window.resize(1100, 760)
window.show()
settle(1.0)
window.entries = list(window.entries) + [ENTRY]
window.reload_views()
key = ENTRY.identity_key

print("\n=== 3. a real game started outside the launcher ===")
real = (rules.WATCH_PROCESS_POLL_S, rules.PLAYTIME_WRITE_INTERVAL_S)
try:
    check("a start alone writes nothing to config.json for the watch (a first run's file is its question's)",
          rules.WATCH_SINCE_KEY not in config_io.load_saved())
    check("the window watches the made-up game", key in window._watched and window.watch_on())
    check("the process watch runs once the session has begun", window.process_worker is not None
          and window.process_worker.isRunning())
    rules.WATCH_PROCESS_POLL_S, rules.PLAYTIME_WRITE_INTERVAL_S = 1, 30  # faster looks, an earlier bank
    settle(rules.WATCH_PROCESS_POLL_S * 6)  # the worker's current sleep, at the old pace, runs out
    before = dict(window.overrides.get(key))
    began = time.monotonic()
    window._observed_last_bank = began  # the cadence counted from the game's start: a bank at 30 s, one at 60
    starter = start_outside(75)
    seen_at = None
    while time.monotonic() - began < 20 and seen_at is None:
        settle(0.5)
        if window.observed_running(key):
            seen_at = time.monotonic() - began
    starter.wait(timeout=10)
    check(f"seen running {seen_at:.1f} s after it started -- within a look or two" if seen_at else "seen running",
          seen_at is not None and seen_at < 6, seen_at)
    check("its starter is gone and it goes on: one session, not ended by the shim", starter.poll() is not None
          and window.observed_running(key) and len([s for s in window.observer.live if s == key]) == 1)
    check("the tray's tooltip would say it is being played (the launcher's own words for it)",
          any(seen.name == "p93 outside game" for seen in window.observer.live.values()))
    while time.monotonic() - began < 68:
        settle(1.0)
    live = dict(window.overrides.get(key))
    live_sessions = live.get(rules.SESSIONS_KEY) or []
    check("banked live on the cadence, before the game ends: one observed session of 1 minute",
          window.observed_running(key) and len(live_sessions) == 1
          and live_sessions[0].get(rules.SESSION_ORIGIN_KEY) == rules.SESSION_OBSERVED
          and live_sessions[0]["minutes"] == 1, live_sessions)
    while window.observed_running(key) or key in window.observer.live:
        settle(1.0)
        if time.monotonic() - began > 110:
            break
    after = dict(window.overrides.get(key))
    after_sessions = after.get(rules.SESSIONS_KEY) or []
    gained = int(after.get("playtime_seconds", 0)) - int(before.get("playtime_seconds", 0))
    check("it ended on its own, after the game closed", key not in window.observer.live)
    check("one session, observed, 1 minute (75 s played, each edge within a look)",
          len(after_sessions) == 1 and after_sessions[0]["minutes"] == 1
          and after_sessions[0].get(rules.SESSION_ORIGIN_KEY) == rules.SESSION_OBSERVED, after_sessions)
    check(f"its time added to playtime: {gained} s for about 75 played (a folder game: no store counts it)",
          74 - 2 * rules.WATCH_PROCESS_POLL_S <= gained <= 76, gained)
    check("last played moved", after.get("last_played") and after.get("last_played") != before.get("last_played"))
    check("the log says what was noticed and how it ended",
          any("noticed p93 outside game running" in line for line in lines.lines)
          and any("p93 outside game closed: 1 min, observed" in line for line in lines.lines))

    lines.lines.clear()
    window.overrides.update(key, args="-n 30 127.0.0.1")  # the game's own arguments, as a user sets them
    window.reload_views()
    view = window.by_key[key]
    ui_actions.play(window, view)  # the same game, started from the launcher: the tracker times it
    settle(4)
    check("started from the launcher, the tracker times it", window.tracker.is_running(key))
    check("and the watch never observes it, though its processes are in the folder",
          key not in window.observer.live and not window.observed_running(key))
    window.tracker.stop(key)
    window._poll_playtime()
    kill_game()
    settle(2)
except Exception as exc:
    unreached("3", exc)
finally:
    rules.WATCH_PROCESS_POLL_S, rules.PLAYTIME_WRITE_INTERVAL_S = real
    kill_game()

print("\n=== 4. the minimum; a very long one; the switch off ===")
try:
    seen = observe.Seen("p93 short", "p93 short", True, "exe", datetime.now().astimezone().replace(microsecond=0),
                        time.monotonic(), seconds=40)
    window._bank_observed(seen, final=True)
    check("under a minute: nothing written, not even last played", window.overrides.get("p93 short") == {})
    long_one = observe.Seen(key, "p93 outside game", True, "uri", (datetime.now().astimezone() - timedelta(hours=13))
                            .replace(microsecond=0), time.monotonic(), seconds=13 * 3600)
    lines.lines.clear()
    window._bank_observed(long_one, final=True)
    check(f"longer than {rules.SESSION_MAX_HOURS} hours: recorded, and said at warning",
          any(s["minutes"] == 13 * 60 for s in window.overrides.get(key)[rules.SESSIONS_KEY])
          and any("an observed session of 13 hours" in line for line in lines.lines))
    worker = window.process_worker
    window.config[rules.WATCH_GAMES_KEY] = False
    window._apply_watch()
    check("the switch off: the looking stops at once", window.process_worker is None and worker.isFinished())
    window.config[rules.WATCH_GAMES_KEY] = True
    window._apply_watch()
    check("and on again, it starts again", window.process_worker is not None and window.process_worker.isRunning())
    check("the day the watch began is kept, by its own key", config_io.load_saved().get(rules.WATCH_SINCE_KEY)
          == window.config.get(rules.WATCH_SINCE_KEY) and len(window.config.get(rules.WATCH_SINCE_KEY, "")) == 10)
except Exception as exc:
    unreached("4", exc)

print("\n=== 5. no hour counted twice ===")
try:
    conn = window.overrides._conn
    steam = conn.execute(
        "SELECT g.identity_key, h.appid, h.minutes_launcher, h.minutes_steam, h.minutes FROM game g "
        "JOIN install i ON i.game_id = g.id JOIN v_hours h ON h.appid = g.steam_appid "
        "WHERE g.source = 'steam' AND h.minutes_steam > 0 ORDER BY h.minutes_steam DESC LIMIT 1").fetchone()
    check("a Steam game with Steam's own counter in the copy", steam is not None, steam)
    steam_key, appid, launcher_before, steam_minutes, total_before = steam
    seen = observe.Seen(steam_key, "a Steam game", False, "uri",
                        datetime.now().astimezone().replace(microsecond=0) - timedelta(minutes=50),
                        time.monotonic(), seconds=50 * 60)
    playtime_before = int(window.overrides.get(steam_key).get("playtime_seconds", 0))
    window._bank_observed(seen, final=True)
    row = conn.execute("SELECT minutes_launcher, minutes_steam, minutes FROM v_hours WHERE appid = ?", (appid,)).fetchone()
    check("its observed session is recorded, 50 minutes, observed",
          any(s["minutes"] == 50 and s.get(rules.SESSION_ORIGIN_KEY) == rules.SESSION_OBSERVED
              for s in window.overrides.get(steam_key)[rules.SESSIONS_KEY]))
    check("and its hours do not move: playtime_seconds, v_hours.minutes_launcher as they were",
          int(window.overrides.get(steam_key).get("playtime_seconds", 0)) == playtime_before
          and row[0] == launcher_before, (playtime_before, launcher_before, row))
    check("v_hours.minutes is still the launcher's (if any) plus Steam's counter, nothing more",
          row[2] == total_before and row[1] == steam_minutes, (row, total_before))
    check("and Steam's files are due at the next tick: its counter has moved",
          window._steam_played_since_scan is True)
    folder_row = lambda: conn.execute(  # noqa: E731
        "SELECT h.minutes_launcher FROM game g JOIN v_hours h ON h.game_id = g.id WHERE g.identity_key = ?",
        (key,)).fetchone()
    grown_before = folder_row()[0]
    seen = observe.Seen(key, "p93 outside game", True, "exe",
                        datetime.now().astimezone().replace(microsecond=0) - timedelta(minutes=30),
                        time.monotonic(), seconds=30 * 60)
    window._bank_observed(seen, final=True)
    check("a folder game's observed session grows its hours in v_hours by the session",
          abs(folder_row()[0] - grown_before - 30) < 0.01, (grown_before, folder_row()[0]))
except Exception as exc:
    unreached("5", exc)

print("\n=== 6. the upgrade, and a session's origin through every road ===")
try:
    conn = window.overrides._conn
    check(f"the copy is at version {library_db.SCHEMA_VERSION}, through the launcher's own upgrade",
          library_db.SCHEMA_VERSION >= 7 and window.overrides.version == library_db.SCHEMA_VERSION
          and window.overrides.keeps_observed)  # 8 since Phase 101
    origins = dict(conn.execute("SELECT origin, COUNT(*) FROM session GROUP BY origin").fetchall())
    check(f"every session the user's library had at version 6 reads 'launched' ({COPY_SESSIONS} of them; the "
          "suite's own observed ones besides)", origins.get("launched", 0) >= COPY_SESSIONS, origins)
    try:
        conn.execute("UPDATE session SET origin = 'guessed' WHERE id = (SELECT MIN(id) FROM session)")
        refused = False
    except sqlite3.IntegrityError:
        refused = True
    check("the column refuses anything but launched and observed", refused)
    observed_at = datetime(2026, 10, 1, 20, 0).astimezone()
    record = {rules.SESSIONS_KEY: sessions.dump(sessions.upsert([], observed_at, 12, rules.SESSION_OBSERVED)
                                                 + [sessions.Session(observed_at - timedelta(days=1), 30)])}
    check("a record says 'observed' only for an observed session; a launched one keeps the old shape",
          record[rules.SESSIONS_KEY][0] == {"start": (observed_at - timedelta(days=1)).isoformat(timespec="seconds"),
                                            "minutes": 30}
          and record[rules.SESSIONS_KEY][1].get(rules.SESSION_ORIGIN_KEY) == rules.SESSION_OBSERVED)
    window.overrides.update("p93 origin", **record)
    saved = test_sandbox.records().get("p93 origin")
    check("written and read back from the file, the origin kept", saved == record, saved)
    merged = sessions.merge(sessions.load(record), [sessions.Session(observed_at, 20)])
    check("a merge keeps the longer session, with how it was measured",
          [(s.minutes, s.origin) for s in merged] == [(30, "launched"), (20, "launched")]
          and [(s.minutes, s.origin) for s in sessions.merge(sessions.load(record), [])][-1] == (12, "observed"))
    net = subprocess.run([sys.executable, str(PROJECT / "tests" / "check_migration.py")], capture_output=True,
                         text=True, encoding="utf-8", errors="replace")
    check("the migration net, on a copy of the user's library: green", net.returncode == 0, net.stdout[-400:])
except Exception as exc:
    unreached("6", exc)

from logic import analysis, comparison, reports as reports_module, stats as stats_module
from data_access import reports as data_reports
from presentation import ui_continue, ui_detail, ui_library, ui_settings
from PySide6.QtWidgets import QDialog, QLabel
import json
import re

print("\n=== 7. Settings: Notice games started outside the launcher ===")
try:
    plain = {k: v for k, v in config_io.load_config().items() if k not in (rules.WATCH_GAMES_KEY, rules.WATCH_SINCE_KEY)}
    dialog = ui_settings.SettingsDialog(plain, None, known_keys=set())
    rows = {r.title.text(): r for r in dialog.findChildren(ui_settings.SettingRow)}
    row = rows.get("Notice games started outside the launcher")
    keep = rows["Keep running when the window is closed"]
    check("a third row in Running in the background, after Start with Windows",
          row is not None and row.parent() is keep.parent() and row.switch is dialog.observe_box)
    check("on by default, with the brief's quieter line", dialog.observe_box.isChecked()
          and row.hint.text() == ui_settings.WATCH_HINT, row.hint.text())
    check("its answer is its own key", dialog.values()[rules.WATCH_GAMES_KEY] is True)
    dialog.deleteLater()
    since = ui_settings.SettingsDialog(dict(plain, **{rules.WATCH_SINCE_KEY: "2026-10-18"}), None, known_keys=set())
    since_row = next(r for r in since.findChildren(ui_settings.SettingRow) if r.switch is since.observe_box)
    check("and says since when sessions have been seen", since_row.hint.text().endswith("Sessions seen since 18 Oct 2026."),
          since_row.hint.text())
    since.deleteLater()
    real_exec, real_values = ui_settings.SettingsDialog.exec, ui_settings.SettingsDialog.values
    ui_settings.SettingsDialog.exec = lambda self: QDialog.DialogCode.Accepted
    ui_settings.SettingsDialog.values = lambda self: dict(real_values(self), **{rules.WATCH_GAMES_KEY: False})
    try:
        window.open_settings()
        check("switched off in Settings: the looks stop at once", window.process_worker is None)
        ui_settings.SettingsDialog.values = lambda self: dict(real_values(self), **{rules.WATCH_GAMES_KEY: True})
        window.open_settings()
        check("and on again from Settings, they start", window.process_worker is not None
              and window.process_worker.isRunning())
    finally:
        ui_settings.SettingsDialog.exec, ui_settings.SettingsDialog.values = real_exec, real_values
except Exception as exc:
    unreached("7", exc)

print("\n=== 8. while a game is seen running ===")
try:
    conn = window.overrides._conn
    steam_key = conn.execute("SELECT g.identity_key FROM game g JOIN install i ON i.game_id = g.id "
                             "WHERE g.source = 'steam' ORDER BY g.identity_key LIMIT 1").fetchone()[0]
    window._stop_watch()  # the real looks would end the planted session: the window alone, here
    window.reload_views()
    view = window.by_key[steam_key]
    seen = observe.Seen(steam_key, view.display_name, False, "uri",
                        datetime.now().astimezone().replace(microsecond=0), time.monotonic(), seconds=600)
    window.observer.live[steam_key] = seen
    window.show_detail(steam_key)
    settle(0.6)
    page = window.detail
    pill = page.pills["Running"]
    check("its page says so: \"Running — timed by watching\"", not pill.isHidden()
          and pill.text().strip() == ui_detail.OBSERVED_WORDS, pill.text())
    check("Play rests: it reads Running, cannot be pressed, and there is no Stop",
          page.play_button.text() == ui_detail.OBSERVED_PLAY_TEXT and not page.play_button.isEnabled()
          and page.play_button.objectName() == "HeroPlay", (page.play_button.text(), page.play_button.objectName()))
    check("its tile's line says so too", ui_library.tile_subtitle(view, None, True) == "Running — timed by watching")
    calls = []
    real_play = ui_actions.play
    ui_actions.play = lambda w, v: calls.append(v.key)
    try:
        window._play_key(steam_key)
        window.play(view)
    finally:
        ui_actions.play = real_play
    check("Play from the tile, the card, the tray or the pad never starts it a second time", calls == [], calls)
    del window.observer.live[steam_key]
    window.refresh_running_state()
    settle(0.3)
    check("it ends: the page's Play is back, the words gone", page.play_button.isEnabled()
          and page.play_button.text() == ui_detail.PLAY_TEXT and pill.isHidden())
    window._bank_observed(seen, final=True)
    window.reload_views()
    window.show_detail(steam_key)
    settle(0.6)
    lengths = [row[2] for row in page.session_bars.rows]
    check("a Steam game now has Recent sessions, and an observed one's length is marked approximate",
          not page.sessions_card.isHidden() and lengths and lengths[0].startswith(ui_detail.APPROXIMATE), lengths)
    window.show_library()
    settle(0.4)
    picked = ui_continue.pick(window.views)
    check("the Continue card offers it next: picked by last played, an observed session moves it",
          picked is not None and picked.key == steam_key, picked and picked.display_name)
    window._apply_watch()
except Exception as exc:
    unreached("8", exc)

print("\n=== 9. the anonymous export and the comparison ===")
try:
    built = analysis.build(window.overrides, code="p-0123456789")
    by_origin = built["sessions"]["by_origin"]
    total = built["sessions"]["count"]
    check(f"format version 2 or later (3 since Phase 102), and the session totals say how they were measured "
          f"({by_origin})", built["version"] >= 2 and set(by_origin) == {"launched", "observed"}
          and by_origin["launched"]["count"] + by_origin["observed"]["count"] == total
          and by_origin["observed"]["count"] >= 1)
    observed_games = [g for g in built["games"] if g.get("observed_sessions")]
    check("each game carries its observed sessions' count and minutes",
          observed_games and all(g["observed_minutes"] > 0 for g in observed_games))
    check("and the file says what the column means", "observed" in built["sessions"]["origin_means"])
    folder = Path(box.folder) / "p93 exports"
    folder.mkdir(exist_ok=True)
    new_file = folder / "new.json"
    new_file.write_text(json.dumps(built), encoding="utf-8")
    old = json.loads(json.dumps(built))
    old["version"] = 1
    old["participant"] = "p-9876543210"
    del old["sessions"]["by_origin"], old["sessions"]["origin_means"]
    for g in old["games"]:
        g.pop("observed_sessions", None)
        g.pop("observed_minutes", None)
    (folder / "old.json").write_text(json.dumps(old), encoding="utf-8")
    loaded = comparison.load([folder])
    by_code = {p.code: p for p in loaded.participants}
    check("an export of version 1 still compares, read as every session launched",
          "p-9876543210" in by_code and by_code["p-9876543210"].observed_sessions == 0
          and by_code["p-9876543210"].sessions == total, (loaded.skipped, list(by_code)))
    check("and a version 2 one gives its observed sessions", by_code["p-0123456789"].observed_sessions
          == by_origin["observed"]["count"])
except Exception as exc:
    unreached("9", exc)

print("\n=== 10. the old words gone; the new ones true ===")
try:
    def text(rel):
        return (PROJECT / rel).read_text(encoding="utf-8")
    gone = {
        "logic/reports.py": ["Only the games the launcher starts and times",
                             "A game played from its own shortcut, or before the launcher was installed",
                             "and which games no source times"],
        "logic/stats.py": ['none of that time is counted here."'],
        "presentation/ui_detail.py": ["a URI game is never timed, so it has no sessions at all"],
        "presentation/ui_window.py": ["a Steam, Epic or Xbox game is never timed, so there are no sessions"],
        "data_access/reports.py": ["'started by its own client'"],
        "docs/ANALIZA.md": ["Un joc pornit de Steam, Epic sau Xbox nu e cronometrat aici",
                            "Doar jocurile pornite și cronometrate de launcher: contoarele Steam au totaluri",
                            "Epic, Xbox și Ubisoft nu spun niciodată dacă un joc a fost jucat",
                            "ce jocuri nu cronometrează nicio sursă."],
    }
    found = [(rel, words) for rel, many in gone.items() for words in many if words in text(rel)]
    check("not one of the old sentences is left where it was", not found, found)
    words = stats_module.caveats(stats_module.gather(window.views, window.overrides, watching_since="2026-10-18"))
    check("Stats says since when Steam, Epic and Xbox games are seen, and that Steam's hours stay Steam's",
          any("Since 18 Oct 2026 the launcher sees them running" in w and "stay Steam's own counter" in w for w in words),
          words)
    check("and that the observed sessions' ends are within a few seconds",
          any("were seen rather than started here" in w for w in words))
    off = stats_module.caveats(stats_module.gather(window.views, window.overrides, watching_since=None))
    check("with the watch off, it says the switch is there", any("Notice games started outside the launcher" in w
                                                                 for w in off))
    built_reports = reports_module.build(data_reports.Reports(window.overrides._conn))
    five = next(r for r in built_reports if r.key == "sessions")
    measured = next(p for p in five.parts if p.heading == "How they were measured")
    check("report 5 says how its sessions were measured, and the observed ones in its sentence",
          measured.data[1][0] == rules.SESSION_OBSERVED and measured.data[1][1] >= 1
          and "seen running rather than started here" in five.sentence, five.sentence)
    quoted = re.search(r"```sql\n-- session_origins\n(.*?)\n```", text("docs/ANALIZA.md"), re.S)
    check("ANALIZA quotes the new query exactly as the code has it",
          quoted and quoted.group(1).strip() == data_reports.QUERIES["session_origins"].strip())
    check("CITESTE-MA names the third switch in the friends' words, and keeps to its page",
          "**Notice games started outside the launcher** (pornit)" in text("docs/CITESTE-MA.md")
          and len(text("docs/CITESTE-MA.md").splitlines()) <= 110)
    check("BAZA_DE_DATE has the column, the upgrade and the no-double-count rule with the two-store case",
          all(w in text("docs/BAZA_DE_DATE.md") for w in ("### Versiunea 7 (faza 93)", "nicio oră numărată de două ori",
                                                          "nu e o numărare dublă")))
except Exception as exc:
    unreached("10", exc)

print("\n=== 11. the reports' time; one look's time; the layers; the real data ===")
reports_times = []
for _ in range(5):
    began = time.perf_counter()
    reports_module.build(data_reports.Reports(window.overrides._conn))
    reports_times.append((time.perf_counter() - began) * 1000)
check(f"the reports (eleven since Phase 103): best of 5 {min(reports_times):.1f} ms, under 50", min(reports_times) < 50, reports_times)
times = []
for _ in range(20):
    began = time.perf_counter()
    observe.processes()
    times.append((time.perf_counter() - began) * 1000)
times.sort()
median = (times[9] + times[10]) / 2
check(f"one look at every process: median {median:.1f} ms, under {rules.WATCH_ENUMERATION_MAX_MS}",
      median < rules.WATCH_ENUMERATION_MAX_MS, times)
layers = subprocess.run([sys.executable, str(PROJECT / "tests" / "check_layers.py")], capture_output=True, text=True,
                        encoding="utf-8", errors="replace")
check("no import points up a layer; sqlite3 only in data_access/", layers.returncode == 0, layers.stdout[-300:])
check("nothing in this suite reached the network", attempts == [], attempts)
window._stop_watch()
window._shut_down = True
window.overrides.close()
changed = box.finish()
check("config.json, the library database and the Run key's value are unchanged", not changed, changed)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
