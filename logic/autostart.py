"""Start with Windows (Phase 92): the launcher's value in the user's Run key, and Windows' own say.

HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run, value "Game Launcher": the command that starts the
launcher hidden in the tray. From source the venv's pythonw with launcher.py, installed the exe itself
-- taskbar.launch_command decides, as it does for the shortcuts -- then --background. Writing it again
writes the same thing (an idempotent startup entry). No shortcut is involved, so the shortcuts' app-id
trap does not apply: the process claims its own id before any window exists, as it always has.

Windows' Startup apps toggle (Task Manager, Settings) never deletes the value: it writes a 12-byte
REG_BINARY of the same name under ...\\Explorer\\StartupApproved\\Run. Read off this PC on 17 October
2026: the first byte is 02 for the entries allowed to start (Steam, LGHUB), 03 for those turned off
(Discord, OneDrive); an entry never toggled has no value there at all. An odd first byte is off. The
launcher reads it and never writes it: it is Windows' record of the user's own choice.
"""

from __future__ import annotations

import logging
import os

from logic import taskbar
from shared import registry
from shared import rules

log = logging.getLogger(__name__)

ON = "on"
OFF = "off"
BLOCKED = "blocked"  # the value is there, and Windows' Startup apps has it turned off


def keys() -> tuple[str, str]:
    """(the Run key, Windows' StartupApproved key) -- under a test's own root when one is named."""
    root = os.environ.get(rules.STARTUP_TEST_KEY_ENV, "").strip("\\")
    if root:
        return root + "\\Run", root + "\\StartupApproved\\Run"
    return rules.STARTUP_RUN_KEY, rules.STARTUP_APPROVED_KEY


def command() -> str:
    """What the value holds: this launcher, hidden in the tray."""
    program, arguments, _icon = taskbar.launch_command(False)
    return " ".join(part for part in (f'"{program}"', arguments, rules.BACKGROUND_ARGUMENT) if part)


def current() -> str | None:
    return registry.read_value("HKCU", keys()[0], rules.STARTUP_VALUE_NAME)


def allowed_by_windows() -> bool:
    """False when Windows' Startup apps has the entry turned off; True when it is on or never toggled."""
    blob = registry.read_binary("HKCU", keys()[1], rules.STARTUP_VALUE_NAME)
    return not blob or not blob[0] & 1


def state() -> str:
    """ON, OFF, or BLOCKED -- the effective answer to "will it start when I sign in"."""
    if current() is None:
        return OFF
    return ON if allowed_by_windows() else BLOCKED


def enable() -> bool:
    value = command()
    done = registry.write_string("HKCU", keys()[0], rules.STARTUP_VALUE_NAME, value)
    if done:
        log.info("start with Windows: on -- HKCU\\%s, %s = %s", keys()[0], rules.STARTUP_VALUE_NAME, value)
    return done


def disable() -> bool:
    done = registry.delete_value("HKCU", keys()[0], rules.STARTUP_VALUE_NAME)
    if done:
        log.info("start with Windows: off -- the value %s deleted from HKCU\\%s", rules.STARTUP_VALUE_NAME, keys()[0])
    return done


def names(value: str | None, exe) -> bool:
    """Does a Run value start this exe? Compared as paths, case aside."""
    if not value:
        return False
    return os.path.normcase(os.path.normpath(str(exe))) in os.path.normcase(value)


def remove_if_ours(exe) -> bool:
    """For an uninstall: the value goes if it starts this exe -- Windows would otherwise try to start a
    missing exe at every sign-in -- and stays if it starts another copy (one run from source, say)."""
    value = current()
    if value is None:
        return True
    if not names(value, exe):
        log.info("start with Windows: the Run value starts another copy (%s); left as it is", value)
        return True
    return disable()
