"""How was it? (Phase 102): one quiet question after a session -- explicit feedback beside the implicit hours.

Everything else the launcher measures is what was done (hours, sessions); a rating is what was thought of it. So
the question is asked rarely and answered in one tap: after a session of rules.RATE_MIN_MINUTES or more -- step 0
measured the sessions splitting there, quick starts and bounces below (the 10th percentile is 2 minutes), play
above -- launched or seen running, when no game is running any more, once a game a day, with the Settings switch
on, never over a dialog or a menu. Five stars, Skip, or no answer: only a star writes anything. A session not
rated then can be rated from its game's page for rules.RATE_LATE_DAYS; nothing older is asked for -- memory fades,
and a rating two weeks on is another thing (docs/ANALIZA.md says so).

The rules and the words; the card, the balloon and the page's stars are presentation's. No Qt, no SQL.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from shared import humanize
from shared import rules


@dataclass(frozen=True)
class Ask:
    """A session to ask about: its game (the store's key and the name shown), its start as the session row holds
    it -- the rating's key with the game -- and its length."""
    key: str
    name: str
    started_at: str
    minutes: int


def due(minutes: int, *, enabled: bool, running: bool, asked_today: bool, rated_today: bool,
        is_tool: bool) -> tuple[bool, str]:
    """Whether a session that has just ended is asked about, and why not when it is not."""
    if not enabled:
        return False, "the switch is off"
    if is_tool:
        return False, "a tool, not a game"
    if minutes < rules.RATE_MIN_MINUTES:
        return False, f"shorter than {rules.RATE_MIN_MINUTES} minutes"
    if running:
        return False, "a game is still running"
    if rules.RATE_ASK_ONCE_PER_DAY and (asked_today or rated_today):
        return False, "asked about today already"
    return True, ""


def started_text(moment: datetime) -> str:
    """A session's start as its row holds it: local time with the offset, to the second (logic/sessions.dump)."""
    return moment.isoformat(timespec="seconds")


def question(ask: Ask) -> str:
    """The card's line: "Max Payne 3, 1h 23m. How was it?"."""
    return f"{ask.name}, {humanize.playtime(ask.minutes * 60)}. How was it?"


def balloon(ask: Ask) -> str:
    """The tray's line, when the window is hidden: "How was Max Payne 3? Click to rate"."""
    return f"How was {ask.name}? Click to rate"


def thanks(stars: int) -> str:
    return f"Thanks: {stars} star{'s' if stars != 1 else ''}"


def rateable(start: datetime, now: datetime | None = None) -> bool:
    """A session late ratings may still reach: started in the last rules.RATE_LATE_DAYS."""
    now = now or datetime.now().astimezone()
    return start >= now - timedelta(days=rules.RATE_LATE_DAYS)


def last_unrated(entries, ratings: dict[str, int], now: datetime | None = None, key: str = "", name: str = ""):
    """The newest session of a game, of RATE_MIN_MINUTES or more, still rateable and not rated: what the game's
    menu offers to rate ("Rate your last session..."), or None."""
    for session in sorted(entries, key=lambda s: s.start, reverse=True):
        text = started_text(session.start)
        if session.minutes >= rules.RATE_MIN_MINUTES and rateable(session.start, now) and text not in ratings:
            return Ask(key, name, text, session.minutes)
    return None
