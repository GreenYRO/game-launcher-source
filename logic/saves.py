"""Where a game keeps its saves -- found by what it wrote while you played it.

Nothing here guesses a path. The launcher already records when each game ran (Phase 20),
so a save folder is a folder that was written *during* those sessions and looks like a
save folder. Both halves matter. Read off this machine against its real sessions:

* During play, far more is written than saves: graphics-driver shader caches, browsers,
  chat apps, the Claude app, WeMod. So a folder only counts if its shape says save --
  a path component with "save" in it (but not Unreal's bare "Saved", which also holds
  Config, Logs and Crashes), the Steam cloud layout that Steam emulators copy
  (<appid>\\remote), anything in Windows' own Saved Games, or a file named like a save.
* A save-shaped folder can still belong to something else running alongside. So it is
  taken only if it is inside the game's own folder, names the game, carries its Steam
  appid -- or was mostly written while this game was running (SAVES_OWNED_FRACTION).
  Unreal games often save under an internal project name ("Ride" for RV There Yet,
  "Ravage" for Halloween), which is why the last rule exists.

The known folders are resolved through SHGetKnownFolderPath, never assembled under the
user profile. No Qt here and no writes: this module only reads names and dates.
"""

from __future__ import annotations

import difflib
import logging
import os
import re
import stat as stat_module
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from shared import rules

log = logging.getLogger(__name__)

FILE_ATTRIBUTE_REPARSE_POINT = 0x400
SAVE_EXTENSIONS = (".sav", ".save")
# Words too common in game titles and folder names to say anything on their own -- and
# the Steam emulators' names, which turn up both in packaged builds' folder names
# ("gospodars.tales-goldberg") and in the emulators' own save folders ("Goldberg SteamEmu
# Saves"). Left in, that one word made American Truck Simulator's saves look like
# another game's.
COMMON_WORDS = frozenset({
    "game", "games", "the", "and", "edition", "remastered", "definitive", "deluxe",
    "complete", "ultimate", "save", "saves", "saved", "steam", "data", "user", "local",
    "goldberg", "steamemu", "gse", "rune", "codex", "p2p", "remote",
})


@dataclass
class Found:
    path: str
    reason: str


@dataclass
class Index:
    """Every save-shaped folder seen in one walk, with the write times of its files."""

    folders: dict[str, list[float]] = field(default_factory=dict)
    files_walked: int = 0


def known_folder(name: str) -> str:
    """One known folder's path as Windows reports it (a FOLDERID_ name), or "" -- never assembled by hand.
    Also where the recap's Save image... opens (Phase 96: FOLDERID_Pictures)."""
    from win32com.shell import shell, shellcon

    try:
        path = shell.SHGetKnownFolderPath(getattr(shellcon, name), 0, None)
    except Exception as exc:  # pywintypes.com_error and friends
        log.warning("Windows would not say where %s is: %s", name, exc)
        return ""
    return path if path and os.path.isdir(path) else ""


def known_folders() -> list[tuple[str, str]]:
    """(folder id, path) for each place games save to, as Windows reports them."""
    found = []
    for name in rules.SAVES_KNOWN_FOLDERS:
        path = known_folder(name)
        if path:
            found.append((name, path))
    return found


def session_windows(record: dict) -> list[tuple[float, float]]:
    """(start, end) timestamps of a game's recorded sessions, with the closing slack."""
    windows = []
    for session in record.get(rules.SESSIONS_KEY, []) or []:
        try:
            start = datetime.fromisoformat(session["start"]).astimezone()
            minutes = int(session["minutes"])
        except (KeyError, TypeError, ValueError) as exc:
            log.debug("skipping an unreadable session %r: %s", session, exc)
            continue
        end = start + timedelta(minutes=minutes, seconds=rules.SAVES_SESSION_SLACK_S)
        windows.append((start.timestamp(), end.timestamp()))
    return sorted(windows)


# -- what a save looks like ---------------------------------------------------------------


def _is_save_word(name: str) -> bool:
    folded = name.casefold()
    return folded != "saved" and "save" in folded


def _is_save_file(name: str) -> bool:
    """A .sav/.save file, or one whose name starts with "save" -- not merely containing it.

    "Contains" took Chained Together's controller-settings file for a save.
    """
    stem, ext = os.path.splitext(name.casefold())
    return ext in SAVE_EXTENSIONS or stem.startswith("save")


def could_be_save_folder(path: str) -> bool:
    """False for a folder that holds copies of saves without being where a game keeps them.

    A crash reporter's queue and a program's telemetry (rules.SAVES_NEVER_PARTS and
    _WORDS). Checked on every folder found, on every folder found before -- so a wrong
    one recorded earlier is dropped -- and on every folder a copy would put back.
    """
    for part in re.split(r"[\\/]+", path):
        folded = part.casefold()
        if folded in rules.SAVES_NEVER_PARTS:
            return False
        if any(word in folded for word in rules.SAVES_NEVER_WORDS):
            return False
    return True


def only_save_folders(folders) -> list[str]:
    """The folders that could be saves, in order; the others logged as they are dropped."""
    kept = []
    for folder in folders or []:
        if could_be_save_folder(folder):
            kept.append(folder)
        else:
            log.info("not a save folder, dropped: %s", folder)
    return kept


def save_root(parts: list[str], filename: str, folder_id: str) -> list[str] | None:
    """The save folder a file belongs to, as components under its base -- or None.

    Never the base itself: a file sitting loose in LocalAppData or Saved Games does not
    make the whole of it a save folder.
    """
    for i in range(1, len(parts)):
        if parts[i].casefold() == "remote" and parts[i - 1].isdigit():
            return parts[:i]  # the appid folder of a Steam-cloud-shaped save
    if folder_id == "FOLDERID_SavedGames":
        return parts[:2] if parts else None
    for i, part in enumerate(parts):
        if _is_save_word(part):
            # "GSE Saves/3357650", "Goldberg SteamEmu Saves/270880": the emulator's folder
            # holds every game's saves, one appid each. Stopping at the save word took the
            # whole of it for whichever game happened to be running.
            if i + 1 < len(parts) and parts[i + 1].isdigit():
                return parts[: i + 2]
            return parts[: i + 1]
    if parts and _is_save_file(filename):
        return parts
    return None


# -- walking ------------------------------------------------------------------------------


def build_index(bases: list[tuple[str, str]], since: float = 0.0) -> Index:
    """Walk each (folder id, path) once and note every save-shaped folder's write times.

    Only writes at or after `since` are kept: nothing older can tell us anything about
    sessions the launcher recorded.
    """
    index = Index()
    for folder_id, base in bases:
        skip = {name.casefold() for name in rules.SAVES_WALK_SKIP.get(folder_id, ())}
        stack: list[tuple[str, list[str]]] = [(base, [])]
        while stack:
            path, parts = stack.pop()
            try:
                with os.scandir(path) as iterator:
                    entries = list(iterator)
            except OSError as exc:
                log.debug("cannot look inside %s: %s", path, exc)
                continue
            for entry in entries:
                try:
                    info = entry.stat(follow_symlinks=False)
                except OSError as exc:
                    log.debug("cannot stat %s: %s", entry.path, exc)
                    continue
                if getattr(info, "st_file_attributes", 0) & FILE_ATTRIBUTE_REPARSE_POINT:
                    continue
                if stat_module.S_ISDIR(info.st_mode):
                    if not parts and entry.name.casefold() in skip:
                        continue
                    if len(parts) < rules.SAVES_MAX_DEPTH:
                        stack.append((entry.path, parts + [entry.name]))
                    continue
                index.files_walked += 1
                if info.st_mtime < since:
                    continue
                root = save_root(parts, entry.name, folder_id)
                if root is None:
                    continue
                folder = os.path.join(base, *root)
                if not could_be_save_folder(folder):
                    continue
                index.folders.setdefault(folder, []).append(info.st_mtime)
    return index


# -- which of them belong to this game ----------------------------------------------------


def _compact(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.casefold())


def _names_the_game(folder_parts: list[str], name: str) -> bool:
    words = [w for w in re.findall(r"[a-z0-9]+", name.casefold())
             if len(w) >= 4 and w not in COMMON_WORDS]
    whole = _compact(name)
    for part in folder_parts:
        compact = _compact(part)
        if not compact or compact in COMMON_WORDS:
            continue
        if whole and (whole in compact or (len(compact) >= 4 and compact in whole)):
            return True
        if any(word in compact for word in words):
            return True
        if difflib.SequenceMatcher(None, whole, compact).ratio() >= 0.75:
            return True
    return False


def _inside(path: str, folder: str) -> bool:
    try:
        return os.path.commonpath([os.path.normcase(path), os.path.normcase(folder)]) == \
            os.path.normcase(folder)
    except ValueError:  # different drives
        return False


def belongs(folder: str, writes: list[float], *, name: str, appid: str, install_dir: str,
            windows: list[tuple[float, float]], base: str) -> str:
    """Why this save-shaped folder is this game's -- or "" if it is not."""
    if install_dir and _inside(folder, install_dir):
        return "inside the game's own folder"
    parts = os.path.relpath(folder, base).split(os.sep) if base else folder.split(os.sep)
    if appid and appid in parts:
        return f"carries its Steam number ({appid})"
    if _names_the_game(parts, name):
        return "named after it"
    first = windows[0][0] if windows else 0.0
    relevant = [w for w in writes if w >= first]
    if not relevant:
        return ""
    during = sum(1 for w in relevant if any(s <= w <= e for s, e in windows))
    if during < rules.SAVES_OWNED_MIN_WRITES:
        return ""  # one stray write is not evidence of anything
    if during / len(relevant) >= rules.SAVES_OWNED_FRACTION:
        return f"written while it ran ({during} of {len(relevant)} writes)"
    return ""


def find(index: Index, bases: list[tuple[str, str]], *, name: str, appid: str,
         install_dir: str, windows: list[tuple[float, float]],
         ignored: tuple[str, ...] = (), other_names: tuple[str, ...] = ()) -> list[Found]:
    """This game's save folders: written during its sessions, save-shaped, and its own.

    A folder named after a *different* game is never this one's, however it was written:
    one stray write during a Spider-Man 2 session once claimed The Last of Us Part I's
    Saved Games folder for it.
    """
    if not windows:
        return []
    ignored_keys = {os.path.normcase(p) for p in ignored}
    candidates = []
    for folder, writes in index.folders.items():
        if os.path.normcase(folder) in ignored_keys:
            continue
        if not any(s <= w <= e for w in writes for s, e in windows):
            continue
        base = next((b for _id, b in bases if _inside(folder, b)), "")
        parts = os.path.relpath(folder, base).split(os.sep) if base else []
        names_another = any(other and _names_the_game(parts, other) for other in other_names)
        if names_another and not _names_the_game(parts, name):
            continue
        if _holds_appid_folders(folder, index):
            # The emulator's own folder -- every game's saves, one numbered folder each,
            # plus its settings. Writing those settings during a session once made the
            # whole thing American Truck Simulator's. Its numbered folders can still be.
            continue
        reason = belongs(folder, writes, name=name, appid=appid, install_dir=install_dir,
                         windows=windows, base=base)
        if reason:
            candidates.append(Found(folder, reason))
    # A folder inside another one that was also found is already covered by it.
    return _collapse(candidates)


def _holds_appid_folders(folder: str, index: Index) -> bool:
    """Whether any save folder seen anywhere sits inside this one under a Steam appid."""
    key = os.path.normcase(folder)
    for other in index.folders:
        other_key = os.path.normcase(other)
        if other_key != key and _inside(other_key, key) and os.path.basename(other).isdigit():
            return True
    return False


def _collapse(found: list[Found]) -> list[Found]:
    """Drop folders inside others, and fold two or more siblings into their parent.

    Stalker 2 keeps dated backup folders side by side; listed one by one they read as
    four places, when they are one.
    """
    by_parent: dict[str, list[Found]] = {}
    for item in found:
        by_parent.setdefault(os.path.normcase(os.path.dirname(item.path)), []).append(item)
    merged: list[Found] = []
    for items in by_parent.values():
        if len(items) >= 2:
            merged.append(Found(os.path.dirname(items[0].path), items[0].reason))
        else:
            merged.extend(items)
    merged.sort(key=lambda f: len(f.path))
    kept: list[Found] = []
    for item in merged:
        if not any(_inside(item.path, k.path) for k in kept):
            kept.append(item)
    return kept
