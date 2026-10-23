"""Bringing the launcher back to the front after a game, which Windows resists.

Windows refuses to let a program in the background take the foreground, and on this
machine it never relents: SPI_GETFOREGROUNDLOCKTIMEOUT reads 2147483647 ms, so the lock
never expires. Qt's raise_() + activateWindow() therefore only ever flashed the taskbar
button -- which on a couch, with a controller and no mouse, is a dead end.

Measured with a probe before anything was written: a background window asking with Qt's
calls lost; the same window attaching its input to the foreground window's thread for
the moment of SetForegroundWindow won. That is what bring_to_front does. It fakes no key
presses (the other common workaround taps Alt), it detaches at once, and it never
attaches to a window that Windows reports as hung.

Checked on this machine, not assumed: the desktop is a window of class Progman (it is
what GetShellWindow returns, and it hosts SHELLDLL_DefView, the desktop icons), and the
taskbars are Shell_TrayWnd plus one Shell_SecondaryTrayWnd per extra screen.
"""

from __future__ import annotations

import ctypes
import logging
from ctypes import wintypes

log = logging.getLogger(__name__)

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

_user32.GetForegroundWindow.restype = wintypes.HWND
_user32.GetShellWindow.restype = wintypes.HWND
_user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
_user32.GetWindowThreadProcessId.restype = wintypes.DWORD
_user32.AttachThreadInput.argtypes = (wintypes.DWORD, wintypes.DWORD, wintypes.BOOL)
_user32.AttachThreadInput.restype = wintypes.BOOL
_user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
_user32.SetForegroundWindow.restype = wintypes.BOOL
_user32.BringWindowToTop.argtypes = (wintypes.HWND,)
_user32.BringWindowToTop.restype = wintypes.BOOL
_user32.IsHungAppWindow.argtypes = (wintypes.HWND,)
_user32.IsHungAppWindow.restype = wintypes.BOOL
_user32.GetClassNameW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
_user32.GetClassNameW.restype = ctypes.c_int
_kernel32.GetCurrentThreadId.restype = wintypes.DWORD
_user32.SendMessageTimeoutW.argtypes = (
    wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
    wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t),
)
_user32.SendMessageTimeoutW.restype = ctypes.c_ssize_t

WM_NULL = 0x0000
SMTO_ABORTIFHUNG = 0x0002
# How long the window in front gets to show it is awake before we tie our input to it.
RESPONSIVE_WITHIN_MS = 250

# The bare desktop and the taskbars: what has the foreground when nothing does.
EMPTY_FOREGROUND_CLASSES = frozenset({"Progman", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"})


def foreground() -> int:
    return int(_user32.GetForegroundWindow() or 0)


def class_name(hwnd: int) -> str:
    buffer = ctypes.create_unicode_buffer(256)
    if not _user32.GetClassNameW(hwnd, buffer, len(buffer)):
        return ""
    return buffer.value


def foreground_is_empty() -> bool:
    """True when nothing the user chose has the foreground: the desktop, a taskbar, or none.

    That is where a game that has just closed usually leaves you, and the only case in
    which the ordinary window takes itself back to the front -- anything else is a window
    you moved to while the game ran, and must not be snatched from under you.
    """
    hwnd = foreground()
    if not hwnd:
        return True
    if hwnd == int(_user32.GetShellWindow() or 0):
        return True
    return class_name(hwnd) in EMPTY_FOREGROUND_CLASSES


def _responsive(hwnd: int) -> bool:
    """Whether the window's thread answers a do-nothing message promptly.

    Attaching input to a thread that is not pumping messages blocks us with it: the
    focus change waits for that thread to answer. Found by the test -- a helper tied to a
    window whose owner was itself waiting on the helper, and both stopped. IsHungAppWindow
    alone only notices after five seconds of silence, far too late for a GUI thread.
    """
    result = ctypes.c_size_t()
    return bool(
        _user32.SendMessageTimeoutW(
            hwnd, WM_NULL, 0, 0, SMTO_ABORTIFHUNG, RESPONSIVE_WITHIN_MS, ctypes.byref(result)
        )
    )


def bring_to_front(hwnd: int) -> bool:
    """Make `hwnd` the foreground window, past Windows' focus-stealing lock.

    Returns whether it worked. Never raises: failing to come to the front is a nuisance,
    and must never take the launcher down with it.
    """
    try:
        current = foreground()
        if current == hwnd:
            return True
        ours = _kernel32.GetCurrentThreadId()
        theirs = _user32.GetWindowThreadProcessId(current, None) if current else 0
        attach = (
            bool(theirs)
            and theirs != ours
            and not _user32.IsHungAppWindow(current)
            and _responsive(current)
        )
        attached = bool(_user32.AttachThreadInput(theirs, ours, True)) if attach else False
        try:
            _user32.BringWindowToTop(hwnd)
            _user32.SetForegroundWindow(hwnd)
        finally:
            if attached:
                _user32.AttachThreadInput(theirs, ours, False)
        won = foreground() == hwnd
        if not won:
            log.info("could not take the foreground from %s", class_name(current) or "nothing")
        return won
    except Exception as exc:  # ctypes and user32 failures alike; logged, never raised
        log.warning("bringing the window to the front failed: %s", exc)
        return False
