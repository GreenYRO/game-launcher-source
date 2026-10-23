"""The update check off the GUI thread (Phase 79): a window must never wait on GitHub.

Like every other worker, it is stopped from the window's closeEvent: Qt aborts the process if
a QThread is still running when its owner is destroyed.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QThread, Signal

log = logging.getLogger(__name__)


class UpdateWorker(QThread):
    answered = Signal(object, bool)  # web.updates.Answer or None, asked GitHub just now

    def __init__(self, cache_dir: str, parent=None) -> None:
        super().__init__(parent)
        self.cache_dir = cache_dir

    def run(self) -> None:
        from web import updates

        answer, asked = updates.check(self.cache_dir)
        if self.isInterruptionRequested():
            log.debug("update check interrupted; dropping the answer")
            return
        self.answered.emit(answer, asked)
