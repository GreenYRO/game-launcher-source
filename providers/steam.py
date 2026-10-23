"""Steam games, read from the client's own local manifests.

Nothing here talks to the network. Everything comes from the registry, libraryfolders.vdf
and the appmanifest_*.acf files, all of which are text VDF and are parsed with the vdf
package rather than pattern-matched.

Steam games are launched by URI, never by exe path: a great many are DRM-wrapped and will
either bounce or refuse to start when run directly, and even for those that do start, going
around the client loses the overlay, Cloud saves and achievements.
"""

from __future__ import annotations

import glob
import logging
import os
import time
import winreg

import vdf

from shared import naming
from shared import rules
from shared.models import GameEntry
from providers import steam_art
from web import steam_web

log = logging.getLogger(__name__)

SOURCE = "steam"
HIVES = {"HKCU": winreg.HKEY_CURRENT_USER, "HKLM": winreg.HKEY_LOCAL_MACHINE}


class SteamProvider:
    name = SOURCE

    def __init__(self, allow_network: bool = False, cache_dir: str = "") -> None:
        self.steam_path = find_steam()
        self.library_roots: list[str] = []
        self.allow_network = allow_network
        self.cache_dir = cache_dir

    def is_available(self) -> bool:
        return self.steam_path is not None

    def exclusion_hints(self) -> list[str]:
        """Library roots, so the folder scanner never walks steamapps\\common."""
        return list(self.library_roots)

    def discover(self) -> list[GameEntry]:
        started = time.perf_counter()
        if self.steam_path is None:
            log.info("steam: not installed here")
            return []

        self.library_roots = library_paths(self.steam_path)
        cache_dir = os.path.join(self.steam_path, "appcache", "librarycache")
        legacy_index = steam_art.build_legacy_index(cache_dir)

        entries: list[GameEntry] = []
        skipped: dict[str, int] = {}
        manifest_count = 0

        for library in self.library_roots:
            for path in sorted(glob.glob(os.path.join(library, "steamapps", "appmanifest_*.acf"))):
                manifest_count += 1
                entry, reason = self._read_manifest(path, library, cache_dir, legacy_index)
                if entry is not None:
                    entries.append(entry)
                elif reason:
                    skipped[reason] = skipped.get(reason, 0) + 1

        if self.allow_network and entries:
            # Local manifests cannot tell a game from a demo or a tool, and some games have
            # no artwork cached. Both come from the store endpoint; both are cached on disk,
            # so this is a no-op on a normal rescan. Never allowed to break discovery.
            try:
                steam_web.enrich(entries, self.cache_dir)
            except Exception as exc:
                log.exception("steam web enrichment failed, continuing without it: %s", exc)
        elif entries:
            log.info("steam: network lookups disabled; app types and missing art unavailable")

        log.info(
            "steam: %d entries from %d manifest(s) across %d librar(ies) in %.2fs; skipped %s",
            len(entries),
            manifest_count,
            len(self.library_roots),
            time.perf_counter() - started,
            skipped or "nothing",
        )
        return entries

    def _read_manifest(
        self, path: str, library: str, cache_dir: str, legacy_index: dict[str, list[str]]
    ) -> tuple[GameEntry | None, str]:
        state = _load_app_state(path)
        if state is None:
            return None, "unreadable manifest"

        appid = str(_get(state, "appid") or "").strip()
        name = naming.sanitize_title(str(_get(state, "name") or "")) or f"Steam app {appid}"
        installdir = str(_get(state, "installdir") or "").strip()
        if not appid or not installdir:
            log.warning("manifest %s has no appid or installdir; skipping", path)
            return None, "incomplete manifest"

        reason = skip_reason(appid, name, installdir)
        if reason:
            log.info("skipping %s (appid %s): %s", name, appid, reason)
            return None, reason

        flags = _as_int(_get(state, "StateFlags"))
        if not flags & rules.STEAM_STATE_FULLY_INSTALLED:
            log.info("skipping %s (appid %s): StateFlags=%d, not fully installed", name, appid, flags)
            return None, "not fully installed"

        install_dir = os.path.join(library, "steamapps", "common", installdir)
        if not os.path.isdir(install_dir):
            log.warning("%s claims %s but it is not there; skipping", name, install_dir)
            return None, "install directory missing"

        artwork = steam_art.find_artwork(cache_dir, appid, legacy_index)
        banner = steam_art.find_banner(cache_dir, appid, legacy_index)
        return (
            GameEntry(
                source=SOURCE,
                source_id=appid,
                display_name=name,
                install_dir=install_dir,
                launch_kind="uri",
                launch_target=f"steam://rungameid/{appid}",
                working_dir=install_dir,
                icon_hint=artwork or os.path.join(self.steam_path or "", "steam.exe"),
                size_on_disk=_as_int(_get(state, "SizeOnDisk")),
                detection="manifest",
                extra={
                    "appid": appid,
                    "library": library,
                    "installdir": installdir,
                    "state_flags": flags,
                    "last_updated_unix": _as_int(_get(state, "LastUpdated")),
                    # Steam's own record of when this was last played. Used as a fallback
                    # on the tile so a game played outside this launcher is not shown as
                    # "never".
                    "last_played_unix": _as_int(_get(state, "LastPlayed")),
                    "artwork": artwork,
                    "banner": banner,
                    "manifest": path,
                },
            ),
            "",
        )


# -- locating steam ------------------------------------------------------------------------


def find_steam() -> str | None:
    for hive_name, subkey, value_name in rules.STEAM_REGISTRY_LOCATIONS:
        raw = _read_registry(hive_name, subkey, value_name)
        if not raw:
            continue
        # HKCU stores a lowercase forward-slash path; normalise before anything touches it.
        path = os.path.normpath(raw.replace("/", "\\"))
        if os.path.isdir(path):
            log.info("steam found at %s (via %s\\%s)", path, hive_name, subkey)
            return path
        log.warning("%s\\%s points at %s, which does not exist", hive_name, subkey, path)
    log.info("steam not found in the registry")
    return None


def _read_registry(hive_name: str, subkey: str, value_name: str) -> str | None:
    try:
        with winreg.OpenKey(HIVES[hive_name], subkey) as key:
            value, _ = winreg.QueryValueEx(key, value_name)
    except FileNotFoundError:
        log.debug("registry key absent: %s\\%s", hive_name, subkey)
        return None
    except OSError as exc:
        log.warning("could not read %s\\%s\\%s: %s", hive_name, subkey, value_name, exc)
        return None
    return value if isinstance(value, str) else None


def library_paths(steam_path: str) -> list[str]:
    """Every library folder, including ones on other drives. Never assumes C:."""
    found = [steam_path]
    manifest = os.path.join(steam_path, "steamapps", "libraryfolders.vdf")
    if not os.path.isfile(manifest):
        log.warning("no libraryfolders.vdf at %s; using the Steam folder alone", manifest)
        return found

    data = _load_vdf(manifest)
    if data is None:
        return found

    root = _get(data, "libraryfolders") or {}
    if not isinstance(root, dict):
        log.error("libraryfolders.vdf has an unexpected shape: %r", type(root))
        return found

    for key, value in root.items():
        if not str(key).isdigit():
            continue  # TimeNextStatsReport and friends
        path = _get(value, "path") if isinstance(value, dict) else value
        if not isinstance(path, str) or not path.strip():
            continue
        candidate = os.path.normpath(path.replace("/", "\\"))
        if os.path.isdir(candidate):
            found.append(candidate)
        else:
            log.warning("library %s listed but not present; skipping", candidate)

    unique: list[str] = []
    seen: set[str] = set()
    for path in found:
        key = os.path.normcase(path)
        if key not in seen:
            seen.add(key)
            unique.append(path)
    log.info("steam libraries: %s", unique)
    return unique


# -- skip rules ------------------------------------------------------------------------------


def skip_reason(appid: str, name: str, installdir: str) -> str:
    if appid in rules.STEAM_SKIP_APPIDS:
        return f"appid {appid} is on the skip list"
    if installdir.casefold() in rules.STEAM_SKIP_INSTALLDIRS:
        return f"installdir {installdir!r} is shared tooling, not a game"
    lowered = name.casefold().strip()
    if lowered in rules.STEAM_SKIP_NAMES_EXACT:
        return f"{name!r} is a runtime, not a game"
    for prefix in rules.STEAM_SKIP_NAME_PREFIXES:
        if lowered.startswith(prefix):
            return f"{name!r} is a runtime, not a game"
    return ""


# -- vdf helpers -------------------------------------------------------------------------------


def _load_vdf(path: str):
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return vdf.load(handle)
    except OSError as exc:
        log.error("could not open %s: %s", path, exc)
    except Exception as exc:  # the vdf package raises SyntaxError and ValueError variants
        log.error("could not parse %s: %s: %s", path, type(exc).__name__, exc)
    return None


def _load_app_state(path: str):
    data = _load_vdf(path)
    if data is None:
        return None
    state = _get(data, "AppState")
    if not isinstance(state, dict):
        log.error("%s has no AppState block", path)
        return None
    return state


def _get(mapping, name: str):
    """Case-insensitive lookup; ACF key casing has drifted between client versions."""
    if not isinstance(mapping, dict):
        return None
    if name in mapping:
        return mapping[name]
    folded = name.casefold()
    for key, value in mapping.items():
        if str(key).casefold() == folded:
            return value
    return None


def _as_int(value) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return 0
