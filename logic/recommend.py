"""For you (Phase 98): of what is installed and not started, what is most like what you play, and why;
and, with the time there is tonight, what fits.

No Qt and no SQL: `page` takes the store's queries -- report 4's own `backlog`, and For you's in
data_access/recommend.py -- and hands back a Page, every line a sentence with its numbers. The waiting games
are report 4's rows, never a second copy of its rule: `waiting` keeps its 'never' and 'under' that are not
hidden, not Finished or Dropped. The score is logic/fit.py's -- the Wishlist page's own fit
-- so a game reads the same words here as a wished game does there: "72% like what you play · Action,
RPG". It is similarity of genre mix, weighted by the hours, **never a forecast of liking**, and the page
says so once. A game with no genres known is never scored 0: it is named apart (the cold start). A game
played in the last FORYOU_RECENT_DAYS is left out, and named, since Jump back in offers it already.

Tonight is the median of each game's sessions (both origins) -- a robust middle a single marathon does
not move -- for the games with SESSION_MEDIAN_MIN sessions or more; a game with fewer is not judged, and
the page says on how many it judged.
"""

from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta

from logic import fit as fit_module
from shared import humanize
from shared import rules

log = logging.getLogger(__name__)

QUIET = ("Like what you play means a similar mix of genres, weighted by your hours: not a promise you "
         "will like it.")
NOTHING_WAITING = ("Nothing is waiting: every installed game has been played two hours or more, or is "
                   "marked Finished or Dropped.")
ALL_RECENT = f"Everything waiting was played in the last {rules.FORYOU_RECENT_DAYS} days: Jump back in offers it."
# Report 9's look back (Phase 98): why an evening could not be ranked.
SAME_DAY = "played the day it arrived: never waiting"
NO_GENRES = "no genres to compare by"
NO_PAST = "nothing played before it to compare with"
# Left behind (Phase 103): the row's own words.
LEFT_NOTE = f"Marked Playing, not played for {rules.LEFT_BEHIND_DAYS} days or more"
STILL_LINE = f"\"Still playing\" leaves it alone for another {rules.LEFT_BEHIND_DAYS} days."
ANSWERS = (("finished", "Finished"), ("dropped", "Dropped"), ("still", "Still playing"))


@dataclass(frozen=True)
class Suggestion:
    """One waiting game, as the page shows it."""
    key: str
    name: str
    share: float
    reason: str  # Phase 89's words: "72% like what you play · Action, RPG"
    played: str  # "never played", "26 min played"
    appid: int | None

    @property
    def likeness(self) -> str:
        return self.reason.split(" · ")[0]

    @property
    def genres(self) -> str:
        return self.reason.split(" · ", 1)[1] if " · " in self.reason else ""


@dataclass(frozen=True)
class Typical:
    """A game's typical session: the median of its sessions' minutes, when it has enough of them."""
    name: str
    key: str  # the record to play: the installed one, if any
    minutes: tuple[int, ...]
    last: str  # the newest session's local start
    offered: bool  # installed, not hidden, not Dropped: Tonight may offer it

    @property
    def sessions(self) -> int:
        return len(self.minutes)

    @property
    def judged(self) -> bool:
        return self.sessions >= rules.SESSION_MEDIAN_MIN

    @property
    def median(self) -> float:
        return float(statistics.median(self.minutes))

    @property
    def usual(self) -> str:
        return f"usually {humanize.playtime(round(self.median * 60))} a session"

    @property
    def pill(self) -> str:
        return self.usual[:1].upper() + self.usual[1:]

    def within(self, limit: int) -> int:
        return sum(1 for m in self.minutes if m <= limit)


@dataclass(frozen=True)
class Tonight:
    minutes: int
    label: str  # "1 h"
    games: tuple = ()  # (Typical, words) for each game offered
    judged: int = 0  # how many games it could judge
    note: str = ""  # "Judged on 7 games you have played 3 times or more"
    empty: str = ""  # why nothing is offered, when nothing is


@dataclass(frozen=True)
class LeftBehind:
    """A game marked Playing that nothing has been heard of for LEFT_BEHIND_DAYS (Phase 103)."""
    key: str
    name: str
    days: int  # since its last session -- or, with none, its last date of play
    hours: str  # "12h 38m", as the reports count them; "" when none are known

    @property
    def words(self) -> str:
        """ "Left 30 days ago at 12h 38m" """
        return f"Left {self.days} day{'' if self.days == 1 else 's'} ago" + (f" at {self.hours}" if self.hours else "")


@dataclass(frozen=True)
class Page:
    picks: tuple = ()  # the first FORYOU_GAMES
    more: tuple = ()  # the rest, up to FORYOU_MORE
    beyond: int = 0  # how many more than that
    cold: tuple = ()  # names with no genres to compare by
    recent: tuple = ()  # names left out, played in the last FORYOU_RECENT_DAYS
    compared: bool = True  # False when nothing played has genres: then nothing waiting can be ranked
    empty: str = ""
    tonight: Tonight | None = None
    typical: dict = field(default_factory=dict)  # name key -> Typical
    keys: dict = field(default_factory=dict)  # a record's identity key -> its game's name key
    raw: dict = field(default_factory=dict)
    left: tuple = ()  # Left behind (Phase 103): LeftBehind, the longest left first

    @property
    def cold_line(self) -> str:
        if not self.cold:
            return ""
        n = len(self.cold)
        if not self.compared:
            return (f"Nothing you have played has genres to compare by yet, so {n} waiting game"
                    f"{'s' if n != 1 else ''} cannot be ranked: {', '.join(self.cold)}.")
        return (f"{n} waiting game{'s have' if n != 1 else ' has'} no genres to compare by: "
                f"{', '.join(self.cold)}.")

    @property
    def recent_line(self) -> str:
        if not self.recent:
            return ""
        return (f"Played in the last {rules.FORYOU_RECENT_DAYS} days, so not offered here: "
                f"{', '.join(self.recent)}.")

    def suggestion(self, key: str) -> Suggestion | None:
        return next((s for s in self.picks + self.more if s.key == key), None)


@dataclass(frozen=True)
class Case:
    """One game's first session, looked back on: where the fit placed it the evening before, if it could."""
    name: str
    day: str  # the first session's day, YYYY-MM-DD
    rank: int | None = None
    of: int = 0  # how many waiting games could be ranked that evening
    note: str = ""


@dataclass(frozen=True)
class Looking:
    """Report 9's look back: every first play considered, and how many were left out, and why."""
    cases: tuple = ()
    left_out: tuple = ()  # (why, how many)

    @property
    def ranked(self) -> tuple:
        return tuple(c for c in self.cases if c.rank is not None)

    @property
    def same_day(self) -> int:
        return sum(1 for c in self.cases if c.note == SAME_DAY)

    @property
    def top(self) -> int:
        return sum(1 for c in self.ranked if c.rank <= rules.FORYOU_GAMES)

    @property
    def mean_rank(self) -> float | None:
        return statistics.mean(c.rank for c in self.ranked) if self.ranked else None


WAITING_STATES = ("never", "under")  # report 4's own words for "not started": never played, or under two hours
NOT_WAITING = (rules.STATUS_FINISHED, rules.STATUS_DROPPED)
PLAYED_DATES = ("last_played", "store_last_played", "steam_last_played")  # the launcher's, the store's, Steam's


def _moment(text: str | None) -> datetime | None:
    """A stored date (ISO text with its offset) as a moment; one with no offset is local wall time."""
    if not text:
        return None
    try:
        found = datetime.fromisoformat(text)
    except ValueError:
        log.warning("for you: a date it cannot read, %r -- taken as no date", text)
        return None
    return found if found.tzinfo else found.astimezone()


def waiting(rows, since: datetime) -> tuple[list, tuple]:
    """For you's waiting games, from report 4's own `backlog` rows: 'never' or 'under' by its rule, not hidden,
    not Finished or Dropped (Playing is still waiting). Those played since `since` -- by the launcher, their
    store or Steam -- come apart, by name: Jump back in offers them already."""
    kept, recent = [], []
    for row in rows:
        if row["state"] not in WAITING_STATES or row["hidden"] or row["status"] in NOT_WAITING:
            continue
        lately = any((m := _moment(row[k])) is not None and m >= since for k in PLAYED_DATES)
        (recent if lately else kept).append(row)
    return kept, tuple(r["name"] for r in recent)


def choice_of(value) -> tuple[int, str, str]:
    """A remembered choice (minutes) as one of TONIGHT_CHOICES; anything else is the default."""
    for choice in rules.TONIGHT_CHOICES:
        if value == choice[0]:
            return choice
    return next(c for c in rules.TONIGHT_CHOICES if c[0] == rules.TONIGHT_DEFAULT)


def _played(row) -> str:
    minutes = row["minutes"] or 0
    return "never played" if row["state"] == "never" or minutes < 1 else f"{humanize.playtime(round(minutes * 60))} played"


def typical_sessions(rows) -> tuple[dict[str, Typical], dict[str, str]]:
    """The session_lengths_by_game rows, by game (its name): the minutes, the newest start, a key to play;
    and each record's key to its game's name key (the database lowers the name, so it is matched by key)."""
    found: dict[str, dict] = {}
    keys: dict[str, str] = {}
    for row in rows:
        keys[row["identity_key"]] = row["name_key"]
        game = found.setdefault(row["name_key"], {"name": row["name"], "key": row["identity_key"], "minutes": [],
                                                  "last": "", "offered": False})
        game["minutes"].append(int(row["minutes"]))
        game["last"] = max(game["last"], row["started_local"] or "")
        if row["offered"] and not game["offered"]:
            game.update(offered=True, key=row["identity_key"], name=row["name"])
    return ({k: Typical(name=g["name"], key=g["key"], minutes=tuple(g["minutes"]), last=g["last"],
                        offered=g["offered"]) for k, g in found.items()}, keys)


def tonight(typical: dict[str, Typical], minutes: int) -> Tonight:
    """The games whose typical session fits the time: median at or under it, ranked by the share of their
    sessions that fit, then by the one played last; only games with SESSION_MEDIAN_MIN sessions or more."""
    limit, label, within = choice_of(minutes)
    judged = [t for t in typical.values() if t.offered and t.judged]
    fits = sorted((t for t in judged if t.median <= limit), key=lambda t: t.name.casefold())
    fits.sort(key=lambda t: t.last, reverse=True)  # then the one played last first (stable sorts, the last decides)
    fits.sort(key=lambda t: t.within(limit) / t.sessions, reverse=True)
    games = tuple((t, f"{t.sessions} sessions, {'all' if t.within(limit) == t.sessions else t.within(limit)} {within}")
                  for t in fits[: rules.FORYOU_TONIGHT])
    n = len(judged)
    note = f"Judged on {n} game{'s' if n != 1 else ''} you have played {rules.SESSION_MEDIAN_MIN} times or more" if n else ""
    if not n:
        empty = (f"No game has {rules.SESSION_MEDIAN_MIN} sessions yet: Tonight learns how long you play as you "
                 "play.")
    elif not games:
        empty = f"Nothing you have played {rules.SESSION_MEDIAN_MIN} times or more usually fits {within}."
    else:
        empty = ""
    return Tonight(minutes=limit, label=label, games=games, judged=n, note=note, empty=empty)


def recent_since(now: datetime | None = None) -> datetime:
    """The moment FORYOU_RECENT_DAYS before now: a game played since is left out, and named."""
    return (now or datetime.now().astimezone()).astimezone() - timedelta(days=rules.FORYOU_RECENT_DAYS)


def page(source, choice: int | None = None, now: datetime | None = None) -> Page:
    """The For you page, from the store's queries (`LibraryStore.recommend()`)."""
    built = page_of(source.rows("backlog"), source.rows("recommend_genres"),
                    fit_module.profile_of(source.rows("wishlist_profile")), source.rows("wishlist_idf"),
                    source.rows("session_lengths_by_game"), choice, now)
    built = replace(built, left=left_behind(source.rows("left_behind"), now))
    log.info("for you: %d waiting game(s) ranked, %d with no genres, %d played lately; Tonight at %s: %d of %d judged; "
             "%d left behind", len(built.raw["ranked"]), len(built.cold), len(built.recent), built.tonight.label,
             len(built.tonight.games), built.tonight.judged, len(built.left))
    return built


def left_behind(rows, now: datetime | None = None) -> tuple:
    """The games marked Playing that nothing has been heard of for LEFT_BEHIND_DAYS (Phase 103), from the
    `left_behind` query's rows: no counted session -- or, for a game with none, no other date of play -- and no
    mark set and no nudge answered in that time. The longest left first (then by name), at most
    LEFT_BEHIND_GAMES. A game with no date of play at all is never asked about: unknown is not long ago."""
    return all_left_behind(rows, now)[: rules.LEFT_BEHIND_GAMES]


def all_left_behind(rows, now: datetime | None = None) -> tuple:
    """Every game left behind by `left_behind`'s rule, uncapped: what report 11 counts."""
    now = (now or datetime.now().astimezone()).astimezone()
    found = []
    for row in rows:
        played = _moment(row["last_session"])
        if played is None:  # no counted session: its newest date of play from anywhere
            dates = [d for d in (_moment(row[name]) for name in PLAYED_DATES) if d is not None]
            played = max(dates) if dates else None
        if played is None:
            continue
        heard = max(d for d in (played, _moment(row["status_changed_at"]), _moment(row["nudged_at"])) if d is not None)
        if now - heard < timedelta(days=rules.LEFT_BEHIND_DAYS):
            continue
        minutes = row["minutes"] or 0
        found.append(LeftBehind(key=row["identity_key"], name=row["name"], days=(now - played).days,
                                hours=humanize.playtime(round(minutes * 60)) if minutes > 0 else ""))
    found.sort(key=lambda g: (-g.days, g.name.casefold()))
    return tuple(found)


def page_of(backlog_rows, genre_rows, profile: dict, idf_rows, session_rows, choice: int | None = None,
            now: datetime | None = None) -> Page:
    """The page from the queries' rows and the profile of what is played (`fit.profile_of` or, for report 9,
    `fit.profile_from`: the same dict) -- the page's and report 9's one way of working it out."""
    rows, recent = waiting(backlog_rows, recent_since(now))
    genres: dict[int, list] = {}
    for row in genre_rows:
        genres.setdefault(row["appid"], []).append((row["genre_id"], row["name"]))
    weights = fit_module.weights_of(idf_rows)
    played = fit_module.taste(profile, weights)
    scored, cold = [], []
    for row in rows:
        found = (fit_module.fit(genres.get(row["steam_appid"], []), profile, bool(row["has_record"]), weights, played)
                 if row["steam_appid"] else fit_module.Fit(None, fit_module.NOT_FETCHED))
        if found.share is None:
            cold.append(row["name"])
            continue
        scored.append(Suggestion(key=row["identity_key"], name=row["name"], share=found.share, reason=found.words,
                                 played=_played(row), appid=row["steam_appid"]))
    ranked = sorted(scored, key=lambda s: (-s.share, s.name.casefold()))
    typical, keys = typical_sessions(session_rows)
    rest = ranked[rules.FORYOU_GAMES:]
    built = Page(picks=tuple(ranked[: rules.FORYOU_GAMES]), more=tuple(rest[: rules.FORYOU_MORE]),
                 beyond=max(0, len(rest) - rules.FORYOU_MORE), cold=tuple(cold), recent=recent,
                 compared=bool(played),
                 empty="" if ranked or cold else ALL_RECENT if recent else NOTHING_WAITING,
                 tonight=tonight(typical, choice_of(choice)[0]), typical=typical, keys=keys,
                 raw={"ranked": [(s.name, round(s.share, 4)) for s in ranked], "cold": cold, "recent": list(recent)})
    return built


def retrospective(games, sessions, genre_rows, idf_rows) -> Looking:
    """Report 9's look back, an offline evaluation: for each game's first counted session, the games waiting
    the evening before ranked by the fit as it stood then -- the taste from the launcher's sessions before
    that evening -- and where the game actually started came. A game is its Steam app where it has one (two
    records of one app are one game), else its record. Today's genre weights are used throughout."""
    weights = fit_module.weights_of(idf_rows)
    genres: dict[int, list] = {}
    for row in genre_rows:
        genres.setdefault(row["appid"], []).append(row["genre_id"])
    vectors = {appid: fit_module.vector(ids, weights) for appid, ids in genres.items()}
    units: dict[tuple, dict] = {}
    for g in games:
        unit = ("app", g["steam_appid"]) if g["steam_appid"] else ("game", g["game_id"])
        u = units.setdefault(unit, {"name": g["name"], "appid": g["steam_appid"], "seen": None, "first": None,
                                    "steam": False})
        if g["first_seen_local"] and (u["seen"] is None or g["first_seen_local"] < u["seen"]):
            u["seen"] = g["first_seen_local"]
        if g["first_played"] and (u["first"] is None or g["first_played"] < u["first"]):
            u.update(first=g["first_played"], name=g["name"])
        u["steam"] = u["steam"] or bool(g["steam_counted"])
    timed = sorted((s["started_local"], s["steam_appid"], s["minutes"]) for s in sessions
                   if s["started_local"] and s["steam_appid"] in vectors and vectors[s["steam_appid"]])
    left = {"no day it was first seen": 0, "played before it was first seen": 0, "Steam counts its hours": 0}
    cases = []
    for unit, u in sorted(units.items(), key=lambda kv: (kv[1]["first"] or "", kv[1]["name"].casefold())):
        if u["first"] is None:
            continue
        if u["seen"] is None:
            left["no day it was first seen"] += 1
            continue
        if u["first"] <= u["seen"]:
            left["played before it was first seen"] += 1
            continue
        if u["steam"]:
            left["Steam counts its hours"] += 1  # its hours have no dates: its first play may be earlier
            continue
        day = u["first"][:10]
        eve = f"{day}T00:00:00"
        if u["seen"] >= eve:
            cases.append(Case(u["name"], day, note=SAME_DAY))
            continue
        if not vectors.get(u["appid"]):
            cases.append(Case(u["name"], day, note=NO_GENRES))
            continue
        minutes: dict[int, float] = {}
        for when, appid, length in timed:
            if when >= eve:
                break
            minutes[appid] = minutes.get(appid, 0.0) + length
        played = fit_module.taste({a: (m, frozenset(genres[a])) for a, m in minutes.items()}, weights)
        if not played:
            cases.append(Case(u["name"], day, note=NO_PAST))
            continue
        pool = [v for v, w in units.items() if w["appid"] and vectors.get(w["appid"]) and not w["steam"]
                and w["seen"] is not None and w["seen"] < eve and (w["first"] is None or w["first"] >= eve)]
        scores = {v: fit_module.share_of(vectors[units[v]["appid"]], played) for v in pool}
        order = sorted(pool, key=lambda v: (-scores[v], units[v]["name"].casefold()))
        cases.append(Case(u["name"], day, order.index(unit) + 1, len(order),
                          fit_module.like_words(scores[unit], "what you had played")))
    return Looking(cases=tuple(cases), left_out=tuple((why, n) for why, n in left.items() if n))


def facts_for(built: Page, key: str) -> tuple[str, str]:
    """The game page's two lines (Phase 98): its typical session as a pill ("Usually 25 min a session"), and,
    for a waiting game, the Details card's fact -- "72% like what you play · Action, RPG", the very words the
    For you page shows for it."""
    usual = built.typical.get(built.keys.get(key, ""))
    pill = usual.pill if usual is not None and usual.judged else ""
    waiting = built.suggestion(key)
    return pill, waiting.reason if waiting is not None else ""
