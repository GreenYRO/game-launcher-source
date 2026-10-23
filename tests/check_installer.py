"""The built installer, run for real, twice -- in a fake profile, never the user's (Phase 78).

    .venv\\Scripts\\python.exe packaging\\build.py
    .venv\\Scripts\\python.exe tests\\check_installer.py [--over OLD-Setup.exe]

Not part of run_all: it needs a fresh build (half a minute, 70 MB) and takes a few minutes.
Run it after every build that is to be handed to anyone. Grown from Phase 47's and Phase
68's one-off tests, which lived in a scratch folder.

USERPROFILE, APPDATA and LOCALAPPDATA point into a temporary folder for every process it starts:
the install folder, the Desktop and the Start Menu are all found through them -- and the
uninstaller removes every shortcut that declares the app id, which the user's four real ones
do. Those four are fingerprinted before and after. The one thing outside the fake profile is
the Add/Remove Programs entry in HKCU: it must be absent before (no installed copy here), and
the test's uninstall removes the one its install writes. The user's own launcher may be open
while this runs, under the same window title: every window here is found by its process.

What it proves, in order: the build is this code's (the version stamped, the schema and its
upgrade scripts and the fonts byte for byte); a first install; a first start as a friend's PC
sees it -- no config.json, so the question comes up, and closing it writes an empty list of
folders and the app goes on to scan the stores; the second question, a SteamGridDB key, closed
and nothing written (Phase 79); the update check -- the one real request to GitHub, which has no
release to offer until the first is published (Phase 79); a second install over the first keeps every
byte of the user's data (the database, the settings, the log, the cache, the backups) and
replaces the program, leaving it exactly as the first install did (an idempotent upgrade); the
updated copy starts without asking again; a quiet uninstall keeps the data; and the user's own
shortcuts were never touched.

Start with Windows (Phase 92): the installed copy's Run value is looked for under a test key of this
run's own (rules.STARTUP_TEST_KEY_ENV, in every process it starts), never the user's Run key, whose
value is fingerprinted before and after. Planted there as the installed copy writes it, the value
survives the update over the first install and is gone after the uninstall.

With --over, the installer of the version the friends have (kept aside before the build replaced
it), the path each of them takes, in a second fake profile (Phase 85): that version installed and
started as a friend's PC starts it, then this installer over it; the updated copy starts without
a question, brings its library up to this version's schema with a snapshot of the older file
first, keeps the library's games row for row and the settings, and logs no error.

The one question and what is new on screen (Phase 100, for 1.2.8): a first run's start never asks whether to
keep running in the tray; the next start does, once, and closing it is "Not now" -- the day written, the switch
left off. Then what the installed copy shows is read the way a screen reader reads it, through Windows' UI
Automation from PowerShell (no new dependency): the For you place in its window, and, Settings pressed, the
Accent row with its five colours; Settings closed again, nothing written.

What 1.2.10 brings (Phase 107): on the friend's path, the first start after the update opens "What's new in
1.2.10" first -- read off the screen, the version seen still the old one while it is open and this one once it is
closed -- and only then the one question; and this version's notes in the build, byte for byte.

What 1.2.9 brings (Phase 104): Settings' "After a game" row, "Ask how a session was", read off the screen the same
way; and, on the friend's path, a price alert -- a wished game with a target, one price above it and a newer one
under it planted as a scan leaves it for the window (the price hand-off), the network off: the next start lands
it and the alert is written once, said on screen, and the same price planted again sets nothing off.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
import winreg
from pathlib import Path

import win32con
import win32gui
import win32process

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
# Whatever it prints reaches a file or a console whatever its code page (Phase 107: a Romanian letter stopped a run).
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from logic import first_run  # noqa: E402 -- the project's own answer to "is there an XboxGames folder"
from presentation import ui_offer, ui_rules, ui_whats_new  # noqa: E402 -- the dialogs' titles, the accents (100, 107)
from shared import rules, version  # noqa: E402

SETUP = PROJECT / "dist" / "GameLauncher-Setup.exe"
BUILT = PROJECT / "build" / "app" / "GameLauncher" / "_internal"
KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\GameLauncher"
NAMES = ("Game Launcher.lnk", "Game Launcher (TV).lnk")
QUESTION = "Where do you keep your games?"
KEY_QUESTION = "Want more cover art?"  # ui_first_run.KEY_TITLE (suite 79 holds the two together)
OFFER = ui_offer.TITLE  # the one question (Phase 99): "Keep Game Launcher running?"
WHATS_NEW = ui_whats_new.TITLE.format(version=version.APP_VERSION)  # "What's new in 1.2.10" (Phases 106, 107)
ACCENTS = tuple(f"{name} accent" for name in ui_rules.ACCENTS)  # each swatch's accessible name (ui_settings)
DATA_NAMES = ("library.db", "config.json", "launcher.log")
# A planted wished game (Phase 104): an appid Steam has no app for, never asked about -- the network is off then.
WISHED = 9_999_901
WISHED_ACCOUNT = 123_456_789  # a planted account marked mine; its SteamID64 by the schema's own rule
# Start with Windows (Phase 92): this run's own key root, never the user's Run key.
STARTUP_ROOT = rf"Software\GameLauncherTest\installer-{os.getpid()}"
# The newest schema this build brings: the number of its newest upgrade script (NNN_name.sql).
SCHEMA = max(int(p.name[:3]) for p in (PROJECT / "data_access" / "upgrades").glob("[0-9][0-9][0-9]_*.sql"))
OVER = None
if "--over" in sys.argv[1:]:
    at = sys.argv.index("--over")
    OVER = Path(sys.argv[at + 1]) if at + 1 < len(sys.argv) else None
    if OVER is None or not OVER.is_file():
        raise SystemExit("--over names the installer of the version before this one, and there is none there.")
passed = failed = 0


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"   PASS  {name}")
    else:
        failed += 1
        print(f"   FAIL  {name}   {detail}")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree(folder: Path) -> dict[str, str]:
    """Every file under a folder, by its path inside it, with its fingerprint."""
    return {p.relative_to(folder).as_posix(): sha(p) for p in sorted(folder.rglob("*")) if p.is_file()}


def registered() -> dict | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY) as key:
            return {name: winreg.QueryValueEx(key, name)[0] for name in ("DisplayName", "DisplayVersion")}
    except OSError:
        return None


def windows_of(pid: int) -> dict[int, str]:
    """The visible top-level windows of one process, with their titles."""
    found = {}

    def each(hwnd, _):
        if win32gui.IsWindowVisible(hwnd) and win32process.GetWindowThreadProcessId(hwnd)[1] == pid:
            found[hwnd] = win32gui.GetWindowText(hwnd)
        return True

    win32gui.EnumWindows(each, None)
    return found


def wait_for(predicate, seconds: float, step: float = 0.5):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        answer = predicate()
        if answer:
            return answer
        time.sleep(step)
    return predicate()


def log_text(target: Path) -> str:
    path = target / rules.LOG_FILENAME
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def close_app(app: subprocess.Popen) -> bool:
    """Close the app as a person does -- its window's close -- and wait; terminate if it will not."""
    for hwnd, title in windows_of(app.pid).items():
        if title == version.APP_NAME:
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
    try:
        app.wait(timeout=30)
        return True
    except subprocess.TimeoutExpired:
        app.terminate()
        app.wait(timeout=30)
        return False


def fake_env(profile: Path) -> dict:
    """The environment of a process whose profile -- install folder, Desktop, Start Menu -- is `profile`.

    Its Start with Windows value under this run's own key, too (Phase 92): HKCU cannot be redirected
    the way the profile's folders are."""
    env = dict(os.environ, USERPROFILE=str(profile), APPDATA=str(profile / "AppData" / "Roaming"),
               LOCALAPPDATA=str(profile / "AppData" / "Local"))
    env[rules.STARTUP_TEST_KEY_ENV] = STARTUP_ROOT
    for folder in (profile / "Desktop", Path(env["APPDATA"]), Path(env["LOCALAPPDATA"])):
        folder.mkdir(parents=True, exist_ok=True)
    return env


def run_value(key: str) -> str | None:
    """The Game Launcher value of a Run key -- the user's or this run's test one -- or None."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as handle:
            return winreg.QueryValueEx(handle, rules.STARTUP_VALUE_NAME)[0]
    except FileNotFoundError:
        return None


def delete_test_keys(key: str) -> None:
    """This run's test key and everything under it -- only ever below Software\\GameLauncherTest."""
    if not key.startswith("Software\\GameLauncherTest\\"):
        raise RuntimeError(f"refusing to delete {key}")
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as handle:
            children = [winreg.EnumKey(handle, i) for i in range(winreg.QueryInfoKey(handle)[0])]
    except FileNotFoundError:
        return
    for child in children:
        delete_test_keys(key + "\\" + child)
    winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key)


def seed_cache(target: Path) -> None:
    """The Steam caches copied in, read only, so a first start fetches nothing it does not need to."""
    real_cache = PROJECT / "data" / "cache"
    for part in ("steam_web.json", "steam_search.json", "steam_details", "steam_art"):
        source = real_cache / part
        if source.is_dir():
            shutil.copytree(source, target / "cache" / part)
        elif source.is_file():
            (target / "cache").mkdir(exist_ok=True)
            shutil.copyfile(source, target / "cache" / part)


def first_start(target: Path, env: dict) -> subprocess.Popen:
    """Start an installed copy with no config.json, close its two questions as someone who only uses
    stores, and wait for its first scan to land."""
    app = subprocess.Popen([str(target / "GameLauncher.exe")], env=env, cwd=str(target))
    for title in (QUESTION, KEY_QUESTION):
        asked = wait_for(lambda: next((h for h, t in windows_of(app.pid).items() if t.startswith(title)), None), 60)
        if asked:
            win32gui.PostMessage(asked, win32con.WM_CLOSE, 0, 0)
    wait_for(lambda: "scan finished" in log_text(target), 90)
    time.sleep(3)  # the landing after the scan, on the window's thread
    return app


ON_SCREEN = r"""
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$A = [System.Windows.Automation.AutomationElement]
$condition = New-Object System.Windows.Automation.PropertyCondition($A::ProcessIdProperty, [int]__PID__)
$windows = $A::RootElement.FindAll([System.Windows.Automation.TreeScope]::Children, $condition)
$pressed = $false
$out = @()
foreach ($window in $windows) {
    $names = @()
    $all = $window.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
    foreach ($element in $all) {
        $current = $element.Current
        if ($current.IsOffscreen -or -not $current.Name) { continue }
        $names += $current.Name
        if (-not $pressed -and '__PRESS__' -ne '' -and $current.Name -eq '__PRESS__' -and
                $current.ControlType -eq [System.Windows.Automation.ControlType]::Button) {
            $element.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
            $pressed = $true
        }
    }
    $out += New-Object PSObject -Property @{ title = $window.Current.Name; names = @($names) }
}
ConvertTo-Json -InputObject @{ windows = @($out); pressed = $pressed } -Depth 4 -Compress
"""


def on_screen(pid: int, press: str = "") -> tuple[list[str], bool]:
    """Every named control one process shows, as a screen reader finds them (Windows' UI Automation, from
    PowerShell), and whether `press` -- a button's name -- was pressed: Qt clicks it a moment later."""
    script = ON_SCREEN.replace("__PID__", str(int(pid))).replace("__PRESS__", press.replace("'", "''"))
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    done = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    try:
        answer = json.loads(done.stdout.strip() or "{}")
    except json.JSONDecodeError:
        print(f"   (UI Automation gave no answer: {(done.stdout + done.stderr)[-300:]})")
        return [], False
    names = []
    for window in answer.get("windows") or []:
        found = window.get("names")
        names += [found] if isinstance(found, str) else list(found or [])
    return names, bool(answer.get("pressed"))


def meets_whats_new(app: subprocess.Popen, target: Path, seen_before: str) -> None:
    """The first start after an update (Phases 106, 107): What's new comes up first, the version seen still the one
    before while it is open; its title and Close read off the screen; closed, the version seen is this one."""
    settings = lambda: json.loads((target / "config.json").read_text(encoding="utf-8"))
    shown = wait_for(lambda: next((h for h, t in windows_of(app.pid).items() if t.startswith(WHATS_NEW)), None), 30)
    check(f'"{WHATS_NEW}" comes up first, the one question not yet', bool(shown)
          and not any(t.startswith(OFFER) for t in windows_of(app.pid).values()), windows_of(app.pid))
    check(f"while it is open the version seen is still {seen_before}",
          settings().get(rules.VERSION_SEEN_KEY) == seen_before, settings().get(rules.VERSION_SEEN_KEY))
    names, _ = on_screen(app.pid)
    check("read off the screen: its title and Close", WHATS_NEW in names and "Close" in names,
          [n for n in names if "new" in n.lower() or n == "Close"][:6])
    if shown:
        win32gui.PostMessage(shown, win32con.WM_CLOSE, 0, 0)
    written = wait_for(lambda: settings().get(rules.VERSION_SEEN_KEY) == version.APP_VERSION, 20)
    check(f"closed: the version seen is {version.APP_VERSION} now, and the notes are gone",
          bool(written) and not any(t.startswith(WHATS_NEW) for t in windows_of(app.pid).values()),
          settings().get(rules.VERSION_SEEN_KEY))


def answer_offer(app: subprocess.Popen, target: Path) -> None:
    """The one question at a start that is not a first run's: it comes up, once; closed, it is Not now."""
    asked = wait_for(lambda: next((h for h, t in windows_of(app.pid).items() if t.startswith(OFFER)), None), 30)
    check(f'the one question comes up: "{OFFER}"', bool(asked), windows_of(app.pid))
    if asked:
        win32gui.PostMessage(asked, win32con.WM_CLOSE, 0, 0)  # closed: Not now
    settings = lambda: json.loads((target / "config.json").read_text(encoding="utf-8"))
    wait_for(lambda: rules.TRAY_OFFER_KEY in settings(), 20)
    saved = settings()
    check("closed, it is Not now: the day it was asked written, the switch left off",
          bool(saved.get(rules.TRAY_OFFER_KEY)) and not saved.get(rules.KEEP_RUNNING_KEY)
          and not any(t.startswith(OFFER) for t in windows_of(app.pid).values()),
          {k: saved.get(k) for k in (rules.TRAY_OFFER_KEY, rules.KEEP_RUNNING_KEY)})


def shows_whats_new(app: subprocess.Popen, target: Path) -> None:
    """What 1.2.8 and 1.2.9 bring, on the installed copy's own screen (Phases 100, 104): For you in its window;
    Settings pressed, the Accent row and its five colours, and the After a game row; Settings closed, and nothing
    written."""
    names, _ = on_screen(app.pid)
    check("its window shows the For you place", "For you" in names, names[:12])
    config_before = (target / "config.json").read_bytes()
    _, pressed = on_screen(app.pid, press="Settings")
    # Qt adds the application's name to a dialog's title in an installed copy: "Settings - Game Launcher".
    opened = wait_for(lambda: next((h for h, t in windows_of(app.pid).items() if t.startswith("Settings")), None), 20)
    names, _ = on_screen(app.pid) if opened else ([], False)
    check(f"Settings, pressed, shows the Accent row and its {len(ACCENTS)} colours",
          pressed and bool(opened) and "Accent" in names and all(a in names for a in ACCENTS),
          (pressed, bool(opened), [n for n in names if "ccent" in n]))
    check('and the After a game row, "Ask how a session was" (1.2.9: the question after a session)',
          "After a game" in names and "Ask how a session was" in names,
          [n for n in names if "game" in n or "session" in n][:6])
    if opened:
        win32gui.PostMessage(opened, win32con.WM_CLOSE, 0, 0)  # closed: Cancel, nothing kept
    gone = wait_for(lambda: not any(t.startswith("Settings") for t in windows_of(app.pid).values()), 20)
    check("closed again, and nothing written", bool(gone) and (target / "config.json").read_bytes() == config_before)


def icon_images(path: Path) -> list[bytes]:
    """The pictures an .ico holds, smallest first, each as its bytes (ICONDIR, then 16-byte entries)."""
    data = path.read_bytes()
    count = int.from_bytes(data[4:6], "little")
    entries = []
    for i in range(count):
        entry = data[6 + 16 * i:22 + 16 * i]
        size, offset = int.from_bytes(entry[8:12], "little"), int.from_bytes(entry[12:16], "little")
        entries.append((entry[0] or 256, data[offset:offset + size]))
    return [blob for _, blob in sorted(entries, key=lambda e: e[0])]


def read_db(path: Path, sql: str):
    """A question to a library file, on a read-only connection: nothing here may change it."""
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=10)
    try:
        return connection.execute(sql).fetchall()
    finally:
        connection.close()


def views_answer(path: Path) -> list[str]:
    """The views of a library file that cannot be read -- none, when the schema is whole."""
    broken = []
    for (name,) in read_db(path, "SELECT name FROM sqlite_master WHERE type = 'view'"):
        try:
            read_db(path, f'SELECT COUNT(*) FROM "{name}"')
        except sqlite3.Error as exc:
            broken.append(f"{name}: {exc}")
    return broken


def plant_alert(target: Path, again: bool = False) -> str:
    """A price alert waiting to happen (Phase 104), as a friend's library would hold it: an account marked theirs
    with a game on its wishlist, a target of 20,00 EUR, one price above it -- and a new price under it in the price
    hand-off, where a scan leaves what it fetched for the window to land. The network off in config.json, so
    nothing is asked. `again`: only the same new price planted once more. Answers the new price's moment."""
    observed = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(time.time() - 60))
    if not again:
        settings = json.loads((target / "config.json").read_text(encoding="utf-8"))
        settings["allow_network"] = False
        (target / "config.json").write_text(json.dumps(settings, indent=2), encoding="utf-8")
        read_at = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(time.time() - 120))
        connection = sqlite3.connect(target / rules.LIBRARY_DB_FILE)
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            with connection:
                connection.execute("INSERT OR IGNORE INTO steam_app (appid, has_record, name) VALUES (?, 0, ?)",
                                   (WISHED, "Planted Wish"))
                connection.execute("INSERT INTO steam_account (account_id, steam_id64, is_mine, first_seen, last_seen) "
                                   "VALUES (?, ?, 1, ?, ?)", (WISHED_ACCOUNT, WISHED_ACCOUNT + 76561197960265728,
                                                              read_at, read_at))
                connection.execute("INSERT INTO wishlist_read (account_id, read_at, state, items) VALUES (?, ?, 'items', 1)",
                                   (WISHED_ACCOUNT, read_at))
                connection.execute("INSERT INTO wishlist (account_id, appid, priority, first_seen, last_seen) "
                                   "VALUES (?, ?, 0, ?, ?)", (WISHED_ACCOUNT, WISHED, read_at, read_at))
                connection.execute("INSERT INTO price_snapshot (appid, observed_at, kind, currency, initial_cents, "
                                   "final_cents, discount_percent) VALUES (?, '2026-10-20T10:00:00+00:00', 'priced', "
                                   "'EUR', 2999, 2999, 0)", (WISHED,))
                connection.execute("INSERT INTO price_target (appid, cents, currency, set_at) "
                                   "VALUES (?, 2000, 'EUR', '2026-10-21T10:00:00+00:00')", (WISHED,))
        finally:
            connection.close()
    handoff = target / "cache" / rules.PRICE_HANDOFF_FILE
    handoff.parent.mkdir(parents=True, exist_ok=True)
    row = {"appid": WISHED, "observed_at": observed, "kind": "priced", "currency": "EUR", "initial_cents": 2999,
           "final_cents": 1999, "discount_percent": 33}
    if again:  # the very price that already landed: its moment read back from the library
        row["observed_at"] = observed = read_db(target / rules.LIBRARY_DB_FILE, "SELECT MAX(observed_at) FROM "
                                                f"price_snapshot WHERE appid = {WISHED}")[0][0]
    handoff.write_text(json.dumps({"observations": [row]}, indent=1), encoding="utf-8")
    return observed


def _writable_and_again(func, path, _exc) -> None:
    os.chmod(path, stat.S_IWRITE)
    func(path)


real_folders = [Path(os.path.expanduser("~")) / "Desktop",
                Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs"]
real = {str(f / n): sha(f / n) for f in real_folders for n in NAMES if (f / n).is_file()}
print(f"the user's real shortcuts: {len(real)} found")
real_run = run_value(rules.STARTUP_RUN_KEY)
print(f"the user's real Run value: {'set' if real_run else 'not set'}")
if registered():
    raise SystemExit("An installed copy is registered here; not touching it.")
if not SETUP.is_file():
    raise SystemExit(f"No installer at {SETUP}: build it first (packaging\\build.py).")

fake = Path(tempfile.mkdtemp(prefix="installer_test_"))
profile = fake / "profile"
env = fake_env(profile)
target = Path(env["LOCALAPPDATA"]) / "Programs" / version.APP_NAME
fake_folders = [profile / "Desktop", Path(env["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs"]
made = [f / n for f in fake_folders for n in NAMES]

try:
    print("\n=== 1. the build is this code's ===")
    newest_source = max(p.stat().st_mtime for folder in ("presentation", "adapters", "logic", "providers", "web",
                                                         "data_access", "shared") for p in (PROJECT / folder).rglob("*.py"))
    check(f"the installer is built ({SETUP.stat().st_size / 1e6:.0f} MB) after the newest source file",
          SETUP.stat().st_mtime >= newest_source)
    check(f"stamped {version.APP_VERSION}, with the day it was built",
          (BUILT / version.VERSION_FILE).read_text(encoding="utf-8").strip() == version.APP_VERSION
          and (BUILT / version.BUILD_FILE).is_file(), (BUILT / version.VERSION_FILE).read_text(encoding="utf-8"))
    sql = ["data_access/schema.sql"] + [f"data_access/upgrades/{p.name}" for p in
                                        sorted((PROJECT / "data_access" / "upgrades").glob("*.sql"))]
    check(f"the schema and its {len(sql) - 1} upgrade scripts, byte for byte",
          all(sha(BUILT / s) == sha(PROJECT / s) for s in sql), sql)
    fonts = sorted(p.name for p in (PROJECT / "presentation" / "fonts").iterdir() if p.is_file())
    check(f"all {len(fonts)} font files and licences, byte for byte",
          all(sha(BUILT / "presentation" / "fonts" / n) == sha(PROJECT / "presentation" / "fonts" / n) for n in fonts))
    notes = PROJECT.joinpath(*rules.RELEASE_NOTES_DIR) / f"{version.APP_VERSION}.md"
    check(f"this version's release notes, {notes.name}, byte for byte: What's new reads them (Phase 106)",
          notes.is_file() and sha(BUILT.joinpath(*rules.RELEASE_NOTES_DIR) / notes.name) == sha(notes))
    # The icon (the user's own since Phase 100): the file the window, the tray and the shortcuts read, and the
    # largest picture in it inside GameLauncher.exe's and Setup.exe's own icons -- an icon resource keeps an
    # .ico's PNG bytes as they are, where payload.zip's copies are compressed.
    largest = icon_images(PROJECT / "launcher.ico")[-1]
    check("the icon, byte for byte, and in the program's and the installer's own icons",
          sha(BUILT / "launcher.ico") == sha(PROJECT / "launcher.ico")
          and largest in (BUILT.parent / "GameLauncher.exe").read_bytes() and largest in SETUP.read_bytes())

    print("\n=== 2. a first install, in the fake profile ===")
    done = subprocess.run([str(SETUP), "--silent"], env=env, capture_output=True, text=True, timeout=600)
    check("installed", done.returncode == 0 and (target / "GameLauncher.exe").is_file(), done.stderr[-500:])
    check("its four shortcuts in the fake profile", all(p.is_file() for p in made),
          [str(p) for p in made if not p.is_file()])
    entry = registered()
    check(f"an Add/Remove Programs entry, version {version.APP_VERSION}",
          entry == {"DisplayName": version.APP_NAME, "DisplayVersion": version.APP_VERSION}, entry)
    check("no config.json yet: the next start is a first run", not (target / "config.json").exists())
    program_after_first = {k: v for k, v in tree(target).items() if k.startswith("_internal/") or k == "GameLauncher.exe"}

    print("\n=== 3. the first start, as a friend's PC sees it ===")
    seed_cache(target)
    app = subprocess.Popen([str(target / "GameLauncher.exe")], env=env, cwd=str(target))
    # Qt adds the application's name to a dialog's title: "Where do you keep your games? - Game Launcher".
    asked = wait_for(lambda: next((h for h, t in windows_of(app.pid).items() if t.startswith(QUESTION)), None), 60)
    check("the question comes up before anything is scanned", bool(asked)
          and "scan finished" not in log_text(target), windows_of(app.pid))
    if asked:
        win32gui.PostMessage(asked, win32con.WM_CLOSE, 0, 0)  # closed, as someone who only uses stores
    wait_for(lambda: (target / "config.json").is_file(), 20)
    # The second question (Phase 79): a SteamGridDB key. Closed too -- skipped, nothing written.
    key_asked = wait_for(lambda: next((h for h, t in windows_of(app.pid).items() if t.startswith(KEY_QUESTION)),
                                      None), 30)
    check("then the second question, a SteamGridDB key", bool(key_asked), windows_of(app.pid))
    if key_asked:
        win32gui.PostMessage(key_asked, win32con.WM_CLOSE, 0, 0)
    wait_for(lambda: "first run: no SteamGridDB key" in log_text(target), 20)
    config = (target / "config.json").read_text(encoding="utf-8") if (target / "config.json").is_file() else ""
    saved = json.loads(config) if config else None
    # The answer carries the version that ran (Phase 99): a first run's start writes nothing else.
    check("both closed: config.json written, no folders, no key -- and Xbox as this PC's drives say",
          saved == {"roots": [], "enable_xbox": first_run.xbox_found(), rules.VERSION_SEEN_KEY: version.APP_VERSION},
          saved)
    finished = wait_for(lambda: "scan finished" in log_text(target), 90)
    time.sleep(3)  # the landing after the scan, on the window's thread
    log = log_text(target)
    check("then it scans the stores", bool(finished), log[-400:])
    check(f"its log starts with {version.APP_NAME} {version.APP_VERSION}, built, an installed copy",
          f"{version.APP_NAME} {version.APP_VERSION}, built " in log and "installed copy" in log, log[:300])
    check("and says it was a first run, and what was answered",
          "first run: no config.json yet" in log and "first run answered: no folders -- stores only" in log)
    check("a library database of its own", (target / "library.db").is_file())
    # 1.2.6 is the first copy handed out that looks at the process list (Phase 93): frozen, it still reads it.
    check("it watches for games started outside it: the process list read, as an installed copy",
          "process watch: a look every" in log and "refuse to be asked their path" in log,
          [line for line in log.splitlines() if "process watch" in line][:3])
    check("nothing went wrong", "Traceback" not in log and " ERROR " not in log,
          [line for line in log.splitlines() if "ERROR" in line or "Traceback" in line][:3])
    check("a first run's start never asks the tray question (Phase 99)",
          not any(t.startswith(OFFER) for t in windows_of(app.pid).values()), windows_of(app.pid))
    fetched = [line for line in log.splitlines() if "steam web: appid" in line]
    print(f"   (store requests this start made: {len(fetched)})")
    # The update check (Phase 79): an installed copy asks GitHub, a few seconds after it appears.
    kept = target / "cache" / rules.UPDATE_CACHE_FILE
    wait_for(lambda: kept.is_file(), 30)
    answer = json.loads(kept.read_text(encoding="utf-8")) if kept.is_file() else {}
    log = log_text(target)
    # Its notes as their length (Phase 107): a release's body is Romanian and English, and its text is not the point.
    print(f"   (GitHub's answer: { {**answer, 'notes': f'{len(answer.get('notes') or '')} characters'} })")
    check("it asked GitHub once whether a newer version is out, and kept the answer",
          answer.get("reached") is True and log.count("update check:") >= 1
          and "update check: not asked" not in log, [l for l in log.splitlines() if "update check" in l])
    check(f"nothing newer than {version.APP_VERSION} is offered", not answer.get("latest")
          or not version.is_newer(answer["latest"]), answer)
    check("closed by its window, as a person closes it", close_app(app))

    print("\n=== 4. a second install over the first: the data kept, the program replaced ===")
    (target / "backups" / "planted").mkdir(parents=True, exist_ok=True)
    (target / "backups" / "planted" / "a snapshot.txt").write_text("phase 78", encoding="utf-8")
    (target / "save_backups").mkdir(exist_ok=True)
    (target / "save_backups" / "a copy.zip").write_bytes(b"phase 78: a save copy")
    for n in (1, 2):
        (target / f"{rules.LOG_FILENAME}.{n}").write_text(f"an older log {n}\n", encoding="utf-8")
    (target / "_internal" / "left by an old build.txt").write_text("x", encoding="utf-8")
    (target / "left by an old build.txt").write_text("x", encoding="utf-8")
    data_before = {n: sha(target / n) for n in DATA_NAMES + (f"{rules.LOG_FILENAME}.1", f"{rules.LOG_FILENAME}.2")}
    folders_before = {name: tree(target / name) for name in ("cache", "backups", "save_backups")}
    # Start with Windows turned on in the installed copy: its value, as logic/autostart writes it.
    planted = f'"{target / "GameLauncher.exe"}" {rules.BACKGROUND_ARGUMENT}'
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, STARTUP_ROOT + "\\Run", 0, winreg.KEY_SET_VALUE) as handle:
        winreg.SetValueEx(handle, rules.STARTUP_VALUE_NAME, 0, winreg.REG_SZ, planted)
    done = subprocess.run([str(SETUP), "--silent"], env=env, capture_output=True, text=True, timeout=600)
    check("updated", done.returncode == 0 and "updated to" in done.stdout, (done.stdout, done.stderr[-300:]))
    check("the database, the settings and the log -- with its two older copies -- byte for byte",
          all((target / n).is_file() and sha(target / n) == h for n, h in data_before.items()),
          [n for n, h in data_before.items() if not (target / n).is_file() or sha(target / n) != h])
    check(f"the cache, the backups and the save copies, every file ({sum(len(t) for t in folders_before.values())})",
          all(tree(target / name) == t for name, t in folders_before.items()))
    check("what an old build left is gone, inside the program and beside it",
          not (target / "_internal" / "left by an old build.txt").exists()
          and not (target / "left by an old build.txt").exists())
    program_after_second = {k: v for k, v in tree(target).items() if k.startswith("_internal/") or k == "GameLauncher.exe"}
    check(f"the program exactly as the first install left it ({len(program_after_second)} files): an idempotent upgrade",
          program_after_second == program_after_first,
          sorted(set(program_after_first) ^ set(program_after_second))[:5])
    check("the Add/Remove entry still says the version", (registered() or {}).get("DisplayVersion") == version.APP_VERSION)
    check("Start with Windows: the update keeps its Run value as it was (Phase 92)",
          run_value(STARTUP_ROOT + "\\Run") == planted, run_value(STARTUP_ROOT + "\\Run"))

    print("\n=== 5. the updated copy starts, and does not ask again ===")
    before_lines = len(log_text(target).splitlines())
    app = subprocess.Popen([str(target / "GameLauncher.exe")], env=env, cwd=str(target))
    main_window = wait_for(lambda: next((h for h, t in windows_of(app.pid).items() if t == version.APP_NAME), None), 60)
    check("its window, and neither first-run question", bool(main_window)
          and not any(t.startswith((QUESTION, KEY_QUESTION)) for t in windows_of(app.pid).values()),
          windows_of(app.pid))
    answer_offer(app, target)  # the one question: this is the start after a first run's (Phase 99)
    shows_whats_new(app, target)
    time.sleep(9)  # past the update check's moment (rules.UPDATE_CHECK_DELAY_MS)
    new_lines = "\n".join(log_text(target).splitlines()[before_lines:])
    check("its log: a start, no first run", "starting" in new_lines and "first run" not in new_lines, new_lines[:300])
    check("GitHub not asked again the same day", "update check: asked" in new_lines and "not again yet" in new_lines,
          [l for l in new_lines.splitlines() if "update check" in l])
    check("closed by its window", close_app(app))

    print("\n=== 6. a quiet uninstall keeps the data ===")
    db_before = sha(target / "library.db")
    done = subprocess.run([str(target / "GameLauncher.exe"), "--uninstall", "--quiet"], env=env,
                          capture_output=True, text=True, timeout=120)
    wait_for(lambda: not (target / "_internal").exists(), 30)
    check("uninstalled", done.returncode == 0, done.stderr[-500:])
    check("the program is gone", not (target / "GameLauncher.exe").exists() and not (target / "_internal").exists())
    check("the data stays: the database, the settings, the log, the backups",
          sha(target / "library.db") == db_before and (target / "config.json").is_file()
          and (target / rules.LOG_FILENAME).is_file() and (target / "backups" / "planted" / "a snapshot.txt").is_file())
    check("its shortcuts are gone from the fake profile", not any(p.exists() for p in made))
    check("the Add/Remove Programs entry is gone", registered() is None)
    check("Start with Windows: the uninstall removed its Run value -- no missing exe started at sign-in",
          run_value(STARTUP_ROOT + "\\Run") is None, run_value(STARTUP_ROOT + "\\Run"))

    print("\n=== 8. a friend's copy of the version before, updated to this one (--over) ===")
    if OVER is None:
        print("   (not run: --over names the installer the friends have)")
    else:
        over_env = fake_env(fake / "over")
        old_target = Path(over_env["LOCALAPPDATA"]) / "Programs" / version.APP_NAME
        done = subprocess.run([str(OVER), "--silent"], env=over_env, capture_output=True, text=True, timeout=600)
        stamp = old_target / "_internal" / version.VERSION_FILE
        old_version = stamp.read_text(encoding="utf-8").strip() if stamp.is_file() else ""
        check(f"the version before installed ({old_version}), older than {version.APP_VERSION}",
              done.returncode == 0 and version.is_newer(version.APP_VERSION, old_version)
              and (registered() or {}).get("DisplayVersion") == old_version, (old_version, done.stderr[-300:]))
        seed_cache(old_target)
        app = first_start(old_target, over_env)
        old_log = log_text(old_target)
        check(f"it started as a friend's PC starts it: {version.APP_NAME} {old_version}, the two questions, a scan",
              f"{version.APP_NAME} {old_version}, built " in old_log and "first run answered" in old_log
              and "scan finished" in old_log, old_log[-300:])
        check("closed by its window", close_app(app))
        database = old_target / "library.db"
        old_schema = read_db(database, "PRAGMA user_version")[0][0] if database.is_file() else None
        # The columns the version before had: an upgrade may add some (version 8 two, Phase 104), never change one.
        old_columns = [row[1] for row in read_db(database, "PRAGMA table_info(game)")] if database.is_file() else []
        games_sql = f"SELECT {', '.join(old_columns)} FROM game"
        games_before = sorted(read_db(database, games_sql)) if database.is_file() else None
        settings_before = json.loads((old_target / "config.json").read_text(encoding="utf-8"))
        print(f"   (its library: schema version {old_schema}, {len(games_before or [])} game rows)")

        before_lines = len(log_text(old_target).splitlines())
        done = subprocess.run([str(SETUP), "--silent"], env=over_env, capture_output=True, text=True, timeout=600)
        check(f"this installer over it: updated, Add/Remove says {version.APP_VERSION}",
              done.returncode == 0 and "updated to" in done.stdout
              and (registered() or {}).get("DisplayVersion") == version.APP_VERSION, (done.stdout, done.stderr[-300:]))
        app = subprocess.Popen([str(old_target / "GameLauncher.exe")], env=over_env, cwd=str(old_target))
        main_window = wait_for(lambda: next((h for h, t in windows_of(app.pid).items() if t == version.APP_NAME),
                                            None), 60)
        upgraded = wait_for(lambda: f"the library database is at version {SCHEMA} now" in log_text(old_target), 30)
        time.sleep(3)
        new_lines = "\n".join(log_text(old_target).splitlines()[before_lines:])
        check(f"it starts as {version.APP_VERSION}: its window, no question, no first run", bool(main_window)
              and f"{version.APP_NAME} {version.APP_VERSION}, built " in new_lines and "first run" not in new_lines
              and not any(t.startswith((QUESTION, KEY_QUESTION)) for t in windows_of(app.pid).values()),
              new_lines[:300])
        # A friend who updates meets What's new first (Phase 107), then the one question, and the new places.
        meets_whats_new(app, old_target, old_version)
        answer_offer(app, old_target)
        shows_whats_new(app, old_target)
        new_lines = "\n".join(log_text(old_target).splitlines()[before_lines:])
        if old_schema is not None and old_schema < SCHEMA:
            noted = re.search(rf"the library database is at version {SCHEMA} now \(snapshot (\S+) first\)", new_lines)
            held = old_target / "backups" / noted.group(1) / rules.LIBRARY_DB_FILE if noted else None
            check(f"its library brought from schema version {old_schema} to {SCHEMA}", bool(upgraded)
                  and read_db(database, "PRAGMA user_version")[0][0] == SCHEMA,
                  [line for line in new_lines.splitlines() if "library database" in line])
            check(f"a snapshot first, holding the library at version {old_schema}",
                  held is not None and held.is_file() and read_db(held, "PRAGMA user_version")[0][0] == old_schema,
                  noted.group(0) if noted else "no snapshot named")
        else:
            print(f"   (the same schema version, {SCHEMA}: nothing to upgrade)")
        views = [name for (name,) in read_db(database, "SELECT name FROM sqlite_master WHERE type = 'view'")]
        broken = views_answer(database)
        check(f"every view of this version answers on it ({len(views)}, v_hours among them)",
              not broken and "v_hours" in views, broken)
        games_after = sorted(read_db(database, games_sql))
        check("the library's games row for row as the version before left them", games_after == games_before,
              [row for row in games_after if row not in (games_before or [])][:2])
        # Every setting as it was, but the version a start last ran as (Phase 99): 1.2.8's first run wrote it.
        settings_after = json.loads((old_target / "config.json").read_text(encoding="utf-8"))
        moved = {k for k in settings_before if settings_after.get(k) != settings_before[k]}
        check("and its settings, but the version it last ran as, which says this one now",
              moved <= {rules.VERSION_SEEN_KEY} and settings_after.get(rules.VERSION_SEEN_KEY, version.APP_VERSION)
              == version.APP_VERSION, sorted(moved))
        added = [row[1] for row in read_db(database, "PRAGMA table_info(game)") if row[1] not in old_columns]
        if added:
            filled = " OR ".join(f"{name} IS NOT NULL" for name in added)
            check(f"the game columns this version adds ({', '.join(added)}) empty in every row: the upgrade made "
                  "nothing up", read_db(database, f"SELECT COUNT(*) FROM game WHERE {filled}")[0][0] == 0, added)
        check("nothing went wrong", "Traceback" not in new_lines and " ERROR " not in new_lines,
              [line for line in new_lines.splitlines() if "ERROR" in line or "Traceback" in line][:3])
        check("closed by its window", close_app(app))

        # A price alert, as a friend meets one (Phase 104): planted, landed at the next start's scan, once.
        observed = plant_alert(old_target)
        before_lines = len(log_text(old_target).splitlines())
        app = subprocess.Popen([str(old_target / "GameLauncher.exe")], env=over_env, cwd=str(old_target))
        said = wait_for(lambda: "price alerts: 1 set off" in "\n".join(
            log_text(old_target).splitlines()[before_lines:]), 120)
        time.sleep(2)
        lines = "\n".join(log_text(old_target).splitlines()[before_lines:])
        sent = read_db(database, f"SELECT appid, observed_at, kind, final_cents FROM price_alert WHERE appid = {WISHED}")
        check("a planted target alerts: the new price under it set off one alert, written to the log first",
              bool(said) and sent == [(WISHED, observed, "target", 1999)] and "1 written to the log" in lines,
              (sent, [line for line in lines.splitlines() if "price" in line][:4]))
        check("and said in words: under your 20,00 € target",
              "under your 20,00\u00a0\u20ac target" in lines or "under your 20,00 \u20ac target" in lines,
              [line for line in lines.splitlines() if "price alerts:" in line][:2])
        check("closed by its window", close_app(app))
        plant_alert(old_target, again=True)
        before_lines = len(log_text(old_target).splitlines())
        app = subprocess.Popen([str(old_target / "GameLauncher.exe")], env=over_env, cwd=str(old_target))
        landed = wait_for(lambda: "observation(s) landed in the library" in "\n".join(
            log_text(old_target).splitlines()[before_lines:]), 120)
        time.sleep(2)
        lines = "\n".join(log_text(old_target).splitlines()[before_lines:])
        check("the same price planted again: it sets nothing off -- an alert once a drop",
              bool(landed) and "price alerts: 1 set off" not in lines and read_db(
                  database, f"SELECT COUNT(*) FROM price_alert WHERE appid = {WISHED}")[0][0] == 1,
              [line for line in lines.splitlines() if "price" in line][:4])
        check("nothing went wrong", "Traceback" not in lines and " ERROR " not in lines,
              [line for line in lines.splitlines() if "ERROR" in line or "Traceback" in line][:3])
        check("closed by its window", close_app(app))
        done = subprocess.run([str(old_target / "GameLauncher.exe"), "--uninstall", "--quiet"], env=over_env,
                              capture_output=True, text=True, timeout=120)
        wait_for(lambda: not (old_target / "_internal").exists(), 30)
        check("uninstalled, its Add/Remove entry gone", done.returncode == 0 and registered() is None)
finally:
    # A run stopped half way must not leave anything behind: a copy it started, or its own
    # Add/Remove entry -- removed only when it points inside this run's fake profile.
    running = globals().get("app")
    if running is not None and running.poll() is None:
        running.terminate()
        running.wait(timeout=30)
    print("\n=== 7. the user's own shortcuts were never touched ===")
    after = {str(f / n): sha(f / n) for f in real_folders for n in NAMES if (f / n).is_file()}
    check(f"all {len(real)} byte for byte as they were", after == real and len(real) == 4, (len(real), len(after)))
    check("and the user's own Run value as it was", run_value(rules.STARTUP_RUN_KEY) == real_run)
    delete_test_keys(STARTUP_ROOT)
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_ROOT.rsplit(chr(92), 1)[0]) as handle:
            empty = winreg.QueryInfoKey(handle)[:2] == (0, 0)
    except FileNotFoundError:
        # A run stopped before any test key was made has no root to tidy (found in Phase 107, after a stop).
        print("   (no test Run key root to tidy)")
        empty = False
    if empty:  # the test root too, when no suite's key is under it
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, STARTUP_ROOT.rsplit(chr(92), 1)[0])
    if registered():
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY) as key:
            where = winreg.QueryValueEx(key, "InstallLocation")[0]
        if where.startswith(str(fake)):
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, KEY)
            print("   (this run's Add/Remove entry, left by a stop half way, removed)")
    shutil.rmtree(fake, onexc=_writable_and_again)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
