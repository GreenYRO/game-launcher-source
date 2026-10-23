"""Phase 67: the library database beside the JSON -- built, checked, and not used yet.

The database, step 4 of 8. data_access/schema.sql is the schema; data_access/library_db.py
opens and creates the database, maps a record to its rows and back, projects a cached Steam
record, loads the program's own data, checks what it built, and holds LibraryStore: the
repository on SQLite with the same operations as today's store. logic/migration.py gathers
what a database is built from. The program still runs on the JSON; Phase 69 switches.

This suite proves the schema enforces what it declares, that the Steam projection keeps
what it should and refuses to guess, and -- the point of the step -- that LibraryStore does
exactly what catalog_io.Overrides does: the same sequence of the program's own operations
(an edit, a session banked, the merge, the artwork found again, a carry-over, an export and
an import) run on both, from the same copy of the real library, leaves the same records in
memory and the same records saved. Tests may run SQL against a scratch database to probe a
constraint; the app may not (check_layers). Runs on a throwaway copy of the data.
"""
import json
import sqlite3
import subprocess
import sys
import threading
import zipfile
from datetime import datetime
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

import check_layers
import sources
from data_access import catalog_io, library_db
from logic import lineage, migration, transfer
from shared import paths, rules
from shared.models import GameEntry

passed = failed = 0
NOW = datetime(2026, 10, 10, 22, 0, 0).astimezone()


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"   PASS  {name}")
    else:
        failed += 1
        print(f"   FAIL  {name}   {detail}")


def refused(conn, sql, *args):
    try:
        conn.execute(sql, args)
    except sqlite3.IntegrityError:
        return True
    return False


print("=== 1. the schema ===")
scratch = library_db.connect(SANDBOX / "scratch.db")
library_db.create(scratch)
tables = {r[0] for r in scratch.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
views = {r[0] for r in scratch.execute("SELECT name FROM sqlite_master WHERE type = 'view'")}
# The schema as it is today: Phase 67's fourteen tables and two views, since Phase 73 (version
# 2) the price series and the purchases, with their three views, and since Phase 75 (version 3)
# Steam's own playtime -- the accounts, the read log and the series -- with its two views, and
# since Phase 83 (version 5) v_hours, the reports' view, and since Phase 86 (version 6) the wishlist and
# its read log, with its view; since Phase 101 (version 8) the price alerts' two tables and the ratings'.
expected = {"meta", "game", "install", "scan", "session", "save_folder", "lineage", "steam_app", "genre",
            "steam_app_genre", "category", "steam_app_category", "company", "steam_app_company",
            "price_snapshot", "purchase", "steam_account", "steam_read", "steam_playtime",
            "wishlist_read", "wishlist", "price_target", "price_alert", "rating"}
check(f"the {len(expected)} tables and the nine views", tables == expected and views == {
    "v_library", "v_playtime_check", "v_price_latest", "v_price_range", "v_game_money",
    "v_steam_time_latest", "v_steam_time_mine", "v_hours", "v_wishlist_now"},
      (sorted(tables ^ expected), sorted(views)))
check("every table is STRICT", all(scratch.execute(
    "SELECT strict FROM pragma_table_list WHERE name = ?", (t,)).fetchone()[0] == 1 for t in expected))
check(f"version {library_db.SCHEMA_VERSION} (2 since Phase 73, 3 since Phase 75, 4 since Phase 76, 5 since "
      "Phase 83, 6 since Phase 86, 7 since Phase 93, 8 since Phase 101), in meta and in user_version",
      library_db.SCHEMA_VERSION == 8 and library_db.schema_version(scratch) == library_db.SCHEMA_VERSION
      and scratch.execute("SELECT schema_version FROM meta").fetchone()[0] == library_db.SCHEMA_VERSION)
check("foreign keys are on for every connection the store opens",
      scratch.execute("PRAGMA foreign_keys").fetchone()[0] == 1)
plain = sqlite3.connect(SANDBOX / "scratch.db")
check("-- and off on a plain sqlite3 connection, which is why connect() turns them on",
      plain.execute("PRAGMA foreign_keys").fetchone()[0] == 0)
plain.close()

print("\n=== 2. the database refuses what it declares it will ===")
scratch.execute("BEGIN")
scratch.execute("INSERT INTO game (identity_key, name_origin, first_seen) VALUES ('c:\\games\\a', 'none', "
                "'2026-10-10T12:00:00+03:00')")
probes = [
    ("a session of a game that does not exist (foreign key)",
     "INSERT INTO session (game_id, started_at, minutes) VALUES (999, '2026-10-10T12:00:00+03:00', 5)"),
    ("a mark outside playing / finished / dropped (CHECK)",
     "UPDATE game SET status = 'paused' WHERE identity_key = 'c:\\games\\a'"),
    ("words where a whole number of seconds goes (STRICT)",
     "UPDATE game SET playtime_seconds = 'lots' WHERE identity_key = 'c:\\games\\a'"),
    ("a session start without its offset (GLOB)",
     "INSERT INTO session (game_id, started_at, minutes) VALUES (1, '2026-10-10 12:00:00', 5)"),
    ("carried somewhere, but not when (the pair CHECK)",
     "UPDATE game SET carried_to = 1 WHERE identity_key = 'c:\\games\\a'"),
    ("a Steam link without where it came from (the pair CHECK)",
     "UPDATE game SET steam_appid = 730 WHERE identity_key = 'c:\\games\\a'"),
    ("the same identity key twice (UNIQUE)",
     "INSERT INTO game (identity_key, name_origin) VALUES ('c:\\games\\a', 'none')"),
    ("a second row about the file (meta)", "INSERT INTO meta (id, schema_version, created_at) VALUES (2, 1, 'x')"),
    ("a price without its currency", "INSERT INTO steam_app (appid, has_record, price_final_cents) VALUES (1, 1, 999)"),
]
for label, sql in probes:
    check(f"refused: {label}", refused(scratch, sql))
scratch.execute("ROLLBACK")

print("\n=== 3. the Steam projection ===")
cache = str(paths.cache_dir())
from web import steam_web  # noqa: E402

stored = steam_web.stored_detail_ids(cache)
full = next(steam_web.load_details(cache, a) for a in stored
            if (r := steam_web.load_details(cache, a)).get("genres") and r.get("price_overview") and r.get("developers"))
appid = int(full["steam_appid"])
scratch.execute("BEGIN")
notes = library_db.store_steam_app(scratch, appid, full, "2026-10-01T10:00:00+00:00")
row = scratch.execute("SELECT name, app_type, price_final_cents, currency, release_text FROM steam_app WHERE appid = ?",
                      (appid,)).fetchone()
genres = {r[0] for r in scratch.execute("SELECT genre_id FROM steam_app_genre WHERE appid = ?", (appid,))}
check(f"{full['name']}: its name, type, price and release kept as Steam gave them",
      row == (full["name"], full["type"], full["price_overview"]["final"], full["price_overview"]["currency"],
              full["release_date"]["date"]), row)
check("and every genre, category and company, as rows of their own",
      genres == {int(g["id"]) for g in full["genres"]}
      and scratch.execute("SELECT COUNT(*) FROM steam_app_category WHERE appid = ?", (appid,)).fetchone()[0]
      == len({c["id"] for c in full.get("categories") or []}))
before = library_db.fingerprint(scratch)
library_db.store_steam_app(scratch, appid, full, "2026-10-01T10:00:00+00:00")
check("stored again, nothing changes", library_db.fingerprint(scratch) == before)
fewer = dict(full, genres=full["genres"][1:])
library_db.store_steam_app(scratch, appid, fewer, "2026-10-02T10:00:00+00:00")
check("a newer record with a genre fewer replaces the old rows",
      {r[0] for r in scratch.execute("SELECT genre_id FROM steam_app_genre WHERE appid = ?", (appid,))}
      == {int(g["id"]) for g in fewer["genres"]})
odd = dict(full, required_age="18+", release_date={"date": "Coming soon", "coming_soon": True})
notes = library_db.store_steam_app(scratch, appid, odd, None)
row = scratch.execute("SELECT required_age, release_date, release_text FROM steam_app WHERE appid = ?", (appid,)).fetchone()
check("an age that is not a number and a date that is not a date are left empty, and said so",
      row == (None, None, "Coming soon") and len(notes) == 2, (row, notes))
zloty = dict(full, price_overview=dict(full["price_overview"], currency="PLN", final=22999))
library_db.store_steam_app(scratch, appid, zloty, None)
check("a price in zloty stays in zloty -- never converted",
      scratch.execute("SELECT price_final_cents, currency FROM steam_app WHERE appid = ?", (appid,)).fetchone()
      == (22999, "PLN"))
scratch.execute("ROLLBACK")
scratch.close()

print("\n=== 4. the database store does what today's store does ===")
records = test_sandbox.records()
entries = catalog_io.load_catalog()
built = migration.build(SANDBOX / "library.db", records, entries)
check("built from the copy: nothing refused, nothing different", built.good,
      (built.load.misfits[:3], built.verdict.problems[:3]))
A = test_sandbox.separate_store("json side", records, kind="json")
B = library_db.LibraryStore(built.path)


def same(label):
    """Both stores hold the same in memory, and the same was saved by each."""
    fresh = library_db.LibraryStore(B.path)
    try:
        saved = fresh.export_records()
    finally:
        fresh.close()
    in_memory = A.export_records() == B.export_records()
    on_disk = test_sandbox.records(A) == saved
    check(f"{label}: the same records, in memory and saved", in_memory and on_disk,
          (in_memory, on_disk, sorted(k for k in set(saved) | set(test_sandbox.records(A))
                                      if saved.get(k) != test_sandbox.records(A).get(k))[:3]))


same("opened")
timed = next(k for k, r in records.items() if r.get(rules.SESSIONS_KEY))
plain_key = next(k for k, r in records.items() if not r.get("favorite") and not r.get(rules.NOTES_KEY))
for store in (A, B):
    store.update(plain_key, notes="Halfway through act 2.", favorite=True)
    store.update(plain_key, favorite=None)
same("a note written, a star given and taken back")
session = sorted(records[timed][rules.SESSIONS_KEY], key=lambda s: s["start"]) + \
    [{"start": "2026-10-10T21:00:00+03:00", "minutes": 42}]
for store in (A, B):
    store.update(timed, playtime_seconds=int(records[timed].get("playtime_seconds") or 0) + 2520,
                 last_played="2026-10-10T21:42:00+03:00", sessions=session)
same("a session banked, its minutes and the total with it")
with_saves = [k for k, r in records.items() if r.get(rules.SAVE_DIRS_KEY)][:2]
for store in (A, B):
    store.update_many({with_saves[0]: {rules.SAVE_DIRS_KEY: None, rules.SAVE_DIRS_CHECKED_KEY: None},
                       with_saves[1]: {rules.SAVE_DIRS_KEY: records[with_saves[1]][rules.SAVE_DIRS_KEY]
                                       + [r"C:\Users\someone\Saved Games\Another"]}})
same("two games' save folders changed in one write")
check("values_of and uncarried answer alike",
      A.values_of("cover") == B.values_of("cover")
      and [k for k, _r in A.uncarried()] == [k for k, _r in B.uncarried()])
check("and the database store hands out the same live dict each time, as the views need",
      B.get(timed) is B.get(timed) and B.get(timed)["playtime_seconds"] == A.get(timed)["playtime_seconds"])


class Fixed(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW if tz is None else NOW.astimezone(tz)


newcomer = GameEntry(source="folders", source_id=r"C:\games\Phase 67 Newcomer\game.exe",
                     display_name="Phase 67 Newcomer", install_dir=r"C:\games\Phase 67 Newcomer",
                     launch_kind="exe", launch_target=r"C:\games\Phase 67 Newcomer\game.exe",
                     working_dir=r"C:\games\Phase 67 Newcomer", icon_hint="", size_on_disk=1, detection="heuristic")
real_datetime = catalog_io.datetime
catalog_io.datetime = Fixed
try:
    shown = {name: catalog_io.merge(entries + [newcomer], store) for name, store in (("A", A), ("B", B))}
finally:
    catalog_io.datetime = real_datetime
same("the merge: a new game stamped and tagged NEW, names kept current")
check("and the views it hands back read the same", [v.data for v in shown["A"]] == [v.data for v in shown["B"]]
      and next(v for v in shown["B"] if v.key == newcomer.identity_key).is_new)

(SANDBOX / "cache").mkdir(exist_ok=True)
(SANDBOX / "cache" / "phase67-moved.jpg").write_bytes(b"not really a picture")
gone = r"C:\Users\nobody\An Old Project Folder\data\cache\phase67-moved.jpg"
for store in (A, B):
    store.update(plain_key, cover=gone)
moved = (catalog_io.relocate_artwork(A), catalog_io.relocate_artwork(B))
same(f"a chosen cover found again after a move ({moved[0]} and {moved[1]} moved)")

by_key = {v.key: v for v in shown["A"]}
pair = next(((v, e) for v in shown["A"] for e in lineage.everything(v, A, by_key.keys()) if e.why), None)
if pair is None:
    pair = next((v, e) for v in shown["A"] for e in lineage.everything(v, A, by_key.keys()))
view, earlier = pair
said = []
for store in (A, B):
    carried = lineage.carry_over(store, earlier.key, view.key, new_install_dir=view.entry.install_dir, now=NOW)
    said.append(carried)
same(f"a history carried over, {earlier.name} onto {view.display_name}")
check("with the same account of what moved", said[0] == said[1], said)
errors = []
for store in (A, B):
    try:
        lineage.carry_over(store, earlier.key, view.key, now=NOW)
    except ValueError as exc:
        errors.append(str(exc))
check("and carrying it twice is refused alike", len(errors) == 2 and errors[0] == errors[1], errors)

bundles = {}
for name, store in (("A", A), ("B", B)):
    bundles[name] = SANDBOX / f"bundle-{name}.zip"
    transfer.export_bundle(bundles[name], include_key=False, now=NOW, store=store)
with zipfile.ZipFile(bundles["A"]) as a, zipfile.ZipFile(bundles["B"]) as b:
    names_a, names_b = sorted(a.namelist()), sorted(b.namelist())
    same_bundle = names_a == names_b and all(
        (json.loads(a.read(n)) == json.loads(b.read(n))) if n.endswith(".json") else a.read(n) == b.read(n)
        for n in names_a)
check(f"an export from either holds the same {len(names_a)} members", same_bundle)
for store in (A, B):
    transfer.import_bundle(bundles["A"], set(by_key), store=store)
same("an import of that bundle")

print("\n=== 5. a write the database refuses ===")
mark = library_db.fingerprint(B._conn)
held = B.export_records()
ok = B.import_records({plain_key: {"first_seen": "2026-10-10T12:00:00+03:00", rules.STATUS_KEY: "paused"}})
check("answers False", ok is False)
check("and the database and the records in memory are as they were",
      library_db.fingerprint(B._conn) == mark and B.export_records() == held)
ok = B.update(timed, sessions=[{"start": "yesterday", "minutes": 5}])
check("a session start it cannot keep is refused the same way, nothing half written",
      ok is False and library_db.fingerprint(B._conn) == mark and B.export_records() == held)

print("\n=== 6. the catalogue ===")
B.save_catalog(entries, roots=("C:\\games",), trigger="manual", started_at=NOW.isoformat(timespec="seconds"))
check(f"the {len(entries)} entries come back as written, in the order the scan found them",
      [e.to_dict() for e in B.load_catalog()] == [e.to_dict() for e in catalog_io.load_catalog()])
check("and the last scan's time is the scan's own", B.last_scan_time() is not None
      and abs((datetime.now().astimezone() - B.last_scan_time()).total_seconds()) < 120)
probe = library_db.connect(B.path)
linked = [r[0] for r in probe.execute("SELECT identity_key FROM game WHERE steam_appid IS NOT NULL")]
B.save_catalog([e for e in entries if e.identity_key not in linked[:1]], roots=(), trigger="manual")
kept = probe.execute("SELECT steam_appid IS NOT NULL FROM game WHERE identity_key = ?", (linked[0],)).fetchone()[0]
installed = probe.execute("SELECT COUNT(*) FROM install i JOIN game g ON g.id = i.game_id WHERE g.identity_key = ?",
                          (linked[0],)).fetchone()[0]
probe.close()
check("a game a later scan does not find is no longer installed, and keeps its Steam link",
      installed == 0 and kept == 1, (installed, kept))
fresh_entry = GameEntry(source="folders", source_id=r"C:\games\Found Just Now\run.exe", display_name="Found Just Now",
                        install_dir=r"C:\games\Found Just Now", launch_kind="exe",
                        launch_target=r"C:\games\Found Just Now\run.exe", working_dir=r"C:\games\Found Just Now",
                        icon_hint="", size_on_disk=1, detection="heuristic")
B.save_catalog(entries + [fresh_entry], trigger="watch")
check("a game a scan has just found has no record until the merge stamps it",
      B.get(fresh_entry.identity_key) == {} and fresh_entry.identity_key not in B.export_records())
catalog_io.merge(entries + [fresh_entry], B)
check("-- then it has one", B.get(fresh_entry.identity_key).get("first_seen") is not None)

print("\n=== 7. one thread writes ===")
caught = []


def from_another_thread():
    try:
        library_db.read_records(B._conn)
    except sqlite3.ProgrammingError as exc:
        caught.append(str(exc))


worker = threading.Thread(target=from_another_thread)
worker.start()
worker.join()
check("the store's connection refuses to be used from another thread", caught and "thread" in caught[0], caught)
B.close()

print("\n=== 8. beside the JSON, not used by the program yet ===")
import ast  # noqa: E402

users, stores = {}, set()
for path in sources.python_files():
    rel = path.relative_to(PROJECT)
    if rel.parts[0] in ("tests", "docs", "packaging"):
        continue
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
        named = []
        if isinstance(node, ast.Import):
            named = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            named = [f"{node.module}.{a.name}" for a in node.names] + [node.module]
        for target in named:
            if target in ("data_access.library_db", "logic.migration"):
                users.setdefault(target, set()).add(rel.as_posix())
        if (isinstance(node, ast.Attribute) and node.attr == "LibraryStore") or                 (isinstance(node, ast.Name) and node.id == "LibraryStore"):
            stores.add(rel.as_posix())
# Since Phase 68 backups.py copies, compares and puts back database files with it; since
# the switch (Phase 69) the window opens its library through migration.open_library, and
# transfer opens the library as saved when no window hands it a store.
check("the database module is used by the migration, the backups and transfer -- and the migration by the window",
      users == {"data_access.library_db": {"logic/migration.py", "data_access/backups.py", "logic/transfer.py"},
                "logic.migration": {"presentation/ui_window.py"}}, users)
check("and a LibraryStore is opened only by the migration, never by the window itself",
      stores <= {"data_access/library_db.py", "logic/migration.py"}, stores)
check("the layer net refuses sqlite3 in presentation/ or logic/, and only there",
      check_layers.sql_outside("presentation/x.py", "presentation", "import sqlite3\n")
      and check_layers.sql_outside("logic/x.py", "logic", "from sqlite3 import connect\n")
      and not check_layers.sql_outside("data_access/x.py", "data_access", "import sqlite3\n"))
ignored = [subprocess.run(["git", "check-ignore", "-q", name], cwd=PROJECT).returncode
           for name in ("data/library.db", "data/library.db-journal")]
check("data/library.db and its journal are never committed", ignored == [0, 0], ignored)

print("\n=== 9. the real library is exactly as it was found ===")
changed = box.finish()
check("overrides.json, config.json and catalog.json are byte for byte unchanged", not changed, changed)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
