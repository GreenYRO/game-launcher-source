"""Xbox / Game Pass titles.

Off by default (`config.json: "enable_xbox"`), because this is the least certain source.

C:\\Program Files\\WindowsApps is never touched -- it is ACL-locked to TrustedInstaller and
reading it means fighting the OS. Instead this reads <drive>:\\XboxGames, where modern Game
Pass installs actually land and which is readable by an ordinary user. The presence of
Content\\MicrosoftGame.config is what makes a folder a game, which sidesteps the real
problem with the Get-StartApps approach: among 255 Start entries, ordinary UWP apps and
even Steam shortcuts are indistinguishable from games by name alone.

The launch id (AUMID) is assembled from two verified halves: the package family name, which
PowerShell reports, and the executable id inside MicrosoftGame.config. On this machine that
produces exactly the AUMID Get-StartApps lists, and Get-StartApps is the fallback when the
package cannot be resolved.

Known limitation: Game Pass titles installed before the XboxGames layout, which live only
under WindowsApps, are not found. Listing them would mean guessing which of the Start menu's
UWP entries are games.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import time
import xml.etree.ElementTree as ElementTree

from shared import rules
from shared import walk
from shared.models import GameEntry

log = logging.getLogger(__name__)

SOURCE = "xbox"
POWERSHELL_FLAGS = ["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command"]


class XboxProvider:
    name = SOURCE

    def is_available(self) -> bool:
        return bool(game_roots())

    def discover(self) -> list[GameEntry]:
        started = time.perf_counter()
        roots = game_roots()
        if not roots:
            log.info("xbox: no XboxGames directory on any drive")
            return []

        families = package_families()
        start_apps = start_menu_apps()
        entries: list[GameEntry] = []
        skipped: dict[str, int] = {}
        looked_at = 0

        for root in roots:
            try:
                names = sorted(os.listdir(root))
            except OSError as exc:
                log.warning("xbox: cannot list %s: %s", root, exc)
                continue
            for name in names:
                folder = os.path.join(root, name)
                if not os.path.isdir(folder):
                    continue
                looked_at += 1
                entry, reason = self._read_game(folder, families, start_apps)
                if entry is not None:
                    entries.append(entry)
                elif reason:
                    skipped[reason] = skipped.get(reason, 0) + 1

        log.info(
            "xbox: %d entries from %d folder(s) across %d root(s) in %.2fs; skipped %s",
            len(entries),
            looked_at,
            len(roots),
            time.perf_counter() - started,
            skipped or "nothing",
        )
        return entries

    def _read_game(
        self, folder: str, families: dict[str, str], start_apps: dict[str, str]
    ) -> tuple[GameEntry | None, str]:
        config_path = os.path.join(folder, *rules.XBOX_CONFIG_RELATIVE)
        if not os.path.isfile(config_path):
            log.debug("xbox: %s has no MicrosoftGame.config; not a game", folder)
            return None, "not a game folder"

        info = parse_game_config(config_path)
        if info is None:
            return None, "unreadable MicrosoftGame.config"

        identity, display_name, executable_id = info
        display_name = display_name or os.path.basename(folder)

        family = families.get(identity.casefold(), "")
        aumid = f"{family}!{executable_id}" if family and executable_id else ""
        if not aumid:
            aumid = start_apps.get(display_name.casefold(), "")
            if aumid:
                log.info("xbox: %s resolved via Get-StartApps", display_name)
        if not aumid:
            log.warning(
                "xbox: cannot build a launch id for %s (identity=%r, family=%r, exe id=%r)",
                display_name,
                identity,
                family,
                executable_id,
            )
            return None, "no launch id"

        content = os.path.join(folder, rules.XBOX_CONFIG_RELATIVE[0])
        return (
            GameEntry(
                source=SOURCE,
                source_id=aumid,
                display_name=display_name,
                install_dir=folder,
                launch_kind="uri",
                launch_target=rules.XBOX_LAUNCH_TARGET.format(aumid=aumid),
                working_dir=folder,
                icon_hint=find_logo(content) or folder,
                size_on_disk=walk.measure_size(folder) if rules.MEASURE_INSTALL_SIZE else 0,
                detection="manifest",
                extra={
                    "aumid": aumid,
                    "package_identity": identity,
                    "package_family": family,
                    "executable_id": executable_id,
                    "config": config_path,
                },
            ),
            "",
        )


def game_roots() -> list[str]:
    """Every <drive>:\\XboxGames that exists."""
    roots = []
    for drive in _drives():
        candidate = os.path.join(drive, rules.XBOX_GAMES_DIRNAME)
        if os.path.isdir(candidate):
            roots.append(candidate)
    return roots


def _drives() -> list[str]:
    try:
        return list(os.listdrives())
    except (AttributeError, OSError) as exc:
        log.debug("os.listdrives unavailable (%s); falling back to a letter scan", exc)
        return [f"{letter}:\\" for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ"]


def parse_game_config(path: str) -> tuple[str, str, str] | None:
    """Return (package identity, display name, executable id) from MicrosoftGame.config."""
    try:
        root = ElementTree.parse(path).getroot()
    except (OSError, ElementTree.ParseError) as exc:
        log.error("xbox: could not parse %s: %s", path, exc)
        return None

    identity_node = root.find("Identity")
    identity = identity_node.get("Name", "") if identity_node is not None else ""

    visuals = root.find("ShellVisuals")
    display_name = visuals.get("DefaultDisplayName", "") if visuals is not None else ""

    executable_id = ""
    executables = root.find("ExecutableList")
    if executables is not None:
        first = executables.find("Executable")
        if first is not None:
            executable_id = first.get("Id", "")

    if not identity:
        log.warning("xbox: %s has no Identity Name", path)
    return identity, display_name, executable_id


def find_logo(content_dir: str) -> str:
    for name in rules.XBOX_LOGO_PREFERENCE:
        candidate = os.path.join(content_dir, name)
        if os.path.isfile(candidate):
            return candidate
    log.debug("xbox: no packaged logo in %s", content_dir)
    return ""


def package_families() -> dict[str, str]:
    """Map package identity -> PackageFamilyName, via PowerShell."""
    raw = _powershell(
        "Get-AppxPackage | Select-Object Name,PackageFamilyName | ConvertTo-Json -Compress"
    )
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        log.warning("xbox: could not parse Get-AppxPackage output: %s", exc)
        return {}
    if isinstance(payload, dict):
        payload = [payload]
    mapping: dict[str, str] = {}
    for item in payload:
        if isinstance(item, dict) and item.get("Name") and item.get("PackageFamilyName"):
            mapping[str(item["Name"]).casefold()] = str(item["PackageFamilyName"])
    log.info("xbox: %d installed package(s) known to Windows", len(mapping))
    return mapping


def start_menu_apps() -> dict[str, str]:
    """Map display name -> AUMID, via Get-StartApps. Only used as a fallback."""
    raw = _powershell("Get-StartApps | Select-Object Name,AppID | ConvertTo-Json -Compress")
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        log.warning("xbox: could not parse Get-StartApps output: %s", exc)
        return {}
    if isinstance(payload, dict):
        payload = [payload]
    return {
        str(item["Name"]).casefold(): str(item["AppID"])
        for item in payload
        if isinstance(item, dict) and item.get("Name") and item.get("AppID")
    }


def _powershell(command: str) -> str:
    try:
        result = subprocess.run(
            ["powershell", *POWERSHELL_FLAGS, command],
            capture_output=True,
            text=True,
            timeout=rules.XBOX_POWERSHELL_TIMEOUT_SECONDS,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("xbox: PowerShell call failed: %s: %s", type(exc).__name__, exc)
        return ""
    if result.returncode != 0:
        log.warning("xbox: PowerShell exited %s: %s", result.returncode, result.stderr.strip()[:200])
        return ""
    return result.stdout.strip()
