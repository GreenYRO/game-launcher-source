"""Choosing a game to suggest.

Weighted, not uniform, and every weight is a named constant in rules.py. A weight only
ever *multiplies*, so nothing is ever impossible to draw -- the point is a nudge towards
what you probably want, not a filter.

The one rule that is easy to get wrong, and is the reason this is its own module rather
than three lines in the window: **a URI game's playtime is unknown, not zero.** Steam,
Epic and Xbox games run under their own client and this launcher never sees the time, so
almost all of them sit at 0 seconds. Reading that as "barely played" would boost every one
of them at once and the Steam library would win nearly every roll. The boost applies only
to exe games, whose playtime this launcher measures itself.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from datetime import datetime, timedelta

from shared import rules

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Weighted:
    """One candidate, with the reasoning kept so it can be logged and tested."""

    view: object
    weight: float
    reasons: tuple[str, ...]


def eligible(views: list) -> list:
    """Everything the user can actually see: no hidden entries, no demos or tools.

    And nothing they marked as dropped: they gave up on it, and saying so is the whole
    point of the mark.
    """
    return [
        v for v in views
        if not v.hidden and not v.is_non_game and v.status != rules.STATUS_DROPPED
    ]


def weigh(view, now: datetime | None = None) -> Weighted:
    weight = rules.PICK_BASE_WEIGHT
    reasons: list[str] = []

    played = view.last_played
    if played is not None:
        moment = now or datetime.now().astimezone()
        if played.tzinfo is None:
            played = played.astimezone()
        if moment - played <= timedelta(days=rules.PICK_RECENT_DAYS):
            weight *= rules.PICK_RECENT_FACTOR
            reasons.append(f"played in the last {rules.PICK_RECENT_DAYS} days")

    if view.entry.launch_kind == "exe":
        if view.playtime_seconds < rules.PICK_BARELY_PLAYED_UNDER_S:
            weight *= rules.PICK_BARELY_PLAYED_FACTOR
            reasons.append("barely played")
    else:
        weight *= rules.PICK_UNKNOWN_PLAYTIME_FACTOR
        reasons.append("playtime unknown (runs under its own launcher)")

    if view.favorite:
        weight *= rules.PICK_FAVORITE_FACTOR
        reasons.append("a favorite")

    if view.status == rules.STATUS_FINISHED:
        weight *= rules.PICK_FINISHED_FACTOR
        reasons.append("finished")

    return Weighted(view=view, weight=weight, reasons=tuple(reasons))


def weights(views: list, now: datetime | None = None) -> list[Weighted]:
    return [weigh(view, now) for view in eligible(views)]


def choose(views: list, avoid_key: str = "", now: datetime | None = None,
           rng: random.Random | None = None):
    """Pick a game. Returns a GameView, or None when there is nothing to pick from.

    `avoid_key` is the previous pick: pressing the button again must never land on the
    same game twice running. It is only honoured while something else remains -- with a
    one-game library, that game is the only possible answer.
    """
    candidates = weights(views, now)
    if not candidates:
        log.info("nothing to pick from")
        return None

    remaining = [c for c in candidates if c.view.key != avoid_key] or candidates
    total = sum(c.weight for c in remaining)
    if total <= 0:  # every weight zeroed out somehow; fall back to an even draw
        log.warning("all weights came out at zero; picking evenly")
        chosen = (rng or random).choice(remaining)
    else:
        roll = (rng or random).uniform(0, total)
        running = 0.0
        chosen = remaining[-1]
        for candidate in remaining:
            running += candidate.weight
            if roll <= running:
                chosen = candidate
                break

    log.info(
        "picked %s (weight %.2f of %.2f across %d games)%s",
        chosen.view.display_name,
        chosen.weight,
        total,
        len(remaining),
        f" -- {', '.join(chosen.reasons)}" if chosen.reasons else "",
    )
    return chosen.view
