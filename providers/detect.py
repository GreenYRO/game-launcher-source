"""Choosing which exe inside a game folder is the one a human means by "play this".

Engine fingerprints run in priority order and are near-certain when they match; the score
in _score is only consulted when none of them do, and as a tiebreaker when several do.
"""

from __future__ import annotations

import logging
import math
import os
from collections import Counter
from dataclasses import dataclass, field
from fnmatch import fnmatchcase

from shared import naming
from providers import peinfo
from shared import rules
from shared import walk
from shared.models import Alternative

log = logging.getLogger(__name__)


@dataclass
class Selection:
    chosen: walk.FileHit | None = None
    detection: str = "none"
    detail: str = ""
    scores: dict[str, float] = field(default_factory=dict)
    reasons: dict[str, str] = field(default_factory=dict)
    version: peinfo.VersionInfo = peinfo.EMPTY
    skipped: Counter = field(default_factory=Counter)
    effective_root: str = ""


DETAIL = {
    "loader": "sits beside a Steam-emulation layer and must run before the game",
    "unreal_bootstrap": "Unreal's own launcher at the top of the game folder",
    "unity": "exe has a matching <name>_Data folder beside it",
    "unreal": "shipping build under Binaries\\Win64",
    "godot": "exe has a matching .pck beside it",
    "heuristic": "no engine fingerprint; picked by name, location, size and version resource",
}


def skipped_exe_glob(filename: str) -> str | None:
    """The skip rule this filename trips, or None if it is a real candidate."""
    lowered = filename.casefold()
    for pattern in rules.SKIP_EXE_GLOBS:
        if fnmatchcase(lowered, pattern):
            return pattern
    return None


def select_target(game_dir: str, files: list[walk.FileHit]) -> Selection:
    """Apply the engine fingerprints in priority order, then fall back to scoring."""
    selection = Selection(effective_root=effective_root(game_dir))
    candidates: list[walk.FileHit] = []

    for hit in files:
        if not hit.name.casefold().endswith(".exe"):
            continue
        glob = skipped_exe_glob(hit.name)
        if glob is not None:
            selection.skipped[glob] += 1
            continue
        if hit.size < rules.MIN_CANDIDATE_SIZE_BYTES:
            selection.skipped["<min-size>"] += 1
            continue
        candidates.append(hit)

    if not candidates:
        return selection

    candidates.sort(key=lambda h: h.size, reverse=True)
    versions = {
        hit.path: peinfo.read_version_info(hit.path, hit.size)
        for hit in candidates[: rules.MAX_PE_READS_PER_GAME]
    }
    folder_clean = naming.clean_folder_name(os.path.basename(game_dir))

    for hit in candidates:
        selection.scores[hit.path] = _score(
            hit, folder_clean, selection.effective_root, versions.get(hit.path)
        )

    detection, chosen, matches = _engine_choice(candidates, folder_clean, selection.scores)
    if chosen is None:
        return selection

    # Two overrides, in order of authority. Both exist because the engine binary is the
    # right file to identify the game and the wrong file to start it.
    #
    # 1. Unreal ships a small bootstrapper at the top of the game folder; it is the entry
    #    point the game's own Start menu shortcut uses, and anything layered over the game
    #    hooks at that level rather than at the shipping binary.
    if detection == "unreal":
        bootstrap = unreal_bootstrapper(
            selection.effective_root, candidates, chosen, versions, folder_clean
        )
        if bootstrap is not None and bootstrap.path != chosen.path:
            chosen, detection = bootstrap, "unreal_bootstrap"

    # 2. A loader beside a Steam-emulation layer. Starting the engine binary underneath it
    #    lets the game boot and then crash when it cannot reach Steam.
    loader = loader_at_root(selection.effective_root, candidates, folder_clean)
    if loader is not None and loader.path != chosen.path:
        chosen, detection = loader, "loader"

    selection.chosen = chosen
    selection.detection = detection
    selection.detail = DETAIL[detection]
    selection.version = versions.get(chosen.path, peinfo.EMPTY)
    for hit in candidates:
        if hit.path != chosen.path:
            selection.reasons[hit.path] = (
                f"not chosen by {detection} rule"
                if hit in matches
                else f"lower score than the {detection} match"
            )
    return selection


def _engine_choice(candidates, folder_clean, scores):
    """The engine fingerprints in priority order, then the fallback score."""
    for detection, matches in (
        ("unity", [h for h in candidates if is_unity(h)]),
        ("unreal", [h for h in candidates if is_unreal(h)]),
        ("godot", [h for h in candidates if is_godot(h)]),
        ("heuristic", candidates),
    ):
        if not matches:
            continue
        if detection == "unreal":
            # "If several, prefer the one whose prefix matches the game folder name."
            matches = sorted(
                matches,
                key=lambda h: naming.similarity(unreal_prefix(h.name), folder_clean),
                reverse=True,
            )
        return detection, _best(matches, scores), matches
    return "none", None, []


def alternatives_for(selection: Selection, chosen_path: str) -> list[Alternative]:
    """Every rejected candidate, best first, so an entry can be retargeted later."""
    others = [
        Alternative(path=path, score=score, reason=selection.reasons.get(path, "not chosen"))
        for path, score in selection.scores.items()
        if path != chosen_path
    ]
    others.sort(key=lambda a: a.score, reverse=True)
    return others[: rules.MAX_ALTERNATIVES]


def has_loader_markers(directory: str) -> bool:
    """Is there a Steam-emulation layer sitting in this directory?"""
    try:
        names = {entry.name.casefold(): entry for entry in os.scandir(directory)}
    except OSError as exc:
        log.debug("cannot inspect %s for loader markers: %s", directory, exc)
        return False

    for marker in rules.LOADER_MARKER_FILES:
        entry = names.get(marker)
        if entry is not None and entry.is_file(follow_symlinks=False):
            log.debug("loader marker %s in %s", marker, directory)
            return True
    for marker in rules.LOADER_MARKER_DIRS:
        entry = names.get(marker)
        if entry is not None and entry.is_dir(follow_symlinks=False):
            log.debug("loader marker dir %s in %s", marker, directory)
            return True
    return False


def at_root(effective_root: str, candidates: list[walk.FileHit]) -> list[walk.FileHit]:
    root = os.path.normcase(effective_root)
    return [h for h in candidates if os.path.normcase(os.path.dirname(h.path)) == root]


def loader_at_root(
    effective_root: str, candidates: list[walk.FileHit], folder_clean: str
) -> walk.FileHit | None:
    """The loader to run instead of a nested engine binary, if there is one.

    Picking the largest exe here would be wrong: a loader is usually the *smallest* file in
    the folder. Preference goes to one named after the game, then to the conventional
    launcher names, and only then to size.
    """
    if not rules.PREFER_LOADER_AT_ROOT or not effective_root:
        return None
    if not has_loader_markers(effective_root):
        return None

    roots = at_root(effective_root, candidates)
    if not roots:
        log.debug("loader markers in %s but no exe at that level", effective_root)
        return None

    named = [h for h in roots if naming.similarity(_stem(h), folder_clean) >= rules.LOADER_NAME_RATIO]
    if named:
        chosen = max(named, key=lambda h: naming.similarity(_stem(h), folder_clean))
    else:
        conventional = [h for h in roots if _stem(h).casefold() in rules.LOADER_EXE_NAMES]
        chosen = conventional[0] if conventional else max(roots, key=lambda h: h.size)

    log.info("loader layer present; preferring %s", chosen.path)
    return chosen


def unreal_bootstrapper(
    effective_root: str,
    candidates: list[walk.FileHit],
    shipping: walk.FileHit,
    versions: dict,
    folder_clean: str,
) -> walk.FileHit | None:
    """Unreal's small launcher at the top of the game folder, if it is there.

    Identified two ways, because neither alone covers the games on this machine: the stem
    matching the shipping binary's prefix (SHProto.exe -> SHProto-Win64-Shipping.exe), or a
    version resource that names it outright, which is how Khazan's KZ.exe is recognised
    despite shipping BBQ-Win64-Shipping.exe.
    """
    if not rules.PREFER_UNREAL_BOOTSTRAPPER or not effective_root:
        return None

    prefix = unreal_prefix(shipping.name).casefold()
    for hit in at_root(effective_root, candidates):
        stem = _stem(hit).casefold()
        version = versions.get(hit.path)
        product = (getattr(version, "product_name", "") or "").casefold()
        if (
            stem == prefix
            or product in rules.UNREAL_BOOTSTRAP_PRODUCT_NAMES
            or naming.similarity(stem, folder_clean) >= rules.LOADER_NAME_RATIO
        ):
            log.info("using Unreal bootstrapper %s instead of %s", hit.path, shipping.name)
            return hit
    return None


def _stem(hit: walk.FileHit) -> str:
    return os.path.splitext(hit.name)[0]


# -- engine fingerprints -----------------------------------------------------------------


def is_unity(hit: walk.FileHit) -> bool:
    stem = os.path.splitext(hit.name)[0]
    return os.path.isdir(os.path.join(os.path.dirname(hit.path), stem + "_Data"))


def is_unreal(hit: walk.FileHit) -> bool:
    if not hit.name.casefold().endswith(rules.UNREAL_SHIPPING_SUFFIX):
        return False
    parts = [p.casefold() for p in hit.path.split(os.sep)]
    if len(parts) < 3:
        return False
    return tuple(parts[-3:-1]) == rules.UNREAL_REQUIRED_PARENTS


def unreal_prefix(filename: str) -> str:
    return filename[: -len(rules.UNREAL_SHIPPING_SUFFIX)]


def is_godot(hit: walk.FileHit) -> bool:
    return os.path.isfile(os.path.splitext(hit.path)[0] + rules.GODOT_PACK_SUFFIX)


# -- fallback scoring --------------------------------------------------------------------


def _best(matches: list[walk.FileHit], scores: dict[str, float]) -> walk.FileHit:
    """Highest score wins; ties break on the shorter, alphabetically earlier name."""
    return sorted(
        matches, key=lambda h: (-scores.get(h.path, 0.0), len(h.name), h.name.casefold())
    )[0]


def _score(
    hit: walk.FileHit, folder_clean: str, root: str, version: peinfo.VersionInfo | None
) -> float:
    stem = os.path.splitext(hit.name)[0]
    score = rules.SCORE_NAME_SIMILARITY * naming.similarity(stem, folder_clean)
    score += rules.SCORE_DEPTH_BONUS / (1 + _depth_below(hit.path, root))

    megabytes = hit.size / (1024 * 1024)
    ceiling = math.log10(1 + rules.SCORE_SIZE_CEILING_MB)
    score += rules.SCORE_SIZE_MAX * min(1.0, math.log10(1 + megabytes) / ceiling)

    if version is not None and not version.is_empty:
        score += rules.SCORE_PE_PRESENT
        ratios = [
            naming.similarity(name, folder_clean)
            for name in (version.product_name, version.file_description)
            if name
        ]
        if ratios:
            score += rules.SCORE_PE_NAME_MATCH * max(ratios)
    return score


def _depth_below(path: str, root: str) -> int:
    try:
        return max(0, os.path.relpath(path, root).count(os.sep))
    except ValueError:  # different drives
        return 0


def effective_root(game_dir: str) -> str:
    """Descend through pointless single-subfolder wrappers common in packaged builds.

    "Cinderia.v0.6.10b\\Cinderia.v0.6.10b\\..." holds the real game one level down; without
    this, nothing would ever earn the "sits at the top of the game folder" bonus.
    """
    current = game_dir
    for _ in range(rules.WRAPPER_DESCENT_MAX):
        try:
            children = list(os.scandir(current))
        except OSError as exc:
            log.debug("cannot descend wrapper at %s: %s", current, exc)
            return current
        if len(children) == 1 and children[0].is_dir(follow_symlinks=False):
            current = children[0].path
            continue
        return current
    return current
