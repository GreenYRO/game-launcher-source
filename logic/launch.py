"""Starting a game, following it until the whole thing has exited, and the elevation
fallback when Windows refuses.

Working directory matters more than it looks: a great many games resolve asset paths
relative to the process working directory and simply crash if it is anywhere but the
folder holding the exe. cwd is always the chosen exe's own directory.

**Every exe launch gets its own Job Object.** Most of this library is packaged builds, where the
exe that gets started is a shim -- a loader, a bitness picker, a DRM wrapper -- which
spawns the real game and exits within seconds. Watching only the process we started made
those titles record a few seconds per session however long they were played. Children
inherit job membership, so the job stays occupied until the last of them has gone.

Three things about how the job is configured, each deliberate:

  * **kill-on-job-close is off.** Closing the launcher must never take a running game
    with it. The cost is that timing stops when the launcher does.
  * **explicit breakaway is allowed.** A child that asks to leave the job and is refused
    fails to start outright; a rare untracked child is much better than a game that will
    not boot.
  * **silent breakaway is off**, since that would let anything leave unasked and defeat
    the whole thing.
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime

import pywintypes
import win32api
import win32con
import win32job
import win32process

from shared import rules

log = logging.getLogger(__name__)

ERROR_ACCESS_DENIED = 5
ERROR_CANCELLED = 1223  # user clicked No on the UAC prompt
ERROR_ELEVATION_REQUIRED = 740
SHELL_EXECUTE_SUCCESS_THRESHOLD = 32  # ShellExecute returns <=32 to mean failure


@dataclass
class RunningGame:
    key: str
    name: str
    started: float
    # Wall-clock, unlike `started` which is a time.monotonic() reading. A session has to be
    # recorded against a real date, and the monotonic clock has no relationship to one.
    started_at: datetime = field(default_factory=lambda: datetime.now().astimezone())
    handle: int | None = None
    job: object | None = None
    process: subprocess.Popen | None = None
    last_tick: float = 0.0  # the monotonic reading at the last look
    tracks_tree: bool = False
    # The time counted so far: every gap between two looks, each at most rules.PLAYTIME_GAP_MAX_S
    # (Phase 94). With no sleep in it, this is exactly the time since `started`.
    played: float = 0.0

    def __post_init__(self) -> None:
        self.last_tick = self.last_tick or self.started


@dataclass
class Tick:
    """One poll's worth of a session: how much time to add, and whether it has ended."""

    key: str
    name: str
    seconds: int
    finished: bool
    # Carried so the window can file this time against the right session without having to
    # keep its own parallel bookkeeping of what started when.
    started_at: datetime | None = None
    total_seconds: int = 0


@dataclass
class LaunchResult:
    ok: bool
    running: RunningGame | None = None
    error: str = ""
    needs_elevation: bool = False


def _refused_in_a_test_copy(view) -> LaunchResult | None:
    """A test copy of the data never starts one of the user's games (rules.TEST_COPY_ENV, set by
    tests/test_sandbox.py): only a game whose folder is in the temp folder -- where every suite makes its fake
    games -- may start there; any other, and every store's link, is refused as if made -- nothing to time, no
    dialog to hold a suite up -- and written into the copy's folder, so the suite reports it at its end. None
    outside a test copy: the user's own launcher never has the variable."""
    folder = os.environ.get(rules.TEST_COPY_ENV)
    if not folder:
        return None
    if view.entry.launch_kind == "exe" and view.entry.install_dir:
        temp = os.path.normcase(os.path.realpath(tempfile.gettempdir()))
        home = os.path.normcase(os.path.realpath(view.entry.install_dir))
        if home.startswith(temp + os.sep):
            return None  # a suite's own fake game
    log.warning("a test copy of the data: not starting %s (%s)", view.display_name, view.launch_target)
    try:
        with open(os.path.join(folder, rules.TEST_COPY_STARTS), "a", encoding="utf-8") as out:
            out.write(f"{view.display_name}\t{view.launch_target}\n")
    except OSError as exc:
        log.error("a test copy: the refused start of %s could not be noted (%s)", view.display_name, exc)
    return LaunchResult(True)


def launch_game(view) -> LaunchResult:
    """Start a game as the current user."""
    refused = _refused_in_a_test_copy(view)
    if refused is not None:
        return refused
    if view.entry.launch_kind == "uri":
        return _launch_uri(view)

    exe = view.launch_target
    if not os.path.isfile(exe):
        log.error("launch target no longer exists: %s", exe)
        return LaunchResult(False, error=f"The file is gone:\n{exe}")

    cwd = view.working_dir
    if not os.path.isdir(cwd):
        log.warning("working dir %s missing; falling back to the exe's folder", cwd)
        cwd = os.path.dirname(exe)

    command = f'"{exe}" {view.args}'.strip() if view.args else f'"{exe}"'
    log.info("launching %s (cwd=%s, args=%r)", exe, cwd, view.args)
    try:
        handle, pid, job = _spawn_in_job(command, cwd)
    except pywintypes.error as exc:
        # pywintypes.error is not an OSError, so it needs catching by name -- without this
        # the elevation prompt would never appear for a game that requires it.
        code = getattr(exc, "winerror", None)
        elevation = code in (ERROR_ELEVATION_REQUIRED, ERROR_ACCESS_DENIED)
        log.error("could not start %s (winerror=%s): %s", exe, code, exc)
        return LaunchResult(False, error=exc.strerror or str(exc), needs_elevation=elevation)
    except OSError as exc:
        code = getattr(exc, "winerror", None)
        elevation = code in (ERROR_ELEVATION_REQUIRED, ERROR_ACCESS_DENIED)
        log.error("could not start %s (winerror=%s): %s", exe, code, exc)
        return LaunchResult(False, error=str(exc), needs_elevation=elevation)

    log.info(
        "%s started as pid %d, %s",
        view.display_name,
        pid,
        "following the whole process tree" if job else "timing this process only",
    )
    return LaunchResult(
        True,
        running=RunningGame(
            key=view.key,
            name=view.display_name,
            started=time.monotonic(),
            handle=handle,
            job=job,
            tracks_tree=job is not None,
        ),
    )


def _make_job():
    """A job the game and its children live in. None if Windows will not give us one."""
    try:
        job = win32job.CreateJobObject(None, "")
        info = win32job.QueryInformationJobObject(
            job, win32job.JobObjectExtendedLimitInformation
        )
        # Exactly one flag. Not KILL_ON_JOB_CLOSE: closing the launcher would kill the
        # game. Not SILENT_BREAKAWAY_OK: children could leave unnoticed and the session
        # would appear to end while the game was still running.
        info["BasicLimitInformation"]["LimitFlags"] = win32job.JOB_OBJECT_LIMIT_BREAKAWAY_OK
        win32job.SetInformationJobObject(job, win32job.JobObjectExtendedLimitInformation, info)
        return job
    except pywintypes.error as exc:
        log.warning("no job object available, so only the first process is timed: %s", exc)
        return None


def _spawn_in_job(command: str, cwd: str):
    """Start suspended, put it in the job, then let it run.

    Suspended first so that nothing can spawn a child before the job exists around it --
    a shim that started the real game in that gap would escape the tracking entirely.
    """
    job = _make_job()
    startup = win32process.STARTUPINFO()
    handle, thread, pid, _tid = win32process.CreateProcess(
        None, command, None, None, 0, win32con.CREATE_SUSPENDED, None, cwd, startup
    )
    if job is not None:
        try:
            win32job.AssignProcessToJobObject(job, handle)
        except pywintypes.error as exc:
            log.warning("could not put %s in a job (%s); timing this process only", command, exc)
            _close(job)
            job = None
    try:
        win32process.ResumeThread(thread)
    finally:
        _close(thread)
    return handle, pid, job


def _close(handle) -> None:
    try:
        win32api.CloseHandle(handle)
    except pywintypes.error as exc:
        log.debug("closing a handle failed: %s", exc)


def _launch_uri(view) -> LaunchResult:
    """Hand a protocol URI to the shell, which routes it to the owning launcher.

    Nothing comes back to wait on: the shell returns as soon as Steam has been handed the
    URI, and the game is then Steam's child, not ours. So a URI entry is never timed.
    """
    target = view.launch_target
    log.info("opening %s", target)

    # Packaged apps (Xbox / Game Pass) are addressed by a shell folder path rather than a
    # registered protocol, and are started by handing that path to Explorer.
    if target.casefold().startswith("shell:"):
        try:
            subprocess.Popen(["explorer.exe", target], close_fds=True)
        except OSError as exc:
            log.error("could not hand %s to Explorer: %s", target, exc)
            return LaunchResult(False, error=f"Windows could not start it:\n{target}\n\n{exc}")
        return LaunchResult(True)

    try:
        os.startfile(target)
    except OSError as exc:
        log.error("shell refused %s: %s", target, exc)
        return LaunchResult(
            False,
            error=f"Windows could not open this link:\n{target}\n\n{exc}",
        )
    return LaunchResult(True)


def launch_elevated(view) -> LaunchResult:
    """Retry through ShellExecuteW "runas", which raises the UAC prompt.

    No process handle comes back from this path, so a game started here cannot be timed.
    """
    refused = _refused_in_a_test_copy(view)
    if refused is not None:
        return refused
    exe = view.launch_target
    cwd = view.working_dir if os.path.isdir(view.working_dir) else os.path.dirname(exe)
    log.info("retrying %s elevated", exe)
    try:
        result = win32api.ShellExecute(
            0, "runas", exe, view.args or None, cwd, win32con.SW_SHOWNORMAL
        )
    except Exception as exc:  # pywintypes.error
        if getattr(exc, "winerror", None) == ERROR_CANCELLED:
            log.info("user declined the UAC prompt for %s", exe)
            return LaunchResult(False, error="You declined the administrator prompt.")
        log.error("elevated launch of %s failed: %s", exe, exc)
        return LaunchResult(False, error=str(exc))

    if isinstance(result, int) and result <= SHELL_EXECUTE_SUCCESS_THRESHOLD:
        log.error("ShellExecute refused to start %s (code %s)", exe, result)
        return LaunchResult(False, error=f"Windows refused to start it (code {result}).")
    return LaunchResult(True)


class PlaytimeTracker:
    """Times a game from start until the last of its processes has gone.

    A session ends when the job reports zero active processes, which is what makes a
    shim-fronted game -- The Last of Us Part I's launcher.exe, the Cinderia loader --
    record the time actually played rather than the two seconds the shim lived for.

    Time is reported in increments rather than one total at the end, so nothing worse than
    a single interval is lost if the launcher is closed or crashes mid-session. Two things
    are still not measured, both accepted: a game started with administrator rights (there
    is no handle to follow), and any time after the launcher itself is closed.

    A sleep is not play (Phase 94). A game left open while the PC sleeps still has its
    processes when it wakes, and nothing looked in between, so each gap between two looks
    counts at most rules.PLAYTIME_GAP_MAX_S -- whatever the clock did meanwhile.
    """

    def __init__(self) -> None:
        self.running: list[RunningGame] = []

    def add(self, game: RunningGame) -> None:
        self.running.append(game)

    def poll(self) -> list[Tick]:
        """Time played per game since the last call, and which sessions have ended."""
        now = time.monotonic()
        ticks: list[Tick] = []
        still_running: list[RunningGame] = []
        for game in self.running:
            gap = max(0.0, now - game.last_tick)
            if gap > rules.PLAYTIME_GAP_MAX_S:
                # Nothing looked for this long: the PC slept or hibernated with the game open
                # (or the launcher stood still), and that is not play (Phase 94).
                log.info("%s: %ds between two looks, counted as %ds -- the PC was asleep, or the "
                         "launcher stood still", game.name, int(gap), rules.PLAYTIME_GAP_MAX_S)
                gap = rules.PLAYTIME_GAP_MAX_S
            game.last_tick = now
            # The total is everything counted, rounded once (Phase 53: a sum of each tick's whole
            # seconds lost a sixth of every session). `seconds` is what this tick adds to it, so
            # the ticks still sum to it exactly -- nothing that adds them up loses the fraction.
            counted = int(game.played)
            game.played += gap
            total = int(game.played)
            seconds = total - counted
            if self._alive(game):
                still_running.append(game)
                ticks.append(Tick(game.key, game.name, seconds, finished=False,
                                  started_at=game.started_at, total_seconds=total))
                continue
            log.info(
                "%s finished after %ds (%s)",
                game.name,
                total,
                "whole process tree" if game.tracks_tree else "single process",
            )
            ticks.append(Tick(game.key, game.name, seconds, finished=True,
                              started_at=game.started_at, total_seconds=total))
            self._release(game)
        self.running = still_running
        return ticks

    def _alive(self, game: RunningGame) -> bool:
        if game.job is not None:
            try:
                counts = win32job.QueryInformationJobObject(
                    game.job, win32job.JobObjectBasicAccountingInformation
                )
            except pywintypes.error as exc:
                log.warning("lost sight of %s's job (%s); watching the first process", game.name, exc)
                _close(game.job)
                game.job = None
            else:
                return counts["ActiveProcesses"] > 0
        if game.handle is not None:
            try:
                return win32process.GetExitCodeProcess(game.handle) == win32con.STILL_ACTIVE
            except pywintypes.error as exc:
                log.warning("could not read %s's exit code: %s", game.name, exc)
                return False
        if game.process is not None:
            return game.process.poll() is None
        return False

    def _release(self, game: RunningGame) -> None:
        """Hand back the handles. Safe: the job does not kill what it holds when closed."""
        for handle in (game.job, game.handle):
            if handle is not None:
                _close(handle)
        game.job = game.handle = None

    def stop(self, key: str) -> bool:
        """End a running game on purpose, at the user's request.

        The launcher never does this on its own -- not at exit, not on a rescan. This is
        the single deliberate exception, and it exists because a game that has hung with no
        window of its own leaves no other way out.

        Terminating the *job* takes the whole tree at once: the shim, the game it spawned,
        and any children. Killing only the process we started would leave the real game
        running with nothing watching it. Where there is no job -- rare, and logged when it
        happens -- the started process is all there is to end.
        """
        game = next((g for g in self.running if g.key == key), None)
        if game is None:
            log.info("asked to stop %s, which is not running", key)
            return False
        try:
            if game.job is not None:
                win32job.TerminateJobObject(game.job, rules.STOP_EXIT_CODE)
                log.info("stopped %s: terminated the whole job", game.name)
            elif game.handle is not None:
                win32process.TerminateProcess(game.handle, rules.STOP_EXIT_CODE)
                log.info("stopped %s: no job, so only the started process", game.name)
            else:
                log.warning("nothing to terminate for %s", game.name)
                return False
        except pywintypes.error as exc:
            log.error("could not stop %s: %s", game.name, exc)
            return False
        return True

    def is_running(self, key: str) -> bool:
        return any(game.key == key for game in self.running)

    @property
    def active_keys(self) -> set[str]:
        return {game.key for game in self.running}
