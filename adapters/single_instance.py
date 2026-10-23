"""One launcher at a time (Phase 92): a lock, and a channel to the one already running.

Two launchers would write the library and take the readings twice, so a second start never
makes a second one: it asks the running launcher to show itself -- in TV mode, when it was the
TV shortcut -- and ends. The lock and the channel are both named from the data folder, so a copy
with data of its own (an installed one, a test's sandbox) never answers for another.

The lock is Qt's QLockFile, in the temporary folder: it writes its owner's process id, and a lock
whose owner is gone -- the launcher crashed, or was ended from Task Manager -- is taken over
rather than obeyed (its stale time is 0: never judged by age, only by whether the owner lives).
While its owner runs, Windows keeps the file open, so it cannot be taken. The channel is a
QLocalServer, a named pipe on Windows, open to this user only.

Qt that draws nothing, turning a second start into a signal: an adapter, like controller.py.
"""

from __future__ import annotations

import hashlib
import logging
import os
import time

from PySide6.QtCore import QDir, QLockFile, QObject, QThread, QTimer, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from shared import rules

log = logging.getLogger(__name__)

SHOW = b"show"
SHOW_TV = b"show tv"
OK = b"ok"


def key(data_dir) -> str:
    """'GameLauncher-' and the first 16 hex digits of a hash of the data folder's path."""
    folder = os.path.normcase(os.path.abspath(str(data_dir)))
    return rules.SINGLE_INSTANCE_PREFIX + hashlib.sha256(folder.encode("utf-8")).hexdigest()[:16]


def lock_path(name: str) -> str:
    return os.path.join(QDir.tempPath(), name + ".lock")


def take(name: str) -> QLockFile | None:
    """The lock, if no living launcher holds it -- or None. One left by a dead owner is taken over."""
    lock = QLockFile(lock_path(name))
    lock.setStaleLockTime(0)
    if lock.tryLock(0):
        return lock
    log.info("another launcher holds %s (%s)", lock_path(name), lock.error().name)
    return None


def hand_over(name: str, tv: bool, timeout_ms: int) -> bool:
    """A second start's half: ask the running launcher to show itself, and wait for its 'ok'.

    The running one may still be building its window, so the channel is tried again until the
    time is up. True only when it answered.
    """
    deadline = time.monotonic() + timeout_ms / 1000
    message = (SHOW_TV if tv else SHOW) + b"\n"
    while time.monotonic() < deadline:
        socket = QLocalSocket()
        socket.connectToServer(name)
        left = max(1, int((deadline - time.monotonic()) * 1000))
        if socket.waitForConnected(min(left, 1000)):
            socket.write(message)
            socket.flush()
            answer = b""
            while time.monotonic() < deadline and OK not in answer:
                left = max(1, int((deadline - time.monotonic()) * 1000))
                if not socket.waitForReadyRead(left):
                    break
                answer += bytes(socket.readAll().data())
            socket.abort()
            if OK in answer:
                return True
            continue
        socket.abort()
        QThread.msleep(rules.SINGLE_INSTANCE_RETRY_MS)
    return False


class Owner(QObject):
    """The running launcher's half: holds the lock, and answers a second start on the channel."""

    showRequested = Signal(bool)  # True: the TV shortcut asked

    def __init__(self, name: str, lock: QLockFile, parent=None) -> None:
        super().__init__(parent)
        self.name = name
        self.lock = lock
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        QLocalServer.removeServer(name)
        if self.server.listen(name):
            log.info("one launcher at a time: listening as %s", name)
        else:
            log.warning("could not open the channel %s (%s); a second start will say this one is not "
                        "answering", name, self.server.errorString())
        self.server.newConnection.connect(self._accept)

    def _accept(self) -> None:
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            socket.readyRead.connect(lambda s=socket: self._read(s))
            socket.disconnected.connect(socket.deleteLater)

    def _read(self, socket: QLocalSocket) -> None:
        line = bytes(socket.readAll().data()).strip()
        if line not in (SHOW, SHOW_TV):
            log.warning("the channel heard something that is not a request: %r", line[:40])
            socket.disconnectFromServer()
            return
        tv = line == SHOW_TV
        socket.write(OK + b"\n")
        socket.flush()
        socket.disconnectFromServer()
        log.info("a second start asked the running launcher to show itself%s", " in TV mode" if tv else "")
        QTimer.singleShot(0, lambda: self.showRequested.emit(tv))  # answered first, shown after

    def release(self) -> None:
        self.server.close()
        self.lock.unlock()
