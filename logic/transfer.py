"""Carrying a library between machines.

The installer deliberately contains nothing personal, so this is the other half: one zip
holding the two files that cannot be regenerated, plus the artwork they point at.

    manifest.json     format version, when it was made, what is inside
    config.json       preferences, scan folders, and the SteamGridDB key unless left out
    overrides.json    playtime, chosen artwork, renames, hidden flags
    art/...           only the images an override actually points at

Everything inside is a relative path. An absolute path from another machine is worthless
here, so covers and banners are rewritten to `art/<name>` on the way out and turned back
into local absolute paths on the way in.

Import never deletes. Imported records win where both machines know the same game, local
records the bundle has never heard of are left exactly as they were, and a backup is taken
before any of it.

Since Phase 65 the records come from the store and go back through it (`export_records`,
`import_records`), and the settings through `config_io`: this module decides what goes
into a bundle and how one is merged, and opens none of the launcher's own files.
"""

from __future__ import annotations

import json
import logging
import shutil
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from data_access import backups
from data_access import catalog_io
from data_access import config_io
from data_access import library_db
from shared import paths
from shared import rules
from logic import sessions
from shared.models import ROLE_BANNER, ROLE_COVER

log = logging.getLogger(__name__)

ART_KEYS = (ROLE_COVER, ROLE_BANNER)


@dataclass
class ExportReport:
    ok: bool
    message: str
    path: Path | None = None
    games: int = 0
    art_files: int = 0
    includes_key: bool = False
    purchases: int = 0  # Phase 74
    ratings: int = 0  # Phase 102


@dataclass
class ImportReport:
    ok: bool
    message: str
    added: int = 0
    overwritten: list[str] = field(default_factory=list)
    matched: int = 0
    dormant: int = 0
    art_files: int = 0
    backup: str = ""
    purchases: int = 0  # new here (Phase 74); a purchase already here is not counted
    purchases_skipped: int = 0  # in the bundle, but this library keeps none (an upgrade refused)
    ratings: int = 0  # new here (Phase 102); a session already rated here keeps its stars
    ratings_skipped: int = 0  # their session is not in this library, or it keeps none


# -- reading what is here ------------------------------------------------------------------


def _store(store):
    """The window's store when it hands one over; otherwise the library as it is saved --
    the database since the switch (Phase 69), opened here and closed again after."""
    return (library_db.open_saved(), True) if store is None else (store, False)


def art_files(games: dict) -> dict[str, str]:
    """Absolute art path -> the name it gets inside the bundle.

    Only files an override points at. The rest of cache/ is downloaded art that any machine
    can fetch again, and including it would turn a 200 KB bundle into hundreds of megabytes.
    """
    mapping: dict[str, str] = {}
    used: set[str] = set()
    for record in games.values():
        for key in ART_KEYS:
            source = record.get(key)
            if not isinstance(source, str) or not source or source in mapping:
                continue
            if not Path(source).is_file():
                log.warning("skipping %s: the file is gone", source)
                continue
            name = Path(source).name
            stem, suffix = Path(name).stem, Path(name).suffix
            counter = 2
            while name in used:  # two folders can hold the same file name
                name = f"{stem}-{counter}{suffix}"
                counter += 1
            used.add(name)
            mapping[source] = name
    return mapping


# -- out ------------------------------------------------------------------------------------


def default_name(now: datetime | None = None) -> str:
    stamp = (now or datetime.now()).strftime("%Y-%m-%d")
    return f"game-launcher-library-{stamp}{rules.TRANSFER_SUFFIX}"


def export_bundle(target: Path, include_key: bool = True,
                  now: datetime | None = None, store=None) -> ExportReport:
    held, opened = _store(store)
    try:
        games = held.export_records()
        # What the user paid (Phase 74) travels as the sessions do: it is theirs, and no other
        # machine can know it. The price series does not -- it is the same observation anywhere.
        bought = held.all_purchases() if getattr(held, "keeps_prices", False) else {}
        # A session's stars (Phase 102) the same way: the user's own, and nowhere else to be had.
        rated = held.all_ratings() if getattr(held, "keeps_ratings", False) else {}
    finally:
        if opened:
            held.close()
    if not games:
        return ExportReport(False, "There is nothing to export yet.")

    config = config_io.load_saved()
    if not include_key:
        config.pop("steamgriddb_key", None)
    for key in rules.TRANSFER_LOCAL_KEYS:
        config.pop(key, None)  # this machine's window, not a preference

    art = art_files(games)
    # A copy, with every artwork path rewritten to where it will sit inside the bundle.
    portable = {"version": catalog_io.OVERRIDES_VERSION, "games": {}}
    for key, record in games.items():
        copied = dict(record)
        for art_key in ART_KEYS:
            source = copied.get(art_key)
            if isinstance(source, str) and source in art:
                copied[art_key] = f"{rules.TRANSFER_ART_DIR}/{art[source]}"
            elif isinstance(source, str) and source:
                # Pointed at a file that has since been deleted; carrying a dead absolute
                # path to another machine would be worse than carrying nothing.
                copied.pop(art_key, None)
        portable["games"][key] = copied

    manifest = {
        "format": rules.TRANSFER_FORMAT,
        "app": "Game Launcher",
        "created": (now or datetime.now()).astimezone().isoformat(timespec="seconds"),
        "games": len(games),
        "art_files": len(art),
        "includes_steamgriddb_key": bool(include_key and config.get("steamgriddb_key")),
    }
    purchase_count = sum(len(rows) for rows in bought.values())
    if purchase_count:
        manifest["purchases"] = purchase_count
    rating_count = sum(len(rows) for rows in rated.values())
    if rating_count:
        manifest["ratings"] = rating_count

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
            bundle.writestr(rules.TRANSFER_MANIFEST, json.dumps(manifest, indent=2))
            bundle.writestr(rules.TRANSFER_RECORDS_MEMBER,
                            json.dumps(portable, indent=2, ensure_ascii=False))
            bundle.writestr(rules.TRANSFER_CONFIG_MEMBER, json.dumps(config, indent=2))
            if purchase_count:  # absent when there are none: such a bundle is what it always was
                bundle.writestr(rules.TRANSFER_PURCHASES_MEMBER,
                                json.dumps({"version": 1, "games": bought}, indent=2, ensure_ascii=False))
            if rating_count:  # the same: absent when nothing is rated
                bundle.writestr(rules.TRANSFER_RATINGS_MEMBER,
                                json.dumps({"version": 1, "games": rated}, indent=2, ensure_ascii=False))
            for source, name in art.items():
                bundle.write(source, f"{rules.TRANSFER_ART_DIR}/{name}")
    except (OSError, zipfile.BadZipFile) as exc:
        log.error("could not write the bundle %s: %s", target, exc)
        return ExportReport(False, f"The file could not be written:\n{exc}")

    log.info("exported %d games, %d art files, %d purchase(s) and %d rating(s) to %s", len(games), len(art),
             purchase_count, rating_count, target)
    bought_line = f" and {purchase_count} purchase{'s' if purchase_count != 1 else ''}" if purchase_count else ""
    if rating_count:
        bought_line += f" and {rating_count} session rating{'s' if rating_count != 1 else ''}"
    return ExportReport(
        True,
        f"Exported {len(games)} games{bought_line} and {len(art)} artwork files.",
        path=target,
        games=len(games),
        art_files=len(art),
        includes_key=manifest["includes_steamgriddb_key"],
        purchases=purchase_count,
        ratings=rating_count,
    )


# -- in ---------------------------------------------------------------------------------------


def read_manifest(bundle: Path) -> tuple[dict | None, str]:
    """What a bundle says about itself, without unpacking any of it."""
    try:
        with zipfile.ZipFile(bundle) as archive:
            names = set(archive.namelist())
            if rules.TRANSFER_MANIFEST not in names:
                return None, "That file is not a Game Launcher bundle."
            manifest = json.loads(archive.read(rules.TRANSFER_MANIFEST))
    except (OSError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
        return None, f"That file could not be read:\n{exc}"
    if not isinstance(manifest, dict):
        return None, "That bundle's description is unreadable."
    version = manifest.get("format")
    if not isinstance(version, int) or version > rules.TRANSFER_FORMAT:
        return None, (
            f"That bundle was made by a newer version of Game Launcher "
            f"(format {version}). Update this copy first."
        )
    return manifest, ""


def _is_uri_key(key: str) -> bool:
    """Steam, Epic and Xbox entries are keyed by the launcher's own id, not by a path.

    Told apart by where the colon falls: `steam:730` against `c:\\games\\foo`, whose colon
    is the drive letter's.
    """
    return ":" in key and key[1:2] != ":"


def import_bundle(bundle: Path, known_keys: set[str] | None = None, store=None) -> ImportReport:
    manifest, problem = read_manifest(bundle)
    if manifest is None:
        return ImportReport(False, problem)

    # Before anything is touched, and before the merge -- this is the destructive one.
    snapshot = backups.snapshot("before-import")

    try:
        with zipfile.ZipFile(bundle) as archive:
            names = set(archive.namelist())
            incoming = json.loads(archive.read(rules.TRANSFER_RECORDS_MEMBER))
            incoming_config = (
                json.loads(archive.read(rules.TRANSFER_CONFIG_MEMBER))
                if rules.TRANSFER_CONFIG_MEMBER in names
                else {}
            )
            # A bundle made before Phase 74 has no purchases file, and imports as it always did.
            incoming_purchases = (
                json.loads(archive.read(rules.TRANSFER_PURCHASES_MEMBER)).get("games") or {}
                if rules.TRANSFER_PURCHASES_MEMBER in names
                else {}
            )
            # One made before Phase 102 has no ratings file: nothing is rated, nothing changes.
            incoming_ratings = (
                json.loads(archive.read(rules.TRANSFER_RATINGS_MEMBER)).get("games") or {}
                if rules.TRANSFER_RATINGS_MEMBER in names
                else {}
            )
            art_dir = paths.cache_dir() / rules.IMPORTED_ART_DIRNAME
            art_map = _extract_art(archive, names, art_dir)
    except (OSError, zipfile.BadZipFile, json.JSONDecodeError, KeyError) as exc:
        log.error("could not read %s: %s", bundle, exc)
        return ImportReport(False, f"The bundle could not be read:\n{exc}")

    games = incoming.get("games") if isinstance(incoming.get("games"), dict) else {}
    if not games:
        return ImportReport(False, "That bundle contains no library data.")

    store, opened = _store(store)
    try:
        return _merge_in(store, games, art_map, incoming_config, known_keys, snapshot, bundle,
                         incoming_purchases, incoming_ratings)
    finally:
        if opened:
            store.close()


def _merge_in(store, games, art_map, incoming_config, known_keys, snapshot, bundle,
              incoming_purchases=None, incoming_ratings=None) -> ImportReport:
    local_games = store.export_records()

    overwritten, added = [], 0
    merged: dict[str, dict] = {}
    for key, record in games.items():
        copied = dict(record)
        for art_key in ART_KEYS:
            relative = copied.get(art_key)
            if isinstance(relative, str) and relative in art_map:
                copied[art_key] = str(art_map[relative])
            elif isinstance(relative, str) and relative.startswith(rules.TRANSFER_ART_DIR):
                copied.pop(art_key, None)  # named a file the bundle did not carry
        # Session history is the one field that must never be replaced wholesale. Every
        # other key is a preference with a single right answer, but sessions are a record
        # of things that actually happened on each machine, and letting the imported list
        # win would quietly erase every evening played here on a game both machines know.
        existing = local_games.get(key, {})
        combined = sessions.merge(sessions.load(existing), sessions.load(copied))
        if combined:
            copied[rules.SESSIONS_KEY] = sessions.dump(sessions.prune(combined))

        if key in local_games and local_games[key] != copied:
            overwritten.append(key)
        elif key not in local_games:
            added += 1
        merged[key] = copied

    if not store.import_records(merged):
        return ImportReport(False, "The imported data could not be saved.")

    # Purchases join what is here (Phase 74) -- never replace it, never take anything away: the
    # same purchase is the same date, amount and store, so importing a bundle twice adds nothing.
    purchases_added = purchases_skipped = 0
    incoming_purchases = {k: v for k, v in (incoming_purchases or {}).items() if isinstance(v, list)}
    if incoming_purchases:
        if getattr(store, "keeps_prices", False):
            added_now = store.add_purchases(incoming_purchases)
            if added_now is None:
                return ImportReport(False, "The imported purchases could not be saved; the rest was.")
            purchases_added = added_now
        else:
            purchases_skipped = sum(len(rows) for rows in incoming_purchases.values())
            log.warning("%d purchase(s) in the bundle not imported: this library keeps none", purchases_skipped)

    # Ratings join too (Phase 102), after the records: a rating names its session, which the merge above
    # has just brought in -- and a session already rated here keeps its own stars.
    ratings_added = ratings_skipped = 0
    incoming_ratings = {k: v for k, v in (incoming_ratings or {}).items() if isinstance(v, list)}
    if incoming_ratings:
        if getattr(store, "keeps_ratings", False):
            joined = store.add_ratings(incoming_ratings)
            if joined is None:
                return ImportReport(False, "The imported ratings could not be saved; the rest was.")
            ratings_added, ratings_skipped = joined
        else:
            ratings_skipped = sum(len(rows) for rows in incoming_ratings.values())
            log.warning("%d rating(s) in the bundle not imported: this library keeps none", ratings_skipped)

    _merge_config(incoming_config)

    known = known_keys if known_keys is not None else set()
    matched = sum(1 for key in games if key in known)
    report = ImportReport(
        ok=True,
        message="",
        added=added,
        overwritten=overwritten,
        matched=matched,
        dormant=len(games) - matched,
        art_files=len(art_map),
        backup=snapshot.stamp if snapshot else "",
        purchases=purchases_added,
        purchases_skipped=purchases_skipped,
        ratings=ratings_added,
        ratings_skipped=ratings_skipped,
    )
    report.message = describe(report, len(games))
    log.info("imported %d records from %s (%s)", len(games), bundle, report.message)
    return report


def _extract_art(archive: zipfile.ZipFile, names: set[str], art_dir: Path) -> dict[str, Path]:
    """Unpack the bundle's images, returning bundle path -> local absolute path."""
    prefix = rules.TRANSFER_ART_DIR + "/"
    mapping: dict[str, Path] = {}
    wanted = [n for n in names if n.startswith(prefix) and not n.endswith("/")]
    if not wanted:
        return mapping
    art_dir.mkdir(parents=True, exist_ok=True)
    for name in wanted:
        # Never trust a path out of an archive: keep the file name and nothing else.
        safe = Path(name).name
        if not safe:
            continue
        target = art_dir / safe
        data = archive.read(name)
        if target.is_file() and target.read_bytes() == data:
            mapping[name] = target
            continue
        stem, suffix = target.stem, target.suffix
        counter = 2
        while target.is_file():  # same name, different picture
            target = art_dir / f"{stem}-{counter}{suffix}"
            counter += 1
        try:
            target.write_bytes(data)
        except OSError as exc:
            log.warning("could not unpack %s: %s", name, exc)
            continue
        mapping[name] = target
    return mapping


def _merge_config(incoming: dict) -> None:
    """Imported preferences win, except for the lists of places to look, which combine."""
    if not incoming:
        return
    current = config_io.load_saved()
    values = {}
    for key, value in incoming.items():
        if key in rules.TRANSFER_LOCAL_KEYS:
            continue  # never taken from a bundle, whichever build or hand made it
        if key in rules.TRANSFER_UNION_KEYS and isinstance(value, list):
            existing = current.get(key) if isinstance(current.get(key), list) else []
            combined = list(existing)
            combined.extend(item for item in value if item not in combined)
            values[key] = combined
        else:
            values[key] = value
    config_io.save_config(values)


def describe(report: ImportReport, total: int) -> str:
    """The completion report, in the terms the user actually cares about."""
    lines = [f"Imported {total} saved games from the bundle."]
    if report.added:
        lines.append(f"{report.added} were new here.")
    if report.overwritten:
        shown = ", ".join(_pretty_key(k) for k in report.overwritten[:5])
        more = f" and {len(report.overwritten) - 5} more" if len(report.overwritten) > 5 else ""
        lines.append(f"{len(report.overwritten)} replaced what this PC had: {shown}{more}.")
    else:
        lines.append("Nothing that was already here had to be replaced.")

    lines.append("")
    lines.append(
        f"{report.matched} match a game installed on this PC and take effect now."
    )
    if report.dormant:
        lines.append(
            f"{report.dormant} are being kept in reserve. Games from Steam, Epic and Game "
            "Pass reattach on any PC, but a game found by folder is remembered by where it "
            "sits on disk, so those only come back if it is installed to the same path — "
            "the same way your settings survive uninstalling a game."
        )
    if report.art_files:
        lines.append("")
        lines.append(f"{report.art_files} artwork files were copied in.")
    if report.purchases:
        lines.append(f"{report.purchases} purchase{'s were' if report.purchases != 1 else ' was'} added to "
                     "what you paid.")
    if report.purchases_skipped:
        lines.append(f"{report.purchases_skipped} purchases were not imported: this library keeps none.")
    if report.ratings:
        lines.append(f"{report.ratings} session rating{'s were' if report.ratings != 1 else ' was'} added.")
    if report.ratings_skipped:
        lines.append(f"{report.ratings_skipped} rating{'s were' if report.ratings_skipped != 1 else ' was'} not "
                     "imported: the session is not in this library, or it keeps no ratings.")
    if report.backup:
        lines.append(f"Your previous data was saved as backup {report.backup} first.")
    return "\n".join(lines)


def _pretty_key(key: str) -> str:
    """An identity key is a path or a launcher id; show something a person can read."""
    if _is_uri_key(key):
        return key
    return Path(key).name or key
