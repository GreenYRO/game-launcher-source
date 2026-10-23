"""Phase 28: coming back to the front after a game, past Windows' focus lock.

Runs against a throwaway copy of the data (test_sandbox). This one cannot avoid your
screen: it is about which window Windows puts in front, so small windows jump forward for
a moment, a fake "game" opens and closes, and at the end focus goes back to whatever you
were using when it started.
"""
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # the project folder, one up from tests/
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import test_sandbox

box = test_sandbox.start()

import logging

logging.basicConfig(level=logging.ERROR)

import ctypes

from PySide6.QtWidgets import QApplication, QLabel

app = QApplication([])

from data_access import catalog_io
from logic import focus
from presentation import ui_actions
from presentation import ui_window
from shared.models import GameEntry

passed = failed = 0
windows = []
FAKE_GAME = Path(tempfile.mkdtemp(prefix="p28_game_"))
PYTHONW = str(Path(sys.executable).with_name("pythonw.exe"))


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"   PASS  {name}")
    else:
        failed += 1
        print(f"   FAIL  {name}   {detail}")


def pump(seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


def wait_for(predicate, timeout):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    return bool(predicate())


def move_focus_from_outside(hwnd):
    """Hand the foreground to `hwnd` from a separate process, as you would with a click.

    Doing it from inside this process -- the launcher's own -- leaves Windows treating the
    launcher as entitled to the foreground, and the control below then passed for the old
    way too. A first version of this test did exactly that.
    """
    import subprocess
    code = ("import sys; sys.path.insert(0, sys.argv[2]); from logic import focus; "
            "raise SystemExit(0 if focus.bring_to_front(int(sys.argv[1])) else 1)")
    helper = subprocess.Popen([sys.executable, "-c", code, str(hwnd), str(Path(__file__).resolve().parents[1])])
    # Keep this process's windows answering while the helper works: a helper tied to a
    # window whose owner is blocked waiting for it deadlocks -- which is how this test
    # found the case focus._responsive now guards against.
    wait_for(lambda: helper.poll() is not None, 20)
    if helper.poll() is None:
        helper.kill()
        return False
    return helper.returncode == 0


def title(hwnd):
    buffer = ctypes.create_unicode_buffer(256)
    ctypes.windll.user32.GetWindowTextW(hwnd, buffer, 256)
    return buffer.value


original = focus.foreground()
print(f"\nyou were using: {focus.class_name(original) or 'nothing'} -- focus goes back there at the end")

try:
    print("\n=== 1. the lock, and the way past it ===")
    SPI_GETFOREGROUNDLOCKTIMEOUT = 0x2000
    lock = ctypes.c_uint32()
    ctypes.windll.user32.SystemParametersInfoW(SPI_GETFOREGROUNDLOCKTIMEOUT, 0, ctypes.byref(lock), 0)
    print(f"   this machine's foreground lock timeout: {lock.value} ms")

    probe = QLabel("phase 28 test -- a window coming back to the front")
    probe.setWindowTitle("p28 probe")
    probe.resize(460, 90)
    probe.move(80, 80)
    probe.show()
    pump(0.4)
    hwnd = int(probe.winId())

    move_focus_from_outside(original)  # put the probe behind whatever you were using
    pump(0.4)
    check("the probe starts behind another program", focus.foreground() != hwnd,
          focus.class_name(focus.foreground()))
    probe.raise_()
    probe.activateWindow()
    pump(0.5)
    polite = focus.foreground() == hwnd
    print(f"   Qt's polite request (the old way) {'won' if polite else 'lost'}")
    check("control: Qt's polite request alone does not bring it back", not polite)
    if polite:
        move_focus_from_outside(original)
        pump(0.4)
    check("bring_to_front takes the foreground from another program",
          focus.bring_to_front(hwnd) and focus.foreground() == hwnd)
    check("the probe is not mistaken for an empty desktop", not focus.foreground_is_empty())

    # Windows will not let a program hand the foreground to the desktop -- asked to, it
    # activated the next window instead -- so the classification is checked against the
    # real desktop and taskbar handles on this machine rather than a staged foreground.
    desktop = int(ctypes.windll.user32.GetShellWindow())
    taskbar = int(ctypes.windll.user32.FindWindowW("Shell_TrayWnd", None) or 0)
    real_foreground = focus.foreground
    try:
        focus.foreground = lambda: desktop
        check(f"the bare desktop ({focus.class_name(desktop)}) counts as nothing in front",
              focus.foreground_is_empty())
        focus.foreground = lambda: taskbar
        check(f"so does the taskbar ({focus.class_name(taskbar)})", taskbar and focus.foreground_is_empty())
        focus.foreground = lambda: 0
        check("and no foreground window at all", focus.foreground_is_empty())
        focus.foreground = lambda: original
        check(f"but the program you were using ({focus.class_name(original)}) does not",
              not focus.foreground_is_empty())
    finally:
        focus.foreground = real_foreground
    check("asking when already in front is a quiet yes", focus.bring_to_front(hwnd))
    check("a window that does not exist is a no, not a crash", focus.bring_to_front(0x7FFFFFF0) is False)
    probe.close()

    print("\n=== 2. when the launcher takes itself back to the front ===")
    w = ui_window.MainWindow()
    windows.append(w)
    calls = []
    real_bring, real_empty = focus.bring_to_front, focus.foreground_is_empty
    focus.bring_to_front = lambda h: calls.append(h) or True
    try:
        w.tv_mode = True
        focus.foreground_is_empty = lambda: False
        w._come_back_to_front()
        check("in TV mode, always -- even over another program", len(calls) == 1)
        w.tv_mode = False
        calls.clear()
        w._come_back_to_front()
        check("at a desk, never over a program you moved to", not calls)
        focus.foreground_is_empty = lambda: True
        w._come_back_to_front()
        check("at a desk, yes when the game left you on the bare desktop", len(calls) == 1)
        calls.clear()
        w.tracker.running.append(object())
        w.tv_mode = True
        w._come_back_to_front()
        check("never while another game started from here is still running", not calls)
        w.tracker.running.clear()
    finally:
        focus.bring_to_front, focus.foreground_is_empty = real_bring, real_empty
        w.tv_mode = False

    print("\n=== 3. for real: a game starts, you end up elsewhere, the game quits ===")
    script = FAKE_GAME / "fake_game.py"
    script.write_text(
        "import sys, time\n"
        "from PySide6.QtCore import QTimer\n"
        "from PySide6.QtWidgets import QApplication, QLabel\n"
        "app = QApplication(sys.argv)\n"
        "w = QLabel('p28 fake game -- closes by itself')\n"
        "w.setWindowTitle('p28 fake game')\n"
        "w.resize(420, 90); w.move(140, 220); w.show(); w.raise_(); w.activateWindow()\n"
        "QTimer.singleShot(3500, app.quit)\n"
        "app.exec()\n",
        encoding="utf-8",
    )
    entry = GameEntry(
        source="folders", source_id=PYTHONW, display_name="p28 fake game",
        install_dir=str(FAKE_GAME), launch_kind="exe", launch_target=PYTHONW,
        working_dir=str(FAKE_GAME), icon_hint=PYTHONW, size_on_disk=0, detection="heuristic",
    )
    game = catalog_io.GameView(entry, {"args": f'"{script}"'})

    w.showFullScreen = lambda: None  # TV mode's rules, without taking your whole screen
    w.showNormal = lambda: None
    w.resize(900, 560)
    w.move(40, 40)
    w.show()
    w.set_tv_mode(True)
    launcher_hwnd = int(w.winId())

    bring = focus.bring_to_front  # the test's own moves always use the real thing

    def one_round(label):
        bring(launcher_hwnd)  # you are in the launcher when you press Play
        pump(0.3)
        ui_actions.play(w, game)
        up = wait_for(lambda: title(focus.foreground()) == "p28 fake game", 8)
        move_focus_from_outside(original)  # ...and by the time it quits, you are elsewhere
        pump(0.3)

        def finished():
            w._poll_playtime()  # what the window's own three-second timer does
            return not w.tracker.running

        ended = wait_for(finished, 15)
        pump(0.5)
        back = focus.foreground() == launcher_hwnd
        print(f"   {label}: game took the screen {up}, ended {ended}, launcher in front after {back}")
        return up, ended, back

    real = focus.bring_to_front
    focus.bring_to_front = lambda h: False  # the old behaviour: only Qt's polite request
    try:
        _up, _ended, back_before = one_round("with the old way")
    finally:
        focus.bring_to_front = real
    check("control: with only the polite request, the launcher stays behind", not back_before)

    up, ended, back = one_round("with the new way")
    check("the fake game really took the screen", up)
    check("the launcher noticed it close", ended)
    check("and came back to the front by itself", back)
    w.set_tv_mode(False)
    w.close()

finally:
    for window in windows:
        try:
            window.close()
        except RuntimeError:
            pass
    focus.bring_to_front(original)
    pump(0.3)
    print(f"\nfocus handed back to what you were using: {focus.foreground() == original}")
    print("\n=== 4. the real library is exactly as it was found ===")
    changed = box.finish()
    check("overrides.json, config.json and catalog.json are byte for byte unchanged", not changed,
          changed)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
