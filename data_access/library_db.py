"""The library database (Phase 67): SQLite through the standard library, beside the JSON.

What lives here, and nowhere else -- tests/check_layers.py refuses sqlite3 outside
data_access/, so every SQL statement of the launcher is in this package:

  - opening a database file, and creating one from schema.sql;
  - the mapping between a record -- the dict per game overrides.json has always held --
    and the rows that keep it, written once, in both directions;
  - LibraryStore: the repository on SQLite, with the same operations as
    catalog_io.Overrides (get, update, values_of, uncarried, update_many, carry,
    export_records, import_records) and the catalogue's own (save_catalog,
    load_catalog, last_scan_time);
  - the Steam projection: one cached appdetails record into steam_app and its
    satellites -- the same code for a migrated record and, from Phase 70, for every
    record a scan has fetched since (LibraryStore.store_steam_records);
  - the loader that builds a database from the program's own data, and the check that
    compares what it built with what it was given, field by field;
  - schema evolution (Phase 73): a database made by an older version is brought up to
    SCHEMA_VERSION by the numbered scripts in data_access/upgrades/, each version in turn,
    all in one transaction with the version bump -- upgraded whole, or left as it was;
  - the price series (Phase 73): observations added, never updated or deleted;
  - Steam's own playtime (Phase 75): the accounts, a log of every reading, and the counters
    recorded only when they change -- the readings and counters added, never updated or deleted.

Built beside the JSON in Phase 67; since the switch (Phase 69) it is the library the program
runs on, opened through logic.migration.open_library.

Transactions are explicit: connections are opened with autocommit on, and every write is
one BEGIN ... COMMIT, so a change touching several rows -- a game and its sessions, two
games in a carry-over -- lands whole or not at all.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import os
import sqlite3
import threading
import weakref
from collections import Counter, defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from data_access import recap as recap_module
from data_access import recommend as recommend_module
from data_access import reports as reports_module
from shared import naming, paths, rules
from shared.models import GameEntry

log = logging.getLogger(__name__)

SCHEMA_VERSION = 8  # 1: Phase 67; 2: prices and purchases (Phase 73); 3: Steam's own playtime (Phase 75);
#                     4: v_steam_time_mine in one pass (Phase 76); 5: v_hours, for the reports (Phase 83);
#                     6: the Steam wishlist (Phase 86); 7: a session's origin, observed sessions (Phase 93);
#                     8: price alerts, a session's rating, dated status marks (Phase 101, for 101-103)
SCHEMA_FILE = "schema.sql"
UPGRADES_DIRNAME = "upgrades"  # NNN_name.sql: the script that brings version NNN-1 to NNN
MIGRATED_FROM = "overrides.json + catalog.json"
SOURCES = ("folders", "steam", "gog", "epic", "ubisoft", "xbox")

# -- the mapping between a record and its rows ---------------------------------------------
# A field kept as one value on the game row, under a column of its own name.
TEXT_FIELDS = {
    "name": "custom_name",
    "exe": "custom_exe",
    "args": "launch_args",
    rules.STATUS_KEY: "status",
    rules.NOTES_KEY: "notes",
    "first_seen": "first_seen",
    "last_played": "last_played",
    "cover": "cover_path",
    "banner": "banner_path",
    rules.SAVE_DIRS_CHECKED_KEY: "save_dirs_checked",
    rules.CARRIED_AT_KEY: "carried_at",
}
# A field version 8 added (Phase 101), on the game row under its own name: written and read only where the
# file has the column -- a library whose upgrade was refused stays on 7 and keeps working, as has_origin does.
MARK_FIELDS = {rules.STATUS_CHANGED_KEY: "status_changed_at", rules.NUDGED_KEY: "nudged_at"}  # Phases 101, 103
# True or absent in a record; 1 or 0 on the row.
FLAG_FIELDS = {"hidden": "hidden", "favorite": "favorite", rules.NEW_KEY: "is_new"}
# The rest, each handled on its own: a name with its origin, a chosen appid, a three-way
# tool mark, a total, another game named by key, and five lists kept as rows of their own.
OTHER_FIELDS = (rules.KNOWN_AS_KEY, "appid", "is_tool", "playtime_seconds", rules.CARRIED_TO_KEY,
                rules.SESSIONS_KEY, rules.SAVE_DIRS_KEY, rules.SAVE_DIRS_IGNORED_KEY,
                rules.EARLIER_KEYS_KEY, rules.NOT_SAME_KEY)
FIELDS = frozenset(TEXT_FIELDS) | frozenset(FLAG_FIELDS) | frozenset(OTHER_FIELDS) | frozenset(MARK_FIELDS)
SAVE_LISTS = ((0, rules.SAVE_DIRS_KEY), (1, rules.SAVE_DIRS_IGNORED_KEY))
LINEAGE_LISTS = (("carried_from", rules.EARLIER_KEYS_KEY), ("not_same", rules.NOT_SAME_KEY))


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def is_uri_key(key: str) -> bool:
    """`steam:730`, not `c:\\games\\foo` -- whose colon is the drive letter's."""
    return ":" in key and key[1:2] != ":"


# -- opening and creating ------------------------------------------------------------------


def schema_text() -> str:
    return (paths.resource_dir() / "data_access" / SCHEMA_FILE).read_text(encoding="utf-8")


def connect(path: Path | str) -> sqlite3.Connection:
    """A connection with foreign keys enforced and transactions left to the caller.

    It refuses use from any thread but the one that opened it (sqlite3's own
    check_same_thread, left on): the GUI thread is the one writer (docs, section 12).
    """
    conn = sqlite3.connect(str(path), autocommit=True)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection):
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


@contextmanager
def _savepoint(conn: sqlite3.Connection):
    conn.execute("SAVEPOINT one_record")
    try:
        yield
    except BaseException:
        conn.execute("ROLLBACK TO one_record")
        conn.execute("RELEASE one_record")
        raise
    conn.execute("RELEASE one_record")


def create(conn: sqlite3.Connection, now: str | None = None) -> None:
    """The tables, the views and the one row about the file itself, in one transaction."""
    with transaction(conn):
        conn.executescript(schema_text())
        conn.execute("INSERT INTO meta (id, schema_version, created_at) VALUES (1, ?, ?)",
                     (SCHEMA_VERSION, now or _now()))
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def schema_version(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


def upgrade_scripts() -> dict[int, Path]:
    """The upgrade scripts on disk, by the version each brings a database to."""
    folder = paths.resource_dir() / "data_access" / UPGRADES_DIRNAME
    found = {}
    for script in sorted(folder.glob("[0-9][0-9][0-9]_*.sql")) if folder.is_dir() else []:
        found[int(script.name[:3])] = script
    return found


def upgrade(conn: sqlite3.Connection) -> list[int]:
    """Bring a database made by an older version up to SCHEMA_VERSION; return the versions applied.

    Every missing script runs in one transaction with the version bump (meta.schema_version
    and PRAGMA user_version, which SQLite keeps in the file's header and also rolls back):
    any failure -- a script missing, a statement refused -- raises, and the file is left
    exactly as it was. The caller takes the snapshot first and decides what then runs.
    """
    have = schema_version(conn)
    missing = list(range(have + 1, SCHEMA_VERSION + 1))
    if not missing:
        return []
    scripts = upgrade_scripts()
    absent = [version for version in missing if version not in scripts]
    if absent:
        raise ValueError(f"no upgrade script for version(s) {absent}")
    with transaction(conn):
        for version in missing:
            conn.executescript(scripts[version].read_text(encoding="utf-8"))
        conn.execute("UPDATE meta SET schema_version = ? WHERE id = 1", (SCHEMA_VERSION,))
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    log.info("library database upgraded from version %d to %d", have, SCHEMA_VERSION)
    return missing


def has_origin(conn: sqlite3.Connection) -> bool:
    """Version 7 or newer: a session says how it was measured (Phase 93)."""
    return schema_version(conn) >= 7


def has_marks(conn: sqlite3.Connection) -> bool:
    """Version 8 or newer: a game's mark carries the moment it was set (Phase 101)."""
    return schema_version(conn) >= 8


def fingerprint(conn: sqlite3.Connection) -> str:
    """A digest of everything the database holds, written out as SQL.

    Bytes cannot tell an unchanged database: SQLite reuses pages, so a change undone leaves
    other bytes behind (measured in Phase 63). The content can.
    """
    digest = hashlib.sha256()
    for line in conn.iterdump():
        digest.update(line.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


# -- whole database files: for snapshots and restores (Phase 68) -------------------------------


def copy_database(source: Path | str, target: Path | str) -> None:
    """A consistent copy of a database file, through SQLite's own backup.

    Never a plain copy of the file: a database open in the launcher may be mid-write, and a
    file copy could catch it half done. The backup reads it the way SQLite itself does.
    """
    src = sqlite3.connect(str(source))
    try:
        dst = sqlite3.connect(str(target))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


def file_fingerprint(path: Path | str) -> str:
    """fingerprint() of the database in a file."""
    conn = sqlite3.connect(str(path))
    try:
        return fingerprint(conn)
    finally:
        conn.close()


def put_back(source: Path | str, target: Path | str) -> None:
    """Replace the database at `target` with a copy of the one at `source`.

    Copied through a temporary file beside the target, then renamed over it in one step. No
    connection may hold the target open while this runs (Windows will not replace an open
    file), so the store is closed first. A journal left by a write cut short is dealt with by
    opening the old database once before it goes: SQLite rolls the half write back and
    removes the journal, which could otherwise be applied to the new file.
    """
    target = Path(target)
    if target.is_file() and Path(f"{target}-journal").exists():
        settled = sqlite3.connect(str(target))  # the first read rolls a hot journal back
        settled.execute("SELECT count(*) FROM sqlite_master").fetchone()
        settled.close()
    temp = target.with_name(target.name + ".restoring")
    temp.unlink(missing_ok=True)
    copy_database(source, temp)
    os.replace(temp, target)


# -- the Steam projection ------------------------------------------------------------------

RELEASE_FORMATS = ("%d %b, %Y", "%b %d, %Y", "%d %B, %Y", "%B %d, %Y")


def release_iso(text: str) -> str | None:
    """Steam's "9 Dec, 2020" as an ISO date; None for "Coming soon", "Q4 2026" -- never guessed."""
    for fmt in RELEASE_FORMATS:
        try:
            return datetime.strptime(text.strip(), fmt).date().isoformat()
        except (ValueError, AttributeError):
            continue
    return None


def _whole(value, what: str, appid: int, notes: list[str]) -> int | None:
    """A whole number Steam wrote as a number or as digits; anything else is noted and left NULL."""
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        notes.append(f"steam {appid}: {what} is a boolean {value!r}; left NULL")
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value)
    notes.append(f"steam {appid}: {what} {value!r} is not a whole number; left NULL")
    return None


def ensure_steam_app(conn: sqlite3.Connection, appid: int, app_type: str | None = None,
                     fetched_at: str | None = None) -> None:
    """A row for an appid a game names, before its record is cached (has_record 0)."""
    conn.execute("INSERT INTO steam_app (appid, has_record, app_type, fetched_at) VALUES (?, 0, ?, ?) "
                 "ON CONFLICT (appid) DO NOTHING", (appid, app_type, fetched_at))


def store_steam_app(conn: sqlite3.Connection, appid: int, record: dict,
                    fetched_at: str | None) -> list[str]:
    """One cached appdetails record into steam_app and its satellites, replacing what was there.

    Run inside a transaction. Returns a note for every value left NULL rather than guessed.
    """
    notes: list[str] = []
    price = record.get("price_overview") or {}
    release = record.get("release_date") or {}
    text = release.get("date") or None
    iso = release_iso(text) if text else None
    if text and not iso:
        notes.append(f"steam {appid}: release text {text!r} is not a date; release_date left NULL")
    row = {
        "appid": appid, "has_record": 1, "name": record.get("name"), "app_type": record.get("type"),
        "is_free": int(bool(record.get("is_free"))), "release_date": iso, "release_text": text,
        "coming_soon": int(bool(release.get("coming_soon"))) if release else None,
        "price_initial_cents": _whole(price.get("initial"), "price initial", appid, notes),
        "price_final_cents": _whole(price.get("final"), "price final", appid, notes),
        "discount_percent": _whole(price.get("discount_percent"), "discount", appid, notes),
        "currency": price.get("currency") or None,
        "metacritic_score": _whole((record.get("metacritic") or {}).get("score"), "metacritic", appid, notes),
        "recommendations": _whole((record.get("recommendations") or {}).get("total"),
                                  "recommendations", appid, notes),
        "controller_support": record.get("controller_support"),
        "required_age": _whole(record.get("required_age"), "required_age", appid, notes),
        "achievements_total": _whole((record.get("achievements") or {}).get("total"),
                                     "achievements", appid, notes),
        "short_description": record.get("short_description"),
        "fetched_at": fetched_at,
    }
    if (row["price_final_cents"] is None) != (row["currency"] is None):
        notes.append(f"steam {appid}: a price without its currency, or the other way; both left NULL")
        row["price_initial_cents"] = row["price_final_cents"] = row["discount_percent"] = row["currency"] = None
    columns = ", ".join(row)
    updates = ", ".join(f"{name} = excluded.{name}" for name in row if name != "appid")
    conn.execute(f"INSERT INTO steam_app ({columns}) VALUES ({', '.join('?' * len(row))}) "
                 f"ON CONFLICT (appid) DO UPDATE SET {updates}", tuple(row.values()))
    for table in ("steam_app_genre", "steam_app_category", "steam_app_company"):
        conn.execute(f"DELETE FROM {table} WHERE appid = ?", (appid,))
    for genre in record.get("genres") or []:
        conn.execute("INSERT INTO genre (id, name) VALUES (?, ?) ON CONFLICT (id) DO NOTHING",
                     (int(genre["id"]), genre["description"]))
        conn.execute("INSERT OR IGNORE INTO steam_app_genre (appid, genre_id) VALUES (?, ?)",
                     (appid, int(genre["id"])))
    for category in record.get("categories") or []:
        conn.execute("INSERT INTO category (id, name) VALUES (?, ?) ON CONFLICT (id) DO NOTHING",
                     (int(category["id"]), category["description"]))
        conn.execute("INSERT OR IGNORE INTO steam_app_category (appid, category_id) VALUES (?, ?)",
                     (appid, int(category["id"])))
    for role, key in (("developer", "developers"), ("publisher", "publishers")):
        for name in record.get(key) or []:
            company = conn.execute("INSERT INTO company (name) VALUES (?) ON CONFLICT (name) "
                                   "DO UPDATE SET name = name RETURNING id", (name,)).fetchone()[0]
            conn.execute("INSERT OR IGNORE INTO steam_app_company (appid, company_id, role) VALUES (?, ?, ?)",
                         (appid, company, role))
    return notes


# -- writing a record -----------------------------------------------------------------------


def _game_row(conn: sqlite3.Connection, key: str) -> tuple[int, sqlite3.Row | tuple]:
    """The game row for an identity key, made bare if there is none: no record yet."""
    found = conn.execute("SELECT id, name_origin, appid_source FROM game WHERE identity_key = ?",
                         (key,)).fetchone()
    if found is not None:
        return found[0], found
    source, source_id = None, None
    if is_uri_key(key):
        prefix, rest = key.split(":", 1)
        if prefix in SOURCES:
            source, source_id = prefix, rest
    gid = conn.execute("INSERT INTO game (identity_key, source, source_id, name_origin) VALUES (?, ?, ?, 'none')",
                       (key, source, source_id)).lastrowid
    return gid, (gid, "none", None)


def write_record(conn: sqlite3.Connection, key: str, record: dict | None) -> None:
    """One game's record onto its rows -- all of them, replacing what they held.

    Run inside a transaction. None (no record) blanks the user's columns and lists; the row
    stays, because an install, another game's history or a recovered name may name it.
    """
    record = record or {}
    unknown = set(record) - FIELDS
    if unknown:
        raise ValueError(f"{key}: fields the store does not keep: {sorted(unknown)}")
    gid, (_id, origin, appid_source) = _game_row(conn, key)
    values: dict[str, Any] = {column: record.get(name) for name, column in TEXT_FIELDS.items()}
    if has_marks(conn):
        values.update({column: record.get(name) for name, column in MARK_FIELDS.items()})
    values.update({column: 1 if record.get(name) else 0 for name, column in FLAG_FIELDS.items()})
    tool = record.get("is_tool")
    values["is_tool"] = None if tool is None else int(bool(tool))
    values["playtime_seconds"] = record.get("playtime_seconds")
    if rules.KNOWN_AS_KEY in record:
        values["known_as"], values["name_origin"] = record[rules.KNOWN_AS_KEY], "scan"
    elif origin == "scan":
        values["known_as"], values["name_origin"] = None, "none"
    # otherwise a name the migration recovered stays, for the analysis -- never handed back
    if "appid" in record:
        values["steam_appid"], values["appid_source"] = int(record["appid"]), "chosen"
        ensure_steam_app(conn, values["steam_appid"])
    elif appid_source == "chosen":
        values["steam_appid"] = values["appid_source"] = None
    target = record.get(rules.CARRIED_TO_KEY)
    values["carried_to"] = _game_row(conn, target)[0] if target else None
    assignments = ", ".join(f"{column} = ?" for column in values)
    conn.execute(f"UPDATE game SET {assignments} WHERE id = ?", (*values.values(), gid))

    conn.execute("DELETE FROM session WHERE game_id = ?", (gid,))
    entries = record.get(rules.SESSIONS_KEY) or []
    if has_origin(conn):
        conn.executemany("INSERT INTO session (game_id, started_at, minutes, origin) VALUES (?, ?, ?, ?)",
                         [(gid, item["start"], item["minutes"], item.get(rules.SESSION_ORIGIN_KEY) or
                           rules.SESSION_LAUNCHED) for item in entries])
    else:  # a file left at version 6 (an upgrade refused): no observed session is ever made for it
        conn.executemany("INSERT INTO session (game_id, started_at, minutes) VALUES (?, ?, ?)",
                         [(gid, item["start"], item["minutes"]) for item in entries])
    if has_marks(conn):
        # A rating names its session by game and start (Phase 102); the sessions just put back keep theirs, and a
        # session gone from the record -- pruned after SESSION_KEEP_DAYS, or carried to another game -- takes its
        # rating with it in this same write, so the key checked at the commit always holds.
        conn.execute("DELETE FROM rating WHERE game_id = ? AND started_at NOT IN "
                     "(SELECT started_at FROM session WHERE game_id = ?)", (gid, gid))
    conn.execute("DELETE FROM save_folder WHERE game_id = ?", (gid,))
    rows, position = [], 0
    for ignored, name in SAVE_LISTS:
        for folder in record.get(name) or []:
            rows.append((gid, folder, ignored, position))
            position += 1
    conn.executemany("INSERT INTO save_folder (game_id, path, ignored, position) VALUES (?, ?, ?, ?)", rows)
    conn.execute("DELETE FROM lineage WHERE game_id = ?", (gid,))
    rows, position = [], 0
    for relation, name in LINEAGE_LISTS:
        for other in record.get(name) or []:
            rows.append((gid, _game_row(conn, other)[0], relation, position))
            position += 1
    conn.executemany("INSERT INTO lineage (game_id, earlier_id, relation, position) VALUES (?, ?, ?, ?)", rows)


# -- reading records back ---------------------------------------------------------------------


def read_records(conn: sqlite3.Connection) -> dict[str, dict]:
    """Every record, in the dict shape overrides.json has always held -- the facade's side.

    A game row with nothing of the user's on it -- found by a scan, not yet stamped -- is no
    record, as a key missing from overrides.json was none.
    """
    cursor = conn.execute("SELECT * FROM game ORDER BY id")
    columns = [d[0] for d in cursor.description]
    games = [dict(zip(columns, row)) for row in cursor]
    keys = {game["id"]: game["identity_key"] for game in games}
    sessions: dict[int, list] = defaultdict(list)
    origin = "origin" if has_origin(conn) else f"'{rules.SESSION_LAUNCHED}'"
    for gid, start, minutes, how in conn.execute(
            f"SELECT game_id, started_at, minutes, {origin} FROM session "
            "ORDER BY game_id, julianday(started_at), id"):
        item = {"start": start, "minutes": minutes}
        if how == rules.SESSION_OBSERVED:  # 'launched' is the shape a session always had: left unsaid
            item[rules.SESSION_ORIGIN_KEY] = how
        sessions[gid].append(item)
    folders: dict[tuple, list] = defaultdict(list)
    for gid, folder, ignored in conn.execute(
            "SELECT game_id, path, ignored FROM save_folder ORDER BY game_id, position"):
        folders[(gid, ignored)].append(folder)
    lineage: dict[tuple, list] = defaultdict(list)
    for gid, earlier, relation in conn.execute(
            "SELECT game_id, earlier_id, relation FROM lineage ORDER BY game_id, position"):
        lineage[(gid, relation)].append(keys[earlier])

    found: dict[str, dict] = {}
    for game in games:
        gid, record = game["id"], {}
        if game["known_as"] is not None and game["name_origin"] == "scan":
            record[rules.KNOWN_AS_KEY] = game["known_as"]
        for name, column in TEXT_FIELDS.items():
            if game[column] is not None:
                record[name] = game[column]
        for name, column in MARK_FIELDS.items():
            if game.get(column) is not None:
                record[name] = game[column]
        for name, column in FLAG_FIELDS.items():
            if game[column]:
                record[name] = True
        if game["is_tool"] is not None:
            record["is_tool"] = bool(game["is_tool"])
        if game["playtime_seconds"] is not None:
            record["playtime_seconds"] = game["playtime_seconds"]
        if game["appid_source"] == "chosen":
            record["appid"] = str(game["steam_appid"])
        if game["carried_to"] is not None:
            record[rules.CARRIED_TO_KEY] = keys[game["carried_to"]]
        if sessions[gid]:
            record[rules.SESSIONS_KEY] = sessions[gid]
        for ignored, name in SAVE_LISTS:
            if folders[(gid, ignored)]:
                record[name] = folders[(gid, ignored)]
        for relation, name in LINEAGE_LISTS:
            if lineage[(gid, relation)]:
                record[name] = lineage[(gid, relation)]
        if record:
            found[game["identity_key"]] = record
    return found


# -- the catalogue -------------------------------------------------------------------------------


def write_catalog(conn: sqlite3.Connection, entries: list[GameEntry], *, roots=(), trigger: str,
                  started_at: str | None, finished_at: str | None = None) -> int:
    """What a scan found: one scan row, and the install rows rewritten. Run inside a transaction.

    A game's source and its Steam link come from its entry -- the link only where the user
    did not choose one, and kept when a later scan no longer says it (that is how a game
    keeps its link once it is gone). Returns the scan's id.
    """
    scan_id = conn.execute(
        "INSERT INTO scan (started_at, finished_at, roots, entry_count, trigger) VALUES (?, ?, ?, ?, ?)",
        (started_at, finished_at or _now(), json.dumps(list(roots), ensure_ascii=False), len(entries), trigger),
    ).lastrowid
    conn.execute("DELETE FROM install")
    for position, entry in enumerate(entries):
        gid, _row = _game_row(conn, entry.identity_key)
        conn.execute("UPDATE game SET source = ?, source_id = ? WHERE id = ?", (entry.source, entry.source_id, gid))
        appid = str(entry.extra.get("appid") or "").strip()
        if appid.isdigit():
            kind = "search" if entry.extra.get("appid_source") == rules.APPID_SOURCE_SEARCH else "manifest"
            ensure_steam_app(conn, int(appid))
            conn.execute("UPDATE game SET steam_appid = ?, appid_source = ? WHERE id = ? "
                         "AND (appid_source IS NULL OR appid_source <> 'chosen')", (int(appid), kind, gid))
        stamp = entry.extra.get("last_played_unix")
        data = entry.to_dict()
        conn.execute(
            "INSERT INTO install (game_id, position, display_name, install_dir, launch_kind, launch_target, "
            "working_dir, icon_hint, size_on_disk, detection, alternatives, extra, store_last_played, scan_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (gid, position, entry.display_name, entry.install_dir, entry.launch_kind, entry.launch_target,
             entry.working_dir, entry.icon_hint, entry.size_on_disk, entry.detection,
             json.dumps(data["alternatives"], ensure_ascii=False), json.dumps(entry.extra, ensure_ascii=False),
             datetime.fromtimestamp(int(stamp)).astimezone().isoformat(timespec="seconds")
             if isinstance(stamp, int) and stamp > 0 else None,
             scan_id),
        )
    return scan_id


def read_entries(conn: sqlite3.Connection) -> list[GameEntry]:
    """The last scan's entries, in the order it found them, as catalog.json gave them back."""
    entries = []
    for row in conn.execute(
            "SELECT g.source, g.source_id, i.display_name, i.install_dir, i.launch_kind, i.launch_target, "
            "i.working_dir, i.icon_hint, i.size_on_disk, i.detection, i.alternatives, i.extra "
            "FROM install i JOIN game g ON g.id = i.game_id ORDER BY i.position"):
        names = ("source", "source_id", "display_name", "install_dir", "launch_kind", "launch_target",
                 "working_dir", "icon_hint", "size_on_disk", "detection")
        data = dict(zip(names, row[:10]))
        data["alternatives"] = json.loads(row[10])
        data["extra"] = json.loads(row[11])
        entries.append(GameEntry.from_dict(data))
    return entries


def last_scan_time(conn: sqlite3.Connection) -> datetime | None:
    found = conn.execute("SELECT finished_at FROM scan ORDER BY id DESC LIMIT 1").fetchone()
    if found is None:
        return None
    try:
        return datetime.fromisoformat(found[0]).astimezone()
    except ValueError:
        log.warning("unreadable scan time %r", found[0])
        return None


# -- the repository ---------------------------------------------------------------------------


class LibraryStore:
    """catalog_io.Overrides on SQLite: the same operations, the same dicts handed out.

    The records are held in memory as Overrides holds them -- `get` gives back the same live
    dict every time, which the views read -- and every operation writes what it changed
    straight through to the database, in one transaction. If a write is refused, the
    database keeps what it had, the records in memory are read back from it, the refusal is
    logged, and the operation answers False; nothing is half written.
    """

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._owner = threading.get_ident()
        fresh = not self.path.is_file()
        self._connection: sqlite3.Connection | None = connect(self.path)
        if fresh:
            create(self._connection)
            log.info("created the library database at %s", self.path)
        self._records = read_records(self._connection)
        self.version = schema_version(self._connection)
        _OPEN.add(self)

    @property
    def _conn(self) -> sqlite3.Connection:
        """The connection, opened again if it was released -- on the thread that made the store only."""
        if self._connection is None:
            if threading.get_ident() != self._owner:
                raise sqlite3.ProgrammingError("the library store is used from the thread that opened it only")
            self._connection = connect(self.path)
        return self._connection

    def close(self) -> None:
        """Let go of the file; the store opens it again if it is used after this."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    # -- the facade, as Overrides has it --------------------------------------------------

    def get(self, key: str) -> dict[str, Any]:
        return self._records.get(key, {})

    def values_of(self, name: str) -> dict[str, Any]:
        return {key: record[name] for key, record in self._records.items() if name in record}

    def uncarried(self) -> list[tuple[str, dict[str, Any]]]:
        return [(key, record) for key, record in self._records.items()
                if not record.get(rules.CARRIED_TO_KEY)]

    def export_records(self) -> dict[str, dict[str, Any]]:
        return copy.deepcopy(self._records)

    def update(self, key: str, **values: Any) -> bool:
        return self.update_many({key: values})

    def update_many(self, changes: dict[str, dict[str, Any]]) -> bool:
        for key, values in changes.items():
            record = self._records.setdefault(key, {})
            for name, value in values.items():
                if value is None:
                    record.pop(name, None)
                else:
                    record[name] = value
            if not record:
                self._records.pop(key, None)
        return self._write(changes) if changes else True

    def carry(self, old_key: str, new_key: str, *, old_record: dict[str, Any],
              new_record: dict[str, Any]) -> bool:
        record = self._records.setdefault(new_key, {})
        record.clear()
        record.update(new_record)
        self._records[old_key] = dict(old_record)
        if not has_marks(self._conn):
            return self._write([new_key, old_key])
        # The carried sessions take their ratings to the new game (Phase 102), in the one transaction: the new
        # record first (its sessions, the old ones merged in), the ratings moved onto it where their session came
        # along, then the old record -- whose sessions, and any rating left on them, go.
        try:
            with transaction(self._conn):
                write_record(self._conn, new_key, self._records.get(new_key))
                old_id, new_id = _game_row(self._conn, old_key)[0], _game_row(self._conn, new_key)[0]
                self._conn.execute(
                    "INSERT OR IGNORE INTO rating (game_id, started_at, stars, rated_at) "
                    "SELECT ?, r.started_at, r.stars, r.rated_at FROM rating r "
                    "JOIN session s ON s.game_id = ? AND s.started_at = r.started_at WHERE r.game_id = ?",
                    (new_id, new_id, old_id))
                write_record(self._conn, old_key, self._records.get(old_key))
        except (sqlite3.Error, ValueError, KeyError, TypeError) as exc:
            log.error("the library could not be written (%s); nothing was kept", exc)
            self._reread()
            return False
        return True

    def import_records(self, records: dict[str, dict[str, Any]]) -> bool:
        for key, values in records.items():
            record = self._records.setdefault(key, {})
            record.clear()
            record.update(values)
        return self._write(records) if records else True

    # -- the catalogue --------------------------------------------------------------------

    def save_catalog(self, entries: list[GameEntry], roots=(), *, trigger: str = "manual",
                     started_at: str | None = None) -> bool:
        try:
            with transaction(self._conn):
                write_catalog(self._conn, entries, roots=roots, trigger=trigger, started_at=started_at)
        except (sqlite3.Error, ValueError) as exc:
            log.error("the scan's findings could not be written: %s", exc)
            return False
        return True

    def load_catalog(self) -> list[GameEntry]:
        # Imported here: catalog_io imports backups, which copies databases with this module.
        from data_access import catalog_io

        return catalog_io.relocate_entries(read_entries(self._conn))

    def last_scan_time(self) -> datetime | None:
        return last_scan_time(self._conn)

    # -- the Steam projection (Phase 70) --------------------------------------------------

    def steam_fetched(self) -> dict[int, str | None] | None:
        """When each Steam record the database holds was fetched, by appid (rows with a record).

        None if the database cannot say -- logged, and the projection waits for the next scan.
        """
        try:
            return dict(self._conn.execute("SELECT appid, fetched_at FROM steam_app WHERE has_record = 1"))
        except sqlite3.Error as exc:
            log.error("could not read which Steam records the library holds: %s", exc)
            return None

    def store_steam_records(self, records: dict[int, tuple[dict, str | None]]) -> tuple[list[str], dict[int, str]]:
        """Records into steam_app and its satellites -- {appid: (record, fetched at)} -- in one transaction.

        Each record in a savepoint of its own, as the loader does: one that does not fit is
        left as the database had it and named, with why, in the second answer; the others
        still land. The first answer is the notes, a value left NULL rather than guessed.
        """
        notes: list[str] = []
        refused: dict[int, str] = {}
        try:
            with transaction(self._conn):
                for appid, (record, fetched_at) in sorted(records.items()):
                    try:
                        with _savepoint(self._conn):
                            notes += store_steam_app(self._conn, appid, record, fetched_at)
                    except (sqlite3.Error, ValueError, KeyError, TypeError) as exc:
                        refused[appid] = f"{type(exc).__name__}: {exc}"
        except sqlite3.Error as exc:
            log.error("the Steam records could not be written: %s", exc)
            return notes, {appid: str(exc) for appid in records}
        return notes, refused

    # -- schema evolution and the price series (Phase 73) ----------------------------------

    def upgrade(self) -> list[int]:
        """The database brought up to SCHEMA_VERSION (see `upgrade`); raises if it was refused."""
        applied = upgrade(self._conn)
        self.version = schema_version(self._conn)
        return applied

    @property
    def keeps_prices(self) -> bool:
        """Version 2 or newer: the price series and the purchases exist in this file."""
        return self.version >= 2

    def prices_due(self, days: int, now: datetime | None = None,
                   wishlist_hours: int | None = None) -> list[int] | None:
        """Apps whose price was never observed, or not since `days` ago -- the oldest first.

        Every app with a cached record, installed or not: the series of a game played last
        year is still a series. Since Phase 86 a game on a wishlist of the accounts marked mine
        is due once `wishlist_hours` have passed instead: a sale is over in a week or two. None
        when this database keeps no prices (version 1).
        """
        if not self.keeps_prices:
            return None
        moment = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        since = (moment - timedelta(days=days)).isoformat(timespec="seconds")
        wished, wished_since = "0", since
        if wishlist_hours is not None and self.keeps_wishlist:
            wished = "a.appid IN (SELECT appid FROM v_wishlist_now WHERE lists > 0)"
            wished_since = (moment - timedelta(hours=wishlist_hours)).isoformat(timespec="seconds")
        return [row[0] for row in self._conn.execute(
            "SELECT a.appid FROM steam_app a "
            "LEFT JOIN (SELECT appid, MAX(observed_at) AS newest FROM price_snapshot GROUP BY appid) p "
            "ON p.appid = a.appid "
            f"WHERE a.has_record = 1 AND (p.newest IS NULL OR p.newest < ? OR ({wished} AND p.newest < ?)) "
            "ORDER BY p.newest IS NOT NULL, p.newest, a.appid", (since, wished_since))]

    def observation_keys(self) -> set[tuple[int, str]] | None:
        """(appid, observed_at) of every observation held; None at version 1."""
        if not self.keeps_prices:
            return None
        return set(self._conn.execute("SELECT appid, observed_at FROM price_snapshot"))

    def add_observations(self, rows: list[dict]) -> tuple[set[tuple[int, str]], dict[tuple[int, str], str]]:
        """Observations into the series, in one transaction; a row already there is left as it is.

        Append-only: there is no update and no delete for price_snapshot anywhere in the
        program. ON CONFLICT DO NOTHING makes adding the same observation twice change
        nothing (an idempotent insert). Each row in a savepoint of its own: one the table
        refuses is named with why, the rest land. Answers what is in the database now (landed,
        or there already) and what was refused.
        """
        landed: set[tuple[int, str]] = set()
        refused: dict[tuple[int, str], str] = {}
        if not self.keeps_prices or not rows:
            return landed, refused
        columns = ("appid", "observed_at", "kind", "currency", "initial_cents", "final_cents", "discount_percent")
        try:
            with transaction(self._conn):
                for row in rows:
                    key = (row.get("appid"), row.get("observed_at"))
                    try:
                        with _savepoint(self._conn):
                            self._conn.execute(
                                f"INSERT INTO price_snapshot ({', '.join(columns)}) "
                                f"VALUES ({', '.join('?' * len(columns))}) "
                                "ON CONFLICT (appid, observed_at) DO NOTHING",
                                tuple(row.get(name) for name in columns))
                        landed.add(key)
                    except (sqlite3.Error, ValueError, TypeError) as exc:
                        refused[key] = f"{type(exc).__name__}: {exc}"
        except sqlite3.Error as exc:
            log.error("the price observations could not be written: %s", exc)
            return set(), {(row.get("appid"), row.get("observed_at")): str(exc) for row in rows}
        return landed, refused

    # -- what the user paid (Phase 74) --------------------------------------------------------

    PURCHASE_FIELDS = ("paid_cents", "currency", "store", "bought_on", "note", "recorded_at")

    def purchases(self, key: str) -> list[dict]:
        """A game's purchases, oldest first (a date unknown last), each with its id."""
        if not self.keeps_prices:
            return []
        rows = self._conn.execute(
            "SELECT p.id, p.paid_cents, p.currency, p.store, p.bought_on, p.note, p.recorded_at "
            "FROM purchase p JOIN game g ON g.id = p.game_id WHERE g.identity_key = ? "
            "ORDER BY p.bought_on IS NULL, p.bought_on, p.id", (key,))
        return [dict(zip(("id",) + self.PURCHASE_FIELDS, row)) for row in rows]

    def add_purchase(self, key: str, *, paid_cents: int, currency: str, store: str,
                     bought_on: str | None = None, note: str | None = None,
                     recorded_at: str | None = None) -> int | None:
        """One purchase for a game, typed by the user; its id, or None if the table refused it."""
        if not self.keeps_prices:
            return None
        try:
            with transaction(self._conn):
                gid, _row = _game_row(self._conn, key)
                new_id = self._conn.execute(
                    "INSERT INTO purchase (game_id, paid_cents, currency, store, bought_on, note, recorded_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING id",
                    (gid, paid_cents, currency, store, bought_on, note or None, recorded_at or _now())).fetchone()[0]
        except (sqlite3.Error, ValueError, TypeError) as exc:
            log.error("the purchase for %s was refused (%s); nothing was kept", key, exc)
            return None
        return new_id

    def remove_purchase(self, purchase_id: int) -> bool:
        """The one row this program ever deletes from the money tables: a purchase the user removes."""
        if not self.keeps_prices:
            return False
        try:
            with transaction(self._conn):
                gone = self._conn.execute("DELETE FROM purchase WHERE id = ?", (purchase_id,)).rowcount
        except sqlite3.Error as exc:
            log.error("the purchase %s could not be removed (%s)", purchase_id, exc)
            return False
        return gone == 1

    def all_purchases(self) -> dict[str, list[dict]]:
        """Every purchase, by game, without ids -- what an export bundle carries."""
        if not self.keeps_prices:
            return {}
        found: dict[str, list[dict]] = {}
        for row in self._conn.execute(
                "SELECT g.identity_key, p.paid_cents, p.currency, p.store, p.bought_on, p.note, p.recorded_at "
                "FROM purchase p JOIN game g ON g.id = p.game_id ORDER BY g.identity_key, p.id"):
            found.setdefault(row[0], []).append(dict(zip(self.PURCHASE_FIELDS, row[1:])))
        return found

    def add_purchases(self, by_key: dict[str, list[dict]]) -> int | None:
        """Purchases from a bundle, joined to what is here; how many were new -- None if refused.

        A union, never a replacement: a purchase is the same one when its date, amount and store
        are (the brief's rule), so importing a bundle twice adds nothing, and nothing here is
        ever taken away. One transaction: all of a bundle's purchases, or none.
        """
        if not self.keeps_prices:
            return None
        added = 0
        try:
            with transaction(self._conn):
                for key, rows in by_key.items():
                    gid, _row = _game_row(self._conn, key)
                    have = set(self._conn.execute(
                        "SELECT bought_on, paid_cents, store FROM purchase WHERE game_id = ?", (gid,)))
                    for row in rows:
                        same = (row.get("bought_on"), row.get("paid_cents"), row.get("store"))
                        if same in have:
                            continue
                        self._conn.execute(
                            "INSERT INTO purchase (game_id, paid_cents, currency, store, bought_on, note, recorded_at) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (gid, row.get("paid_cents"), row.get("currency") or "EUR", row.get("store"),
                             row.get("bought_on"), row.get("note"), row.get("recorded_at") or _now()))
                        have.add(same)
                        added += 1
        except (sqlite3.Error, ValueError, TypeError) as exc:
            log.error("the bundle's purchases were refused (%s); none were kept", exc)
            return None
        return added

    def money(self, key: str) -> dict | None:
        """What the game's page says about money: the latest list price, the range seen, what
        was paid, and what an hour cost -- from the three views. None when there is nothing to
        say: a database that keeps no prices, or a game it does not know."""
        if not self.keeps_prices:
            return None
        row = self._conn.execute(
            "SELECT steam_appid, purchases, paid_cents, paid_currency, playtime_seconds, cents_per_hour "
            "FROM v_game_money WHERE identity_key = ?", (key,)).fetchone()
        if row is None:
            return None
        appid, count, paid_cents, paid_currency, playtime, per_hour = row
        latest = span = None
        if appid is not None:
            found = self._conn.execute(
                "SELECT kind, currency, initial_cents, final_cents, discount_percent, observed_at "
                "FROM v_price_latest WHERE appid = ?", (appid,)).fetchone()
            if found is not None:
                latest = dict(zip(("kind", "currency", "initial_cents", "final_cents", "discount_percent",
                                   "observed_at"), found))
            found = self._conn.execute(
                "SELECT observations, lowest_cents, lowest_currency, lowest_on FROM v_price_range WHERE appid = ?",
                (appid,)).fetchone()
            if found is not None:
                span = dict(zip(("observations", "lowest_cents", "lowest_currency", "lowest_on"), found))
        return {"latest": latest, "range": span, "purchases": self.purchases(key) if count else [],
                "paid_cents": paid_cents, "paid_currency": paid_currency,
                "playtime_seconds": playtime, "cents_per_hour": per_hour}

    # -- the reports (Phase 83) -----------------------------------------------------------------

    def reports(self):
        """The reports' queries (data_access/reports.py) on this store's own connection -- one
        reader, on the GUI thread -- or None below version 5, which has no v_hours yet."""
        if self.version < reports_module.NEEDS_VERSION:
            return None
        return reports_module.Reports(self._conn)

    def recap(self):
        """The recap's queries (data_access/recap.py, Phase 96) on this store's own connection, as the
        reports' are -- or None below the reports' version: the one rule needs a session's origin."""
        if self.version < reports_module.NEEDS_VERSION:
            return None
        return recap_module.Recap(self._conn)

    def recommend(self):
        """For you's queries (data_access/recommend.py, Phase 98) on this store's own connection, read-only --
        or None below the reports' version."""
        if self.version < reports_module.NEEDS_VERSION:
            return None
        return recommend_module.Recommend(self._conn)

    # -- Steam's own playtime (Phase 75) ------------------------------------------------------

    @property
    def keeps_steam_time(self) -> bool:
        """Version 3 or newer: the Steam accounts, readings and playtime series exist in this file."""
        return self.version >= 3

    def steam_accounts(self) -> list[dict]:
        """Every Steam account seen on this machine, with its mark and its newest reading -- and,
        since version 6, its wishlist's newest read (wishlist_read_at, wishlist_state,
        wishlist_items; None when never read)."""
        if not self.keeps_steam_time:
            return []
        wishlist = ("w.read_at, w.state, w.items" if self.keeps_wishlist else "NULL, NULL, NULL")
        joined = ("LEFT JOIN (SELECT x.*, ROW_NUMBER() OVER (PARTITION BY account_id ORDER BY read_at DESC) "
                  "AS newest FROM wishlist_read x) w ON w.account_id = a.account_id AND w.newest = 1 "
                  if self.keeps_wishlist else "")
        rows = self._conn.execute(
            "SELECT a.account_id, a.steam_id64, a.account_name, a.persona, a.is_mine, a.last_login, "
            f"r.read_at, r.file_modified, r.apps_in_file, r.apps_with_time, {wishlist} "
            "FROM steam_account a LEFT JOIN (SELECT s.*, ROW_NUMBER() OVER (PARTITION BY account_id "
            "ORDER BY read_at DESC) AS newest FROM steam_read s) r ON r.account_id = a.account_id AND r.newest = 1 "
            f"{joined}"
            "ORDER BY a.persona IS NULL, a.persona COLLATE NOCASE, a.account_id")
        names = ("account_id", "steam_id64", "account_name", "persona", "is_mine", "last_login", "read_at",
                 "file_modified", "apps_in_file", "apps_with_time", "wishlist_read_at", "wishlist_state",
                 "wishlist_items")
        return [dict(zip(names, row)) for row in rows]

    def set_account_mark(self, account_id: int, mine: bool | None) -> bool:
        """Mine, not mine, or not decided (None) -- from Settings only. Changes no other data."""
        if not self.keeps_steam_time:
            return False
        try:
            with transaction(self._conn):
                changed = self._conn.execute("UPDATE steam_account SET is_mine = ? WHERE account_id = ?",
                                             (None if mine is None else int(bool(mine)), account_id)).rowcount
        except sqlite3.Error as exc:
            log.error("the mark of Steam account %s could not be saved (%s)", account_id, exc)
            return False
        return changed == 1

    def steam_times(self) -> dict[str, dict]:
        """Steam's own time on the accounts marked mine, by game (Phase 76).

        Through `game.steam_appid`: a game is here only when an account marked mine holds its
        app -- the minutes summed over those accounts (None when they hold only a last played),
        how many hold it, and the newest last played. Empty at version 2 or older.
        """
        if not self.keeps_steam_time:
            return {}
        rows = self._conn.execute(
            "SELECT g.identity_key, m.minutes, m.accounts, m.last_played "
            "FROM game g JOIN v_steam_time_mine m ON m.appid = g.steam_appid")
        return {key: {"minutes": minutes, "accounts": accounts, "last_played": last}
                for key, minutes, accounts, last in rows}

    def hours(self) -> dict[str, dict]:
        """Each game's hours as the reports count them (Phase 102 extension), by its key: its row of v_hours --
        the launcher's own time of every record of the game's Steam app (of the record alone, with no app) and
        Steam's counter on the accounts marked mine, an app counted once. Read once a reload, as the Steam
        hours are: a game's page shows it as its Played pill. Empty below version 5, which has no v_hours."""
        if self.version < 5:
            return {}
        rows = self._conn.execute(
            "WITH h AS MATERIALIZED (SELECT appid, game_id, minutes, minutes_launcher, minutes_steam FROM v_hours) "
            "SELECT g.identity_key, h.minutes, h.minutes_launcher, h.minutes_steam FROM game g "
            "JOIN h ON h.appid = g.steam_appid OR (g.steam_appid IS NULL AND h.game_id = g.id)")
        return {key: {"minutes": minutes or 0.0, "launcher": launcher or 0.0, "steam": steam}
                for key, minutes, launcher, steam in rows}

    def genres(self) -> dict[str, tuple[str, ...]]:
        """Each game's Steam genres, by its key (Phase 99: the library's genre pill), read once a reload as the
        Steam hours are. Through `game.steam_appid`; a game with no app, no record or no genre has no entry --
        "No genre known". The content warnings (rules.GENRE_FILTER_LEFT_OUT) are not kinds of game."""
        left_out = ",".join(str(int(g)) for g in rules.GENRE_FILTER_LEFT_OUT) or "-1"
        rows = self._conn.execute(
            "SELECT g.identity_key, genre.name FROM game g "
            "JOIN steam_app_genre sg ON sg.appid = g.steam_appid "
            "JOIN genre ON genre.id = sg.genre_id "
            f"WHERE genre.id NOT IN ({left_out}) ORDER BY g.identity_key, genre.name")
        found: dict[str, list[str]] = {}
        for key, name in rows:
            found.setdefault(key, []).append(name)
        return {key: tuple(names) for key, names in found.items()}

    # -- an anonymous export for analysis (Phase 80) ---------------------------------------------

    def analysis_source(self) -> dict[str, list[tuple]]:
        """The rows an anonymous export is made from (logic/analysis shapes them).

        Asked for by column, so nothing personal is ever read here: no path, no folder or exe, no
        custom name, note or chosen picture, no account's number leaves this method except to join
        its own minutes, no persona or account name at all. A game whose history was carried to a
        newer install is left out (its time is counted on the newer one) -- unless it is installed again. `name` is the store's own
        title, and only for a game a store installed -- a folder game's name is its folder's.
        """
        games = self._conn.execute(
            "SELECT g.id, g.source, i.game_id IS NOT NULL, g.steam_appid, g.appid_source, s.name, s.app_type, "
            "CASE WHEN g.source IS NOT NULL AND g.source <> 'folders' THEN COALESCE(i.display_name, g.known_as) END, "
            "g.is_tool, g.hidden, g.favorite, g.status, g.first_seen, g.last_played, g.playtime_seconds "
            "FROM game g LEFT JOIN install i ON i.game_id = g.id LEFT JOIN steam_app s ON s.appid = g.steam_appid "
            # A carried record installed again (The Witcher 3 here: carried on to a newer build, whose
            # folder was then renamed back) is a game on the PC: kept, with what it holds now.
            "WHERE g.carried_to IS NULL OR i.game_id IS NOT NULL ORDER BY g.id").fetchall()
        origin = "origin" if has_origin(self._conn) else f"'{rules.SESSION_LAUNCHED}'"  # how measured (Phase 93)
        sessions = self._conn.execute(
            f"SELECT game_id, started_at, minutes, {origin} FROM session ORDER BY started_at").fetchall()
        genres = self._conn.execute(
            "SELECT sg.appid, ge.name FROM steam_app_genre sg JOIN genre ge ON ge.id = sg.genre_id "
            "ORDER BY sg.appid, ge.name").fetchall()
        purchases = steam = accounts = ratings = marked = []
        if self.keeps_ratings:  # a session's stars and the day a mark was set (format 3, Phase 102)
            ratings = self._conn.execute(
                "SELECT game_id, started_at, stars FROM rating ORDER BY game_id, started_at").fetchall()
            marked = self._conn.execute(
                "SELECT id, status_changed_at FROM game WHERE status_changed_at IS NOT NULL ORDER BY id").fetchall()
        if self.keeps_prices:
            purchases = self._conn.execute(
                "SELECT game_id, paid_cents, currency, store, bought_on FROM purchase ORDER BY game_id, id").fetchall()
        if self.keeps_steam_time:
            steam = self._conn.execute(
                "SELECT m.appid, m.minutes, m.accounts, m.last_played, s.name, s.app_type "
                "FROM v_steam_time_mine m LEFT JOIN steam_app s ON s.appid = m.appid ORDER BY m.appid").fetchall()
            accounts = self._conn.execute(
                "SELECT a.account_id, COALESCE(SUM(l.minutes_total), 0), COALESCE(SUM(l.minutes_total > 0), 0), "
                "(SELECT MAX(r.read_at) FROM steam_read r WHERE r.account_id = a.account_id) "
                "FROM steam_account a LEFT JOIN v_steam_time_latest l ON l.account_id = a.account_id "
                "WHERE a.is_mine = 1 GROUP BY a.account_id").fetchall()
        return {"games": games, "sessions": sessions, "genres": genres, "purchases": purchases,
                "steam": steam, "accounts": accounts, "ratings": ratings, "marked": marked}

    def personal_values(self) -> dict[str, set[str]]:
        """What must never be in an anonymous export -- for its last check, never for the export.

        paths: every folder, exe, picture and save folder the library holds (and the identity keys
        that are paths); ids: the Steam accounts' numbers and SteamID64s; texts: notes, launch
        arguments, purchase notes. Names (personas, account names, custom names) are not here: they
        can be ordinary words a game title also holds, and no field of the export is drawn from them.
        """
        def column(sql: str) -> set[str]:
            return {str(row[0]) for row in self._conn.execute(sql) if row[0] not in (None, "")}

        paths = (column("SELECT install_dir FROM install") | column("SELECT launch_target FROM install "
                                                                    "WHERE launch_kind = 'exe'")
                 | column("SELECT working_dir FROM install") | column("SELECT custom_exe FROM game")
                 | column("SELECT cover_path FROM game") | column("SELECT banner_path FROM game")
                 | column("SELECT path FROM save_folder")
                 | {key for key in column("SELECT identity_key FROM game") if ":" in key[:3] or key.startswith("\\\\")})
        texts = column("SELECT notes FROM game") | column("SELECT launch_args FROM game")
        if self.keeps_prices:
            texts |= column("SELECT note FROM purchase")
        ids: set[str] = set()
        if self.keeps_steam_time:
            ids = column("SELECT account_id FROM steam_account") | column("SELECT steam_id64 FROM steam_account")
        return {"paths": paths, "texts": texts, "ids": ids}

    def steam_records_wanted(self, limit: int | None = None) -> list[int]:
        """Apps on the accounts marked mine that have no Steam record yet, the most played first.

        `limit` None is every one -- a few hundred numbers at most, and the scan needs them all:
        it skips the ones whose store answer is cached (a delisted game), so a cut-off list
        could hold nothing but those and stop the fetching for good."""
        if not self.keeps_steam_time:
            return []
        played = [row[0] for row in self._conn.execute(
            "SELECT l.appid FROM v_steam_time_latest l JOIN steam_app s ON s.appid = l.appid "
            "WHERE l.is_mine = 1 AND s.has_record = 0 "
            "GROUP BY l.appid ORDER BY COALESCE(SUM(l.minutes_total), 0) DESC, l.appid")]
        # Then the games on the wishlists (Phase 86), after every played one: the names that
        # matter arrive first, and a wished game's record gives it a price and its genres.
        wished = [] if not self.keeps_wishlist else [row[0] for row in self._conn.execute(
            "SELECT appid FROM v_wishlist_now WHERE has_record = 0 AND lists > 0 ORDER BY date_added, appid")]
        known = set(played)
        found = played + [appid for appid in wished if appid not in known]
        return found if limit is None else found[:limit]

    STEAM_TIME_FIELDS = ("minutes_total", "minutes_2wks", "minutes_disconnected", "last_played")

    def land_steam_time(self, reading: dict) -> dict | None:
        """One reading of Steam's files into the database, in one transaction -- None if refused.

        The accounts are upserted -- their names, last login and last seen brought up to date, a
        new one added not decided -- and is_mine is never touched. Each account's read row goes in
        (a read already there is left as it is). A counter goes in only when it is new or one of its
        four values differs from that pair's newest row: an append-only observation log, recorded
        on change. An app the store has no row for gets one, has_record 0, so the foreign key holds.
        Answers what was written, and which counters went down (kept as read, for the log).
        """
        if not self.keeps_steam_time:
            return None
        done = {"accounts": 0, "reads": 0, "observations": 0, "lowered": []}
        try:
            with transaction(self._conn):
                for account in reading.get("accounts", []):
                    seen = next((r["read_at"] for r in reading.get("reads", [])
                                 if r["account_id"] == account["account_id"]), None)
                    if seen is None:
                        continue
                    self._conn.execute(
                        "INSERT INTO steam_account (account_id, steam_id64, account_name, persona, most_recent, "
                        "last_login, first_seen, last_seen) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                        "ON CONFLICT (account_id) DO UPDATE SET account_name = COALESCE(excluded.account_name, account_name), "
                        "persona = COALESCE(excluded.persona, persona), most_recent = excluded.most_recent, "
                        "last_login = COALESCE(excluded.last_login, last_login), last_seen = excluded.last_seen",
                        (account["account_id"], account["steam_id64"], account.get("account_name"),
                         account.get("persona"), account.get("most_recent"), account.get("last_login"), seen, seen))
                    done["accounts"] += 1
                for read in reading.get("reads", []):
                    account_id, read_at = read["account_id"], read["read_at"]
                    added = self._conn.execute(
                        "INSERT INTO steam_read (account_id, read_at, file_modified, apps_in_file, apps_with_time) "
                        "VALUES (?, ?, ?, ?, ?) ON CONFLICT (account_id, read_at) DO NOTHING",
                        (account_id, read_at, read["file_modified"], read["apps_in_file"],
                         read["apps_with_time"])).rowcount
                    if not added:
                        continue  # this reading landed before: its counters did too
                    done["reads"] += 1
                    newest = {row[0]: row[1:] for row in self._conn.execute(
                        "SELECT appid, minutes_total, minutes_2wks, minutes_disconnected, last_played "
                        "FROM v_steam_time_latest WHERE account_id = ?", (account_id,))}
                    for value in read.get("values", []):
                        appid = value["appid"]
                        now = tuple(value.get(name) for name in self.STEAM_TIME_FIELDS)
                        before = newest.get(appid)
                        if before == now:
                            continue
                        ensure_steam_app(self._conn, appid)
                        self._conn.execute(
                            "INSERT INTO steam_playtime (account_id, appid, observed_at, minutes_total, minutes_2wks, "
                            "minutes_disconnected, last_played) VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (account_id, appid, read_at) + now)
                        done["observations"] += 1
                        if before is not None and before[0] is not None and now[0] is not None and now[0] < before[0]:
                            done["lowered"].append((account_id, appid, before[0], now[0]))
        except (sqlite3.Error, ValueError, KeyError, TypeError) as exc:
            log.error("the reading of Steam's files could not be written (%s); nothing was kept", exc)
            return None
        return done

    # -- the Steam wishlist (Phase 86) --------------------------------------------------------

    @property
    def keeps_wishlist(self) -> bool:
        """Version 6 or newer: the wishlist and its read log exist in this file."""
        return self.version >= 6

    @property
    def keeps_observed(self) -> bool:
        """Version 7 or newer: a session can say it was observed, not launched (Phase 93)."""
        return self.version >= 7

    @property
    def keeps_alerts(self) -> bool:
        """Version 8 or newer: a wished game's target, and the log of the alerts sent (Phase 101)."""
        return self.version >= 8

    @property
    def keeps_ratings(self) -> bool:
        """Version 8 or newer: a session's rating, 1 to 5 stars (Phase 102 writes the table version 8 made)."""
        return self.version >= 8

    # -- a session's rating (Phase 102) -------------------------------------------------------

    def ratings_of(self, key: str) -> dict[str, int]:
        """A game's ratings by the start of their session (the session row's own text)."""
        if not self.keeps_ratings:
            return {}
        return dict(self._conn.execute(
            "SELECT r.started_at, r.stars FROM rating r JOIN game g ON g.id = r.game_id WHERE g.identity_key = ?",
            (key,)))

    def rated_on(self, key: str, day: str) -> bool:
        """Whether a game was rated on a day (YYYY-MM-DD, local): the once-a-day rule survives a restart."""
        if not self.keeps_ratings:
            return False
        return self._conn.execute(
            "SELECT 1 FROM rating r JOIN game g ON g.id = r.game_id WHERE g.identity_key = ? "
            "AND substr(r.rated_at, 1, 10) = ? LIMIT 1", (key, day)).fetchone() is not None

    def rate_session(self, key: str, started_at: str, stars: int, now: datetime | None = None) -> bool:
        """One session's rating: one row, its session named by game and start; rating it again replaces the
        stars and the moment. The only new write of Phase 102. False when refused -- no such session, stars
        outside 1-5, or a library below version 8."""
        if not self.keeps_ratings:
            return False
        moment = (now or datetime.now().astimezone()).isoformat(timespec="seconds")
        try:
            with transaction(self._conn):
                found = self._conn.execute(
                    "SELECT s.game_id FROM session s JOIN game g ON g.id = s.game_id "
                    "WHERE g.identity_key = ? AND s.started_at = ?", (key, started_at)).fetchone()
                if found is None:
                    raise ValueError(f"no session of {key} began at {started_at}")
                self._conn.execute(
                    "INSERT INTO rating (game_id, started_at, stars, rated_at) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT (game_id, started_at) DO UPDATE SET stars = excluded.stars, "
                    "rated_at = excluded.rated_at", (found[0], started_at, int(stars), moment))
        except (sqlite3.Error, ValueError) as exc:
            log.error("the rating of %s's session at %s could not be written (%s)", key, started_at, exc)
            return False
        log.info("rated %s's session of %s: %d star(s)", key, started_at, stars)
        return True

    RATING_FIELDS = ("started_at", "stars", "rated_at")

    def all_ratings(self) -> dict[str, list[dict]]:
        """Every session's rating, by game -- what an export bundle carries, as it carries purchases."""
        if not self.keeps_ratings:
            return {}
        found: dict[str, list[dict]] = {}
        for row in self._conn.execute(
                "SELECT g.identity_key, r.started_at, r.stars, r.rated_at FROM rating r JOIN game g ON g.id = r.game_id "
                "ORDER BY g.identity_key, r.started_at"):
            found.setdefault(row[0], []).append(dict(zip(self.RATING_FIELDS, row[1:])))
        return found

    def add_ratings(self, by_key: dict[str, list[dict]]) -> tuple[int, int] | None:
        """Ratings from a bundle, joined to what is here: (added, skipped) -- None if refused.

        A rating names its session, so one whose session is not here -- pruned by age, or a game the bundle
        did not bring -- is skipped, as is one that is not a rating (stars outside 1-5, a moment without its
        offset). A session already rated here keeps its own stars: a union, never a replacement, so importing
        a bundle twice adds nothing. One transaction: all of a bundle's ratings, or none.
        """
        if not self.keeps_ratings:
            return None
        added = skipped = 0
        try:
            with transaction(self._conn):
                for key, rows in by_key.items():
                    game = self._conn.execute("SELECT id FROM game WHERE identity_key = ?", (key,)).fetchone()
                    for row in rows if isinstance(rows, list) else []:
                        row = row if isinstance(row, dict) else {}
                        stars, started, rated = row.get("stars"), row.get("started_at"), row.get("rated_at")
                        try:
                            moment = datetime.fromisoformat(rated) if isinstance(rated, str) else None
                        except ValueError:
                            moment = None
                        if (game is None or not isinstance(stars, int) or isinstance(stars, bool)
                                or not 1 <= stars <= rules.RATE_STARS or not isinstance(started, str)
                                or moment is None or moment.tzinfo is None
                                or self._conn.execute("SELECT 1 FROM session WHERE game_id = ? AND started_at = ?",
                                                      (game[0], started)).fetchone() is None):
                            skipped += 1
                            continue
                        added += self._conn.execute(
                            "INSERT OR IGNORE INTO rating (game_id, started_at, stars, rated_at) VALUES (?, ?, ?, ?)",
                            (game[0], started, stars, moment.isoformat(timespec="seconds"))).rowcount
        except (sqlite3.Error, ValueError, TypeError) as exc:
            log.error("the bundle's ratings were refused (%s); none were kept", exc)
            return None
        return added, skipped

    def wishlist_due(self, hours: int, now: datetime | None = None) -> list[dict]:
        """The accounts marked mine whose list was never read, or not in the last `hours`."""
        if not self.keeps_wishlist:
            return []
        moment = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        since = (moment - timedelta(hours=hours)).isoformat(timespec="seconds")
        return [{"account_id": account_id, "steam_id64": steam_id64} for account_id, steam_id64 in self._conn.execute(
            "SELECT a.account_id, a.steam_id64 FROM steam_account a "
            "LEFT JOIN (SELECT account_id, MAX(read_at) AS newest FROM wishlist_read GROUP BY account_id) r "
            "ON r.account_id = a.account_id "
            "WHERE a.is_mine = 1 AND (r.newest IS NULL OR r.newest < ?) ORDER BY a.account_id", (since,))]

    def land_wishlist(self, reading: dict) -> dict | None:
        """One account's answer into the database, in one transaction -- None if refused.

        A read row first (a reading already there is left as it is, and changes nothing more).
        With items: each game gets a steam_app row if it has none (has_record 0, so the foreign
        key holds), is added the first time, or has its last_seen moved and any removed_at
        cleared; a game the account's list held and this read does not gets removed_at, the
        read's moment -- never a delete. With nothing to read (a private list answers as an empty
        one does), only the read row: nothing is taken off. A reading older than the newest one
        landed for its account is not applied.
        """
        if not self.keeps_wishlist:
            return None
        done = {"read": 0, "added": 0, "seen": 0, "returned": 0, "removed": 0}
        account_id, read_at, items = reading["account_id"], reading["read_at"], reading.get("items") or []
        state = "items" if items else "nothing"
        try:
            with transaction(self._conn):
                newest = self._conn.execute("SELECT MAX(read_at) FROM wishlist_read WHERE account_id = ?",
                                            (account_id,)).fetchone()[0]
                if newest is not None and newest >= read_at:
                    return done  # landed before, or older than what landed: nothing to do
                self._conn.execute("INSERT INTO wishlist_read (account_id, read_at, state, items) VALUES (?, ?, ?, ?)",
                                   (account_id, read_at, state, len(items)))
                done["read"] = 1
                if state == "nothing":
                    return done
                held = {appid: removed for appid, removed in self._conn.execute(
                    "SELECT appid, removed_at FROM wishlist WHERE account_id = ?", (account_id,))}
                for item in items:
                    appid = item["appid"]
                    ensure_steam_app(self._conn, appid)
                    if appid not in held:
                        done["added"] += 1
                    elif held[appid] is not None:
                        done["returned"] += 1
                    else:
                        done["seen"] += 1
                    self._conn.execute(
                        "INSERT INTO wishlist (account_id, appid, priority, date_added, first_seen, last_seen) "
                        "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (account_id, appid) DO UPDATE SET "
                        "priority = excluded.priority, date_added = COALESCE(excluded.date_added, date_added), "
                        "last_seen = excluded.last_seen, removed_at = NULL",
                        (account_id, appid, item.get("priority"), item.get("date_added"), read_at, read_at))
                listed = {item["appid"] for item in items}
                gone = [appid for appid, removed in held.items() if removed is None and appid not in listed]
                for appid in gone:
                    self._conn.execute("UPDATE wishlist SET removed_at = ? WHERE account_id = ? AND appid = ?",
                                       (read_at, account_id, appid))
                done["removed"] = len(gone)
        except (sqlite3.Error, ValueError, KeyError, TypeError) as exc:
            log.error("the wishlist of Steam account %s could not be written (%s); nothing was kept", account_id, exc)
            return None
        return done

    # -- price alerts (Phase 101) -----------------------------------------------------------

    def set_price_target(self, appid: int, cents: int, currency: str, now: datetime | None = None) -> bool:
        """A wished game's target -- one per game, a new one replacing the old. A setting, not a series: its
        rows are replaced and deleted, as purchases are. False when refused (or below version 8)."""
        if not self.keeps_alerts:
            return False
        moment = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(timespec="seconds")
        try:
            with transaction(self._conn):
                ensure_steam_app(self._conn, int(appid))
                self._conn.execute(
                    "INSERT INTO price_target (appid, cents, currency, set_at) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT (appid) DO UPDATE SET cents = excluded.cents, currency = excluded.currency, "
                    "set_at = excluded.set_at", (int(appid), int(cents), currency, moment))
        except sqlite3.Error as exc:
            log.error("the target of app %s could not be written (%s)", appid, exc)
            return False
        log.info("price target: app %s, %d %s", appid, cents, currency)
        return True

    def remove_price_target(self, appid: int) -> bool:
        """"Remove alert": the game's target taken away; the alerts it sent stay in the log."""
        if not self.keeps_alerts:
            return False
        try:
            with transaction(self._conn):
                self._conn.execute("DELETE FROM price_target WHERE appid = ?", (int(appid),))
        except sqlite3.Error as exc:
            log.error("the target of app %s could not be removed (%s)", appid, exc)
            return False
        log.info("price target: app %s removed", appid)
        return True

    def log_price_alerts(self, alerts, now: datetime | None = None) -> list:
        """The alerts a landing set off into the log, in one transaction, before anything is shown; answers the
        ones the log took. Append-only: no update and no delete of price_alert anywhere in the program. An
        alert already there (the same price and kind) is not taken again, so a message never repeats one;
        refused, nothing is taken and nothing is shown."""
        if not self.keeps_alerts or not alerts:
            return []
        moment = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(timespec="seconds")
        taken = []
        try:
            with transaction(self._conn):
                for alert in alerts:
                    cursor = self._conn.execute(
                        "INSERT INTO price_alert (appid, observed_at, kind, final_cents, currency, sent_at) "
                        "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (appid, observed_at, kind) DO NOTHING",
                        (alert.appid, alert.observed_at, alert.kind, alert.cents, alert.currency,
                         max(moment, alert.observed_at)))
                    if cursor.rowcount == 1:
                        taken.append(alert)
        except sqlite3.Error as exc:
            log.error("the price alerts could not be written (%s); none is shown", exc)
            return []
        return taken

    # -- writing ----------------------------------------------------------------------------

    def _write(self, keys: Iterable[str]) -> bool:
        keys = list(dict.fromkeys(keys))
        try:
            with transaction(self._conn):
                for key in keys:
                    write_record(self._conn, key, self._records.get(key))
        except (sqlite3.Error, ValueError, KeyError, TypeError) as exc:
            log.error("the library could not be written (%s); nothing was kept", exc)
            self._reread()
            return False
        return True

    def _reread(self) -> None:
        """The records in memory put back to what the database holds, the live dicts kept."""
        stored = read_records(self._conn)
        for key in list(self._records):
            if key not in stored:
                del self._records[key]
        for key, record in stored.items():
            mine = self._records.setdefault(key, {})
            mine.clear()
            mine.update(record)


# Every store open in this process, so that a restore can let go of the file first: Windows
# will not replace a file a connection holds (Phase 69).
_OPEN: "weakref.WeakSet[LibraryStore]" = weakref.WeakSet()


def release(path: Path | str) -> int:
    """Close every store's connection to the database at `path`; each reopens when next used."""
    target = Path(path).resolve()
    released = 0
    for store in list(_OPEN):
        if store.path.resolve() == target and store._connection is not None:
            store.close()
            released += 1
    return released


def database_path() -> Path:
    return paths.data_dir() / rules.LIBRARY_DB_FILE


def open_saved():
    """The library as it is saved, never migrating: the database, or the JSON before the switch.

    For whatever reads or writes the library outside the window -- an export without one,
    the tests. The program itself opens it through logic.migration.open_library.
    """
    if database_path().is_file():
        return LibraryStore(database_path())
    from data_access import catalog_io

    return catalog_io.Overrides()


# -- building one from the program's own data -------------------------------------------------


@dataclass
class LoadReport:
    """What the loader did, and everything it would not do."""
    misfits: list[str] = field(default_factory=list)  # records refused whole: the migration stops on any
    notes: list[str] = field(default_factory=list)  # Steam values left NULL rather than guessed
    names: Counter = field(default_factory=Counter)  # where each game's name came from
    unnamed: list[str] = field(default_factory=list)  # no name anywhere on disk
    unsourced: list[str] = field(default_factory=list)  # the store is not recorded
    recovered: list[tuple[str, str, float]] = field(default_factory=list)  # Steam links found again
    unlinked_played: list[tuple[str, int]] = field(default_factory=list)
    not_eur: list[tuple[int, str, int, str]] = field(default_factory=list)


def load(conn: sqlite3.Connection, records: dict[str, dict], entries: list[GameEntry], *,
         header: dict, steam_records: dict[str, dict], steam_summary: dict[str, dict],
         search_names: dict[str, dict], now: str | None = None,
         steam_fetched: dict[str, str] | None = None) -> LoadReport:
    """Build the tables from the records, the catalogue and the Steam caches, in one transaction.

    Every record is written by write_record -- the same code the store writes with -- each
    in a savepoint of its own: a record that does not fit is listed whole and left out,
    never coerced, and the caller decides (the migration refuses to go on). The analysis
    gets what the catalogue had lost: names from folders and Steam records, Steam links
    through the search cache at the scan's own gate -- each marked with where it came from,
    and never handed back to the program as its own. `steam_fetched` is when each record was
    fetched (Phase 70, web.steam_web.details_fetched_at); without it, the summary's time.
    """
    report = LoadReport()
    with transaction(conn):
        for appid, record in sorted(steam_records.items(), key=lambda kv: int(kv[0])):
            fetched = (steam_fetched or {}).get(str(appid)) or (steam_summary.get(str(appid)) or {}).get("fetched_at")
            try:
                with _savepoint(conn):
                    report.notes += store_steam_app(conn, int(appid), record, fetched)
            except (sqlite3.Error, ValueError, KeyError, TypeError) as exc:
                report.misfits.append(f"steam record {appid}: {exc}")
        installed = {entry.identity_key for entry in entries}
        for key in list(records) + [k for k in dict.fromkeys(e.identity_key for e in entries) if k not in records]:
            _game_row(conn, key)  # every game first, in the records' own order
        for key, record in records.items():
            try:
                with _savepoint(conn):
                    write_record(conn, key, record)
            except (sqlite3.Error, ValueError, KeyError, TypeError) as exc:
                report.misfits.append(f"record {key}: {exc}")
        try:
            with _savepoint(conn):
                write_catalog(conn, entries, roots=header.get("roots") or (), trigger="migration",
                              started_at=None, finished_at=header.get("generated_at") or now or _now())
        except (sqlite3.Error, ValueError, KeyError, TypeError) as exc:
            report.misfits.append(f"catalogue: {exc}")
        _recover(conn, installed, steam_summary, search_names, report)
        conn.execute("UPDATE meta SET migrated_from = ?, migrated_at = ? WHERE id = 1",
                     (MIGRATED_FROM, now or _now()))
    report.names = Counter(dict(conn.execute("SELECT name_origin, COUNT(*) FROM game GROUP BY name_origin")))
    report.unnamed = [r[0] for r in conn.execute(
        "SELECT identity_key FROM game g WHERE known_as IS NULL AND NOT EXISTS "
        "(SELECT 1 FROM install i WHERE i.game_id = g.id) ORDER BY id")]
    report.unsourced = [r[0] for r in conn.execute("SELECT identity_key FROM game WHERE source IS NULL ORDER BY id")]
    report.unlinked_played = [tuple(r) for r in conn.execute(
        "SELECT name, playtime_seconds FROM v_library WHERE steam_appid IS NULL AND playtime_seconds > 0 "
        "ORDER BY playtime_seconds DESC")]
    report.not_eur = [tuple(r) for r in conn.execute(
        "SELECT appid, name, price_final_cents, currency FROM steam_app "
        "WHERE currency IS NOT NULL AND currency <> 'EUR' ORDER BY appid")]
    return report


def _recover(conn, installed: set[str], summary: dict, search_names: dict, report: LoadReport) -> None:
    """Names and Steam links the catalogue forgot, for games no longer installed."""
    gate = rules.STEAM_SEARCH_MATCH_RATIO
    gone = [row for row in conn.execute(
        "SELECT id, identity_key, source, source_id, known_as, steam_appid FROM game ORDER BY id")
        if row[1] not in installed]
    for gid, key, source, source_id, known_as, appid in gone:
        name = known_as
        if name is None:
            if source == "steam" and source_id and source_id.isdigit():
                found = conn.execute("SELECT name FROM steam_app WHERE appid = ? AND has_record = 1",
                                     (int(source_id),)).fetchone()
                if found and found[0]:
                    name = found[0]
                    conn.execute("UPDATE game SET known_as = ?, name_origin = 'steam' WHERE id = ?", (name, gid))
            elif not is_uri_key(key):
                name = naming.clean_folder_name(key.rstrip("\\/").replace("/", "\\").rsplit("\\", 1)[-1])
                if name:
                    conn.execute("UPDATE game SET known_as = ?, name_origin = 'folder' WHERE id = ?", (name, gid))
        if appid is not None:
            continue
        if source == "steam" and source_id and source_id.isdigit():
            ensure_steam_app(conn, int(source_id))
            conn.execute("UPDATE game SET steam_appid = ?, appid_source = 'manifest' WHERE id = ?",
                         (int(source_id), gid))
        elif not is_uri_key(key) and name:
            hit = search_names.get(naming.normalize(name)) or {}
            if str(hit.get("appid") or "").isdigit() and float(hit.get("ratio") or 0) >= gate:
                ensure_steam_app(conn, int(hit["appid"]))
                conn.execute("UPDATE game SET steam_appid = ?, appid_source = 'recovered' WHERE id = ?",
                             (int(hit["appid"]), gid))
                report.recovered.append((name, str(hit.get("matched_name") or ""), float(hit.get("ratio") or 0)))
    for appid, record in summary.items():  # what the summary cache knows of apps with no record
        if str(appid).isdigit():
            conn.execute("UPDATE steam_app SET app_type = COALESCE(app_type, ?), fetched_at = COALESCE(fetched_at, ?) "
                         "WHERE appid = ? AND has_record = 0", (record.get("app_type"), record.get("fetched_at"), int(appid)))


# -- the check ------------------------------------------------------------------------------------


@dataclass
class Verdict:
    """The migration's own test: every count and every field, read back through the facade."""
    problems: list[str] = field(default_factory=list)
    counts: dict[str, tuple[Any, Any]] = field(default_factory=dict)  # what was given, what is there

    @property
    def passed(self) -> bool:
        return not self.problems


def _given_counts(records: dict[str, dict], entries: list[GameEntry]) -> dict[str, Any]:
    every = list(records.values())
    return {
        "records": len(records),
        "sessions": sum(len(r.get(rules.SESSIONS_KEY) or []) for r in every),
        "session minutes": sum(int(s.get("minutes") or 0) for r in every for s in r.get(rules.SESSIONS_KEY) or []),
        "playtime seconds": sum(int(r.get("playtime_seconds") or 0) for r in every),
        "save folders": sum(len(r.get(n) or []) for r in every for _i, n in SAVE_LISTS),
        "lineage": sum(len(r.get(n) or []) for r in every for _rel, n in LINEAGE_LISTS),
        "carried over": sum(1 for r in every if r.get(rules.CARRIED_TO_KEY)),
        "installs": len(entries),
    }


def counts(conn: sqlite3.Connection) -> dict[str, Any]:
    """The same figures, counted in the tables -- and what else the database holds."""
    one = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731
    return {
        "records": len(read_records(conn)),
        "sessions": one("SELECT COUNT(*) FROM session"),
        "session minutes": one("SELECT COALESCE(SUM(minutes), 0) FROM session"),
        "playtime seconds": one("SELECT COALESCE(SUM(playtime_seconds), 0) FROM game"),
        "save folders": one("SELECT COUNT(*) FROM save_folder"),
        "lineage": one("SELECT COUNT(*) FROM lineage"),
        "carried over": one("SELECT COUNT(*) FROM game WHERE carried_to IS NOT NULL"),
        "installs": one("SELECT COUNT(*) FROM install"),
        "games": one("SELECT COUNT(*) FROM game"),
        "steam apps": one("SELECT COUNT(*) FROM steam_app"),
        "genres": one("SELECT COUNT(*) FROM genre"),
        "categories": one("SELECT COUNT(*) FROM category"),
        "companies": one("SELECT COUNT(*) FROM company"),
        "foreign key violations": len(conn.execute("PRAGMA foreign_key_check").fetchall()),
    }


def verify(conn: sqlite3.Connection, records: dict[str, dict], entries: list[GameEntry]) -> Verdict:
    """Compare what the database holds with what it was built from; any difference is a problem."""
    verdict = Verdict()
    given, there = _given_counts(records, entries), counts(conn)
    for name, expected in given.items():
        verdict.counts[name] = (expected, there[name])
        if expected != there[name]:
            verdict.problems.append(f"{name}: {expected} given, {there[name]} in the database")
    if there["foreign key violations"]:
        verdict.problems.append(f"{there['foreign key violations']} foreign key violation(s)")
    keys = {r[0] for r in conn.execute("SELECT identity_key FROM game")}
    wanted = set(records) | {entry.identity_key for entry in entries}
    if keys != wanted:
        verdict.problems.append(f"identity keys differ: {sorted(keys ^ wanted)[:5]}")
    back = read_records(conn)
    for key in sorted(set(records) | set(back)):
        mine, theirs = records.get(key), back.get(key)
        if mine != theirs:
            fields_differ = sorted(n for n in set(mine or {}) | set(theirs or {})
                                   if (mine or {}).get(n) != (theirs or {}).get(n))
            verdict.problems.append(f"record {key}: {fields_differ}")
    read = [entry.to_dict() for entry in read_entries(conn)]
    gave = [entry.to_dict() for entry in entries]
    if read != gave:
        verdict.problems.append(f"catalogue entries differ: {sum(1 for a, b in zip(read, gave) if a != b)} "
                                f"of {len(gave)}, {len(read)} read back")
    return verdict
