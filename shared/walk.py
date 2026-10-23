"""Depth-limited directory walk that will not follow a junction into an infinite loop.

os.walk is not used: it cannot tell a directory junction from a real directory, and
C:\\Users\\All Users is a junction back onto ProgramData. Every entry is stat'ed without
following links and tested for FILE_ATTRIBUTE_REPARSE_POINT before we descend.
"""

from __future__ import annotations

import logging
import os
import stat as stat_module
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Iterable

from shared import drives
from shared import rules

log = logging.getLogger(__name__)

FILE_ATTRIBUTE_REPARSE_POINT = 0x400

ProgressFn = Callable[[str], None]


@dataclass
class FileHit:
    path: str
    name: str
    depth: int  # 1 == directly inside the walked root
    size: int


@dataclass
class WalkReport:
    dirs_visited: int = 0
    files_seen: int = 0
    total_size: int = 0
    skipped_dirs: Counter = field(default_factory=Counter)
    skipped_dir_samples: dict[str, str] = field(default_factory=dict)
    reparse_points: list[str] = field(default_factory=list)
    permission_errors: list[str] = field(default_factory=list)
    other_errors: list[str] = field(default_factory=list)
    depth_truncated: list[str] = field(default_factory=list)
    system_folders: list[str] = field(default_factory=list)  # Windows' own, never entered (Phase 82)

    def summary(self) -> str:
        parts = [f"{self.dirs_visited} dirs", f"{self.files_seen} files"]
        if self.skipped_dirs:
            skipped = ", ".join(f"{reason}={n}" for reason, n in self.skipped_dirs.most_common())
            parts.append(f"skipped[{skipped}]")
        if self.reparse_points:
            parts.append(f"reparse={len(self.reparse_points)}")
        if self.permission_errors:
            parts.append(f"denied={len(self.permission_errors)}")
        if self.depth_truncated:
            parts.append(f"too-deep={len(self.depth_truncated)}")
        if self.system_folders:
            parts.append(f"windows-folders={len(self.system_folders)}")
        if self.other_errors:
            parts.append(f"errors={len(self.other_errors)}")
        return " ".join(parts)


def directory_skip_reason(name: str, relative_path: str) -> str | None:
    """Why this directory should not be descended into, or None to descend."""
    if name.casefold() in rules.SKIP_DIR_NAMES:
        return f"name:{name.casefold()}"
    lowered = relative_path.casefold()
    for fragment in rules.SKIP_DIR_PATH_FRAGMENTS:
        if lowered == fragment or lowered.endswith("\\" + fragment):
            return f"path:{fragment}"
    return None


def walk_tree(
    root: str,
    *,
    max_depth: int = rules.MAX_DEPTH,
    progress: ProgressFn | None = None,
) -> tuple[list[FileHit], WalkReport]:
    """Collect every file under `root` down to `max_depth`, with a report of what was skipped."""
    report = WalkReport()
    files: list[FileHit] = []
    stack: list[tuple[str, int]] = [(root, 0)]

    while stack:
        current, depth = stack.pop()
        if progress is not None:
            progress(current)

        entries = _scandir(current, report)
        if entries is None:
            continue
        report.dirs_visited += 1

        for entry in entries:
            try:
                info = entry.stat(follow_symlinks=False)
            except OSError as exc:
                report.other_errors.append(f"{entry.path}: {exc}")
                log.debug("stat failed, ignoring entry %s: %s", entry.path, exc)
                continue

            if getattr(info, "st_file_attributes", 0) & FILE_ATTRIBUTE_REPARSE_POINT:
                report.reparse_points.append(entry.path)
                log.debug("not following reparse point: %s", entry.path)
                continue

            child_depth = depth + 1
            if stat_module.S_ISDIR(info.st_mode):
                # Windows' own folders are never walked, whatever the walk started from (Phase
                # 82) -- told by where they sit below the drive's root, so a game's own
                # Engine\Binaries\ThirdParty\Windows is walked as before.
                if drives.is_system_folder(entry.path):
                    report.system_folders.append(entry.path)
                    continue
                relative = os.path.relpath(entry.path, root)
                reason = directory_skip_reason(entry.name, relative)
                if reason is not None:
                    report.skipped_dirs[reason] += 1
                    report.skipped_dir_samples.setdefault(reason, entry.path)
                    continue
                if child_depth >= max_depth:
                    report.depth_truncated.append(entry.path)
                    continue
                stack.append((entry.path, child_depth))
            else:
                report.files_seen += 1
                report.total_size += info.st_size
                files.append(FileHit(entry.path, entry.name, child_depth, info.st_size))

    return files, report


def _scandir(path: str, report: WalkReport) -> list[os.DirEntry] | None:
    try:
        with os.scandir(path) as iterator:
            return list(iterator)
    except PermissionError as exc:
        report.permission_errors.append(f"{path}: {exc}")
        log.warning("permission denied, skipping directory %s: %s", path, exc)
    except OSError as exc:
        report.other_errors.append(f"{path}: {exc}")
        log.warning("cannot read directory %s: %s", path, exc)
    return None


def iter_top_level(root: str) -> tuple[list[os.DirEntry], list[os.DirEntry], WalkReport]:
    """Split a root's immediate children into (directories, loose files).

    One game is one top-level subfolder; a loose exe sitting in the root is its own game.
    """
    report = WalkReport()
    entries = _scandir(root, report) or []
    directories: list[os.DirEntry] = []
    loose: list[os.DirEntry] = []

    for entry in entries:
        try:
            info = entry.stat(follow_symlinks=False)
        except OSError as exc:
            report.other_errors.append(f"{entry.path}: {exc}")
            log.warning("cannot stat top-level entry %s: %s", entry.path, exc)
            continue
        if getattr(info, "st_file_attributes", 0) & FILE_ATTRIBUTE_REPARSE_POINT:
            report.reparse_points.append(entry.path)
            log.info("skipping top-level reparse point: %s", entry.path)
            continue
        if stat_module.S_ISDIR(info.st_mode):
            directories.append(entry)
        else:
            loose.append(entry)

    return directories, loose, report


def total_size(files: Iterable[FileHit]) -> int:
    return sum(hit.size for hit in files)


def measure_size(path: str, max_depth: int = rules.MAX_DEPTH) -> int:
    """Bytes under a directory. For providers whose records carry no size of their own."""
    if not os.path.isdir(path):
        return 0
    _, report = walk_tree(path, max_depth=max_depth)
    return report.total_size


def fingerprint(path: str, max_depth: int = rules.WATCH_MEASURE_MAX_DEPTH) -> tuple[int, int, int] | None:
    """How many files, how many bytes, and the newest write time, under `path`.

    This decides whether an install has finished, so every file is asked directly with
    os.stat rather than read from the directory listing. Windows updates a directory
    entry's size lazily: a file still held open by the program writing it can read as the
    same size for as long as the writer keeps it open, and a large .pak being unpacked
    would look exactly like a finished install. os.stat on the path goes to the file.

    None if the path is gone. A loose file is measured on its own.
    """
    try:
        top = os.stat(path, follow_symlinks=False)
    except OSError as exc:
        log.debug("nothing to measure at %s: %s", path, exc)
        return None
    if not stat_module.S_ISDIR(top.st_mode):
        return 1, top.st_size, top.st_mtime_ns

    files = size = newest = 0
    stack: list[tuple[str, int]] = [(path, 0)]
    while stack:
        current, depth = stack.pop()
        try:
            with os.scandir(current) as iterator:
                entries = list(iterator)
        except OSError as exc:
            log.debug("cannot measure inside %s: %s", current, exc)
            continue
        for entry in entries:
            try:
                info = os.stat(entry.path, follow_symlinks=False)
            except OSError as exc:  # deleted or renamed between the listing and now
                log.debug("cannot measure %s: %s", entry.path, exc)
                continue
            if getattr(info, "st_file_attributes", 0) & FILE_ATTRIBUTE_REPARSE_POINT:
                continue
            if stat_module.S_ISDIR(info.st_mode):
                if depth + 1 < max_depth:
                    stack.append((entry.path, depth + 1))
                continue
            files += 1
            size += info.st_size
            newest = max(newest, info.st_mtime_ns)
    return files, size, newest
