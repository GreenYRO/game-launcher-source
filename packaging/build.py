"""Build GameLauncher-Setup.exe.

    .venv\\Scripts\\python.exe packaging\\build.py      (from the project folder)

Three steps, in order, because each feeds the next:

1. freeze the launcher into a folder of files      -> build/app/GameLauncher/
2. zip that folder                                 -> build/payload.zip
3. freeze the installer with the zip inside it     -> dist/GameLauncher-Setup.exe

Step 3 is a one-file build on purpose: an installer is run once, so the slow unpack that
makes one-file wrong for the app itself costs nothing here.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
import time
import zipfile
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
sys.path.insert(0, str(PROJECT))

from shared import version  # noqa: E402 -- the one place the version lives (Phase 77)
BUILD = PROJECT / "build"
DIST = PROJECT / "dist"
APP_DIR = BUILD / "app" / "GameLauncher"
PAYLOAD = BUILD / "payload.zip"

VERSION = version.APP_VERSION  # not a number of its own: shared/version.py is the one source


def megabytes(path: Path) -> float:
    if path.is_file():
        return path.stat().st_size / 1024 / 1024
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / 1024 / 1024


def run_pyinstaller(spec: Path, distpath: Path, workpath: Path) -> None:
    command = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--distpath", str(distpath),
        "--workpath", str(workpath),
        str(spec),
    ]
    result = subprocess.run(command, cwd=str(PROJECT), capture_output=True, text=True)
    if result.returncode != 0:
        sys.stderr.write(result.stdout[-4000:])
        sys.stderr.write(result.stderr[-4000:])
        raise SystemExit(f"PyInstaller failed on {spec.name}")


def stamp_version(app_dir: Path = APP_DIR) -> None:
    """Leave the version where the installer can read it for Add/Remove Programs, and the day
    of the build beside it, which the installed app shows in Settings."""
    internal = app_dir / "_internal"
    (internal / version.VERSION_FILE).write_text(VERSION + "\n", encoding="utf-8")
    (internal / version.BUILD_FILE).write_text(date.today().isoformat() + "\n", encoding="utf-8")


def make_payload() -> None:
    if PAYLOAD.exists():
        PAYLOAD.unlink()
    # Deflate rather than store: it roughly halves the installer, and the one-off cost of
    # unpacking on install is a second or two.
    with zipfile.ZipFile(PAYLOAD, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for item in sorted(APP_DIR.rglob("*")):
            if item.is_file():
                archive.write(item, item.relative_to(APP_DIR).as_posix())


def _writable_and_again(func, path, exc) -> None:
    r"""rmtree's error handler: a read-only folder loses the mark and is removed again.

    PyInstaller copies folders with their attributes, and data_access\upgrades carries Windows'
    ReadOnly mark (the October folders' mystery, CLAUDE.md Phase 69): the second build over an
    existing build\ stopped on it, "Access is denied" (found in Phase 79). Anything else raises.
    """
    if not isinstance(exc, PermissionError):
        raise exc
    os.chmod(path, stat.S_IWRITE)
    func(path)


def check_notes(number: str = VERSION) -> str:
    """"" when this version's release notes are written -- docs/release-notes/<version>.md, the Romanian and the
    English under their headings (Phase 106) -- else why the build is refused. The first thing main() does; a test
    calls it without building."""
    from logic import whats_new
    from shared import rules

    ok, why = whats_new.ready(number, PROJECT.joinpath(*rules.RELEASE_NOTES_DIR))
    return "" if ok else why


def main() -> int:
    started = time.time()
    refused = check_notes()
    if refused:
        print(f"Not built: {refused}.")
        return 1
    for stale in (BUILD, DIST):
        if stale.exists():
            shutil.rmtree(stale, onexc=_writable_and_again)

    print("1/3  freezing the launcher ...")
    run_pyinstaller(HERE / "app.spec", BUILD / "app", BUILD / "work-app")
    stamp_version()
    print(f"     {megabytes(APP_DIR):.0f} MB, {sum(1 for _ in APP_DIR.rglob('*') if _.is_file())} files")

    print("2/3  packing it ...")
    make_payload()
    print(f"     {megabytes(PAYLOAD):.0f} MB compressed")

    print("3/3  building the installer ...")
    run_pyinstaller(HERE / "setup.spec", DIST, BUILD / "work-setup")

    setup = DIST / "GameLauncher-Setup.exe"
    if not setup.is_file():
        raise SystemExit("the installer was not produced")
    print(f"\nDone in {time.time() - started:.0f}s")
    print(f"   {setup}   ({megabytes(setup):.0f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
