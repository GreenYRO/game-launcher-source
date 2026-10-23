"""Entry point for the GUI.

    python launcher.py               normal
    python launcher.py --tv          start in TV mode
    python launcher.py --background  start hidden in the tray, if "Keep running" is on (Phase 92)
    python launcher.py -v            with the full discovery log on the console

One launcher at a time (Phase 92): a start while one is running asks it to show itself -- in TV
mode for --tv -- and ends; see adapters/single_instance.py.
"""

from __future__ import annotations

import argparse
import logging
import logging.handlers
import platform
import sys
import threading
import traceback
from pathlib import Path

import PySide6
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from shared import paths
from shared import rules
from shared import version
from adapters import single_instance
from logic import taskbar
from presentation.ui_window import MainWindow

log = logging.getLogger("launcher")

ICON_PATH = taskbar.ICON_PATH
CONSOLE_FORMAT = "%(levelname)-7s %(name)s: %(message)s"


def configure_logging(verbose: bool, log_file: Path | None) -> None:
    """The console, as always, plus a small rotating file while the window runs.

    The shortcuts start the launcher with pythonw.exe, which has no console at all: until
    Phase 26 everything it logged -- the traceback of a crash included -- went nowhere,
    and a problem reported from real use could only be reconstructed by guessing. The
    file is what makes "what happened?" answerable.

    No file for --make-shortcuts or --uninstall. Those are one-off jobs, and an uninstall
    must not hold a file open inside the folder it is about to delete.
    """
    level = logging.DEBUG if verbose else logging.INFO
    handlers: list[logging.Handler] = []
    if sys.stderr is not None:  # None under pythonw.exe
        console = logging.StreamHandler(sys.stderr)
        console.setFormatter(logging.Formatter(CONSOLE_FORMAT))
        handlers.append(console)
    problem = ""
    if log_file is not None:
        try:
            file_handler = logging.handlers.RotatingFileHandler(
                log_file,
                maxBytes=rules.LOG_MAX_BYTES,
                backupCount=rules.LOG_BACKUP_COUNT,
                encoding="utf-8",
            )
        except OSError as exc:
            problem = f"no log file at {log_file}: {exc}"  # reported once logging exists
        else:
            file_handler.setFormatter(logging.Formatter(rules.LOG_FORMAT))
            handlers.append(file_handler)
    logging.basicConfig(level=level, handlers=handlers, force=True)
    if problem:
        log.warning(problem)


def install_crash_logging() -> None:
    """Send anything uncaught to the log -- including an error inside a Qt slot.

    PySide6 reports an exception raised in a slot through sys.excepthook and carries on,
    so without this such an error vanished completely under pythonw.exe. The previous hook
    still runs afterwards, so a console, when there is one, prints it as before.
    """
    previous = sys.excepthook

    def excepthook(kind, value, tb) -> None:
        log.critical("uncaught exception", exc_info=(kind, value, tb))
        previous(kind, value, tb)

    previous_thread = threading.excepthook

    def thread_excepthook(args) -> None:
        name = args.thread.name if args.thread is not None else "?"
        log.critical(
            "uncaught exception in thread %s", name,
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )
        previous_thread(args)

    sys.excepthook = excepthook
    threading.excepthook = thread_excepthook


def application_icon() -> QIcon:
    if not ICON_PATH.is_file():
        log.warning("no icon at %s; the window will use the default", ICON_PATH)
        return QIcon()
    icon = QIcon(str(ICON_PATH))
    if icon.isNull():
        log.warning("%s would not load as an icon", ICON_PATH)
    return icon


WEDGED = ("Game Launcher is already running but not responding; check the tray or Task Manager.")


def second_start(name: str, tv: bool) -> int:
    """Another launcher holds the lock: ask it to show itself, and end. Never a second one.

    0 when it answered. When it did not -- it is wedged -- a plain message says so, and this start
    ends all the same: two launchers would write the library and take the readings twice.
    """
    if single_instance.hand_over(name, tv, rules.SINGLE_INSTANCE_TIMEOUT_MS):
        log.info("already running: it was asked to show itself%s; this start ends", " in TV mode" if tv else "")
        return 0
    log.warning("already running, but no answer within %d ms; this start ends", rules.SINGLE_INSTANCE_TIMEOUT_MS)
    QMessageBox.warning(None, "Game Launcher", WEDGED)
    return 1


def present(window: MainWindow, args) -> None:
    """Shown, in TV mode or not -- or hidden in the tray for --background, when that makes sense."""
    if args.background:
        if window.first_run:
            log.info("%s, but this is a first run: the window is shown to ask where the games are",
                     rules.BACKGROUND_ARGUMENT)
        elif not window.keep_running:
            log.info("%s with 'Keep running' off: there is nothing to hide into, so the window is shown",
                     rules.BACKGROUND_ARGUMENT)
        else:
            window.start_hidden()
            return
    # The flag wins for this run; the saved setting is what the plain shortcut uses.
    if args.tv or window.config.get("tv_mode"):
        window.set_tv_mode(True)
    else:
        window.show()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="launcher.py", description="Windows game launcher.")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument(
        "--tv",
        action="store_true",
        help="start in TV mode: fullscreen, larger, with controller button hints",
    )
    parser.add_argument(
        "--make-shortcuts",
        action="store_true",
        help="rewrite the Desktop and Start Menu shortcuts, then exit "
        "(needed if the project folder is ever moved or renamed)",
    )
    parser.add_argument(
        "--uninstall",
        action="store_true",
        help="remove an installed copy; this is what Add/Remove Programs calls",
    )
    parser.add_argument("--quiet", action="store_true", help="with --uninstall, ask nothing")
    parser.add_argument(
        rules.BACKGROUND_ARGUMENT,
        action="store_true",
        help="start hidden in the tray (what Start with Windows runs); shown if Keep running is off",
    )
    args = parser.parse_args(argv)

    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    one_off = args.make_shortcuts or args.uninstall
    configure_logging(args.verbose, None if one_off else paths.data_dir() / rules.LOG_FILENAME)

    if args.make_shortcuts:
        for path in taskbar.write_shortcuts():
            print(f"wrote {path}")
        return 0

    if args.uninstall:
        from logic import uninstall

        # A windowed build has nowhere to print a traceback, so PyInstaller shows it in a
        # modal dialog instead -- which, for an uninstall run from Add/Remove Programs with
        # no visible window, is a process that hangs forever waiting for a click nobody can
        # give. Catch it here and fail properly instead.
        try:
            return uninstall.run(quiet=args.quiet)
        except Exception:
            log.exception("uninstall failed")
            uninstall.report_failure(traceback.format_exc(), quiet=args.quiet)
            return 1

    install_crash_logging()
    log.info(
        "%s starting%s -- %s, Python %s, PySide6 %s",
        version.describe(),
        " in TV mode" if args.tv else " hidden in the tray" if args.background else "",
        "installed copy" if paths.FROZEN else "from source",
        platform.python_version(),
        PySide6.__version__,
    )

    # Before QApplication on purpose: after a window exists, Windows ignores it.
    taskbar.claim_identity(args.tv)

    app = QApplication(sys.argv[:1])
    app.setApplicationName("Game Launcher")
    app.setApplicationDisplayName("Game Launcher")
    app.setOrganizationName("Game Launcher")
    app.setDesktopFileName("Game Launcher")
    app.setWindowIcon(application_icon())

    # One launcher at a time (Phase 92): before anything reads or writes the library.
    name = single_instance.key(paths.data_dir())
    lock = single_instance.take(name)
    if lock is None:
        return second_start(name, args.tv)
    owner = single_instance.Owner(name, lock)

    window = MainWindow()
    owner.showRequested.connect(window.bring_forward)
    present(window, args)
    code = app.exec()
    owner.release()
    log.info("Game Launcher closed (exit code %s)", code)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
