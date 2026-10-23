"""Snapshots of the two files that cannot be regenerated.

catalog.json rebuilds itself from disk in seconds and cache/ re-downloads, so neither is
worth protecting. overrides.json and config.json are different: they hold playtime, chosen
artwork, custom names, hidden flags, the scan roots and the SteamGridDB key, and nothing
anywhere else can reconstruct them. Everything in this module exists so that a crash, a
bug, or a bad later phase cannot take them.

One snapshot is one folder, `backups\\<timestamp>\\`, holding a plain copy of each file.
A folder rather than an archive because it can be opened and read by eye, and restoring is
then just a copy back.

Since Phase 68 a snapshot also holds the library database, when there is one: a copy made
through SQLite's own backup, never a file copy of a database that may be open, and judged
"unchanged" by what it holds rather than by its bytes -- SQLite reuses pages, so a change
undone leaves other bytes behind (measured in Phase 63).

`atomic_write` lives here too. It is the other half of the same promise: a snapshot is no
use if the live file can be left half-written by a crash mid-save.
"""

from __future__ import annotations

import logging
import os
import shutil
import stat
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from shared import paths
from shared import rules

log = logging.getLogger(__name__)


def atomic_write(path: Path, text: str) -> bool:
    """Write via a temp file in the same directory, then replace in one step.

    Same directory on purpose: os.replace is only atomic within a filesystem, and a temp
    folder can easily be on another drive.
    """
    temp = path.with_suffix(path.suffix + ".tmp")
    try:
        temp.write_text(text, encoding="utf-8", newline="\n")
        os.replace(temp, path)
    except OSError as exc:
        log.error("could not write %s: %s", path, exc)
        try:
            temp.unlink(missing_ok=True)
        except OSError as cleanup_exc:
            log.error("could not remove temp file %s: %s", temp, cleanup_exc)
        return False
    return True


# -- where things live -------------------------------------------------------------------


def backup_dir() -> Path:
    return paths.data_dir() / rules.BACKUP_DIRNAME


def protected_paths() -> list[Path]:
    return [paths.data_dir() / name for name in rules.PROTECTED_FILES]


def database_path() -> Path:
    return paths.data_dir() / rules.LIBRARY_DB_FILE


def _same_database(live: Path, copy: Path) -> bool:
    if live.is_file() != copy.is_file():
        return False
    if not live.is_file():
        return True
    from data_access import library_db  # here, not above: only needed once a database exists

    try:
        return library_db.file_fingerprint(live) == library_db.file_fingerprint(copy)
    except Exception as exc:  # noqa: BLE001 -- an unreadable copy is a reason to take a new one
        log.warning("could not compare %s with its last copy (%s); taking a new one", live.name, exc)
        return False


@dataclass(frozen=True)
class Snapshot:
    """One folder of copies, plus what it turned out to contain."""

    path: Path
    taken: datetime
    files: tuple[str, ...]
    size: int

    @property
    def stamp(self) -> str:
        return self.path.name


def _parse_stamp(name: str) -> datetime | None:
    """Read a folder name back into a time, tolerating the same-second suffix.

    Two snapshots inside one second get names like `..._04-51-42` and `..._04-51-42-1`.
    Without the second attempt here the suffixed one parses as nothing, which would make it
    invisible to the list, to the rotation and to restore -- an orphan folder that grows
    forever. That is exactly what the tests caught.
    """
    for candidate in (name, name.rpartition("-")[0]):
        try:
            return datetime.strptime(candidate, rules.BACKUP_STAMP_FORMAT)
        except ValueError:
            continue
    return None


def list_snapshots() -> list[Snapshot]:
    """Every snapshot on disk, newest first. Anything unrecognised is ignored, not deleted."""
    root = backup_dir()
    if not root.is_dir():
        return []
    found: list[Snapshot] = []
    for child in root.iterdir():
        if not child.is_dir():
            continue
        taken = _parse_stamp(child.name)
        if taken is None:
            log.debug("ignoring %s: not a snapshot folder", child)
            continue
        files = tuple(sorted(f.name for f in child.iterdir() if f.is_file()))
        size = sum(f.stat().st_size for f in child.iterdir() if f.is_file())
        found.append(Snapshot(path=child, taken=taken, files=files, size=size))
    # The name breaks ties: two snapshots in the same second share a timestamp, and the
    # suffixed one is the later of the two.
    return sorted(found, key=lambda s: (s.taken, s.path.name), reverse=True)


# -- taking one --------------------------------------------------------------------------


def _unchanged_since(newest: Snapshot | None) -> bool:
    """True when every protected file is byte-identical to its copy in `newest`.

    Without this, opening the launcher five times on a quiet evening would push every
    older snapshot out of the recent tier while changing nothing.
    """
    if newest is None:
        return False
    for live in protected_paths():
        copy = newest.path / live.name
        if live.is_file() != copy.is_file():
            return False
        if live.is_file() and live.read_bytes() != copy.read_bytes():
            return False
    return _same_database(database_path(), newest.path / rules.LIBRARY_DB_FILE)


def snapshot(reason: str = "startup", now: datetime | None = None) -> Snapshot | None:
    """Copy the protected files aside. Returns None when there was nothing new to save.

    Never raises: a launcher that will not open because a backup failed would be a worse
    bug than the one this is guarding against.
    """
    existing = list_snapshots()
    if _unchanged_since(existing[0] if existing else None):
        log.info("backup skipped (%s): nothing has changed since %s", reason, existing[0].stamp)
        return None

    live = [p for p in protected_paths() if p.is_file()]
    database = database_path()
    if not live and not database.is_file():
        log.info("backup skipped (%s): neither protected file exists yet", reason)
        return None

    moment = now or datetime.now()
    folder = backup_dir() / moment.strftime(rules.BACKUP_STAMP_FORMAT)
    # A second snapshot inside the same second would collide; walk forward rather than
    # overwrite, because the one being overwritten could be the good copy.
    suffix = 1
    while folder.exists():
        folder = backup_dir() / f"{moment.strftime(rules.BACKUP_STAMP_FORMAT)}-{suffix}"
        suffix += 1

    try:
        folder.mkdir(parents=True)
        for source in live:
            shutil.copy2(source, folder / source.name)
        if database.is_file():
            from data_access import library_db

            library_db.copy_database(database, folder / database.name)
            live.append(database)
    except Exception as exc:  # noqa: BLE001 -- never raises: see the docstring
        log.error("could not write the backup %s: %s", folder, exc)
        return None

    log.info("backup (%s): %s holds %s", reason, folder.name, ", ".join(p.name for p in live))
    prune()
    return next((s for s in list_snapshots() if s.path == folder), None)


# -- rotation ----------------------------------------------------------------------------


def snapshot_or_newest(reason: str) -> Snapshot | None:
    """The files as they are now, held in a snapshot: a new one, or the newest when nothing has changed since it
    -- it already holds them (Phase 105: the undo of filling missing covers). None only when neither could be."""
    taken = snapshot(reason)
    if taken is not None:
        return taken
    existing = list_snapshots()
    return existing[0] if existing and _unchanged_since(existing[0]) else None


def keepers(snapshots: list[Snapshot]) -> set[Path]:
    """Which snapshots the two-tier rule protects. Newest-first input."""
    keep = {s.path for s in snapshots[: rules.BACKUP_KEEP_RECENT]}

    first_of_day: dict[object, Snapshot] = {}
    for snap in snapshots:  # newest first, so the last write for a date is its earliest
        first_of_day[snap.taken.date()] = snap
    for day in sorted(first_of_day, reverse=True)[: rules.BACKUP_KEEP_DAILY_DAYS]:
        keep.add(first_of_day[day].path)
    return keep


def _clear_read_only(func, path, exc) -> None:
    """rmtree's error handler: a read-only file or folder loses the mark and is tried again.

    Windows will not remove a folder that carries the ReadOnly attribute, even an empty one,
    and on this machine most folders made from 6 to 10 October 2026 carry it -- set by
    nothing in the launcher. Without this, every old snapshot was emptied and its folder
    left behind, listed by the restore dialog as a snapshot holding nothing. Anything else
    goes back to the caller, which logs it.
    """
    if not isinstance(exc, PermissionError):
        raise exc
    os.chmod(path, stat.S_IWRITE)
    func(path)


def prune() -> list[Path]:
    snapshots = list_snapshots()
    keep = keepers(snapshots)
    removed = []
    for snap in snapshots:
        if snap.path in keep:
            continue
        try:
            shutil.rmtree(snap.path, onexc=_clear_read_only)
            removed.append(snap.path)
        except OSError as exc:
            log.warning("could not remove the old backup %s: %s", snap.path, exc)
    if removed:
        log.info("removed %d old backup(s)", len(removed))
    return removed


# -- putting one back ----------------------------------------------------------------------


def restore(snap: Snapshot) -> tuple[bool, str]:
    """Put a snapshot's files back, after snapshotting what is there now.

    The safety snapshot first is the whole point: restoring is itself a destructive act,
    and the state being replaced might turn out to be the one that was wanted.
    """
    before = snapshot(reason="before-restore")
    sources = [snap.path / name for name in rules.PROTECTED_FILES]
    sources = [s for s in sources if s.is_file()]
    held = snap.path / rules.LIBRARY_DB_FILE
    if not sources and not held.is_file():
        return False, f"{snap.stamp} contains none of the files this restores."

    restored = []
    for source in sources:
        target = paths.data_dir() / source.name
        try:
            # Through a temp file in the destination directory, so a failure part way
            # cannot leave the live file truncated.
            temp = target.with_suffix(target.suffix + ".tmp")
            shutil.copy2(source, temp)
            os.replace(temp, target)
            restored.append(source.name)
        except OSError as exc:
            log.error("could not restore %s: %s", source.name, exc)
            return False, f"{source.name} could not be restored: {exc}"
    rebuilt = ""
    if held.is_file() or database_path().is_file():
        from data_access import library_db

        library_db.release(database_path())  # Windows will not replace or move an open file
    if held.is_file():
        # Put back through SQLite's backup into a temporary file, renamed into place.
        try:
            library_db.put_back(held, database_path())
            restored.append(held.name)
        except Exception as exc:  # noqa: BLE001 -- reported, as a failed copy above is
            log.error("could not restore %s: %s", held.name, exc)
            return False, f"{held.name} could not be restored: {exc}"
    elif database_path().is_file() and rules.PROTECTED_FILES[0] in restored:
        # A snapshot from before the switch holds the records as overrides.json and no
        # database. Put back as files alone they would change nothing the program shows, so
        # the database goes aside -- the snapshot just taken holds a copy of it -- and the
        # next opening rebuilds it from them, through the migration and its check (Phase 69).
        aside = paths.data_dir() / rules.MIGRATED_DIRNAME / f"{(before.stamp if before else 'replaced')}-replaced"
        try:
            # What the last scan found goes back out as catalog.json first, so the rebuilt
            # library still knows which games are installed before the next scan runs.
            from data_access import catalog_io

            reader = library_db.connect(database_path())
            try:
                found = library_db.read_entries(reader)
            finally:
                reader.close()
            catalog_io.save_catalog(found, path=paths.data_dir() / "catalog.json")
            aside.mkdir(parents=True, exist_ok=True)
            os.replace(database_path(), aside / rules.LIBRARY_DB_FILE)
        except Exception as exc:  # noqa: BLE001 -- a database unreadable here is reported, not raised
            log.error("could not set the library database aside: %s", exc)
            return False, f"The library database could not be set aside to rebuild it: {exc}"
        rebuilt = " The library database will be built again from them."

    kept = f" Your current files were saved as {before.stamp} first." if before else ""
    log.info("restored %s from %s%s", ", ".join(restored), snap.stamp, " (the database set aside)" if rebuilt else "")
    named = " and ".join(restored) if len(restored) < 3 else f"{', '.join(restored[:-1])} and {restored[-1]}"
    return True, f"Restored {named} from {snap.stamp}.{rebuilt}{kept}"
