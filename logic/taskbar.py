"""How Windows sees this app: its taskbar identity, and the shortcuts that carry it.

Windows decides which taskbar button a window belongs to -- and what happens when you pin
that button -- from an "Application User Model ID". Two halves have to agree:

1. the process claims an id, before it creates any window;
2. a shortcut *declares the same id* in its property store.

With only the first half, "Pin to taskbar" has no shortcut to pin. It falls back to the exe
that started the process, which is pythonw.exe, and produces a pin called "Python" that runs
Python with no arguments and opens nothing. That is exactly what happened here, and it is
why the shortcuts are written from this module rather than by hand: a shortcut without the
id is worse than useless, because it looks correct until you try to pin it.

Normal and TV mode get different ids on purpose. If both shortcuts declared the same one,
Windows would have two candidates to pin and no way to choose, so pinning "Game Launcher"
could silently give you the fullscreen TV shortcut.
"""

from __future__ import annotations

import ctypes
import logging
import os
import sys
from pathlib import Path

from shared import paths

log = logging.getLogger(__name__)

HERE = paths.program_dir()
ICON_PATH = paths.resource_dir() / "launcher.ico"
SCRIPT_PATH = HERE / "launcher.py"
PYTHONW_PATH = HERE / ".venv" / "Scripts" / "pythonw.exe"

APP_ID = "Andrei.GameLauncher"
APP_ID_TV = "Andrei.GameLauncher.TV"

DISPLAY_NAME = "Game Launcher"
DISPLAY_NAME_TV = "Game Launcher (TV)"

DESCRIPTION = "Your games from folders, Steam, GOG, Epic and Game Pass in one grid"
DESCRIPTION_TV = "Game Launcher in TV mode: fullscreen, larger, controller button hints"

# SHGetPropertyStoreFromParsingName flags, and the COM error meaning "this thread already
# has COM running in the other apartment model", which is not a failure for our purposes.
GPS_DEFAULT = 0x0
GPS_READWRITE = 0x2
RPC_E_CHANGED_MODE = -2147417850
SHCNF_PATHW = 0x0005  # the wide-character form; shellcon only exposes the ANSI one


def app_id(tv: bool = False) -> str:
    return APP_ID_TV if tv else APP_ID


def display_name(tv: bool = False) -> str:
    return DISPLAY_NAME_TV if tv else DISPLAY_NAME


def launch_command(tv: bool = False) -> tuple[Path, str, Path]:
    """What a shortcut has to run: (program, arguments, icon source).

    Installed, the program is the exe itself and it carries the icon in its own resources.
    Run from source it is the venv's pythonw with launcher.py as an argument, and the icon
    comes from the .ico file. Getting this wrong writes a shortcut that opens nothing, so
    it is one function rather than a guess at each call site.
    """
    tail = " --tv" if tv else ""
    if paths.FROZEN:
        exe = Path(sys.executable).resolve()
        return exe, tail.strip(), exe
    return PYTHONW_PATH, f'"{SCRIPT_PATH}"{tail}', ICON_PATH


def relaunch_command(tv: bool = False) -> str:
    """The command line Windows should run for a pin made from the live window."""
    program, arguments, _ = launch_command(tv)
    return f'"{program}" {arguments}'.rstrip()


# -- part one: the running process -----------------------------------------------------------


def claim_identity(tv: bool = False) -> bool:
    """Tell Windows this process is its own application, not an instance of Python.

    Must be called before any window exists; afterwards it has no effect.
    """
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id(tv))
    except (AttributeError, OSError) as exc:
        log.warning("could not set the taskbar identity: %s", exc)
        return False
    return True


def current_identity() -> str:
    """Read the id back out of Windows. Empty if none was set."""
    buffer = ctypes.c_wchar_p()
    try:
        result = ctypes.windll.shell32.GetCurrentProcessExplicitAppUserModelID(
            ctypes.byref(buffer)
        )
    except (AttributeError, OSError) as exc:
        log.warning("could not read the taskbar identity: %s", exc)
        return ""
    return buffer.value or "" if result == 0 else ""


def tag_window(hwnd: int, tv: bool | None = None) -> bool:
    """Give one window everything Windows needs to pin it without a shortcut.

    The process-wide id is what groups the taskbar button; these three properties are what
    let Windows build a working pin, and a jump list headed with our name and icon, straight
    from the live window. Belt and braces: if the shortcuts are ever missing or moved, this
    is what keeps "Pin to taskbar" honest.

    `tv` defaults to whichever id the process already claimed, so the window can never
    disagree with the process about which shortcut it came from. Note that this follows the
    shortcut used to *start* the app, not the mode it is in now: switching to TV mode from
    inside the normal window must still pin the normal shortcut.
    """
    if not hwnd:
        log.warning("no window handle to tag")
        return False
    if tv is None:
        tv = current_identity() == APP_ID_TV
    try:
        import pythoncom
        from win32comext.propsys import propsys, pscon
    except ImportError as exc:
        log.warning("pywin32's property system is unavailable, so the window is untagged: %s", exc)
        return False

    if not _ensure_com():
        return False
    try:
        store = propsys.SHGetPropertyStoreForWindow(int(hwnd), propsys.IID_IPropertyStore)
        for key, value in (
            (pscon.PKEY_AppUserModel_ID, app_id(tv)),
            (pscon.PKEY_AppUserModel_RelaunchCommand, relaunch_command(tv)),
            (pscon.PKEY_AppUserModel_RelaunchDisplayNameResource, display_name(tv)),
            (pscon.PKEY_AppUserModel_RelaunchIconResource, f"{ICON_PATH},0"),
        ):
            store.SetValue(key, propsys.PROPVARIANTType(value, pythoncom.VT_LPWSTR))
        store.Commit()
    except Exception as exc:  # pywintypes.com_error and anything else COM throws
        log.warning("could not tag the window for the taskbar: %s", exc)
        return False
    log.info("tagged the window as %s", app_id(tv))
    return True


def _ensure_com() -> bool:
    import pythoncom

    try:
        pythoncom.CoInitialize()
    except Exception as exc:
        code = getattr(exc, "hresult", getattr(exc, "args", [None])[0])
        if code == RPC_E_CHANGED_MODE:
            return True  # Qt already started COM here, in the other apartment. Fine.
        log.warning("COM would not start, so Windows shell properties are unavailable: %s", exc)
        return False
    return True


# -- part two: the shortcuts that declare the same id -----------------------------------------


def shortcut_folders() -> dict[str, Path]:
    """Desktop for reaching it, Start Menu because that is what Windows Search indexes."""
    return {
        "Desktop": Path(os.path.expanduser("~")) / "Desktop",
        "Start Menu": Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs",
    }


def write_shortcuts(folders: dict[str, Path] | None = None) -> list[Path]:
    """(Re)create all four shortcuts, each declaring its app id.

    They hold absolute paths, so this has to be re-run if the project folder ever moves.
    """
    import pythoncom
    from win32com.shell import shell
    from win32comext.propsys import propsys, pscon

    for required in {p for tv in (False, True) for p in launch_command(tv)[::2]}:
        if not required.is_file():
            raise FileNotFoundError(required)
    if not _ensure_com():
        raise RuntimeError("COM is unavailable, so no shortcut can be written")

    written: list[Path] = []
    for folder in (folders or shortcut_folders()).values():
        folder.mkdir(parents=True, exist_ok=True)
        for tv in (False, True):
            program, arguments, icon = launch_command(tv)
            path = folder / f"{display_name(tv)}.lnk"
            link = pythoncom.CoCreateInstance(
                shell.CLSID_ShellLink, None, pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IShellLink
            )
            link.SetPath(str(program))
            link.SetArguments(arguments)
            link.SetWorkingDirectory(str(HERE))
            link.SetIconLocation(str(icon), 0)
            link.SetDescription(DESCRIPTION_TV if tv else DESCRIPTION)

            # The whole point: stamp the id before saving, so the file is never on disk in
            # the state that produces a "Python" pin.
            store = link.QueryInterface(propsys.IID_IPropertyStore)
            store.SetValue(
                pscon.PKEY_AppUserModel_ID,
                propsys.PROPVARIANTType(app_id(tv), pythoncom.VT_LPWSTR),
            )
            store.Commit()

            link.QueryInterface(pythoncom.IID_IPersistFile).Save(str(path), True)
            _notify_shell(path)
            written.append(path)
            log.info("wrote %s declaring %s", path, app_id(tv))
    return written


def _notify_shell(path: Path) -> None:
    """Tell Explorer the shortcut changed, so it re-reads it without a sign-out."""
    from win32com.shell import shell, shellcon

    try:
        # SHCNF_PATHW, not shellcon.SHCNF_PATH: the ANSI form wants bytes and would mangle
        # any non-ASCII character in the path.
        shell.SHChangeNotify(
            shellcon.SHCNE_UPDATEITEM, SHCNF_PATHW | shellcon.SHCNF_FLUSH, str(path), None
        )
    except Exception as exc:
        log.warning("Explorer was not told about %s, so it may need a sign-out: %s", path, exc)


def read_shortcut(path: str | Path) -> dict[str, str]:
    """What a .lnk actually says, for checking rather than trusting."""
    import pythoncom
    from win32com.shell import shell
    from win32comext.propsys import propsys, pscon

    if not _ensure_com():
        return {}
    link = pythoncom.CoCreateInstance(
        shell.CLSID_ShellLink, None, pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IShellLink
    )
    link.QueryInterface(pythoncom.IID_IPersistFile).Load(str(path))
    target, _ = link.GetPath(shell.SLGP_RAWPATH)
    icon, index = link.GetIconLocation()
    store = propsys.SHGetPropertyStoreFromParsingName(
        str(path), None, GPS_DEFAULT, propsys.IID_IPropertyStore
    )
    return {
        "target": target,
        "arguments": link.GetArguments(),
        "working_dir": link.GetWorkingDirectory(),
        "icon": f"{icon},{index}",
        "app_id": store.GetValue(pscon.PKEY_AppUserModel_ID).GetValue() or "",
    }
