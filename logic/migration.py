"""From the JSON files to the library database: building one, and checking it (Phase 67).

`build(target)` gathers everything the database is made from -- the records through the
store, the catalogue through catalog_io, the cached Steam records and name lookups through
web/ (all from disk; nothing is fetched) -- and has data_access.library_db make the
database at `target`, then checks it against what it was made from: every count, every
field of every record, every catalogue entry, read back through the store's dict shape.

No SQL here (tests/check_layers.py refuses sqlite3 outside data_access/): this module only
decides what goes in and judges what came out.

`open_library()` is how the program opens its library (Phase 69, the switch): the database
if there is one; otherwise, if overrides.json is there, the migration -- a snapshot first, the
database built in a temporary file and checked, renamed into place only if the check passes,
then overrides.json and catalog.json moved into data/migrated/<time>/, never deleted. A
check that fails changes nothing: the program runs on the JSON as before, the reason in the
log, the refused build kept beside it for a look, and the next start tries again.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from data_access import backups
from data_access import catalog_io
from data_access import library_db
from logic import steam_projection
from shared import paths
from shared import rules
from web import steam_search
from web import steam_web

log = logging.getLogger(__name__)


@dataclass
class Built:
    """A database built, what the loader said, and the check's verdict."""
    path: Path
    load: library_db.LoadReport
    verdict: library_db.Verdict
    counts: dict

    @property
    def good(self) -> bool:
        """Nothing refused, nothing different: the only state in which it may be used."""
        return not self.load.misfits and self.verdict.passed


def build(target: Path, records: dict | None = None, entries: list | None = None) -> Built:
    """Make the database at `target` from the program's own data, and check it.

    `target` is replaced if it exists. The records and entries are read here unless given.
    """
    records = catalog_io.Overrides().export_records() if records is None else records
    entries = catalog_io.load_catalog() if entries is None else entries
    cache_dir = str(paths.cache_dir())
    details = {appid: steam_web.load_details(cache_dir, appid) for appid in steam_web.stored_detail_ids(cache_dir)}
    summary = steam_web.SteamWebCache(cache_dir).records
    target = Path(target)
    target.unlink(missing_ok=True)
    conn = library_db.connect(target)
    try:
        library_db.create(conn)
        report = library_db.load(
            conn, records, entries,
            header=catalog_io.read_catalog_header(),
            steam_records={appid: record for appid, record in details.items() if record},
            steam_summary=summary,
            search_names=steam_search.NameCache(cache_dir).records,
            steam_fetched=steam_web.details_fetched_at(cache_dir, summary),
        )
        verdict = library_db.verify(conn, records, entries)
        counts = library_db.counts(conn)
    finally:
        conn.close()
    built = Built(target, report, verdict, counts)
    log.info("built %s: %d misfit(s), %d problem(s)", target, len(report.misfits), len(verdict.problems))
    return built


# -- the switch (Phase 69) -------------------------------------------------------------------

BUILDING = ".building"  # the database while it is built and checked, beside where it goes
REFUSED = ".refused"  # a build its check refused, kept for a look until the next attempt


def open_library():
    """The store the program runs on, migrating the JSON into the database first if it must."""
    database = library_db.database_path()
    records = paths.data_dir() / rules.PROTECTED_FILES[0]
    if database.is_file():
        if records.is_file():
            log.warning("%s sits beside the library database and is not read; the database is the "
                        "library since the switch", records.name)
        return _upgraded(library_db.LibraryStore(database))
    if not records.is_file():
        log.info("no library yet: starting one in %s", database)
        return library_db.LibraryStore(database)
    store = migrate()
    if isinstance(store, library_db.LibraryStore):
        _seed(store)  # a database made by the migration starts its price series at once
    return store


def _upgraded(store):
    """A database made by an older version, brought up to this one -- or left as it was (Phase 73).

    Schema evolution: a snapshot first, then every missing upgrade script in one transaction
    with the version bump. Refused, the file is exactly as it was (the transaction rolled
    back), the reason goes to the log, and the program runs on the older version -- whatever
    the new tables hold simply does not show. Upgraded, the price series is seeded from the
    Steam records already on disk.
    """
    if store.version >= library_db.SCHEMA_VERSION:
        return store
    have = store.version
    backups.snapshot(f"before-schema-{library_db.SCHEMA_VERSION}")  # skipped when the startup one holds the same
    newest = backups.list_snapshots()
    try:
        store.upgrade()
    except Exception as exc:  # noqa: BLE001 -- a refused upgrade must not stop the launcher
        log.error("the library database stays at version %d: its upgrade to %d was refused (%s); "
                  "the file is as it was", have, library_db.SCHEMA_VERSION, exc)
        return store
    log.info("the library database is at version %d now (snapshot %s first)", store.version,
             newest[0].stamp if newest else "none")
    _seed(store)
    return store


def _seed(store) -> None:
    """The price series begun from the Steam records already on disk: one observation each."""
    done = steam_projection.refresh(store)
    log.info("the price series seeded with %d observation(s) from the cached Steam records", done.observed)


def migrate():
    """Move the library from the JSON files into the database, or leave it where it is."""
    database = library_db.database_path()
    backups.snapshot("before-database")  # skipped when the startup snapshot already holds the same
    newest = backups.list_snapshots()
    protected = newest[0].stamp if newest else "none"
    building = database.with_name(database.name + BUILDING)
    refused = database.with_name(database.name + REFUSED)
    try:
        built = build(building)
    except Exception as exc:  # noqa: BLE001 -- whatever stops a migration must not stop the launcher
        log.exception("the library could not be moved into the database (%s); staying on the JSON", exc)
        building.unlink(missing_ok=True)
        return catalog_io.Overrides()
    if not built.good:
        log.error("the library stays on the JSON: the database built from it was refused -- %d record(s) "
                  "did not fit, %d difference(s): %s", len(built.load.misfits), len(built.verdict.problems),
                  "; ".join((built.load.misfits + built.verdict.problems)[:5]))
        os.replace(building, refused)
        return catalog_io.Overrides()
    os.replace(building, database)
    refused.unlink(missing_ok=True)
    moved = _set_aside()
    log.info("the library moved into %s (snapshot %s first): %s; %s set aside in %s",
             database.name, protected, ", ".join(f"{k} {v}" for k, v in built.counts.items()),
             " and ".join(p.name for p in moved) or "nothing", rules.MIGRATED_DIRNAME)
    return library_db.LibraryStore(database)


def _set_aside() -> list[Path]:
    """overrides.json and catalog.json into data/migrated/<time>/ -- moved, never deleted."""
    folder = paths.data_dir() / rules.MIGRATED_DIRNAME / datetime.now().strftime(rules.BACKUP_STAMP_FORMAT)
    moved = []
    for name in (rules.PROTECTED_FILES[0], "catalog.json"):
        source = paths.data_dir() / name
        if not source.is_file():
            continue
        try:
            folder.mkdir(parents=True, exist_ok=True)
            os.replace(source, folder / name)
            moved.append(folder / name)
        except OSError as exc:
            log.error("could not set %s aside (%s); it stays, and is not read any more", name, exc)
    return moved
