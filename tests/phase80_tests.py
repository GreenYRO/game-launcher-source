"""Phase 80: an anonymous copy of the library, for a comparison of libraries in a bachelor thesis.

On a copy of the real library, with personal things planted in it on purpose -- a note, a custom
name, an exe picked by hand, launch arguments, purchases with notes and a typed store: the export
holds the games the library shows (hidden ones and tools left out, by GameView's own rule, checked
game by game), names only a store gave, the sessions only as totals that agree with each other
and with the database, Steam's time on the accounts marked as theirs with those accounts as A, B,
... -- and none of the planted things, no path, no account number or name, no key, no time of day;
the last check refuses a file with a path, a number or a note in it, and writes nothing; what was
paid only when asked for; one random code per PC, kept in config.json, never in the diagnostics
bundle; Settings' row and the dialog, with the mouse and with the pad; the documents.

On a throwaway copy of the data. Nothing is fetched; nothing is sent.
"""
import json
import re
import sqlite3
import sys
import urllib.request
import zipfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import sources  # the build log's notes (Phase 91)
import test_sandbox

box = test_sandbox.start()
SANDBOX = box.folder
CONFIG = SANDBOX / "config.json"
DB = SANDBOX / "library.db"


def no_network(request, *args, **kwargs):
    raise OSError("the network is blocked in this suite")


urllib.request.urlopen = no_network

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)

from adapters import controller
from data_access import catalog_io
from logic import diagnostics
from presentation import ui_settings, ui_window
from shared import rules

try:
    from logic import analysis
    from presentation import ui_analysis
except ImportError:  # the code before this phase has neither
    analysis = ui_analysis = None

passed = failed = 0
SECRET_NOTE = "left off at the lighthouse, the code is 4471"
SECRET_NAME = "Totally Legit Build by Someone"
SECRET_ARGS = "-windowed -profile=secret-profile-name"
SECRET_PURCHASE_NOTE = "a birthday gift from my aunt"
SECRET_SHOP = "Bob's back-alley key shop"


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


def modal():
    return QApplication.activeModalWidget()


def run(steps, notes: dict, limit_ms: int = 60_000) -> None:
    position = [0]
    loop = QEventLoop()
    ended = [False]

    def advance():
        if position[0] >= len(steps):
            loop.quit()
            return
        QTimer.singleShot(200, advance)
        try:
            if steps[position[0]]():
                position[0] += 1
        except Exception as exc:  # noqa: BLE001
            notes.setdefault("errors", []).append(f"step {position[0]}: {exc!r}")
            position[0] += 1

    def watchdog():
        if ended[0]:  # this chain's loop has ended (Phase 86: see suite 79)
            return
        for widget in (QApplication.activePopupWidget(), QApplication.activeModalWidget()):
            if widget is not None:
                widget.close()
        notes["watchdog"] = True
        loop.quit()

    QTimer.singleShot(200, advance)
    QTimer.singleShot(limit_ms, watchdog)
    loop.exec()
    ended[0] = True
    settle(0.3)


def read_only(sql: str, params=()) -> list:
    """The copy's database read directly -- the test's own answer, not the app's."""
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def strings(node):
    if isinstance(node, dict):
        for key, value in node.items():
            yield str(key)
            yield from strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from strings(value)
    elif node is not None:
        yield str(node)


# What is planted: a folder game with nothing chosen for it gets a note, a custom name, an exe
# picked by hand and launch arguments; a Steam game gets two purchases, one at a typed shop.
store = test_sandbox.library()
entries = store.load_catalog()
folder = next(e for e in entries if e.source == "folders" and not (store.get(e.identity_key) or {}).get("name"))
shown_now = {v.key for v in catalog_io.merge(entries, store) if not v.hidden and not v.is_non_game}
steam_game = next(e for e in entries if e.source == "steam" and e.identity_key in shown_now)  # not a demo
store.update(folder.identity_key, notes=SECRET_NOTE, name=SECRET_NAME,
             exe=str(Path(folder.install_dir) / "secret_launcher.exe"), args=SECRET_ARGS)
store.add_purchase(steam_game.identity_key, paid_cents=1999, currency="EUR", store="Steam", bought_on="2026-03-14")
store.add_purchase(steam_game.identity_key, paid_cents=500, currency="EUR", store=SECRET_SHOP,
                   bought_on="2026-09-02", note=SECRET_PURCHASE_NOTE)
CODE = "p-0123456789"

print("=== 1. the export, on a copy of the real library ===")
data = None
try:
    data = analysis.build(store, CODE)
    text = json.dumps(data, ensure_ascii=False)
    check("a format of its own, versioned, the app's version, the day, the participant's code",
          # version 2 since Phase 93: how each session was measured; 3 since Phase 102: the ratings
          data["format"] == "game-launcher-analysis" and data["version"] == rules.ANALYSIS_FORMAT_VERSION
          and data["participant"] == CODE
          and re.fullmatch(r"\d{4}-\d{2}-\d{2}", data["made_on"]) and data["app_version"])
    check("it says what it is and what is never in it, in Romanian and English",
          any("lucrare de licență" in line for line in data["about"]) and "notes" in data["never_in_it"])
    check(f"{len(data['games'])} games, {data['sessions']['count']} sessions, {len(data['steam']['history'])} Steam "
          f"apps, {len(data['steam']['accounts'])} accounts -- the real library's", data["games"]
          and data["sessions"]["count"] > 0 and data["steam"]["history"], data["left_out"])
    check("readable as plain JSON, and the same read back", json.loads(text) == data)
except Exception as exc:
    unreached("1", exc)

print("\n=== 2. nothing personal in it ===")
try:
    text = json.dumps(data, ensure_ascii=False)
    lowered = text.lower()
    paths = {row[0] for sql in ("SELECT install_dir FROM install", "SELECT working_dir FROM install",
                                "SELECT launch_target FROM install WHERE launch_kind = 'exe'",
                                "SELECT custom_exe FROM game", "SELECT cover_path FROM game",
                                "SELECT banner_path FROM game", "SELECT path FROM save_folder")
             for row in read_only(sql) if row[0]}
    keys = {row[0] for row in read_only("SELECT identity_key FROM game") if ":" in row[0][:3]}
    check(f"none of the library's {len(paths)} folders, exes, pictures and save folders, nor its "
          f"{len(keys)} keys that are paths", not [p for p in paths | keys if p.lower() in lowered])
    check("no backslash at all, no drive, no Users folder", "\\" not in text and ":\\" not in text
          and "users" not in lowered.replace("users'", ""), re.findall(r".{20}\\\\.{20}", text)[:2])
    accounts = read_only("SELECT account_id, steam_id64, account_name, persona FROM steam_account")
    numbers = {str(n) for row in accounts for n in row[:2]}
    names = {row[i] for row in accounts for i in (2, 3) if row[i]}
    values = set(strings(data))
    check(f"no Steam account's number or SteamID64 ({len(numbers)}), anywhere",
          not [n for n in numbers if any(re.search(rf"(?<!\d){n}(?!\d)", v) for v in values)])
    check(f"no account name or persona ({len(names)})", not [n for n in names if n.lower() in lowered], names)
    check("none of what was planted: the note, the custom name, the exe, the launch arguments",
          SECRET_NOTE not in text and SECRET_NAME not in text and "secret_launcher" not in text
          and SECRET_ARGS not in text)
    key = json.loads(CONFIG.read_text(encoding="utf-8")).get("steamgriddb_key") or "no-key-in-this-copy"
    check("not the SteamGridDB key", key not in text)
    # Days, never a time (format 3, Phase 102): a rated session's day and the day a mark was set.
    days = ({data["made_on"]} | {r["day"] for g in data["games"] for r in g.get("ratings") or []}
            | {g["status_since"] for g in data["games"] if g.get("status_since")})
    check("no time of day of any session: no moment anywhere, only months, the day it was made, and the days of a "
          "rated session and of a mark", not re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:", text)
          and set(re.findall(r"\d{4}-\d{2}-\d{2}", text)) <= days, re.findall(r"\d{4}-\d{2}-\d{2}T", text)[:3])
    unmatched = [g for g in data["games"] if g["source"] in ("folders", "unknown") and g["steam_appid"] is None]
    check(f"the {len(unmatched)} folder games matched to nothing have no name in it",
          unmatched and all(g["name"] is None for g in unmatched))
    steam_names = dict(read_only("SELECT appid, name FROM steam_app"))
    matched = [g for g in data["games"] if g["steam_appid"] is not None]
    check(f"the {len(matched)} games matched to Steam carry Steam's own name, never a chosen one",
          all(g["name"] == steam_names.get(g["steam_appid"]) or (steam_names.get(g["steam_appid"]) is None)
              for g in matched))
    check("nothing paid in it unless asked: no amounts, no shop", "paid" not in "".join(
        k for g in data["games"] for k in g) and "1999" not in text and SECRET_SHOP not in text
          and data["paid_included"] is False)
except Exception as exc:
    unreached("2", exc)

print("\n=== 3. which games: the library's, as it shows them ===")
try:
    views = catalog_io.merge(store.load_catalog(), store)
    columns = {key: (marked, appid_source, app_type) for key, marked, appid_source, app_type in read_only(
        "SELECT g.identity_key, g.is_tool, g.appid_source, s.app_type FROM game g "
        "LEFT JOIN steam_app s ON s.appid = g.steam_appid")}
    disagree = [v.key for v in views if v.key in columns and analysis._is_tool(*columns[v.key]) != v.is_non_game]
    check(f"tools told from games by GameView's own rule, for every one of the {len(views)} installed games",
          not disagree, disagree)
    shown = [v for v in views if not v.hidden and not v.is_non_game]
    exported = [g for g in data["games"] if g["installed"]]
    check(f"every installed game the library shows is in it ({len(shown)}), and none it hides",
          len(exported) == len(shown)
          and sorted(g["source"] for g in exported) == sorted(v.entry.source for v in shown))
    hidden_before = data["left_out"].get("hidden", 0)
    victim = shown[0]
    store.update(victim.key, hidden=True)
    again = analysis.build(store, CODE)
    check("hide one more game and it leaves the export", len(again["games"]) == len(data["games"]) - 1
          and again["left_out"].get("hidden") == hidden_before + 1)
    store.update(victim.key, hidden=None)
    carried = read_only("SELECT COUNT(*) FROM game g WHERE carried_to IS NOT NULL AND NOT EXISTS "
                        "(SELECT 1 FROM install i WHERE i.game_id = g.id)")[0][0]
    check(f"a game whose history moved to a newer install is not counted twice ({carried} such) -- "
          "unless it is installed again", len(data["games"]) + sum(data["left_out"].values()) == read_only(
              "SELECT COUNT(*) FROM game g WHERE carried_to IS NULL OR EXISTS "
              "(SELECT 1 FROM install i WHERE i.game_id = g.id)")[0][0], data["left_out"])
except Exception as exc:
    unreached("3", exc)

print("\n=== 4. how much was played: totals that agree ===")
try:
    sessions = data["sessions"]
    check("by month, by hour and by weekday each add up to the sessions' minutes",
          sum(sessions["by_month"].values()) == sum(sessions["by_hour"].values())
          == sum(sessions["by_weekday"].values()) == sessions["minutes"], sessions["minutes"])
    check("and the games' own counts add up to the same",
          sum(g["sessions"] for g in data["games"]) == sessions["count"]
          and sum(g["session_minutes"] for g in data["games"]) == sessions["minutes"])
    left = read_only(
        "SELECT COUNT(se.id), COALESCE(SUM(se.minutes), 0) FROM session se JOIN game g ON g.id = se.game_id "
        "LEFT JOIN steam_app s ON s.appid = g.steam_appid WHERE (g.carried_to IS NULL OR EXISTS (SELECT 1 FROM install i WHERE i.game_id = g.id)) AND g.hidden = 0 AND "
        "NOT (COALESCE(g.is_tool, CASE WHEN g.appid_source = 'manifest' AND s.app_type IS NOT NULL "
        "AND s.app_type <> 'game' THEN 1 ELSE 0 END) = 1)")[0]
    check(f"the database agrees: {left[0]} sessions, {left[1]} minutes, of the games shown",
          (sessions["count"], sessions["minutes"]) == left, (sessions["count"], sessions["minutes"]))
    hours = read_only("SELECT local_hour, SUM(minutes) FROM session GROUP BY local_hour")
    check("the hour is the local hour each session was written with (the database's own column)",
          all(sessions["by_hour"][str(h)] <= m for h, m in hours))
    launcher = sum(g["launcher_minutes"] or 0 for g in data["games"])
    check(f"the launcher's minutes per game: {launcher} in all, each its total's whole minutes",
          launcher > 0 and all(g["launcher_minutes"] is None or g["launcher_minutes"] >= 0 for g in data["games"]))
except Exception as exc:
    unreached("4", exc)

print("\n=== 5. Steam's own time: the accounts marked as theirs, as A, B, ... ===")
try:
    mine = read_only("SELECT appid, minutes, accounts FROM v_steam_time_mine")
    history = {h["steam_appid"]: (h["minutes"], h["accounts"]) for h in data["steam"]["history"]}
    check(f"every app on those accounts, its minutes and how many hold it ({len(mine)})",
          history == {appid: (minutes, held) for appid, minutes, held in mine})
    marked = read_only("SELECT account_id FROM steam_account WHERE is_mine = 1")
    labels = [a["account"] for a in data["steam"]["accounts"]]
    check(f"the {len(marked)} accounts marked as theirs, called {', '.join(labels)}, most played first",
          len(labels) == len(marked) and labels == [chr(65 + n) for n in range(len(labels))]
          and [a["minutes"] for a in data["steam"]["accounts"]] == sorted(
              (a["minutes"] for a in data["steam"]["accounts"]), reverse=True))
    check("each account only its minutes, apps with time and the month last read",
          all(set(a) == {"account", "minutes", "apps_with_time", "last_read"} for a in data["steam"]["accounts"]))
    if marked:
        store.set_account_mark(marked[0][0], False)
        fewer = analysis.build(store, CODE)
        check("an account marked not theirs is not in it", len(fewer["steam"]["accounts"]) == len(marked) - 1)
        store.set_account_mark(marked[0][0], True)
except Exception as exc:
    unreached("5", exc)

print("\n=== 6. what was paid, only when asked ===")
try:
    with_paid = analysis.build(store, CODE, include_paid=True)
    text = json.dumps(with_paid, ensure_ascii=False)
    bought = [p for g in with_paid["games"] for p in g.get("paid", [])]
    check("asked for: the two purchases, amount, currency and month",
          sorted((p["amount_cents"], p["month"]) for p in bought if p["month"] in ("2026-03", "2026-09"))
          == [(500, "2026-09"), (1999, "2026-03")], bought)
    check("a typed shop leaves as 'other'; a purchase's note never leaves",
          SECRET_SHOP not in text and SECRET_PURCHASE_NOTE not in text and any(p["store"] == "other" for p in bought))
    check("and it says it holds them", with_paid["paid_included"] is True
          and "What you paid: included" in " ".join(analysis.summary(with_paid)))
except Exception as exc:
    unreached("6", exc)

print("\n=== 7. the last check: something personal, and nothing is written ===")
try:
    personal = store.personal_values()
    check("it knows the library's paths, account numbers and notes",
          personal["paths"] and personal["ids"] and SECRET_NOTE in personal["texts"])
    target = SANDBOX / "exports" / "planted.json"
    for label, plant in (("a folder path", lambda d: d["games"][0].update(name=folder.install_dir)),
                         ("a Steam account's number", lambda d: d["steam"]["accounts"][0].update(
                             minutes=int(sorted(personal["ids"])[0]))),
                         ("a note or launch argument", lambda d: d["games"][0].update(status=SECRET_NOTE))):
        planted = json.loads(json.dumps(data))
        plant(planted)
        try:
            analysis.write(target, planted, personal)
            refused = None
        except analysis.Refused as exc:
            refused = str(exc)
        check(f"{label} planted: refused, saying what kind, and nothing written",
              refused == label and not target.exists()
              and not list((SANDBOX / "exports").glob(".analysis-*")), refused)
    clean = SANDBOX / "exports" / "clean.json"
    analysis.write(clean, data, personal)
    check("the real one written whole, and read back the same", json.loads(clean.read_text(encoding="utf-8")) == data
          and not list(clean.parent.glob(".analysis-*")))
except Exception as exc:
    unreached("7", exc)

print("\n=== 8. one code per PC, never in the diagnostics ===")
try:
    new, is_new = analysis.participant({})
    kept, kept_new = analysis.participant({rules.ANALYSIS_ID_SETTING: CODE})
    bad, bad_new = analysis.participant({rules.ANALYSIS_ID_SETTING: "Andrei's PC"})
    check("a new code is random, p- and ten hex digits; a kept one is kept; anything else is replaced",
          re.fullmatch(r"p-[0-9a-f]{10}", new) and is_new and kept == CODE and not kept_new
          and bad != "Andrei's PC" and bad_new)
except Exception as exc:
    unreached("8", exc)
store.close()

print("\n=== 9. Settings: the row, the dialog, the mouse and the pad ===")
try:
    saved_to = SANDBOX / "exports" / "from-settings.json"
    window = ui_window.MainWindow()
    window.resize(1280, 820)
    window.show()
    settle(0.5)
    config_before = json.loads(CONFIG.read_text(encoding="utf-8"))
    dialog = ui_settings.SettingsDialog(window.config, window, store=window.overrides)
    dialog.choose_analysis_path = lambda: str(saved_to)
    dialog.show()
    settle(0.3)
    notes: dict = {}
    # The click is scheduled, not made: it opens a dialog that waits, and a step that waits is
    # called again by the chain's own timer -- a dialog inside a dialog, until the stack runs out.
    run([lambda: QTimer.singleShot(0, dialog.analysis_button.click) or True,
         lambda: isinstance(modal(), ui_analysis.AnalysisDialog),
         lambda: notes.update(lines=[label.text() for label in modal().lines], paid=modal().include_paid.isChecked(),
                              title=modal().windowTitle()) or True,
         lambda: modal().save_button.click() or True,
         lambda: not isinstance(modal(), ui_analysis.AnalysisDialog)], notes)
    written = json.loads(saved_to.read_text(encoding="utf-8")) if saved_to.is_file() else {}
    code = json.loads(CONFIG.read_text(encoding="utf-8")).get(rules.ANALYSIS_ID_SETTING)
    check("the dialog shows what is in it, in the library's numbers, before anything is saved",
          notes.get("title") == ui_analysis.TITLE and notes.get("lines")
          and notes["lines"][0].startswith("•  ") and "games:" in notes["lines"][0], notes.get("lines"))
    check("what was paid is off unless switched on", notes.get("paid") is False and written.get("paid_included") is False)
    check("Save: the file where it was asked to go, with this PC's new code -- kept in config.json",
          written.get("participant") == code and re.fullmatch(r"p-[0-9a-f]{10}", code or ""))
    check("and the row says where, and that sending it is up to them",
          dialog.analysis_status.isVisible() and "Saved as" in dialog.analysis_status.text()
          and "up to you" in dialog.analysis_status.text())
    check("config.json gained the code and nothing else changed",
          {k: v for k, v in json.loads(CONFIG.read_text(encoding="utf-8")).items()
           if k != rules.ANALYSIS_ID_SETTING} == config_before)

    second = SANDBOX / "exports" / "from-the-couch.json"
    dialog.choose_analysis_path = lambda: str(second)
    notes = {}

    def press(name):
        window.pads.action.emit(name)

    # The click is scheduled, not made: it opens a dialog that waits, and a step that waits is
    # called again by the chain's own timer -- a dialog inside a dialog, until the stack runs out.
    run([lambda: QTimer.singleShot(0, dialog.analysis_button.click) or True,
         lambda: isinstance(modal(), ui_analysis.AnalysisDialog),
         lambda: notes.update(start=modal().focusWidget() is modal().include_paid) or True,
         lambda: press(controller.ACTIVATE) or True,  # A: what I paid, on
         lambda: notes.update(on=modal().include_paid.isChecked()) or True,
         lambda: press(controller.DOWN) or True,
         lambda: press(controller.DOWN) or True,
         lambda: notes.update(at_save=modal().focusWidget() is modal().save_button) or True,
         lambda: press(controller.ACTIVATE) or True,
         lambda: not isinstance(modal(), ui_analysis.AnalysisDialog)], notes)
    couch = json.loads(second.read_text(encoding="utf-8")) if second.is_file() else {}
    check("with the pad (its presses, as the hub sends them): it starts on the switch; A turns it on; down, down to Save; A saves",
          notes.get("start") and notes.get("on") and notes.get("at_save") and couch.get("paid_included") is True,
          notes)
    check("the same code as the first time: one PC, one participant", couch.get("participant") == code)
    third = SANDBOX / "exports" / "cancelled.json"
    dialog.choose_analysis_path = lambda: str(third)
    # The click is scheduled, not made: it opens a dialog that waits, and a step that waits is
    # called again by the chain's own timer -- a dialog inside a dialog, until the stack runs out.
    run([lambda: QTimer.singleShot(0, dialog.analysis_button.click) or True,
         lambda: isinstance(modal(), ui_analysis.AnalysisDialog),
         lambda: press(controller.BACK) or True,
         lambda: not isinstance(modal(), ui_analysis.AnalysisDialog)], notes)
    check("B cancels: nothing written", not third.exists())
    check("no watchdog and no error", not notes.get("watchdog") and not notes.get("errors"), notes.get("errors"))
    dialog.reject()

    zipped = SANDBOX / "exports" / "diagnostics.zip"
    diagnostics.write(zipped, window.overrides)
    with zipfile.ZipFile(zipped) as bundle:
        settings = json.loads(bundle.read("config.json"))
        everything = b"".join(bundle.read(n) for n in bundle.namelist())
    check("the diagnostics bundle (it has paths) never carries the code: the two cannot be joined",
          rules.ANALYSIS_ID_SETTING not in settings and code.encode() not in everything)
    window.close()
    settle(0.3)
    window.overrides.close()
except Exception as exc:
    unreached("9", exc)

print("\n=== 10. the documents, and the layers ===")
try:
    readme = " ".join((PROJECT / "docs" / "CITESTE-MA.md").read_text(encoding="utf-8").split())
    check("CITESTE-MA.md says where the export is made and what it holds",
          "Anonymous export" in readme and "nu pleacă nimic singur" in readme)
    plan = (PROJECT / "docs" / "DISTRIBUTIE.md").read_text(encoding="utf-8")
    ten = plan.split("## 10.")[1].split("## 11.")[0]
    check("DISTRIBUTIE.md section 10 is written: the format, field by field",
          "încă negândit" not in ten and '"steam_minutes"' in ten and "pseudonim" in ten)
    claude = (PROJECT / "CLAUDE.md").read_text(encoding="utf-8")
    check("CLAUDE.md has the phase", "| 80 |" in claude and "## Phase 80 notes" in sources.build_log())
    import subprocess

    layers = subprocess.run([sys.executable, str(PROJECT / "tests" / "check_layers.py")], cwd=PROJECT,
                            capture_output=True, text=True, timeout=120)
    check("no import points up a layer; SQL only in data_access/", "upward imports: 0" in layers.stdout
          and "sqlite3 outside data_access/: 0" in layers.stdout, layers.stdout[-200:])
except Exception as exc:
    unreached("10", exc)

print("\n=== 11. the real library is exactly as it was found ===")
changed = box.finish()
check("config.json and the library database are unchanged", not changed, changed)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
