"""The layer between the GUI and the providers.

The GUI asks this module for games and never touches a provider itself. Two things happen
here that deliberately do not happen inside any provider:

  * manifest providers run first, and the library roots they report are handed to the
    folder scanner as exclusions, so it never walks steamapps\\common at all; and
  * any folder-scanner entry that still lands inside a directory a manifest provider has
    claimed is dropped. A manifest knows what a game is; a folder scan is guessing.
"""

from __future__ import annotations

import logging
import time

from shared import drives
from shared import paths
from shared import rules
from shared.models import GameEntry, is_inside
from providers.epic import EpicProvider
from providers.folders import FolderProvider
from providers.gog import GogProvider
from providers.steam import SteamProvider
from web import steam_search
from providers.ubisoft import UbisoftProvider
from providers.xbox import XboxProvider
from shared.walk import ProgressFn

log = logging.getLogger(__name__)

# What the last name-resolution pass did, so the CLI and the GUI can report it in plain
# language. Diagnostics only -- nothing reads this to make a decision.
last_search_report: dict = {}


def manifest_providers(config: dict) -> list:
    """Providers backed by a launcher's own records. These win every dispute.

    Only Steam contributes scan exclusions: steamapps\\common is one well-defined tree, so
    excluding it wholesale is safe. The others install games to scattered locations, and a
    blanket exclusion could silently hide a folder the user actually wants scanned -- for
    those, the per-directory dedup below is enough.
    """
    steam = SteamProvider(
        allow_network=bool(config.get("allow_network", rules.ALLOW_NETWORK_DEFAULT)),
        cache_dir=str(paths.cache_dir()),
    )
    providers = [steam, GogProvider(), EpicProvider(), UbisoftProvider()]
    if config.get("enable_xbox", rules.XBOX_ENABLED_DEFAULT):
        providers.append(XboxProvider())
    else:
        log.info("xbox provider disabled (set \"enable_xbox\": true in config.json)")
    return providers


def run_discovery(
    config: dict,
    progress: ProgressFn | None = None,
    providers_out: list | None = None,
    folders_only: bool = False,
) -> list[GameEntry]:
    """Run everything and return the merged catalog.

    providers_out, if given, collects the provider instances used, so a caller can read
    per-provider diagnostics afterwards without discovery having to model them.
    """
    manifest_entries: list[GameEntry] = []
    hints: list[str] = []

    for provider in [] if folders_only else manifest_providers(config):
        if providers_out is not None:
            providers_out.append(provider)
        entries, provider_hints = _run_manifest(provider)
        manifest_entries.extend(entries)
        hints.extend(provider_hints)

    exclusions = list(config.get("exclusions", ())) + hints
    if hints:
        log.info("folder scanner will skip %d launcher-owned location(s)", len(hints))

    # A whole drive or one of Windows' own folders is never scanned (Phase 82): kept in
    # config.json until the user changes it -- the program never edits his list -- and said so,
    # here in the log and in the window. This, not a timer or a cap, is what bounds a scan.
    roots, refused = drives.split_roots(config.get("roots", rules.DEFAULT_ROOTS))
    for root, why in refused:
        log.warning("not scanned: %s (%s)", root, why)

    folders = FolderProvider(
        roots,
        max_depth=config.get("max_depth", rules.MAX_DEPTH),
        exclusions=exclusions,
        progress=progress,
    )
    if providers_out is not None:
        providers_out.append(folders)
    folder_entries = _safe_discover(folders)

    kept = deduplicate(folder_entries, manifest_entries)
    entries = manifest_entries + kept

    # Entries with no appid of their own (folder, GOG, Epic, Xbox) get one looked up by
    # name, which then feeds the same art and app-type pipeline Steam entries use. Runs
    # after dedup so nothing is looked up for an entry that is about to be dropped.
    if config.get("allow_network", rules.ALLOW_NETWORK_DEFAULT):
        try:
            last_search_report.clear()
            last_search_report.update(
                steam_search.resolve_missing(entries, str(paths.cache_dir()))
            )
        except Exception as exc:
            log.exception("name resolution failed, continuing without it: %s", exc)
    else:
        log.info("network lookups disabled; entries without an appid keep generated covers")

    entries.sort(key=lambda e: e.display_name.casefold())
    log.info("discovery produced %d entries", len(entries))
    return entries


def deduplicate(
    folder_entries: list[GameEntry], manifest_entries: list[GameEntry]
) -> list[GameEntry]:
    """Drop folder entries sitting inside a directory a manifest provider already claims."""
    claims = [(entry.install_dir, entry) for entry in manifest_entries if entry.install_dir]
    if not claims:
        return folder_entries

    kept: list[GameEntry] = []
    for entry in folder_entries:
        owner = next((c for path, c in claims if is_inside(entry.install_dir, path)), None)
        if owner is None:
            kept.append(entry)
        else:
            log.info(
                "dropping folder entry %r (%s): already claimed by %s as %r",
                entry.display_name,
                entry.install_dir,
                owner.source,
                owner.display_name,
            )
    return kept


def _run_manifest(provider) -> tuple[list[GameEntry], list[str]]:
    started = time.perf_counter()
    if not provider.is_available():
        log.info("provider %s is not available here; skipping", provider.name)
        return [], []

    entries = _safe_discover(provider)
    log.info(
        "provider %s contributed %d entries in %.2fs",
        provider.name,
        len(entries),
        time.perf_counter() - started,
    )

    hints: list[str] = []
    getter = getattr(provider, "exclusion_hints", None)
    if callable(getter):
        try:
            hints = list(getter())
        except Exception as exc:
            log.exception("provider %s failed to report exclusions: %s", provider.name, exc)
    return entries, hints


def _safe_discover(provider) -> list[GameEntry]:
    """A provider must never take the whole scan down with it."""
    try:
        return provider.discover()
    except Exception as exc:
        log.exception("provider %s raised, which it must not: %s", provider.name, exc)
        return []
