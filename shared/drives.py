"""The PC's drives, which of them are fixed disks (Phase 77), and what on them is no game folder
(Phase 82).

Windows' own answer, through GetDriveTypeW: a fixed disk is an internal drive; a USB stick
says "removable", a mapped share "remote", a DVD "cdrom". Only fixed disks are offered as
places a new user's games might be -- a stick that is not plugged in next week would make a
game folder that silently vanishes. Non-raising, like registry.py beside it: a drive that
cannot be asked is simply not listed.

Phase 82: a whole drive is not a game folder -- with C:\\ as one, the scan took every folder of
the drive for a game, walked each six levels deep for ten minutes at every start, and offered
"Remove from disk..." on Program Files. Nor is one of Windows' own folders (rules.SYSTEM_FOLDERS),
told by where it sits below its drive's root rather than by its name. The judgements live here,
in shared/, because the first run and Settings (refusing them), discovery (not scanning them),
the folder provider and the walk (never entering them) and removal (never deleting them) all ask.
"""

from __future__ import annotations

import ctypes
import logging
import os

from shared import rules

log = logging.getLogger(__name__)

DRIVE_FIXED = 3  # GetDriveTypeW: 0 unknown, 1 no root, 2 removable, 3 fixed, 4 remote, 5 cdrom, 6 ramdisk


def all_drives() -> list[str]:
    """Every drive root Windows knows of, 'C:\\' first."""
    try:
        return sorted(os.listdrives())
    except (AttributeError, OSError) as exc:
        log.debug("os.listdrives unavailable (%s); trying every letter", exc)
        return [f"{letter}:\\" for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ" if os.path.isdir(f"{letter}:\\")]


def drive_type(root: str) -> int:
    try:
        return int(ctypes.windll.kernel32.GetDriveTypeW(root))
    except (AttributeError, OSError) as exc:
        log.debug("could not ask the type of %s: %s", root, exc)
        return 0


def fixed_drives() -> list[str]:
    """The fixed disks' roots -- internal drives only, never USB sticks, shares or discs."""
    return [root for root in all_drives() if drive_type(root) == DRIVE_FIXED]


# -- what is no game folder (Phase 82) --------------------------------------------------------


def below_root(folder: str) -> str | None:
    """`folder`'s path below its drive's root, in lower case with backslashes: "" for the root
    itself ("D:\\", "D:", a share's "\\\\server\\share"), "program files\\windowsapps" for that
    folder; None for a path that names no drive. A test stands in for it to make a folder of its
    own a drive."""
    drive, rest = os.path.splitdrive(os.path.normpath(folder))
    if not drive:
        return None
    return rest.replace("/", "\\").strip("\\").casefold()


def is_drive_root(folder: str) -> bool:
    """'D:\\' or 'D:' -- a whole drive, which would treat every folder on it as a game."""
    return below_root(folder) == ""


def is_system_folder(folder: str) -> bool:
    """One of Windows' own folders, by where it sits: C:\\Windows, C:\\Program Files\\WindowsApps --
    never a game's own subfolder that happens to share the name."""
    return below_root(folder) in rules.SYSTEM_FOLDERS


def on_drive_root(folder: str) -> bool:
    """Directly below a drive's root: C:\\Games, C:\\Windows -- one step from the whole drive."""
    below = below_root(folder)
    return bool(below) and "\\" not in below


def drive_name(root: str) -> str:
    """A drive's root as it is written to the user, and looked in: 'C:\\' -- never 'C:', which
    Windows reads as that drive's current folder rather than its root."""
    name = os.path.normpath(root)
    return name if name.endswith("\\") else name + "\\"


def not_a_game_folder(folder: str) -> str:
    """Why `folder` can never be a game folder, in a sentence for the user -- or "" when it may be."""
    if is_drive_root(folder):
        return f"{drive_name(folder)} is a whole drive, not a game folder."
    if is_system_folder(folder):
        return f"{os.path.normpath(folder)} is a Windows folder, not a game folder."
    return ""


def split_roots(roots) -> tuple[list[str], list[tuple[str, str]]]:
    """The roots the scan may look in, and the ones it never does, each with why."""
    usable, refused = [], []
    for root in roots or ():
        why = not_a_game_folder(root)
        if why:
            refused.append((root, why))
        else:
            usable.append(root)
    return usable, refused
