"""Phase 82: a whole drive is not a game folder (the 1.2.2 hotfix).

The first friend to install 1.2.1 answered "Where do you keep your games?" with C:\\: every
top-level folder of the drive became a game, each walked six levels deep for ten minutes at every
start, and "Remove from disk..." was offered on Program Files. Here:

  1. the judgements, on real paths -- a drive, Windows' own folders by where they sit, a game's
     own Engine\\Binaries\\ThirdParty\\Windows that is none of them;
  2. the folder list of the first run and of Settings refusing a drive and offering its game
     folders, ticked, in its place -- on a made-up drive and on this PC's real C:\\ -- and refusing
     a Windows folder;
  3. the scan on a made-up drive: the folder provider never takes a Windows folder for a game, the
     walk never enters one (and still walks a game's own Content\\Windows), discovery never hands
     a drive to the provider, and says so once;
  4. removal's fifth rule, in each of its three cases, in the plan and again where the deleting
     happens -- against a stand-in for Windows' shell, so nothing can be removed whatever happens;
  5. a config.json that already holds C:\\ (the friend's): not scanned, not watched, named in the
     empty library and in a message card, his file left as it is; Settings lists it as not scanned;
  6. the documents, the version, the layers.

A made-up drive is a folder of the suite's own that drives.below_root is told to take for a drive
root, the way suite 77 stood in for Windows' drive list. On a throwaway copy of the data; the
network is blocked.
"""
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path
from types import SimpleNamespace

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import sources  # the build log's notes (Phase 91)
import test_sandbox

box = test_sandbox.start()
SANDBOX = box.folder
CONFIG = SANDBOX / "config.json"

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

app = QApplication(sys.argv)

from logic import discovery, first_run, removal
from presentation import ui_first_run, ui_folders, ui_settings, ui_window
from providers.folders import FolderProvider
from shared import drives, rules, version, walk

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


def settle(seconds: float = 0.3) -> None:
    loop = QEventLoop()
    QTimer.singleShot(int(seconds * 1000), loop.quit)
    loop.exec()


# -- a made-up drive -------------------------------------------------------------------------

WORK = Path(tempfile.mkdtemp(prefix="phase82_"))
DRIVE = WORK / "drive"      # stands in for a whole drive, laid out as C:\ is
EMPTY = WORK / "empty"      # a drive with no game folder on it
REAL_BELOW = getattr(drives, "below_root", None)  # the code before this phase has none


def make(path: Path, data: bytes = b"MZ" + b"\0" * (64 * 1024)) -> None:  # over MIN_CANDIDATE_SIZE_BYTES
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


for relative in (r"Windows\System32\notepad.exe", r"Program Files\Some App\app.exe",
                 r"Program Files\WindowsApps\Store.App\store.exe", r"ProgramData\Vendor\service.exe",
                 r"Users\Public\thing.exe", r"Tool\tool.exe",
                 r"Games\Some Game\SomeGame.exe",
                 r"Games\Some Game\Content\Windows\helper.exe",  # as SILENT HILL Townfall's own
                 r"Jocuri\Alt Joc\AltJoc.exe"):
    make(DRIVE / relative)
EMPTY.mkdir()
SYSTEM_HERE = sorted(str(DRIVE / name) for name in ("Program Files", "ProgramData", "Users", "Windows"))


def stand_in(folder: str):
    """drives.below_root, with DRIVE and EMPTY taken for drive roots."""
    path = os.path.normcase(os.path.normpath(os.path.abspath(folder)))
    for root in (DRIVE, EMPTY):
        top = os.path.normcase(str(root))
        if path == top:
            return ""
        if path.startswith(top + os.sep):
            return path[len(top) + 1:].replace("/", "\\").casefold()
    return REAL_BELOW(folder) if REAL_BELOW else None


print("=== 1. what is no game folder ===")
try:
    check("a whole drive is one, however it is written",
          all(drives.is_drive_root(p) for p in ("C:\\", "C:", "C:/", "d:\\", "\\\\server\\share"))
          and not any(drives.is_drive_root(p) for p in (r"C:\games", r"D:\Games\x", "games")))
    check("Windows' own folders are, by where they sit",
          all(drives.is_system_folder(p) for p in (r"C:\Windows", r"C:\Program Files", r"c:\program files (x86)",
                                                    r"C:\ProgramData", r"C:\Users", r"D:\$Recycle.Bin",
                                                    r"C:\System Volume Information", r"C:\Program Files\WindowsApps")))
    own = r"C:\games\SILENT HILL Townfall\Engine\Binaries\ThirdParty\Windows"
    check("a game's own Windows folder is not one (13 of them in the real games here), nor a folder inside one",
          not any(drives.is_system_folder(p) for p in (own, r"C:\games\Adobe Lightroom Classic 2026\Data\ProgramData",
                                                       r"C:\Windows\System32", r"C:\Users\andre", r"C:\games")))
    check("the sentences the user reads",
          drives.not_a_game_folder("C:") == "C:\\ is a whole drive, not a game folder."
          and drives.not_a_game_folder(r"C:\Program Files") == r"C:\Program Files is a Windows folder, not a game folder."
          and drives.not_a_game_folder(r"C:\games") == "", drives.not_a_game_folder("C:"))
    check("the roots split into the ones scanned and the ones never",
          drives.split_roots(["C:\\", r"C:\games", r"C:\Windows", r"C:\voices38"])
          == ([r"C:\games", r"C:\voices38"], [("C:\\", "C:\\ is a whole drive, not a game folder."),
                                             (r"C:\Windows", r"C:\Windows is a Windows folder, not a game folder.")]))
    check("one list of Windows' folders: the first run's old one is gone",
          not hasattr(rules, "FIRST_RUN_SYSTEM_FOLDERS") and "windows" in rules.SYSTEM_FOLDERS
          and r"program files\windowsapps" in rules.SYSTEM_FOLDERS)
    check("the first run still never offers one, and the warning that allowed a drive is gone",
          not hasattr(ui_folders, "DRIVE_WARNING"))
except Exception as exc:
    unreached("1", exc)

print("\n=== 2. the folder list refuses a drive and offers its game folders ===")
try:
    drives.below_root = stand_in
    offered = first_run.instead_of(str(DRIVE))
    check("in a drive's place: the folders on it the first run would offer",
          offered == [str(DRIVE / "Games"), str(DRIVE / "Jocuri")], offered)

    dialog = ui_first_run.FirstRunDialog([], False, 1.0)
    editor = dialog.folders
    editor.choose_folder = lambda: str(DRIVE)
    editor.add_button.click()
    check("the first run: the drive itself is not added", str(DRIVE) not in editor.all_folders(),
          editor.all_folders())
    check("its game folders are, ticked -- the answer in one click",
          editor.folders() == offered and editor.all_folders() == offered, editor.all_folders())
    check("the line under the list says why, and what was done instead",
          editor.warning.isVisibleTo(editor)
          and f"{DRIVE}\\ is a whole drive, not a game folder." in editor.warning.text()
          and ui_folders.INSTEAD.strip() in editor.warning.text(), editor.warning.text())
    dialog.continue_button.click()
    check("Continue answers with the drive's game folders, never the drive",
          dialog.answer()[0] == offered, dialog.answer())

    editor = ui_folders.FolderList([], checkable=True, scale=1.0)
    editor.choose_folder = lambda: str(DRIVE / "Program Files")
    editor.add_button.click()
    check("a Windows folder is refused, nothing in its place",
          editor.all_folders() == [] and "is a Windows folder, not a game folder" in editor.warning.text(),
          (editor.all_folders(), editor.warning.text()))
    editor.choose_folder = lambda: str(EMPTY)
    editor.add_button.click()
    check("a drive with no game folder on it: refused, and said so",
          editor.all_folders() == [] and ui_folders.NOTHING_INSTEAD.strip() in editor.warning.text(),
          editor.warning.text())
    editor.choose_folder = lambda: str(DRIVE / "Games")
    editor.add_button.click()
    check("an ordinary folder is added, and the refusal goes",
          editor.all_folders() == [str(DRIVE / "Games")] and not editor.warning.isVisibleTo(editor),
          editor.warning.text())
    drives.below_root = REAL_BELOW

    # This PC's own C:\, as the friend chose it -- the finder only lists its top folders.
    expected = first_run.candidates(["C:\\"])
    plain = ui_folders.FolderList([], checkable=False, scale=1.0)  # Settings' list: no ticks
    plain.choose_folder = lambda: "C:\\"
    plain.add_button.click()
    check(f"this PC's C:\\ chosen in Settings' list: refused, and {expected} added instead",
          "C:\\" not in plain.all_folders() and plain.folders() == expected
          and "C:\\ is a whole drive, not a game folder." in plain.warning.text(),
          (plain.all_folders(), plain.warning.text()))
    plain.choose_folder = lambda: "C:"
    plain.add_button.click()
    check("written as C: too", "C:" not in plain.all_folders() and plain.folders() == expected)
except Exception as exc:
    unreached("2", exc)
finally:
    drives.below_root = REAL_BELOW

print("\n=== 3. the scan on a made-up drive ===")
try:
    drives.below_root = stand_in
    lines.clear()
    provider = FolderProvider([str(DRIVE)])
    entries = provider.discover()
    dirs = sorted(e.install_dir for e in entries)
    check("handed a whole drive, the folder provider takes no Windows folder for a game",
          not any(d in SYSTEM_HERE for d in dirs) and str(DRIVE / "Tool") in dirs, dirs)
    check("and keeps out of each of them", sorted(provider.kept_out) == SYSTEM_HERE, provider.kept_out)
    said = [line for line in lines if "kept out of" in line]
    check("said once in the scan's log, naming them", len(said) == 1 and all(p in said[0] for p in SYSTEM_HERE), said)

    files, report = walk.walk_tree(str(DRIVE))
    hits = [hit.path for hit in files]
    check("the walk never enters a Windows folder",
          sorted(report.system_folders) == SYSTEM_HERE
          and not any(hit.startswith(tuple(p + os.sep for p in SYSTEM_HERE)) for hit in hits),
          (report.system_folders, hits))
    helper = str(DRIVE / r"Games\Some Game\Content\Windows\helper.exe")
    check("and still walks a game's own Windows folder", helper in hits, hits)

    game_root = FolderProvider([str(DRIVE / "Games")])
    found = game_root.discover()
    check("a game folder as the root: its game found, nothing kept out",
          [e.install_dir for e in found] == [str(DRIVE / r"Games\Some Game")] and game_root.kept_out == [],
          ([e.install_dir for e in found], game_root.kept_out))

    lines.clear()
    used = []
    entries = discovery.run_discovery({"roots": [str(DRIVE), str(DRIVE / "Games")], "allow_network": False,
                                       "enable_xbox": False}, providers_out=used, folders_only=True)
    folders = [p for p in used if isinstance(p, FolderProvider)][0]
    check("discovery never hands the drive to the folder provider", folders.roots == [str(DRIVE / "Games")],
          folders.roots)
    check("and says so in the log", any(f"not scanned: {DRIVE}" in line and "whole drive" in line for line in lines),
          [line for line in lines if "not scanned" in line])
    check("what is found is the game folder's game alone",
          [e.install_dir for e in entries] == [str(DRIVE / r"Games\Some Game")], [e.install_dir for e in entries])
except Exception as exc:
    unreached("3", exc)
finally:
    drives.below_root = REAL_BELOW

print("\n=== 4. removal's fifth rule ===")


class Shell:
    """Stands in for Windows' shell: records what it was asked to remove and removes nothing."""

    def __init__(self):
        self.asked = []

    def SHFileOperation(self, operation):
        self.asked.append(operation[2])
        return 0, False


real_shell = removal.shell
fake = Shell()
try:
    removal.shell = fake
    check("the shell is stood in for before anything is asked", removal.shell is fake)

    def view(folder, source="folders"):
        entry = SimpleNamespace(source=source, install_dir=folder, source_id=folder)
        return SimpleNamespace(entry=entry, display_name=os.path.basename(folder) or folder, key=folder.casefold())

    friend = {"roots": ["C:\\"]}
    for folder, words in (("C:\\", "a whole drive"), (r"C:\Windows", "one of Windows' own folders"),
                          (r"C:\Program Files", "one of Windows' own folders"),
                          (r"C:\games", "directly on C:\\")):
        plan = removal.plan(view(folder), friend)
        check(f"{folder} under the friend's C:\\ root: blocked -- {words}",
              plan.tier == rules.TIER_BLOCKED and not plan.deletes and words in plan.blocked, plan.blocked)
    check("the three cases, as the rule says them",
          "whole drive" in removal.protected("D:\\") and "Windows' own" in removal.protected(r"C:\Program Files\WindowsApps")
          and "directly on C:\\" in removal.protected(r"C:\Some Folder") and removal.protected(r"C:\games\Slow Roads") == "")

    drives.below_root = stand_in
    on_drive = removal.plan(view(str(DRIVE / "Tool")), {"roots": [str(DRIVE)]})
    deeper = removal.plan(view(str(DRIVE / r"Games\Some Game")), {"roots": [str(DRIVE / "Games")]})
    check("on a made-up drive: a top folder of it blocked, a game in a game folder still removable",
          on_drive.tier == rules.TIER_BLOCKED and deeper.tier == rules.TIER_DELETE and deeper.deletes,
          (on_drive, deeper))
    drives.below_root = REAL_BELOW

    for folder in ("C:\\", r"C:\Windows", r"C:\games"):
        ok, message = removal.send_to_recycle_bin(folder, interactive=False)
        check(f"asked straight to remove {folder}, the one place that deletes refuses it", not ok and message)
    check("and Windows' shell was never asked", fake.asked == [], fake.asked)
    spare = WORK / "spare"
    spare.mkdir()
    removal.send_to_recycle_bin(str(spare), interactive=False)
    check("an ordinary folder still reaches the shell (the stand-in, which removes nothing)",
          fake.asked == [str(spare)] and spare.is_dir(), fake.asked)
except Exception as exc:
    unreached("4", exc)
finally:
    removal.shell = real_shell
    drives.below_root = REAL_BELOW

print("\n=== 5. a config.json that already holds C:\\ (the friend's) ===")
real_manifests = discovery.manifest_providers
real_top = walk.iter_top_level
real_queue = ui_window.MainWindow.queue_status
walked: list[str] = []
cards: list[str] = []


def watched_top(root):
    walked.append(root)
    if drives.is_drive_root(root):
        raise RuntimeError(f"a whole drive was walked: {root}")
    return real_top(root)


def keep_card(self, text, ms):
    cards.append(text)
    return real_queue(self, text, ms)


try:
    saved = json.loads(CONFIG.read_text(encoding="utf-8"))
    # The version that ran is written at a start when it differs (Phase 99): a friend's config holds it after
    # the first start of this version, and the check below is that nothing else is written.
    saved.update({"roots": ["C:\\"], "watch_folders": True, rules.VERSION_SEEN_KEY: version.APP_VERSION})
    CONFIG.write_text(json.dumps(saved, indent=2), encoding="utf-8")
    before = CONFIG.read_bytes()
    discovery.manifest_providers = lambda config: []  # no store games: the library ends empty
    walk.iter_top_level = watched_top
    ui_window.MainWindow.queue_status = keep_card
    lines.clear()

    window = ui_window.MainWindow()
    window.resize(1280, 820)
    window.show()
    settle(0.5)
    check("a message card at start names it", any(text.startswith("C:\\ is a whole drive, not a game folder.")
                                                  and "not scanned" in text for text in cards), cards)
    check("the folder watch does not watch it", window.watcher._roots == {}, window.watcher._roots)
    window.start_scan(trigger="manual")
    while window.worker is not None and window.worker.isRunning():
        settle(0.2)
    settle(0.5)
    check("the scan never walked the drive", not any(drives.is_drive_root(r) for r in walked), walked)
    check("and logged that it was not scanned", any("not scanned: C:\\" in line for line in lines),
          [line for line in lines if "not scanned" in line])
    check("the library, empty, says why", window.library.empty.isVisibleTo(window)
          and window.library.empty_title.text() == "C:\\ is a whole drive, not a game folder"
          and "does not look in it" in window.library.empty_text.text(), window.library.empty_title.text())
    check("with the button to Game folders", window.library.empty_button.isVisibleTo(window)
          and window.library.empty_button.text() == "Game folders...", window.library.empty_button.text())
    asked = []
    window.open_settings = lambda focus=None: asked.append(focus)
    window.library.empty_button.click()
    check("which opens Settings on the Game folders row", asked == ["roots"], asked)
    check("his config.json is left exactly as it was", CONFIG.read_bytes() == before)

    dialog = ui_settings.SettingsDialog(window.config, window, known_keys=set(), store=window.overrides)
    roots = dialog.roots_editor
    check("Settings lists it, and says it is not scanned",
          roots.all_folders() == ["C:\\"]
          and "C:\\ is a whole drive, not a game folder. It is not scanned" in roots.warning.text(),
          (roots.all_folders(), roots.warning.text()))
    roots.list.setCurrentRow(0)
    roots.remove_button.click()
    check("taken out, the line goes", roots.all_folders() == [] and roots.warning.text() == "",
          roots.warning.text())
    dialog.reject()
    window.close()
    settle(0.3)
    window.overrides.close()
except Exception as exc:
    unreached("5", exc)
finally:
    discovery.manifest_providers = real_manifests
    walk.iter_top_level = real_top
    ui_window.MainWindow.queue_status = real_queue

print("\n=== 6. the documents, the version, the layers ===")
try:
    claude = (PROJECT / "CLAUDE.md").read_text(encoding="utf-8")
    distribution = (PROJECT / "docs" / "DISTRIBUTIE.md").read_text(encoding="utf-8")
    readme = (PROJECT / "docs" / "CITESTE-MA.md").read_text(encoding="utf-8")
    # 1.2.2 or later: the hotfix is in every release after it (1.2.3 brought the Reports tab, Phase 85).
    check("version 1.2.2 or later", version.parse(version.APP_VERSION) >= (1, 2, 2), version.APP_VERSION)
    check("CLAUDE.md has the phase and its notes", "| 82 |" in claude and "## Phase 82 notes" in sources.build_log())
    check("DISTRIBUTIE says a whole drive is refused, from 1.2.2",
          "nu se mai poate alege, de la 1.2.2" in distribution and "se poate alege, dar e însoțită" not in distribution)
    check("the friends' note says it in one sentence, and names the version",
          "nu un disc întreg" in readme and f"Versiunea {version.APP_VERSION}" in readme)
    layers = subprocess.run([sys.executable, str(PROJECT / "tests" / "check_layers.py")], capture_output=True,
                            text=True, encoding="utf-8", errors="replace")
    check("no import points up a layer", layers.returncode == 0, layers.stdout[-400:])
    check("nothing in this suite reached the network", attempts == [], attempts)
except Exception as exc:
    unreached("6", exc)

print("\n=== 7. the real library is exactly as it was found ===")
changed = box.finish()
check("config.json and the library database are unchanged", not changed, changed)
import shutil
shutil.rmtree(WORK, ignore_errors=True)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
