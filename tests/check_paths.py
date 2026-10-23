"""Safety net: the paths that fail quietly when files move.

    .venv\\Scripts\\python.exe tests\\check_paths.py       (from the project folder)

A wrong import name stops the program at once. A wrong *path* does not: paths.py one
folder off makes the launcher start as if for the first time, with none of the user's
playtime or artwork, and the test sandbox one folder off guards the wrong files. Each
check here proves one such path points where it should, using nothing but reads -- the
real data is never written.

1. The program finds itself: the folder paths.py calls home holds launcher.py, the icon,
   and the user's real overrides.json; the shortcuts' targets (taskbar.py) all exist.
2. The sandbox watches the real files: test_sandbox.REAL is that same folder.
3. Its byte-for-byte check works: a change planted in a throwaway copy is reported.
4. It patches the paths module the app really uses: once started, the data modules point
   into the sandbox -- which a second copy of paths, loaded under another name, would not.
5. Its guard fires: start() refuses when a data module was imported first (checked in a
   separate process, since the guard is about a fresh start).
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

import sources

ROOT = sources.ROOT
sys.path.insert(0, str(ROOT))

import test_sandbox  # noqa: E402

passed = failed = 0


def check(name: str, condition, detail="") -> None:
    global passed, failed
    if condition:
        passed += 1
        print(f"   PASS  {name}")
    else:
        failed += 1
        print(f"   FAIL  {name}   {detail}")


# Module names as the app imports them today. A move changes these lines, and the checks
# that follow fail if they are not changed with it.
DATA_MODULES = ("data_access.catalog_io", "data_access.config_io")

print("=== 1. the program finds itself ===")
from shared import paths  # noqa: E402
from logic import taskbar  # noqa: E402

check("paths.program_dir() is the project folder", paths.program_dir() == ROOT, paths.program_dir())
check("launcher.py is there", (paths.program_dir() / "launcher.py").is_file())
check("so is the icon", (paths.resource_dir() / "launcher.ico").is_file(), paths.resource_dir())
overrides = paths.data_dir() / "overrides.json"
database = paths.data_dir() / test_sandbox.REAL_DB
if database.is_file():  # since the switch (Phase 69): counted read only, no app module loaded
    reader = sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True)
    try:
        games = [row[0] for row in reader.execute("SELECT identity_key FROM game WHERE first_seen IS NOT NULL")]
    finally:
        reader.close()
else:
    games = json.loads(overrides.read_text(encoding="utf-8")).get("games", {}) if overrides.is_file() else {}
check("the data folder holds the real library", len(games) > 0, paths.data_dir())
print(f"         ({len(games)} records in it, {'in library.db' if database.is_file() else 'in overrides.json'})")
check("the shortcuts would start this launcher.py", taskbar.SCRIPT_PATH == ROOT / "launcher.py",
      taskbar.SCRIPT_PATH)
check("with this project's pythonw.exe", taskbar.PYTHONW_PATH.is_file(), taskbar.PYTHONW_PATH)
check("and this icon", taskbar.ICON_PATH.is_file(), taskbar.ICON_PATH)

print("\n=== 2. the sandbox watches the real files ===")
check("test_sandbox.REAL is the data folder", test_sandbox.REAL == ROOT / "data", test_sandbox.REAL)
check("and the folder the launcher keeps its data in", test_sandbox.REAL == paths.data_dir(),
      (test_sandbox.REAL, paths.data_dir()))

def plant_stand_ins(folder: Path) -> None:
    """The real files copied into a folder that plays them -- or, for one that is no longer
    there, a small file in its place: since the switch (Phase 69) overrides.json and
    catalog.json live in data/migrated/, and these sections only need files to watch."""
    for name in test_sandbox.REAL_FILES:
        if (test_sandbox.REAL / name).is_file():
            shutil.copy2(test_sandbox.REAL / name, folder / name)
        else:
            (folder / name).write_text('{"version": 1, "games": {}}\n', encoding="utf-8")


print("\n=== 3. its byte-for-byte check catches a change ===")
stand_in = Path(tempfile.mkdtemp(prefix="check_paths_real_"))
try:
    plant_stand_ins(stand_in)
    real = test_sandbox.REAL
    test_sandbox.REAL = stand_in  # only for this section: the copy plays the real files
    try:
        box = test_sandbox.start(migrate=False)
        with open(stand_in / "overrides.json", "ab") as handle:
            handle.write(b" ")  # what a test writing the "real" file would do
        changed = box.finish()
    finally:
        test_sandbox.REAL = real
    check("a planted change to overrides.json is reported", changed == ["overrides.json"], changed)
finally:
    shutil.rmtree(stand_in, ignore_errors=True)

print("\n=== 3b. and the library database, by what it holds (Phase 68) ===")
stand_in = Path(tempfile.mkdtemp(prefix="check_paths_real_"))
try:
    plant_stand_ins(stand_in)
    db = stand_in / test_sandbox.REAL_DB
    planted = sqlite3.connect(db)
    planted.execute("CREATE TABLE game (identity_key TEXT)")
    planted.execute("INSERT INTO game VALUES ('c:\\games\\a')")
    planted.commit()
    planted.close()
    real = test_sandbox.REAL
    test_sandbox.REAL = stand_in  # only for this section: the copy plays the real library
    try:
        box = test_sandbox.start(migrate=False)
        copied = test_sandbox.db_fingerprint(box.path(test_sandbox.REAL_DB)) == test_sandbox.db_fingerprint(db)
        bytes_before = db.read_bytes()
        rewrite = sqlite3.connect(db)
        rewrite.execute("INSERT INTO game VALUES ('c:\\games\\b')")
        rewrite.execute("DELETE FROM game WHERE identity_key = 'c:\\games\\b'")
        rewrite.commit()
        rewrite.close()
        same_content = box.real_changes()
        other_bytes = db.read_bytes() != bytes_before
        changed_by_a_test = sqlite3.connect(db)
        changed_by_a_test.execute("INSERT INTO game VALUES ('c:\\games\\written by a test')")
        changed_by_a_test.commit()
        changed_by_a_test.close()
        changed = box.finish()
    finally:
        test_sandbox.REAL = real
    check("a real database is copied into the sandbox as it is", copied)
    check("a write that leaves other bytes but the same content is no alarm",
          other_bytes and same_content == [], (other_bytes, same_content))
    check("a planted change to what it holds is reported", changed == [test_sandbox.REAL_DB], changed)
finally:
    shutil.rmtree(stand_in, ignore_errors=True)

print("\n=== 4. it patches the paths the app really uses ===")
box = test_sandbox.start(migrate=False)
try:
    import importlib

    modules = [importlib.import_module(name) for name in DATA_MODULES]
    catalog_io, config_io = modules
    inside = lambda p: Path(p).resolve().is_relative_to(Path(box.folder).resolve())  # noqa: E731
    check("overrides.json is read from the sandbox", inside(catalog_io.OVERRIDES_PATH), catalog_io.OVERRIDES_PATH)
    check("catalog.json too", inside(catalog_io.CATALOG_PATH), catalog_io.CATALOG_PATH)
    check("config.json too", inside(config_io.CONFIG_PATH), config_io.CONFIG_PATH)
    loaded_paths = [m for m in sys.modules.values()
                    if getattr(m, "__file__", None) and Path(m.__file__).name == "paths.py"]
    check("exactly one paths module is loaded", len(loaded_paths) == 1, [m.__name__ for m in loaded_paths])
finally:
    changed = box.finish()
check("and the real files are untouched", not changed, changed)

print("\n=== 5. its guard fires ===")
probe = (
    "import sys, importlib; sys.path[:0] = [sys.argv[1], sys.argv[2]]; "
    "importlib.import_module(sys.argv[3]); import test_sandbox\n"
    "try:\n    test_sandbox.start()\nexcept RuntimeError:\n    print('REFUSED')\n"
    "else:\n    print('STARTED')"
)
for name in DATA_MODULES:
    result = subprocess.run([sys.executable, "-c", probe, str(ROOT), str(ROOT / "tests"), name],
                            capture_output=True, text=True, timeout=120)
    check(f"start() refuses after {name} was imported first", "REFUSED" in result.stdout,
          (result.stdout.strip(), result.stderr[-300:]))

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
