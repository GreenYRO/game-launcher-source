"""Finds games by looking at folders on disk, with no launcher or manifest to help.

One game is one top-level subfolder of a configured root, or one loose exe sitting directly
in a root. Deciding which exe inside a folder is the game lives in detect.py; this module
walks the roots and turns each decision into a GameEntry.
"""

from __future__ import annotations

import logging
import os
import time

from shared import drives
from shared import naming
from providers import peinfo
from shared import rules
from shared import walk
from shared.models import GameEntry, is_inside, normalize_path
from providers import detect

log = logging.getLogger(__name__)

SOURCE = "folders"


class FolderProvider:
    name = SOURCE

    def __init__(
        self,
        roots,
        *,
        max_depth: int = rules.MAX_DEPTH,
        exclusions=(),
        progress: walk.ProgressFn | None = None,
    ) -> None:
        self.roots = [os.path.abspath(r) for r in roots]
        self.max_depth = max_depth
        self.progress = progress
        # Prefix-based, not exact: an exclusion covers the whole tree beneath it, which is
        # what makes "exclude the Steam library root" keep us out of steamapps\common.
        self.exclusions = [str(e) for e in exclusions if str(e).strip()]
        # Folders that produced no entry, with the reason. Reported by the CLI so a
        # missing game is visible rather than silently absent.
        self.empty_folders: list[tuple[str, str]] = []
        # Windows' own folders this scan kept out of -- as game folders or as places to walk --
        # said once at its end (Phase 82). Discovery never hands over a whole drive, so this is
        # defence in depth: it holds for anything that ever does.
        self.kept_out: list[str] = []

    def is_available(self) -> bool:
        return any(os.path.isdir(root) for root in self.roots)

    def _excluded_by(self, path: str) -> str | None:
        return next((e for e in self.exclusions if is_inside(path, e)), None)

    def discover(self) -> list[GameEntry]:
        started = time.perf_counter()
        entries: list[GameEntry] = []
        self.empty_folders.clear()
        self.kept_out.clear()
        for root in self.roots:
            if not os.path.isdir(root):
                log.warning("root does not exist, skipping: %s", root)
                continue
            excluded_by = self._excluded_by(root)
            if excluded_by is not None:
                log.info("root %s sits inside excluded %s; skipping entirely", root, excluded_by)
                continue
            entries.extend(self._scan_root(root))
        if self.kept_out:
            log.info("kept out of %d Windows folder(s), never game folders: %s",
                     len(self.kept_out), ", ".join(self.kept_out))
        log.info(
            "%s: %d entries from %d root(s) in %.2fs",
            self.name,
            len(entries),
            len(self.roots),
            time.perf_counter() - started,
        )
        return entries

    # -- roots -------------------------------------------------------------------------

    def _scan_root(self, root: str) -> list[GameEntry]:
        started = time.perf_counter()
        directories, loose, report = walk.iter_top_level(root)
        if report.permission_errors or report.other_errors:
            log.warning("root %s: %s", root, report.summary())

        entries: list[GameEntry] = []
        for entry in directories:
            if drives.is_system_folder(entry.path):
                self.kept_out.append(entry.path)
                continue
            excluded_by = self._excluded_by(entry.path)
            if excluded_by is not None:
                log.info("excluded (inside %s): %s", excluded_by, entry.path)
                continue
            built = self._entry_for_folder(root, entry.path, entry.name)
            if built is not None:
                entries.append(built)

        for entry in loose:
            if entry.name.casefold().endswith(".exe"):
                built = self._entry_for_loose_exe(root, entry)
                if built is not None:
                    entries.append(built)

        log.info(
            "root %s: %d entries from %d folders in %.2fs",
            root,
            len(entries),
            len(directories),
            time.perf_counter() - started,
        )
        return entries

    # -- one game ----------------------------------------------------------------------

    def _entry_for_folder(self, root: str, game_dir: str, folder_name: str) -> GameEntry | None:
        try:
            files, report = walk.walk_tree(
                game_dir, max_depth=self.max_depth, progress=self.progress
            )
        except OSError as exc:
            log.error("walk failed for %s: %s", game_dir, exc)
            self.empty_folders.append((game_dir, f"could not be read: {exc}"))
            return None

        self.kept_out.extend(report.system_folders)
        selection = detect.select_target(game_dir, files)
        log.debug("%s -> %s [%s]", folder_name, selection.chosen, report.summary())

        if selection.chosen is None:
            skipped = dict(selection.skipped)
            why = (
                f"{report.files_seen} files, no exe left after filtering ({skipped})"
                if skipped
                else f"no exe found among {report.files_seen} files"
            )
            log.info("no launchable exe in %s (%s)", game_dir, why)
            self.empty_folders.append((game_dir, why))
            return None

        folder_clean = naming.clean_folder_name(folder_name)
        display, origin = naming.choose_display_name(
            selection.version.product_name, selection.version.file_description, folder_clean
        )
        chosen = selection.chosen

        return GameEntry(
            source=SOURCE,
            source_id=normalize_path(game_dir),
            display_name=display,
            install_dir=game_dir,
            launch_kind="exe",
            launch_target=chosen.path,
            working_dir=os.path.dirname(chosen.path),
            icon_hint=chosen.path,
            size_on_disk=report.total_size,
            detection=selection.detection,
            alternatives=detect.alternatives_for(selection, chosen.path),
            extra={
                "root": root,
                "folder_name": folder_name,
                "folder_name_clean": folder_clean,
                "name_origin": origin,
                "name_candidates": {
                    "pe_product": selection.version.product_name,
                    "pe_description": selection.version.file_description,
                    "folder": folder_clean,
                },
                "publisher": selection.version.company_name,
                "detection_detail": selection.detail,
                "engine_root": selection.effective_root,
                "exe_size": chosen.size,
                "files_seen": report.files_seen,
                "skipped_exes": dict(selection.skipped),
                "walk": report.summary(),
            },
        )

    def _entry_for_loose_exe(self, root: str, entry: os.DirEntry) -> GameEntry | None:
        glob = detect.skipped_exe_glob(entry.name)
        if glob is not None:
            log.info("loose exe %s skipped by rule %r", entry.path, glob)
            return None
        try:
            size = entry.stat(follow_symlinks=False).st_size
        except OSError as exc:
            log.warning("cannot stat loose exe %s: %s", entry.path, exc)
            return None

        stem = os.path.splitext(entry.name)[0]
        version = peinfo.read_version_info(entry.path, size)
        clean = naming.clean_folder_name(stem)
        display, origin = naming.choose_display_name(
            version.product_name, version.file_description, clean
        )
        # A loose exe has no folder of its own, so install_dir would collide with every
        # other loose exe in the same root; source_id carries the exe path instead.
        return GameEntry(
            source=SOURCE,
            source_id=normalize_path(entry.path),
            display_name=display,
            install_dir=root,
            launch_kind="exe",
            launch_target=entry.path,
            working_dir=root,
            icon_hint=entry.path,
            size_on_disk=size,
            detection="loose_exe",
            extra={
                "root": root,
                "folder_name": stem,
                "folder_name_clean": clean,
                "name_origin": origin,
                "publisher": version.company_name,
                "detection_detail": "single exe sitting directly in a root",
                "exe_size": size,
            },
        )
