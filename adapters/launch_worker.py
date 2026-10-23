"""A game's start off the GUI thread (Phase 99).

Windows' start call can take seconds -- 13.1 s for Hellraiser's first start, measured in launcher.log (the
system checking a program it had not seen), 0-4.4 s for the rest -- and the window could not paint while it
waited: the launcher looked frozen. `LaunchWorker` runs logic.launch's start on a thread of its own; the
window waits for it in a local event loop (`MainWindow.run_launch`), so it keeps painting the splash and
answering Escape and the pad meanwhile, and the caller still gets its result back as before.

Only a start from a program file: a store's address (Steam, Epic, Xbox) is handed over at once.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QThread

log = logging.getLogger(__name__)


class LaunchWorker(QThread):
    """Runs `start()` once and keeps what it returned (`result`) -- or what it raised (`error`), logged."""

    def __init__(self, start, parent=None) -> None:
        super().__init__(parent)
        self._start = start
        self.result = None
        self.error: BaseException | None = None

    def run(self) -> None:
        try:
            self.result = self._start()
        except Exception as exc:  # noqa: BLE001 -- a start that raises is reported, never lost on the thread
            log.exception("the game's start raised on its thread")
            self.error = exc
