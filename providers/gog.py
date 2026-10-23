"""GOG games, read from the registry the GOG installers write.

GOG games are DRM free and are launched by exe path directly -- there is no client to go
through, and no overlay or achievement plumbing to lose by not going through one. That is
the one place a manifest provider still produces launch_kind "exe".

The registry gives an absolute exe and a working directory, so none of the folder
scanner's guessing about which exe is the game applies here.
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

SOURCE = "gog"


class GogProvider:
    name = SOURCE

    def is_available(self) -> bool:
        return any(
            registry.key_exists(hive, subkey) for hive, subkey in rules.GOG_REGISTRY_LOCATIONS
        )

    def discover(self) -> list[GameEntry]:
        started = time.perf_counter()
        entries: list[GameEntry] = []
        skipped: dict[str, int] = {}
        seen: set[str] = set()

        for hive, subkey in rules.GOG_REGISTRY_LOCATIONS:
            for game_id in registry.subkey_names(hive, subkey):
                if game_id in seen:
                    continue
                seen.add(game_id)
                entry, reason = self._read_game(hive, f"{subkey}\\{game_id}", game_id)
                if entry is not None:
                    entries.append(entry)
                elif reason:
                    skipped[reason] = skipped.get(reason, 0) + 1

        log.info(
            "gog: %d entries from %d registry key(s) in %.2fs; skipped %s",
            len(entries),
            len(seen),
            time.perf_counter() - started,
            skipped or "nothing",
        )
        return entries

    def _read_game(self, hive: str, subkey: str, game_id: str) -> tuple[GameEntry | None, str]:
        values = registry.read_all_values(hive, subkey)
        if not values:
            log.warning("GOG key %s has no values; skipping", subkey)
            return None, "empty registry key"

        exe = _text(values.get("exe"))
        install_dir = _text(values.get("path"))
        name = naming.sanitize_title(_text(values.get("gameName"))) or f"GOG game {game_id}"

        if not exe:
            log.warning("GOG %s (%s) has no exe value; skipping", name, game_id)
            return None, "no exe recorded"

        exe = os.path.normpath(exe)
        if not os.path.isfile(exe):
            log.warning("GOG %s points at %s, which is not there; skipping", name, exe)
            return None, "exe missing on disk"

        install_dir = os.path.normpath(install_dir) if install_dir else os.path.dirname(exe)
        working_dir = _text(values.get("workingDir")) or os.path.dirname(exe)
        working_dir = os.path.normpath(working_dir)
        if not os.path.isdir(working_dir):
            log.warning("GOG %s working dir %s missing; using the exe folder", name, working_dir)
            working_dir = os.path.dirname(exe)

        size = walk.measure_size(install_dir) if rules.MEASURE_INSTALL_SIZE else 0
        return (
            GameEntry(
                source=SOURCE,
                source_id=game_id,
                display_name=name,
                install_dir=install_dir,
                launch_kind="exe",
                launch_target=exe,
                working_dir=working_dir,
                icon_hint=exe,
                size_on_disk=size,
                detection="manifest",
                extra={
                    "game_id": game_id,
                    "registry_key": f"{hive}\\{subkey}",
                    "launch_param": _text(values.get("launchParam")),
                    "install_date": _text(values.get("INSTALLDATE")),
                    "build_id": _text(values.get("buildId")),
                },
            ),
            "",
        )


def _text(value) -> str:
    return value.strip() if isinstance(value, str) else ""
