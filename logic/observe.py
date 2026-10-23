"""Games started outside the launcher (Phase 93): the process list, matched to the games here.

The launcher times what it starts (Phase 16). A game started from Steam, Epic, Xbox or its own
shortcut left no session at all -- and Steam games, whose hours Steam's own counter holds, had no
sessions anywhere, so every report about the hour of the day or the length of a sitting left them
out. Living in the tray since Phase 92, the launcher can look at the process list every few seconds
and notice a known game running, whoever started it: a passive observer. It reads the names and
paths of the processes on this PC, keeps nothing but the sessions of games it already knows, never
opens a process for more than its path, never touches or ends one.

Three parts, none of them Qt (adapters/process_worker.py runs the looking on a thread of its own,
the window writes what it finds):

  * `processes()` -- the image path of every process that lets itself be asked
    (EnumProcesses, OpenProcess with PROCESS_QUERY_LIMITED_INFORMATION, QueryFullProcessImageNameW,
    through ctypes -- the same rights Task Manager uses). Measured on 18 October: 321 processes,
    one look 3.0 ms (median of 20); 162 refuse, every one a Windows service or a system part (no
    game among them). The ones that refuse are counted and named (a Toolhelp snapshot, which names
    a process without opening it), never guessed at.
  * `watched_games(views, roots)` and `owners(paths, games)` -- which games are watched and which
    of them a process belongs to. A process belongs to a game when its path is inside the game's
    folder, compared as normalised paths with the separator included: C:\\games\\Doom\\ never claims
    C:\\games\\Doom2\\ (this PC has the real case: WARDOGS beside WARDOGS Playtest). A loose exe -- an
    exe straight in a scan root, whose install_dir is the root -- matches its own path exactly and
    nothing else; a root itself never matches. A tool is never watched (the user's mark, or Steam's
    type when it is certain): a tool that runs all day would be a day-long session. Demos and mods
    are games; hidden games are watched (hiding does not unplay).
  * `Observer` -- the sessions. One opens at the first look that sees a game, and closes after
    rules.WATCH_GONE_POLLS looks in a row that see none of it. Its length is first seen to last
    seen, each gap between looks counted up to rules.WATCH_GAP_MAX_S, so a PC that sleeps with a
    game open counts a few seconds, not the night. Each edge is uncertain by one look.

The no-double-count rule is `adds_hours`: a game whose store keeps its hours (Steam: its own
counter, read since Phase 75 and added in v_hours) gets its sessions for their shape -- when, how
long -- and never adds to playtime_seconds; any other game's observed minutes are its hours,
because nothing else counts them. docs/BAZA_DE_DATE.md states it, with the case it leaves.
"""

from __future__ import annotations

import ctypes
import logging
import os
from ctypes import wintypes
from dataclasses import dataclass, field
from datetime import datetime

from shared import rules

log = logging.getLogger(__name__)

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
TH32CS_SNAPPROCESS = 0x2
NO_IMAGE = (0, 4)  # the System Idle Process and System: nothing to ask

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.OpenProcess.restype = wintypes.HANDLE
_k32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
_k32.QueryFullProcessImageNameW.argtypes = (wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                            ctypes.POINTER(wintypes.DWORD))
_k32.CloseHandle.argtypes = (wintypes.HANDLE,)
_k32.K32EnumProcesses.argtypes = (ctypes.POINTER(wintypes.DWORD), wintypes.DWORD, ctypes.POINTER(wintypes.DWORD))
_k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
_k32.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)


class _ProcessEntry(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_void_p), ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260)]


_k32.Process32FirstW.argtypes = (wintypes.HANDLE, ctypes.POINTER(_ProcessEntry))
_k32.Process32NextW.argtypes = (wintypes.HANDLE, ctypes.POINTER(_ProcessEntry))
INVALID_HANDLE = wintypes.HANDLE(-1).value


def _pids() -> list[int]:
    size = 4096
    while True:
        array = (wintypes.DWORD * size)()
        needed = wintypes.DWORD()
        if not _k32.K32EnumProcesses(array, ctypes.sizeof(array), ctypes.byref(needed)):
            log.warning("process watch: the process list could not be read (error %d)", ctypes.get_last_error())
            return []
        if needed.value < ctypes.sizeof(array):
            return list(array[: needed.value // ctypes.sizeof(wintypes.DWORD)])
        size *= 2


def processes() -> tuple[list[str], set[int]]:
    """(the image path of every process that can be asked, the ids of those that refused).

    Never this launcher's own process. Nothing is kept: the paths are matched and let go.
    """
    paths, refused = [], set()
    buffer = ctypes.create_unicode_buffer(32768)
    mine = os.getpid()
    for pid in _pids():
        if pid in NO_IMAGE or pid == mine:
            continue
        handle = _k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            refused.add(pid)
            continue
        try:
            length = wintypes.DWORD(len(buffer))
            if _k32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(length)):
                paths.append(buffer.value)
            else:
                refused.add(pid)
        finally:
            _k32.CloseHandle(handle)
    return paths, refused


def names(pids: set[int]) -> dict[int, str]:
    """The file names of some processes, without opening any (a Toolhelp snapshot)."""
    snap = _k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not snap or snap == INVALID_HANDLE:
        return {}
    found = {}
    try:
        entry = _ProcessEntry()
        entry.dwSize = ctypes.sizeof(_ProcessEntry)
        ok = _k32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            if entry.th32ProcessID in pids:
                found[entry.th32ProcessID] = entry.szExeFile
            ok = _k32.Process32NextW(snap, ctypes.byref(entry))
    finally:
        _k32.CloseHandle(snap)
    return found


# -- which games, and which game a process belongs to --------------------------------------------


def norm(path: str) -> str:
    return os.path.normcase(os.path.normpath(path)) if path else ""


@dataclass(frozen=True)
class Watched:
    key: str
    name: str
    folder: str  # normalised install folder; "" for a loose exe
    exe: str  # normalised exe path, for a loose exe only
    adds_hours: bool  # its observed minutes are its hours (no store keeps them)
    launch_kind: str  # "exe" or "uri": whether the saves search applies after a session


def adds_hours(view) -> bool:
    """The no-double-count rule: False for a game whose store keeps its hours (Steam's counter)."""
    return view.entry.source not in rules.HOURS_KEPT_BY_STORE


def is_watched(view) -> bool:
    """A game, not a tool: the user's own mark first; then Steam's type, when the appid is certain."""
    marked = view.data.get("is_tool")
    if marked is not None:
        return not marked
    if view.entry.extra.get("appid_source") == rules.APPID_SOURCE_SEARCH:
        return True  # a guessed appid never decides anything (after Phase 9)
    kind = view.app_type
    return not kind or kind in rules.WATCH_GAME_TYPES


def watched_games(views, roots=()) -> list[Watched]:
    """The games whose processes are looked for: every one but a tool, and never a scan root."""
    root_set = {norm(root) for root in roots}
    found = []
    for view in views:
        if not is_watched(view):
            continue
        entry = view.entry
        if entry.detection == "loose_exe":
            exe = norm(view.launch_target)
            if exe:
                found.append(Watched(view.key, view.display_name, "", exe, adds_hours(view), entry.launch_kind))
            continue
        folder = norm(entry.install_dir)
        drive = os.path.splitdrive(folder)[0]
        if not folder or folder in root_set or folder.rstrip("\\/") == drive:
            continue  # a root or a drive is never a game's folder
        found.append(Watched(view.key, view.display_name, folder, "", adds_hours(view), entry.launch_kind))
    return found


def owners(paths, games) -> set[str]:
    """The keys of the games some process in `paths` belongs to."""
    folders = [(game.folder.rstrip("\\/") + os.sep, game.key) for game in games if game.folder]
    exes = {game.exe: game.key for game in games if game.exe}
    found = set()
    for path in paths:
        p = norm(path)
        key = exes.get(p)
        if key is not None:
            found.add(key)
            continue
        for prefix, key in folders:
            if p.startswith(prefix):
                found.add(key)
                break
    return found


# -- sessions ------------------------------------------------------------------------------------


@dataclass
class Seen:
    """One observed session while it lasts."""

    key: str
    name: str
    adds_hours: bool
    launch_kind: str
    started_at: datetime  # the wall clock of the first look that saw it, to the second
    last_seen: float  # time.monotonic() of the last look that saw it
    seconds: float = 0.0  # first seen to last seen, each gap counted up to WATCH_GAP_MAX_S
    absent: int = 0  # looks in a row that saw none of it
    banked: int = field(default=0)  # seconds already added to playtime_seconds (adds_hours games)

    @property
    def minutes(self) -> int:
        return int(self.seconds // 60)


class Observer:
    """The live observed sessions, fed one look at a time. Pure: the clock comes in with each look."""

    def __init__(self) -> None:
        self.live: dict[str, Seen] = {}

    def feed(self, running: set[str], games: dict[str, Watched], owned: set[str], now: float,
             wall: datetime) -> list[Seen]:
        """One look: the games seen running now. Returns the sessions that ended with it.

        `owned`: the games the launcher's own tracker times -- never observed while it does; a
        session seen before the launcher took the game over ends at its last sighting.
        """
        ended = []
        for key in sorted(running):
            if key in owned or key not in games:
                continue
            seen = self.live.get(key)
            if seen is None:
                game = games[key]
                self.live[key] = Seen(key, game.name, game.adds_hours, game.launch_kind,
                                      wall.replace(microsecond=0), now)
                continue
            seen.seconds += min(max(0.0, now - seen.last_seen), rules.WATCH_GAP_MAX_S)
            seen.last_seen = now
            seen.absent = 0
        for key in list(self.live):
            if key in owned:
                ended.append(self.live.pop(key))
            elif key not in running:
                seen = self.live[key]
                seen.absent += 1
                if seen.absent >= rules.WATCH_GONE_POLLS:
                    ended.append(self.live.pop(key))
        return ended

    def end_all(self) -> list[Seen]:
        """Every live session, ended at its last sighting: the watch stopping, the launcher quitting."""
        ended = list(self.live.values())
        self.live.clear()
        return ended

    def running(self) -> set[str]:
        """The games seen running at the last look (not the ones only waiting out the grace)."""
        return {key for key, seen in self.live.items() if seen.absent == 0}
