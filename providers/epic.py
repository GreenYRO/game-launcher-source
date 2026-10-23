"""Epic Games Store titles, read from the launcher's own .item manifests.

Each manifest is plain JSON in %ProgramData%\\Epic\\EpicGamesLauncher\\Data\\Manifests.
Launching goes through the com.epicgames.launcher:// protocol rather than the executable:
the manifests point at a bootstrapper, and Epic titles generally expect the launcher to
have authenticated first.

Paths inside the manifests use forward slashes ("C:/Program Files/Epic Games/Fortnite")
and must be normalised before use.
"""

from __future__ import annotations

import json
import logging
import os
import time
from urllib.parse import quote

from shared import naming
from shared import rules
from shared.models import GameEntry

log = logging.getLogger(__name__)

SOURCE = "epic"


def manifest_dir() -> str:
    program_data = os.environ.get("ProgramData") or r"C:\ProgramData"
    return os.path.join(program_data, *rules.EPIC_MANIFEST_SUBPATH)


class EpicProvider:
    name = SOURCE

    def __init__(self) -> None:
        self.manifest_dir = manifest_dir()

    def is_available(self) -> bool:
        return os.path.isdir(self.manifest_dir)

    def discover(self) -> list[GameEntry]:
        started = time.perf_counter()
        if not os.path.isdir(self.manifest_dir):
            log.info("epic: no manifest directory at %s", self.manifest_dir)
            return []

        try:
            names = sorted(os.listdir(self.manifest_dir))
        except OSError as exc:
            log.error("epic: cannot list %s: %s", self.manifest_dir, exc)
            return []

        entries: list[GameEntry] = []
        skipped: dict[str, int] = {}
        count = 0
        for name in names:
            if not name.casefold().endswith(rules.EPIC_MANIFEST_SUFFIX):
                continue
            count += 1
            entry, reason = self._read_manifest(os.path.join(self.manifest_dir, name))
            if entry is not None:
                entries.append(entry)
            elif reason:
                skipped[reason] = skipped.get(reason, 0) + 1

        log.info(
            "epic: %d entries from %d manifest(s) in %.2fs; skipped %s",
            len(entries),
            count,
            time.perf_counter() - started,
            skipped or "nothing",
        )
        return entries

    def _read_manifest(self, path: str) -> tuple[GameEntry | None, str]:
        try:
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            log.error("epic: could not read %s: %s", path, exc)
            return None, "unreadable manifest"
        if not isinstance(data, dict):
            log.error("epic: %s is not a JSON object", path)
            return None, "unreadable manifest"

        name = naming.sanitize_title(str(data.get("DisplayName") or "")) or "Unknown Epic title"
        app_name = str(data.get("AppName") or "").strip()
        namespace = str(data.get("CatalogNamespace") or "").strip()
        item_id = str(data.get("CatalogItemId") or "").strip()

        if not (app_name and namespace and item_id):
            log.warning("epic: %s lacks the ids needed to build a launch URI; skipping", path)
            return None, "incomplete manifest"

        if data.get("bIsIncompleteInstall"):
            log.info("epic: %s is a partial install; skipping", name)
            return None, "incomplete install"

        categories = [str(c).casefold() for c in data.get("AppCategories") or []]
        if categories and rules.EPIC_REQUIRED_CATEGORY not in categories:
            log.info("epic: %s is categorised %s, not a game; skipping", name, categories)
            return None, "not categorised as a game"

        install_dir = _normalise(str(data.get("InstallLocation") or ""))
        if not install_dir or not os.path.isdir(install_dir):
            log.warning("epic: %s claims %r, which is not there; skipping", name, install_dir)
            return None, "install directory missing"

        relative_exe = _normalise(str(data.get("LaunchExecutable") or ""))
        exe = os.path.join(install_dir, relative_exe) if relative_exe else ""
        if exe and not os.path.isfile(exe):
            log.info("epic: %s launch executable %s not found; icon will fall back", name, exe)
            exe = ""

        return (
            GameEntry(
                source=SOURCE,
                source_id=app_name,
                display_name=name,
                install_dir=install_dir,
                launch_kind="uri",
                launch_target=rules.EPIC_LAUNCH_URI.format(
                    namespace=quote(namespace, safe=""),
                    item_id=quote(item_id, safe=""),
                    app_name=quote(app_name, safe=""),
                ),
                working_dir=install_dir,
                icon_hint=exe or install_dir,
                size_on_disk=_as_int(data.get("InstallSize")),
                detection="manifest",
                extra={
                    "app_name": app_name,
                    "catalog_namespace": namespace,
                    "catalog_item_id": item_id,
                    "launch_executable": exe,
                    "categories": categories,
                    "version": str(data.get("AppVersionString") or ""),
                    "manifest": path,
                },
            ),
            "",
        )


def _normalise(path: str) -> str:
    return os.path.normpath(path.replace("/", "\\")) if path.strip() else ""


def _as_int(value) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return 0
