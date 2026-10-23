"""The launcher's own name and version number -- one place for both (Phase 77).

Semantic versioning, MAJOR.MINOR.PATCH: the friends who install it see versions, not phase
numbers. A fix that changes nothing else raises PATCH; something new that leaves everything
working raises MINOR; something that breaks what was there raises MAJOR. 1.0 was the
installer as first built (Phase 47); 1.1.0 was built in Phase 78 and never handed out; 1.2.0
(Phase 79, the update check) is the first one handed to anyone, published on GitHub; 1.2.1
(Phase 80) adds the anonymous export; 1.2.2 (Phase 82, a hotfix) refuses a whole drive as a game
folder; 1.2.3 (Phase 85) brings the Reports tab (Phases 83-84); 1.2.4 (Phase 88) the Steam wishlist and its
tab (Phases 86-87); 1.2.5 (Phase 90) the wishlist's sharper fit, report 8 and the price lines (Phase 89);
1.2.6 (Phase 95) the tray and Start with Windows (Phase 92), sessions of games started outside the launcher
(Phase 93) and a sleep never counted as play (Phase 94); 1.2.7 (Phase 97) the recap card -- a month or a year in
review as one image -- and the one rule that makes Stats count every game played (Phase 96); 1.2.8 (Phase 100)
For you and report 9 (Phase 98), the tray offered once, an accent of one's own, Starting... and the genre
pill (Phase 99); 1.2.9 (Phase 104) price alerts on the wishlist (Phase 101), the question after a session and
report 10 (Phase 102), the hours pill on a game's page (its extension), Left behind and report 11 (Phase 103) --
the library from schema 7 to 8; 1.2.10 (Phase 107) the missing covers in one go (Phase 105) and What's new, each
version's notes in the project (Phase 106).
**The user's rule since 12 October: each
release raises the last number by one** (1.2.1, 1.2.2, ...), a feature included -- smaller steps than semantic
versioning's MINOR. The update check only needs every new number to be higher.

`is_newer` compares two of these the way the numbers mean, not as text: "1.10.0" is newer than
"1.9.0", and a tag GitHub carries ("v1.2.0") reads as its number. Anything else -- a pre-release
suffix, a word -- is not a version and is never newer.

The single source of truth: packaging/build.py reads APP_VERSION from here and stamps it into
the built app's _internal\\VERSION, which the installer reads for Add/Remove Programs; the
running app writes it into launcher.log at every start and shows it in Settings. A test holds
all four to the same value.
"""

from __future__ import annotations

import logging
import re
from datetime import date

from shared import paths

log = logging.getLogger(__name__)

APP_NAME = "Game Launcher"
APP_VERSION = "1.2.10"

# Beside the code of a built copy (paths.resource_dir(), _internal\): the version for the
# installer, and the day it was built. A copy run from source has neither.
VERSION_FILE = "VERSION"
BUILD_FILE = "BUILD"


def build_date() -> date | None:
    """The day this copy was built -- None when it runs from source, or the file is unreadable."""
    if not paths.FROZEN:
        return None
    try:
        return date.fromisoformat((paths.resource_dir() / BUILD_FILE).read_text(encoding="utf-8").strip())
    except (OSError, ValueError) as exc:
        log.warning("no build date (%s)", exc)
        return None


def describe() -> str:
    """'Game Launcher 1.1.0, built 2026-10-12' -- or 'run from source' -- for the log."""
    built = build_date()
    return f"{APP_NAME} {APP_VERSION}, " + (f"built {built.isoformat()}" if built else "run from source")


# "1.2.0", "v1.2.0", "1.2" (read as 1.2.0) -- and nothing else: no suffix, no words.
_VERSION = re.compile(r"[vV]?(\d+)\.(\d+)(?:\.(\d+))?")


def parse(text: str) -> tuple[int, int, int] | None:
    """A version's three numbers, or None when the text is not a plain version."""
    match = _VERSION.fullmatch(str(text or "").strip())
    if match is None:
        return None
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch or 0)


def is_newer(candidate: str, current: str | None = None) -> bool:
    """Is `candidate` a later version than `current` (this copy's, unless named)? Never, if either
    is not a version."""
    theirs, ours = parse(candidate), parse(APP_VERSION if current is None else current)
    return theirs is not None and ours is not None and theirs > ours
