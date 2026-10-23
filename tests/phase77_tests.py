"""Phase 77: the first run -- where the games are -- and what a friend's PC needs that this one never did.

The folder finder on made-up drives (game words matched, store libraries, Windows' folders,
hidden folders, links and Steam libraries left out, fixed drives only, a whole drive warned
against); the question, asked exactly when there is no config.json -- never with one, never in a
sandboxed suite -- closed (no folders, written, never asked again), answered (the ticked folders
and Xbox written, the first scan using them), and worked by the pad at TV size; the Game
folders row in Settings, which writes only its keys, re-arms the folder watch and scans, and
deletes nothing; the empty library's three messages and its button; one version in build.py,
the stamped file, the installer's reading and the running app; and the diagnostics bundle, the
key and the Steam accounts out of it, the paths in it, nothing of the play history.

On a throwaway copy of the data. Nothing is fetched.
"""
import _winapi
import ast
import ctypes
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from datetime import date
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import test_sandbox

box = test_sandbox.start()
SANDBOX = box.folder

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
from PySide6.QtWidgets import QApplication

app = QApplication([])

from adapters import controller
from data_access import config_io
from shared import paths, rules

try:
    from logic import first_run
    from presentation import ui_first_run, ui_folders, ui_offer
    from shared import drives, version
except ImportError:  # the code before this phase has none of them; the sections that need them say so
    first_run = ui_first_run = ui_folders = ui_offer = drives = version = None
from presentation import ui_settings, ui_window

CONFIG = SANDBOX / "config.json"
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


def modal():
    return QApplication.activeModalWidget()


def run(steps, notes: dict, limit_ms: int = 60_000) -> None:
    """Each step after the last, a step tried again until it says it is done; a watchdog closes
    whatever is still open if the chain gets stuck (a dialog runs its own loop inside it)."""
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


def hide(path: Path) -> None:
    ctypes.windll.kernel32.SetFileAttributesW(str(path), 0x2)  # FILE_ATTRIBUTE_HIDDEN


def make_drives() -> dict[str, Path]:
    """Three made-up drives: one with every kind of folder, one empty, one with Xbox's."""
    base = SANDBOX / "drives"
    a, b, c = base / "A", base / "B", base / "C"
    for name in ("Games", "PC Games", "Jocuri", "Games2", "My Stuff", "SteamLibrary", "Epic Games",
                 "GOG Games", "XboxGames", "Riot Games", "Program Files", "Windows", "Users",
                 "Steam Games", "Hidden Games", "gaming"):
        (a / name).mkdir(parents=True)
    (a / "Steam Games" / "steamapps").mkdir()  # a Steam library, whatever it is called
    hide(a / "Hidden Games")
    _winapi.CreateJunction(str(a / "Games"), str(a / "Games Link"))  # a link to elsewhere
    (a / "games.txt").write_text("a file, not a folder", encoding="utf-8")
    b.mkdir(parents=True)
    (c / "XboxGames").mkdir(parents=True)
    return {"A": a, "B": b, "C": c}


print("=== 1. the folder finder, on made-up drives ===")
fake = {}
try:
    fake = make_drives()
    found = first_run.candidates([str(fake["A"]), str(fake["B"])])
    expected = [str(fake["A"] / n) for n in ("Games", "Games2", "gaming", "Jocuri", "PC Games")]
    check("game words matched, in any case and beside other words or digits; nothing else",
          found == expected, found)
    check("store libraries left out by name: SteamLibrary, Epic Games, GOG Games, XboxGames, Riot Games",
          not any(n in " ".join(found) for n in ("SteamLibrary", "Epic Games", "GOG Games", "XboxGames", "Riot")))
    check("a folder holding steamapps is a Steam library whatever its name", str(fake["A"] / "Steam Games") not in found)
    names = [Path(f).name for f in found]
    check("Windows' own folders, a hidden folder, a link and a file left out",
          not any(n in names for n in ("Program Files", "Windows", "Users", "Hidden Games", "Games Link", "games.txt")),
          names)
    check("an empty drive offers nothing", first_run.candidates([str(fake["B"])]) == [])
    check("Xbox: found only where a drive has an XboxGames folder",
          first_run.xbox_found([str(fake["C"])]) and not first_run.xbox_found([str(fake["B"])]))
    real_all, real_type = drives.all_drives, drives.drive_type
    kinds = {}
    drives.all_drives = lambda: list(kinds)
    drives.drive_type = lambda root: kinds[root]
    try:
        kinds.update({str(fake["A"]): drives.DRIVE_FIXED, str(fake["B"]): 2, str(fake["C"]): 4})
        check("a fixed drive is looked at", drives.fixed_drives() == [str(fake["A"])]
              and first_run.candidates() == expected)
        # A, full of games and with an XboxGames folder, as a USB stick; C, with Xbox's, a share.
        kinds.update({str(fake["A"]): 2, str(fake["B"]): drives.DRIVE_FIXED, str(fake["C"]): 4})
        check("a removable drive and a network one are not looked at, for folders or for Xbox",
              drives.fixed_drives() == [str(fake["B"])] and first_run.candidates() == []
              and not first_run.xbox_found())
    finally:
        drives.all_drives, drives.drive_type = real_all, real_type
    check("Windows says what a drive is: C: fixed here", drives.drive_type("C:\\") == drives.DRIVE_FIXED)
    check("a whole drive is told apart from a folder on it",
          all(first_run.is_drive_root(p) for p in ("D:\\", "D:", "C:/"))
          and not any(first_run.is_drive_root(p) for p in (r"D:\Games", r"C:\games\x")))
    check("the folders there and the ones not there", first_run.reachable([str(fake["A"]), r"Z:\gone"])
          == ([str(fake["A"])], [r"Z:\gone"]))
except Exception as exc:
    unreached("1", exc)

print("\n=== 2. the folder list: add, remove, tick; a whole drive refused (Phase 82) ===")
try:
    editor = ui_folders.FolderList([str(fake["A"] / "Games")], checkable=True, scale=1.0)
    # Since Phase 82 a whole drive is refused and the drive's game folders offered instead; the
    # real D:'s are this PC's, so the finder is stood in for (suite 82 checks what it offers).
    real_instead = first_run.instead_of
    first_run.instead_of = lambda folder: []
    try:
        editor.choose_folder = lambda: "D:\\"
        editor.add_button.click()
    finally:
        first_run.instead_of = real_instead
    check("a whole drive is not added, and the list says why",
          "D:\\" not in editor.all_folders() and editor.warning.isVisibleTo(editor)
          and "D:\\ is a whole drive, not a game folder" in editor.warning.text(), editor.warning.text())
    editor.add_folder(str(fake["A"] / "games"))
    check("a folder already there is not added twice (any case)", len(editor.all_folders()) == 1)
    editor.add_folder(str(fake["B"] / "Jocuri"))
    editor.list.item(1).setCheckState(Qt.CheckState.Unchecked)
    check("an unticked folder is not chosen",
          editor.folders() == [str(fake["A"] / "Games")])
    editor.list.setCurrentRow(0)
    editor.remove_button.click()
    check("Remove takes the current one out of the list -- and nothing off the disk",
          editor.all_folders() == [str(fake["B"] / "Jocuri")] and (fake["A"] / "Games").is_dir())
    plain = ui_folders.FolderList([r"C:\games", r"C:\voices38"], checkable=False, scale=1.0)
    check("without ticks, every folder listed is chosen", plain.folders() == [r"C:\games", r"C:\voices38"])
except Exception as exc:
    unreached("2", exc)

print("\n=== 3. with a config.json -- this machine, every sandboxed suite -- nobody is asked ===")
try:
    check("the sandbox writes the copy's config.json before any suite runs", CONFIG.is_file())
    window = ui_window.MainWindow()
    window.resize(1280, 820)
    window.show()
    settle(1.5)
    check("no first run, no question", window.first_run is False and modal() is None)
    check("the roots are the ones config.json names", window.config.get("roots") == json.loads(
        CONFIG.read_text(encoding="utf-8")).get("roots", list(rules.DEFAULT_ROOTS)))
    window.close()
    settle(0.3)
    window.overrides.close()
except Exception as exc:
    unreached("3", exc)


def without_version(written):
    """A first run's config.json less the version that ran, which its answer carries since Phase 99."""
    if not isinstance(written, dict):
        return written
    return {k: v for k, v in written.items() if k != "version_seen"}


def fresh_install() -> None:
    """The copy as a fresh install leaves it: no config.json (the library is kept: harmless)."""
    CONFIG.unlink(missing_ok=True)


def with_found(folders, xbox):
    first_run.candidates = lambda roots=None: list(folders)
    first_run.xbox_found = lambda roots=None: xbox


real_candidates, real_xbox = (first_run.candidates, first_run.xbox_found) if first_run else (None, None)

print("\n=== 4. a fresh install: the question, closed ===")
try:
    fresh_install()
    with_found([str(fake["A"] / "Games")], True)
    window = ui_window.MainWindow()
    check("no config.json: a first run", window.first_run is True)
    check("no scan before the answer -- not even the no-catalog one", window.worker is None)
    notes: dict = {}
    window.resize(1280, 820)
    run([lambda: notes.update(shown=True) or window.show() or True,
         lambda: isinstance(modal(), ui_first_run.FirstRunDialog),
         lambda: notes.update(offered=modal().folders.all_folders(), xbox=modal().xbox.isChecked(),
                              scanning=window.worker is not None) or True,
         lambda: modal().reject() or True,
         # Since Phase 79 a second question follows, a SteamGridDB key: skipped here.
         lambda: isinstance(modal(), ui_first_run.KeyDialog) and (modal().reject() or True),
         lambda: notes.update(closed=modal() is None) or True], notes)
    check("on screen, the question comes over the window", notes.get("closed") is True)
    check("it offers what the finder found, ticked, and Xbox on when a folder was found",
          notes.get("offered") == [str(fake["A"] / "Games")] and notes.get("xbox") is True, notes)
    check("still no scan while it is open", notes.get("scanning") is False)
    saved = json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.is_file() else None
    # Since Phase 99 the answer also carries the version that ran (version_seen).
    check("closed: config.json written with no folders -- explicitly, not the defaults -- and Xbox as shown",
          saved is not None and saved.pop("version_seen", None) == version.APP_VERSION
          and saved == {"roots": [], "enable_xbox": True}, saved)
    check("then the first scan runs, on no folders", window._scan_trigger == "first_run"
          and window.worker is not None and window.worker.config.get("roots") == [])
    while window.worker is not None and window.worker.isRunning():
        settle(0.2)
    settle(0.3)
    window.close()
    settle(0.3)
    window.overrides.close()
    again = ui_window.MainWindow()
    # Since Phase 99 the next start asks one thing, once: whether to keep running in the tray. It comes a
    # second after the window appears, inside the wait below -- noted and answered Not now from a timer.
    seen_then: list = []

    def answer_offer():
        seen_then.append(modal())
        if modal() is not None:
            modal().reject()

    QTimer.singleShot(1300, answer_offer)
    again.show()
    settle(1.5)
    check("the next start asks no more first-run questions, though the list of folders is empty -- only the tray "
          "offer, once", again.first_run is False and len(seen_then) == 1 and ui_offer is not None
          and isinstance(seen_then[0], ui_offer.TrayOfferDialog) and modal() is None, seen_then)
    again.close()
    settle(0.3)
    again.overrides.close()
except Exception as exc:
    unreached("4", exc)

print("\n=== 5. a fresh install: the question, answered ===")
try:
    fresh_install()
    with_found([str(fake["A"] / "Games"), str(fake["A"] / "Jocuri")], False)
    window = ui_window.MainWindow()
    window.resize(1280, 820)
    notes = {}
    added = SANDBOX / "drives" / "E" / "My own games"
    added.mkdir(parents=True)

    def answer():
        dialog = modal()
        if not isinstance(dialog, ui_first_run.FirstRunDialog):
            return False
        dialog.folders.list.item(1).setCheckState(Qt.CheckState.Unchecked)  # not Jocuri
        dialog.folders.choose_folder = lambda: str(added)
        dialog.folders.add_button.click()
        dialog.xbox.setChecked(True)
        dialog.continue_button.click()
        return True

    run([lambda: window.show() or True, answer,
         lambda: isinstance(modal(), ui_first_run.KeyDialog) and (modal().reject() or True),  # Phase 79
         lambda: notes.update(closed=modal() is None) or True], notes)
    saved = json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.is_file() else None
    check("Continue writes the ticked folders, the one added, and Xbox",
          without_version(saved) == {"roots": [str(fake["A"] / "Games"), str(added)], "enable_xbox": True}, saved)
    check("and the first scan uses them", window.worker is not None
          and window.worker.config.get("roots") == saved["roots"] and window.worker.config.get("enable_xbox") is True)
    check("the folder watch follows them", sorted(window.watcher._roots.values()) == sorted(
        os.path.normpath(r) for r in saved["roots"]), window.watcher._roots)
    while window.worker is not None and window.worker.isRunning():
        settle(0.2)
    settle(1.6)  # past the startup scan's moment: it stands down for the question's own
    check("the quiet startup scan stood down for it", any("first-run question's own scan" in line for line in lines))
    window.close()
    settle(0.3)
    window.overrides.close()
except Exception as exc:
    unreached("5", exc)

print("\n=== 6. a fresh install on a couch: the question at TV size, worked by the pad ===")
try:
    fresh_install()
    with_found([str(fake["A"] / "Games"), str(fake["A"] / "Jocuri")], False)
    window = ui_window.MainWindow()
    window.set_tv_mode(True)
    notes = {}

    def press(name):
        window.pads.action.emit(name)

    def until(predicate, name, tries=20):
        left = [tries]

        def step():
            if predicate() or left[0] <= 0:
                return True
            left[0] -= 1
            press(name)
            return False
        return step

    def ticked():
        return [item.checkState() == Qt.CheckState.Checked
                for item in (modal().folders.list.item(r) for r in range(modal().folders.list.count()))]

    run([
        lambda: isinstance(modal(), ui_first_run.FirstRunDialog),
        lambda: notes.update(scale=modal().scale, on_list=modal().focusWidget() is modal().folders.list,
                             row=modal().folders.list.currentRow()) or True,
        lambda: press(controller.DOWN) or True,  # to Jocuri
        lambda: press(controller.ACTIVATE) or True,  # A: untick it
        lambda: notes.update(after_a=ticked(), still=isinstance(modal(), ui_first_run.FirstRunDialog)) or True,
        lambda: press(controller.DOWN) or True,  # past the end: on to the next control
        lambda: notes.update(left_list=modal().focusWidget() is not modal().folders.list) or True,
        until(lambda: modal().focusWidget() is modal().continue_button, controller.DOWN),
        lambda: press(controller.ACTIVATE) or True,  # A on Continue
        lambda: isinstance(modal(), ui_first_run.KeyDialog),  # Phase 79: the key question next
        lambda: press(controller.BACK) or True,  # B: skipped
        lambda: notes.update(closed=modal() is None) or True,
    ], notes)
    saved = json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.is_file() else None
    check("in TV mode the question is at TV size", notes.get("scale") == float(ui_settings.ui_rules.TV_SCALE_DEFAULT),
          notes.get("scale"))
    check("the pad starts on the folders, on the first one", notes.get("on_list") and notes.get("row") == 0, notes)
    check("down, then A: the second folder unticked -- and the dialog still open (A did not press Continue)",
          notes.get("after_a") == [True, False] and notes.get("still"), notes.get("after_a"))
    check("down past the last folder goes on to the next control: the list is no trap", notes.get("left_list"))
    check("down to Continue and A: closed, the one still ticked written",
          notes.get("closed") and without_version(saved) == {"roots": [str(fake["A"] / "Games")], "enable_xbox": False},
          saved)
    check("no watchdog and no error", not notes.get("watchdog") and not notes.get("errors"), notes.get("errors"))
    while window.worker is not None and window.worker.isRunning():
        settle(0.2)
    window.close()
    settle(0.3)
    window.overrides.close()
except Exception as exc:
    unreached("6", exc)
finally:
    if first_run is not None:
        first_run.candidates, first_run.xbox_found = real_candidates, real_xbox

print("\n=== 7. Settings: the Game folders row ===")
window = None
try:
    # Since Phase 99 with the one question as asked, as every test copy has it (the fresh install above lost it).
    config_io.save_config({"roots": [str(fake["A"] / "Games")], "enable_xbox": False, **test_sandbox.ALWAYS_WRITTEN})
    # One folder game, so the scans below and the bundle in section 10 have one to show: a real
    # program (the venv's own launcher) in a folder of its own.
    tiny = fake["A"] / "Games" / "Tiny Game"
    tiny.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(PROJECT / ".venv" / "Scripts" / "python.exe", tiny / "TinyGame.exe")
    before = json.loads(CONFIG.read_text(encoding="utf-8"))
    window = ui_window.MainWindow()
    window.resize(1280, 820)
    window.show()
    settle(1.6)  # past the quiet startup scan's moment, so only Settings' own scans are counted
    while window.worker is not None and window.worker.isRunning():
        settle(0.2)
    extra = SANDBOX / "drives" / "F" / "More games"
    extra.mkdir(parents=True)
    notes = {}

    def add_one():
        dialog = modal()
        if not isinstance(dialog, ui_settings.SettingsDialog):
            return False
        notes["shown"] = dialog.roots_editor.all_folders()
        dialog.roots_editor.choose_folder = lambda: str(extra)
        dialog.roots_editor.add_button.click()
        dialog.accept()
        return True

    starts: list[str] = []
    real_start = window.start_scan
    window.start_scan = lambda *a, **k: (starts.append(k.get("trigger") or ""), real_start(*a, **k))[1]
    run([lambda: QTimer.singleShot(0, window.open_settings) or True, add_one,
         lambda: notes.update(closed=modal() is None) or True], notes)
    after = json.loads(CONFIG.read_text(encoding="utf-8"))
    probe = ui_settings.SettingsDialog(window.config, window, store=window.overrides)
    settings_keys = set(probe.values())
    probe.done(0)
    check("it shows the folders config.json names", notes.get("shown") == [str(fake["A"] / "Games")], notes)
    check("OK writes the new list", after.get("roots") == [str(fake["A"] / "Games"), str(extra)], after.get("roots"))
    check("and only Settings' own keys: every other setting as it was",
          all(after.get(k) == v for k, v in before.items() if k not in settings_keys)
          and set(after) - set(before) <= settings_keys, sorted(set(after) ^ set(before)))
    check("the folder watch follows the new list", os.path.normpath(str(extra)) in window.watcher._roots.values())
    check("and a scan starts at once, for the folder added", starts == ["manual"], starts)
    while window.worker is not None and window.worker.isRunning():
        settle(0.2)
    starts.clear()

    def same_again():
        dialog = modal()
        if not isinstance(dialog, ui_settings.SettingsDialog):
            return False
        dialog.accept()
        return True

    run([lambda: QTimer.singleShot(0, window.open_settings) or True, same_again], {})
    check("OK with the list unchanged starts no scan", starts == [], starts)

    def take_one_out():
        dialog = modal()
        if not isinstance(dialog, ui_settings.SettingsDialog):
            return False
        dialog.roots_editor.list.setCurrentRow(1)
        dialog.roots_editor.remove_button.click()
        dialog.accept()
        return True

    run([lambda: QTimer.singleShot(0, window.open_settings) or True, take_one_out], {})
    after = json.loads(CONFIG.read_text(encoding="utf-8"))
    check("a folder taken out: gone from the list, still on the disk, and scanned without it",
          after.get("roots") == [str(fake["A"] / "Games")] and extra.is_dir() and starts == ["manual"], (after, starts))
    window.start_scan = real_start
    while window.worker is not None and window.worker.isRunning():
        settle(0.2)
except Exception as exc:
    unreached("7", exc)

print("\n=== 8. the empty library says why ===")
try:
    window.entries = []
    shown = {}
    for case, roots in (("none", []), ("missing", [r"Z:\Games", r"Y:\Jocuri"]),
                        ("nothing", [str(fake["B"])]), ("some missing", [str(fake["B"]), r"Z:\Games"])):
        window.config["roots"] = roots
        window.reload_views()
        settle(0.2)
        shown[case] = (window.library.empty.isVisible(), window.library.list.isVisible(),
                       window.library.empty_title.text(), window.library.empty_text.text(),
                       window.library.empty_button.isVisible())
    check("no folders, no games: says so, and offers to choose folders",
          shown["none"][:3] == (True, False, "No games yet") and shown["none"][4], shown["none"])
    check("folders that cannot be reached: names them", shown["missing"][2] == "Your game folders cannot be reached"
          and r"Z:\Games" in shown["missing"][3] and r"Y:\Jocuri" in shown["missing"][3], shown["missing"])
    check("folders there and nothing in them: names them",
          shown["nothing"][2] == "No games found" and str(fake["B"]) in shown["nothing"][3], shown["nothing"])
    check("some there, some not: both said", str(fake["B"]) in shown["some missing"][3]
          and r"Z:\Games" in shown["some missing"][3] and "cannot be reached" in shown["some missing"][3])
    check("the line is whole: as tall as its words need",
          window.library.empty_text.height() >= window.library.empty_text.heightForWidth(
              window.library.empty_text.width()))
    window.worker = type("Busy", (), {"isRunning": lambda self: True})()
    window._update_empty_state()
    check("while a scan runs: it is looking, no button", window.library.empty_title.text() == "Looking for your games..."
          and not window.library.empty_button.isVisibleTo(window.library))
    window.worker = None
    window.config["roots"] = []
    window._update_empty_state()
    notes = {}
    run([lambda: QTimer.singleShot(0, window.library.empty_button.click) or True,
         lambda: isinstance(modal(), ui_settings.SettingsDialog),
         lambda: notes.update(focused=modal().focusWidget() is modal().roots_editor.add_button) or True,
         lambda: modal().reject() or True], notes)
    check("its button opens Settings on the Game folders row", notes.get("focused"), notes)
    window.entries = window.overrides.load_catalog()
    window.reload_views()
    check("with games, the grid again and no message", not window.library.empty.isVisible()
          and window.library.list.isVisible())
except Exception as exc:
    unreached("8", exc)


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(f"packaging_{name}", PROJECT / "packaging" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


print("\n=== 9. one version, four places ===")
try:
    # 1.1.0 here; raised with each installer since (1.2.0 in Phase 79), so: this one or later.
    check(f"the version is {version.APP_VERSION}, MAJOR.MINOR.PATCH, 1.1.0 or later",
          re.fullmatch(r"\d+\.\d+\.\d+", version.APP_VERSION)
          and tuple(int(n) for n in version.APP_VERSION.split(".")) >= (1, 1, 0))
    build = load_script("build")
    installer = load_script("installer")
    check("build.py carries no number of its own: it reads shared/version.py", build.VERSION == version.APP_VERSION)
    app_dir = SANDBOX / "built" / "GameLauncher"
    (app_dir / "_internal").mkdir(parents=True)
    build.stamp_version(app_dir)
    stamped = (app_dir / "_internal" / version.VERSION_FILE).read_text(encoding="utf-8").strip()
    check("the stamped file says it, and the build's day beside it",
          stamped == version.APP_VERSION and (app_dir / "_internal" / version.BUILD_FILE).read_text(
              encoding="utf-8").strip() == date.today().isoformat())
    check("the installer reads it for Add/Remove Programs", installer.read_version(app_dir) == version.APP_VERSION)
    real_frozen, real_resource = paths.FROZEN, paths.resource_dir
    paths.FROZEN, paths.resource_dir = True, lambda: app_dir / "_internal"
    try:
        built = version.build_date()
        dialog = ui_settings.SettingsDialog(window.config, window, store=window.overrides)
        built_line = (dialog.version_row.title.text(), dialog.version_row.hint.text())
        dialog.done(0)
    finally:
        paths.FROZEN, paths.resource_dir = real_frozen, real_resource
    check("an installed copy's Settings shows the version and the day it was built",
          built == date.today() and built_line[0] == f"{version.APP_NAME} {version.APP_VERSION}"
          and built_line[1].startswith("Built ") and str(date.today().year) in built_line[1], built_line)
    dialog = ui_settings.SettingsDialog(window.config, window, store=window.overrides)
    check("a copy run from source says so", dialog.version_row.title.text().endswith(version.APP_VERSION)
          and "from source" in dialog.version_row.hint.text(), dialog.version_row.hint.text())
    sections = [label.text() for label in dialog.findChildren(ui_settings.QLabel) if label.objectName() == "SettingSection"]
    check("the version is Settings' last section", sections[-1] == "About", sections)
    dialog.done(0)
    tree = ast.parse((PROJECT / "launcher.py").read_text(encoding="utf-8"))
    logs_it = any(isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "info"
                  and any(isinstance(a, ast.Call) and getattr(a.func, "attr", "") == "describe"
                          and getattr(a.func.value, "id", "") == "version" for a in node.args)
                  for node in ast.walk(tree))
    check("launcher.log says it at every start", logs_it and version.describe().startswith(
        f"{version.APP_NAME} {version.APP_VERSION}, "))
except Exception as exc:
    unreached("9", exc)

print("\n=== 10. the diagnostics bundle ===")
try:
    store = window.overrides
    key = "0123456789abcdef0123456789abcdef"
    config_io.save_config({"steamgriddb_key": key})
    accounts = store.steam_accounts() if getattr(store, "keeps_steam_time", False) else []
    account = accounts[0] if accounts else {"account_id": 794996709, "steam_id64": 794996709 + rules.STEAM_ID64_BASE,
                                            "persona": None}
    log_file = paths.data_dir() / rules.LOG_FILENAME
    log_file.write_text(
        "2026-10-12 10:00:00,000 INFO    logic.steam_time: steam time: account "
        f"{account['account_id']}'s localconfig.vdf does not read\n"
        f"2026-10-12 10:00:01,000 INFO    web.steamgriddb: GET https://www.steamgriddb.com/api/v2?key={key}\n"
        f"2026-10-12 10:00:02,000 INFO    logic.x: SteamID64 {account['steam_id64']} seen\n", encoding="utf-8")
    (log_file.with_name(log_file.name + ".1")).write_text("an older log\n", encoding="utf-8")
    target = SANDBOX / "out" / "diagnostics.zip"
    dialog = ui_settings.SettingsDialog(window.config, window, store=store)
    dialog.choose_diagnostics_path = lambda: str(target)
    dialog.diagnostics_button.click()
    status = dialog.diagnostics_status.text()
    dialog.done(0)
    check("Save diagnostics... writes one zip where asked, and says where", target.is_file() and str(target) in status,
          status)
    with zipfile.ZipFile(target) as archive:
        names = archive.namelist()
        texts = {n: archive.read(n).decode("utf-8") for n in names}
    check("about, settings, the scan, a summary, and the logs",
          names == ["about.txt", "config.json", "scan.json", "summary.txt", "launcher.log", "launcher.log.1"], names)
    check("the SteamGridDB key is in no part of it -- the log's copy included",
          not any(key in t for t in texts.values()) and "<SteamGridDB key removed>" in texts["launcher.log"])
    settings = json.loads(texts["config.json"])
    check("its settings say a key is set, never what", "steamgriddb_key" not in settings
          and settings.get("steamgriddb_key (set?)") is True)
    check("no Steam account in it: the log's ids become steam-account-N",
          not any(str(account["account_id"]) in t or str(account["steam_id64"]) in t for t in texts.values())
          and re.search(r"steam-account-\d", texts["launcher.log"]))
    scan = json.loads(texts["scan.json"])
    folder_games = [i for i in scan["installs"] if i["source"] == "folders"]
    check(f"every game the last scan found, with its folder and what starts it ({len(scan['installs'])})",
          len(scan["installs"]) == len(store.load_catalog()) and folder_games
          and all(i["install_dir"] in texts["summary.txt"] and i["launch_target"] for i in folder_games))
    check("with how its exe was chosen, the ones passed over, and the store's own details",
          all({"detection", "alternatives", "extra", "chosen_exe"} <= set(i) for i in scan["installs"]))
    check("and the game folders, there or not", scan["game_folders"] == config_io.load_config().get("roots")
          and "game_folders_missing" in scan)
    records = store.export_records()
    personal = [r.get("notes") for r in records.values() if r.get("notes")] + \
               [s["start"] for r in records.values() for s in r.get("sessions") or []][:20]
    check("nothing of the play history: no session, note or playtime field",
          not any(str(p) in t for p in personal for t in texts.values())
          and not any(f'"{k}"' in texts["scan.json"] for k in ("sessions", "playtime_seconds", "notes", "favorite")),
          [p for p in personal if any(str(p) in t for t in texts.values())][:3])
    purchases = store.all_purchases() if hasattr(store, "all_purchases") else {}
    bought_at = {r["store"] for rows in purchases.values() for r in rows} - set(rules.SOURCE_LABELS.values())
    check(f"no purchase (the copy holds {sum(len(r) for r in purchases.values())})",
          not any(f'"{k}"' in t for k in ("paid_cents", "purchases") for t in texts.values())
          and not any(s in t for s in bought_at for t in texts.values()), bought_at)
    check("the version is in it", f"{version.APP_NAME} {version.APP_VERSION}" in texts["about.txt"])
except Exception as exc:
    unreached("10", exc)

if window is not None:
    window.close()
    settle(0.3)
    window.overrides.close()

print("\n=== 11. the layers ===")
try:
    layers = subprocess.run([sys.executable, str(PROJECT / "tests" / "check_layers.py")], cwd=PROJECT,
                            capture_output=True, text=True, timeout=120)
    check("no import points up a layer, and sqlite3 stays in data_access/",
          "upward imports: 0" in layers.stdout and "sqlite3 outside data_access/: 0" in layers.stdout,
          layers.stdout[-300:])
    # A fresh install has the network on by default, as a friend's will: its first scan asks
    # Steam's store for what it found (blocked here). Only the sanctioned hosts are asked.
    hosts = {re.match(r"https?://([^/]+)/", url).group(1) for url in attempts}
    # Since Phase 86 also Steam's wishlist service, for the accounts the copy has marked mine.
    wishlist_only = all(url.startswith("https://api.steampowered.com/IWishlistService/") for url in attempts
                        if "api.steampowered.com" in url)
    check(f"only Steam's store, its picture server and its wishlist service were asked ({len(attempts)} blocked here)",
          hosts <= {"store.steampowered.com", "cdn.akamai.steamstatic.com", "shared.akamai.steamstatic.com",
                    "steamcdn-a.akamaihd.net", "api.steampowered.com"} and wishlist_only, hosts)
except Exception as exc:
    unreached("11", exc)

print("\n=== 12. the real library is exactly as it was found ===")
changed = box.finish()
check("config.json and the library database are unchanged", not changed, changed)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
