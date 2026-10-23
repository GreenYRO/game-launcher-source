"""A throwaway copy of the launcher's data, for tests. Import it before any project module.

Every module that touches data binds its path when it is imported -- CONFIG_PATH,
OVERRIDES_PATH, CATALOG_PATH -- so paths.data_dir has to point at the copy first, or a
test writes the user's real files. That has destroyed real data in this project three
times; this module exists so that it cannot happen a fourth.

    import test_sandbox
    box = test_sandbox.start({"allow_network": False})
    from data_access import catalog_io  # ...and everything else, only now
    ...
    box.finish()  # compares the real files byte for byte, then removes the copy

Artwork paths inside the copied overrides still point into the real cache. Those files
are only ever read.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import sys
import tempfile
import winreg
from dataclasses import dataclass, field
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]  # the project folder, one up from tests/
REAL = PROJECT / "data"  # the real data (rules.DATA_DIRNAME; check_paths proves they agree)
REAL_FILES = ("overrides.json", "config.json", "catalog.json")
REAL_DB = "library.db"  # the library database, once there is one (rules.LIBRARY_DB_FILE)

# Safe defaults for any test: nothing leaves the machine, the real pad is left alone, and
# nothing scans or watches on its own unless a test asks for it.
QUIET_CONFIG = {
    "allow_network": False,
    "enable_controller": False,
    "startup_scan": False,
    "watch_folders": False,
}

# Never carried into the copy, quiet or not. The real window's size and place describe how
# the user last left it -- maximized, on the TV -- and a test window that inherits that
# ignores the size the test asks for (Phase 32's grid could not scroll once the real
# launcher had been closed maximized). Phase 26 drops it from its own sandbox for the
# same reason. The interface sizes likewise (Phase 62): the user set 125%, and every suite
# measures the design's numbers at the default 100% (TV at 85%) -- a suite that wants
# another size asks for it.
# Since Phase 92 also the tray: the user runs with Keep running on (18 October), and a suite's window
# that hid on close, or never said its first-hide balloon, would test something it was not written
# for. A suite that wants either asks for it in start().
# Since Phase 93 also the day the watch first saw a game (`watch_games_since`): the user's first observed
# session wrote it (18 October), and a copy that carries it would never show a start writing it -- the
# bug a first run's config.json met. A copy begins as if nothing had been seen; a suite's own sessions date it.
NEVER_COPIED = ("window_geometry", "ui_scale", "tv_scale", "keep_running", "tray_hint_shown",
                "watch_games_since", "accent")
# Since Phase 99 also the accent: the suites measure the design's colours, which are Violet's; a suite that
# wants another asks for it (ui_rules.ACCENT_KEY).

# Always written into a copy, quiet or not (Phase 99): the one question as already asked. A copy has Keep
# running off (above), so every suite's window would otherwise ask it a second after appearing and stand
# on the dialog. rules.TRAY_OFFER_KEY, by name: nothing of the project's may load before start(); suite 99
# holds the two names equal, and a suite that wants the question asked removes it in start().
# "How was it?" (Phase 102) off in every copy too, by name (rules.RATE_ASK_KEY): a suite that ends a session of ten
# minutes or more would otherwise find the card holding the pad; suite 102 turns it on for itself.
ALWAYS_WRITTEN = {"tray_offer_shown": "a test copy", "ask_rating": False}
# And the version seen as this one (Phase 106, rules.VERSION_SEEN_KEY by name): a copy holds the user's, and once a
# release raises the version before his launcher has started on it, every suite's window would open What's new and
# stand on it. Read from shared/version.py as text, for the same reason; suite 106 plants an older one itself.
VERSION_SEEN = "version_seen"


def _app_version() -> str:
    text = (PROJECT / "shared" / "version.py").read_text(encoding="utf-8")
    found = re.search(r'^APP_VERSION = "([^"]+)"', text, re.MULTILINE)
    return found.group(1) if found else ""

# Start with Windows (Phase 92): every suite writes and reads a Run key of its own, named here through
# the launcher's own test variable (rules.STARTUP_TEST_KEY_ENV), and the real value is photographed:
# no test can ever touch what the user's sign-in starts.
STARTUP_TEST_KEY_ENV = "GAME_LAUNCHER_TEST_STARTUP_KEY"
# A test copy never starts a game (Phase 103: a suite's pad once started two of the user's): the launcher's own
# test variable (rules.TEST_COPY_ENV) names the copy's folder, a start asked for there is refused and written
# into it (rules.TEST_COPY_STARTS), and finish() reports it as a change -- the suite fails, saying which game.
TEST_COPY_ENV = "GAME_LAUNCHER_TEST_COPY"
TEST_COPY_STARTS = "starts_refused.txt"
TEST_KEY_ROOT = r"Software\GameLauncherTest"
REAL_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
REAL_APPROVED_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
RUN_VALUE = "Game Launcher"


def real_startup() -> tuple:
    """The user's real Run value and Windows' StartupApproved bytes for it, as they are now."""
    found = []
    for key in (REAL_RUN_KEY, REAL_APPROVED_KEY):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as handle:
                found.append(winreg.QueryValueEx(handle, RUN_VALUE)[0])
        except FileNotFoundError:
            found.append(None)
    return tuple(found)


def delete_key_tree(subkey: str) -> None:
    """Remove a test's own key and everything under it -- only ever below TEST_KEY_ROOT."""
    if not subkey.lower().startswith(TEST_KEY_ROOT.lower()):
        raise RuntimeError(f"refusing to delete {subkey}: not a test key")
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, subkey) as handle:
            children = [winreg.EnumKey(handle, i) for i in range(winreg.QueryInfoKey(handle)[0])]
    except FileNotFoundError:
        return
    for child in children:
        delete_key_tree(subkey + "\\" + child)
    winreg.DeleteKey(winreg.HKEY_CURRENT_USER, subkey)


def delete_test_root_if_empty() -> None:
    """The test root goes too, once no other suite's key is under it -- nothing left in the registry."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, TEST_KEY_ROOT) as handle:
            empty = winreg.QueryInfoKey(handle)[0] == 0 and winreg.QueryInfoKey(handle)[1] == 0
    except FileNotFoundError:
        return
    if empty:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, TEST_KEY_ROOT)


def _read_only(path: Path) -> sqlite3.Connection:
    """The real database opened so that nothing done through it can write a byte."""
    return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)


def db_fingerprint(path: Path) -> str | None:
    """What a database holds, as a digest of it written out as SQL -- None if there is none.

    Its content, not its bytes: SQLite reuses pages, so the same library can sit in other
    bytes, and the question here is whether a test changed the user's library (Phase 68).
    Computed here, not by the app's code: the guard must not depend on what it guards.
    """
    if not path.is_file():
        return None
    conn = _read_only(path)
    try:
        digest = hashlib.sha256()
        for line in conn.iterdump():
            digest.update(line.encode("utf-8") + b"\n")
        return digest.hexdigest()
    finally:
        conn.close()


@dataclass
class Sandbox:
    folder: Path
    before: dict[str, bytes] = field(default_factory=dict)
    before_db: str | None = None
    before_startup: tuple = ()
    startup_key: str = ""

    def path(self, name: str) -> Path:
        return self.folder / name

    def read_json(self, name: str) -> dict:
        return json.loads(self.path(name).read_text(encoding="utf-8"))

    def real_changes(self) -> list[str]:
        """The real files that are no longer byte for byte what they were at start() -- one
        that appeared or went among them -- and the real database, if what it holds is not."""
        changed = [name for name in REAL_FILES if _read(REAL / name) != self.before[name]]
        if db_fingerprint(REAL / REAL_DB) != self.before_db:
            changed.append(REAL_DB)
        if real_startup() != self.before_startup:
            changed.append("the Run key's Game Launcher value")
        return changed

    def copy_cache(self, *parts: str) -> None:
        """Copy parts of the real cache into the copy, for a test that needs what was fetched.

        Tests start with an empty cache, which is the right default -- nothing fetched,
        nothing to reach the network for -- but a game page with no Steam record cannot
        show its description, screenshots or updates (Phase 33). The real cache is only
        read; everything lands in the throwaway folder.
        """
        for part in parts:
            source = REAL / "cache" / part
            target = self.folder / "cache" / part
            if source.is_dir():
                shutil.copytree(source, target, dirs_exist_ok=True)
            elif source.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)

    def finish(self) -> list[str]:
        changed = self.real_changes()
        refused = self.folder / TEST_COPY_STARTS
        if refused.is_file():  # a game this copy was asked to start, and did not (Phase 103)
            names = sorted({line.split("\t")[0] for line in refused.read_text(encoding="utf-8").splitlines() if line})
            changed.append("a game start refused in the test copy: " + ", ".join(names))
        if self.startup_key:
            delete_key_tree(self.startup_key)
            delete_test_root_if_empty()
        _let_go(self.folder)
        shutil.rmtree(self.folder, onexc=_writable_and_again)
        return changed


def _read(path: Path) -> bytes | None:
    return path.read_bytes() if path.is_file() else None


def read_real(name: str) -> bytes | None:
    """One of the user's real files, as it is -- None if it is not there (since the switch,
    overrides.json and catalog.json are in data/migrated/)."""
    return _read(REAL / name)


def copy_real_db(target: Path) -> str | None:
    """Copy the user's real database, if there is one, to `target`; return what it holds.

    Through SQLite's backup from a read-only connection: the user's launcher may have it
    open, and a file copy could catch it mid-write. None when there is no database.
    """
    real_db = REAL / REAL_DB
    if not real_db.is_file():
        return None
    held = db_fingerprint(real_db)
    source, copy_to = _read_only(real_db), sqlite3.connect(target)
    try:
        source.backup(copy_to)
    finally:
        copy_to.close()
        source.close()
    return held


def _writable_and_again(func, path, exc) -> None:
    """Remove what refused to go once its ReadOnly mark is off; say so if it still refuses.

    Most of the real data's folders carry Windows' ReadOnly attribute (set from 6 to 10 October
    2026, by nothing in the launcher), copytree copies it into the copy, and Windows will not
    remove such a folder even when empty -- so every copy of the cache or the save copies was
    left in the temp folder, emptied, 235 of them by Phase 70. The path is always inside the
    copy: rmtree follows no junction.
    """
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except OSError as again:
        print(f"  (left in the temp folder: {path}: {again})")


def _let_go(folder: Path) -> None:
    """Close any store still open on a database in the copy, so the folder can be removed."""
    library_db = sys.modules.get("data_access.library_db")
    if library_db is None:
        return
    for store in list(library_db._OPEN):
        if Path(folder).resolve() in store.path.resolve().parents:
            store.close()


def start(config_changes: dict | None = None, *, quiet: bool = True, migrate: bool = True,
          as_json: bool = False) -> Sandbox:
    """A throwaway copy of the user's data, the app's data folder pointed at it.

    `migrate` (Phase 69): since the switch the launcher keeps its library in the database,
    so a copy that is still JSON -- the real folder before the user's own switch -- is moved
    into one by the launcher's own migration before the suite begins, and every suite runs
    on what the launcher runs on. A suite that needs the copy as it is asks for that.

    Since Phase 73 `migrate` also upgrades a copy whose database an older version made, through
    the launcher's own upgrade (a snapshot first, the scripts, the seeding): suites run on what
    the launcher will run on after the user's next start, as they did across the switch.

    `as_json`: the library as the code before the database read it -- overrides.json and
    catalog.json, and no database -- for the suites that compare with that code or test the
    migration itself. While the real folder was JSON that was the copy as it is; since the
    user's switch (10 October 2026) the real overrides.json and catalog.json are in
    data/migrated/, so the copy's database is written out into the two files, by the store's
    own export and the app's own writers, and removed from the copy. It holds exactly what
    the database holds -- the round trip check_migration proves.
    """
    if "data_access.catalog_io" in sys.modules or "data_access.config_io" in sys.modules:
        raise RuntimeError("test_sandbox.start() must run before any project module is imported")

    box = Sandbox(Path(tempfile.mkdtemp(prefix="launcher_test_")))
    box.before = {name: _read(REAL / name) for name in REAL_FILES}
    box.before_startup = real_startup()
    box.startup_key = rf"{TEST_KEY_ROOT}\{box.folder.name}"
    os.environ[STARTUP_TEST_KEY_ENV] = box.startup_key
    os.environ[TEST_COPY_ENV] = str(box.folder)
    for name in ("overrides.json", "catalog.json"):
        if box.before[name] is not None:
            box.path(name).write_bytes(box.before[name])
    box.before_db = copy_real_db(box.path(REAL_DB))
    config = json.loads(box.before["config.json"])
    for key in NEVER_COPIED:
        config.pop(key, None)
    config.update(ALWAYS_WRITTEN)
    config[VERSION_SEEN] = _app_version()
    if quiet:
        config.update(QUIET_CONFIG)
        config.update(_recaps_offered())
    # The suites before Phase 60 were written for the top bar's library; the side rail is
    # the default at the desk since, so they ask for the bar. Phase 60's asks for the rail.
    config["library_layout"] = "top"
    config.update(config_changes or {})
    box.path("config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")

    sys.path.insert(0, str(PROJECT))
    from shared import paths

    paths.data_dir = lambda: box.folder
    if as_json:
        if box.path(REAL_DB).is_file():
            _write_out_as_json(box, config.get("roots", ()))
    elif migrate and not box.path(REAL_DB).is_file() and box.path("overrides.json").is_file():
        from logic import migration  # only now: the data folder is the copy's

        migration.open_library().close()
        if not box.path(REAL_DB).is_file():
            raise RuntimeError("the launcher's migration refused the test copy; see the log")
    elif migrate and box.path(REAL_DB).is_file() and _version(box.path(REAL_DB)) < _current_version():
        # A database made by an older version -- the real one before the user's next start after
        # Phase 73: brought up to this version by the launcher's own upgrade, as it will be.
        from logic import migration

        store = migration.open_library()
        store.close()
        if _version(box.path(REAL_DB)) < _current_version():
            raise RuntimeError("the launcher's upgrade refused the test copy; see the log")
    return box


def _recaps_offered() -> dict:
    """The recap's offers as already shown (Phase 96): a quiet copy's window never adds a toast of its own
    to a suite's start. The month just ended, and the year the offer would be for now."""
    from datetime import datetime
    today = datetime.now()
    last = (today.year - (today.month == 1), (today.month - 2) % 12 + 1)
    year = today.year - 1 if today.month == 1 else today.year
    return {"recap_offered": f"{last[0]:04d}-{last[1]:02d}", "recap_year_offered": f"{year:04d}"}


def _version(path: Path) -> int:
    reader = _read_only(path)
    try:
        return reader.execute("PRAGMA user_version").fetchone()[0]
    finally:
        reader.close()


def _current_version() -> int:
    from data_access import library_db  # only after start() has pointed the data folder at the copy

    return library_db.SCHEMA_VERSION


def _write_out_as_json(box: Sandbox, roots) -> None:
    """The copy's database as overrides.json and catalog.json, and the database gone from it."""
    from data_access import catalog_io, library_db  # only now: the data folder is the copy's

    store = library_db.LibraryStore(box.path(REAL_DB))
    try:
        records, entries = store.export_records(), store.load_catalog()
    finally:
        store.close()
    box.path(REAL_DB).unlink()
    if not catalog_io.Overrides().import_records(records):
        raise RuntimeError("the test copy's records could not be written out as overrides.json")
    catalog_io.save_catalog(entries, roots=roots)
    if not (box.path("overrides.json").is_file() and box.path("catalog.json").is_file()):
        raise RuntimeError("the test copy could not be written out as JSON")


# -- the library as a test sees it (Phase 66; the database since Phase 69) -----------------
# A test that asks what was saved, plants records for its setup, or needs a library of its
# own does it through these, and these go through the store. So a test asserts what was
# written without knowing how it is kept: when the library moved into the database
# (Phase 69), this was the one place in tests/ that had to change. Call them only once
# start() -- or a suite's own sandbox -- has pointed the data folder at a copy.


def _library_db():
    from data_access import library_db

    return library_db


def library():
    """The library the app under test opens, without migrating -- the copy's database since
    the switch. Close it when done."""
    return _library_db().open_saved()


def _fresh(store):
    """A store opened afresh on what `store` saved."""
    from data_access import catalog_io

    if isinstance(store, catalog_io.Overrides):
        return catalog_io.Overrides(store.path)
    return _library_db().LibraryStore(store.path)


def records(store=None) -> dict[str, dict]:
    """Every record as it was saved: read back fresh, never a store's memory.

    With no store, the library the app under test uses; with one, what that store saved.
    """
    held = library() if store is None else _fresh(store)
    try:
        return held.export_records()
    finally:
        held.close()


def put_records(new: dict[str, dict], store=None) -> None:
    """Plant whole records, as a test's setup, through the store's own import: written at once.

    With no store, into the library the app under test opens; with one -- a live window's --
    into it, which is then what the window shows.
    """
    target = library() if store is None else store
    try:
        if not target.import_records(copy.deepcopy(new)):
            raise RuntimeError("the test's records could not be written")
    finally:
        if store is None:
            target.close()


def separate_store(name: str, held: dict[str, dict] | None = None, *, kind: str = "database"):
    """A library of its own beside the copy, empty unless given records.

    A database by default, as the launcher keeps one; `kind="json"` for a suite comparing
    with the code from before the database, which knows only overrides.json.
    """
    from data_access import catalog_io
    from shared import paths

    if kind == "json":
        path = paths.data_dir() / f"{name}.json"
        path.unlink(missing_ok=True)
        store = catalog_io.Overrides(path)
    else:
        path = paths.data_dir() / f"{name}.db"
        _library_db().release(path)
        path.unlink(missing_ok=True)
        store = _library_db().LibraryStore(path)
    if held:
        put_records(held, store)
    return store


def records_in(folder: Path) -> dict[str, dict]:
    """The records a library saved in another folder holds -- a snapshot, say: its database
    if it has one, else its overrides.json. Read only."""
    folder = Path(folder)
    if (folder / REAL_DB).is_file():
        conn = _read_only(folder / REAL_DB)
        try:
            return _library_db().read_records(conn)
        finally:
            conn.close()
    from data_access import catalog_io

    return catalog_io.Overrides(folder / REAL_FILES[0]).export_records()


def real_records() -> dict[str, dict]:
    """The user's real library, read and never written: for a suite's own check that it was left alone."""
    return records_in(REAL)


def real_stamp() -> float:
    """When the user's real library was last written: its database, or before the switch its JSON."""
    db = REAL / REAL_DB
    return (db if db.is_file() else REAL / REAL_FILES[0]).stat().st_mtime


# The columns a table had before a later version added one (Phase 93: session.origin; Phase 101: game's
# status_changed_at and nudged_at). A suite that compares rows across an upgrade asks for these on both
# sides, and checks the new columns on their own.
COLUMNS_BEFORE = {"session": "id, game_id, started_at, minutes, started_local, local_hour",
                  "game": "id, identity_key, source, source_id, known_as, name_origin, custom_name, custom_exe, launch_args, steam_appid, appid_source, is_tool, hidden, favorite, status, notes, is_new, first_seen, last_played, playtime_seconds, cover_path, banner_path, save_dirs_checked, carried_to, carried_at"}


def rows_in_old_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    """A table's rows, sorted, as text -- in the columns it had before any later version added one."""
    return sorted(map(repr, conn.execute(f"SELECT {COLUMNS_BEFORE.get(table, '*')} FROM {table}")))


def require_sandbox(suite: str) -> None:
    """For suites 22-25, which write the data they run on by design: refused unless tests/run_sandboxed.py has
    started a sandbox first -- the app's data folder is then a throwaway copy, never the real one (Phase 101: a
    loop of phaseNN_tests.py ran suite 23 bare on 20 October and wrote the real data, the third such slip after
    Phases 70 and 87; the rule is the code's now, not memory's)."""
    from shared import paths

    if Path(paths.data_dir()).resolve() == REAL.resolve():
        name = Path(suite).name
        raise SystemExit(f"{name} writes the data it runs on, by design, and refuses the real data: run it as\n"
                         f"    .venv\\Scripts\\python.exe tests\\run_sandboxed.py {name}")


def undo_upgrades(conn: sqlite3.Connection, to_version: int) -> list[tuple[str, str]]:
    """Take a copy's database back to `to_version` by dropping what the later upgrade scripts made
    (Phase 86): for the suites that prove an older version's upgrade on a library the user's own
    start has already taken further. Only scripts that add can be undone this way -- objects, and
    since Phase 93 a column (ALTER TABLE ... ADD COLUMN, undone by DROP COLUMN: SQLite drops a column
    with its own CHECK, and the table's text then reads as it did); one that drops or replaces
    something (004 replaces a view) is refused, and its suite puts the old object back itself. A
    copy only: a table dropped takes its rows with it, a column its values. Run inside the caller's
    transaction or none; answers what was dropped, newest first."""
    import re

    folder = PROJECT / "data_access" / "upgrades"
    dropped = []
    add_column = r"\bALTER\s+TABLE\s+(\w+)\s+ADD\s+COLUMN\s+(\w+)"
    have = conn.execute("PRAGMA user_version").fetchone()[0]
    for script in sorted(folder.glob("[0-9][0-9][0-9]_*.sql"), reverse=True):
        version = int(script.name[:3])
        if version <= to_version or version > have:
            continue  # only what this file's own upgrades made
        text = re.sub(r"--[^\n]*", "", script.read_text(encoding="utf-8"))
        columns = re.findall(add_column, text, re.I)
        if re.search(r"\b(DROP|ALTER)\b", re.sub(add_column, "", text, flags=re.I), re.I):
            raise ValueError(f"{script.name} changes what was there; it cannot be undone by dropping")
        for table, column in reversed(columns):
            conn.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
            dropped.append(("column", f"{table}.{column}"))
        made =re.findall(r"\bCREATE\s+(TABLE|VIEW|INDEX)\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)", text, re.I)
        for kind, name in reversed(made):  # the last made first: a view before the tables it reads
            conn.execute(f"DROP {kind.upper()} IF EXISTS {name}")
            dropped.append((kind.lower(), name))
    conn.execute(f"UPDATE meta SET schema_version = {int(to_version)}")
    conn.execute(f"PRAGMA user_version = {int(to_version)}")
    return dropped
