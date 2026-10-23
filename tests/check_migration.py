"""Safety net, the fourth (Phase 67): the library database, built from a copy of the real data.

    .venv\\Scripts\\python.exe tests\\check_migration.py       (from the project folder)

The migration's own test, run on every full test run until the switch (Phase 69) and
after: build the database from a throwaway copy of the real library -- its records, its
catalogue and its cached Steam records -- exactly as the migration will, then check it:

  - nothing refused: every record, entry and Steam record fitted its tables, none coerced;
  - the same number of records, sessions and session minutes, the same total play time,
    the same save folders, the same lineage, the same installs;
  - every field of every record and every catalogue entry equal when read back through the
    store's dict shape -- through LibraryStore too, opened afresh on the file;
  - no foreign key broken.

First, since Phase 101, the newest upgrade script on its own copy of the library: every old row as it was,
the columns it adds empty, the tables it makes empty, the schema a fresh database's (prove_upgrade).

Then it says what the analysis gains (names and Steam links recovered, prices not in euros)
and that the real files were left alone. Nothing here writes anywhere but the copy.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import test_sandbox

box = test_sandbox.start(migrate=False)  # the JSON as it is (Phase 69)
box.copy_cache("steam_details", "steam_web.json", "steam_search.json")  # copies, read only

import logging

logging.basicConfig(level=logging.ERROR)

from data_access import catalog_io, library_db
from logic import migration


def _schema_of(conn) -> list[tuple]:
    """sqlite_master as normalised SQL: comments and runs of white space dropped (suite 73's measure)."""
    return [(kind, name, re.sub(r"\s+", " ", re.sub(r"--[^\n]*", "", sql)).strip())
            for kind, name, sql in conn.execute("SELECT type, name, sql FROM sqlite_master WHERE sql IS NOT NULL "
                                                "ORDER BY type, name")]


def prove_upgrade(database: Path) -> bool:
    """The newest upgrade script on its own copy of the real library (Phase 101): the copy taken back to the
    version before it when the user's own start has already run it (test_sandbox.undo_upgrades), then brought
    up through library_db.upgrade -- every row of every table as it was, in the columns it had; the columns it
    adds empty (NULL, or their default); the tables it makes empty; the schema a fresh database's; no foreign
    key broken. Runs before the store opens the copy, which would upgrade it in place."""
    import sqlite3

    newest = library_db.SCHEMA_VERSION
    work = box.folder / "upgrade-check.db"
    source = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    conn = sqlite3.connect(work, autocommit=True)
    source.backup(conn)
    source.close()
    conn.execute("PRAGMA foreign_keys = ON")
    if library_db.schema_version(conn) >= newest:
        conn.execute("BEGIN")
        test_sandbox.undo_upgrades(conn, newest - 1)
        conn.execute("COMMIT")
    have = library_db.schema_version(conn)
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' "
                                         "AND name NOT LIKE 'sqlite_%' AND name != 'meta'")]
    columns = {t: [r[1] for r in conn.execute(f"PRAGMA table_info({t})")] for t in tables}
    before = {t: sorted(map(repr, conn.execute(f"SELECT {', '.join(columns[t])} FROM {t}"))) for t in tables}
    applied = library_db.upgrade(conn)
    kept = [t for t in tables if sorted(map(repr, conn.execute(f"SELECT {', '.join(columns[t])} FROM {t}"))) == before[t]]
    added, empty = [], True
    for t in tables:
        for _cid, name, _type, _notnull, default, _pk in conn.execute(f"PRAGMA table_info({t})"):
            if name not in columns[t]:
                added.append(f"{t}.{name}")
                value = "NULL" if default is None else default
                empty &= conn.execute(f"SELECT COUNT(*) FROM {t} WHERE {name} IS NOT {value}").fetchone()[0] == 0
    made = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")
            if r[0] not in tables and r[0] != "meta"]
    made_empty = all(conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] == 0 for t in made)
    fresh = sqlite3.connect(":memory:", autocommit=True)
    library_db.create(fresh)
    same_schema = _schema_of(fresh) == _schema_of(conn)
    broken = conn.execute("PRAGMA foreign_key_check").fetchall()
    at = library_db.schema_version(conn)
    conn.close()
    fresh.close()
    good = (applied == list(range(have + 1, newest + 1)) and at == newest and len(kept) == len(tables) and empty
            and made_empty and same_schema and not broken)
    print(f"   the upgrade {have} -> {newest} on a copy ({', '.join(f'{v:03d}' for v in applied) or 'nothing'}): "
          f"{len(kept)} of {len(tables)} tables with every row as it was; "
          f"added {', '.join(added) or 'no column'} -- {'empty' if empty else 'NOT EMPTY'}; "
          f"made {', '.join(made) or 'no table'} -- {'empty' if made_empty else 'NOT EMPTY'}; "
          f"the schema {'a fresh one' if same_schema else 'NOT a fresh one'}'s; foreign keys {broken or 'whole'}")
    return good


def main() -> int:
    database = box.folder / library_db.database_path().name
    upgrade_good = prove_upgrade(database) if database.is_file() else True
    if database.is_file():
        # Since the switch (Phase 69) the copy's library is a database: the net builds a fresh
        # one from what it holds, through the same loader and the same check -- a round trip.
        held = library_db.LibraryStore(database)
        records, entries = held.export_records(), held.load_catalog()
        held.close()
        print("   the library is a database: rebuilding one from what it holds")
    else:
        records = catalog_io.Overrides().export_records()
        entries = catalog_io.load_catalog()
        print("   the library is still JSON: building the database the migration would")
    built = migration.build(box.folder / "library-check.db", records, entries)
    print("   given -> in the database:")
    for name, (given, there) in built.verdict.counts.items():
        print(f"      {name:<18} {given:>8} -> {there}{'' if given == there else '   <-- differs'}")
    extra = {k: v for k, v in built.counts.items() if k not in built.verdict.counts}
    print("   and:", ", ".join(f"{k} {v}" for k, v in extra.items()))
    print(f"   refused: {built.load.misfits or 'nothing'}")
    print(f"   differences: {built.verdict.problems or 'none'}")
    print(f"   Steam values left empty rather than guessed: {built.load.notes or 'none'}")
    print(f"   names by where they came from: {dict(sorted(built.load.names.items()))}; "
          f"no name anywhere: {len(built.load.unnamed)}; store not recorded: {len(built.load.unsourced)}")
    print(f"   Steam links found again through the search cache: {len(built.load.recovered)}")
    print(f"   played, still without a Steam link: "
          f"{[(n, round(s / 3600, 1)) for n, s in built.load.unlinked_played]}")
    print(f"   prices not in euros: {built.load.not_eur or 'none'}")

    store = library_db.LibraryStore(built.path)
    try:
        same_records = store.export_records() == records
        same_entries = [e.to_dict() for e in store.load_catalog()] == [e.to_dict() for e in entries]
    finally:
        store.close()
    print(f"   opened afresh as a store: records {'the same' if same_records else 'DIFFERENT'}, "
          f"catalogue {'the same' if same_entries else 'DIFFERENT'}")

    changed = box.finish()
    print(f"   the real files: {'CHANGED ' + str(changed) if changed else 'untouched'}")
    good = built.good and same_records and same_entries and not changed and upgrade_good
    print("   the migration would go ahead" if good else "   THE MIGRATION WOULD STOP")
    return 0 if good else 1


if __name__ == "__main__":
    raise SystemExit(main())
