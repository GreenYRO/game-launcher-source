"""The recap (Phase 96): a month, or a year, in review -- the figures the library holds, shaped into a card.

No Qt and no I/O of its own: `build` takes the store's recap queries (data_access/recap.py) and a
Period and hands back a Recap, every line a humanized sentence with its raw numbers beside it, and
only the lines that have something to say. **A figure that is not known is never drawn as zero**:
the line is left out, or the footer says what was not seen.

The sessions are the ones the Stats page and report 5 count (one rule: a game not marked a tool,
installed or not), so the card's hours for a month are Stats' "played this month" and report 5's sum
for the same days -- a test holds the three equal. A period is half-open, [start, end), in local wall
time; a session counts, whole, in the period it began in.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from shared import humanize
from shared import rules
from shared import version

log = logging.getLogger(__name__)

# What a fact on the card is about; the card picks its icon by this, logic never names one.
LONGEST, WHEN, NEW, MONEY = "longest", "when", "new", "money"


@dataclass(frozen=True)
class Period:
    """A calendar month, [the 1st at 00:00, the next 1st at 00:00), local wall time -- or, with month 0,
    a calendar year, [1 January, the next 1 January)."""

    year: int
    month: int = 0

    @property
    def is_year(self) -> bool:
        return self.month == 0

    @property
    def start(self) -> datetime:
        return datetime(self.year, self.month or 1, 1)

    @property
    def end(self) -> datetime:
        if self.is_year:
            return datetime(self.year + 1, 1, 1)
        return datetime(self.year + (self.month == 12), self.month % 12 + 1, 1)

    @property
    def name(self) -> str:
        return str(self.year) if self.is_year else rules.RECAP_MONTH_NAMES[self.month - 1]

    @property
    def label(self) -> str:
        return self.name if self.is_year else f"{self.name} {self.year}"

    @property
    def key(self) -> str:
        return f"{self.year:04d}" if self.is_year else f"{self.year:04d}-{self.month:02d}"

    @property
    def noun(self) -> str:
        return "year" if self.is_year else "month"

    def previous(self) -> Period:
        if self.is_year:
            return Period(self.year - 1)
        return Period(self.year - (self.month == 1), (self.month - 2) % 12 + 1)

    def following(self) -> Period:
        if self.is_year:
            return Period(self.year + 1)
        return Period(self.year + (self.month == 12), self.month % 12 + 1)

    def months(self) -> list[Period]:
        """A year's twelve months; a month is its own one."""
        return [Period(self.year, m) for m in range(1, 13)] if self.is_year else [self]

    def holds(self, moment: datetime) -> bool:
        """Is a local wall time inside [start, end)?"""
        return self.start <= moment.replace(tzinfo=None) < self.end

    def bounds(self) -> dict:
        """The query parameters: local wall time as session.started_local holds it, the days a purchase
        is dated by, and UTC for price_snapshot.observed_at -- each bound half-open."""
        return {"start": _wall(self.start), "end": _wall(self.end),
                "start_day": self.start.date().isoformat(), "end_day": self.end.date().isoformat(),
                "start_utc": _utc(self.start), "end_utc": _utc(self.end)}

    @property
    def file_name(self) -> str:
        return rules.RECAP_FILE_NAME.format(app=version.APP_NAME, period=self.label)


def _wall(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%S")


def _utc(moment: datetime) -> str:
    """A local wall time as the UTC text price_snapshot keeps; a naive time is read as this PC's."""
    return moment.astimezone().astimezone(timezone.utc).isoformat(timespec="seconds")


def _local(now: datetime | None) -> datetime:
    return (now or datetime.now().astimezone()).astimezone().replace(tzinfo=None)


def this_month(now: datetime | None = None) -> Period:
    moment = _local(now)
    return Period(moment.year, moment.month)


def last_month(now: datetime | None = None) -> Period:
    return this_month(now).previous()


def this_year(now: datetime | None = None) -> Period:
    return Period(_local(now).year)


def choices(now: datetime | None = None) -> list[tuple[str, Period]]:
    """The dialog's chooser, in its order: Last year only in January, when the year has just ended."""
    found = [("This month", this_month(now)), ("Last month", last_month(now)), ("This year", this_year(now))]
    if _local(now).month == 1:
        found.append(("Last year", this_year(now).previous()))
    return found


def offers(now: datetime | None, offered_month: str | None, offered_year: str | None, sessions_in) -> list:
    """The recaps ready to be offered and not offered yet: (config key, its value, the words) for each.

    The month that just ended, once, when it holds a session. The year, once, from RECAP_YEAR_OFFER_DAY
    (15 December) to the end of January -- in January the year just ended. `sessions_in(period)` counts.
    """
    found = []
    month = last_month(now)
    if offered_month != month.key and sessions_in(month) > 0:
        found.append((rules.RECAP_OFFERED_KEY, month.key, f"Your {month.name} recap is ready: Stats, Share as image"))
    moment = _local(now)
    year = (Period(moment.year) if (moment.month, moment.day) >= rules.RECAP_YEAR_OFFER_DAY else
            Period(moment.year - 1) if moment.month == 1 else None)
    if year is not None and offered_year != year.key and sessions_in(year) > 0:
        found.append((rules.RECAP_YEAR_OFFERED_KEY, year.key, f"Your {year.name} recap is ready: Stats, Share as image"))
    return found


@dataclass(frozen=True)
class Game:
    name: str
    minutes: int
    sessions: int
    share: float  # its minutes against the first game's, 0..1: the bar under its cover
    time: str
    identity_key: str
    steam_appid: int | None
    cover_path: str | None
    installed: bool


@dataclass(frozen=True)
class Fact:
    kind: str
    label: str
    value: str
    detail: str = ""
    # A list in the detail (the new games): the card names as many as fit, then "and N more".
    names: tuple[str, ...] = ()
    # The detail in fewer words, for a narrow card (a year's three in a row) where the whole does not fit.
    short: str = ""


def listing(names, room: int) -> str:
    """The first `room` names, then how many more: "A, B and 5 more"; all of them when they are few."""
    shown = list(names[:max(1, room)])
    more = len(names) - len(shown)
    return ", ".join(shown) + (f" and {more:,} more" if more else "")


@dataclass(frozen=True)
class MonthBar:
    """One of a year's twelve months on its card: as Stats' chart draws them, faint when not recorded."""

    label: str
    minutes: int
    recorded: bool


@dataclass(frozen=True)
class Recap:
    period: Period
    running: bool  # the period has not ended yet
    title: str
    minutes: int = 0
    sessions: int = 0
    games: int = 0
    observed: int = 0
    headline: str = ""
    unit: str = ""
    counts: tuple[str, ...] = ()
    comparison: str = ""
    top: tuple[Game, ...] = ()
    # One game only: the lines beside its cover, in place of the facts about sessions.
    single: tuple[str, ...] = ()
    facts: tuple[Fact, ...] = ()
    empty_lines: tuple[str, ...] = ()
    months: tuple[MonthBar, ...] = ()  # a year's twelve
    busiest: str = ""  # a year's busiest month, in words
    footer: tuple[str, ...] = ()
    raw: dict = field(default_factory=dict)  # the numbers behind the words, for tests and the log

    @property
    def empty(self) -> bool:
        return self.sessions == 0


def _parse(text: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(text) if text else None
    except ValueError:
        log.warning("recap: unreadable local time %r", text)
        return None


def _plural(n: int, one: str, many: str | None = None) -> str:
    return f"{n:,} {one if n == 1 else (many or one + 's')}"


def headline(minutes: int) -> tuple[str, str]:
    """The big number: minutes under an hour, hours with one decimal under ten, whole hours after."""
    if minutes < 60:
        return str(minutes), "min"
    hours = minutes / 60
    if hours < 10:
        return f"{hours:.1f}".removesuffix(".0"), "h"
    return f"{round(hours):,}", "h"


def amount(minutes: int) -> str:
    """A difference in time, in the card's words: minutes under an hour, whole hours after."""
    return f"{minutes} min" if minutes < 60 else f"{round(minutes / 60):,} h"


def _day(moment: datetime, weekday: bool = True) -> str:
    text = f"{moment.day} {rules.MONTH_ABBREVIATIONS[moment.month - 1]}"
    return f"{rules.ANALYSIS_WEEKDAYS[moment.weekday()]} {text}" if weekday else text


def _part(hours: list[dict]) -> tuple[str, int]:
    """The part of the day the most sessions began in (ties: more minutes, then the earlier part)."""
    best, best_key = "", None
    for first, last, words in rules.RECAP_DAY_PARTS:
        rows = [r for r in hours if first <= r["hour"] < last]
        starts, minutes = sum(r["sessions"] for r in rows), sum(r["minutes"] or 0 for r in rows)
        key = (starts, minutes)
        if starts and (best_key is None or key > best_key):
            best, best_key = words, key
    return best, (best_key or (0, 0))[0]


def _weekday(rows: list[dict]) -> str:
    """The weekday with the most minutes (ties: more sessions, then Monday first)."""
    if not rows:
        return ""
    order = {d: i for i, d in enumerate((1, 2, 3, 4, 5, 6, 0))}
    best = max(rows, key=lambda r: (r["minutes"] or 0, r["sessions"], -order[r["weekday"]]))
    return rules.RECAP_WEEKDAYS[best["weekday"]]


def _money(rows: list[dict]) -> str:
    """What was paid, each currency on its own: nothing is ever converted."""
    sums: dict[str, int] = {}
    for row in rows:
        sums[row["currency"]] = sums.get(row["currency"], 0) + row["paid_cents"]
    return " + ".join(humanize.money(cents, currency) for currency, cents in sorted(sums.items()))


def _measured(sessions: int, observed: int) -> str:
    within = f"each end within {rules.WATCH_PROCESS_POLL_S} s"
    if not observed:
        return f"From {_plural(sessions, 'session')} the launcher timed."
    if observed == sessions:
        return f"From {_plural(sessions, 'session')} the launcher watched, {within}."
    return (f"From {_plural(sessions, 'session')} the launcher timed or watched; {observed:,} "
            f"{'was' if observed == 1 else 'were'} watched, {within}.")


STEAM_LINE = "Steam time played while the launcher was not running is not included."


def build(source, period: Period, now: datetime | None = None) -> Recap:
    """The card for one period, from the store's recap queries (`LibraryStore.recap()`)."""
    moment = _local(now)
    running = period.holds(moment)
    bounds = period.bounds()
    totals = source.one("recap_totals", **bounds)
    history = _parse(source.one("recap_history").get("first"))
    steam = (source.one("recap_steam_games").get("games") or 0) > 0
    title = f"{period.noun.title()} so far" if running else f"{period.noun.title()} in review"
    n, minutes, observed = totals.get("sessions") or 0, totals.get("minutes") or 0, totals.get("observed") or 0
    raw = {"sessions": n, "minutes": minutes, "games": totals.get("games") or 0, "observed": observed,
           "history": history}
    if not n:
        lines = ["No sessions recorded", f"The launcher saw no sessions in {period.label}."]
        if history is None:
            lines.append("Its history begins with the first game it times or sees running.")
        elif history >= period.end:
            lines.append(f"Its history begins on {_day(history, weekday=False)} {history.year}.")
        return Recap(period=period, running=running, title=title, empty_lines=tuple(lines),
                     footer=(STEAM_LINE,) if steam else (), raw=raw)

    games = totals.get("games") or 0
    big, unit = headline(minutes)
    counts = ((_plural(n, "session"), f"of {_plural(games, 'game')}") if games == 1 else
              (_plural(n, "session"), f"{_plural(games, 'game')} played at least once") if period.is_year else
              (_plural(n, "session"), f"across {_plural(games, 'game')}"))

    comparison = ""
    previous = period.previous()
    if not running and history is not None and history <= previous.start:
        before = source.one("recap_totals", **previous.bounds()).get("minutes") or 0
        raw["previous_minutes"] = before
        if before:
            diff = minutes - before
            where = f"in {previous.name}"
            comparison = (f"the same as {where}" if diff == 0 else
                          f"{amount(abs(diff))} {'more' if diff > 0 else 'less'} than {where}")

    rows = source.rows("recap_games", top=rules.RECAP_YEAR_TOP_GAMES if period.is_year else rules.RECAP_TOP_GAMES,
                       **bounds)
    first = rows[0]["minutes"] if rows else 0
    top = tuple(Game(name=r["name"], minutes=r["minutes"], sessions=r["sessions"],
                     share=(r["minutes"] / first) if first else 0.0, time=humanize.playtime(r["minutes"] * 60),
                     identity_key=r["identity_key"], steam_appid=r["steam_appid"], cover_path=r["cover_path"],
                     installed=bool(r["installed"])) for r in rows)
    raw["top"] = [(g.name, g.minutes) for g in top]

    longest = source.one("recap_longest", **bounds)
    longest_at = _parse(longest.get("started_local"))
    part, part_starts = _part(source.rows("recap_hours", **bounds))
    weekday = _weekday(source.rows("recap_weekdays", **bounds))
    raw.update(longest=(longest.get("name"), longest.get("minutes"), longest.get("started_local")),
               part=part, part_starts=part_starts, weekday=weekday)

    facts: list[Fact] = []
    single: tuple[str, ...] = ()
    if games == 1:
        # One game: what is known of its sessions sits beside its one cover.
        only = top[0]
        lines = [f"{only.time}, " + ("in one sitting" if n == 1 else f"in {n:,} sessions")]
        if n == 1 and longest_at is not None:
            lines.append(f"{rules.RECAP_WEEKDAYS[(longest_at.weekday() + 1) % 7]} "
                         f"{longest_at.day} {rules.RECAP_MONTH_NAMES[longest_at.month - 1]}, {part}")
        else:
            lines.append(f"Mostly {part}, most time on {weekday}s")
            lines.append(f"The longest: {humanize.playtime(longest['minutes'] * 60)}, {_day(longest_at)}")
        single = tuple(lines)
    else:
        facts.append(Fact(LONGEST, "Longest session", humanize.playtime(longest["minutes"] * 60),
                          f"{_day(longest_at)}, {longest['name']}"))  # the day first: a long name is cut, never it
        facts.append(Fact(WHEN, "When you played", part[:1].upper() + part[1:], f"Most time on {weekday}s"))

    new = source.rows("recap_new_games", **bounds)
    if new:
        names = tuple(r["name"] for r in new)
        facts.append(Fact(NEW, f"New this {period.noun}", _plural(len(new), "game"),
                          listing(names, rules.RECAP_NEW_GAMES), names=names))
    raw["new"] = [r["name"] for r in new]

    # Money, when there is any: what was bought in the period, and the wishlist -- its largest fall in
    # price seen in the period, or (this month only: today's prices are not a past month's) how many
    # wished games are on sale today. One fact, so the card keeps its shape.
    bought = source.rows("recap_purchases", **bounds)
    drop = source.one("recap_wishlist_drop", **bounds)
    on_sale = (source.one("recap_wishlist_now").get("on_sale") or 0) if running else 0
    fell = ""
    if drop:
        fell = (f"{humanize.money(drop['before_cents'], drop['currency'])} to "
                f"{humanize.money(drop['final_cents'], drop['currency'])}")
    if bought:
        wished = (f"; wishlist: {drop['name']} fell" if drop else
                  f"; wishlist: {on_sale:,} on sale" if on_sale else "")
        facts.append(Fact(MONEY, "Spent", _money(bought), _plural(len(bought), "purchase") + wished,
                          short=_plural(len(bought), "purchase")))
    elif drop:
        facts.append(Fact(MONEY, "Your wishlist", fell, f"{drop['name']}, the biggest drop this {period.noun}"))
    elif on_sale:
        facts.append(Fact(MONEY, "Your wishlist", f"{on_sale:,} on sale today",
                          "of the games on your wishlist"))
    raw.update(bought=[(r["name"], r["paid_cents"], r["currency"]) for r in bought], drop=drop, on_sale=on_sale)

    months: tuple[MonthBar, ...] = ()
    busiest = ""
    if period.is_year:
        # The twelve months, as Stats' chart draws them: a month is recorded once history had begun by
        # its end and it has begun; the busiest named. When in the day and the week goes beside it.
        rows_by = {r["month"]: r["minutes"] or 0 for r in source.rows("recap_months", **bounds)}
        months = tuple(MonthBar(label=rules.MONTH_ABBREVIATIONS[m.month - 1], minutes=rows_by.get(m.month, 0),
                                recorded=history is not None and history < m.end and m.start <= moment)
                       for m in period.months())
        top_month = max(range(12), key=lambda i: (months[i].minutes, -i))
        busiest = (f"Busiest: {rules.RECAP_MONTH_NAMES[top_month]}, {humanize.playtime(months[top_month].minutes * 60)}"
                   + (f". Mostly {part}, most time on {weekday}s" if n > 1 else ""))
        facts = [f for f in facts if f.kind != WHEN]  # said beside the months instead
        raw["months"] = [(b.label, b.minutes, b.recorded) for b in months]

    footer = [_measured(n, observed)]
    if history is not None and period.start < history < period.end:
        footer.append(f"Recorded from {_day(history, weekday=False)}, when the launcher's history begins.")
    if steam:
        footer.append(STEAM_LINE)
    return Recap(period=period, running=running, title=title, minutes=minutes, sessions=n, games=games,
                 observed=observed, headline=big, unit=unit, counts=counts, comparison=comparison, top=top,
                 single=single, facts=tuple(facts), months=months, busiest=busiest, footer=tuple(footer), raw=raw)


def summary(recap: Recap) -> str:
    """The Stats page's one line, from the same card the dialog draws."""
    when = f"{recap.period.name} so far" if recap.running else recap.period.label
    if recap.empty:
        return f"{when}: nothing recorded yet." if recap.running else f"{when}: nothing recorded."
    return (f"{when}: {humanize.playtime(recap.minutes * 60)} across {_plural(recap.games, 'game')}, "
            f"{_plural(recap.sessions, 'session')}")


def strings(recap: Recap) -> list[str]:
    """Every piece of text the card draws -- what the no-personal-data check reads."""
    found = [version.APP_NAME, recap.title, recap.period.label, recap.headline, recap.unit, recap.comparison,
             *recap.counts, *recap.single, *recap.empty_lines, recap.busiest, *(b.label for b in recap.months),
             *recap.footer]
    for game in recap.top:
        found += [game.name, game.time]
    for fact in recap.facts:
        found += [fact.label, fact.value, fact.detail]
    return [text for text in found if text]
