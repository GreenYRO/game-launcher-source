"""Removing an installed copy, reached as `GameLauncher.exe --uninstall`.

It lives in the app rather than in a separate uninstaller exe so the installed folder does
not have to carry a second 12 MB Python runtime just to be able to delete itself.

The awkward part is that a program cannot delete the folder it is running from. So this
does everything it can immediately -- shortcuts, the Add/Remove Programs entry -- and hands
the folder itself to a detached command that waits two seconds for this process to exit.
"""

from __future__ import annotations

import ctypes
import logging
import subprocess
import sys
import tempfile
import winreg
from pathlib import Path

from shared import paths
from logic import taskbar

log = logging.getLogger(__name__)

REGISTRY_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\GameLauncher"
# The same list as packaging/installer.py's, kept in step with it (Phase 68). Nothing here
# reads it: an uninstall asks first, and keeping the data removes only the program
# (_internal and the exe), so every data file stays -- the database among them.
USER_DATA = ("config.json", "overrides.json", "catalog.json", "cache", "library.db", "library.db-journal",
             "launcher.log", "launcher.log.1", "launcher.log.2")

MB_OK, MB_YESNO = 0x0, 0x4
MB_ICONERROR, MB_ICONQUESTION, MB_ICONINFO = 0x10, 0x20, 0x40
MB_TOPMOST = 0x40000
IDYES = 6

DETACHED_PROCESS = 0x00000008
CREATE_NO_WINDOW = 0x08000000


# Set by run(). Every message box waits for a click, and an uninstall started with --quiet
# has no one to click it, so in that mode they all become stderr lines instead.
QUIET = False


def _message(text: str, flags: int = MB_OK | MB_ICONINFO) -> int:
    if QUIET:
        sys.stderr.write(text.replace("\n\n", " ").replace("\n", " ") + "\n")
        return 0
    return ctypes.windll.user32.MessageBoxW(None, text, taskbar.DISPLAY_NAME, flags | MB_TOPMOST)


def _ask(text: str) -> bool:
    return _message(text, MB_YESNO | MB_ICONQUESTION) == IDYES


def looks_installed(folder: Path) -> bool:
    """Refuse to delete anything that is not unmistakably an installed copy of this app.

    Both marks have to be present. A folder holding GameLauncher.exe *and* the _internal
    directory a frozen build produces is ours; anything else is someone else's data.
    """
    return (folder / "GameLauncher.exe").is_file() and (folder / "_internal").is_dir()


def remove_shortcuts() -> list[Path]:
    """Delete only shortcuts that declare our app id, never merely ones with our name."""
    removed = []
    for folder in taskbar.shortcut_folders().values():
        for tv in (False, True):
            path = folder / f"{taskbar.display_name(tv)}.lnk"
            if not path.is_file():
                continue
            declared = taskbar.read_shortcut(path).get("app_id", "")
            if declared != taskbar.app_id(tv):
                log.info("leaving %s alone: it declares %r, not ours", path, declared)
                continue
            try:
                path.unlink()
                removed.append(path)
            except OSError as exc:
                log.warning("could not remove %s: %s", path, exc)
    return removed


def remove_registry_entry() -> bool:
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEY)
    except FileNotFoundError:
        return True  # never registered, or already gone
    except OSError as exc:
        log.warning("could not remove the Add/Remove Programs entry: %s", exc)
        return False
    return True


def schedule_removal(folder: Path, keep_data: bool) -> bool:
    """Hand the folder to a detached command that runs once this process has exited."""
    if not looks_installed(folder):
        log.error("refusing to delete %s: it does not look like an installed copy", folder)
        return False

    if keep_data:
        targets = f'rmdir /s /q "{folder / "_internal"}" & del /q "{folder / "GameLauncher.exe"}"'
    else:
        targets = f'rmdir /s /q "{folder}"'
    # ping, not timeout: timeout needs a console and this process is detached from one.
    command = f"cmd /c ping 127.0.0.1 -n 3 >nul & {targets}"
    try:
        subprocess.Popen(
            command,
            # Anywhere but the folder being deleted. A process cannot remove its own
            # working directory, so inheriting this one would make the delete fail.
            cwd=tempfile.gettempdir(),
            creationflags=DETACHED_PROCESS | CREATE_NO_WINDOW,
        )
    except OSError as exc:
        log.error("could not schedule the removal of %s: %s", folder, exc)
        return False
    return True


def report_failure(details: str, quiet: bool = False) -> None:
    """Say an uninstall went wrong, in a way that cannot hang an unattended run."""
    if quiet:
        sys.stderr.write(details)
        return
    _message(
        f"{taskbar.DISPLAY_NAME} could not be removed.\n\nNothing was deleted.\n\n"
        f"{details.strip().splitlines()[-1]}",
        MB_OK | MB_ICONERROR,
    )


def run(quiet: bool = False) -> int:
    global QUIET
    QUIET = quiet
    if not paths.FROZEN:
        _message(
            "This is the version running from source, so there is nothing to uninstall.\n\n"
            "Delete the project folder instead.",
            MB_OK | MB_ICONERROR,
        )
        return 1

    folder = paths.program_dir()
    if not looks_installed(folder):
        _message(f"This does not look like an installed copy:\n\n{folder}", MB_OK | MB_ICONERROR)
        return 1

    keep_data = True
    if not quiet:
        if not _ask(f"Remove {taskbar.DISPLAY_NAME}?\n\nIt will be deleted from:\n{folder}"):
            return 1
        keep_data = not _ask(
            "Also delete your settings, playtime and the artwork you picked?\n\n"
            "Yes  -  remove everything\n"
            "No  -  keep them, so reinstalling restores your library"
        )

    removed = remove_shortcuts()
    remove_registry_entry()
    # Start with Windows (Phase 92): the Run value goes with the exe it starts.
    from logic import autostart

    autostart.remove_if_ours(sys.executable)
    if not schedule_removal(folder, keep_data):
        _message("The files could not be removed. Nothing was deleted.", MB_OK | MB_ICONERROR)
        return 1

    if not quiet:
        kept = "\n\nYour settings and playtime were kept." if keep_data else ""
        _message(f"{taskbar.DISPLAY_NAME} has been removed ({len(removed)} shortcuts).{kept}")
    return 0
