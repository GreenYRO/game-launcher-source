"""The weekly price observation (Phase 73): which apps are due, asking the store, landing the rows.

The shape is the Steam projection's (Phase 70) -- the network on the scan thread, the database
on the GUI thread afterwards -- with one step before it:

  1. `due`, on the GUI thread, before a window scan starts: the apps whose newest price is
     older than rules.PRICE_REFRESH_DAYS, or that have none, the oldest first. Handed to the
     scan as an argument -- never through config.json, where a passing value must not be saved.
     The network off, or a database that keeps no prices: nothing is due.
  2. `observe`, on the scan thread: web.steam_web asks the store, a batch per request, and
     writes what it answered to the hand-off file in cache/.
  3. `land`, on the GUI thread, after the scan's findings and the Steam projection: the
     observations go into price_snapshot; those in the database leave the hand-off, and one
     that did not land stays for the next scan.

Only the window's scans observe prices; scanner.py's command line does not. No SQL here: the
store writes, this module decides what goes in.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from shared import paths
from shared import rules
from web import steam_web

log = logging.getLogger(__name__)


@dataclass
class Landed:
    """What one landing did."""
    landed: int = 0  # observations now in the database (new, or there already)
    fresh: list = field(default_factory=list)  # (appid, observed_at) of the ones this landing added (Phase 101)
    kept: int = 0  # observations left in the hand-off for the next scan
    refused: dict = field(default_factory=dict)  # (appid, observed_at) -> why


def due(store, allow_network: bool, say: bool = True) -> list[int]:
    """The apps to ask the store about in the next scan, the oldest-observed first.

    `say=False` is the tick's question (Phase 92), every half hour: the answer is logged at debug, not
    as "this scan" -- no scan may follow."""
    if not allow_network:
        if say:
            log.info("prices: none asked for this scan -- the network is off")
        return []
    # A game on a wishlist is asked for every day (Phase 86, the user's yes): a sale is over in a
    # week or two, and the weekly look could miss it.
    found = (store.prices_due(rules.PRICE_REFRESH_DAYS, wishlist_hours=rules.WISHLIST_PRICE_HOURS)
             if hasattr(store, "prices_due") else None)
    if found is None:
        if say:
            log.info("prices: none asked for this scan -- this library keeps no prices")
        return []
    # Every scan says it, zero included (Phase 74): "how many prices did this scan look at" is a
    # question the log must answer even in the six days a week when the answer is none.
    (log.info if say else log.debug)(
        "prices: %d app(s) due for a price %s (none seen in %d days, or %d hours for a wishlist game)",
        len(found), "this scan" if say else "(the tick asked)", rules.PRICE_REFRESH_DAYS, rules.WISHLIST_PRICE_HOURS)
    return list(found)


def observe(appids: list[int], cache_dir: str | None = None) -> int:
    """The scan thread's half: ask the store and write the hand-off. Never raises."""
    if not appids:
        return 0
    try:
        return steam_web.observe_prices(appids, str(paths.cache_dir()) if cache_dir is None else cache_dir)
    except Exception as exc:  # noqa: BLE001 -- a price must never cost a scan its result
        log.exception("price observation failed, the scan goes on without it: %s", exc)
        return 0


def land(store, cache_dir: str | None = None) -> Landed:
    """The window's half: the hand-off's observations into the database, then out of the hand-off."""
    done = Landed()
    cache_dir = str(paths.cache_dir()) if cache_dir is None else cache_dir
    rows = steam_web.price_handoff(cache_dir)
    if not rows:
        return done
    if not getattr(store, "keeps_prices", False):
        done.kept = len(rows)  # a database that keeps no prices yet: they wait for one that does
        log.info("prices: %d observation(s) wait -- this library keeps no prices", len(rows))
        return done
    held = store.observation_keys() or set()  # what was there before: the price alerts judge only the new
    landed, done.refused = store.add_observations(rows)
    done.fresh = sorted(key for key in landed if key not in held)
    remaining = [row for row in rows if (row.get("appid"), row.get("observed_at")) not in landed]
    steam_web.write_price_handoff(cache_dir, remaining)
    done.landed, done.kept = len(rows) - len(remaining), len(remaining)
    log.info("prices: %d observation(s) landed in the library, %d kept for the next scan",
             done.landed, done.kept)
    for key, why in done.refused.items():
        log.warning("prices: the observation %s was refused (%s)", key, why)
    return done
