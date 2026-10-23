"""Phase 92: the launcher lives in the tray.

  1. Settings' "Running in the background": after "Controller and TV", off by default, a switch
     the dialog's answers carry;
  2. the tray icon while "Keep running" is on, its tooltip, and its menu: the games played last,
     Play through ui_actions.play, then Rescan, Settings..., Quit;
  3. a close hides the window: the timers and the folder watch go on, a game started for real (a
     shim that hands over to a child and exits, as Phase 16's) is banked at the hide and goes on
     being timed after it; the first hide's balloon once, never again;
  4. the game ending with the window hidden leaves it hidden (Phase 28's return to the front);
  5. "Keep running" turned off while hidden shows the window and removes the icon, and the next
     close quits as it always did;
  6. Quit does what a close did, in its order -- recorded, not read;
  7. one launcher at a time: the lock, a lock left by a killed process taken over;
  8. a real second start (launcher.py in another process, on this copy's data): the running one is
     asked to show itself -- in TV mode for --tv -- and the second ends with 0;
  9. a running one that holds the lock and does not answer: the plain message, and the end;
 10. --background: the session begins with no window; a first run, or Keep running off, shows it;
 11. the tray late at sign-in: waited for, and the window shown if it never comes;
 12. Settings' "Start with Windows": never on without Keep running, Windows' own off said in words;
 13. the Run key value, on this suite's own test key: written, read back, both command forms,
     Windows' StartupApproved bytes, deleted; an uninstall removes only the value that starts its exe;
 14. the tick's decision table, on stood-in due rules.

The user's real Run key is never written: every suite's sandbox names a test key of its own
(test_sandbox), and the real value is photographed at the start and compared at the end.

On a throwaway copy of the data, the network off; the Windows notification of the first hide is
stood in for, so nothing pops up on the screen.
"""
import os
import subprocess
import sys
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import test_sandbox

# The desk, whatever the real settings say (the user's are in TV mode since 16 October): a window
# shown here must not take the whole screen.
box = test_sandbox.start({"keep_running": True, "allow_network": False, "startup_scan": False,
                          "tv_mode": False})

import logging

logging.basicConfig(level=logging.ERROR)

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QSystemTrayIcon

app = QApplication([])

from data_access import catalog_io, config_io
from shared import rules
from shared.models import GameEntry
from presentation import ui_actions, ui_rules, ui_settings, ui_window

try:  # what this phase adds; on the code before it, each section fails on its own (both ways)
    from presentation import ui_tray
    from adapters import single_instance
    from logic import autostart
except ImportError as missing:
    print(f"   (not on this code: {missing})")
    ui_tray = single_instance = autostart = None

passed = failed = 0
FAKE_GAME = Path(box.folder) / "p92 shim game"
FAKE_GAME.mkdir(exist_ok=True)
PYTHONW = str(Path(sys.executable).with_name("pythonw.exe"))
CMD = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "cmd.exe")


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"   PASS  {name}")
    else:
        failed += 1
        print(f"   FAIL  {name}   {detail}")


def unreached(section: str, exc: Exception):
    """A section that could not run to its end on this code counts as one failure."""
    check(f"section {section} runs to its end on this code", False, repr(exc))


def settle(seconds: float) -> None:
    loop = QEventLoop()
    QTimer.singleShot(int(seconds * 1000), loop.quit)
    loop.exec()


def shim_game(seconds: int):
    """A game the way Phase 16 met them: cmd starts the real process and is gone at once; the
    child lives on in the job for `seconds`."""
    entry = GameEntry(
        source="folders", source_id=str(FAKE_GAME / "shim"), display_name="p92 shim game",
        install_dir=str(FAKE_GAME), launch_kind="exe", launch_target=CMD, working_dir=str(FAKE_GAME),
        icon_hint=CMD, size_on_disk=0, detection="heuristic",
    )
    args = f'/c start "" /b "{PYTHONW}" -c "import time; time.sleep({seconds})"'
    return catalog_io.GameView(entry, {"args": args})


print("=== 1. Settings: Running in the background ===")
try:
    plain = {k: v for k, v in config_io.load_config().items() if k != rules.KEEP_RUNNING_KEY}
    dialog = ui_settings.SettingsDialog(plain, None, known_keys=set())
    sections = [label.text() for label in dialog.findChildren(QLabel) if label.objectName() == "SettingSection"]
    check("a section 'Running in the background', right after 'Controller and TV'",
          "Running in the background" in sections
          and sections.index("Running in the background") == sections.index("Controller and TV") + 1, sections)
    row = next((r for r in dialog.findChildren(ui_settings.SettingRow) if r.switch is dialog.keep_box), None)
    check("its row: 'Keep running when the window is closed', the brief's quieter line",
          row is not None and row.title.text() == "Keep running when the window is closed"
          and row.hint.text().startswith("Stays in the tray: keeps timing a running game"), row and row.hint.text())
    check("off by default: a config.json without the key leaves it off",
          dialog.keep_box.isChecked() is False and dialog.values()[rules.KEEP_RUNNING_KEY] is False)
    dialog.keep_box.setChecked(True)
    check("the dialog's answers carry it, under its own key", dialog.values()[rules.KEEP_RUNNING_KEY] is True)
    dialog.deleteLater()
except Exception as exc:
    unreached("1", exc)

window = ui_window.MainWindow()
window.detail.allow_network = False
window.resize(1100, 760)
window.show()
settle(1.0)
said: list[str] = []

print("\n=== 2. the tray icon and its menu ===")
try:
    check("Windows has a tray here", QSystemTrayIcon.isSystemTrayAvailable())
    check("with 'Keep running' on, the icon is in the tray", window.tray is not None and window.tray.visible())
    check("its tooltip: Game Launcher", window.tray.icon.toolTip() == "Game Launcher", window.tray.icon.toolTip())
    check("closing the last window no longer quits Qt on its own (only Quit does)",
          QApplication.instance().quitOnLastWindowClosed() is False)
    window.tray.say = said.append  # the first-hide balloon, recorded rather than shown
    window.tray.fill()
    entries = window.tray.entries()
    played = sorted((v for v in window.views if not v.hidden and not v.is_non_game and v.last_played is not None),
                    key=lambda v: -v.last_played.timestamp())[: ui_rules.RECENT_TRAY_GAMES]
    expected = ([ "Open Game Launcher", "-"] + [f"Play {v.display_name}".replace("&", "&&") for v in played]
                + ["-", "Rescan", "Settings...", "Quit"])
    check(f"the menu: Open, the {len(played)} games played last (newest first), Rescan, Settings..., Quit",
          entries == expected, entries)
    calls = []
    real_play = ui_actions.play
    ui_actions.play = lambda w, view: calls.append((w, view.key))
    try:
        action = next(a for a in window.tray.menu.actions() if a.text().startswith("Play "))
        action.trigger()
    finally:
        ui_actions.play = real_play
    check("its Play goes through ui_actions.play, as a click on the tile does",
          calls == [(window, played[0].key)], calls)
except Exception as exc:
    unreached("2", exc)

game = shim_game(40)
window.views.append(game)  # as a game played from its tile is: among the window's games
window.by_key[game.key] = game

print("\n=== 3. a close hides; a game goes on being timed; the balloon once ===")
try:
    ui_actions.play(window, game)
    check("the shim game is being timed (its cmd gone, its child in the job)", window.tracker.is_running(game.key))
    settle(3.5)
    window._poll_playtime()
    window.tray.fill()
    check("the menu offers Stop for it, first among the games",
          window.tray.entries()[2] == "Stop p92 shim game", window.tray.entries())
    before = int(window.overrides.get(game.key).get("playtime_seconds", 0))
    window.close()
    settle(0.5)
    at_hide = int(window.overrides.get(game.key).get("playtime_seconds", 0))
    check("closing hid the window, it did not quit", not window.isVisible() and window._in_tray
          and not window._shut_down)
    check("the playtime was banked at the hide", at_hide > before and at_hide >= 3, (before, at_hide))
    check("the poll timer and the folder watch go on", window.timer.isActive() and window.watcher is not None
          and not getattr(window, "_shut_down", True))
    check("the game is still being timed", window.tracker.is_running(game.key))
    check("the first hide said once where the launcher went", said == [ui_tray.FIRST_HIDE], said)
    check("and remembered it, by its own key in config.json",
          config_io.load_saved().get(rules.TRAY_HINT_KEY) is True)
    settle(3.5)
    window._poll_playtime()
    window._bank_playtime()
    later = int(window.overrides.get(game.key).get("playtime_seconds", 0))
    check("its time goes on growing after the hide", later > at_hide, (at_hide, later))
    check("the tooltip says what is being played and for how long",
          window.tray.icon.toolTip().startswith("Playing p92 shim game for "), window.tray.icon.toolTip())
    window.bring_forward()
    settle(0.5)
    check("a click on the icon brings the window back", window.isVisible() and not window._in_tray)
    window.close()
    settle(0.5)
    check("a second close hides again and says nothing", not window.isVisible() and said == [ui_tray.FIRST_HIDE], said)
except Exception as exc:
    unreached("3", exc)

print("\n=== 4. the game ends while the window is hidden ===")
try:
    real_front = ui_window.focus.bring_to_front
    fronted = []
    ui_window.focus.bring_to_front = lambda hwnd: fronted.append(hwnd) or True
    try:
        window.tracker.stop(game.key)
        settle(0.5)
        window._poll_playtime()
        settle(0.3)
    finally:
        ui_window.focus.bring_to_front = real_front
    check("the session ended", not window.tracker.is_running(game.key))
    check("the window stays hidden: it was in the tray (Phase 28's return to the front stands aside)",
          not window.isVisible() and fronted == [], fronted)
    check("the tooltip is back to Game Launcher", window.tray.icon.toolTip() == "Game Launcher",
          window.tray.icon.toolTip())
    total = int(window.overrides.get(game.key).get("playtime_seconds", 0))
    check("the whole session is in its total, the time after the hide included", total >= later, (later, total))
except Exception as exc:
    unreached("4", exc)

print("\n=== 5. 'Keep running' turned off while hidden ===")
try:
    real_exec = ui_settings.SettingsDialog.exec
    real_values = ui_settings.SettingsDialog.values
    ui_settings.SettingsDialog.exec = lambda self: QDialog.DialogCode.Accepted
    ui_settings.SettingsDialog.values = lambda self: dict(real_values(self), **{rules.KEEP_RUNNING_KEY: False})
    try:
        window.open_settings()  # what the tray menu's Settings... calls
    finally:
        ui_settings.SettingsDialog.exec, ui_settings.SettingsDialog.values = real_exec, real_values
    settle(0.5)
    check("the window is shown at once", window.isVisible() and not window._in_tray)
    check("the icon is gone from the tray", window.tray is None)
    check("and closing the last window quits again", QApplication.instance().quitOnLastWindowClosed() is True)
    check("written by its own key", config_io.load_saved().get(rules.KEEP_RUNNING_KEY) is False)
    window.close()
    settle(0.5)
    check("the next close quits as it always did: the launcher shut down", window._shut_down and not window.isVisible())
except Exception as exc:
    unreached("5", exc)

print("\n=== 6. Quit: what a close did, in its order ===")
try:
    QApplication.instance().setQuitOnLastWindowClosed(True)
    quitter = ui_window.MainWindow()
    quitter.detail.allow_network = False
    quitter.show()
    settle(1.0)
    order: list[str] = []

    def record(name, function=None):
        def stand_in(*args, **kwargs):
            order.append(name)
            return function(*args, **kwargs) if function else None
        return stand_in

    class SavingZip:
        def isRunning(self):
            return True

        def requestInterruption(self):
            pass

        def wait(self, ms):
            order.append("wait for the save copy")
            return True

    quitter.save_worker = SavingZip()
    quitter.pads.stop = record("stop the pad", quitter.pads.stop)
    quitter.watcher.stop = record("stop the folder watch", quitter.watcher.stop)
    quitter.detail.stop_downloads = record("stop the downloads", quitter.detail.stop_downloads)
    quitter._save_geometry = record("save the window's place", quitter._save_geometry)
    quitter._bank_playtime = record("bank the playtime", quitter._bank_playtime)
    quitter.overrides.close = record("let go of the database", quitter.overrides.close)
    quitter._exit_application = record("exit")
    quitter.quit_launcher()
    check("Quit: the pad, the watch, the save copy, the downloads, the place, the playtime, the database, then exit",
          order == ["stop the pad", "stop the folder watch", "wait for the save copy", "stop the downloads",
                    "save the window's place", "bank the playtime", "let go of the database", "exit"], order)
    quitter.save_worker = None
    order.clear()
    quitter.close()
    settle(0.3)
    check("the close that follows Quit does it all only once", order == [], order)
except Exception as exc:
    unreached("6", exc)

from argparse import Namespace

from shared import paths
import launcher


def make_window(**config):
    """A fresh window on this copy, Keep running as asked, its exit stood in for."""
    if config:
        config_io.save_config(config)
    w = ui_window.MainWindow()
    w.detail.allow_network = False
    w.exited = []
    w._exit_application = lambda: w.exited.append(True)
    return w


def finish(w):
    w.quit_launcher()
    settle(0.2)


def hold_lock(name: str, serve: bool = False):
    """Another process holding the launcher's lock -- answering on the channel or not."""
    code = (
        "import sys, time\n"
        f"sys.path.insert(0, r'{PROJECT}')\n"
        "from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer\n"
        "app = QCoreApplication([])\n"
        "from adapters import single_instance\n"
        f"lock = single_instance.take('{name}')\n"
        "print('held' if lock else 'refused', flush=True)\n"
        "time.sleep(120)\n"
    )
    child = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True)
    return child, child.stdout.readline().strip()


print("\n=== 7. one launcher at a time: the lock ===")
try:
    name = single_instance.key(paths.data_dir())
    check("the name: GameLauncher- and 16 hex digits of the data folder",
          name.startswith("GameLauncher-") and len(name) == len("GameLauncher-") + 16, name)
    check("the same folder, written differently, gives the same name",
          single_instance.key(str(paths.data_dir()).upper() + "\\") == name)
    check("another data folder -- an installed copy's, the real one -- another name",
          single_instance.key(PROJECT / "data") != name)
    first = single_instance.take(name)
    second = single_instance.take(name)
    check("the first start takes the lock; while it holds it no other start can",
          first is not None and second is None)
    first.unlock()
    child, said_child = hold_lock(name)
    check("another process holds it", said_child == "held", said_child)
    check("while that process lives, the lock is refused", single_instance.take(name) is None)
    child.kill()
    child.wait()
    settle(0.3)
    check("the lock file it left is still on disk", os.path.isfile(single_instance.lock_path(name)))
    taken = single_instance.take(name)
    check("a lock left by a killed process does not stop a start: it is taken over", taken is not None)
    if taken is not None:
        taken.unlock()
except Exception as exc:
    unreached("7", exc)

print("\n=== 8. a real second start, in another process ===")
try:
    script = Path(box.folder) / "second_start.py"
    script.write_text(
        "import sys\n"
        "from pathlib import Path\n"
        f"sys.path.insert(0, r'{PROJECT}')\n"
        "from shared import paths\n"
        f"paths.data_dir = lambda: Path(r'{paths.data_dir()}')\n"
        "import launcher\n"
        "def refuse(*args, **kwargs):\n"
        "    raise SystemExit(7)  # a second start never builds a window\n"
        "launcher.MainWindow = refuse\n"
        "raise SystemExit(launcher.main(sys.argv[1:]))\n",
        encoding="utf-8",
    )
    owner_lock = single_instance.take(name)
    owner = single_instance.Owner(name, owner_lock)
    asked: list[bool] = []
    target = make_window(keep_running=True)
    target.show()
    settle(0.8)
    target.hide_to_tray()
    fullscreen = []
    target.showFullScreen = lambda: fullscreen.append(True)  # TV mode's rules, not your whole screen
    owner.showRequested.connect(asked.append)
    owner.showRequested.connect(target.bring_forward)

    def second(*flags):
        began = time.monotonic()
        child = subprocess.Popen([sys.executable, str(script), *flags], stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True)
        while child.poll() is None and time.monotonic() - began < 40:
            settle(0.1)
        if child.poll() is None:
            child.kill()
        settle(0.3)
        return child.returncode, time.monotonic() - began

    code, took = second()
    check(f"the second start ended with 0, in {took:.1f} s", code == 0, code)
    check("the running one was asked to show itself", asked == [False], asked)
    check("and it did: the window is back", target.isVisible() and not target._in_tray)
    target.hide_to_tray()
    code, took = second("--tv")
    check(f"with --tv the second start ended with 0 too, in {took:.1f} s", code == 0, code)
    check("and asked for TV mode, which the running one entered", asked == [False, True] and target.tv_mode
          and fullscreen, (asked, target.tv_mode))
    target.tv_mode = False
    owner.release()
    finish(target)
except Exception as exc:
    unreached("8", exc)

print("\n=== 9. a running one that does not answer ===")
try:
    child, said_child = hold_lock(name)
    shown = []
    real_warning = launcher.QMessageBox.warning
    real_timeout = rules.SINGLE_INSTANCE_TIMEOUT_MS
    launcher.QMessageBox.warning = lambda parent, title, text: shown.append(text)
    rules.SINGLE_INSTANCE_TIMEOUT_MS = 1500
    try:
        began = time.monotonic()
        code = launcher.second_start(name, False)
        took = time.monotonic() - began
    finally:
        launcher.QMessageBox.warning = real_warning
        rules.SINGLE_INSTANCE_TIMEOUT_MS = real_timeout
        child.kill()
        child.wait()
    check("the lock held, nobody answering", said_child == "held", said_child)
    check(f"the second start gave up after the timeout ({took:.1f} s) and ended with 1",
          code == 1 and 1.4 <= took < 6, (code, took))
    check("saying so plainly, in a message", shown == [launcher.WEDGED], shown)
    check("in the brief's words", "already running but not responding; check the tray or Task Manager"
          in launcher.WEDGED)
except Exception as exc:
    unreached("9", exc)

print("\n=== 10. --background ===")
try:
    hidden = make_window(keep_running=True)
    launcher.present(hidden, Namespace(background=True, tv=False))
    settle(0.5)
    check("started with no window", not hidden.isVisible() and not hidden._shown and hidden._in_tray)
    check("the tray icon is there", hidden.tray is not None and hidden.tray.visible())
    check("the session began anyway: the startup scan, the saves, the update check are scheduled",
          hidden._startup_scan_started and hidden._saves_started and hidden._updates_started)
    hidden.begin()
    check("and only once: a later first show adds nothing", hidden._startup_scan_started)
    finish(hidden)

    off = make_window(keep_running=False)
    launcher.present(off, Namespace(background=True, tv=False))
    settle(0.5)
    check("--background with Keep running off: there is nothing to hide into, so it is shown",
          off.isVisible() and off.tray is None)
    finish(off)

    config = Path(box.folder) / "config.json"
    saved = config.read_bytes()
    config.unlink()
    try:
        fresh = ui_window.MainWindow()
        fresh.detail.allow_network = False
        fresh._exit_application = lambda: None
        questions = []
        fresh._ask_where_games_are = lambda: questions.append(True)
        launcher.present(fresh, Namespace(background=True, tv=False))
        settle(0.5)
        check("--background on a first run (no config.json): shown, to ask where the games are",
              fresh.isVisible() and questions == [True], questions)
        finish(fresh)
    finally:
        config.write_bytes(saved)
except Exception as exc:
    unreached("10", exc)

print("\n=== 11. the tray late at sign-in ===")
try:
    real_available = ui_window.tray_available
    real_retry, real_max = rules.TRAY_RETRY_MS, rules.TRAY_RETRY_MAX_S
    rules.TRAY_RETRY_MS, rules.TRAY_RETRY_MAX_S = 100, 1
    there = {"now": False}
    ui_window.tray_available = lambda: there["now"]
    try:
        late = make_window(keep_running=True)
        launcher.present(late, Namespace(background=True, tv=False))
        settle(0.3)
        check("no tray yet: no icon, the window still hidden, waiting",
              late.tray is None and not late.isVisible() and late._tray_wait is not None)
        there["now"] = True
        settle(0.4)
        check("the tray comes: the icon appears, the window stays hidden",
              late.tray is not None and not late.isVisible() and late._tray_wait is None)
        finish(late)
        there["now"] = False
        never = make_window(keep_running=True)
        launcher.present(never, Namespace(background=True, tv=False))
        settle(1.6)
        check("the tray never comes: after the wait the window is shown -- never no window and no icon",
              never.isVisible() and never.tray is None and never._tray_wait is None)
        finish(never)
    finally:
        ui_window.tray_available = real_available
        rules.TRAY_RETRY_MS, rules.TRAY_RETRY_MAX_S = real_retry, real_max
except Exception as exc:
    unreached("11", exc)

from logic import launch as launch_module, prices, steam_time, taskbar, wishlist
from shared import registry
import winreg


def approved(first_byte):
    """Windows' StartupApproved bytes for the value, as Task Manager writes them -- or none."""
    run_key, approved_key = autostart.keys()
    if first_byte is None:
        registry.delete_value("HKCU", approved_key, rules.STARTUP_VALUE_NAME)
        return
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, approved_key, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, rules.STARTUP_VALUE_NAME, 0, winreg.REG_BINARY, bytes([first_byte]) + bytes(11))


print("\n=== 12. Settings: Start with Windows ===")
try:
    run_key, approved_key = autostart.keys()
    check("this suite's own test key, not the real Run key", run_key.startswith(test_sandbox.TEST_KEY_ROOT)
          and run_key != rules.STARTUP_RUN_KEY, run_key)
    dialog = ui_settings.SettingsDialog(dict(config_io.load_config(), keep_running=False), None, known_keys=set())
    row = next((r for r in dialog.findChildren(ui_settings.SettingRow) if r.switch is dialog.start_box), None)
    keep_row = next(r for r in dialog.findChildren(ui_settings.SettingRow) if r.switch is dialog.keep_box)
    rows = [r for r in dialog.findChildren(ui_settings.SettingRow) if r.switch in (dialog.keep_box, dialog.start_box)]
    check("'Start with Windows', in the same section, right under Keep running",
          row is not None and row.title.text() == "Start with Windows" and row.parent() is keep_row.parent()
          and rows == [keep_row, row])
    check("off by default, its line the brief's", not dialog.start_box.isChecked()
          and row.hint.text() == "Starts hidden in the tray when you sign in.", row.hint.text())
    from adapters import controller as pad
    dialog.show()
    settle(0.3)
    dialog.tv_scale_box.setFocus()  # the row above the section, as a pad coming down would be
    window._drive_dialog(dialog, pad.DOWN)
    on_keep = dialog.focusWidget() is dialog.keep_box
    window._drive_dialog(dialog, pad.ACTIVATE)
    keep_flipped = dialog.keep_box.isChecked()
    window._drive_dialog(dialog, pad.DOWN)
    on_start = dialog.focusWidget() is dialog.start_box
    window._drive_dialog(dialog, pad.ACTIVATE)
    check("the pad works both rows as every other: down to each switch, A flips it",
          on_keep and keep_flipped and on_start and dialog.start_box.isChecked(),
          (on_keep, keep_flipped, on_start, dialog.start_box.isChecked()))
    dialog.keep_box.setChecked(False)  # both off again (the second follows the first), for what follows
    dialog.hide()
    dialog.start_box.setChecked(True)
    check("turning it on turns Keep running on too", dialog.keep_box.isChecked())
    dialog.keep_box.setChecked(False)
    check("turning Keep running off turns it off too", not dialog.start_box.isChecked())
    dialog.start_box.blockSignals(True)
    dialog.start_box.setChecked(True)
    dialog.start_box.blockSignals(False)
    check("and the answers hold it even so: on means Keep running on",
          dialog.start_with_windows() is True and dialog.values()[rules.KEEP_RUNNING_KEY] is True)
    check("Start with Windows is not a key of config.json: the Run value is its record",
          "start_with_windows" not in dialog.values())
    dialog.deleteLater()
    registry.write_string("HKCU", run_key, rules.STARTUP_VALUE_NAME, autostart.command())
    approved(0x03)
    blocked = ui_settings.SettingsDialog(config_io.load_config(), None, known_keys=set())
    blocked_row = next(r for r in blocked.findChildren(ui_settings.SettingRow) if r.switch is blocked.start_box)
    check("Windows' Startup apps has it off: the switch reads off, and the line says so",
          not blocked.start_box.isChecked() and blocked_row.hint.text().startswith("Windows has turned this off "
                                                                                  "in Startup apps"),
          blocked_row.hint.text())
    blocked.deleteLater()
    approved(None)
    registry.delete_value("HKCU", run_key, rules.STARTUP_VALUE_NAME)
except Exception as exc:
    unreached("12", exc)

print("\n=== 13. the Run key value ===")
try:
    check("from source: the venv's pythonw, launcher.py, --background", autostart.command() ==
          f'"{PROJECT / ".venv" / "Scripts" / "pythonw.exe"}" "{PROJECT / "launcher.py"}" --background',
          autostart.command())
    real_frozen, real_executable = taskbar.paths.FROZEN, taskbar.sys.executable
    taskbar.paths.FROZEN, taskbar.sys.executable = True, r"C:\Games\Game Launcher\GameLauncher.exe"
    try:
        frozen = autostart.command()
    finally:
        taskbar.paths.FROZEN, taskbar.sys.executable = real_frozen, real_executable
    check("installed: the exe itself, --background",
          frozen == '"C:\\Games\\Game Launcher\\GameLauncher.exe" --background', frozen)
    check("nothing there to begin with", autostart.state() == autostart.OFF and autostart.current() is None)
    check("on: written", autostart.enable() and autostart.current() == autostart.command()
          and autostart.state() == autostart.ON)
    check("on again writes the same thing: one value, the same command (an idempotent entry)",
          autostart.enable() and registry.read_all_values("HKCU", autostart.keys()[0])
          == {rules.STARTUP_VALUE_NAME: autostart.command()})
    approved(0x03)
    check("Windows' Startup apps turned it off (first byte 03): blocked, the value still there",
          autostart.state() == autostart.BLOCKED and autostart.current() is not None)
    approved(0x02)
    check("turned back on there (02): on", autostart.state() == autostart.ON)
    approved(None)
    check("never toggled (no bytes at all): on", autostart.state() == autostart.ON)
    check("off: the value deleted", autostart.disable() and autostart.current() is None
          and autostart.state() == autostart.OFF)
    check("off again: nothing to delete, still fine", autostart.disable())

    registry.write_string("HKCU", autostart.keys()[0], rules.STARTUP_VALUE_NAME, '"C:\\Other\\GameLauncher.exe" --background')
    check("an uninstall leaves a value that starts another copy",
          autostart.remove_if_ours(r"C:\Games\Game Launcher\GameLauncher.exe") and autostart.current() is not None)
    registry.write_string("HKCU", autostart.keys()[0], rules.STARTUP_VALUE_NAME,
                          '"C:\\Games\\Game Launcher\\GameLauncher.exe" --background')
    check("and removes the one that starts its own exe (case aside)",
          autostart.remove_if_ours(r"c:\games\game launcher\GameLauncher.exe") and autostart.current() is None)

    switch_window = make_window(keep_running=True)
    switch_window.show()
    settle(0.5)
    real_exec = ui_settings.SettingsDialog.exec
    real_start = ui_settings.SettingsDialog.start_with_windows
    ui_settings.SettingsDialog.exec = lambda self: QDialog.DialogCode.Accepted
    try:
        ui_settings.SettingsDialog.start_with_windows = lambda self: True
        switch_window.open_settings()
        check("Settings' OK with the switch on writes the value", autostart.current() == autostart.command())
        ui_settings.SettingsDialog.start_with_windows = lambda self: False
        switch_window.open_settings()
        check("with it off, deletes it at once", autostart.current() is None)
        check("and leaves Keep running as it was", switch_window.keep_running is True
              and config_io.load_saved().get(rules.KEEP_RUNNING_KEY) is True)
        switch_window.open_settings()
        check("an OK that changes nothing touches nothing", autostart.current() is None)
    finally:
        ui_settings.SettingsDialog.exec, ui_settings.SettingsDialog.start_with_windows = real_exec, real_start
    finish(switch_window)
except Exception as exc:
    unreached("13", exc)

print("\n=== 14. the tick ===")
try:
    ticking = make_window(keep_running=True)
    ticking.show()
    settle(0.5)
    check("the tick runs once the session has begun, every 30 minutes",
          ticking.tick.isActive() and ticking.tick.interval() == rules.BACKGROUND_TICK_MINUTES * 60 * 1000
          and rules.BACKGROUND_TICK_MINUTES == 30, ticking.tick.interval())
    scans, updates_asked = [], []
    ticking.start_scan = lambda **kwargs: scans.append(kwargs) or True
    ticking._check_for_updates = lambda quiet=False: updates_asked.append(quiet)
    real = (prices.due, wishlist.due, steam_time.due, steam_time.files_changed_since)
    answers = {"prices": [], "wishlists": [], "steam": False}
    prices.due = lambda store, online, say=True: answers["prices"]
    wishlist.due = lambda store, online, say=True: answers["wishlists"]
    steam_time.due = lambda store: True
    steam_time.files_changed_since = lambda moment: answers["steam"]
    try:
        ticking._tick()
        check("nothing due: no scan", scans == [], scans)
        check("the update check is asked with every tick, quietly (it keeps its own once a day)",
              updates_asked == [True], updates_asked)
        answers["prices"] = [730]
        ticking._tick()
        check("prices due, nothing in the way: one quiet scan, recorded as a watch scan",
              scans == [{"background": True, "trigger": "watch"}], scans)
        scans.clear()
        answers["prices"], answers["wishlists"] = [], [{"account_id": 1, "steam_id64": 2}]
        ticking._tick()
        check("a wishlist due: the same", len(scans) == 1)
        scans.clear()
        answers["wishlists"], answers["steam"] = [], True
        ticking._steam_played_since_scan = False
        ticking._last_scan_began = time.time()
        ticking._tick()
        check("Steam's files written since the last scan, and nothing played: no scan (Steam rewrites them "
              "with no play at all -- on 18 October the tick scanned every half hour for them)", scans == [], scans)
        ticking._steam_played_since_scan = True
        ticking._tick()
        check("written, and a Steam game seen played since: a quiet scan", len(scans) == 1, scans)
        scans.clear()
        check("and the reasons are named", ticking.readings_due() == ["Steam's playtime files"])
        ticking._steam_played_since_scan = False
        ticking._last_scan_began = time.time() - (rules.STEAM_TIME_TICK_HOURS * 3600 + 60)
        ticking._tick()
        check(f"written, nothing played, but the last scan over {rules.STEAM_TIME_TICK_HOURS} hours ago: a quiet scan",
              len(scans) == 1, scans)
        scans.clear()
        ticking._steam_played_since_scan = True
        playing = launch_module.RunningGame(key="p92 tick", name="p92 tick", started=time.monotonic())
        ticking.tracker.running.append(playing)
        ticking._tick()
        check("due, but a game started from here is running: no scan", scans == [], scans)
        ticking.tracker.running.remove(playing)

        class Busy:
            def isRunning(self):
                return True

        ticking.worker = Busy()
        ticking._tick()
        check("due, but a scan is already running: no second one", scans == [], scans)
        ticking.worker = None
        answers["steam"] = False
        ticking._tick()
        check("nothing due again: nothing", scans == [], scans)
    finally:
        prices.due, wishlist.due, steam_time.due, steam_time.files_changed_since = real
    check("Steam's files: none written in the future", not steam_time.files_changed_since(time.time() + 3600))
    check("the real tick on the real (stood-in) store: due rules asked, one decision",
          isinstance(ticking.readings_due(), list))
    finish(ticking)
except Exception as exc:
    unreached("14", exc)

print("\n=== 15. the layers; the real data ===")
layers = subprocess.run([sys.executable, str(PROJECT / "tests" / "check_layers.py")], capture_output=True, text=True,
                        encoding="utf-8", errors="replace")
check("no import points up a layer; sqlite3 only in data_access/", layers.returncode == 0, layers.stdout[-300:])
changed = box.finish()
check("config.json, the library database and the Run key's Game Launcher value are unchanged", not changed, changed)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
