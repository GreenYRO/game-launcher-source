"""Finding a game's cover art in Steam's local artwork cache.

The cache layout has changed across client versions. This install uses per-appid folders
(appcache\\librarycache\\730\\library_600x900.jpg); older clients kept flat files named
appcache\\librarycache\\730_library_600x900.jpg. Both are searched, and neither filename
is required to exist -- if nothing recognisable is there, the largest real image wins, and
if there is no real image at all the caller falls back to a placeholder.

The flat form is matched on "<appid>_" and never "<appid>*": a bare prefix glob for appid
550 also matches 550140, 550650 and 550900, which are different games entirely.
"""

from __future__ import annotations

import logging
import os

from shared import rules

log = logging.getLogger(__name__)


def build_legacy_index(cache_dir: str) -> dict[str, list[str]]:
    """Map appid -> flat artwork files, scanning the cache directory once."""
    index: dict[str, list[str]] = {}
    if not os.path.isdir(cache_dir):
        return index
    try:
        entries = list(os.scandir(cache_dir))
    except OSError as exc:
        log.warning("cannot read artwork cache %s: %s", cache_dir, exc)
        return index

    for entry in entries:
        try:
            if not entry.is_file(follow_symlinks=False):
                continue
        except OSError as exc:
            log.debug("cannot stat %s: %s", entry.path, exc)
            continue
        appid, separator, _ = entry.name.partition("_")
        if separator and appid.isdigit():
            index.setdefault(appid, []).append(entry.path)
    return index


def find_artwork(cache_dir: str, appid: str, legacy_index: dict[str, list[str]]) -> str | None:
    """Best available cover image for this appid, or None."""
    return _pick(_candidates(cache_dir, appid, legacy_index), appid, rules.STEAM_ARTWORK_NAMES)


def find_banner(cache_dir: str, appid: str, legacy_index: dict[str, list[str]]) -> str | None:
    """Best available wide banner for this appid, or None.

    Uses a strict name list rather than "anything with hero in it": the client also caches
    library_hero_blur.jpg, a ~2 KB smudge that is not artwork.
    """
    usable = _usable(_candidates(cache_dir, appid, legacy_index))
    for preferred in rules.STEAM_BANNER_NAMES:
        for path, _ in usable:
            stem = os.path.splitext(os.path.basename(path))[0].casefold()
            if stem == preferred or stem.endswith("_" + preferred):
                return path
    return None


def _candidates(cache_dir: str, appid: str, legacy_index: dict[str, list[str]]) -> list[str]:
    candidates: list[str] = []
    folder = os.path.join(cache_dir, appid)
    if os.path.isdir(folder):
        try:
            candidates.extend(
                entry.path for entry in os.scandir(folder) if entry.is_file(follow_symlinks=False)
            )
        except OSError as exc:
            log.warning("cannot read artwork folder %s: %s", folder, exc)
    candidates.extend(legacy_index.get(appid, []))
    return candidates


def _usable(candidates: list[str]) -> list[tuple[str, int]]:
    usable: list[tuple[str, int]] = []
    for path in candidates:
        if os.path.splitext(path)[1].casefold() not in rules.STEAM_ARTWORK_EXTENSIONS:
            continue
        try:
            size = os.path.getsize(path)
        except OSError as exc:
            log.debug("cannot size %s: %s", path, exc)
            continue
        if size >= rules.STEAM_ARTWORK_MIN_BYTES:
            usable.append((path, size))
    return usable


def _pick(candidates: list[str], appid: str, names: tuple[str, ...]) -> str | None:
    usable = _usable(candidates)
    if not usable:
        log.debug("no usable artwork for appid %s among %d file(s)", appid, len(candidates))
        return None

    for preferred in names:
        for path, _ in usable:
            stem = os.path.splitext(os.path.basename(path))[0].casefold()
            if stem == preferred or stem.endswith("_" + preferred):
                return path

    largest = max(usable, key=lambda pair: pair[1])[0]
    log.debug("appid %s: no known artwork name, using largest image %s", appid, largest)
    return largest
