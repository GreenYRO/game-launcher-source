"""Notice a game arriving in a scan root while the launcher is open, and say when to scan.

The scan that runs when the launcher opens (Phase 14) already finds anything installed
while it was closed. This covers the other half: installing a game with the window open.

Three decisions, each made for a reason:

* **Only the top level of each root is watched.** One game is one top-level folder, or a
  loose exe, so a new name there is the whole signal. Watching every file inside every
  game would fire each time a running game wrote a line to its log.
* **A new folder is not scanned the moment it appears.** An installer creates the folder
  first and then fills it for minutes. So it is measured every WATCH_SETTLE_POLL_MS, off
  the GUI thread, and a scan is asked for only once WATCH_SETTLE_CHECKS measurements in a
  row have found nothing changed. walk.fingerprint explains why it stats every file.
* **It keeps an eye on it afterwards.** Installers pause, so a folder that has settled is
  still measured for WATCH_FOLLOW_UP_S and reported again if it changes and settles again.

A removal needs no settling -- a folder that is gone is gone -- and is reported at once.

This module only ever asks. Whether a scan runs now, or waits for one already running or
for a game to close, is the window's decision.
"""

from __future__ import annotations

import logging
import os
import stat as stat_module
import time
from dataclasses import dataclass

from PySide6.QtCore import QFileSystemWatcher, QObject, QThread, QTimer, Signal

from shared import rules
from shared import walk

log = logging.getLogger(__name__)


def top_level(root: str) -> set[str]:
    """The names in a root that could be a game: folders, and loose exes.

    The same view of a root the scanner takes, so a download landing beside the games --
    an archive still arriving, a text file -- is never waited on.
    """
    names: set[str] = set()
    try:
        with os.scandir(root) as iterator:
            for entry in iterator:
                try:
                    info = entry.stat(follow_symlinks=False)
                except OSError as exc:
                    log.debug("cannot stat %s: %s", entry.path, exc)
                    continue
                if getattr(info, "st_file_attributes", 0) & walk.FILE_ATTRIBUTE_REPARSE_POINT:
                    continue
                if stat_module.S_ISDIR(info.st_mode) or entry.name.casefold().endswith(".exe"):
                    names.add(entry.name)
    except OSError as exc:
        log.warning("cannot list %s: %s", root, exc)
    return names


def _key(path: str) -> str:
    return os.path.normcase(os.path.normpath(path))


@dataclass
class _Arrival:
    """One new top-level entry, being measured until it stops changing."""

    since: float  # when it appeared, or last changed after settling (monotonic)
    fingerprint: tuple | None = None
    quiet: int = 0  # measurements in a row that found nothing changed
    settled_at: float | None = None  # None while still waiting for it to settle


class _MeasureWorker(QThread):
    """Measures folders off the GUI thread: a large install can take a second to walk.

    One instance, restarted for each round. A new QThread per round would leave one
    finished thread object behind every twenty seconds for as long as an install runs.
    """

    measured = Signal(object)  # dict[str, tuple | None]

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.targets: list[str] = []

    def run(self) -> None:
        results = {}
        for target in self.targets:
            if self.isInterruptionRequested():
                return
            results[target] = walk.fingerprint(target)
        self.measured.emit(results)


class FolderWatcher(QObject):
    scanWanted = Signal(str)  # why, in words, for the log

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._system = QFileSystemWatcher(self)
        self._system.directoryChanged.connect(self._on_changed)
        self._roots: dict[str, str] = {}  # key -> the root as configured
        self._listings: dict[str, set[str]] = {}
        self._arrivals: dict[str, _Arrival] = {}
        self._dirty: set[str] = set()

        self._worker = _MeasureWorker(self)
        self._worker.measured.connect(self._on_measured)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(rules.WATCH_DEBOUNCE_MS)
        self._debounce.timeout.connect(self._relist)

        self._tick = QTimer(self)
        self._tick.setInterval(rules.WATCH_SETTLE_POLL_MS)
        self._tick.timeout.connect(self._measure)

    @property
    def roots(self) -> list[str]:
        return list(self._roots.values())

    @property
    def arrivals(self) -> list[str]:
        """New entries still being measured, settled or not."""
        return list(self._arrivals)

    # -- switching on and off ------------------------------------------------------------

    def watch(self, roots) -> None:
        """Watch exactly these roots from now on. An empty list switches watching off.

        Calling it again with the roots it already has changes nothing, so saving Settings
        does not forget a game that is half way through installing.
        """
        wanted: dict[str, str] = {}
        for root in roots or ():
            if not root:
                continue
            if os.path.isdir(root):
                wanted[_key(root)] = os.path.normpath(root)
            else:
                log.info("not watching %s: it does not exist", root)
        if wanted.keys() == self._roots.keys():
            return

        for key in set(self._roots) - set(wanted):
            self._system.removePath(self._roots.pop(key))
            self._listings.pop(key, None)
            for path in [p for p in self._arrivals if _key(os.path.dirname(p)) == key]:
                del self._arrivals[path]
        for key, root in wanted.items():
            if key in self._roots:
                continue
            if not self._system.addPath(root):
                log.warning("could not watch %s for new games", root)
                continue
            self._roots[key] = root
            self._listings[key] = top_level(root)

        if self._roots:
            log.info("watching for new games in %s", ", ".join(self._roots.values()))
        else:
            log.info("not watching any folder for new games")
        if not self._arrivals:
            self._tick.stop()

    def stop(self) -> None:
        """For closing: nothing may still be walking a folder when the window goes."""
        self._debounce.stop()
        self._tick.stop()
        for root in self._roots.values():
            self._system.removePath(root)
        self._roots.clear()
        self._listings.clear()
        self._arrivals.clear()
        if self._worker.isRunning():
            self._worker.requestInterruption()
            self._worker.wait(5000)

    # -- the top level of a root changed ---------------------------------------------------

    def _on_changed(self, path: str) -> None:
        self._dirty.add(_key(path))
        self._debounce.start()

    def _relist(self) -> None:
        removed = []
        added = False
        for key in list(self._dirty):
            root = self._roots.get(key)
            if root is None:
                continue
            now = top_level(root)
            before = self._listings.get(key, set())
            for name in sorted(now - before):
                log.info("new in %s: %s -- waiting for it to finish arriving", root, name)
                self._arrivals[os.path.join(root, name)] = _Arrival(since=time.monotonic())
                added = True
            for name in sorted(before - now):
                log.info("gone from %s: %s", root, name)
                self._arrivals.pop(os.path.join(root, name), None)
                removed.append(name)
            self._listings[key] = now
        self._dirty.clear()

        if removed:
            self.scanWanted.emit("removed: " + ", ".join(removed))
        if added:
            self._measure()  # a first measurement now, so the wait starts from here
            self._tick.start()

    # -- measuring what arrived -------------------------------------------------------------

    def _measure(self) -> None:
        now = time.monotonic()
        for path, arrival in list(self._arrivals.items()):
            if arrival.settled_at is not None and now - arrival.settled_at > rules.WATCH_FOLLOW_UP_S:
                del self._arrivals[path]
        if not self._arrivals:
            self._tick.stop()
            return
        if self._worker.isRunning():
            return  # the last round is still walking; the next tick picks this up
        self._worker.targets = list(self._arrivals)
        self._worker.start()

    def _on_measured(self, results: dict) -> None:
        now = time.monotonic()
        settled = []
        for path, measured in results.items():
            arrival = self._arrivals.get(path)
            if arrival is None:
                continue  # removed while it was being measured
            if measured is None:
                del self._arrivals[path]  # gone; the listing reports the removal
                continue

            if measured != arrival.fingerprint:
                if arrival.settled_at is not None:
                    log.info("%s changed again after settling; waiting for it again", path)
                    arrival.settled_at = None
                    arrival.since = now
                arrival.fingerprint = measured
                arrival.quiet = 0
            elif arrival.settled_at is None:
                arrival.quiet += 1

            if arrival.settled_at is not None:
                continue  # following up, and still unchanged
            if arrival.quiet >= rules.WATCH_SETTLE_CHECKS:
                arrival.settled_at = now
                settled.append(path)
            elif now - arrival.since > rules.WATCH_GIVE_UP_S:
                log.info(
                    "%s is still changing after %d minutes; scanning it anyway",
                    path, (now - arrival.since) // 60,
                )
                del self._arrivals[path]
                settled.append(path)

        if settled:
            self.scanWanted.emit(
                "finished arriving: " + ", ".join(os.path.basename(p) for p in settled)
            )
