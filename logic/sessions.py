"""One game's play sessions: recording them, ageing them out, and adding them up.

A session is one exe launch, from the moment it starts until the Job Object reports itself
empty (Phase 16) -- 'launched', timed to the second. Since Phase 93 a session can also be
'observed': a game the launcher saw running in the process list, whoever started it (Steam,
Epic, Xbox, its own shortcut), each edge uncertain by one look (logic/observe.py).

Stored in overrides.json as a plain list per game:

    "sessions": [{"start": "2026-08-14T05:12:33+03:00", "minutes": 47}, ...]

and an observed one also says {"origin": "observed"}; a session that does not say was launched.

Two decisions worth stating. The live session is written into that list as it runs, on the
same banking cadence as playtime, so a crash costs at most one interval rather than the
whole evening. And the list is pruned **by age, not by count**, so the same records serve
both the short "recent sessions" list on a game's page and a twelve-month chart later.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from shared import rules

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Session:
    start: datetime
    minutes: int
    origin: str = rules.SESSION_LAUNCHED

    @property
    def end(self) -> datetime:
        return self.start + timedelta(minutes=self.minutes)


def at_second(moment: datetime) -> datetime:
    """Drop sub-second precision.

    Everything is stored with `timespec="seconds"`, so a start time that keeps its
    microseconds in memory will never match the one that comes back off disk -- and the
    live session, which is matched by start time on every banking pass, would append a new
    entry each time instead of updating the one it already wrote.
    """
    return moment.replace(microsecond=0)


def _parse(raw: dict) -> Session | None:
    stamp = raw.get("start") if isinstance(raw, dict) else None
    if not isinstance(stamp, str):
        return None
    try:
        start = datetime.fromisoformat(stamp)
    except ValueError:
        log.warning("unreadable session start %r; dropping the entry", stamp)
        return None
    if start.tzinfo is None:
        start = start.astimezone()
    start = at_second(start)
    try:
        minutes = max(0, int(raw.get("minutes", 0)))
    except (TypeError, ValueError):
        minutes = 0
    observed = raw.get(rules.SESSION_ORIGIN_KEY) == rules.SESSION_OBSERVED
    return Session(start=start, minutes=minutes,
                   origin=rules.SESSION_OBSERVED if observed else rules.SESSION_LAUNCHED)


def load(record: dict) -> list[Session]:
    """Every session on one game's override record, oldest first."""
    raw = record.get(rules.SESSIONS_KEY)
    if not isinstance(raw, list):
        return []
    found = [session for session in (_parse(item) for item in raw) if session is not None]
    return sorted(found, key=lambda s: s.start)


def dump(entries: list[Session]) -> list[dict]:
    """The list as a record holds it: an observed session says so, a launched one keeps the old shape."""
    dumped = []
    for s in sorted(entries, key=lambda s: s.start):
        item = {"start": s.start.isoformat(timespec="seconds"), "minutes": s.minutes}
        if s.origin == rules.SESSION_OBSERVED:
            item[rules.SESSION_ORIGIN_KEY] = s.origin
        dumped.append(item)
    return dumped


def prune(entries: list[Session], now: datetime | None = None) -> list[Session]:
    """Drop anything older than the keep window. Age, never count."""
    cutoff = (now or datetime.now().astimezone()) - timedelta(days=rules.SESSION_KEEP_DAYS)
    return [session for session in entries if session.start >= cutoff]


def upsert(entries: list[Session], start: datetime, minutes: int,
           origin: str = rules.SESSION_LAUNCHED) -> list[Session]:
    """Add a session, or update the one that began at `start` -- launched, or observed (Phase 93).

    Matching on the start time is what lets a live session be written repeatedly as it
    grows without ever leaving a trail of duplicates behind it.
    """
    start = at_second(start)
    kept = [session for session in entries if session.start != start]
    kept.append(Session(start=start, minutes=max(0, int(minutes)), origin=origin))
    return sorted(kept, key=lambda s: s.start)


def merge(local: list[Session], incoming: list[Session]) -> list[Session]:
    """Combine two machines' histories for the same game.

    Union by start time, keeping the longer of any pair that claims the same moment.
    Letting an imported record replace the local list outright would quietly erase every
    session played on this machine for a game both machines know.
    """
    by_start: dict[datetime, Session] = {}
    for session in list(local) + list(incoming):
        previous = by_start.get(session.start)
        if previous is None or session.minutes > previous.minutes:
            by_start[session.start] = session  # the longer, with how it was measured
    return sorted(by_start.values(), key=lambda s: s.start)


# -- reading them back -------------------------------------------------------------------


def recent(entries: list[Session], count: int) -> list[Session]:
    """The newest few, newest first."""
    return sorted(entries, key=lambda s: s.start, reverse=True)[:count]


def minutes_since(entries: list[Session], since: datetime) -> int:
    return sum(s.minutes for s in entries if s.start >= since)


def minutes_this_week(entries: list[Session], now: datetime | None = None) -> int:
    """This calendar week, counted from Monday morning rather than a rolling seven days."""
    moment = now or datetime.now().astimezone()
    midnight = moment.replace(hour=0, minute=0, second=0, microsecond=0)
    return minutes_since(entries, midnight - timedelta(days=midnight.weekday()))


def minutes_this_month(entries: list[Session], now: datetime | None = None) -> int:
    moment = now or datetime.now().astimezone()
    first = moment.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return minutes_since(entries, first)
