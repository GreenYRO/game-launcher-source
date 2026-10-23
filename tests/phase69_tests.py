"""Phase 69: the switch -- the launcher moves its library into the database and runs on it.

The database, step 6 of 8. At startup `migration.open_library()` opens data/library.db; if
there is none and overrides.json is there, it migrates: a snapshot, the database built in a
temporary file and checked field by field, renamed into place only if the check passes,
overrides.json and catalog.json moved into data/migrated/<time>/ -- never deleted. A check
that fails changes nothing; the launcher runs on the JSON as before.

This suite does all of that to a throwaway copy of the real library, as the launcher will do
it to the real one when the user starts it: the migration, a second start that does nothing,
a migration refused (in a second process, on a copy of its own), the window on the database
-- an edit saved, a scan from the folder watch written by the GUI thread -- and the two
restores: a snapshot of the database, and one from before the switch, which the launcher
rebuilds the database from.
"""
import json
import logging
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import test_sandbox

box = test_sandbox.start(as_json=True)  # the library as JSON: this suite migrates it
SANDBOX = box.folder
box.copy_cache("steam_details", "steam_web.json", "steam_search.json")  # copies, read only

lines: list[str] = []


class Keep(logging.Handler):
    def emit(self, record):
        lines.append(record.getMessage())


logging.basicConfig(level=logging.CRITICAL)
logging.getLogger().addHandler(Keep(level=logging.INFO))
logging.getLogger().setLevel(logging.INFO)

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

app = QApplication([])

from data_access import backups, catalog_io, library_db
from logic import migration, storage
from presentation import ui_actions, ui_window
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


def settle(seconds):
    loop = QEventLoop()
    QTimer.singleShot(round(seconds * 1000), loop.quit)
    loop.exec()


def newest_scan():
    reader = sqlite3.connect(f"{(SANDBOX / rules.LIBRARY_DB_FILE).resolve().as_uri()}?mode=ro", uri=True)
    try:
        return reader.execute("SELECT trigger, started_at, finished_at, entry_count FROM scan "
                              "ORDER BY id DESC LIMIT 1").fetchone()
    finally:
        reader.close()


print("=== 1. the migration, on a copy of the real library ===")
json_bytes = {name: (SANDBOX / name).read_bytes() for name in ("overrides.json", "catalog.json")}
json_records = catalog_io.Overrides().export_records()
json_entries = [e.to_dict() for e in catalog_io.load_catalog()]
snapshots_before = len(backups.list_snapshots())
store = migration.open_library()
database = SANDBOX / rules.LIBRARY_DB_FILE
check("the library opens as the database", isinstance(store, library_db.LibraryStore) and database.is_file())
moved = sorted((SANDBOX / rules.MIGRATED_DIRNAME).iterdir())
check("overrides.json and catalog.json are moved into data/migrated/<time>/, byte for byte",
      len(moved) == 1 and all((moved[0] / n).read_bytes() == b for n, b in json_bytes.items()), moved)
check("and neither is left in the data folder", not any((SANDBOX / n).exists() for n in json_bytes))
check("nothing half made is left beside it",
      not (SANDBOX / "library.db.building").exists() and not (SANDBOX / "library.db.refused").exists())
check(f"the {len(json_records)} records come back from the database as they were",
      store.export_records() == json_records)
check(f"and the {len(json_entries)} catalogue entries, in their order",
      [e.to_dict() for e in store.load_catalog()] == json_entries)
snaps = backups.list_snapshots()
check("a snapshot holds the JSON from just before",
      len(snaps) == snapshots_before + 1 and (snaps[0].path / "overrides.json").read_bytes() == json_bytes["overrides.json"])
said = next((line for line in lines if line.startswith("the library moved into")), "")
check("the log says what moved, and which snapshot protects it", "snapshot" in said and "records 66" in said
      or ("snapshot" in said and "records" in said), said[:200])
store.close()
json_snapshot = snaps[0]

print("\n=== 2. a second start does nothing ===")
mark = library_db.file_fingerprint(database)
again = migration.open_library()
check("the database opens, nothing moved, no snapshot taken",
      isinstance(again, library_db.LibraryStore) and len(list((SANDBOX / rules.MIGRATED_DIRNAME).iterdir())) == 1
      and len(backups.list_snapshots()) == len(snaps))
again.close()
check("and the library is what it was", library_db.file_fingerprint(database) == mark)
(SANDBOX / "overrides.json").write_text('{"version": 1, "games": {}}\n', encoding="utf-8")
lines.clear()
beside = migration.open_library()
check("an overrides.json that turns up beside the database is not read, and the log says so",
      isinstance(beside, library_db.LibraryStore) and beside.export_records() == json_records
      and any("is not read" in line for line in lines))
beside.close()
(SANDBOX / "overrides.json").unlink()

print("\n=== 3. a migration whose check fails changes nothing (a second process, a copy of its own) ===")
child = SANDBOX / "refused_child.py"
child.write_text(f'''import json, sys, logging
sys.path[:0] = [{str(PROJECT)!r}, {str(PROJECT / "tests")!r}]
import test_sandbox
box = test_sandbox.start(as_json=True)
lines = []
class Keep(logging.Handler):
    def emit(self, record):
        lines.append(record.getMessage())
logging.getLogger().addHandler(Keep(level=logging.INFO)); logging.getLogger().setLevel(logging.INFO)
records = box.path("overrides.json")
data = json.loads(records.read_text(encoding="utf-8"))
key = next(iter(data["games"]))
data["games"][key]["status"] = "paused"  # a mark outside the three: the database refuses it
records.write_text(json.dumps(data, indent=2), encoding="utf-8")
before = records.read_bytes()
from data_access import catalog_io, library_db
from logic import migration
first = migration.open_library()
second = migration.open_library()
result = {{
    "json store": isinstance(first, catalog_io.Overrides) and isinstance(second, catalog_io.Overrides),
    "no database": not box.path("library.db").exists(),
    "json untouched": records.read_bytes() == before and box.path("catalog.json").is_file(),
    "refused kept": box.path("library.db.refused").is_file(),
    "said why": any("stays on the JSON" in line and key in line and "CHECK constraint failed" in line
                    for line in lines),
    "tried twice": sum("stays on the JSON" in line for line in lines) == 2,
    "records": first.export_records() == json.loads(before)["games"],
    "real untouched": not box.finish(),
}}
print("RESULT" + json.dumps(result))
''', encoding="utf-8")
run = subprocess.run([sys.executable, str(child)], capture_output=True, text=True, timeout=300)
found = next((json.loads(line[6:]) for line in run.stdout.splitlines() if line.startswith("RESULT")), None)
if found is None:
    check("the second process reported", False, (run.stdout[-500:], run.stderr[-800:]))
else:
    check("refused: the launcher stays on the JSON, the next start tries again and is refused again",
          found["json store"] and found["tried twice"], found)
    check("no database made, overrides.json and catalog.json exactly as they were",
          found["no database"] and found["json untouched"], found)
    check("the refused build is kept for a look, and the log names the reason",
          found["refused kept"] and found["said why"], found)
    check("and the JSON store holds the records as they are", found["records"] and found["real untouched"], found)

print("\n=== 4. the window on the database ===")
w = ui_window.MainWindow()
w.show()
settle(1.0)
check("the window opens its library as the database", isinstance(w.overrides, library_db.LibraryStore))
check("and shows the library", len(w.views) == len(w.entries) > 0, (len(w.views), len(w.entries)))
plain = next(v for v in w.views if not v.favorite and not v.hidden)
ui_actions.toggle_favorite(w, plain)
check("a star given in the window is saved in the database",
      test_sandbox.records().get(plain.key, {}).get("favorite") is True)
ui_actions.toggle_favorite(w, w.by_key[plain.key])
check("and taken back", "favorite" not in test_sandbox.records().get(plain.key, {}))

writers = []
real_write = library_db.write_catalog


def watched(conn, entries, **kwargs):
    writers.append(threading.get_ident())
    return real_write(conn, entries, **kwargs)


library_db.write_catalog = watched
try:
    before_scan = newest_scan()
    started = w.start_scan(background=True)  # what the folder watch asks for
    deadline = time.monotonic() + 120
    while (w.worker is not None and w.worker.isRunning() or not writers) and time.monotonic() < deadline:
        settle(0.2)
    settle(0.5)
finally:
    library_db.write_catalog = real_write
after_scan = newest_scan()
check("a scan the folder watch asked for runs", started and writers, (started, writers))
check("and its findings are written by the GUI thread -- the one writer",
      writers and set(writers) == {threading.main_thread().ident}, writers)
check("its row says who asked and when it began", after_scan[0] == "watch" and after_scan[1] is not None
      and after_scan != before_scan, after_scan)
check("Storage's 'sizes as of' is that scan's time",
      storage.gather(w.views, w.overrides).scanned_at == w.overrides.last_scan_time() is not None
      or storage.gather(w.views, w.overrides).scanned_at == w.overrides.last_scan_time())
check("and nothing was written from another thread", not any("thread" in line and "ProgrammingError" in line
                                                             for line in lines))

print("\n=== 5. restoring a snapshot of the database, the window's store open ===")
w.overrides.update(plain.key, notes="Before the snapshot.")
snap = backups.snapshot("phase69")
w.overrides.update(plain.key, notes="After the snapshot.")
ok, message = backups.restore(snap)
check("restored while the window held the database open", ok, message)
w.reload_after_restore(message)
settle(0.5)
check("the window reads the snapshot's library", w.overrides.get(plain.key).get(rules.NOTES_KEY) == "Before the snapshot.")

print("\n=== 6. restoring a snapshot from before the switch ===")
# What the database knows is installed just before the restore: the scan in section 4, over
# the real disk. It is what a restore writes back out as catalog.json, by design (Phase 68),
# so it -- not the copy's own older catalogue -- is what the rebuilt library must know. On
# 11 October they differed: a new Witcher 3 build was being copied in while the user's
# launcher scanned (33 games), and finished by the time this suite scanned (34).
installed_before = [e.identity_key for e in w.overrides.load_catalog()]
ok, message = backups.restore(json_snapshot)
check("restored, and it says the library will be built again", ok and "built again" in message, message)
replaced = [p for p in (SANDBOX / rules.MIGRATED_DIRNAME).iterdir() if p.name.endswith("-replaced")]
check("the database it replaced is set aside, not deleted",
      len(replaced) == 1 and (replaced[0] / rules.LIBRARY_DB_FILE).is_file())
w.reload_after_restore(message)
settle(0.5)
rebuilt = w.overrides.export_records()
arrived = {key: record for key, record in rebuilt.items() if key not in json_records}
check("the window rebuilt its library from the snapshot -- through the migration and its check",
      isinstance(w.overrides, library_db.LibraryStore)
      and {key: rebuilt.get(key) for key in json_records} == json_records,
      [key for key in json_records if rebuilt.get(key) != json_records[key]][:3])
check(f"anything more is a game the scan found that the snapshot never knew ({len(arrived)}), "
      "carrying only what the merge stamps on a newcomer",
      all(key in installed_before and set(record) <= {"first_seen", rules.NEW_KEY, "known_as"}
          for key, record in arrived.items()), arrived)
check("and still knows which games are installed -- the ones the last scan found",
      [e.identity_key for e in w.entries] == installed_before, (len(w.entries), len(installed_before)))
w.close()

print("\n=== 7. the real library is exactly as it was found ===")
changed = box.finish()
check("overrides.json, config.json and catalog.json are byte for byte unchanged, the database too", not changed, changed)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
