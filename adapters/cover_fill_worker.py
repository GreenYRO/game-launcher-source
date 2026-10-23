"""Filling missing covers off the GUI thread (Phase 105).

The batch (logic/fill_covers.run) asks SteamGridDB about one game after another, paced; this runs it on a thread of
its own and hands each step to the GUI thread as a signal -- the window writes every cover found, as Find online
does, so the library is only ever written from the GUI thread. Cancel is requestInterruption: the game under way
finishes, and a wait for SteamGridDB ends at once. Stopped from the window's shutdown, as every worker here must be.
"""

from __future__ import annotations

import time

from PySide6.QtCore import QThread, Signal

from logic import fill_covers
from shared import rules


class CoverFillWorker(QThread):
    """Looks up (identity key, name) pairs in order; each landing emitted as it happens."""

    progress = Signal(int, str)  # index in the list, name
    found = Signal(str, str)  # identity key, local image path
    missed = Signal(str, str)  # identity key, why (fill_covers.UNMATCHED or NO_IMAGE)
    ended = Signal(object)  # the fill_covers.Outcome

    def __init__(self, games: list[tuple[str, str]], key: str, cache_dir: str, parent=None) -> None:
        super().__init__(parent)
        self.games = list(games)
        self.key = key
        self.cache_dir = cache_dir
        self.outcome: fill_covers.Outcome | None = None

    def run(self) -> None:
        self.outcome = fill_covers.run(
            self.games, self.key, self.cache_dir, pause=time.sleep, wait=self._wait,
            stopped=self.isInterruptionRequested, progress=self.progress.emit, found=self.found.emit,
            missed=self.missed.emit)
        self.ended.emit(self.outcome)

    def _wait(self, seconds: float) -> bool:
        """Wait out SteamGridDB's slow-down; False the moment Cancel is pressed."""
        end = time.monotonic() + seconds
        while (left := end - time.monotonic()) > 0:
            if self.isInterruptionRequested():
                return False
            time.sleep(min(left, rules.SGDB_WAIT_SLICE_SECONDS))
        return not self.isInterruptionRequested()
