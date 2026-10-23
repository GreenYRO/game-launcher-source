"""config.json: the scan roots, the preferences and the SteamGridDB key.

Read with defaults for anything missing, and written by merging, never by rewriting: the
settings dialog, the window and the scanner each own a few keys of one shared file. The
code moved here from logic/discovery.py in Phase 46, unchanged, so that every read and
write of the launcher's three files sits in data_access/ -- discovery finds games, it
does not keep settings.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from data_access import backups
from shared import paths
from shared import rules

log = logging.getLogger(__name__)

CONFIG_PATH = paths.data_dir() / "config.json"


def load_config(path: Path = CONFIG_PATH) -> dict:
    defaults = {
        "roots": list(rules.DEFAULT_ROOTS),
        "max_depth": rules.MAX_DEPTH,
        "exclusions": [],
        # Steam cover art and app types only. Set false to keep the launcher fully offline.
        "allow_network": rules.ALLOW_NETWORK_DEFAULT,
        # Xbox / Game Pass. Off by default: it is the least certain source.
        "enable_xbox": rules.XBOX_ENABLED_DEFAULT,
    }
    if not path.is_file():
        log.info("no config at %s; using defaults", path)
        return defaults
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.error("could not read %s (%s); using defaults", path, exc)
        return defaults
    if not isinstance(loaded, dict):
        log.error("%s is not a JSON object; using defaults", path)
        return defaults
    defaults.update(loaded)
    return defaults


def saved_exists(path: Path = CONFIG_PATH) -> bool:
    """Whether settings were ever saved here. No config.json is a fresh install (Phase 77):
    the window asks where the games are before its first scan, and writes the answer."""
    return path.is_file()


def load_saved(path: Path = CONFIG_PATH) -> dict:
    """The settings as the file holds them, with no defaults filled in -- {} if there are none.

    For an export bundle, which carries what this PC saved rather than what the program would
    assume (Phase 65; transfer read the file itself before).
    """
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.error("could not read %s: %s", path, exc)
        return {}
    return loaded if isinstance(loaded, dict) else {}


def save_config(values: dict, path: Path = CONFIG_PATH) -> bool:
    """Merge `values` into config.json, leaving every other setting untouched.

    Merging rather than rewriting matters: the settings dialog knows about three keys, and
    rewriting the file from those alone would silently delete the scan roots.
    """
    current: dict = {}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                current = loaded
            else:
                log.error("%s is not a JSON object; replacing it", path)
        except (OSError, json.JSONDecodeError) as exc:
            log.error("could not read %s (%s); writing a fresh one", path, exc)

    current.update(values)
    # Atomic, like overrides.json: config.json holds the scan roots and the SteamGridDB
    # key, so a crash part way through a save must not be able to leave it half written.
    if not backups.atomic_write(path, json.dumps(current, indent=2) + "\n"):
        return False
    log.info("saved settings: %s", ", ".join(sorted(values)))
    return True
