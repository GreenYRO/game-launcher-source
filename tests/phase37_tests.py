"""Phase 37: the project folder can be renamed or moved without losing anything.

Asked as "can we safely rename the folder of the project to Game Launcher?". The answer was
yes, once chosen artwork -- stored with full paths -- is found again after a move. Everything
here runs against a throwaway copy of the data (test_sandbox) that is made to look like the
project after a rename: every path the real data holds into the project folder is pointed
at a folder that does not exist, and the artwork itself is copied into the copy, read only.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # the project folder, one up from tests/
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import sources
import test_sandbox

box = test_sandbox.start()
HERE = Path(__file__).resolve().parents[1]
SANDBOX = Path(box.folder)
box.copy_cache("sgdb_art", "steam_art", "imported_art")

# Make the copy look like the project after a rename: every path into the real project
# folder now leads into one that is gone. "The project folder" is where this file is --
# and also whatever folder the chosen pictures sit in, read off them the way
# catalog_io.relocated reads them (the part before their cache folder). In a copy of the
# project (the thesis copy) the data still points into the folder it was copied from;
# with only this folder's name to rewrite nothing was moved, and section 2 had nothing to
# test. Only chosen artwork is read: a game's own folder could contain a "cache" too.
from shared import rules  # noqa: E402  -- no paths in it, safe once the sandbox exists

GONE = r"C:\Users\andre\A Folder That Was Renamed Away"
DATA_FOLDER = re.compile(r"^([A-Za-z]:[\\/].*)[\\/]cache[\\/]", re.IGNORECASE)

library = test_sandbox.records()
real_prefixes = {str(HERE)}
for record in library.values():
    for field in rules.ARTWORK_KEYS:
        found = DATA_FOLDER.match(value) if isinstance(value := record.get(field), str) else None
        if found:
            real_prefixes.add(found.group(1))
print(f"project folders the copied data points into: {sorted(real_prefixes)}")


def moved(value):
    """The same value with every path into a project folder led into one that is gone."""
    text = json.dumps(value, ensure_ascii=False)
    for prefix in real_prefixes:
        text = text.replace(json.dumps(prefix)[1:-1], json.dumps(GONE)[1:-1])
    return json.loads(text)


# Through the store, not its files (Phase 66): every record, and every entry the last scan
# wrote, written back with the paths moved. A key is a game's own folder, never the project.
if any(moved(key) != key for key in library):
    raise RuntimeError("a record's key names the project folder; the copy cannot be moved by records")
test_sandbox.put_records({key: moved(record) for key, record in library.items()})
from data_access import catalog_io, config_io  # noqa: E402  -- the sandbox exists now
from shared.models import GameEntry  # noqa: E402

held = test_sandbox.library()  # the database since Phase 69
held.save_catalog([GameEntry.from_dict(moved(entry.to_dict())) for entry in held.load_catalog()],
                  roots=config_io.load_config().get("roots", ()))
held.close()

import logging

logging.basicConfig(level=logging.ERROR)

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

app = QApplication([])

from data_access import catalog_io
from shared import paths
from shared import rules
from logic import taskbar
from presentation import ui_actions
from presentation import ui_window

passed = failed = 0
windows = []


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"   PASS  {name}")
    else:
        failed += 1
        print(f"   FAIL  {name}   {detail}")


def settle(seconds=0.4):
    """A local event loop -- never app.exec() ended by app.quit() (the Phase 31 lesson)."""
    loop = QEventLoop()
    QTimer.singleShot(round(seconds * 1000), loop.quit)
    loop.exec()


played = []
real_play = ui_actions.play
ui_actions.play = lambda window, view: played.append(view.key)

print(f"\nsandbox data folder: {box.folder}")

try:
    print("\n=== 1. finding a picture again after the folder moved ===")
    some_art = next((SANDBOX / "cache" / "sgdb_art").glob("*.jpg"), None)
    check("there is artwork in the copy to test with", some_art is not None)
    if some_art is not None:
        old = rf"{GONE}\cache\sgdb_art\{some_art.name}"
        check("a picture from the old folder's cache is found in the current one",
              catalog_io.relocated(old) == str(some_art), catalog_io.relocated(old))
        check("forward slashes and odd case make no difference",
              catalog_io.relocated(old.replace("\\", "/").replace("cache", "Cache")) == str(some_art))
        check("a path that still exists is left alone", catalog_io.relocated(str(some_art)) == str(some_art))
    outside = r"D:\Downloads\Browser\never-existed-phase37.jpg"
    check("a picture picked from somewhere else is never redirected",
          catalog_io.relocated(outside) == outside)
    stray = rf"{GONE}\cache\sgdb_art\no-such-picture.jpg"
    check("a picture that is not in the current folder either stays as it was",
          catalog_io.relocated(stray) == stray)
    check("only the launcher's own folders are searched",
          set(rules.OWN_DATA_FOLDERS) == {"cache", rules.BACKUP_DIRNAME, rules.SAVES_BACKUP_DIRNAME})

    print("\n=== 2. the real library, as if the folder had been renamed ===")
    raw = test_sandbox.records()
    chosen = {(key, field): value for key, record in raw.items()
              for field in rules.ARTWORK_KEYS
              if isinstance(value := record.get(field), str) and value}
    from_project = {k: v for k, v in chosen.items() if v.startswith(GONE)}
    from_elsewhere = {k: v for k, v in chosen.items() if not v.startswith(GONE)}
    print(f"         ({len(from_project)} chosen pictures were in the project folder, "
          f"{len(from_elsewhere)} somewhere else)")
    check("the copy really points at a folder that is gone",
          from_project and not any(os.path.exists(v) for v in from_project.values()))

    w = ui_window.MainWindow()
    windows.append(w)
    w.resize(1500, 900)
    w.move(app.primaryScreen().availableGeometry().topLeft())
    w.show()
    settle(1.5)
    now = {(key, field): w.overrides.get(key).get(field) for key, field in from_project}
    check("every chosen picture from the project folder points at the current one",
          all(isinstance(v, str) and v.startswith(str(SANDBOX)) for v in now.values()),
          [v for v in now.values() if not str(v).startswith(str(SANDBOX))][:3])
    check("and every one of them is really there", all(os.path.isfile(v) for v in now.values()))
    check("pictures picked from elsewhere are untouched",
          all(w.overrides.get(key).get(field) == value for (key, field), value in from_elsewhere.items()))
    on_disk = test_sandbox.records()
    check("overrides.json itself says the new paths -- an export only takes art it can find",
          all(on_disk[key][field] == now[(key, field)] for key, field in from_project))
    shown = [v for v in w.views if any(k == v.key for k, _f in from_project)]
    check("each of those games draws its chosen cover or banner, not a fallback",
          all((not (v.key, "cover") in from_project or v.cover_source.startswith(str(SANDBOX)))
              and (not (v.key, "banner") in from_project or v.banner_source.startswith(str(SANDBOX)))
              for v in shown), [v.display_name for v in shown if not v.cover_source][:3])
    hints = [v.entry.icon_hint for v in w.views if v.entry.icon_hint.startswith(GONE)]
    check("the game list's own pictures are found too, before any rescan", not hints, hints[:3])
    w.close()

    second = test_sandbox.library()
    check("opening again changes nothing more", catalog_io.relocate_artwork(second) == 0)
    second.close()

    print("\n=== 3. nothing else names the folder ===")
    named = []
    read = 0
    for path in sources.python_files():  # every file of the project, packaging included
        read += 1
        text = path.read_text(encoding="utf-8")
        if "Claude New" in text and path.name not in ("catalog_io.py", "phase37_tests.py"):
            named.append(path.relative_to(HERE).as_posix())
    print(f"         (read {read} source files)")
    check("no test, build script or module carries the old folder's name", not named, named)
    # Two routes to the project folder that must agree: this test's own place, and the one
    # taskbar.py gets from paths. (Until Phase 44 taskbar.py sat in the project folder itself,
    # and its own folder stood in for the project's.)
    check("the shortcuts are made from wherever the project is",
          taskbar.SCRIPT_PATH == HERE / "launcher.py"
          and taskbar.PYTHONW_PATH == HERE / ".venv" / "Scripts" / "pythonw.exe",
          (taskbar.SCRIPT_PATH, taskbar.PYTHONW_PATH))
    check("and so is everything the launcher keeps", paths.data_dir() == SANDBOX
          or paths.data_dir().resolve() == SANDBOX.resolve())

    print("\n=== 4. the launcher's own Python works from a moved folder ===")
    probe = Path(tempfile.mkdtemp(prefix="phase37 moved venv "))
    try:
        (probe / "Scripts").mkdir()
        (probe / "Lib" / "site-packages").mkdir(parents=True)
        shutil.copy2(HERE / ".venv" / "pyvenv.cfg", probe)
        shutil.copy2(HERE / ".venv" / "Scripts" / "python.exe", probe / "Scripts")
        (probe / "Lib" / "site-packages" / "phase37_marker.py").write_text("FOUND = True\n")
        result = subprocess.run(
            [str(probe / "Scripts" / "python.exe"), "-c",
             "import sys, phase37_marker; print(sys.prefix)"],
            capture_output=True, text=True, timeout=60)
        check("it takes its new place as home and finds its packages there",
              result.returncode == 0 and Path(result.stdout.strip()).resolve() == probe.resolve(),
              (result.returncode, result.stdout, result.stderr[-300:]))
    finally:
        shutil.rmtree(probe, ignore_errors=True)
    pth_named = [p.name for p in (HERE / ".venv" / "Lib" / "site-packages").glob("*.pth")
                 if "claude new" in p.read_text(encoding="utf-8", errors="replace").casefold()]
    check("no add-on path file in it names the old folder", not pth_named, pth_named)

finally:
    ui_actions.play = real_play
    for window in windows:
        try:
            window.close()
        except RuntimeError:
            pass
    print("\n=== 5. the real library is exactly as it was found ===")
    changed = box.finish()
    check("overrides.json, config.json and catalog.json are byte for byte unchanged", not changed,
          changed)

check("nothing was started", not played, played)
print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
