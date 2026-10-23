"""Copies of a game's saves: one zip per backup, kept beside the launcher's data.

A zip, not a folder of copies, so a backup is one file that is either complete or not
there at all -- it is written under a temporary name and renamed into place. Inside, each
save folder is stored under its own number, and manifest.json records where each number
came from, what the game was, when and why the copy was made, and a fingerprint of what
was copied. The fingerprint is what lets an unchanged set of saves be skipped instead of
copied again after every session.

Each game has its own folder, named after it and ending in a short hash of its identity
key, so renaming a game in the launcher never strands its older backups.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from shared import naming
from shared import paths
from shared import rules
from logic import saves
from shared import walk

log = logging.getLogger(__name__)

MANIFEST = "manifest.json"
STAMP_FORMAT = "%Y-%m-%d_%H-%M-%S"


@dataclass
class Backup:
    path: Path
    made_at: datetime
    size: int
    manifest: dict


@dataclass
class Result:
    made: Path | None = None  # the new zip, if one was written
    skipped_unchanged: bool = False
    too_big: tuple[str, ...] = ()  # folders left out for size
    missing: tuple[str, ...] = ()  # folders that are no longer there
    error: str = ""


def backups_root() -> Path:
    return paths.data_dir() / rules.SAVES_BACKUP_DIRNAME


def _hash(key: str) -> str:
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:8]


def game_folder(key: str, name: str, create: bool = False) -> Path:
    """This game's backup folder: found by the hash of its key, whatever it is called now."""
    root = backups_root()
    suffix = f" - {_hash(key)}"
    if root.is_dir():
        for child in root.iterdir():
            if child.is_dir() and child.name.endswith(suffix):
                return child
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name).strip(" .") or "game"
    folder = root / f"{safe[:60]}{suffix}"
    if create:
        folder.mkdir(parents=True, exist_ok=True)
    return folder


def list_backups(key: str, name: str) -> list[Backup]:
    """This game's backups, newest first. A zip that cannot be read is logged and left out."""
    folder = game_folder(key, name)
    if not folder.is_dir():
        return []
    found = []
    for zip_path in folder.glob("*.zip"):
        try:
            with zipfile.ZipFile(zip_path) as archive:
                manifest = json.loads(archive.read(MANIFEST))
            made_at = datetime.fromisoformat(manifest["made_at"])
        except (OSError, KeyError, ValueError, zipfile.BadZipFile) as exc:
            log.warning("ignoring unreadable save backup %s: %s", zip_path, exc)
            continue
        found.append(Backup(zip_path, made_at, zip_path.stat().st_size, manifest))
    found.sort(key=lambda b: b.made_at, reverse=True)
    return found


def latest(key: str, name: str) -> Backup | None:
    backups = list_backups(key, name)
    return backups[0] if backups else None


def _fingerprints(folders: list[str]) -> list:
    return [list(walk.fingerprint(folder) or ()) for folder in folders]


def back_up(key: str, name: str, folders: list[str], reason: str,
            now: datetime | None = None) -> Result:
    """Copy these save folders into a new zip, unless nothing changed since the last one.

    Never raises: a failed backup is reported in the result and logged, and must never
    stop the launcher -- or an uninstall that asked for it -- in some half-done state.
    """
    folders = saves.only_save_folders(folders)  # never a crash report's copy (Phase 36)
    present = [f for f in folders if os.path.isdir(f)]
    missing = tuple(f for f in folders if not os.path.isdir(f))
    too_big, kept = [], []
    for folder in present:
        _, report = walk.walk_tree(folder, max_depth=rules.SAVES_MAX_DEPTH)
        if report.total_size > rules.SAVES_BACKUP_MAX_BYTES:
            log.warning("not backing up %s: %d bytes is more than a save", folder, report.total_size)
            too_big.append(folder)
        else:
            kept.append(folder)
    if not kept:
        return Result(too_big=tuple(too_big), missing=missing)

    prints = _fingerprints(kept)
    previous = latest(key, name)
    if previous is not None and previous.manifest.get("folders") == kept \
            and previous.manifest.get("fingerprints") == prints:
        return Result(skipped_unchanged=True, too_big=tuple(too_big), missing=missing)

    moment = (now or datetime.now()).astimezone()
    folder = game_folder(key, name, create=True)
    target = folder / f"{moment.strftime(STAMP_FORMAT)}.zip"
    counter = 1
    while target.exists():
        target = folder / f"{moment.strftime(STAMP_FORMAT)}-{counter}.zip"
        counter += 1
    temporary = target.with_suffix(".zip.tmp")
    manifest = {
        "game": name,
        "key": key,
        "made_at": moment.isoformat(timespec="seconds"),
        "reason": reason,
        "folders": kept,
        "fingerprints": prints,
    }
    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(MANIFEST, json.dumps(manifest, indent=2, ensure_ascii=False))
            for number, source in enumerate(kept):
                for directory, _dirs, files in os.walk(source):
                    for file_name in files:
                        full = os.path.join(directory, file_name)
                        relative = os.path.relpath(full, source)
                        archive.write(full, f"{number}/{relative}")
        os.replace(temporary, target)
    except OSError as exc:
        log.error("save backup for %s failed: %s", name, exc)
        try:
            temporary.unlink(missing_ok=True)
        except OSError as cleanup:
            log.warning("could not remove the half-written %s: %s", temporary, cleanup)
        return Result(error=str(exc), too_big=tuple(too_big), missing=missing)

    log.info("backed up saves of %s (%s): %s", name, reason, target.name)
    _rotate(key, name)
    return Result(made=target, too_big=tuple(too_big), missing=missing)


def _rotate(key: str, name: str) -> None:
    for old in list_backups(key, name)[rules.SAVES_BACKUP_KEEP:]:
        try:
            old.path.unlink()
            log.info("rotated out an old save backup: %s", old.path.name)
        except OSError as exc:
            log.warning("could not remove old save backup %s: %s", old.path, exc)


# -- putting a copy back ---------------------------------------------------------------------


def choices(key: str, name: str, earlier_keys=(), installed=()) -> list[tuple[Backup, bool]]:
    """Copies that could go back for this game, newest first: (backup, from an earlier install).

    Its own, and those of an earlier install: one whose history was carried over to this
    game (`earlier_keys`, Phase 36), or one by the same name. A new packaged version usually
    lands in a new, versioned folder, which is a different key -- without this, the copy
    made when the old one was uninstalled could never come back.

    "The same name" was letter for letter until Phase 36, and The Witcher 3 showed why
    that is not enough: its copies were filed under GOG's "The Witcher 3: Wild Hunt -
    Game of the Year Edition" and the new build is called "The Witcher 3". It is now
    naming.same_title. A game that is still installed is never an earlier install of
    another (`installed`); the list names the game each earlier copy was made for.
    """
    own = [(b, False) for b in list_backups(key, name)]
    own_folder = game_folder(key, name)
    by_hash = {f" - {_hash(k)}" for k in earlier_keys}
    others = {os.path.normcase(k) for k in installed} - {os.path.normcase(key)}
    earlier = []
    root = backups_root()
    if root.is_dir():
        for child in root.iterdir():
            if not child.is_dir() or child == own_folder:
                continue
            carried = any(child.name.endswith(suffix) for suffix in by_hash)
            for backup in _read_folder(child):
                made_for = str(backup.manifest.get("key", ""))
                if not carried and os.path.normcase(made_for) in others:
                    continue
                if carried or naming.same_title(backup.manifest.get("game", ""), name):
                    earlier.append((backup, True))
    both = own + earlier
    both.sort(key=lambda pair: pair[0].made_at, reverse=True)
    return both


def copies_by_key(keys) -> dict[str, tuple[int, str]]:
    """For each install that has copies of its saves: how many, and the name they carry.

    Found by the hash in each folder's name, so nothing is opened but the newest zip of
    each, and that only for its name -- this runs whenever a game's page is opened.
    """
    root = backups_root()
    if not root.is_dir():
        return {}
    folders = [child for child in root.iterdir() if child.is_dir()]
    found: dict[str, tuple[int, str]] = {}
    for key in keys:
        suffix = f" - {_hash(key)}"
        folder = next((f for f in folders if f.name.endswith(suffix)), None)
        if folder is None:
            continue
        zips = sorted(folder.glob("*.zip"), key=lambda p: p.name, reverse=True)
        name = ""
        for zip_path in zips[:1]:
            try:
                with zipfile.ZipFile(zip_path) as archive:
                    name = str(json.loads(archive.read(MANIFEST)).get("game", ""))
            except (OSError, KeyError, ValueError, zipfile.BadZipFile) as exc:
                log.warning("could not read the name in %s: %s", zip_path, exc)
        if zips:
            found[key] = (len(zips), name)
    return found


def _read_folder(folder: Path) -> list[Backup]:
    found = []
    for zip_path in folder.glob("*.zip"):
        try:
            with zipfile.ZipFile(zip_path) as archive:
                manifest = json.loads(archive.read(MANIFEST))
            found.append(Backup(zip_path, datetime.fromisoformat(manifest["made_at"]),
                                zip_path.stat().st_size, manifest))
        except (OSError, KeyError, ValueError, zipfile.BadZipFile) as exc:
            log.warning("ignoring unreadable save backup %s: %s", zip_path, exc)
    return found


def targets(backup: Backup, install_dir: str) -> list[str]:
    """Where each folder in a copy goes back to.

    Where it came from -- except a save folder that lived *inside* the game's own folder,
    which follows the game to wherever it is installed now. Otherwise restoring CULTIC's
    saves after reinstalling it under a new folder name would recreate the old folder.
    """
    old_home = os.path.normcase(os.path.normpath(backup.manifest.get("key", "")))
    new_home = os.path.normpath(install_dir) if install_dir else ""
    result = []
    for folder in backup.manifest.get("folders", []):
        normal = os.path.normcase(os.path.normpath(folder))
        if new_home and old_home and os.path.isabs(old_home) and normal.startswith(old_home + os.sep):
            result.append(os.path.join(new_home, os.path.normpath(folder)[len(old_home) + 1:]))
        else:
            result.append(os.path.normpath(folder))
    return result


def restore(backup: Backup, *, key: str, name: str, install_dir: str, hwnd: int = 0,
            interactive: bool = True) -> tuple[bool, str]:
    """Put a copy back. Returns (ok, what to tell the user).

    In this order, and stopping at the first thing that fails:
    1. every path in the zip is checked to land inside its folder -- nothing is changed
       if one does not;
    2. the saves there now are copied, like any other backup;
    3. each folder there now goes to the Recycle Bin, never deleted outright;
    4. the copy is unpacked into its place, with the files' own dates, since some games
       pick the newest save by date.
    Refusing while the game runs is the caller's job: it is the one holding the tracker.
    """
    import time

    from logic import removal

    places = targets(backup, install_dir)
    try:
        with zipfile.ZipFile(backup.path) as archive:
            plan: list[tuple[str, list[tuple[zipfile.ZipInfo, str]]]] = []
            for number, place in enumerate(places):
                if not saves.could_be_save_folder(place):
                    # A copy made before Phase 36 can hold a crash report's folder. Putting
                    # it back would only queue a stale report to be sent; it is left out.
                    log.info("not restoring %s: it is not a save folder", place)
                    continue
                prefix = f"{number}/"
                base = os.path.normcase(os.path.normpath(place))
                files = []
                for member in archive.infolist():
                    if member.is_dir() or not member.filename.startswith(prefix):
                        continue
                    landing = os.path.normpath(os.path.join(place, member.filename[len(prefix):]))
                    if not os.path.normcase(landing).startswith(base + os.sep):
                        return False, f"The copy holds a file that would land outside its folder " \
                                      f"({member.filename}); nothing was changed."
                    files.append((member, landing))
                plan.append((place, files))

            present = [place for place, _files in plan if os.path.isdir(place)]
            if present:
                safety = back_up(key, name, present, "before restoring")
                if safety.error:
                    return False, f"The saves there now could not be copied first ({safety.error}), " \
                                  "so nothing was changed."

            for place, files in plan:
                if os.path.isdir(place):
                    ok, message = removal.send_to_recycle_bin(
                        place, hwnd, interactive=interactive, already_asked=True)
                    if not ok:
                        return False, f"{place} could not be moved to the Recycle Bin: {message}"
                os.makedirs(place, exist_ok=True)  # an empty save folder is still a folder
                for member, landing in files:
                    os.makedirs(os.path.dirname(landing), exist_ok=True)
                    with archive.open(member) as source, open(landing, "wb") as target:
                        target.write(source.read())
                    stamp = time.mktime(member.date_time + (0, 0, -1))
                    os.utime(landing, (stamp, stamp))
    except (OSError, zipfile.BadZipFile) as exc:
        log.error("restoring %s failed: %s", backup.path, exc)
        return False, f"Restoring failed part way: {exc}. The saves that were there are in the " \
                      "Recycle Bin and in the save backups."

    log.info("restored %s's saves from %s into %s", name, backup.path.name,
             [place for place, _files in plan])
    return True, (f"The saves from {backup.made_at.strftime('%d %b %Y, %H:%M')} are back. "
                  "What was there before is in the Recycle Bin, and copied in the save backups.")
