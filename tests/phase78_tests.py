"""Phase 78: the installer made ready for other people's PCs -- what can be checked without building it.

The Windows Sandbox file make_sandbox.py writes (well formed, both folders read only, the game
copied to C:\\Games, kept out of git); the installer's keep-list (the user's data and, since this
phase, the log with its two older copies -- the uninstaller's copy in step); an update over a
made-up install folder keeping every data file and folder and removing the old program, where the
installer as it was before this phase deleted the logs; the two documents, CITESTE-MA.md for the
friends and DISTRIBUTIE.md; and tests/check_installer.py, the run of the built installer, kept
out of run_all (it needs a fresh build).

The built installer itself is proven by tests/check_installer.py, run by hand after a build.
"""
import hashlib
import importlib.util
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import test_sandbox

box = test_sandbox.start()

from logic import uninstall
from shared import rules

passed = failed = 0
SCRATCH = Path(tempfile.mkdtemp(prefix="phase78_"))


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


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


print("=== 1. the Windows Sandbox file ===")
try:
    make = load("make_sandbox", PROJECT / "packaging" / "sandbox" / "make_sandbox.py")
    dist, game = SCRATCH / "dist", SCRATCH / "games" / "Slow Roads"
    dist.mkdir()
    game.mkdir(parents=True)
    written = make.write(SCRATCH / "test.wsb", dist=dist, game=game)
    root = ET.parse(written).getroot()
    folders = root.findall("./MappedFolders/MappedFolder")
    check("well formed: a Configuration with two mapped folders and a logon command",
          root.tag == "Configuration" and len(folders) == 2 and root.find("./LogonCommand/Command") is not None)
    hosts = [f.findtext("HostFolder") for f in folders]
    inside = [f.findtext("SandboxFolder") for f in folders]
    check("the installer's folder and the game folder, from this PC", hosts == [str(dist), str(game)], hosts)
    check("both read only: nothing in the sandbox can change them",
          [f.findtext("ReadOnly") for f in folders] == ["true", "true"])
    check("both onto the sandbox's Desktop", all(s.startswith(make.SANDBOX_DESKTOP + "\\") for s in inside), inside)
    command = root.findtext("./LogonCommand/Command")
    check("at logon the game is copied to C:\\Games, then Explorer opens on the installer",
          f'robocopy "{inside[1]}" "C:\\Games\\Slow Roads"' in command and command.index("robocopy")
          < command.index("explorer") and f'explorer "{inside[0]}"' in command, command)
    try:
        make.write(SCRATCH / "none.wsb", dist=SCRATCH / "no dist", game=game)
        refused = False
    except SystemExit:
        refused = True
    check("with no installer built, it says so and writes nothing", refused and not (SCRATCH / "none.wsb").exists())
    ignored = subprocess.run(["git", "check-ignore", "-q", "packaging/sandbox/GameLauncher.wsb"], cwd=PROJECT)
    check("the .wsb names this PC's folders, so git ignores it", ignored.returncode == 0)
    real = PROJECT / "packaging" / "sandbox" / "GameLauncher.wsb"
    if real.is_file():
        mapped = [f.findtext("HostFolder") for f in ET.parse(real).getroot().findall("./MappedFolders/MappedFolder")]
        check("the one written here maps folders that are there, the installer among them",
              all(Path(h).is_dir() for h in mapped) and (Path(mapped[0]) / "GameLauncher-Setup.exe").is_file(), mapped)
except Exception as exc:
    unreached("1", exc)

print("\n=== 2. the keep-list ===")
installer = None
try:
    installer = load("installer", PROJECT / "packaging" / "installer.py")
    logs = [rules.LOG_FILENAME] + [f"{rules.LOG_FILENAME}.{n}" for n in range(1, rules.LOG_BACKUP_COUNT + 1)]
    check("the user's data: the settings, the library database and its journal, the cache",
          {"config.json", "library.db", "library.db-journal", "cache"} <= set(installer.USER_DATA))
    check(f"and the log with its {rules.LOG_BACKUP_COUNT} older copies", set(logs) <= set(installer.USER_DATA),
          installer.USER_DATA)
    check("the uninstaller's copy of the list in step", uninstall.USER_DATA == installer.USER_DATA)
except Exception as exc:
    unreached("2", exc)


def made_up_install(folder: Path) -> dict[str, str]:
    """An installed copy as an older build left it, with every kind of the user's data."""
    (folder / "_internal" / "presentation").mkdir(parents=True)
    (folder / "_internal" / "presentation" / "old.pyd").write_bytes(b"old program")
    (folder / "GameLauncher.exe").write_bytes(b"old exe")
    (folder / "left by an old build.txt").write_text("x", encoding="utf-8")
    data = {"config.json": "{}", "library.db": "a database", "launcher.log": "today",
            "launcher.log.1": "yesterday", "launcher.log.2": "before", "cache/steam_web.json": "{}",
            "backups/2026-10-11_20-00-00/library.db": "a snapshot", "save_backups/Slow Roads/1.zip": "saves",
            "migrated/2026-10-10/overrides.json": "{}"}
    for name, text in data.items():
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_text(text, encoding="utf-8")
    return {name: sha(folder / name) for name in data}


print("\n=== 3. an update over an installed copy ===")
try:
    folder = SCRATCH / "installed"
    kept = made_up_install(folder)
    installer.clear_program_files(folder)
    check("every data file and folder kept, byte for byte -- the logs among them",
          all((folder / n).is_file() and sha(folder / n) == h for n, h in kept.items()),
          [n for n, h in kept.items() if not (folder / n).is_file()])
    check("the old program gone: _internal, the exe, what an old build left beside it",
          not (folder / "_internal").exists() and not (folder / "GameLauncher.exe").exists()
          and not (folder / "left by an old build.txt").exists())
    before_text = subprocess.run(["git", "show", "before-phase-78:packaging/installer.py"], cwd=PROJECT,
                                 capture_output=True, check=True).stdout
    (SCRATCH / "installer_before.py").write_bytes(before_text)
    old = load("installer_before", SCRATCH / "installer_before.py")
    older_folder = SCRATCH / "installed-before"
    made_up_install(older_folder)
    old.clear_program_files(older_folder)
    lost = [n for n in ("launcher.log", "launcher.log.1", "launcher.log.2") if not (older_folder / n).exists()]
    check("as it was before this phase, an update deleted the log and its two older copies", len(lost) == 3, lost)
except Exception as exc:
    unreached("3", exc)

print("\n=== 4. the note for the friends, and the one for the thesis ===")
try:
    readme = (PROJECT / "docs" / "CITESTE-MA.md").read_text(encoding="utf-8")
    for words, what in ((r"%LOCALAPPDATA%\Programs\Game Launcher", "where its data lives"),
                        ("Rulează oricum", "what to click when SmartScreen warns"),
                        ("Save diagnostics", "how to send the diagnostics"),
                        ("nu are cont", "that there is no account"),
                        ("nu trimite nimic despre tine", "that nothing about them leaves the PC"),
                        ("SteamGridDB", "SteamGridDB only with their own key"),
                        ("export anonim", "the thesis paragraph: an anonymised export"),
                        ("E alegerea ta", "and that it is their choice"),
                        ("peste cel vechi", "how to update")):
        check(f"CITESTE-MA.md says {what}", words in readme, words)
    check("and fits on a page, roughly", len(readme.splitlines()) <= 110, len(readme.splitlines()))
    plan = (PROJECT / "docs" / "DISTRIBUTIE.md").read_text(encoding="utf-8")
    sections = re.findall(r"^## (\d+)\. (.+)$", plan, re.MULTILINE)
    check("DISTRIBUTIE.md: the installer, the first run, the version, the diagnostics, the Sandbox, 79 and 80",
          [n for n, _ in sections] == [str(i) for i in range(1, 12)]
          and any("faza 79" in t for _, t in sections) and any("faza 80" in t for _, t in sections), sections)
    checklist = plan.split("## 7.")[1].split("## 8.")[0]
    steps = re.findall(r"^\d+\. \*\*", checklist, re.MULTILINE)
    check(f"the Sandbox checklist: {len(steps)} steps, from the install to --silent",
          len(steps) >= 9 and "--silent" in checklist and "Save diagnostics" in checklist
          and "Update Game Launcher?" in checklist)
    check("and how to turn Windows Sandbox on", "Windows Sandbox" in plan and "Virtualization" in plan)
except Exception as exc:
    unreached("4", exc)

print("\n=== 5. the run of the built installer ===")
try:
    script = PROJECT / "tests" / "check_installer.py"
    text = script.read_text(encoding="utf-8")
    check("tests/check_installer.py is there: two installs in a fake profile, the data kept",
          "USERPROFILE" in text and "idempotent" in text and "--silent" in text)
    check("and not in run_all: it needs a fresh build",
          "check_installer" not in (PROJECT / "tests" / "run_all.py").read_text(encoding="utf-8"))
    layers = subprocess.run([sys.executable, str(PROJECT / "tests" / "check_layers.py")], cwd=PROJECT,
                            capture_output=True, text=True, timeout=120)
    check("no import points up a layer", "upward imports: 0" in layers.stdout, layers.stdout[-200:])
except Exception as exc:
    unreached("5", exc)

shutil.rmtree(SCRATCH, ignore_errors=True)
print("\n=== 6. the real library is exactly as it was found ===")
changed = box.finish()
check("config.json and the library database are unchanged", not changed, changed)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
