"""Several friends' anonymous exports, read and set side by side for the thesis (Phase 81).

Each export is the file logic/analysis.py writes (format "game-launcher-analysis", versions 1 to 3).
This reads a folder of them, refuses what is not one -- with the reason -- keeps the newest of
two from one participant, labels the participants P1, P2, ... in the order their files were made
(so adding a friend never renumbers the others), and works out, for each and between them:

  overview     games installed and played or marked, where they came from, the launcher's hours
               and sessions, Steam's hours on the accounts marked theirs, nameless games, marks
  when         the launcher's sessions by hour of the day and day of the week, as shares
  genres       Steam's time by Steam's genres, as shares (a game's minutes split equally among
               its genres, so each participant's shares add up to 100)
  similarity   how alike two participants' played games are: Jaccard, |A and B| / |A or B|, on the
               Steam numbers of the games each has played (launcher or Steam time above zero)
  common       the games more than one participant has played, how many and how long in all

Nothing is fetched and nothing is written here; logic/comparison_report.py writes the report.
Two measures are never added together: the launcher's time is since it was installed, Steam's
is lifetime -- the report shows them apart.
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path

from shared import rules

log = logging.getLogger(__name__)

_CODE = re.compile(r"p-[0-9a-f]{10}")
NO_GENRE = "(fără gen)"
NO_NAME = "(joc fără nume)"
SOURCE_ORDER = ("steam", "folders", "gog", "epic", "xbox", "ubisoft", "unknown")


@dataclass
class Participant:
    label: str
    code: str
    file: str
    data: dict
    games: int = 0
    installed: int = 0
    by_source: dict = field(default_factory=dict)
    launcher_minutes: int = 0
    sessions: int = 0
    session_minutes: int = 0
    # How they were measured (export format 2, Phase 93): an export of version 1 has no such split, and
    # every session in it was launched -- so these read 0 for it.
    observed_sessions: int = 0
    observed_minutes: int = 0
    # A session's stars (format 3, Phase 102): None for an export of version 2 or older, which was never
    # asked -- said as such, never read as zero ratings.
    ratings: int | None = None
    rated_games: int | None = None
    mean_stars: float | None = None
    steam_minutes: int = 0
    set_aside_minutes: int = 0  # Spacewar and Source SDK Base 2007's, left out of every measure (Phase 83)
    steam_apps_played: int = 0
    accounts: int = 0
    nameless: int = 0
    status: dict = field(default_factory=dict)
    favorites: int = 0
    paid_included: bool = False
    paid: dict = field(default_factory=dict)  # currency -> cents
    purchases: int = 0
    played: set = field(default_factory=set)  # Steam numbers of games played
    hour_share: dict = field(default_factory=dict)  # 0..23 -> percent
    weekday_share: dict = field(default_factory=dict)
    genre_share: dict = field(default_factory=dict)  # genre -> percent of Steam time
    top_steam: list = field(default_factory=list)  # (name, minutes)
    top_launcher: list = field(default_factory=list)
    first_month: str | None = None
    last_month: str | None = None


@dataclass
class Loaded:
    participants: list[Participant]
    skipped: list[tuple[str, str]]  # (file name, why)
    replaced: list[tuple[str, str]]  # (older file, by the newer one)


def _problem(data) -> str | None:
    """Why this is not an export this tool reads -- None when it is."""
    if not isinstance(data, dict):
        return "not an export (not a JSON object)"
    if data.get("format") != rules.ANALYSIS_FORMAT:
        return "not an anonymous export of Game Launcher"
    version = data.get("version")
    if not isinstance(version, int) or version < 1:
        return "no format version"
    if version > rules.ANALYSIS_FORMAT_VERSION:
        return f"made in format version {version}, newer than this tool reads ({rules.ANALYSIS_FORMAT_VERSION})"
    if not _CODE.fullmatch(str(data.get("participant") or "")):
        return "no participant code"
    if not isinstance(data.get("games"), list) or not isinstance(data.get("sessions"), dict) \
            or not isinstance(data.get("steam"), dict):
        return "incomplete: games, sessions or Steam missing"
    return None


def load(sources: list[Path]) -> Loaded:
    """Every export among these files and folders (a folder: its *.json), checked; the newest of a
    participant's kept; P1, P2, ... by the day each participant's FIRST file was made, then by code --
    so a friend who sends a newer export keeps the label the thesis already uses."""
    files: list[Path] = []
    for source in sources:
        source = Path(source)
        files += sorted(source.glob("*.json")) if source.is_dir() else [source]
    found: dict[str, tuple[Path, dict]] = {}
    first_made: dict[str, str] = {}
    skipped, replaced = [], []
    for path in files:
        try:
            if path.stat().st_size > rules.COMPARISON_MAX_BYTES:
                skipped.append((path.name, "too big to be an export"))
                continue
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            skipped.append((path.name, f"could not be read ({type(exc).__name__})"))
            continue
        problem = _problem(data)
        if problem:
            skipped.append((path.name, problem))
            continue
        code = data["participant"]
        made = str(data.get("made_on") or "")
        first_made[code] = min(first_made.get(code, made), made)
        if code in found:
            older, newer = sorted([found[code], (path, data)],
                                  key=lambda item: (str(item[1].get("made_on") or ""), item[1]["sessions"].get("count", 0)))
            replaced.append((older[0].name, newer[0].name))
            found[code] = newer
        else:
            found[code] = (path, data)
    order = sorted(found.values(), key=lambda item: (first_made[item[1]["participant"]], item[1]["participant"]))
    participants = [_measure(f"P{n}", path.name, data) for n, (path, data) in enumerate(order, 1)]
    log.info("comparison: %d participant(s) from %d file(s); %d skipped, %d replaced by a newer one",
             len(participants), len(files), len(skipped), len(replaced))
    return Loaded(participants, skipped, replaced)


def _shares(counts: dict, keys) -> dict:
    total = sum(counts.get(k, 0) or 0 for k in keys)
    return {k: (100.0 * (counts.get(k, 0) or 0) / total if total else 0.0) for k in keys}


def _counted(appid) -> bool:
    """Not one of the apps whose hours are other games' (rules.STEAM_NOT_GAMES: Spacewar, Source SDK
    Base 2007): set aside here as the reports set them aside (Phase 83), at analysis -- the exports
    themselves keep them."""
    return appid not in rules.STEAM_NOT_GAMES


def _measure(label: str, file: str, data: dict) -> Participant:
    games = [g for g in data["games"] if isinstance(g, dict)]
    every = [h for h in data["steam"].get("history", []) if isinstance(h, dict)]
    history = [h for h in every if _counted(h.get("steam_appid"))]
    sessions = data["sessions"]
    p = Participant(label=label, code=data["participant"], file=file, data=data)
    p.games = len(games)
    installed = [g for g in games if g.get("installed")]
    p.installed = len(installed)
    counted = Counter(g.get("source") or "unknown" for g in installed)
    p.by_source = {s: counted.get(s, 0) for s in SOURCE_ORDER if counted.get(s)}
    p.launcher_minutes = sum(g.get("launcher_minutes") or 0 for g in games)
    p.sessions = int(sessions.get("count") or 0)
    p.session_minutes = int(sessions.get("minutes") or 0)
    observed = (sessions.get("by_origin") or {}).get(rules.SESSION_OBSERVED) or {}
    p.observed_sessions = int(observed.get("count") or 0)
    p.observed_minutes = int(observed.get("minutes") or 0)
    if int(data.get("version") or 0) >= 3:
        stars = [r.get("stars") for g in games for r in (g.get("ratings") or []) if isinstance(r, dict)
                 and isinstance(r.get("stars"), int) and 1 <= r["stars"] <= rules.RATE_STARS]
        p.ratings = len(stars)
        p.rated_games = sum(1 for g in games if any(isinstance(r, dict) for r in (g.get("ratings") or [])))
        p.mean_stars = sum(stars) / len(stars) if stars else None
    p.steam_minutes = sum(h.get("minutes") or 0 for h in history)
    p.set_aside_minutes = sum(h.get("minutes") or 0 for h in every if not _counted(h.get("steam_appid")))
    p.steam_apps_played = sum(1 for h in history if (h.get("minutes") or 0) > 0)
    p.accounts = len(data["steam"].get("accounts", []))
    p.nameless = sum(1 for g in games if g.get("name") is None)
    p.status = dict(Counter(g["status"] for g in games if g.get("status")))
    p.favorites = sum(1 for g in games if g.get("favorite"))
    p.paid_included = bool(data.get("paid_included"))
    if p.paid_included:
        paid: Counter = Counter()
        for game in games:
            for bought in game.get("paid") or []:
                paid[str(bought.get("currency") or "?")] += int(bought.get("amount_cents") or 0)
                p.purchases += 1
        p.paid = dict(paid)
    p.played = ({g["steam_appid"] for g in games if g.get("steam_appid") is not None
                 and ((g.get("launcher_minutes") or 0) > 0 or (g.get("steam_minutes") or 0) > 0)}
                | {h["steam_appid"] for h in history if h.get("steam_appid") is not None and (h.get("minutes") or 0) > 0})
    p.played = {appid for appid in p.played if _counted(appid)}
    hours = {int(h): m for h, m in (sessions.get("by_hour") or {}).items()}
    p.hour_share = _shares(hours, range(24))
    p.weekday_share = _shares(sessions.get("by_weekday") or {}, rules.ANALYSIS_WEEKDAYS)
    genres: Counter = Counter()
    for h in history:
        minutes = h.get("minutes") or 0
        if minutes <= 0:
            continue
        names = h.get("genres") or [NO_GENRE]
        for genre in names:
            genres[genre] += minutes / len(names)
    total = sum(genres.values())
    p.genre_share = {g: 100.0 * m / total for g, m in genres.most_common()} if total else {}
    p.top_steam = [(h.get("name") or f"app {h.get('steam_appid')}", h.get("minutes") or 0)
                   for h in sorted(history, key=lambda h: -(h.get("minutes") or 0))[:rules.COMPARISON_TOP_GAMES]
                   if (h.get("minutes") or 0) > 0]
    p.top_launcher = [(g.get("name") or NO_NAME, g.get("launcher_minutes") or 0)
                      for g in sorted(games, key=lambda g: -(g.get("launcher_minutes") or 0))[:rules.COMPARISON_TOP_GAMES]
                      if (g.get("launcher_minutes") or 0) > 0]
    p.first_month, p.last_month = sessions.get("first_month"), sessions.get("last_month")
    return p


def jaccard(a: set, b: set) -> float | None:
    """|A and B| / |A or B| -- None when neither has played anything."""
    union = a | b
    return len(a & b) / len(union) if union else None


def similarity(participants: list[Participant]) -> dict[tuple[str, str], float | None]:
    """Every pair's Jaccard on played games, both ways round; a participant with itself is 1."""
    found = {}
    for p in participants:
        found[(p.label, p.label)] = 1.0 if p.played else None
    for a, b in combinations(participants, 2):
        value = jaccard(a.played, b.played)
        found[(a.label, b.label)] = found[(b.label, a.label)] = value
    return found


def common_games(participants: list[Participant]) -> list[dict]:
    """The games more than one participant played: Steam number, name, who, minutes in all."""
    who: dict[int, set] = defaultdict(set)
    names: dict[int, str] = {}
    minutes: Counter = Counter()
    for p in participants:
        for g in p.data["games"]:
            appid = g.get("steam_appid")
            if appid is None or not _counted(appid):
                continue
            if g.get("name"):
                names.setdefault(appid, g["name"])
            minutes[appid] += g.get("launcher_minutes") or 0
        for h in p.data["steam"].get("history", []):
            appid = h.get("steam_appid")
            if appid is None or not _counted(appid):
                continue
            if h.get("name"):
                names.setdefault(appid, h["name"])
            minutes[appid] += h.get("minutes") or 0
        for appid in p.played:
            who[appid].add(p.label)
    rows = [{"steam_appid": appid, "name": names.get(appid) or f"app {appid}",
             "participants": sorted(labels, key=lambda label: int(label[1:])), "minutes": minutes[appid]}
            for appid, labels in who.items() if len(labels) > 1]
    rows.sort(key=lambda row: (-len(row["participants"]), -row["minutes"], row["name"]))
    return rows


def genres_compared(participants: list[Participant]) -> list[str]:
    """The genres shown side by side: the ones with the most share across everyone, NO_GENRE last."""
    total: Counter = Counter()
    for p in participants:
        for genre, share in p.genre_share.items():
            total[genre] += share
    ordered = [g for g, _ in total.most_common() if g != NO_GENRE]
    return ordered[:rules.COMPARISON_TOP_GENRES]
