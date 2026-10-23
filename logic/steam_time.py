"""Steam's own playtime (Phase 75): read from Steam's files on the scan thread, landed by the window.

The shape is the price observation's (Phase 73), with a local source instead of a network one:

  1. `wanted`, on the GUI thread, before a window scan: the apps on the accounts marked mine that
     the launcher has no Steam record of, the most played first -- the scan fetches their records,
     a few a scan, so the history gets names and genres. Nothing with the network off.
  2. `read`, on the scan thread: providers.steam_userdata reads loginusers.vdf and every account's
     localconfig.vdf (local files: read with the network off too), web.steam_web fetches the
     wanted records, and the reading goes to a hand-off file in cache/.
  3. `land`, on the GUI thread, after the Steam projection: the accounts, the read rows and the
     changed counters go into the database in one transaction per reading, and what landed leaves
     the hand-off; one that did not stays for the next scan.

The Steam folder is the one providers.steam finds in the registry; not found, nothing is read --
never a guessed path. No SQL here.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from data_access import backups
from providers import steam
from providers import steam_userdata
from shared import paths
from shared import rules
from web import steam_web

log = logging.getLogger(__name__)


@dataclass
class Landed:
    """What one landing did, over every reading in the hand-off."""
    readings: int = 0  # readings now in the database
    accounts: int = 0
    reads: int = 0  # read rows added
    observations: int = 0  # counters that were new or changed
    lowered: list = field(default_factory=list)  # (account, appid, before, now): kept, and logged as odd
    kept: int = 0  # readings left in the hand-off for the next scan


def due(store) -> bool:
    """Is a reading of Steam's files wanted with this scan? Whenever the library can keep it."""
    return bool(getattr(store, "keeps_steam_time", False))


def files_changed_since(moment: float) -> bool:
    """Has Steam written an account's playtime file since `moment` (a time.time())? The tick's question
    (Phase 92): `due` is not a cadence -- it says yes whenever the library can keep Steam's hours --
    and a scan for nothing every half hour would only walk the disk. Local files, no network."""
    for path in steam_userdata.localconfig_files(steam.find_steam()):
        try:
            if os.path.getmtime(path) > moment:
                return True
        except OSError:
            continue
    return False


def wanted(store, allow_network: bool) -> list[int]:
    """The records to fetch with this scan: apps on the accounts marked mine with no record yet.

    Every one of them, the most played first: the scan fetches at most
    rules.STEAM_HISTORY_RECORDS_PER_SCAN, skipping the ones Steam has already answered "no store
    entry" for (a delisted game) -- a list cut short here could hold only those.
    """
    if not allow_network or not getattr(store, "keeps_steam_time", False):
        return []
    return store.steam_records_wanted()


def handoff_path(cache_dir: str) -> str:
    return os.path.join(cache_dir, rules.STEAM_TIME_HANDOFF_FILE)


def pending(cache_dir: str) -> list[dict]:
    """The readings the scan thread wrote and the window has not landed yet."""
    path = handoff_path(cache_dir)
    if not os.path.isfile(path):
        return []
    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("could not read %s (%s); those readings are lost -- the next scan reads again", path, exc)
        return []
    readings = payload.get("readings") if isinstance(payload, dict) else None
    return [r for r in readings if isinstance(r, dict)] if isinstance(readings, list) else []


def _keep(cache_dir: str, readings: list[dict]) -> bool:
    path = handoff_path(cache_dir)
    if not readings:
        try:
            if os.path.isfile(path):
                os.remove(path)
        except OSError as exc:
            log.error("could not empty %s: %s", path, exc)
            return False
        return True
    os.makedirs(cache_dir, exist_ok=True)
    return backups.atomic_write(Path(path), json.dumps({"readings": readings}, indent=1))


def read(records_wanted: list[int], cache_dir: str | None = None) -> int:
    """The scan thread's half: read Steam's files, fetch the wanted records, write the hand-off.

    Never raises: a reading must not cost the scan its result. Returns how many accounts were read.
    """
    cache_dir = str(paths.cache_dir()) if cache_dir is None else cache_dir
    try:
        reading = steam_userdata.read_all(steam.find_steam())
        skipped = sum(r.get("shortcuts_skipped", 0) for r in reading["reads"])
        if skipped:
            log.info("steam time: %d non-Steam shortcut(s) skipped -- no store app behind them", skipped)
        if reading["reads"]:
            _keep(cache_dir, pending(cache_dir) + [reading])
        if records_wanted:
            steam_web.fetch_records(records_wanted, cache_dir, rules.STEAM_HISTORY_RECORDS_PER_SCAN)
        return len(reading["reads"])
    except Exception as exc:  # noqa: BLE001 -- see the docstring
        log.exception("reading Steam's playtime failed, the scan goes on without it: %s", exc)
        return 0


def land(store, cache_dir: str | None = None) -> Landed:
    """The window's half: every pending reading into the database, oldest first."""
    done = Landed()
    cache_dir = str(paths.cache_dir()) if cache_dir is None else cache_dir
    readings = pending(cache_dir)
    if not readings:
        return done
    if not getattr(store, "keeps_steam_time", False):
        done.kept = len(readings)
        log.info("steam time: %d reading(s) wait -- this library keeps no Steam playtime", len(readings))
        return done
    remaining = []
    for reading in sorted(readings, key=lambda r: min((x["read_at"] for x in r.get("reads", [])), default="")):
        result = store.land_steam_time(reading)
        if result is None:
            remaining.append(reading)
            continue
        done.readings += 1
        done.accounts += result["accounts"]
        done.reads += result["reads"]
        done.observations += result["observations"]
        done.lowered += result["lowered"]
    _keep(cache_dir, remaining)
    done.kept = len(remaining)
    log.info("steam time: %d reading(s) landed -- %d account(s), %d read row(s), %d observation(s) "
             "written (a counter only when it changed); %d kept for the next scan",
             done.readings, done.accounts, done.reads, done.observations, done.kept)
    for account_id, appid, before, now in done.lowered:
        log.warning("steam time: account %s's counter for %s went down, %s -> %s minutes; kept as read",
                    account_id, appid, before, now)
    return done
