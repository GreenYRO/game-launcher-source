"""Phase 52: the pad works Settings and every other window the launcher opens.

Reported from use, after Phase 49: the menu on a game's page worked with the pad, but in
Settings the pad was dead. The cause was the pad's gate (Phase 7): the hub reads the pad
only while `window_is_active()` says yes, and that asked "is the main window active?".
A menu leaves the main window active; Settings is a window of its own, and Windows makes it
the active one -- so every press was dropped before it reached the code that would steer
the dialog. Phase 49's suite emitted presses *after* the gate, which is how it missed this.

This suite drives the hub's real poll -- its 16 ms timer, the gate, the button edges, the
queued signal -- with a pad simulated at the bottom: an object whose buttons the test
holds down. Only SDL's event pump is stubbed. And it checks the other half of the gate:
with another program in front, no press gets through. Runs on a throwaway copy of the
data; nothing is started.

The test is a chain of short steps on timers, never a blocking wait. A dialog runs its own
event loop inside whatever opened it, so a test that pauses with a nested loop of its own
is stuck behind the dialog it means to answer. Each step schedules the next one *before* it
runs, so a step that opens something modal does not hold up the steps that close it.
"""
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))  # the project folder, one up from tests/
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import test_sandbox

box = test_sandbox.start()

import logging

logging.basicConfig(level=logging.ERROR)

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

app = QApplication([])

from adapters import controller
from logic import focus
from presentation import ui_actions
from presentation import ui_window

passed = failed = 0
played = []
real_play = ui_actions.play
ui_actions.play = lambda window, view: played.append(view.key)
pygame = controller.pygame


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


def open_thing():
    return QApplication.activePopupWidget() or QApplication.activeModalWidget()


def run_chain(steps, limit_s):
    """Run (delay_ms, step) pairs one after another, each delay counted from the last step.

    Returns whatever was still open when the chain ended -- None when the pad closed it.
    The end, or a watchdog if a step stalls, closes it, so the suite fails rather than hangs
    when the pad cannot close something itself.
    """
    loop = QEventLoop()
    state = {"over": False, "stalled": None}

    def end():
        # Whatever is still open is closed here, or this loop could never return: a dialog's
        # own loop runs inside it, and quitting the outer one waits for the inner one.
        if state["over"]:
            return
        state["over"] = True
        state["stalled"] = open_thing()
        for _ in range(5):
            if open_thing() is None:
                break
            open_thing().close()
            QApplication.processEvents()
        loop.quit()

    def run(i):
        if i == len(steps):
            end()
            return
        delay, step = steps[i]

        def go():
            if state["over"]:
                return
            run(i + 1)  # first: the step may open something modal and not return until it closes
            step()

        QTimer.singleShot(delay, go)

    QTimer.singleShot(round(limit_s * 1000), end)
    run(0)
    loop.exec()
    settle(0.3)
    return state["stalled"]


class SimulatedPad:
    """What SDL hands the hub, with buttons the test holds down."""

    name = "(8BitDo Ultimate 2C Wireless Controller)"
    id = 1

    def __init__(self):
        self.down = set()

    def get_button(self, button):
        return button in self.down

    def get_axis(self, axis):
        return 0


w = ui_window.MainWindow()
w.resize(1400, 900)
w.move(app.primaryScreen().availableGeometry().topLeft())
w.show()
settle(1.0)

pad = SimulatedPad()
hub = w.pads
real_event_get = pygame.event.get
pygame.event.get = lambda: []  # no SDL here: the pad is the object above
hub.available = True
hub._pads = {pad.id: pad}
hub._active_id = pad.id
heard = []
hub.action.connect(heard.append)  # every press that got past the gate, as it is emitted
hub._timer.start()


def press(button):
    """Hold a button for a few polls, then let go. Never waits."""
    pad.down.add(button)
    QTimer.singleShot(120, lambda: pad.down.discard(button))


def to_front():
    focus.bring_to_front(int(w.winId()))


seen = {}


def note(**values):
    seen.update(values)


print("\n=== 1. Settings, through the hub's real poll, in TV mode: the reported case ===")


def start_settings():
    heard.clear()
    press(pygame.CONTROLLER_BUTTON_START)


def look_settings():
    dialog = QApplication.activeModalWidget()
    note(settings=type(dialog).__name__ if dialog else None, gate_in_settings=hub.window_is_active(),
         heard_start=list(heard), focus_before=QApplication.focusWidget())
    heard.clear()
    press(pygame.CONTROLLER_BUTTON_DPAD_DOWN)


def look_moved():
    note(heard_down=list(heard), focus_after=QApplication.focusWidget())
    press(pygame.CONTROLLER_BUTTON_B)


stalled = run_chain([
    (0, lambda: w.set_tv_mode(True)),
    (1500, to_front),
    (500, start_settings),
    (900, look_settings),
    (500, look_moved),
    (800, lambda: note(after_b=open_thing())),
], limit_s=12)
check("Start gets through the gate", "settings" in seen.get("heard_start", []), seen.get("heard_start"))
check("and opens Settings", seen.get("settings") == "SettingsDialog", seen.get("settings"))
check("with Settings open, the pad's gate still says the launcher is in front",
      seen.get("gate_in_settings") is True, seen.get("gate_in_settings"))
check("down on the d-pad gets through the gate, into Settings", "down" in seen.get("heard_down", []),
      seen.get("heard_down"))
check("and moves to the next setting", seen.get("focus_after") is not seen.get("focus_before"),
      (seen.get("focus_before"), seen.get("focus_after")))
check("B closes Settings", seen.get("after_b") is None and stalled is None, (seen.get("after_b"), stalled))

print("\n=== 2. any window the launcher opens: a confirmation box ===")
seen.clear()


def ask():
    question = QMessageBox(QMessageBox.Icon.Question, "A question", "Carry on?",
                           QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, w)
    question.setDefaultButton(QMessageBox.StandardButton.Cancel)
    question.setEscapeButton(QMessageBox.StandardButton.Cancel)
    note(answer=question.exec())


def look_question():
    note(question=open_thing() is not None, gate_in_question=hub.window_is_active())
    heard.clear()
    press(pygame.CONTROLLER_BUTTON_B)


stalled = run_chain([
    (300, to_front),
    (500, ask),
    (700, look_question),
    (800, lambda: note(after_b=open_thing(), heard_b=list(heard))),
], limit_s=10)
check("a confirmation is open, and the gate says the launcher is in front",
      seen.get("question") is True and seen.get("gate_in_question") is True,
      (seen.get("question"), seen.get("gate_in_question")))
check("B gets through the gate", "back" in seen.get("heard_b", []), seen.get("heard_b"))
check("and answers it with Cancel, from the pad alone",
      seen.get("after_b") is None and stalled is None
      and seen.get("answer") == QMessageBox.StandardButton.Cancel,
      (seen.get("after_b"), stalled, seen.get("answer")))

print("\n=== 3. a menu, through the real poll too (Phase 49's case) ===")
seen.clear()


def look_menu():
    menu = QApplication.activePopupWidget()
    note(menu=menu is not None, first=menu.activeAction() if menu else None)
    press(pygame.CONTROLLER_BUTTON_DPAD_DOWN)


def look_menu_moved():
    menu = QApplication.activePopupWidget()
    note(second=menu.activeAction() if menu else None)
    press(pygame.CONTROLLER_BUTTON_B)


stalled = run_chain([
    (0, lambda: w.show_detail(w.library.visible_keys[0])),
    (1200, to_front),
    (500, lambda: press(pygame.CONTROLLER_BUTTON_X)),
    (800, look_menu),
    (500, look_menu_moved),
    (800, lambda: note(after_b=open_thing())),
], limit_s=12)
check("X opens the game's menu", seen.get("menu") is True)
check("down moves through it", seen.get("second") is not None and seen.get("second") is not seen.get("first"),
      (seen.get("first"), seen.get("second")))
check("B closes it", seen.get("after_b") is None and stalled is None, (seen.get("after_b"), stalled))
check("and nothing was started", not played, played)

print("\n=== 4. another program in front: nothing gets through ===")
seen.clear()
other = Path(tempfile.gettempdir()) / "phase52_other_program.py"
other.write_text(textwrap.dedent(f"""
    import sys
    sys.path.insert(0, {str(PROJECT)!r})
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QLabel
    from logic import focus
    app = QApplication([])
    w = QLabel("another program -- a game, say")
    w.resize(500, 300)
    w.show()
    QTimer.singleShot(300, lambda: focus.bring_to_front(int(w.winId())))
    QTimer.singleShot(5000, app.quit)
    app.exec()
"""), encoding="utf-8")
child = {}


def look_gate():
    note(gate_behind=hub.window_is_active(), front=QApplication.activeWindow())
    heard.clear()
    press(pygame.CONTROLLER_BUTTON_A)


stalled = run_chain([
    (0, lambda: child.update(process=subprocess.Popen([sys.executable, str(other)]))),
    (3000, look_gate),
    (700, lambda: note(heard_a=list(heard))),
], limit_s=10)
check("with another program in front, the gate says no", seen.get("gate_behind") is False,
      seen.get("front"))
check("and a press of A never reaches the launcher", seen.get("heard_a") == [], seen.get("heard_a"))
check("nor did anything start or open", not played and stalled is None, (played, stalled))
child["process"].wait(timeout=20)
other.unlink(missing_ok=True)

hub._timer.stop()
hub._pads = {}
hub.available = False
pygame.event.get = real_event_get
ui_actions.play = real_play
w.set_tv_mode(False)
w.close()
print("\n=== 5. the real library is exactly as it was found ===")
changed = box.finish()
check("overrides.json, config.json and catalog.json are byte for byte unchanged", not changed, changed)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
