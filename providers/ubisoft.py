"""Ubisoft Connect games, read from the launcher's Installs registry keys.

Read this before trusting the output: on the machine this was written against, both
Installs\\<id> keys exist but contain only InstallState, with no InstallDir anywhere in
either hive. The games had been uninstalled -- their cloud saves and cached icons remained,
which is exactly what an uninstall leaves behind -- so the keys are orphans.

That makes the correct result here zero entries, and it means the entry-building path has
never run against a real installed Ubisoft game. It is exercised by tests with injected
registry values instead. An entry is only produced when InstallDir is present AND the
directory exists, so an orphan key can never become a tile for a game that is not there.
"""

from __future__ import annotations

import logging
import os
import time

from shared import naming
from shared import registry
from shared import rules
from shared import walk
from shared.models import GameEntry

log = logging.getLogger(__name__)

SOURCE = "ubisoft"


class UbisoftProvider:
    name = SOURCE

    def is_available(self) -> bool:
        return any(
            registry.key_exists(hive, subkey)
            for hive, subkey in rules.UBISOFT_REGISTRY_LOCATIONS
        )

    def discover(self) -> list[GameEntry]:
        started = time.perf_counter()
        entries: list[GameEntry] = []
        skipped: dict[str, int] = {}
        seen: set[str] = set()

        for hive, subkey in rules.UBISOFT_REGISTRY_LOCATIONS:
            for game_id in registry.subkey_names(hive, subkey):
                if game_id in seen:
                    continue
                values = registry.read_all_values(hive, f"{subkey}\\{game_id}")
                entry, reason = build_entry(game_id, values, f"{hive}\\{subkey}\\{game_id}")
                if entry is not None:
                    seen.add(game_id)
                    entries.append(entry)
                elif reason:
                    skipped[reason] = skipped.get(reason, 0) + 1

        log.info(
            "ubisoft: %d entries in %.2fs; skipped %s",
            len(entries),
            time.perf_counter() - started,
            skipped or "nothing",
        )
        return entries


def build_entry(
    game_id: str, values: dict, origin: str = ""
) -> tuple[GameEntry | None, str]:
    """Turn one Installs\\<id> key into an entry. Separated out so it is testable."""
    install_dir = _text(values.get("InstallDir"))
    if not install_dir:
        log.info(
            "ubisoft: key %s has no InstallDir (values: %s); treating as not installed",
            origin or game_id,
            sorted(values) or "none",
        )
        return None, "no InstallDir recorded"

    install_dir = os.path.normpath(install_dir.replace("/", "\\"))
    if not os.path.isdir(install_dir):
        log.warning("ubisoft: %s points at %s, which is not there; skipping", game_id, install_dir)
        return None, "install directory missing"

    # The registry carries no title, so the folder name is the only local source for one.
    name = naming.clean_folder_name(os.path.basename(install_dir.rstrip("\\")))
    size = walk.measure_size(install_dir) if rules.MEASURE_INSTALL_SIZE else 0

    return (
        GameEntry(
            source=SOURCE,
            source_id=game_id,
            display_name=name or f"Ubisoft game {game_id}",
            install_dir=install_dir,
            launch_kind="uri",
            launch_target=rules.UBISOFT_LAUNCH_URI.format(game_id=game_id),
            working_dir=install_dir,
            icon_hint=install_dir,
            size_on_disk=size,
            detection="manifest",
            extra={
                "game_id": game_id,
                "registry_key": origin,
                "install_state": values.get("InstallState"),
                "name_source": "install folder name (the registry records no title)",
            },
        ),
        "",
    )


def _text(value) -> str:
    return value.strip() if isinstance(value, str) else ""
