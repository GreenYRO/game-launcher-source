"""A new version of a game you had: finding its earlier install, and carrying its past over.

Every record in overrides.json is keyed by where the game is installed -- the identity key
since Phase 1. So a new build that lands in a new folder (a packaged build's next version, or a GOG
install replaced by a folder copy, which is what The Witcher 3 was) is a new key with no
past: no play time, no sessions, no note, no save copies offered back. The old record is
still there, attached to a folder that is gone.

This module finds those records -- earlier installs -- says which look like the game in
front of you, and moves what you built up onto the new key once you say they are the same
game. Only then: a wrong match would mix two games' histories, and a question is one
click. No Qt, and no I/O but the overrides store and a glance at the save copies.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime

from shared import humanize
from shared import naming
from shared import rules
from logic import save_backup
from logic import saves
from logic import sessions

log = logging.getLogger(__name__)

# What a record must hold to be worth offering: something the user did or chose, not only
# the date the launcher first saw it.
_HISTORY = ("playtime_seconds", rules.SESSIONS_KEY, "favorite", rules.STATUS_KEY,
            rules.NOTES_KEY, "cover", "banner", "name", rules.SAVE_DIRS_KEY)

SAME_NAME = "the same name"
SAME_SAVES = "the same save folder"

# How each carried field is named in the message that says what came across.
_LABELS = {"name": "name", "cover": "cover", "banner": "banner", "appid": "Steam match",
           "args": "launch arguments", "is_tool": "tool mark", rules.STATUS_KEY: "mark",
           rules.NOTES_KEY: "note"}


@dataclass
class EarlierInstall:
    key: str
    name: str
    record: dict
    copies: int = 0  # copies of its saves
    why: str = ""  # SAME_NAME, SAME_SAVES -- or "" when it is only listed

    @property
    def playtime_seconds(self) -> int:
        return int(self.record.get("playtime_seconds") or 0)

    @property
    def session_count(self) -> int:
        return len(sessions.load(self.record))

    @property
    def last_played(self) -> datetime | None:
        return _when(self.record.get("last_played"))


@dataclass
class Carried:
    """What moved, for the message that says so."""
    name: str = ""
    seconds: int = 0
    sessions: int = 0
    copies: int = 0
    fields: list[str] = field(default_factory=list)  # note, mark, cover... carried as well


def _when(value) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        log.warning("unreadable time %r in an earlier install's record", value)
        return None


def _norm(path: str) -> str:
    return os.path.normcase(os.path.normpath(path)) if path else ""


def name_of(key: str, record: dict, made_as: str = "") -> str:
    """What an earlier install was called: as last seen, as its save copies say, or its folder."""
    known = record.get(rules.KNOWN_AS_KEY)
    if isinstance(known, str) and known.strip():
        return known.strip()
    if made_as:
        return made_as
    if os.path.isabs(key):
        return naming.clean_folder_name(os.path.basename(key.rstrip("\\/")))
    return ""  # a "steam:730"-style key from before names were kept: nothing to show


def earlier_installs(overrides, installed) -> list[EarlierInstall]:
    """Every record whose game is no longer installed, has a past, and was not carried yet."""
    here = {_norm(key) for key in installed}
    waiting = [(key, record) for key, record in overrides.uncarried() if _norm(key) not in here]
    copies = save_backup.copies_by_key([key for key, _record in waiting])
    found = []
    for key, record in waiting:
        count, made_as = copies.get(key, (0, ""))
        if not count and not any(record.get(name) for name in _HISTORY):
            continue
        name = name_of(key, record, made_as)
        if name:
            found.append(EarlierInstall(key, name, record, count))
    return found


def why_same(view, record: dict, earlier: EarlierInstall) -> str:
    """Why this earlier install looks like the game in front of you -- or "" if it does not."""
    names = {view.display_name, view.entry.display_name}
    if any(naming.same_title(name, earlier.name) for name in names if name):
        return SAME_NAME
    mine = {_norm(p) for p in record.get(rules.SAVE_DIRS_KEY) or []}
    theirs = {_norm(p) for p in earlier.record.get(rules.SAVE_DIRS_KEY) or []}
    if mine & theirs:
        return SAME_SAVES
    return ""


def _recency(earlier: EarlierInstall) -> tuple:
    stamp = earlier.last_played
    return (earlier.playtime_seconds, stamp.timestamp() if stamp else 0.0, earlier.copies)


def offers(view, overrides, installed) -> list[EarlierInstall]:
    """Earlier installs that look like this game, most played first -- for its page to ask about.

    Never one the user already said is a different game.
    """
    record = overrides.get(view.key)
    refused = {_norm(key) for key in record.get(rules.NOT_SAME_KEY) or []}
    found = []
    for earlier in earlier_installs(overrides, installed):
        if _norm(earlier.key) in refused:
            continue
        earlier.why = why_same(view, record, earlier)
        if earlier.why:
            found.append(earlier)
    found.sort(key=_recency, reverse=True)
    return found


def everything(view, overrides, installed) -> list[EarlierInstall]:
    """Every earlier install, for picking by hand: the likely ones first, then the rest."""
    record = overrides.get(view.key)
    found = earlier_installs(overrides, installed)
    for earlier in found:
        earlier.why = why_same(view, record, earlier)
    return sorted(found, key=lambda e: (bool(e.why), _recency(e)), reverse=True)


def summary(earlier: EarlierInstall) -> str:
    """What an earlier install holds, in words: "5h 10m played, 7 sessions, last played ..."."""
    parts = []
    if earlier.playtime_seconds > 0:
        parts.append(f"{humanize.playtime(earlier.playtime_seconds)} played")
    count = earlier.session_count
    if count:
        parts.append(f"{count} session{'s' if count != 1 else ''}")
    if earlier.last_played is not None:
        parts.append(f"last played {humanize.when(earlier.last_played)}")
    if earlier.copies:
        parts.append(f"{earlier.copies} cop{'y' if earlier.copies == 1 else 'ies'} of its saves")
    status = earlier.record.get(rules.STATUS_KEY)
    if status in rules.STATUSES:
        parts.append(f"marked {status}")
    if earlier.record.get(rules.NOTES_KEY):
        parts.append("a note")
    if earlier.record.get("favorite"):
        parts.append("a star")
    return ", ".join(parts) or "a cover or a name you chose"


def _remap(folder: str, old_home: str, new_home: str) -> str:
    """A save folder that lived inside the old game folder follows the game to the new one."""
    if old_home and new_home and os.path.isabs(old_home):
        inside = _norm(folder)
        home = _norm(old_home)
        if inside.startswith(home + os.sep):
            return os.path.join(new_home, os.path.normpath(folder)[len(home) + 1:])
    return folder


def carry_over(overrides, old_key: str, new_key: str, *, new_install_dir: str = "",
               old_name: str = "", now: datetime | None = None) -> Carried:
    """Move an earlier install's history onto this game, and leave a note where it went.

    Field by field: play time is added; sessions are merged by start time, the way an
    import merges them (Phase 20); the most recent "last played" wins; a star on either
    stays; the name, cover, banner, appid, arguments, tool mark, Playing/Finished/Dropped
    are taken only where this game has none of its own; two notes are kept, one under the
    other; save folders are joined, a folder inside the old game folder following the game
    to the new one. Nothing about the old *folder* comes across -- a hand-picked exe, the
    hidden flag -- because it described a place that is gone.

    The old record keeps its first-seen date and name, and says where its history went, so
    it is never offered again. The caller takes a snapshot first, which is the undo.

    The new record is worked out on a copy and both are written by the store in one go
    (Phase 64): a carry that stops half way changes nothing, rather than leaving half a
    history in memory for the next write to keep.
    """
    old = overrides.get(old_key)
    if not old:
        raise LookupError(f"nothing recorded for {old_key}")
    if old.get(rules.CARRIED_TO_KEY):
        raise ValueError(f"{old_key} was already carried over to {old[rules.CARRIED_TO_KEY]}")
    if _norm(old_key) == _norm(new_key):
        raise ValueError("an install cannot carry on from itself")
    new = dict(overrides.get(new_key))
    moment = (now or datetime.now()).astimezone()
    copies = save_backup.copies_by_key([old_key]).get(old_key, (0, ""))
    carried = Carried(name=old_name or name_of(old_key, old, copies[1]), copies=copies[0])

    seconds = int(old.get("playtime_seconds") or 0)
    if seconds > 0:
        new["playtime_seconds"] = int(new.get("playtime_seconds") or 0) + seconds
        carried.seconds = seconds

    theirs = sessions.load(old)
    if theirs:
        merged = sessions.prune(sessions.merge(sessions.load(new), theirs), moment)
        new[rules.SESSIONS_KEY] = sessions.dump(merged)
        carried.sessions = len(theirs)

    played = [t for t in (_when(new.get("last_played")), _when(old.get("last_played"))) if t]
    if played:
        new["last_played"] = max(played).isoformat(timespec="seconds")

    if old.get("favorite") and not new.get("favorite"):
        new["favorite"] = True
        carried.fields.append("star")

    for name in rules.CARRY_IF_MISSING:
        value = old.get(name)
        if value in (None, "", [], {}):
            continue
        if name in ("cover", "banner") and not (isinstance(value, str) and os.path.isfile(value)):
            continue
        mine = new.get(name)
        if name == rules.NOTES_KEY and isinstance(mine, str) and mine.strip() \
                and mine.strip() != str(value).strip():
            # Two notes: neither is thrown away. This game's first, the earlier one under it.
            new[name] = f"{mine.rstrip()}\n\n{str(value).strip()}"[: rules.NOTES_MAX_CHARS]
            carried.fields.append("note")
            continue
        if mine not in (None, ""):
            continue
        new[name] = value
        carried.fields.append(_LABELS.get(name, name))

    known = list(new.get(rules.SAVE_DIRS_KEY) or [])
    seen = {_norm(p) for p in known}
    for folder in old.get(rules.SAVE_DIRS_KEY) or []:
        moved = _remap(folder, old_key, new_install_dir)
        if _norm(moved) not in seen:
            known.append(moved)
            seen.add(_norm(moved))
    known = saves.only_save_folders(known)
    if known:
        new[rules.SAVE_DIRS_KEY] = known

    earlier = list(new.get(rules.EARLIER_KEYS_KEY) or [])
    for key in [old_key, *(old.get(rules.EARLIER_KEYS_KEY) or [])]:
        if key not in earlier and _norm(key) != _norm(new_key):
            earlier.append(key)
    new[rules.EARLIER_KEYS_KEY] = earlier
    refused = [k for k in new.get(rules.NOT_SAME_KEY) or [] if _norm(k) != _norm(old_key)]
    if refused:
        new[rules.NOT_SAME_KEY] = refused
    else:
        new.pop(rules.NOT_SAME_KEY, None)

    left = {name: old[name] for name in ("first_seen",) if name in old}
    left[rules.KNOWN_AS_KEY] = carried.name
    left[rules.CARRIED_TO_KEY] = new_key
    left[rules.CARRIED_AT_KEY] = moment.isoformat(timespec="seconds")
    overrides.carry(old_key, new_key, old_record=left, new_record=new)
    log.info("carried %s over to %s: %d s, %d sessions, %d save copies, and %s",
             old_key, new_key, carried.seconds, carried.sessions, carried.copies,
             ", ".join(carried.fields) or "nothing else")
    return carried


def not_the_same(overrides, key: str, earlier_key: str) -> None:
    """Remember that this earlier install is a different game, so it is not offered again."""
    record = overrides.get(key)
    refused = list(record.get(rules.NOT_SAME_KEY) or [])
    if _norm(earlier_key) not in {_norm(k) for k in refused}:
        refused.append(earlier_key)
        overrides.update(key, **{rules.NOT_SAME_KEY: refused})
        log.info("%s is not the same game as %s; not offered again", key, earlier_key)
