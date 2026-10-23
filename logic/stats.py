"""Everything the stats page shows, worked out from data the launcher already holds.

No Qt in here and no I/O: it takes the merged views and hands back plain numbers, so the
arithmetic can be checked without a window on screen.

**Two different records of time, and they disagree on purpose.** `playtime_seconds` has
been accumulating since the launcher was first used; per-session history only exists from
the day Phase 20 shipped. So the lifetime total reaches back further than the chart does,
and `recording_since` is carried alongside them precisely so the page can say why rather
than leave a gap that looks like a fault.

Which entries count, decided once here rather than in the widgets:

  * **Time counts from everything.** Hiding a game takes it off the grid; it does not
    unplay it. The same goes for anything marked as a tool.
  * **Counts and disk size use the visible library** -- not hidden, not a tool -- so the
    figures agree with the "21 of 26 games" line under the grid.
  * **Most played is exe-launched only.** A Steam, Epic or Xbox game is run by its own
    client and this launcher sees none of that time, so almost every one reads zero; a
    "most played" list that ranked them against timed games would be a list of lies.
  * **Sessions count by one rule (Phase 96)**, the reports' and the recap's: a game not marked a
    tool, installed or not -- uninstalling a game does not unplay it. Until then the chart and the
    week and month figures counted the games installed now, and September 2026 read 26 hours on
    this page where the sessions held 49 (Marvel's Spider-Man 2, since uninstalled, alone 16).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime

from shared import rules
from logic import sessions

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Month:
    """One column of the chart."""

    year: int
    month: int
    minutes: int
    # False for a month that ended before this launcher started keeping session history.
    # Nothing was played *as far as we know* is a different statement from nothing was
    # played, and the chart draws the two differently.
    recorded: bool = True

    @property
    def label(self) -> str:
        return rules.MONTH_ABBREVIATIONS[self.month - 1]

    @property
    def is_january(self) -> bool:
        return self.month == 1


@dataclass(frozen=True)
class Tally:
    """A name and a number: one row of the most-played or per-source lists."""

    label: str
    value: int


@dataclass(frozen=True)
class Stats:
    minutes_this_week: int = 0
    minutes_this_month: int = 0
    lifetime_seconds: int = 0
    months: list[Month] = field(default_factory=list)
    top_games: list[Tally] = field(default_factory=list)
    sources: list[Tally] = field(default_factory=list)
    total_games: int = 0
    total_bytes: int = 0
    timed_games: int = 0
    untimed_games: int = 0
    sessions_recorded: int = 0
    recording_since: datetime | None = None
    # Phase 93: sessions seen in the process list, and the day the watch began (None: it is off).
    observed_sessions: int = 0
    watching_since: date | None = None

    @property
    def peak_month_minutes(self) -> int:
        return max((m.minutes for m in self.months), default=0)

    @property
    def has_history(self) -> bool:
        return self.sessions_recorded > 0

    @property
    def has_playtime(self) -> bool:
        return self.lifetime_seconds > 0


def last_months(now: datetime, count: int) -> list[tuple[int, int]]:
    """The (year, month) pairs ending with the one `now` falls in, oldest first."""
    year, month = now.year, now.month
    found: list[tuple[int, int]] = []
    for _ in range(max(1, count)):
        found.append((year, month))
        month -= 1
        if month == 0:
            month, year = 12, year - 1
    return list(reversed(found))


def _source_label(source: str) -> str:
    return rules.SOURCE_LABELS.get(source, source.title())


def counted_sessions(views, overrides) -> list[sessions.Session]:
    """Every session that counts, by the one rule: the store's own query (data_access/recap.py's
    `recap_counted`, the reports' `sessions`). A store without the database behind it -- a test's
    stand-in -- is read through the views, as the page was before Phase 96."""
    source = overrides.recap() if hasattr(overrides, "recap") else None
    if source is None:
        return [entry for view in views for entry in sessions.load(overrides.get(view.key))]
    found = []
    for row in source.rows("recap_counted"):
        found.append(sessions.Session(start=sessions.at_second(datetime.fromisoformat(row["started_at"])),
                                      minutes=max(0, row["minutes"]), origin=row["origin"]))
    return found


def gather(views, overrides, now: datetime | None = None, watching_since: str | None = None) -> Stats:
    """Every number the page shows, in one pass over the library. `watching_since`: the day the watch of
    the process list began (config's watch_games_since), when it is on (Phase 93)."""
    moment = now or datetime.now().astimezone()

    every_session = counted_sessions(views, overrides)
    by_month: dict[tuple[int, int], int] = {}
    for entry in every_session:
        key = (entry.start.year, entry.start.month)
        by_month[key] = by_month.get(key, 0) + entry.minutes
    played: list[Tally] = []
    counted: dict[str, int] = {}
    total_bytes = 0
    total_games = timed = untimed = 0
    lifetime = 0

    for view in views:
        # Time is time, whether or not the game is currently on the grid.
        lifetime += max(0, view.playtime_seconds)
        if view.entry.launch_kind == "exe" and view.playtime_seconds > 0:
            played.append(Tally(view.display_name, view.playtime_seconds))

        if view.hidden or view.is_non_game:
            continue
        total_games += 1
        total_bytes += max(0, view.entry.size_on_disk or 0)
        counted[view.entry.source] = counted.get(view.entry.source, 0) + 1
        if view.entry.launch_kind == "exe":
            timed += 1
        else:
            untimed += 1

    since = min((s.start for s in every_session), default=None)
    months = [
        Month(
            year=year,
            month=month,
            minutes=by_month.get((year, month), 0),
            # A month is "recorded" once history had started by the time it ended. The
            # month history began in counts, part-recorded though it is. With no history
            # at all *nothing* is recorded -- treating that as twelve quiet months would
            # tell a new user they played nothing all year, which is not what happened.
            recorded=since is not None and (year, month) >= (since.year, since.month),
        )
        for year, month in last_months(moment, rules.STATS_CHART_MONTHS)
    ]

    log.info(
        "stats: %d sessions across %d months, %d timed games, %d untimed, %s on disk",
        len(every_session),
        sum(1 for m in months if m.minutes),
        timed,
        untimed,
        total_bytes,
    )

    return Stats(
        minutes_this_week=sessions.minutes_this_week(every_session, moment),
        minutes_this_month=sessions.minutes_this_month(every_session, moment),
        lifetime_seconds=lifetime,
        months=months,
        top_games=sorted(played, key=lambda t: -t.value)[: rules.STATS_TOP_GAMES],
        sources=sorted(
            (Tally(_source_label(name), count) for name, count in counted.items()),
            key=lambda t: (-t.value, t.label),
        ),
        total_games=total_games,
        total_bytes=total_bytes,
        timed_games=timed,
        untimed_games=untimed,
        sessions_recorded=len(every_session),
        recording_since=since,
        observed_sessions=sum(1 for s in every_session if s.origin == rules.SESSION_OBSERVED),
        watching_since=_since(watching_since),
    )


def _since(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def caveats(stats: Stats) -> list[str]:
    """What these numbers cannot see, in the user's own terms.

    Written from the library rather than as fixed text, so it says "9 of your 22 games"
    instead of a general disclaimer nobody reads. An absence nobody explains reads as a
    bug; an absence stated in numbers reads as a policy.
    """
    lines: list[str] = []
    watching = stats.watching_since
    if stats.untimed_games and watching is not None:
        # Phase 93: the launcher sees them running while it is open, and records their sessions.
        lines.append(
            f"{stats.untimed_games} of your {stats.total_games} games are started through "
            f"Steam, Epic or Xbox. Since {watching:%d %b %Y} the launcher sees them running while "
            "it is open -- in the tray counts -- and records their sessions: a Steam game's hours "
            "stay Steam's own counter, an Epic or Xbox game's are the time seen. Before that day, "
            "or while the launcher was closed, nothing of them is here."
        )
    elif stats.untimed_games:
        lines.append(
            f"{stats.untimed_games} of your {stats.total_games} games are started through "
            "Steam, Epic or Xbox. Those clients time their own games and never tell this "
            "launcher, so none of that time is counted here -- with Notice games started "
            "outside the launcher on in Settings, their sessions are seen while it runs."
        )
    if stats.recording_since is not None:
        lines.append(
            "Session history begins on "
            f"{stats.recording_since:%d %b %Y}, which is as far back as the chart and the "
            "weekly figures can see. The lifetime total goes back further."
        )
    else:
        lines.append(
            "No sessions have been recorded yet. The chart fills in as you play"
            + (": games started from here, and any game you have here however you start it, "
               "while the launcher runs." if watching is not None else " games started from here.")
        )
    if stats.observed_sessions:
        lines.append(
            f"{stats.observed_sessions} of the sessions were seen rather than started here: "
            "each one's ends are within a few seconds. The chart and the weekly figures count "
            "them all, a Steam game's included; the lifetime total is this launcher's own time, "
            "and a Steam game's hours stay on Steam (the Reports tab adds the two)."
        )
    if watching is not None:
        lines.append(
            "Time is only counted while this launcher is open -- in the tray counts. A game it "
            "did not start, or started with administrator rights, is timed by watching."
        )
    else:
        lines.append(
            "Time is only counted while this launcher is open, and a game started with "
            "administrator rights is not timed at all."
        )
    return lines
