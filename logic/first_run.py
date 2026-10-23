"""The first-run question's homework: where a new user's games might be (Phase 77).

A launcher installed on someone else's PC knows nothing of C:\\games. Before its first scan
the window asks "Where do you keep your games?" and offers what this module finds: on every
fixed disk, the folders one level below the root whose name has a game word in it
(rules.FIRST_RUN_FOLDER_HINTS) -- never a store's own library (the providers find those
games, and the scan excludes the folders anyway), never Windows' own folders, never a hidden
or system folder, and never a link to somewhere else. It only looks; it writes nothing.

Also here, what the question and Settings share: whether a folder is a whole drive -- since
Phase 82 refused, with the drive's own game folders offered in its place (`instead_of`); a
warning was not a guard, and the first friend to install 1.2.1 chose C:\\ -- and which of the
chosen folders can be reached now (the empty library says which cannot).
"""

from __future__ import annotations

import logging
import os
import re
import stat

from shared import drives
from shared import rules

log = logging.getLogger(__name__)

_WORDS = re.compile(r"[^\W\d_]+")  # runs of letters, any alphabet


def _flags(path: str) -> int:
    try:
        return os.stat(path, follow_symlinks=False).st_file_attributes
    except (OSError, AttributeError):
        return 0


def _offered(folder: str, name: str) -> bool:
    folded = name.casefold()
    # One level below a drive's root, a Windows folder's path from it is its name (Phase 82: one
    # list of them, rules.SYSTEM_FOLDERS; a test's made-up drive is a folder of its own).
    if folded in rules.FIRST_RUN_STORE_FOLDERS or folded in rules.SYSTEM_FOLDERS:
        return False
    if not set(_WORDS.findall(folded)) & set(rules.FIRST_RUN_FOLDER_HINTS):
        return False
    attributes = _flags(folder)
    if attributes & (stat.FILE_ATTRIBUTE_HIDDEN | stat.FILE_ATTRIBUTE_SYSTEM | stat.FILE_ATTRIBUTE_REPARSE_POINT):
        return False
    # A Steam library is one whatever it is called: Steam keeps its games in "steamapps".
    if os.path.isdir(os.path.join(folder, rules.FIRST_RUN_STEAM_MARKER)):
        return False
    return True


def candidates(roots: list[str] | None = None) -> list[str]:
    """Folders that look like where the games are, drive by drive, in name order.

    `roots` are the drive roots to look under -- the fixed disks when not given, which is what
    the window asks for; a test hands it folders of its own that stand in for drives.
    """
    found = []
    for root in drives.fixed_drives() if roots is None else roots:
        try:
            names = sorted(os.listdir(root), key=str.casefold)
        except OSError as exc:
            log.info("first run: could not look in %s (%s)", root, exc)
            continue
        for name in names:
            folder = os.path.join(root, name)
            if os.path.isdir(folder) and _offered(folder, name):
                found.append(folder)
    log.info("first run: %d folder(s) that look like game folders: %s", len(found), found)
    return found


def xbox_found(roots: list[str] | None = None) -> bool:
    """Whether some fixed disk has the folder the Xbox app installs into."""
    return any(os.path.isdir(os.path.join(root, rules.XBOX_GAMES_DIRNAME))
               for root in (drives.fixed_drives() if roots is None else roots))


def is_drive_root(folder: str) -> bool:
    """'D:\\' or 'D:' -- a whole drive, which would treat every folder on it as a game."""
    return drives.is_drive_root(folder)


def instead_of(folder: str) -> list[str]:
    """What to offer in place of a whole drive chosen as a game folder (Phase 82): the folders on
    it the first run would offer, the same finder."""
    return candidates([drives.drive_name(folder)])


def reachable(roots) -> tuple[list[str], list[str]]:
    """The chosen folders that are there now, and the ones that are not (a drive unplugged)."""
    here, gone = [], []
    for root in roots or ():
        (here if os.path.isdir(root) else gone).append(root)
    return here, gone
