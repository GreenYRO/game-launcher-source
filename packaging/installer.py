"""What GameLauncher-Setup.exe actually does.

Deliberately plain: standard library, ctypes message boxes, no Qt. The installer must not
carry a second copy of a GUI toolkit when the thing it is installing already contains one.

It installs per user, into %LOCALAPPDATA%\\Programs\\Game Launcher, so it never needs an
administrator password and the installed folder stays writable -- which matters, because
the app keeps config.json, overrides.json, catalog.json and cache/ right beside its exe.
That is also what makes a backup easy: copy that one folder and you have everything.
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import winreg
import zipfile
from pathlib import Path

APP_NAME = "Game Launcher"
EXE_NAME = "GameLauncher.exe"
PAYLOAD_NAME = "payload.zip"
REGISTRY_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\GameLauncher"

# Everything the user would be upset to lose. A reinstall must step around these. The
# library database and its rollback journal (Phase 68), before an installed copy ever uses
# them: an upgrade deletes every other file at the top of the folder. And the log with its two
# older copies (Phase 78): a friend who updates and then has a problem sends the diagnostics
# bundle (Phase 77), and the log from before the update is the half that explains it. Folders
# -- cache, backups, save_backups -- are never removed by an update; only _internal is.
USER_DATA = ("config.json", "overrides.json", "catalog.json", "cache", "library.db", "library.db-journal",
             "launcher.log", "launcher.log.1", "launcher.log.2")

MB_OK, MB_YESNO = 0x0, 0x4
MB_ICONERROR, MB_ICONQUESTION, MB_ICONINFO = 0x10, 0x20, 0x40
MB_TOPMOST = 0x40000
IDYES = 6


# Set by --silent. A message box waits for a click, so in an unattended run even a
# non-fatal warning deep inside would hang the install forever.
SILENT = False


def message(text: str, flags: int = MB_OK | MB_ICONINFO) -> int:
    if SILENT:
        sys.stderr.write(text.replace("\n\n", " ").replace("\n", " ") + "\n")
        return 0
    return ctypes.windll.user32.MessageBoxW(None, text, APP_NAME, flags | MB_TOPMOST)


def ask(text: str) -> bool:
    return message(text, MB_YESNO | MB_ICONQUESTION) == IDYES


def install_dir() -> Path:
    root = os.environ.get("LOCALAPPDATA") or os.path.expanduser(r"~\AppData\Local")
    return Path(root) / "Programs" / APP_NAME


def payload_path() -> Path:
    """The zipped app, carried inside this exe."""
    base = Path(getattr(sys, "_MEIPASS", "") or Path(__file__).resolve().parent)
    return base / PAYLOAD_NAME


def running_from(target: Path) -> bool:
    """True if a copy of the app in the target folder is open, which would lock its files."""
    exe = target / EXE_NAME
    if not exe.is_file():
        return False
    try:
        # Opening for append needs the same write access a replacement does, and asks
        # Windows the question directly instead of guessing from a process list.
        with open(exe, "ab"):
            return False
    except OSError:
        return True


def clear_program_files(target: Path) -> None:
    """Remove the previous program, and only the program."""
    import shutil

    internal = target / "_internal"
    if internal.is_dir():
        shutil.rmtree(internal)
    for leftover in target.glob("*"):
        if leftover.name not in USER_DATA and leftover.is_file():
            leftover.unlink()


def extract(payload: Path, target: Path) -> int:
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(payload) as archive:
        names = archive.namelist()
        archive.extractall(target)
    return len(names)


def make_shortcuts(target: Path) -> bool:
    """Let the app write its own shortcuts -- the same code path it has always used."""
    try:
        result = subprocess.run(
            [str(target / EXE_NAME), "--make-shortcuts"],
            cwd=str(target),
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        message(f"Installed, but the shortcuts could not be created:\n\n{exc}", MB_OK | MB_ICONERROR)
        return False
    if result.returncode != 0:
        message(
            "Installed, but the shortcuts could not be created:\n\n"
            f"{result.stderr.strip() or result.stdout.strip()}",
            MB_OK | MB_ICONERROR,
        )
        return False
    return True


def folder_size_kb(target: Path) -> int:
    return sum(f.stat().st_size for f in target.rglob("*") if f.is_file()) // 1024


def register(target: Path, version: str) -> None:
    """The Add/Remove Programs entry. Per user, so no administrator rights are involved."""
    exe = target / EXE_NAME
    values = {
        "DisplayName": APP_NAME,
        "DisplayIcon": str(exe),
        "DisplayVersion": version,
        "Publisher": "Andrei",
        "InstallLocation": str(target),
        "UninstallString": f'"{exe}" --uninstall',
        "QuietUninstallString": f'"{exe}" --uninstall --quiet',
    }
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEY) as key:
            for name, value in values.items():
                winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
            winreg.SetValueEx(key, "EstimatedSize", 0, winreg.REG_DWORD, folder_size_kb(target))
            for flag in ("NoModify", "NoRepair"):
                winreg.SetValueEx(key, flag, 0, winreg.REG_DWORD, 1)
    except OSError as exc:
        # Not fatal: the app is installed and works, it just will not be listed.
        message(
            f"Installed, but it could not be added to the list of installed apps:\n\n{exc}",
            MB_OK | MB_ICONERROR,
        )


def read_version(target: Path) -> str:
    """The version build.py stamped from shared/version.py (Phase 77) -- its first line only."""
    version_file = target / "_internal" / "VERSION"
    try:
        lines = version_file.read_text(encoding="utf-8").splitlines()
        return (lines[0].strip() if lines else "") or "1.0"
    except OSError:
        return "1.0"


def main() -> int:
    # --silent installs without asking and without opening the app afterwards. It exists so
    # the built installer itself can be tested, rather than only the source it was built
    # from, and it is what makes an unattended install possible at all.
    global SILENT
    SILENT = silent = "--silent" in sys.argv[1:]
    payload = payload_path()
    if not payload.is_file():
        message(f"This installer is incomplete: {PAYLOAD_NAME} is missing.", MB_OK | MB_ICONERROR)
        return 1

    target = install_dir()
    upgrading = (target / EXE_NAME).is_file()

    if running_from(target):
        if silent:
            sys.stderr.write(f"{APP_NAME} is open, so its files are locked: {target}\n")
            return 1
        message(
            # Since 1.2.6 a closed window can leave it running in the tray (Keep running): say how to quit.
            f"{APP_NAME} is open at the moment.\n\nPlease close it and run this again. If its icon is "
            "beside the clock, right-click it and choose Quit.",
            MB_OK | MB_ICONERROR,
        )
        return 1

    question = (
        f"Update {APP_NAME}?\n\nIt is already installed at:\n{target}\n\n"
        "Your games, playtime and chosen artwork are kept."
        if upgrading
        else f"Install {APP_NAME}?\n\nIt will go in:\n{target}\n\n"
        "Shortcuts are added to the Desktop and the Start Menu.\nNo administrator password "
        "is needed."
    )
    if not silent and not ask(question):
        return 1

    try:
        if upgrading:
            clear_program_files(target)
        extract(payload, target)
    except OSError as exc:
        if silent:
            sys.stderr.write(f"could not write the files: {exc}\n")
            return 1
        message(f"The files could not be written:\n\n{exc}", MB_OK | MB_ICONERROR)
        return 1

    make_shortcuts(target)
    register(target, read_version(target))

    verb = "updated" if upgrading else "installed"
    if silent:
        print(f"{verb} to {target}")
        return 0
    if ask(f"{APP_NAME} was {verb}.\n\nOpen it now?"):
        try:
            subprocess.Popen([str(target / EXE_NAME)], cwd=str(target))
        except OSError as exc:
            message(f"It is installed, but would not start:\n\n{exc}", MB_OK | MB_ICONERROR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
