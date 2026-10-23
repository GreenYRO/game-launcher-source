"""Runs discovery off the GUI thread.

Scanning stats tens of thousands of files; doing it on the GUI thread freezes the window
for the duration. The worker reports the directory it is in so the status bar can show
something moving.

Since Phase 73 a window's scan also asks the store for the prices that are due: the window
hands the list over as an argument, the worker writes what the store answered to a file in
cache/, and the window puts it into the database once the scan is back. Since Phase 75 it also
reads Steam's own playtime files, and fetches the records the window asked for, the same way;
since Phase 86, the wishlists of the accounts the window names.
Nothing here touches the database.
"""

from __future__ import annotations

import logging
import time

from PySide6.QtCore import QThread, Signal

from logic import discovery
from logic import prices
from logic import steam_time
from logic import wishlist

log = logging.getLogger(__name__)

PROGRESS_INTERVAL_SECONDS = 0.05  # a repaint per directory would be its own slowdown


class ScanWorker(QThread):
    progress = Signal(str)
    scanned = Signal(object)  # list[GameEntry]
    failed = Signal(str)

    def __init__(self, config: dict, parent=None, prices_due: list[int] | None = None,
                 read_steam: bool = False, steam_records: list[int] | None = None,
                 wishlists: list[dict] | None = None) -> None:
        super().__init__(parent)
        self.config = config
        self.prices_due = list(prices_due or [])  # Phase 73: apps whose price is due, oldest first
        self.read_steam = read_steam  # Phase 75: read Steam's own playtime files with this scan
        self.steam_records = list(steam_records or [])  # Phase 75: records wanted, most played first
        self.wishlists = list(wishlists or [])  # Phase 86: the accounts whose wishlist is due
        self._last_emit = 0.0

    def run(self) -> None:
        started = time.perf_counter()
        try:
            entries = discovery.run_discovery(self.config, progress=self._on_directory)
        except Exception as exc:
            log.exception("scan thread failed: %s", exc)
            self.failed.emit(str(exc))
            return
        log.info("scan finished: %d entries in %.2fs", len(entries), time.perf_counter() - started)
        if self.prices_due:
            prices.observe(self.prices_due)  # never raises: a price must not cost the scan
        if self.read_steam:
            steam_time.read(self.steam_records)  # never raises, either
        if self.wishlists:
            wishlist.read(self.wishlists)  # nor this
        self.scanned.emit(entries)

    def _on_directory(self, directory: str) -> None:
        now = time.perf_counter()
        if now - self._last_emit < PROGRESS_INTERVAL_SECONDS:
            return
        self._last_emit = now
        self.progress.emit(directory)
