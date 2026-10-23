"""An anonymous copy of a library, for a comparison of libraries in a bachelor thesis (Phase 80).

What the friends were told (docs/CITESTE-MA.md): "which games you have and how much you played
them, without folder paths and without account names -- your choice". So the file holds:

  games       each game shown in the library (hidden ones and tools left out): its store, whether
              installed, Steam's number, type and genres when it has one, the month it was first
              seen and last played, the marks (playing / finished / dropped, the star), the minutes
              the launcher timed, the sessions' count and minutes, Steam's own minutes on the
              accounts marked as theirs -- and its name only when a store gave it: Steam's name
              for a game matched to Steam, the store's title for a GOG, Epic or Xbox one. A game
              found only in a folder and matched to nothing has no name in the file, because its
              name is its folder's, and a folder's name can say more than anyone meant to share
  sessions    totals only -- by month, by hour of the day, by day of the week -- never a time;
              since format version 2 (Phase 93) also how they were measured: 'launched' (the launcher
              started the game and timed it) and 'observed' (it saw the game running, however it was
              started -- each end within a few seconds), as totals, and per game the observed ones'
              count and minutes. An export of version 1 has none of it: every session in it was launched;
              since format version 3 (Phase 102) per game its ratings -- the stars and the session's day,
              nothing more -- and the day its mark (playing / finished / dropped) was set, when known. An
              export of version 2 or older has no ratings: none were asked for, which is not zero
  steam       Steam's own time per app on the accounts marked as theirs, and those accounts as
              "A", "B", ...: their minutes, apps with time and the month last read; never their
              numbers or names (pseudonymisation; the accounts not marked theirs are not in it)
  paid        only when asked for: what was paid, the currency, the store from the dialog's own
              list (else "other"), the month -- never the note

and never a path, an exe, a note, a chosen picture, a setting, the SteamGridDB key, the log, an
account's number or name, or a time of day of any session. The friend's code is random, kept in
config.json so two of their exports are known to be one person's.

Before a byte is written, the whole export is searched for every path, account number and note
the library holds (`LibraryStore.personal_values`): one found, and nothing is written. Defence in
depth: the shaping below asks for none of them in the first place.

No Qt here; the Settings row asks and calls build() and write().
"""

from __future__ import annotations

import json
import logging
import os
import re
import secrets
import tempfile
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

from shared import humanize
from shared import rules
from shared import version

log = logging.getLogger(__name__)

_PARTICIPANT = re.compile(r"p-[0-9a-f]{10}")
_MONTH = re.compile(r"\d{4}-\d{2}")

SOURCE_WORDS = {"steam": "from Steam", "gog": "from GOG", "epic": "from Epic", "xbox": "from Xbox",
                "ubisoft": "from Ubisoft", "folders": "found in folders", "unknown": "from somewhere not recorded"}

ABOUT = [
    "Un export anonim al unei biblioteci Game Launcher, pentru o comparație într-o lucrare de licență.",
    "Ce jocuri sunt în bibliotecă și cât s-au jucat -- fără căi de foldere, fără nume sau numere de conturi, "
    "fără notițe și fără orele sesiunilor.",
    "An anonymous export of a Game Launcher library, for a comparison in a bachelor thesis: which games, "
    "and how much they were played -- no folder paths, no account names or numbers, no notes, no times of day.",
]
NEVER = ("folder paths and exe names", "the names of games found only in folders",
         "Steam account names and numbers", "notes", "chosen covers", "settings", "the SteamGridDB key",
         "the log", "the times of day of sessions")
WHAT_ORIGIN_MEANS = ("Sesiunile 'launched' au fost cronometrate de launcher, care a pornit jocul; cele 'observed' au "
                     "fost văzute rulând în lista proceselor, oricine ar fi pornit jocul -- fiecare capăt cu câteva "
                     "secunde de nesiguranță. / 'launched': timed by the launcher, which started the game; "
                     "'observed': seen running in the process list, however it was started -- each end within a "
                     "few seconds.")


class Refused(Exception):
    """Something personal was found in an export; nothing was written."""


def participant(config: dict) -> tuple[str, bool]:
    """This PC's code in the comparison, and whether it is new (to be written into config.json)."""
    kept = str(config.get(rules.ANALYSIS_ID_SETTING) or "")
    if _PARTICIPANT.fullmatch(kept):
        return kept, False
    return "p-" + secrets.token_hex(5), True


def _month(text) -> str | None:
    text = str(text or "")
    return text[:7] if _MONTH.match(text) else None


def _is_tool(marked, appid_source, app_type) -> bool:
    """GameView.is_non_game's rule (catalog_io), on the database's columns: the user's mark wins; a
    Steam number found by searching a name never makes a game a tool; else Steam's type decides,
    for a number a store's own files gave."""
    if marked is not None:
        return bool(marked)
    if appid_source != "manifest":
        return False
    return bool(app_type) and app_type not in rules.STEAM_GAME_TYPES


def build(store, code: str, *, include_paid: bool = False, today: date | None = None) -> dict:
    """The export, as a dict ready for JSON. Reads the library through the store; writes nothing."""
    source = store.analysis_source()
    genres: dict[int, list[str]] = defaultdict(list)
    for appid, name in source["genres"]:
        genres[appid].append(name)
    steam = {row[0]: row for row in source["steam"]}
    sessions: dict[int, list[tuple[str, int, str]]] = defaultdict(list)
    for game_id, started, minutes, *how in source["sessions"]:
        sessions[game_id].append((started, minutes, how[0] if how else rules.SESSION_LAUNCHED))
    paid: dict[int, list[dict]] = defaultdict(list)
    rated: dict[int, list[dict]] = defaultdict(list)
    for game_id, started, stars in source.get("ratings", []):
        rated[game_id].append({"stars": stars, "day": str(started)[:10]})  # the session's local day, never its hour
    marked_on = {game_id: str(moment)[:10] for game_id, moment in source.get("marked", []) if moment}
    for game_id, cents, currency, shop, bought_on in source["purchases"]:
        paid[game_id].append({"amount_cents": cents, "currency": currency,
                              "store": shop if shop in rules.PURCHASE_STORES else "other",
                              "month": _month(bought_on)})

    games, kept_sessions = [], []
    left_out = Counter()
    for (game_id, origin, installed, appid, appid_source, steam_name, app_type, store_name, marked, hidden,
         favorite, status, first_seen, last_played, playtime) in source["games"]:
        if hidden:
            left_out["hidden"] += 1
            continue
        if _is_tool(marked, appid_source, app_type):
            left_out["tools"] += 1
            continue
        played = sessions.get(game_id, [])
        on_steam = steam.get(appid) if appid is not None else None
        if not (installed or playtime or played or status or favorite or on_steam or paid.get(game_id)):
            left_out["gone, nothing kept"] += 1  # an old install with nothing of the user's on it
            continue
        item = {
            "source": origin or "unknown",
            "installed": bool(installed),
            "name": steam_name if appid is not None and steam_name else store_name,
            "steam_appid": appid,
            "steam_type": app_type,
            "genres": genres.get(appid, []) if appid is not None else [],
            "first_seen": _month(first_seen),
            "last_played": _month(last_played),
            "status": status,
            "favorite": bool(favorite),
            "launcher_minutes": playtime // 60 if playtime is not None else None,
            "sessions": len(played),
            "session_minutes": sum(m for _s, m, _o in played),
            "observed_sessions": sum(1 for _s, _m, o in played if o == rules.SESSION_OBSERVED),
            "observed_minutes": sum(m for _s, m, o in played if o == rules.SESSION_OBSERVED),
            "steam_minutes": on_steam[1] if on_steam else None,
            "steam_accounts": on_steam[2] if on_steam else 0,
            "ratings": rated.get(game_id, []),
            "status_since": marked_on.get(game_id) if status else None,
        }
        if include_paid:
            item["paid"] = paid.get(game_id, [])
        games.append(item)
        kept_sessions += played

    by_month: Counter = Counter()
    by_hour = {hour: 0 for hour in range(24)}
    by_weekday = {day: 0 for day in rules.ANALYSIS_WEEKDAYS}
    by_origin = {how: {"count": 0, "minutes": 0} for how in (rules.SESSION_LAUNCHED, rules.SESSION_OBSERVED)}
    for started, minutes, how in kept_sessions:
        by_origin[how]["count"] += 1
        by_origin[how]["minutes"] += minutes
        moment = datetime.fromisoformat(started)  # the local time it was written with
        by_month[started[:7]] += minutes
        by_hour[moment.hour] += minutes
        by_weekday[rules.ANALYSIS_WEEKDAYS[moment.weekday()]] += minutes

    accounts = sorted(source["accounts"], key=lambda row: (-(row[1] or 0), row[0]))
    labels = [chr(ord("A") + n) if n < 26 else f"A{n}" for n in range(len(accounts))]
    data = {
        "format": rules.ANALYSIS_FORMAT,
        "version": rules.ANALYSIS_FORMAT_VERSION,
        "app_version": version.APP_VERSION,
        "made_on": (today or date.today()).isoformat(),
        "participant": code,
        "about": ABOUT,
        "never_in_it": list(NEVER),
        "paid_included": include_paid,
        "left_out": dict(sorted(left_out.items())),
        "games": games,
        "sessions": {
            "count": len(kept_sessions),
            "minutes": sum(m for _s, m, _o in kept_sessions),
            "by_origin": by_origin,
            "origin_means": WHAT_ORIGIN_MEANS,
            "first_month": min(by_month) if by_month else None,
            "last_month": max(by_month) if by_month else None,
            "by_month": dict(sorted(by_month.items())),
            "by_hour": {str(hour): minutes for hour, minutes in by_hour.items()},
            "by_weekday": by_weekday,
        },
        "steam": {
            "accounts": [{"account": label, "minutes": minutes or 0, "apps_with_time": with_time or 0,
                          "last_read": _month(read)}
                         for label, (_number, minutes, with_time, read) in zip(labels, accounts)],
            "history": [{"steam_appid": appid, "name": name, "steam_type": kind, "genres": genres.get(appid, []),
                         "minutes": minutes, "accounts": held, "last_played": _month(last)}
                        for appid, minutes, held, last, name, kind in
                        sorted(source["steam"], key=lambda row: (-(row[1] or 0), row[0]))],
        },
    }
    return data


def _count(number: int, word: str) -> str:
    return f"{number} {word}" + ("" if number == 1 else "s")


def summary(data: dict, *, paid_line: bool = True) -> list[str]:
    """What the file holds, in a few plain lines -- what the dialog shows before anything is saved.
    `paid_line` False leaves out the line about purchases, which the dialog asks with a switch."""
    games = data["games"]
    installed = [game for game in games if game["installed"]]
    by_source = Counter(game["source"] for game in installed)
    parts = ", ".join(f"{count} {SOURCE_WORDS.get(origin, origin)}" for origin, count in by_source.most_common())
    gone = len(games) - len(installed)
    line = f"{_count(len(games), 'game')}: {len(installed)} installed" + (f" ({parts})" if parts else "")
    if gone:
        line += f", and {gone} you played or marked that {'is' if gone == 1 else 'are'} no longer installed"
    line += "."
    nameless = sum(1 for game in games if game["name"] is None)
    if nameless:
        line += (f" {nameless} of them {'has' if nameless == 1 else 'have'} no Steam match, so the file does not "
                 f"name {'it' if nameless == 1 else 'them'}.")
    lines = [line]
    timed = data["sessions"]
    played = sum(game["launcher_minutes"] or 0 for game in games)
    lines.append(f"{humanize.playtime(played * 60)} played through the launcher, in {_count(timed['count'], 'session')}"
                 " -- as totals by month, hour of the day and day of the week, never the times themselves.")
    accounts = data["steam"]["accounts"]
    if accounts:
        letters = ", ".join(account["account"] for account in accounts)
        lines.append(f"Steam's own time for {_count(len(data['steam']['history']), 'Steam app')}, on the "
                     f"{_count(len(accounts), 'Steam account')} you marked as yours -- called {letters} in the file, "
                     "without their names or numbers.")
    else:
        lines.append("No Steam account is marked as yours (Settings, Steam accounts), so Steam's own time is "
                     "not in it.")
    lines.append("For each game: its store, Steam's number, type and genres for it, the months it was first "
                 "seen and last played, and your marks -- playing, finished, dropped, the star.")
    rated = sum(len(game.get("ratings") or []) for game in games)
    if rated:
        lines.append(f"{_count(rated, 'session rating')}: the stars and the day of the session, never its time.")
    left = data["left_out"]
    if left.get("hidden") or left.get("tools"):
        lines.append(f"Left out: {_count(left.get('hidden', 0), 'hidden game')} and "
                     f"{_count(left.get('tools', 0), 'tool')}.")
    if paid_line:
        lines.append("What you paid: " + ("included -- the amounts, the store and the month, not your notes."
                                          if data["paid_included"] else "not included."))
    return lines


def _values(node):
    """Every string and number in the export, keys included."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield key
            yield from _values(value)
    elif isinstance(node, list):
        for value in node:
            yield from _values(value)
    elif isinstance(node, (str, int)) and not isinstance(node, bool):
        yield node


def leaks(data: dict, personal: dict[str, set[str]]) -> list[str]:
    """What kinds of personal values are in the export -- the kinds only, never the values."""
    found = set()
    paths = [p.lower() for p in personal.get("paths", ()) if len(p) >= 4]
    texts = [t for t in personal.get("texts", ()) if len(t.strip()) >= 12]  # a short one could be any title's
    ids = {str(i) for i in personal.get("ids", ())}
    for value in _values(data):
        if isinstance(value, int):
            if str(value) in ids:
                found.add("a Steam account's number")
            continue
        lowered = value.lower()
        if ":\\" in value or value.startswith("\\\\") or any(p in lowered for p in paths):
            found.add("a folder path")
        if any(t in value for t in texts):
            found.add("a note or launch argument")
        if ids and any(re.search(rf"(?<!\d){re.escape(i)}(?!\d)", value) for i in ids):
            found.add("a Steam account's number")
    return sorted(found)


def write(target: Path, data: dict, personal: dict[str, set[str]]) -> Path:
    """The export to `target`, whole or not at all. Raises Refused if something personal is in it
    (nothing written), OSError if it cannot be written."""
    found = leaks(data, personal)
    if found:
        log.error("analysis export refused: %s found in it; nothing written", ", ".join(found))
        raise Refused(", ".join(found))
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(prefix=".analysis-", suffix=".json", dir=target.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            json.dump(data, out, indent=1, ensure_ascii=False)
            out.write("\n")
        os.replace(temp, target)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise
    log.info("analysis export: %s written -- %d game(s), %d session(s), %d Steam app(s), %d account(s), paid %s",
             target, len(data["games"]), data["sessions"]["count"], len(data["steam"]["history"]),
             len(data["steam"]["accounts"]), "included" if data["paid_included"] else "not included")
    return target


def default_name(today: date | None = None) -> str:
    return f"{rules.ANALYSIS_FILE_PREFIX}-{(today or date.today()).isoformat()}.json"
