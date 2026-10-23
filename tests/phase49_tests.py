"""Phase 49: the pad keeps working in a menu or a dialog it opened itself.

Reported from use: in TV mode, X on a game opened its menu and then the pad did nothing --
not up, not down, not A, not B -- while the mouse and keyboard still worked. The cause was
not the routing (Phase 27 sends pad presses to an open menu, and its suite proves it) but
the delivery: ControllerHub emits from inside its 16 ms poll timer, the press that opened
the menu ran the menu's own loop inside that timer's callback, and Qt does not fire a timer
again while its callback is running. Every suite before this one pressed buttons by calling
MainWindow._on_pad_action from outside the timer, which is why none of them saw it.

This suite presses buttons the way the hub does -- `window.pads.action.emit(...)` from
inside a timer ticking at the hub's own interval -- and works a menu and the Settings
dialog with nothing else. Runs on a throwaway copy of the data; nothing is started.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # the project folder, one up from tests/
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import test_sandbox

box = test_sandbox.start()

import logging

logging.basicConfig(level=logging.ERROR)

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

app = QApplication([])

from adapters import controller
from logic import focus
from presentation import ui_actions
from presentation import ui_window
from shared import rules

passed = failed = 0
played = []
real_play = ui_actions.play
ui_actions.play = lambda window, view: played.append(view.key)


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"   PASS  {name}")
    else:
        failed += 1
        print(f"   FAIL  {name}   {detail}")


def settle(seconds=0.4):
    """A local event loop -- never app.exec() ended by app.quit() (the Phase 31 lesson)."""
    loop = QEventLoop()
    QTimer.singleShot(round(seconds * 1000), loop.quit)
    loop.exec()


class Pad:
    """Presses buttons the way ControllerHub does: emitted from inside a poll timer.

    `script` is a list of (tick, step): on that tick of the poll, a step that is a pad
    action name is emitted on the window's real `pads.action` signal; a callable step is
    called (to look at what is on screen). If the poll stops ticking, later steps never run.
    """

    def __init__(self, window):
        self.window = window
        self.timer = QTimer()
        self.timer.setInterval(rules.CONTROLLER_POLL_MS)
        self.timer.timeout.connect(self._tick)
        self.ticks = 0
        self.script = []

    def run(self, script, seconds):
        self.ticks, self.script = 0, sorted(script, key=lambda step: step[0])
        # A watchdog for the bug itself: if the menu's loop runs inside the poll's callback,
        # nothing the pad does can close it, and without this the suite would hang instead
        # of failing. It fires inside that loop, closes whatever is open, and is stopped
        # when the run ends normally.
        watchdog = QTimer()
        watchdog.setSingleShot(True)
        watchdog.timeout.connect(self._rescue)
        self.rescued = None
        watchdog.start(round((seconds + 0.5) * 1000))
        self.timer.start()
        settle(seconds)
        self.timer.stop()
        settle(0.7)  # the watchdog's moment, if it is needed
        watchdog.stop()
        left = self.rescued or QApplication.activePopupWidget() or QApplication.activeModalWidget()
        if QApplication.activePopupWidget() or QApplication.activeModalWidget():
            (QApplication.activePopupWidget() or QApplication.activeModalWidget()).close()
            settle(0.3)
        return left

    def _rescue(self):
        stuck = QApplication.activePopupWidget() or QApplication.activeModalWidget()
        if stuck is not None:
            self.rescued = stuck
            stuck.close()

    def _tick(self):
        self.ticks += 1
        while self.script and self.script[0][0] <= self.ticks:
            _, step = self.script.pop(0)
            if callable(step):
                step()
            else:
                self.window.pads.action.emit(step)


w = ui_window.MainWindow()
w.resize(1400, 900)
w.move(app.primaryScreen().availableGeometry().topLeft())
w.show()
settle(1.0)
pad = Pad(w)
config_before = json.loads(box.path("config.json").read_text(encoding="utf-8"))


def work_a_menu(where):
    """X opens the menu, down moves through it, B closes it -- all from the poll."""
    seen = {}

    def look_open():
        menu = QApplication.activePopupWidget()
        seen["menu"] = menu
        seen["first"] = menu.activeAction() if menu else None
        seen["gate"] = w.isActiveWindow()
        seen["row"] = w.library.list.currentRow()

    def look_moved():
        menu = QApplication.activePopupWidget()
        seen["second"] = menu.activeAction() if menu else None
        seen["row after"] = w.library.list.currentRow()

    def look_closed():
        seen["closed"] = QApplication.activePopupWidget() is None

    focus.bring_to_front(int(w.winId()))
    settle(0.4)
    leftover = pad.run([(1, controller.MENU), (20, look_open), (21, controller.DOWN),
                        (35, look_moved), (36, controller.BACK), (50, look_closed)], 2.0)
    check(f"{where}: X opens the menu, and the pad is still read while it is open",
          seen.get("menu") is not None, f"poll ticks: {pad.ticks}")
    check(f"{where}: the window still counts as active for the pad's gate", seen.get("gate") is True,
          seen.get("gate"))
    check(f"{where}: down moves through the menu", seen.get("second") is not None
          and seen.get("second") is not seen.get("first"), (seen.get("first"), seen.get("second")))
    check(f"{where}: B closes it", seen.get("closed") is True and leftover is None, leftover)
    return seen


print("\n=== 1. a game's page in TV mode: the reported case ===")
w.set_tv_mode(True)
settle(1.5)
key = w.library.visible_keys[0]
w.show_detail(key)
settle(1.0)
work_a_menu("game page, TV")
check("and nothing was started", not played, played)

print("\n=== 2. the grid in TV mode: the same menu, and the tiles stay put behind it ===")
w.show_library()
settle(0.8)
w.library.select_key(w.library.visible_keys[2])
settle(0.3)
seen = work_a_menu("grid, TV")
check("the grid's selection did not move while the menu had the pad",
      seen.get("row after") == seen.get("row"), (seen.get("row"), seen.get("row after")))

print("\n=== 3. Start opens Settings; the pad works it and B leaves without saving ===")
seen = {}


def look_dialog():
    dialog = QApplication.activeModalWidget()
    seen["dialog"] = type(dialog).__name__ if dialog else None
    seen["focus"] = QApplication.focusWidget()


def look_focus():
    seen["focus after"] = QApplication.focusWidget()


def look_gone():
    seen["gone"] = QApplication.activeModalWidget() is None


focus.bring_to_front(int(w.winId()))
settle(0.4)
leftover = pad.run([(1, controller.SETTINGS), (25, look_dialog), (26, controller.DOWN),
                    (40, look_focus), (41, controller.BACK), (60, look_gone)], 2.5)
check("Start opens Settings, and the pad is still read while it is open", seen.get("dialog") == "SettingsDialog",
      f"{seen.get('dialog')}, poll ticks: {pad.ticks}")
check("down moves to the next setting", seen.get("focus after") is not None
      and seen.get("focus after") is not seen.get("focus"), (seen.get("focus"), seen.get("focus after")))
check("B closes Settings", seen.get("gone") is True and leftover is None, leftover)
config_after = json.loads(box.path("config.json").read_text(encoding="utf-8"))
check("and keeps nothing it did not ask for", {k: v for k, v in config_after.items() if k != "window_geometry"}
      == {k: v for k, v in config_before.items() if k != "window_geometry"})

print("\n=== 4. the ordinary window, not TV mode ===")
w.set_tv_mode(False)
settle(1.0)
w.show_detail(key)
settle(1.0)
work_a_menu("game page, window")

print("\n=== 5. the delivery itself ===")
# The pad's presses reach the window through the event queue, so the poll returns before
# whatever a press opens starts its own loop. Measured: with the menu open for a second,
# the poll keeps ticking at its own rate rather than stopping at the press that opened it.
ticks_open = {}
pad_open = Pad(w)
focus.bring_to_front(int(w.winId()))
settle(0.4)
pad_open.run([(1, controller.MENU), (2, lambda: ticks_open.setdefault("start", pad_open.ticks))], 1.2)
check("the poll kept ticking with the menu open (dozens of ticks, not one)", pad_open.ticks >= 40, pad_open.ticks)

ui_actions.play = real_play
w.close()
print("\n=== 6. the real library is exactly as it was found ===")
changed = box.finish()
check("overrides.json, config.json and catalog.json are byte for byte unchanged", not changed, changed)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
