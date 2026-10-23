"""Phase 68: backups, the test sandbox and the installer learn the library database.

The database, step 5 of 8. The program still runs on the JSON (Phase 69 switches), but from
the day it does not, every piece that protects the user's data must already know the
database is there:

  - a snapshot holds a copy of it, made through SQLite's own backup -- never a file copy of
    a database that may be open -- and "nothing changed" is judged by what it holds, not
    by its bytes; restore puts one back through a temporary file renamed into place;
  - the test sandbox copies a real database read only and compares it by content at the
    end (check_paths proves the guard, as Phase 38 did for the files);
  - an upgrade of an installed copy steps around library.db and its journal, as it does
    around overrides.json; app.spec bundles schema.sql and the fonts.

This suite proves the first and the third on a throwaway copy of the data, with a database
built from that copy and laid where the launcher will keep it.
"""
import importlib.util
import shutil
import sys
import tempfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import test_sandbox

box = test_sandbox.start(as_json=True)  # the library as JSON, as the code before the database read it
SANDBOX = box.folder
box.copy_cache("steam_details", "steam_web.json", "steam_search.json")  # copies, read only

import logging

logging.basicConfig(level=logging.CRITICAL)

from PySide6.QtWidgets import QApplication

app = QApplication([])

from data_access import backups, catalog_io, library_db
from logic import migration
from presentation import ui_window
from shared import rules

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


def count():
    return len(backups.list_snapshots())


print("=== 1. without a database, a snapshot is what it was ===")
first = backups.snapshot("phase68")
check("the two files, and no database", first is not None and first.files == ("config.json", "overrides.json"),
      first.files if first else None)
check("and taken again with nothing changed, skipped", backups.snapshot("phase68") is None)

print("\n=== 2. with one, a snapshot holds a copy of it ===")
try:
    database = SANDBOX / rules.LIBRARY_DB_FILE
    built = migration.build(database)
    check("a database built from the copy, where the launcher will keep it", built.good and database.is_file())
    held = library_db.LibraryStore(database)  # open, as the launcher will hold it
    taken = backups.snapshot("phase68")
    check("the next snapshot takes it, beside the two files",
          taken is not None and taken.files == ("config.json", rules.LIBRARY_DB_FILE, "overrides.json"),
          taken.files if taken else None)
    copied = taken.path / rules.LIBRARY_DB_FILE
    check("a real database, holding exactly what the live one holds -- copied while open",
          library_db.file_fingerprint(copied) == library_db.file_fingerprint(database))
except Exception as exc:
    unreached("2", exc)

print("\n=== 3. unchanged is judged by what it holds ===")
try:
    before = count()
    for _ in range(20):
        backups.snapshot("startup")
    for _ in range(2):
        window = ui_window.MainWindow()  # its first act is a snapshot
        window.close()
    check("twenty snapshots and two windows later, not one more", count() == before, (before, count()))
    key = next(iter(held.export_records()))
    notes = held.get(key).get(rules.NOTES_KEY)
    bytes_before = database.read_bytes()
    held.update(key, notes="a thought, then not")
    held.update(key, notes=notes)
    check("a change made and undone leaves other bytes behind", database.read_bytes() != bytes_before)
    check("-- and still no snapshot: the library is the same", backups.snapshot("startup") is None and count() == before)
    held.update(key, notes="Written after the snapshot.")
    changed = backups.snapshot("startup")
    check("a real change is a new snapshot", changed is not None and count() == before + 1)
    check("holding the changed library", changed is not None and library_db.file_fingerprint(
        changed.path / rules.LIBRARY_DB_FILE) == library_db.file_fingerprint(database))
except Exception as exc:
    unreached("3", exc)

print("\n=== 4. putting one back ===")
try:
    held.close()  # the store is closed first: Windows will not replace an open file
    ok, message = backups.restore(taken)
    check("restored", ok, message)
    check("the library is the snapshot's again",
          library_db.file_fingerprint(database) == library_db.file_fingerprint(taken.path / rules.LIBRARY_DB_FILE))
    check("and says so, naming all three", message.startswith(
        "Restored overrides.json, config.json and library.db from"), message)
    newest = backups.list_snapshots()[0]
    check("the library it replaced was saved first",
          library_db.file_fingerprint(newest.path / rules.LIBRARY_DB_FILE) == library_db.file_fingerprint(
              changed.path / rules.LIBRARY_DB_FILE))
    reopened = library_db.LibraryStore(database)
    check("and it opens as a store, holding the snapshot's records",
          reopened.get(key).get(rules.NOTES_KEY) == notes)
    reopened.close()
    check("nothing is left beside it from the copy", not (SANDBOX / "library.db.restoring").exists())
except Exception as exc:
    unreached("4", exc)

print("\n=== 5. a JSON-only snapshot still restores the two files ===")
try:
    ok, message = backups.restore(first)
    check("restored, the database left as it was", ok and "library.db" not in message
          and message.startswith("Restored overrides.json and config.json from"), message)
except Exception as exc:
    unreached("5", exc)

print("\n=== 6. an upgrade steps around the database ===")
try:
    spec = importlib.util.spec_from_file_location("installer", PROJECT / "packaging" / "installer.py")
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    check("the keep-list names the database and its journal",
          {"library.db", "library.db-journal"} <= set(installer.USER_DATA))
    folder = Path(tempfile.mkdtemp(prefix="phase68_install_"))
    try:
        for name in ("GameLauncher.exe", "overrides.json", "config.json", "library.db", "library.db-journal",
                     "left by an old build.txt"):
            (folder / name).write_text("x", encoding="utf-8")
        (folder / "_internal").mkdir()
        (folder / "_internal" / "old.pyd").write_text("x", encoding="utf-8")
        (folder / "backups").mkdir()
        installer.clear_program_files(folder)
        left = sorted(p.name for p in folder.iterdir())
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    check("an upgrade keeps the library, its journal, the files and the folders of data",
          left == ["backups", "config.json", "library.db", "library.db-journal", "overrides.json"], left)
except Exception as exc:
    unreached("6", exc)

print("\n=== 7. the installed program carries the schema and the fonts ===")
try:
    spec_text = (PROJECT / "packaging" / "app.spec").read_text(encoding="utf-8")
    check("app.spec bundles schema.sql into data_access/",
          '"data_access", "schema.sql"), "data_access")' in spec_text)
    check("and the fonts folder into presentation/fonts/",
          '(os.path.join(PROJECT, "presentation", "fonts"), os.path.join("presentation", "fonts"))' in spec_text)
except Exception as exc:
    unreached("7", exc)

print("\n=== 8. an old snapshot in a read-only folder goes, folder and all ===")
# Added with the fix after Phase 69: most of the real data's folders carry Windows' ReadOnly
# attribute, and the rotation emptied each old snapshot and left its folder -- 18 of them.
try:
    import ctypes
    import os
    import stat

    kernel32 = ctypes.windll.kernel32

    def read_only(path: Path) -> bool:
        return bool(kernel32.GetFileAttributesW(str(path)) & 0x1)

    planted = []
    for day in range(1, rules.BACKUP_KEEP_DAILY_DAYS + 4):  # more old days than the daily tier keeps
        folder = backups.backup_dir() / f"2020-01-{day:02d}_12-00-00"
        folder.mkdir()
        held_file = folder / "overrides.json"
        held_file.write_text("{}", encoding="utf-8")
        os.chmod(held_file, stat.S_IREAD)  # the file read-only too
        kernel32.SetFileAttributesW(str(folder), 0x10 | 0x1)  # a folder, read-only
        planted.append(folder)
    keep = backups.keepers(backups.list_snapshots())
    doomed = [folder for folder in planted if folder not in keep]
    check(f"planted: {len(planted)} read-only snapshot folders, {len(doomed)} of them past both tiers",
          doomed and all(read_only(folder) for folder in planted))
    removed = backups.prune()
    check("the rotation removes every one past the tiers", set(doomed) <= set(removed),
          sorted(p.name for p in removed))
    check("folder and all -- none left behind, empty or not", not any(folder.exists() for folder in doomed),
          [folder.name for folder in doomed if folder.exists()])
    check("and every snapshot it keeps is still there, whole",
          all(path.is_dir() and any(path.iterdir()) for path in keep))
except Exception as exc:
    unreached("8", exc)

print("\n=== 9. the real library is exactly as it was found ===")
changed = box.finish()
check("overrides.json, config.json and catalog.json are byte for byte unchanged", not changed, changed)
check("and the copy is gone, read-only folders and all", not SANDBOX.exists())

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
