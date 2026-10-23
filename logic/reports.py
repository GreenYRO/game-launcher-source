"""The reports (Phase 83; the eighth, Phase 89; the ninth, Phase 98; the tenth, Phase 102; the eleventh, Phase 103):
the database's answers, shaped for the Reports page, the command line and docs/ANALIZA.md.

Each report answers one fixed question. data_access/reports.py holds its SQL (one query per
figure, a module constant the document quotes); this module turns the rows into a `Report` — the
question, one sentence that answers it, its parts (bar lists, small tables), what the numbers
cannot see (the caveat) and the idea behind it (the concept, with the name to read about). No Qt,
no I/O: the page draws a Report, reports.py in the root prints or writes one.

Hours come from two sources — the launcher's own timing and Steam's counters on the accounts
marked mine, side by side in v_hours — and every report says which it reads. Spacewar and Source
SDK Base 2007 (rules.STEAM_NOT_GAMES) are left out of every figure and shown on their own in the
seventh report, as are demos, mods and tools. The eighth (Phase 89) sets the wishlist against the hours; the
ninth (Phase 98) is For you's ranking, the typical sessions, and a look back at whether the ranking foretold
anything -- worked out by logic/recommend.py, the page's own functions. The tenth (Phase 102) sets the stars a
session was given against the hours, and against the fit: `spearman`, a rank correlation, is worked out here.
The eleventh (Phase 103) counts the marks -- how many games are finished, how long it takes -- with the censored
games counted by Kaplan-Meier's estimate (`kaplan_meier_median`).

`gini` is the one computation finished here rather than in SQL: the shares and their running sums
come sorted from the query, and the coefficient is their weighted sum --

    G = (2 * sum(i * x_i)) / (n * sum(x_i)) - (n + 1) / n,   x_1 <= ... <= x_n,  i = 1..n

-- 0 when every game has the same hours, (n - 1) / n when one game has them all.
"""

from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass, field
from datetime import datetime

from logic import fit
from logic import recommend
from shared import humanize
from shared import rules

log = logging.getLogger(__name__)

SOURCE_WORDS = {"steam": "Steam", "launcher": "the launcher", "both": "both"}
LINK_WORDS = {"manifest": "the store's own record", "search": "a name match",
              "recovered": "a link kept from an old record", "chosen": "chosen by you"}
WEEKDAYS = ((1, "Monday"), (2, "Tuesday"), (3, "Wednesday"), (4, "Thursday"), (5, "Friday"),
            (6, "Saturday"), (0, "Sunday"))  # SQLite's %w: 0 is Sunday


@dataclass(frozen=True)
class Bar:
    label: str
    fraction: float  # the bar's length, 0..1
    value: str       # the figure written beside it


@dataclass(frozen=True)
class Part:
    heading: str
    columns: tuple = ()
    rows: tuple = ()    # each a tuple of strings, as shown
    data: tuple = ()    # the same rows as numbers and plain values, for the CSV files
    bars: tuple = ()
    note: str = ""
    data_columns: tuple = ()  # the names of `data`'s columns, where they are not the table's


@dataclass(frozen=True)
class Report:
    number: int
    key: str
    title: str
    question: str
    sentence: str
    caveat: str
    concept: str
    parts: tuple = ()
    queries: tuple = ()   # the names in data_access.reports.QUERIES it is built from
    curve: tuple = ()     # the Lorenz curve's points (x, y), concentration only
    empty: bool = False   # nothing to say yet: the sentence says so in words


# — numbers, as the page writes them --------------------------------------------------------------

def gini(values) -> float:
    """The Gini coefficient of non-negative amounts: 0 all equal, (n - 1) / n one holds everything."""
    ordered = sorted(max(0.0, float(v)) for v in values)
    n, total = len(ordered), sum(ordered)
    if n == 0 or total == 0:
        return 0.0
    weighted = sum(i * x for i, x in enumerate(ordered, start=1))
    return 2 * weighted / (n * total) - (n + 1) / n


def lorenz(values) -> tuple:
    """The Lorenz curve: the share of the total held by the least x of the items, from (0, 0) to (1, 1)."""
    ordered = sorted(max(0.0, float(v)) for v in values)
    n, total = len(ordered), sum(ordered)
    if n == 0 or total == 0:
        return ()
    points, running = [(0.0, 0.0)], 0.0
    for i, x in enumerate(ordered, start=1):
        running += x
        points.append((i / n, running / total))
    return tuple(points)


def pct(share: float | None) -> str:
    if not share:
        return "0%"
    return f"{share:.0%}" if share >= 0.095 else f"{share:.1%}"


def hours(minutes: float | None) -> str:
    """A game's time as the rest of the launcher writes it: "3964 hours", "12h 30m", "45 min"."""
    return humanize.playtime(round((minutes or 0) * 60))


def total_hours(minutes: float | None) -> str:
    """A total, with its thousands: "10,145 hours"."""
    value = round((minutes or 0) / 60)
    return f"{value:,} hour{'s' if value != 1 else ''}"


def of_hours(part: float | None, whole: float | None) -> str:
    """ "9,988 of 10,145 hours" """
    return f"{round((part or 0) / 60):,} of {total_hours(whole)}"


def count(n: int, word: str) -> str:
    return f"{n:,} {word}{'' if n == 1 else 's'}"


def price(kind, cents, currency) -> str:
    if kind == "priced" and cents is not None:
        return humanize.money(cents, currency)
    return {"free": "free", "unavailable": "not sold"}.get(kind, "—")


def _span(minutes: int) -> str:
    return f"{minutes} minutes" if minutes < 60 else count(minutes // 60, "hour")


def _day(text: str | None) -> str:
    if not text:
        return "—"
    return humanize.day(datetime.fromisoformat(text), year=True)


def _bars(pairs, values) -> tuple:
    """(label, amount) pairs as bars, each as long as its amount against the largest."""
    top = max((amount for _label, amount in pairs), default=0) or 1
    return tuple(Bar(label, amount / top, value) for (label, amount), value in zip(pairs, values))


def _set_aside_names() -> str:
    return " and ".join(rules.STEAM_NOT_GAMES.values())


# — the eleven ------------------------------------------------------------------------------------

def concentration(data: dict) -> Report:
    rows = data["concentration"]
    base = dict(number=1, key="concentration", title="Concentration",
                question="How unevenly are the hours spread over the games?", queries=("concentration",),
                caveat=(f"Hours from both sources, added where a game has both; {_set_aside_names()} are left "
                        "out (report 7), and so are demos, mods and tools. A Steam app counts once however many "
                        "folders share it. Only the Steam accounts marked yours count."),
                concept=("Pareto distribution: a few items hold most of the total (the \"80/20 rule\"). The Lorenz "
                         "curve plots the share of hours held by the least played games; the further it sags "
                         "below the diagonal, the more unequal the spread. The Gini coefficient is twice the area "
                         "between the two: 0 when every game has the same hours, (n - 1)/n when one has them all."))
    if not rows:
        return Report(sentence="No game has any hours yet: the launcher has timed nothing, and no Steam account "
                               "marked yours holds any time.", empty=True, **base)
    n = len(rows)
    total = sum(r["minutes"] for r in rows)
    marks = {m: next(r["rank"] for r in rows if r["cumulative"] >= m - 1e-9) for m in rules.REPORT_CONCENTRATION_MARKS}
    coefficient = gini(r["minutes"] for r in rows)
    half, most = (marks[m] for m in rules.REPORT_CONCENTRATION_MARKS)
    sentence = (f"{rows[0]['name']} alone holds {pct(rows[0]['share'])} of your {total_hours(total)} on games; "
                f"{half} of {n} games make half of them and {most} make "
                f"{rules.REPORT_CONCENTRATION_MARKS[1]:.0%} — a Gini coefficient of {coefficient:.2f}.")
    tops = [k for k in rules.REPORT_CONCENTRATION_TOPS if k <= n]
    top_bars = tuple(Bar(f"Top {k}", rows[k - 1]["cumulative"], pct(rows[k - 1]["cumulative"])) for k in tops)
    shown = rows[: rules.REPORT_TOP_ROWS]
    table = Part(f"The {len(shown)} most played", ("#", "Game", "Hours", "Share", "Cumulative", "Timed by"),
                 tuple((str(r["rank"]), r["name"], hours(r["minutes"]), pct(r["share"]), pct(r["cumulative"]),
                        SOURCE_WORDS.get(r["source"], "")) for r in shown),
                 tuple((r["rank"], r["name"], round(r["minutes"], 1), r["share"], r["cumulative"], r["source"])
                       for r in rows), data_columns=("rank", "game", "minutes", "share", "cumulative", "source"))
    figures = Part("The figures", ("Measure", "Value"),
                   (("Games with any hours", f"{n:,}"), ("Hours on them", total_hours(total)),
                    (f"Games that make {rules.REPORT_CONCENTRATION_MARKS[0]:.0%}", str(half)),
                    (f"Games that make {rules.REPORT_CONCENTRATION_MARKS[1]:.0%}", str(most)),
                    ("Gini coefficient", f"{coefficient:.3f}")),
                   (("games", n), ("minutes", round(total, 1)), ("games_to_half", half), ("games_to_80", most),
                    ("gini", round(coefficient, 4))))
    return Report(sentence=sentence, curve=lorenz(r["minutes"] for r in rows),
                  parts=(Part("Share of all hours held by the most played", bars=top_bars), figures, table), **base)


def abandonment(data: dict) -> Report:
    rows = {r["bucket"]: r for r in data["abandonment"]}
    edges = (rules.REPORT_TEN_MINUTES, rules.REPORT_ONE_HOUR, rules.REPORT_REFUND_WINDOW_MINUTES,
             rules.REPORT_TEN_HOURS, rules.REPORT_HUNDRED_HOURS)
    labels = [f"Under {_span(edges[0])}"] + [f"{_span(a)} to {_span(b)}" for a, b in zip(edges, edges[1:])]
    labels[2] += " (the refund window)"
    labels.append(f"Over {_span(edges[-1])}")
    base = dict(number=2, key="abandonment", title="Abandonment",
                question="How many of the games started on Steam were dropped early?", queries=("abandonment",),
                caveat=("\"Started at least once\": Steam's own file lists only the apps that were launched, so a "
                        "game bought and never opened is not here at all. Steam's time only, on the accounts "
                        f"marked yours; demos, mods, tools, {_set_aside_names()} are left out. The refund window is "
                        "a threshold of time only: the data holds no purchase date, so it never says a refund was "
                        "possible. Free: Steam's free flag or the Free To Play genre; no store record: nothing is "
                        "known of the app; paid: the rest, games no longer sold included."),
                concept=("Steam's refund window: a game played under two hours, within 14 days of buying it, can "
                         "be refunded — the line between trying a game and keeping it. Abandonment (attrition): "
                         "the share of games left early. Confounding variable: something that drives both what is "
                         "compared and the result. Here the business model (report 3's free-to-play line) "
                         "confounds \"dropped early\" with \"tried because it was free\", so paid games are "
                         "counted on their own."))
    n = sum(r["apps"] for r in rows.values())
    if not n:
        return Report(sentence="No Steam account marked yours holds any time yet (Settings, Steam accounts).",
                      empty=True, **base)
    apps = [rows.get(b, {}).get("apps", 0) for b in range(1, 7)]
    minutes = [rows.get(b, {}).get("minutes", 0) for b in range(1, 7)]
    kinds = {k: [rows.get(b, {}).get(k) or 0 for b in range(1, 7)] for k in rules.REPORT_APP_KINDS}
    paid, free, unknown = (kinds[k] for k in ("paid", "free", "unknown"))
    paid_n, paid_under = sum(paid), sum(paid[:3])
    others = " and ".join(words for words in (count(sum(free[:3]), "free-to-play title") if sum(free[:3]) else "",
                                              count(sum(unknown[:3]), "app") + " with no store record"
                                              if sum(unknown[:3]) else "") if words)
    apart = (f"; another {others} {'was' if sum(free[:3]) + sum(unknown[:3]) == 1 else 'were'} also left under two "
             "hours and are counted apart." if others else ".")
    if paid_n:
        sentence = (f"Of the {count(paid_n, 'paid game')} started on Steam, {paid_under:,} ({pct(paid_under / paid_n)}) "
                    f"stayed under two hours, Steam's refund window{apart}")
    else:
        sentence = (f"No paid game has been started on Steam; {count(n, 'game')} started, {sum(apps[:3]):,} of them "
                    "under two hours, all free to play or with no store record.")
    bars = _bars(list(zip(labels, apps)), [f"{a:,} · {pct(a / n)}" for a in apps])
    table = Part("By time played", ("Steam time", "Games", "Share", "Minutes", "Paid", "Free", "No record"), (),
                 tuple((label, a, a / n, m, p, f, u)
                       for label, a, m, p, f, u in zip(labels, apps, minutes, paid, free, unknown)))  # the CSV's
    window = [label.replace(" (the refund window)", "") for label in labels[:3]]
    by_kind = Part("Under two hours, by kind", ("", *window, "Under 2 hours", "2 hours or more"),
                   tuple((rules.REPORT_APP_KINDS[k], *(f"{x:,}" for x in kinds[k][:3]),
                          f"{sum(kinds[k][:3]):,} ({pct(sum(kinds[k][:3]) / sum(kinds[k])) if sum(kinds[k]) else '—'})",
                          f"{sum(kinds[k][3:]):,}") for k in rules.REPORT_APP_KINDS),
                   tuple((k, *kinds[k][:3], sum(kinds[k][:3]), sum(kinds[k][3:]),
                          round(sum(kinds[k][:3]) / sum(kinds[k]), 4) if sum(kinds[k]) else None)
                         for k in rules.REPORT_APP_KINDS),
                   note="Each kind's share is of its own games started on Steam.",
                   data_columns=("kind", "under_ten_minutes", "ten_minutes_to_an_hour", "an_hour_to_two",
                                 "under_two_hours", "two_hours_or_more", "share_under_two_hours"))
    return Report(sentence=sentence, parts=(Part("Games by Steam time", bars=bars), by_kind, table), **base)


def profiles(data: dict) -> Report:
    cover = data["profile_coverage"][0] if data["profile_coverage"] else {}
    played = cover.get("played") or 0
    base = dict(number=3, key="profiles", title="Profiles",
                question="What kind of games do the hours go to: genre, publisher, developer, decade?",
                queries=("profile_coverage", "profile_genres", "profile_companies", "profile_decades"),
                caveat=("A game with several genres (or publishers, or developers) counts in each, so a list's "
                        "shares add up to more than 100%. "
                        + ", ".join(v for k, v in rules.STEAM_NOT_GENRES.items() if k != rules.STEAM_FREE_TO_PLAY_GENRE)
                        + " are left out of the genres — a release state and content descriptors — and Free To "
                        "Play is the price, not the kind of game: it has its own line. Only apps with a Steam "
                        "store record have any of these; a folder game with no Steam link has none."),
                concept=("Coverage: the share of the data a figure can see, said beside every share here. Genre "
                         "versus business model: Free To Play says how a game earns its money, not what kind of "
                         "game it is."))
    if not played:
        return Report(sentence="No game has any hours yet, so there is nothing to profile.", empty=True, **base)

    def dimension(heading, rows, known, word, limit=rules.REPORT_PROFILE_ROWS):
        shown = rows[:limit]
        bars = _bars([(r["label"], r["minutes"]) for r in shown],
                     [f"{pct(r['minutes'] / known)} · {hours(r['minutes'])}" for r in shown]) if known else ()
        note = f"{of_hours(known, played)} have a known {word} ({pct(known / played)})."
        table = tuple((r["label"], r["apps"], round(r["minutes"], 1), (r["minutes"] / known) if known else None)
                      for r in rows)
        return Part(heading, ("", "Games", "Minutes", "Share"), (), table, bars, note)

    genres = data["profile_genres"]
    free = cover.get("free_to_play") or 0
    with_genre = cover.get("with_genre") or 0
    parts = (dimension("Genres", genres, with_genre, "genre"),
             Part("Free to play", note=f"{pct(free / played)} of all the hours ({total_hours(free)}) are on "
                                       "free-to-play titles — the business model the money report's cost per "
                                       "hour leans on."),
             dimension("Publishers", data["profile_publishers"], cover.get("with_publisher") or 0, "publisher"),
             dimension("Developers", data["profile_developers"], cover.get("with_developer") or 0, "developer"),
             dimension("Release decade", data["profile_decades"], cover.get("with_release") or 0, "release date",
                       limit=len(data["profile_decades"])))
    lead = genres[0] if genres else None
    sentence = ((f"{lead['label']} is in {pct(lead['minutes'] / with_genre)} of the hours that have a genre; "
                 if lead and with_genre else "")
                + f"{pct(free / played)} of all your hours are on free-to-play titles, and "
                f"{of_hours(with_genre, played)} have a known genre.")
    return Report(sentence=sentence, parts=parts, **base)


def backlog(data: dict) -> Report:
    rows = data["backlog"]
    never = [r for r in rows if r["state"] == "never"]
    under = [r for r in rows if r["state"] == "under"]
    unknown = [r for r in rows if r["state"] == "unknown"]
    base = dict(number=4, key="backlog", title="Backlog",
                question="What is installed and waiting — never played, or barely?", queries=("backlog",),
                caveat=("\"Never\" means: no time here -- started from the launcher or seen running while it "
                        "ran -- no date from its store, no Steam time on the accounts marked yours. A game played "
                        "while the launcher was not running, or before it was installed, looks unplayed. An Epic, "
                        "Xbox or Ubisoft game with no time seen is \"cannot tell\": its store never says. Two folders "
                        "of one game share its hours."),
                concept=("Backlog (the \"pile of shame\"): games owned and waiting to be played. Their value twice: "
                         "at list price (the price before any discount) and today, sales included — the cost of "
                         "replacing them — never what was paid."))
    if not rows:
        return Report(sentence="No game is installed.", empty=True, **base)
    size = sum(r["size_on_disk"] or 0 for r in never)
    listed_cents, today_cents, currencies = _value(never)
    sentence = (f"{count(len(never), 'installed game')} {'has' if len(never) == 1 else 'have'} never been played "
                f"anywhere — {humanize.size(size)}{value_words(listed_cents, today_cents, currencies)}; "
                f"{len(under):,} more {'was' if len(under) == 1 else 'were'} played under two hours in total."
                if never else
                f"Every installed game the launcher can tell about has been played; {len(under):,} "
                f"{'was' if len(under) == 1 else 'were'} played under two hours in total.")

    def listed(heading, chosen, with_time):
        columns = (("Game", "Played", "Size", "List price", "Today", "From") if with_time
                   else ("Game", "Size", "List price", "Today", "From"))
        shown = tuple(tuple(x for x in (r["name"], _played(r["minutes"]) if with_time else None,
                                        humanize.size(r["size_on_disk"] or 0),
                                        price(r["price_kind"], r["initial_cents"], r["currency"]),
                                        price(r["price_kind"], r["final_cents"], r["currency"]),
                                        rules.SOURCE_LABELS.get(r["source"], r["source"] or "?")) if x is not None)
                      for r in chosen)
        raw = tuple((r["name"], round(r["minutes"], 1), r["size_on_disk"], r["price_kind"], r["initial_cents"],
                     r["final_cents"], r["currency"], r["source"]) for r in chosen)
        return Part(heading, columns, shown, raw, note="" if chosen else "None.",
                    data_columns=("game", "minutes", "bytes", "price_kind", "list_cents", "today_cents", "currency",
                                  "source"))

    parts = [listed("Never played", never, False), listed("Played under two hours", under, True)]
    if unknown:
        parts.append(Part("Cannot tell", note=", ".join(r["name"] for r in unknown) + " — their stores keep "
                                                "no record of play this launcher can read."))
    return Report(sentence=sentence, parts=tuple(parts), **base)


def _played(minutes) -> str:
    """A backlog game's time: one with a start recorded and no minutes was started, not unplayed."""
    return hours(minutes) if minutes else "started, no time"


def _value(rows) -> tuple[int, int, set]:
    """These games' value at list price and today, one price per Steam app (two folders of one game
    are one title) -- with the currencies they are priced in."""
    seen = {}
    for r in rows:
        if r["price_kind"] == "priced" and r["steam_appid"] is not None:
            seen[r["steam_appid"]] = (r["initial_cents"], r["final_cents"], r["currency"])
    return (sum(i for i, _f, _c in seen.values()), sum(f for _i, f, _c in seen.values()),
            {cur for _i, _f, cur in seen.values()})


def value_words(listed_cents: int, today_cents: int, currencies: set) -> str:
    """ ", 89,24 € at list price, 85,00 € today", or one figure when no sale makes them differ."""
    if not currencies:
        return ""
    if len(currencies) > 1:
        return ", priced in more than one currency"
    currency = next(iter(currencies))
    if listed_cents == today_cents:
        return f", {humanize.money(listed_cents, currency)} at list price and today"
    return f", {humanize.money(listed_cents, currency)} at list price, {humanize.money(today_cents, currency)} today"


def sessions(data: dict) -> Report:
    summary = data["session_summary"][0] if data["session_summary"] else {}
    n = summary.get("sessions") or 0
    origins = {row["origin"]: row for row in data.get("session_origins") or []}
    observed = origins.get(rules.SESSION_OBSERVED) or {}
    seen_since = (f"since {_day(observed['first'])}, " if observed.get("first") else "")
    base = dict(number=5, key="sessions", title="Sessions",
                question="How long, and when, are the sittings with a game?",
                queries=("session_summary", "session_origins", "session_lengths", "session_hours", "session_weekdays"),
                caveat=("Every game that has sessions: the ones the launcher starts, timed to the second, and "
                        f"{seen_since}the ones it sees running while it runs, however they were started — a Steam "
                        "game's included — each end within one look, a few seconds. Steam's counters hold totals, "
                        "not sessions, and nothing is here of what was played while the launcher was not running. "
                        f"History since {_day(summary.get('first'))}; a session under a minute is not kept, and "
                        "each counts at the hour it began, not split across hours. Local wall time: the hour on "
                        "your clock that day."),
                concept=("Median and mean: in a skewed distribution the median is the typical session and the "
                         "mean is pulled up by the long ones. The 90th percentile: nine sessions in ten are "
                         "shorter. Wall time versus instant: a session is stored with its offset, so its hour is "
                         "read off the text, never converted to UTC first. Instrumentation versus observation: a "
                         "launched session is measured by the program that started the game; an observed one by a "
                         "passive observer looking every few seconds — its measurement resolution is one look."))
    if not n:
        return Report(sentence="No sessions have been recorded yet: they begin when a game is started from the "
                               "launcher, or seen running while it runs.", empty=True, **base)
    total = summary["minutes"] or 0
    by_hour = {r["hour"]: r for r in data["session_hours"]}
    night = sum((by_hour.get(h) or {}).get("minutes", 0) for h in range(rules.REPORT_NIGHT_ENDS))
    seen = observed.get("sessions") or 0
    sentence = (f"{n:,} sessions since {_day(summary['first'])}"
                + (f", {seen:,} of them seen running rather than started here" if seen else "")
                + f": the median lasts {summary['median']:.0f} minutes "
                f"and the mean {summary['mean']:.0f} — a few long ones pull the mean up; {pct(night / total)} of "
                f"the minutes began between midnight and {rules.REPORT_NIGHT_ENDS} in the morning.")
    launched = origins.get(rules.SESSION_LAUNCHED) or {}
    measured = Part("How they were measured", ("", "Sessions", "Minutes"),
                    (("Started here, timed to the second", f"{launched.get('sessions') or 0:,}",
                      f"{launched.get('minutes') or 0:,}"),
                     ("Seen running, each end within a look", f"{seen:,}", f"{observed.get('minutes') or 0:,}")),
                    ((rules.SESSION_LAUNCHED, launched.get("sessions") or 0, launched.get("minutes") or 0),
                     (rules.SESSION_OBSERVED, seen, observed.get("minutes") or 0)),
                    data_columns=("origin", "sessions", "minutes"))
    figures = Part("The figures", ("Measure", "Value"),
                   (("Sessions", f"{n:,}"), ("Median", f"{summary['median']:.0f} min"),
                    ("Mean", f"{summary['mean']:.0f} min"), ("90th percentile", f"{summary['p90']:.0f} min"),
                    ("All minutes", f"{total:,}"), ("Between 00:00 and 06:00", pct(night / total))),
                   (("sessions", n), ("median", summary["median"]), ("mean", round(summary["mean"], 2)),
                    ("p90", summary["p90"]), ("minutes", total), ("night_share", night / total)))
    edges = rules.REPORT_SESSION_EDGES
    names = ([f"Under {_span(edges[0])}"] + [f"{_span(a)} to {_span(b)}" for a, b in zip(edges, edges[1:])]
             + [f"Over {_span(edges[-1])}"])
    lengths = {r["bucket"]: r for r in data["session_lengths"]}
    counts = [(lengths.get(b) or {}).get("sessions", 0) for b in range(1, len(names) + 1)]
    length_part = Part("How long", ("Length", "Sessions", "Share"), (),
                       tuple((label, c, c / n) for label, c in zip(names, counts)),
                       _bars(list(zip(names, counts)), [f"{c:,} · {pct(c / n)}" for c in counts]))
    hour_minutes = [(by_hour.get(h) or {}).get("minutes", 0) for h in range(24)]
    hour_part = Part("When in the day (the minutes, by the hour they began)", ("Hour", "Sessions", "Minutes"), (),
                     tuple((h, (by_hour.get(h) or {}).get("sessions", 0), hour_minutes[h]) for h in range(24)),
                     _bars([(f"{h:02d}:00", m) for h, m in enumerate(hour_minutes)],
                           [f"{m:,} min" for m in hour_minutes]))
    by_day = {r["weekday"]: r for r in data["session_weekdays"]}
    day_minutes = [((by_day.get(d) or {}).get("minutes", 0), name) for d, name in WEEKDAYS]
    day_part = Part("Which day", ("Day", "Sessions", "Minutes"), (),
                    tuple((name, (by_day.get(d) or {}).get("sessions", 0), (by_day.get(d) or {}).get("minutes", 0))
                          for d, name in WEEKDAYS),
                    _bars([(name, m) for m, name in day_minutes], [f"{m:,} min" for m, _ in day_minutes]))
    return Report(sentence=sentence, parts=(figures, measured, length_part, hour_part, day_part), **base)


def money(data: dict) -> Report:
    lib = data["money_library"][0] if data["money_library"] else {}
    series = data["money_series"][0] if data["money_series"] else {}
    paid, proxy, sales, lowest = data["money_paid"], data["money_proxy"], data["money_sales"], data["money_lowest"]
    per_app = (series.get("observations") or 0) / (series.get("apps") or 1)
    base = dict(number=6, key="money", title="Money",
                question="What is the library worth, and what does an hour of play cost?",
                queries=("money_library", "money_paid", "money_proxy", "money_sales", "money_lowest", "money_wishlist",
                         "money_series", "backlog"),
                caveat=(f"The price series is young: {_day(series.get('first'))} to {_day(series.get('last'))}, "
                        f"{per_app:.1f} prices per app on average, so a \"lowest seen\" rests on very few. Steam's "
                        "prices for Romania, never converted between currencies. The cost per hour divides by both "
                        "sources' hours (a game's own page counts the launcher's only). A list price per hour is a "
                        "stand-in, not what was paid; free games and games with no Steam app have none."),
                concept=("Replacement value: what the library would cost to buy again today, at today's prices, "
                         "sales included. List price: the price before any discount. The gap between the two is "
                         "what today's sales take off your library. Cost per hour: price over hours played. Proxy "
                         "measure: a stand-in figure used where the real one is missing, said as such — here the "
                         "list price per hour. Time series: the same price observed again and again."))
    if not lib.get("games"):
        return Report(sentence="No game is installed, so there is nothing to price.", empty=True, **base)
    currency = lib.get("currency") or rules.STEAM_STORE_CURRENCY
    one_currency = (lib.get("currencies") or 0) <= 1
    several = "an amount in more than one currency"
    listed = humanize.money(lib.get("list_cents") or 0, currency) if one_currency else several
    today = humanize.money(lib.get("today_cents") or 0, currency) if one_currency else several
    priced, on_sale = lib.get("priced") or 0, lib.get("on_sale") or 0
    spent = {}
    for r in paid:
        if r["currencies"] == 1:
            spent[r["currency"]] = spent.get(r["currency"], 0) + r["paid_cents"]
    spent_words = " and ".join(humanize.money(c, cur) for cur, c in spent.items())
    if one_currency and (lib.get("list_cents") or 0) == (lib.get("today_cents") or 0):
        worth = (f"Your installed library lists at {listed} and would cost the same to buy today "
                 f"(none of {priced} titles on sale); ")
    else:
        worth = (f"Your installed library lists at {listed} and would cost {today} to buy today "
                 f"({on_sale} of {priced} titles on sale); ")
    sentence = worth + (f"you recorded {spent_words} paid for {count(len(paid), 'game')}." if paid else
                        "no purchase is recorded yet (\"What I paid...\" in a game's menu).")
    library = Part("The installed library: list price and today's cost", ("", "Count"),
                   (("Installed games", str(lib.get("games") or 0)),
                    ("Steam titles among them", str(lib.get("titles") or 0)),
                    ("With a price", str(priced)), ("Free", str(lib.get("free") or 0)),
                    ("No longer sold", str(lib.get("unavailable") or 0)),
                    ("Never priced", str(lib.get("never_priced") or 0)),
                    ("No Steam app", str(lib.get("no_app") or 0)), ("On sale today", str(on_sale)),
                    ("At list price", listed), ("Today's cost (replacement value)", today)),
                   tuple((k, lib.get(k)) for k in ("games", "titles", "priced", "free", "unavailable",
                                                    "never_priced", "no_app", "on_sale", "list_cents", "today_cents",
                                                    "currency")))
    waiting = [r for r in data["backlog"] if r["state"] == "never"]
    listed_cents, today_cents, currencies = _value(waiting)
    parts = [library,
             Part("The backlog's value",
                  note=(f"{count(len(waiting), 'game')} never played"
                        f"{value_words(listed_cents, today_cents, currencies)}."
                        if waiting else "No installed game is waiting to be played.")),
             Part("What you paid", ("Game", "Paid", "Hours", "Per hour"),
                  tuple((r["name"], humanize.money(r["paid_cents"], r["currency"]) if r["currencies"] == 1
                         else "several currencies", hours(r["minutes"]),
                         humanize.money(round(r["cents_per_hour"]), r["currency"]) if r["cents_per_hour"] else "—")
                        for r in paid),
                  tuple((r["name"], r["paid_cents"], r["currency"], r["minutes"], r["cents_per_hour"]) for r in paid),
                  note="" if paid else "Nothing recorded yet.",
                  data_columns=("game", "paid_cents", "currency", "minutes", "cents_per_hour")),
             Part("List price per hour, where nothing is recorded (a stand-in)", ("Game", "Hours", "List price", "Per hour"),
                  tuple((r["name"], hours(r["minutes"]), humanize.money(r["initial_cents"], r["currency"]),
                         humanize.money(round(r["cents_per_hour"]), r["currency"]))
                        for r in proxy[: rules.REPORT_LIST_ROWS]),
                  tuple((r["name"], r["minutes"], r["initial_cents"], r["currency"], r["cents_per_hour"]) for r in proxy),
                  data_columns=("game", "minutes", "list_cents", "currency", "cents_per_hour"),
                  note=(f"The {min(len(proxy), rules.REPORT_LIST_ROWS)} cheapest hours of {len(proxy):,} games played "
                        f"{_span(rules.REPORT_PROXY_MIN_MINUTES)} or more with a list price." if proxy else "None.")),
             Part(f"On sale today: {len(sales):,}", ("Game", "Discount", "Now", "Was", "Installed"),
                  tuple((r["name"], f"-{r['discount_percent']}%", humanize.money(r["final_cents"], r["currency"]),
                         humanize.money(r["initial_cents"], r["currency"]), "yes" if r["installed"] else "")
                        for r in sales[: rules.REPORT_LIST_ROWS]),
                  tuple((r["name"], r["discount_percent"], r["final_cents"], r["initial_cents"], r["currency"],
                         bool(r["installed"])) for r in sales),
                  data_columns=("game", "discount_percent", "now_cents", "was_cents", "currency", "installed"),
                  note="" if sales else "Nothing in the library is on sale today."),
             Part("Lowest seen, for the installed games", ("Game", "Now", "Lowest", "Seen on", "Prices seen"),
                  tuple((r["name"], humanize.money(r["now_cents"], r["currency"]),
                         humanize.money(r["lowest_cents"], r["currency"]), _day(r["lowest_on"]), str(r["observations"]))
                        for r in lowest if r["lowest_cents"] is not None and r["lowest_cents"] < r["now_cents"]),
                  tuple((r["name"], r["now_cents"], r["lowest_cents"], r["currency"], r["lowest_on"], r["observations"])
                        for r in lowest),
                  data_columns=("game", "now_cents", "lowest_cents", "currency", "lowest_on", "observations"),
                  note=f"{sum(1 for r in lowest if r['lowest_cents'] is not None and r['lowest_cents'] < r['now_cents'])} "
                       f"of {len(lowest)} priced titles have been seen cheaper than today."),
             wishlist_part(data["money_wishlist"][0] if data["money_wishlist"] else {}),
             Part("The price series",
                  note=(f"{series.get('observations') or 0:,} prices of {series.get('apps') or 0:,} apps, from "
                        f"{_day(series.get('first'))} to {_day(series.get('last'))}."))]
    return Report(sentence=sentence, parts=tuple(parts), **base)


def wishlist_part(wish: dict) -> Part:
    """Report 6's two wishlist lines (Phase 86): the games on the lists of the accounts marked mine
    at list price today, and at today's prices, sales included -- with what the series can say."""
    items = wish.get("items") or 0
    if not items:
        return Part("Your wishlist at today's prices",
                    note="No wishlist read: none of the accounts marked yours has one Steam shows (a private "
                         "list answers as an empty one does).")
    priced = wish.get("priced") or 0
    if (wish.get("currencies") or 0) > 1:
        listed = today = "an amount in more than one currency"
    else:
        currency = wish.get("currency") or rules.STEAM_STORE_CURRENCY
        listed = humanize.money(wish.get("list_cents") or 0, currency)
        today = humanize.money(wish.get("today_cents") or 0, currency)
    rest = []
    for key, words in (("free", "free"), ("unavailable", "not sold"), ("never_priced", "not priced yet")):
        if wish.get(key):
            rest.append(f"{wish[key]} {words}")
    return Part("Your wishlist at today's prices", ("", "Amount"),
                (("At list price", listed), ("At today's prices", today),
                 ("On sale today", count(wish.get("on_sale") or 0, "game"))),
                tuple((k, wish.get(k)) for k in ("items", "priced", "on_sale", "list_cents", "today_cents",
                                                  "currency", "oldest_price", "targets", "below_target")),
                note=(f"{count(items, 'game')} on your wishlist, {priced} with a price"
                      + (f" ({', '.join(rest)})" if rest else "") + ". Asked for every day since the wishlist "
                      "was first read, so a sale before that is not in the series." + targets_sentence(wish)))


def targets_sentence(wish: dict) -> str:
    """Report 6's sentence on the price alerts (Phase 101), only when a target is set: "You watch 3 wished games
    with a target; 1 is below it today." A target compares only with a price in its own currency."""
    targets = wish.get("targets") or 0
    if not targets:
        return ""
    below = wish.get("below_target") or 0
    return (f" You watch {count(targets, 'wished game')} with a target; {below} "
            f"{'is' if below == 1 else 'are'} below it today.")


def quality(data: dict) -> Report:
    kinds, aside, sources = data["quality_types"], data["quality_set_aside"], data["quality_sources"]
    links, untimed, currencies = data["quality_links"], data["quality_untimed"], data["quality_currencies"]
    life = data["stats_lifetime"][0] if data["stats_lifetime"] else {}
    counted = sum(r["minutes"] or 0 for r in kinds)
    set_aside = sum(r["minutes"] or 0 for r in aside)
    everything = counted + set_aside
    base = dict(number=7, key="quality", title="Data quality",
                question="What can these numbers not see, and how sure are they?",
                queries=("quality_types", "quality_set_aside", "quality_sources", "quality_links", "quality_untimed",
                         "quality_currencies", "stats_lifetime"),
                caveat=("This report is the limits, as numbers: what is left out, where each hour came from, which "
                        "links between a folder game and a Steam app are guesses, and which games are timed only "
                        "while the launcher watches them, or have no hours from any source."),
                concept=("Data quality: completeness (what is missing), provenance (which source said it) and entity "
                         "resolution (deciding that a folder game and a Steam app are the same game — here by a "
                         f"name match at {rules.STEAM_SEARCH_MATCH_RATIO:.2f} similarity or better)."))
    if not everything:
        return Report(sentence="No hours are known yet, so there is nothing to account for.", empty=True, **base)
    unknown = sum(r["minutes"] or 0 for r in kinds if r["kind"].startswith("unknown"))
    launcher = sum(r["minutes_launcher"] or 0 for r in sources)
    sentence = (f"Of {total_hours(everything)}, {total_hours(set_aside)} are set aside ({_set_aside_names()}), "
                f"{total_hours(unknown)} are on apps the store has no record of, and {total_hours(launcher)} were "
                f"timed by the launcher; {count(len(links), 'game')} {'has' if len(links) == 1 else 'have'} time "
                "from both sources.")
    named = dict(rules.STEAM_NOT_GAMES)
    other = [r for r in currencies if r["currency"] != rules.STEAM_STORE_CURRENCY]
    parts = (Part("What the hours are on", ("Kind", "Apps", "Hours", "Share"),
                  tuple((r["kind"], f"{r['apps']:,}", hours(r["minutes"]), pct((r["minutes"] or 0) / everything))
                        for r in kinds),
                  tuple((r["kind"], r["apps"], r["minutes"]) for r in kinds), data_columns=("kind", "apps", "minutes")),
             Part("Set aside from every report", ("App", "Steam id", "Hours", "Last played"),
                  tuple((named.get(r["appid"], f"app {r['appid']}"), str(r["appid"]), hours(r["minutes"]),
                         _day(r["steam_last_played"])) for r in aside),
                  tuple((named.get(r["appid"]), r["appid"], r["minutes"], r["steam_last_played"]) for r in aside),
                  data_columns=("app", "steam_appid", "minutes", "last_played"),
                  note=("Spacewar is the appid a game uses when it runs on Steam without being sold there; Source "
                        "SDK Base 2007 is what Source mods start on. Their hours are other games', unnamed.")),
             Part("Who timed the hours", ("Timed by", "Apps", "Hours"),
                  tuple((SOURCE_WORDS.get(r["source"], r["source"] or "nobody"), f"{r['apps']:,}", hours(r["minutes"]))
                        for r in sources),
                  tuple((r["source"], r["apps"], r["minutes"], r["minutes_launcher"], r["minutes_steam"]) for r in sources),
                  data_columns=("source", "apps", "minutes", "minutes_launcher", "minutes_steam")),
             Part("Games with time from both", ("Game", "Copies", "Launcher", "Steam", "Linked by"),
                  tuple((r["name"], str(r["games"]), hours(r["minutes_launcher"]), hours(r["minutes_steam"]),
                         ", ".join(LINK_WORDS.get(w, w) for w in (r["linked_by"] or "").split(",") if w))
                        for r in links),
                  tuple((r["name"], r["games"], r["minutes_launcher"], r["minutes_steam"], r["linked_by"]) for r in links),
                  data_columns=("game", "copies", "minutes_launcher", "minutes_steam", "linked_by"),
                  note="" if links else "None."),
             Part("Installed, timed only by watching or not at all", ("Game", "From", "Why"),
                  tuple((r["name"], rules.SOURCE_LABELS.get(r["source"], r["source"]), r["why"]) for r in untimed),
                  tuple((r["name"], r["source"], r["why"]) for r in untimed),
                  note="" if untimed else "None: every installed game has hours from the launcher or from Steam."),
             Part("Prices in another currency",
                  note=(f"{sum(r['observations'] for r in other):,} price rows are not in "
                        f"{rules.STEAM_STORE_CURRENCY}." if other else
                        f"None: every price is in {rules.STEAM_STORE_CURRENCY}.")),
             Part("The launcher's own time",
                  note=(f"{total_hours((life.get('seconds_ever') or 0) / 60)} timed by the launcher on every game it "
                        f"has known; {total_hours((life.get('seconds') or 0) / 60)} on the games installed now — the "
                        "Stats page's lifetime figure.")))
    return Report(sentence=sentence, parts=parts, **base)


def preference(data: dict) -> Report:
    """Report 8 (Phase 89): what is said to be wanted, genre by genre, against what is played."""
    rows = data["stated_revealed"]
    first = rows[0] if rows else {}
    wished_games = first.get("wished_games") or 0
    with_genre = first.get("wished_with_genre") or 0
    minutes_all = first.get("minutes_all") or 0
    base = dict(number=8, key="preference", title="Stated and revealed",
                question="What do you say you want, against what you play?",
                queries=("stated_revealed",),
                caveat=(f"The wishlist is the public lists of the accounts marked yours ({count(wished_games, 'game')} "
                        f"now, {with_genre} with a genre); a wished game counts once, whatever it costs. The hours are "
                        "lifetime, from both sources, while a wish can be years old. A game counts in each of its "
                        "genres, so every column adds up to more than 100%. The hours column is steep because a few "
                        "games hold most of the hours (report 1): the hours measure how long you stay, the games "
                        "played how often you try. A list private on Steam is not seen, and a game whose record is "
                        "not fetched yet has no genre."),
                concept=("Stated and revealed preference: what someone says they want, against what they choose. The "
                         "gap between the two is the intention–behaviour gap — though here it can also be a wish not "
                         "acted on yet: a game not bought. The extensive and the intensive margin: how many games of "
                         "a kind you take up, against how much time you spend on each. A wishlist is a count of "
                         "games, so the games played are its like-for-like comparison; the hours add the intensive "
                         "margin, and with it the concentration of report 1."))
    if not wished_games:
        return Report(sentence="No wishlist to set against your hours: none of the accounts marked yours has a list "
                               "Steam shows (a private list answers as an empty one does).", empty=True, **base)
    if not with_genre:
        return Report(sentence="Your wished games have no genres yet: their records are fetched at the next scans.",
                      empty=True, **base)
    played_all = first.get("played_games_all") or 0
    # (genre, wishlist share, share of the games played, share of the hours, wished games)
    shares = [(r["genre"], (r["wished"] or 0) / with_genre,
               (r["played_games"] or 0) / played_all if played_all else 0.0,
               (r["minutes"] or 0) / minutes_all if minutes_all else 0.0, r["wished"] or 0) for r in rows]
    shares.sort(key=lambda s: (-max(s[1], s[2], s[3]), s[0]))
    said = [s for s in shares if s[4] >= rules.REPORT_STATED_MIN_GAMES and s[1] > s[3]]
    done = [s for s in shares if s[3] > s[1]]
    more = max(said, key=lambda s: (s[1] - s[3], s[0]), default=None)
    less = max(done, key=lambda s: (s[3] - s[1], s[0]), default=None)
    pieces = []
    if more:
        pieces.append(f"{more[0]} is on {pct(more[1])} of your wished games, in {pct(more[2])} of the games you "
                      f"have played and in {pct(more[3])} of your hours")
    if less:
        pieces.append(f"{less[0]} the other way: in {pct(less[3])} of your hours and {pct(less[2])} of the games "
                      f"you have played, on {pct(less[1])} of your wishes")
    sentence = ("; ".join(pieces) + ".") if pieces else "What you wish for and what you play share the same genres."
    shown = shares[: rules.REPORT_LIST_ROWS]
    return Report(sentence=sentence[0].upper() + sentence[1:], parts=(
        Part("On your wishlist", bars=tuple(Bar(g, w, pct(w)) for g, w, _c, _h, _n in shown),
             note=f"{with_genre} of {count(wished_games, 'wished game')} have a genre"
                  + (f"; {wished_games - with_genre} not fetched yet" if wished_games > with_genre else "") + "."),
        Part("In the games you have played", bars=tuple(Bar(g, c, pct(c)) for g, _w, c, _h, _n in shown),
             note=f"Of the {count(played_all, 'game')} you have played that have a genre."),
        Part("In your hours", bars=tuple(Bar(g, h, pct(h)) for g, _w, _c, h, _n in shown),
             note=f"Of the {total_hours(minutes_all)} on games with a genre."),
        Part("Side by side", ("Genre", "Wishlist", "Games played", "Hours", "Wishlist − hours"),
             tuple((g, pct(w), pct(c), pct(h), _points(w - h)) for g, w, c, h, _n in shown),
             tuple((g, n, round(w, 4), round(c, 4), round(h, 4), round(w - h, 4)) for g, w, c, h, n in shares),
             data_columns=("genre", "wished_games", "wishlist_share", "played_share", "hours_share", "gap"))), **base)


def _points(gap: float) -> str:
    """A gap between two shares in percentage points: "+54 points", "+1 point", "-22 points"."""
    value = round(gap * 100)
    return f"{value:+d} point{'' if abs(value) == 1 else 's'}"


def recommendation(data: dict) -> Report:
    """Report 9 (Phase 98): what is waiting, most like what you play; how long a game's session usually runs;
    and, looking back, whether the ranking placed the game you started next near the top."""
    profile = fit.profile_from(data["concentration"], data["recommend_genres"])  # = profile_of(wishlist_profile)
    built = recommend.page_of(data["backlog"], data["recommend_genres"], profile, data["wishlist_idf"],
                              data["session_lengths_by_game"])
    looked = recommend.retrospective(data["recommend_history"], data["session_lengths_by_game"],
                                     data["recommend_genres"], data["wishlist_idf"])
    base = dict(number=9, key="recommendation", title="Recommendation",
                question="Of what is installed and not started, what is most like what you play — and does that "
                         "say what you play next?",
                queries=("backlog", "concentration", "recommend_genres", "wishlist_idf",
                         "session_lengths_by_game", "recommend_history"),
                caveat=("The fit sees genres only — not a game's length, price, reviews, friends or mood — and a game "
                        "with no Steam record has none, so it is named, never ranked. The waiting games are report "
                        "4's never and under two hours, installed, not hidden, not Finished or Dropped; the ones "
                        f"played in the last {rules.FORYOU_RECENT_DAYS} days are left out. A typical session is the "
                        f"median of a game's sessions, judged only with {rules.SESSION_MEDIAN_MIN} or more. Looking "
                        "back takes the day a game was first seen as the day it arrived (the launcher keeps no install "
                        "date), does not know when a game was uninstalled, tastes the past from the launcher's own "
                        "sessions only (Steam's hours have no dates, so a game Steam counts is left out), and weighs "
                        "the genres as the library has them today."),
                concept=("Content-based filtering: each game described by its features — its genres, each weighted by "
                         "how rare it is (TF-IDF) — what you play as one profile weighted by your hours, and the "
                         "cosine similarity of the two. Collaborative filtering would need other people's choices; "
                         "the launcher has one person's. The cold-start problem: a game with no features cannot be "
                         "placed. The median: a typical session one marathon does not move. Offline evaluation: rank "
                         "as on the evening before, then see where the game actually chosen came — the hit rate in "
                         "the top three, the mean rank; on a handful of evenings it says little."))
    if not data["backlog"] and not built.typical and not looked.cases:
        return Report(sentence="Nothing is installed and nothing has been played yet: there is nothing to rank or "
                               "to look back on.", empty=True, **base)
    ranked = built.picks + built.more
    pieces = []
    if ranked:
        first = ranked[0]
        level = [s.name for s in ranked if s.share == first.share]
        if len(level) > 3:  # a tie of many: three named, the rest counted
            level = level[:3] + [f"{len(level) - 3} more"]
        named = ", ".join(level[:-1]) + f" and {level[-1]}" if len(level) > 1 else level[0]
        waiting = len(built.raw["ranked"])
        pieces.append(f"Of {count(waiting, 'waiting game')} that can be compared, {named} "
                      f"{'come' if len(level) > 1 else 'comes'} first, {first.likeness}")
    elif built.cold:
        pieces.append("No waiting game can be ranked yet: " + built.cold_line[0].lower() + built.cold_line[1:-1])
    elif built.empty:
        pieces.append(built.empty[:-1])
    evenings = looked.ranked
    if evenings:
        words = (f"looking back, the game you started next was among the first {rules.FORYOU_GAMES} on "
                 f"{looked.top} of {count(len(evenings), 'evening')} it could be ranked, its mean rank "
                 f"{looked.mean_rank:.1f}")
        if len(evenings) < rules.REPORT_LOOK_BACK_MIN:
            words += " — too few to say whether the fit foretells anything"
        pieces.append(words)
    elif looked.cases:
        pieces.append(f"no evening can be looked back on yet: {looked.same_day} of {len(looked.cases)} first plays "
                      "came the day the game arrived")
    sentence = "; ".join(pieces) + "."
    notes = " ".join(line for line in (built.cold_line, built.recent_line) if line)
    if built.beyond:
        notes = (f"And {built.beyond} more. " + notes).strip()
    judged = sorted((t for t in built.typical.values() if t.judged), key=lambda t: (t.median, t.name.casefold()))
    unjudged = sum(1 for t in built.typical.values() if not t.judged)
    timed = lambda m: humanize.playtime(round(m * 60))  # noqa: E731
    parts = (
        Part("Waiting, most like what you play", ("", "Game", "Fit", "Genres", "Played"),
             tuple((str(i), s.name, s.likeness.replace(" like what you play", ""), s.genres, s.played)
                   for i, s in enumerate(ranked, 1)),
             tuple((i, s.name, round(s.share, 4), s.genres, s.played) for i, s in enumerate(ranked, 1)),
             note=notes or ("" if ranked else "None."),
             data_columns=("rank", "game", "fit", "genres", "played")),
        Part("Typical sessions", ("Game", "Sessions", "Median", "Shortest", "Longest", "Can be offered"),
             tuple((t.name, str(t.sessions), timed(t.median), timed(min(t.minutes)), timed(max(t.minutes)),
                    "yes" if t.offered else "no") for t in judged),
             tuple((t.name, t.sessions, t.median, min(t.minutes), max(t.minutes), int(t.offered)) for t in judged),
             note=(f"Judged on {count(len(judged), 'game')} with {rules.SESSION_MEDIAN_MIN} sessions or more; "
                   f"{unjudged:,} more {'has' if unjudged == 1 else 'have'} fewer. \"Can be offered\": installed, "
                   "not hidden, not Dropped — what Tonight may offer."),
             data_columns=("game", "sessions", "median_minutes", "shortest_minutes", "longest_minutes", "offered")),
        # The evenings that could be judged, or say why not; the ones played the day they arrived only counted
        # in the note (they are most of them), and all of them in the CSV file.
        Part("Looking back", ("Game", "First played", "Rank that evening", "Of", "Note"),
             tuple((c.name, _day(c.day), str(c.rank) if c.rank else "—", str(c.of) if c.rank else "—", c.note)
                   for c in looked.cases if c.note != recommend.SAME_DAY),
             tuple((c.name, c.day, c.rank, c.of, c.note) for c in looked.cases),
             note=(f"{looked.same_day} of {count(len(looked.cases), 'first play')} came the day the game arrived, "
                   "so it was never waiting: not listed."
                   + (" Left out: " + "; ".join(f"{why}, {n}" for why, n in looked.left_out) + "."
                      if looked.left_out else "")) if looked.cases else "No first play to look back on yet.",
             data_columns=("game", "first_played", "rank", "of", "note")),
    )
    return Report(sentence=sentence[0].upper() + sentence[1:], parts=parts, **base)


def ranks(values) -> list[float]:
    """Each value's rank, 1 the smallest; tied values share the mean of the ranks they span (1, 2.5, 2.5, 4)."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    found = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            found[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return found


def spearman(xs, ys) -> float | None:
    """Spearman's rank correlation: the Pearson correlation of the two lists' ranks, ties given their mean rank.
    From -1 to 1; None when it cannot be said -- fewer than two pairs, or one list the same throughout."""
    xs, ys = list(xs), list(ys)
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    rx, ry = ranks(xs), ranks(ys)
    n = len(rx)
    mx, my = sum(rx) / n, sum(ry) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    sxx = sum((a - mx) ** 2 for a in rx)
    syy = sum((b - my) ** 2 for b in ry)
    if not sxx or not syy:
        return None
    return sxy / (sxx * syy) ** 0.5


def correlation_words(rho: float | None, n: int, what: str) -> str:
    """A rank correlation in words, honest about how many games it rests on (rules.REPORT_SPEARMAN_*)."""
    if n < rules.REPORT_SPEARMAN_MIN:
        return (f"{count(n, 'game')} {'is' if n == 1 else 'are'} too few to set {what} side by side "
                f"(it takes {rules.REPORT_SPEARMAN_MIN})")
    if rho is None:
        return f"{what} cannot be ranked against each other: one of them is the same for all {n} games"
    figure = f"\u03c1 = {rho:+.2f} on {n} games"
    if n < rules.REPORT_SPEARMAN_HINT:
        return f"{what} give {figure} \u2014 on so few, a hint and not a finding"
    strength = next(word for limit, word in rules.REPORT_CORRELATION_WORDS if abs(rho) < limit)
    if abs(rho) < rules.REPORT_CORRELATION_WORDS[0][0]:
        return f"{strength} rank correlation between {what}, {figure}"
    way = "they rise together" if rho > 0 else "as one rises the other falls"
    return f"{strength} rank correlation between {what}, {figure}: {way}"


def _rank(value: float) -> str:
    return str(int(value)) if value == int(value) else f"{value:.1f}"


def _stars(mean: float) -> str:
    return f"{mean:.1f} of {rules.RATE_STARS}"


def _first_up(text: str) -> str:
    return text[:1].upper() + text[1:]


def said_played(data: dict) -> Report:
    """Report 10 (Phase 102): what the stars say against the hours -- explicit feedback beside implicit --
    and the recommender's second check, its fit against the stars."""
    # Each rated game's hours are report 1's row for it (the same game: its Steam app, else its record); one it
    # has none for has no hours report 1 counts -- a Steam game on no account marked yours, a demo -- and is
    # left out of what is set against the hours, never shown as 0.
    hours_of = {("app", g["appid"]) if g["appid"] is not None else ("game", g.get("game_id")): g
                for g in data["concentration"]}
    rows = []
    for r in data["said_played"]:
        found = hours_of.get(("app", r["appid"]) if r["appid"] is not None else ("game", r["game_id"]))
        rows.append({**r, "name": found["name"] if found else r["name"], "minutes": found["minutes"] if found else None})
    rows.sort(key=lambda r: (-r["mean_stars"], -(r["minutes"] if r["minutes"] is not None else -1),
                             str(r["name"]).casefold()))
    total = sum(r["ratings"] for r in rows)
    late = sum(r["late"] or 0 for r in rows)
    base = dict(number=10, key="said_played", title="Said and played",
                question="Do the games you rate well get your hours \u2014 and does the fit foretell your stars?",
                queries=("said_played", "concentration", "recommend_genres", "wishlist_idf"),
                caveat=("You rate when you choose to: a session skipped or left unanswered writes nothing, so the "
                        "rated sessions are the ones you felt like rating \u2014 response bias, not a random sample. "
                        "One question a game a day: a day of three sessions of one game gives one rating. A rating "
                        f"can come late, from a game's page, up to {rules.RATE_LATE_DAYS} days after its session "
                        f"({late} of {count(total, 'rating')} did); nothing older is asked for. The hours are "
                        "lifetime, from both sources, while the ratings began when the launcher started asking: a "
                        "game played for years and rated twice is judged on two evenings. A game's mean needs "
                        f"{rules.REPORT_RATED_MIN} ratings; a correlation is worked out from "
                        f"{rules.REPORT_SPEARMAN_MIN} games and read as a finding only from "
                        f"{rules.REPORT_SPEARMAN_HINT}. The fit is measured against your taste without the game "
                        "itself \u2014 its own hours left out \u2014 or every much-played game would look like what "
                        "you play."),
                concept=("Explicit and implicit feedback: what you say about a game (the stars) against what you do "
                         "with it (the hours); recommenders learn mostly from the second, because the first is "
                         "scarce. Rank correlation: Spearman's \u03c1 is the Pearson correlation of the two lists' "
                         "ranks (tied values share their mean rank), from \u22121 to 1 \u2014 ranks, because the "
                         "hours have a long tail (report 1) that would let one game decide an ordinary correlation. "
                         "Response bias: who answers, and when, is not random. Rating sparsity: most sessions are "
                         "never rated and most games never twice \u2014 the table of games and ratings is mostly "
                         "empty, which is why a recommender cannot wait for stars."))
    if not total:
        return Report(sentence=(f"No session has been rated yet: the question comes after a session of "
                                f"{rules.RATE_MIN_MINUTES} minutes or more, and a game's page rates the last "
                                f"{rules.RATE_LATE_DAYS} days'."), empty=True, **base)
    judged = [r for r in rows if r["ratings"] >= rules.REPORT_RATED_MIN]
    once = len(rows) - len(judged)
    times = {1: "once", 2: "twice"}.get(rules.REPORT_RATED_MIN, f"{rules.REPORT_RATED_MIN} times")
    pieces = [f"{count(total, 'rating')} on {count(len(rows), 'game')}, "
              + (f"{len(judged)} of them rated {times} or more" if judged
                 else f"none rated {times} yet, which a game's mean takes")]
    timed = [r for r in judged if r["minutes"] is not None]
    by_stars = ranks([-r["mean_stars"] for r in judged])  # 1 the best rated
    hour_rank = dict(zip(map(id, timed), ranks([-r["minutes"] for r in timed])))  # 1 the most played
    rho = spearman([r["mean_stars"] for r in timed], [r["minutes"] for r in timed])
    if judged:
        pieces.append(correlation_words(rho, len(timed), "the stars and the hours"))
    # The recommender's second check: each rated game's fit to what you play without it, against its stars.
    weights = fit.weights_of(data["wishlist_idf"])
    profile = fit.profile_from(data["concentration"], data["recommend_genres"])
    genres: dict[int, list] = {}
    for row in data["recommend_genres"]:
        genres.setdefault(row["appid"], []).append(row["genre_id"])
    fitted, unfitted = [], 0
    for r in judged:
        game = fit.vector(genres.get(r["appid"], ()), weights) if r["appid"] is not None and r["has_record"] else {}
        rest = fit.taste({k: v for k, v in profile.items() if k != r["appid"]}, weights)
        if not game or not rest:
            unfitted += 1
            continue
        fitted.append((r, fit.share_of(game, rest)))
    rho_fit = spearman([share for _r, share in fitted], [r["mean_stars"] for r, _share in fitted])
    if fitted:
        pieces.append(correlation_words(rho_fit, len(fitted), "the fit and the stars"))
    well = [r for r in timed if r["mean_stars"] >= rules.REPORT_RATED_WELL
            and r["minutes"] < rules.REPORT_BARELY_PLAYED_MINUTES]
    low = [r for r in timed if r["mean_stars"] <= rules.REPORT_RATED_LOW
           and r["minutes"] >= rules.REPORT_PLAYED_MUCH_MINUTES]
    untimed = len(judged) - len(timed)
    sentence = "; ".join(pieces) + "."
    parts = (
        Part("Mean stars", bars=tuple(Bar(r["name"], r["mean_stars"] / rules.RATE_STARS,
                                          f"{_stars(r['mean_stars'])} \u00b7 {count(r['ratings'], 'rating')}")
                                      for r in judged[: rules.REPORT_LIST_ROWS]),
             note="" if judged else f"No game rated {rules.REPORT_RATED_MIN} times yet."),
        Part("Said and played", ("Game", "Ratings", "Mean stars", "Hours", "By stars", "By hours"),
             tuple((r["name"], str(r["ratings"]), _stars(r["mean_stars"]),
                    hours(r["minutes"]) if r["minutes"] is not None else "\u2014", _rank(s),
                    _rank(hour_rank[id(r)]) if id(r) in hour_rank else "\u2014")
                   for r, s in zip(judged, by_stars)),
             tuple((r["name"], r["ratings"], round(r["mean_stars"], 3),
                    round(r["minutes"]) if r["minutes"] is not None else None, s, hour_rank.get(id(r)))
                   for r, s in zip(judged, by_stars)),
             note=(f"Rank 1 is the best rated and the most played; tied games share their mean rank. "
                   + (f"{count(once, 'game')} rated once {'is' if once == 1 else 'are'} not in it. " if once else "")
                   + (f"{count(untimed, 'game')} without hours report 1 counts (a Steam game on no account marked "
                      "yours, or a demo) left out of what is set against the hours." if untimed else "")
                   ).strip(),
             data_columns=("game", "ratings", "mean_stars", "minutes", "rank_by_stars", "rank_by_hours")),
        Part("Where they disagree", ("Game", "Mean stars", "Hours", "Which way"),
             tuple((r["name"], _stars(r["mean_stars"]), hours(r["minutes"]), way) for way, group in
                   (("rated well, barely played", well), ("played much, rated low", low)) for r in group),
             tuple((r["name"], round(r["mean_stars"], 3), round(r["minutes"] or 0), way) for way, group in
                   (("rated well, barely played", well), ("played much, rated low", low)) for r in group),
             note=("" if well or low else
                   f"None: no game rated {rules.REPORT_RATED_WELL:g} or better on average played under "
                   f"{_span(rules.REPORT_BARELY_PLAYED_MINUTES)}, and none rated {rules.REPORT_RATED_LOW:g} or lower "
                   f"played {_span(rules.REPORT_PLAYED_MUCH_MINUTES)} or more."),
             data_columns=("game", "mean_stars", "minutes", "which_way")),
        Part("The fit against the stars", ("Game", "Fit", "Mean stars"),
             tuple((r["name"], fit.like_words(share).replace(" like what you play", ""), _stars(r["mean_stars"]))
                   for r, share in sorted(fitted, key=lambda item: (-item[1], item[0]["name"]))),
             tuple((r["name"], round(share, 4), round(r["mean_stars"], 3)) for r, share in fitted),
             note=(_first_up(correlation_words(rho_fit, len(fitted), "the fit and the stars")) + "."
                   + (f" {count(unfitted, 'game')} without genres to compare (no Steam record, or nothing else "
                      "played to compare with) left out." if unfitted else "")) if judged else "",
             data_columns=("game", "fit", "mean_stars")),
    )
    return Report(sentence=_first_up(sentence), parts=parts, **base)


def kaplan_meier_median(spans) -> float | None:
    """The time by which half would have finished: Kaplan-Meier's product-limit estimate on (days, finished)
    pairs -- finished False is a game with no end yet (censored). At a tie the finishes count before the
    censored, as is usual. None when the share not yet finished never falls to a half."""
    spans = list(spans)
    at_risk, share = len(spans), 1.0
    for t in sorted({d for d, _f in spans}):
        ended = sum(1 for d, f in spans if d == t and f)
        if ended:
            share *= 1 - ended / at_risk
            if share <= 0.5:
                return t
        at_risk -= sum(1 for d, _f in spans if d == t)
    return None


def _moment(text: str | None) -> datetime | None:
    if not text:
        return None
    found = datetime.fromisoformat(text)
    return found if found.tzinfo else found.astimezone()


def _days(start: datetime | None, end: datetime | None) -> int | None:
    return int((end - start).total_seconds() // 86400) if start is not None and end is not None else None


def _to_mark(row) -> int | None:
    """Days from a game's first counted session to its mark -- None when either is unknown, or when the mark
    came first: a game decided before the launcher saw it played cannot say how long it took."""
    days = _days(_moment(row["first_session"]), _moment(row["status_changed_at"]))
    return days if days is not None and days >= 0 else None


def finishing(data: dict) -> Report:
    """Report 11 (Phase 103): of the games you mark, how many you finish, how long it takes, and at how many
    hours a game is finished or dropped."""
    rows = data["finishing"]
    now = data.get("now") or datetime.now().astimezone()
    undated = sum(1 for r in rows if not r["status_changed_at"])
    base = dict(number=11, key="finishing", title="Finishing",
                question="Of the games you mark, how many do you finish \u2014 and how long does it take?",
                queries=("finishing", "concentration"),
                caveat=("A mark is yours, and late by nature: it is set when you think of it \u2014 Left behind "
                        "asks for the ones overdue. A mark set before version 8 carries no date: counted, never "
                        f"timed ({undated} of {count(len(rows), 'mark')} here). The library keeps a game's mark as it "
                        "is now and the moment it was last set, not its history: a game marked Playing and later "
                        "Finished counts once, as Finished. The time to Finished runs from the game's first counted "
                        "session to its mark -- a mark set before that session is counted, not timed; a game still "
                        "Playing has no end yet and is counted as not finished "
                        "after its days so far. The hours are today's, as the reports count them (Steam's counter "
                        "has no dates) \u2014 for a game finished, near enough the hours it was finished at. On a "
                        f"handful of games one more finish moves the rate by many points; under {rules.REPORT_DECIDED_MIN} "
                        "decided it is a hint."),
                concept=("Completion rate: of the games decided \u2014 finished or dropped \u2014 the share "
                         "finished; a game still playing is not decided and is not in it. Time to event: how long "
                         "from a start to an end, here the first session to the Finished mark. Censoring: a game "
                         "still Playing has no end yet; leaving it out keeps only the quick finishes and pulls the "
                         "median down, so the Kaplan\u2013Meier estimate counts it as not finished after its days so "
                         "far and gives the time by which half would have finished. The median: the middle, which "
                         "one very long or very short game does not move."))
    if not rows:
        return Report(sentence=("No game carries a mark yet: Playing, Finished and Dropped are set on a game's page, "
                                "or answered in For you's Left behind."), empty=True, **base)
    hours_of = {("app", g["appid"]) if g["appid"] is not None else ("game", g.get("game_id")): g["minutes"]
                for g in data["concentration"]}

    def minutes(r):
        found = hours_of.get(("app", r["appid"]) if r["appid"] is not None else ("game", r["game_id"]))
        if found is not None:
            return float(found)
        return 0.0 if r["launch_kind"] == "exe" else None  # a game the launcher starts: none is none; else unknown

    by = {status: [r for r in rows if r["status"] == status]
          for status in (rules.STATUS_FINISHED, rules.STATUS_DROPPED, rules.STATUS_PLAYING)}
    done, dropped, playing = by[rules.STATUS_FINISHED], by[rules.STATUS_DROPPED], by[rules.STATUS_PLAYING]
    behind = {g.key for g in recommend.all_left_behind(
        [{**r, "minutes": minutes(r) or 0} for r in playing], now)}
    decided = len(done) + len(dropped)
    pieces = [f"{count(len(rows), 'game')} {'carries' if len(rows) == 1 else 'carry'} a mark: {len(done)} Finished, "
              f"{len(dropped)} Dropped, {len(playing)} still Playing ("
              + (f"{len(behind)} of them left behind)" if behind else "none left behind)")]
    if decided:
        words = (f"{len(done)} of {count(decided, 'decided game')} finished "
                 f"({pct(len(done) / decided)})")
        if decided < rules.REPORT_DECIDED_MIN:
            words += " \u2014 on so few, a hint and not a finding"
        pieces.append(words)
    timed = [(r, d) for r, d in ((r, _to_mark(r)) for r in done) if d is not None]
    spans = [(d, True) for _r, d in timed]
    spans += [(d, False) for d in (_to_mark(r) for r in dropped) if d is not None]
    spans += [(d, False) for d in (_days(_moment(r["first_session"]), now) for r in playing) if d is not None]
    km = kaplan_meier_median(spans)
    still = sum(1 for _d, f in spans if not f)
    if timed:
        days = sorted(d for _r, d in timed)
        middle = statistics.median(days)
        early = sum(1 for r in done if r["status_changed_at"] and r["first_session"] and _to_mark(r) is None)
        pieces.append(f"from the first session to Finished a median of {middle:g} days"
                      + (f" ({days[0]} to {days[-1]})" if len(days) > 1 else "")
                      + f" on {count(len(days), 'dated mark')}"
                      + (f" ({early} more set before the game's first session, not timed)" if early else "") + ", "
                      + (f"{km:g} days counting the {still} not finished as still going (Kaplan\u2013Meier)" if km
                         is not None else f"and with the {still} not finished counted as still going, fewer than "
                                          "half have finished yet (Kaplan\u2013Meier)"))
    else:
        pieces.append("no Finished mark is timed yet" + (f" ({len(done)} counted, none with a date after its first "
                                                         "session)" if done else ""))
    known = {status: [m for m in (minutes(r) for r in group) if m is not None]
             for status, group in ((rules.STATUS_FINISHED, done), (rules.STATUS_DROPPED, dropped))}
    medians = {status: statistics.median(m) if m else None for status, m in known.items()}
    def played(m: float) -> str:
        return "nothing" if m < 0.5 else hours(m)

    said = []
    if medians[rules.STATUS_FINISHED] is not None:
        said.append(f"Finished games had a median of {played(medians[rules.STATUS_FINISHED])} played")
    if medians[rules.STATUS_DROPPED] is not None:
        said.append(f"Dropped ones {played(medians[rules.STATUS_DROPPED])}" if said else
                    f"Dropped games had a median of {played(medians[rules.STATUS_DROPPED])} played")
    if said:
        pieces.append(", ".join(said))
    sentence = "; ".join(pieces) + "."
    total = len(rows)
    bars = tuple(Bar(label, n / total, str(n)) for label, n in (
        ("Finished", len(done)), ("Dropped", len(dropped)), ("Still Playing", len(playing)),
        ("of them left behind", len(behind))))

    def day(text):
        return _day(text) if text else "\u2014"

    def hrs(r):
        m = minutes(r)
        return hours(m) if m is not None else "\u2014"

    def part(heading, group, columns, cells, data_columns, values, note=""):
        return Part(heading, columns, tuple(cells(r) for r in group), tuple(values(r) for r in group),
                    note=note or ("" if group else "None."), data_columns=data_columns)

    parts = (
        Part("The marks", bars=bars, note=f"{undated} of {count(total, 'mark')} undated (set before version 8)."),
        part("Finished", done, ("Game", "First session", "Finished on", "Days", "Hours"),
             lambda r: (r["name"], day(r["first_session"]), day(r["status_changed_at"]),
                        str(_to_mark(r)) if _to_mark(r) is not None else "\u2014", hrs(r)),
             ("game", "first_session", "finished_on", "days", "minutes"),
             lambda r: (r["name"], r["first_session"], r["status_changed_at"], _to_mark(r), minutes(r))),
        part("Not finished yet (censored)", playing, ("Game", "First session", "Days so far", "Left behind", "Hours"),
             lambda r: (r["name"], day(r["first_session"]),
                        str(_days(_moment(r["first_session"]), now)) if r["first_session"] else "\u2014",
                        "yes" if r["identity_key"] in behind else "", hrs(r)),
             ("game", "first_session", "days_so_far", "left_behind", "minutes"),
             lambda r: (r["name"], r["first_session"], _days(_moment(r["first_session"]), now),
                        int(r["identity_key"] in behind), minutes(r)),
             note=f"Counted as not finished after their days so far; left behind by For you's rule "
                  f"({rules.LEFT_BEHIND_DAYS} days with no sign)."),
        part("Dropped", dropped, ("Game", "First session", "Dropped on", "Hours"),
             lambda r: (r["name"], day(r["first_session"]), day(r["status_changed_at"]), hrs(r)),
             ("game", "first_session", "dropped_on", "minutes"),
             lambda r: (r["name"], r["first_session"], r["status_changed_at"], minutes(r))),
    )
    return Report(sentence=sentence[0].upper() + sentence[1:], parts=parts, **base)


BUILDERS = (concentration, abandonment, profiles, backlog, sessions, money, quality, preference, recommendation,
            said_played, finishing)


def fetch(source) -> dict:
    """Every query's rows, each run once (data_access.reports.Reports)."""
    data = {}
    for name in ("concentration", "abandonment", "profile_coverage", "profile_genres", "profile_decades",
                 "backlog", "session_summary", "session_origins", "session_lengths", "session_hours",
                 "session_weekdays",
                 "money_library", "money_paid", "money_proxy", "money_sales", "money_lowest", "money_wishlist",
                 "money_series",
                 "quality_types", "quality_set_aside", "quality_sources", "quality_links", "quality_untimed",
                 "quality_currencies", "stats_lifetime", "stated_revealed",
                 "recommend_genres", "wishlist_idf", "session_lengths_by_game", "recommend_history",
                 "said_played", "finishing"):
        data[name] = source.rows(name)
    companies = source.rows("profile_companies")  # both roles in one run (Phase 98), split here
    data["profile_publishers"] = [r for r in companies if r["role"] == "publisher"]
    data["profile_developers"] = [r for r in companies if r["role"] == "developer"]
    return data


def build(source) -> list[Report]:
    """The eleven reports from a library's queries — or none, when the library cannot answer them. The hours are
    worked out once for the whole build (`Reports.worked_out_once`, Phase 103)."""
    if source is None:
        return []
    once = getattr(source, "worked_out_once", None)
    if once is None:
        data = fetch(source)
    else:
        with once():
            data = fetch(source)
    return [builder(data) for builder in BUILDERS]


# — the command line's forms ----------------------------------------------------------------------

def markdown(reports: list[Report], made: datetime, queries: dict | None = None) -> str:
    """Every report as Markdown, with the day it was made — what refreshes docs/ANALIZA.md's numbers.
    With `queries` (name -> SQL), each report's SQL follows it."""
    lines = [f"# Reports", "", f"Made on {made:%Y-%m-%d %H:%M}.", ""]
    for report in reports:
        lines += [f"## {report.number}. {report.title}", "", f"**{report.question}**", "", report.sentence, ""]
        for part in report.parts:
            if not (part.bars or part.rows or part.note):
                continue  # a part kept for the CSV files alone
            lines += [f"### {part.heading}", ""]
            if part.bars:
                lines += ["| | |", "|---|---|"] + [f"| {_cell(bar.label)} | {_cell(bar.value)} |" for bar in part.bars]
                lines.append("")
            if part.rows:
                lines += ["| " + " | ".join(part.columns) + " |", "|" + "---|" * len(part.columns)]
                lines += ["| " + " | ".join(_cell(c) for c in row) + " |" for row in part.rows]
                lines.append("")
            if part.note:
                lines += [part.note, ""]
        lines += [f"*What it cannot see.* {report.caveat}", "", f"*The idea.* {report.concept}", ""]
        if queries:
            for name in report.queries:
                lines += [f"```sql", f"-- {name}", queries[name], "```", ""]
    return "\n".join(lines)


def _cell(text) -> str:
    return str(text).replace("|", "\\|")


def tables(report: Report) -> list[tuple[str, tuple, tuple]]:
    """A report's parts as (heading, columns, rows of plain values) — one CSV file per report."""
    found = []
    for part in report.parts:
        if part.data:
            columns = part.data_columns or part.columns
            if len(columns) != len(part.data[0]):
                columns = tuple(f"column {i + 1}" for i in range(len(part.data[0])))
            found.append((part.heading, columns, part.data))
        elif part.bars:
            found.append((part.heading, ("", "value"), tuple((b.label, b.value) for b in part.bars)))
        elif part.note:
            found.append((part.heading, ("note",), ((part.note,),)))
    return found
