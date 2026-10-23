"""The look at the process list, every few seconds, off the GUI thread (Phase 93).

A thread of its own, like save_worker.py: each look (logic/observe.processes, about 3 ms) is matched
against the watched games the window hands it -- replaced after every reload -- and the keys of the
games seen running go to the window as a signal, with the moment of the look. The window owns the
sessions and writes them (the one writer); this only looks.

The processes that refuse to be asked (Windows' services and system parts) are counted and named
in the log once per run of the launcher, and again only for a name not seen before -- never
guessed at. A look slower than rules.WATCH_ENUMERATION_MAX_MS is said once -- never the first, which
runs cold (94 ms once on 18 October, against about 3 ms for every look after it).
"""

from __future__ import annotations

import logging
import threading
import time

from PySide6.QtCore import QThread, Signal

from logic import observe
from shared import rules

log = logging.getLogger(__name__)


class ProcessWorker(QThread):
    seen = Signal(list, float)  # the keys of the games seen running, time.monotonic() of the look

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._lock = threading.Lock()
        self._games: tuple = ()
        self._refused_pids: set[int] = set()
        self._refused_names: set[str] = set()
        self._slow_said = False
        self._looks = 0

    def set_games(self, games) -> None:
        """The watched games (observe.Watched), replaced whole; the next look uses them."""
        with self._lock:
            self._games = tuple(games)

    def run(self) -> None:
        log.info("process watch: a look every %d s for games started outside the launcher",
                 rules.WATCH_PROCESS_POLL_S)
        while not self.isInterruptionRequested():
            began = time.monotonic()
            paths, refused = observe.processes()
            took = (time.monotonic() - began) * 1000
            self._looks += 1
            # Not the first look: everything is cold then (94 ms once, against about 3 ms after).
            if took > rules.WATCH_ENUMERATION_MAX_MS and self._looks > 1 and not self._slow_said:
                self._slow_said = True
                log.warning("process watch: one look took %.0f ms (expected under %d)", took,
                            rules.WATCH_ENUMERATION_MAX_MS)
            self._say_refused(refused)
            with self._lock:
                games = self._games
            self.seen.emit(sorted(observe.owners(paths, games)), time.monotonic())
            wake = began + rules.WATCH_PROCESS_POLL_S
            while not self.isInterruptionRequested() and time.monotonic() < wake:
                self.msleep(100)
        log.info("process watch: stopped")

    def _say_refused(self, refused: set[int]) -> None:
        fresh = refused - self._refused_pids
        if not fresh:
            return
        first = not self._refused_pids
        self._refused_pids |= fresh
        new_names = set(observe.names(fresh).values()) - self._refused_names
        self._refused_names |= new_names
        if first:
            log.info("process watch: %d process(es) refuse to be asked their path, so a game among them "
                     "could not be seen: %s", len(refused), ", ".join(sorted(new_names)))
        elif new_names:
            log.info("process watch: another process refuses to be asked: %s", ", ".join(sorted(new_names)))
