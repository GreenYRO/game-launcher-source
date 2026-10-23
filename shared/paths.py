"""Where the app lives, and where it keeps its files.

One owner, because the answer changes completely depending on how the app was started.

Run from source -- which is how it has always run here -- the program and its data share
the project folder, exactly as before. Nothing about that changes.

Frozen into an exe by the installer, `__file__` points inside the bundle's `_internal`
folder. That folder is a build artefact and a reinstall replaces it wholesale, so writing
overrides.json in there would throw away playtime and chosen artwork on every upgrade.
The data goes beside the exe instead, which also means the installed folder holds
everything the app owns -- copying it is a complete backup.
"""

from __future__ import annotations

import sys
from pathlib import Path

from shared import rules

FROZEN = bool(getattr(sys, "frozen", False))

_SOURCE_DIR = Path(__file__).resolve().parents[1]  # the project folder, one up from shared/


def program_dir() -> Path:
    """The folder the program itself was started from."""
    return Path(sys.executable).resolve().parent if FROZEN else _SOURCE_DIR


def data_dir() -> Path:
    """config.json, overrides.json, catalog.json and cache/ all live here.

    Its own function for exactly the day it was needed: since Phase 48, run from source,
    the data has its own folder under the project; an installed copy keeps it beside the
    exe, where a reinstall steps around it.
    """
    return program_dir() if FROZEN else _SOURCE_DIR / rules.DATA_DIRNAME


def resource_dir() -> Path:
    """Read-only files shipped with the program, such as launcher.ico.

    A frozen bundle unpacks these somewhere of its own choosing and points sys._MEIPASS at
    it, which is *not* where the exe is.
    """
    if FROZEN:
        return Path(getattr(sys, "_MEIPASS", "") or program_dir())
    return _SOURCE_DIR


def cache_dir() -> Path:
    return data_dir() / "cache"
