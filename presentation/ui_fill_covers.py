"""Fill missing covers (Phase 105): the games with no cover, by name, looked up on SteamGridDB in one go.

Opened from Settings' Missing covers row. "Look them up" takes a backup first (the undo: Settings' Restore...), then
runs the batch on its own thread (adapters/cover_fill_worker.py) -- one game at a time, each line marked as it is
answered; every cover found goes to the window (`host.cover_found`), which writes it as Find online does. A scan
under way is waited for. Cancel lets the game under way finish and stops; Escape and the close button do the same
while it runs, and close the dialog once it has ended. Styled like the first-run questions, worked by the pad as
every dialog.

`host` is the window: `scan_running()`, `fill_backup()` (the backup's name, or None when none could be taken),
`cover_found(identity_key, path)`, and `track_fill(worker)` so a Quit can stop it.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QPushButton, QVBoxLayout)

from adapters.cover_fill_worker import CoverFillWorker
from logic import fill_covers
from presentation import ui_rules
from presentation.ui_cards import FocusRing
from shared import paths

TITLE = "Fill missing covers"
TEXT = ("Each game below is looked up on SteamGridDB with your key, and the first tall cover of a close match is "
        "used — what Find online does for one game, without the choosing. A cover you set yourself is never "
        "replaced, and a backup is taken first.")
LOOK = "Look them up"
CANCEL = "Cancel"
CLOSE = "Close"
STOPPING = "Stopping..."
WAITING = "A scan is running; the lookup starts as soon as it ends."
NO_BACKUP = "No backup could be taken, so nothing was looked up."
UNDO = " A backup was taken first ({stamp}): Restore... under Your library data puts the library back as it was."
MARKS = {"found": "✓", "missed": "✕", "waiting": "·"}
WHY = {fill_covers.UNMATCHED: "no close match", fill_covers.NO_IMAGE: "no tall cover"}
SCAN_POLL_MS = 500


class FillCoversDialog(QDialog):
    """The list, Look them up, Cancel; the batch's progress and its last words."""

    def __init__(self, games: list[tuple[str, str]], key: str, host, scale: float, tv: bool = False,
                 parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("FirstRun")  # the first-run questions' ground and words
        self.setWindowTitle(TITLE)
        self.games = list(games)
        self.key = key
        self.host = host
        self.scale = scale
        self.tv = tv
        self.worker: CoverFillWorker | None = None
        self.outcome: fill_covers.Outcome | None = None
        self.backup = ""
        self._current = ""
        self._row = {game: index for index, (game, _name) in enumerate(self.games)}

        title = QLabel(TITLE)
        title.setObjectName("SettingsTitle")
        text = QLabel(TEXT)
        text.setObjectName("FirstRunText")
        text.setWordWrap(True)
        self.list = QListWidget()
        self.list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        for _game, name in self.games:
            self.list.addItem(QListWidgetItem(f"{MARKS['waiting']}  {name}"))
        self.status = QLabel(f"{len(self.games)} game{'s' if len(self.games) != 1 else ''} to look up.")
        self.status.setObjectName("FirstRunText")
        self.status.setWordWrap(True)

        self.cancel_button = QPushButton(CANCEL)
        self.look_button = QPushButton(LOOK)
        self.look_button.setDefault(True)
        self.look_button.setAutoDefault(True)
        self.cancel_button.setAutoDefault(False)
        for button in (self.cancel_button, self.look_button):
            button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_button.clicked.connect(self._cancel)
        self.look_button.clicked.connect(self.look)

        buttons = QHBoxLayout()
        buttons.addWidget(self.cancel_button)
        buttons.addStretch(1)
        buttons.addWidget(self.look_button)
        layout = QVBoxLayout(self)
        margin = max(12, round(24 * scale))
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.setSpacing(max(8, round(12 * scale)))
        for widget in (title, text, self.list, self.status):
            layout.addWidget(widget)
        layout.addSpacing(max(4, round(6 * scale)))
        layout.addLayout(buttons)
        self.setMinimumWidth(round(ui_rules.FILL_COVERS_WIDTH * scale))
        self.focus_ring = FocusRing(self, lambda widget: isinstance(widget, QPushButton), scale=lambda: self.scale)
        self._scan_poll = QTimer(self)
        self._scan_poll.setInterval(SCAN_POLL_MS)
        self._scan_poll.timeout.connect(self._after_scan)

    def showEvent(self, event) -> None:
        # The list as tall as its games, up to FILL_COVERS_LIST_ROWS, measured once styled: a row is as tall as
        # the stylesheet makes it, not a number guessed beforehand.
        self.list.ensurePolished()
        rows = max(1, min(len(self.games), ui_rules.FILL_COVERS_LIST_ROWS))
        row = max(1, self.list.sizeHintForRow(0))
        self.list.setFixedHeight(rows * row + 2 * self.list.frameWidth() + 2)
        super().showEvent(event)
        self.look_button.setFocus(Qt.FocusReason.OtherFocusReason)

    def running(self) -> bool:
        return self.worker is not None and self.worker.isRunning()

    # -- the batch ------------------------------------------------------------------------

    def look(self) -> None:
        """Look them up: after a scan under way, and only with a backup taken."""
        if self.running() or self.outcome is not None:
            return
        self.look_button.setEnabled(False)
        if self.host.scan_running():
            self.status.setText(WAITING)
            self._scan_poll.start()
            return
        self._start()

    def _after_scan(self) -> None:
        if not self.host.scan_running():
            self._scan_poll.stop()
            self._start()

    def _start(self) -> None:
        stamp = self.host.fill_backup()
        if not stamp:
            self.status.setText(NO_BACKUP)
            self.look_button.setEnabled(True)
            return
        self.backup = stamp
        self.worker = CoverFillWorker(self.games, self.key, str(paths.cache_dir()), self)
        self.worker.progress.connect(self._progress)
        self.worker.found.connect(self._found)
        self.worker.missed.connect(self._missed)
        self.worker.ended.connect(self._ended)
        self.host.track_fill(self.worker)
        self.look_button.hide()
        self.cancel_button.setFocus(Qt.FocusReason.OtherFocusReason)
        self.worker.start()

    def _mark(self, game: str, mark: str, why: str = "") -> None:
        index = self._row.get(game)
        if index is None:
            return
        name = self.games[index][1]
        self.list.item(index).setText(f"{MARKS[mark]}  {name}" + (f" — {why}" if why else ""))

    def _progress(self, index: int, name: str) -> None:
        self._current = name
        if self.cancel_button.text() != STOPPING:
            self.status.setText(f"Looking up {index + 1} of {len(self.games)}: {name}...")
        self.list.scrollToItem(self.list.item(index))

    def _found(self, game: str, path: str) -> None:
        self.host.cover_found(game, path)
        self._mark(game, "found")

    def _missed(self, game: str, why: str) -> None:
        self._mark(game, "missed", WHY.get(why, why))

    def _ended(self, outcome) -> None:
        self.outcome = outcome
        words = fill_covers.summary(outcome)
        if outcome.found and self.backup:
            words += UNDO.format(stamp=self.backup)
        self.status.setText(words)
        self.cancel_button.setText(CLOSE)
        self.cancel_button.setEnabled(True)
        self.cancel_button.setFocus(Qt.FocusReason.OtherFocusReason)

    # -- leaving --------------------------------------------------------------------------

    def _cancel(self) -> None:
        """Cancel: while it runs, the game under way finishes and the batch stops; otherwise, close."""
        if self.running():
            self.worker.requestInterruption()
            self.cancel_button.setText(STOPPING)
            self.cancel_button.setEnabled(False)
            self.status.setText(f"Stopping after {self._current}..." if self._current else STOPPING)
            return
        self._scan_poll.stop()
        super().reject()

    def reject(self) -> None:
        """Escape and the close button: Cancel's meaning -- never a dialog closed under a running batch."""
        self._cancel()

    def done(self, result) -> None:
        if self.running():  # only reachable by code: wait for the game under way
            self.worker.requestInterruption()
            self.worker.wait()
        self._scan_poll.stop()
        self.focus_ring.detach()
        super().done(result)
