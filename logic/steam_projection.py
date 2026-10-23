"""The Steam projection after every scan (Phase 70).

steam_app and its satellites -- genres, categories, developers and publishers -- are a
projection of the Steam records cached on disk (cache/steam_details/<appid>.json), made once
by the migration. A scan can fetch a record that was missing, or fetch a stale one again;
`refresh` then brings the projection up to date with what is on disk, so the database's
Steam tables always say what the cache says.

Disk only: nothing is fetched here -- the scan has done that, under its own budget. Only what
changed is read: a record is projected again when the database has none for its appid, or
when the moment it was fetched is not the one its row records. On a quiet scan that is
nothing, and the cost is one look at the cache's folder.

Since Phase 73 every cached record is also one observation in the price series, dated by
the moment it was fetched: the price it carried, or that it was free, or that it offered
nothing to buy. The same function reads it as reads a price fetched this week
(steam_web.price_observation), and the insert does nothing for an observation already there,
so the first pass after the upgrade seeds the series and every later pass adds only what is
new. A database that keeps no prices (version 1) gets the projection alone.

No SQL here: the store writes, this module only decides what goes in. Called by the window on
the GUI thread, after the scan's own findings are written -- the one writer.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from shared import paths
from web import steam_web

log = logging.getLogger(__name__)


@dataclass
class Refreshed:
    """What one pass did: the appids brought up to date, the notes, and what was refused."""
    stored: list[int] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)  # values left NULL rather than guessed
    refused: dict[int, str] = field(default_factory=dict)  # left as they were, and why
    observed: int = 0  # price observations taken from the cached records (Phase 73)


def refresh(store, cache_dir: str | None = None) -> Refreshed:
    """Project every cached record the store does not hold as it is on disk."""
    done = Refreshed()
    held = store.steam_fetched()
    if held is None:  # the JSON store after a refused migration keeps none; or it cannot say now
        return done
    cache_dir = str(paths.cache_dir()) if cache_dir is None else cache_dir
    observed = store.observation_keys() if getattr(store, "keeps_prices", False) else None
    changed: dict[int, tuple[dict, str]] = {}
    observations: list[dict] = []
    for appid, moment in steam_web.details_fetched_at(cache_dir).items():
        stale = not (int(appid) in held and held[int(appid)] == moment)
        unobserved = observed is not None and (int(appid), moment) not in observed
        if not stale and not unobserved:
            continue
        record = steam_web.load_details(cache_dir, appid)
        if not record:
            continue
        if stale:
            changed[int(appid)] = (record, moment)
        if unobserved:
            row = steam_web.price_observation(appid, {"success": True, "data": record}, moment)
            if row is not None:
                observations.append(row)
            else:
                log.warning("steam projection: the cached record for %s carries a price that does not read", appid)
    if changed:
        done.notes, done.refused = store.store_steam_records(changed)
        done.stored = sorted(appid for appid in changed if appid not in done.refused)
        log.info("steam projection: %d record(s) brought up to date from the cache", len(done.stored))
        for note in done.notes:
            log.info("steam projection: %s", note)
        for appid, why in done.refused.items():
            log.warning("steam projection: the record for %s does not fit and was left as it was (%s)", appid, why)
    if observations:
        landed, refused = store.add_observations(observations)  # after the rows they refer to
        done.observed = len(landed)
        log.info("steam projection: %d price observation(s) from the cached records", done.observed)
        for key, why in refused.items():
            log.warning("steam projection: the price observation %s was refused (%s)", key, why)
    return done
