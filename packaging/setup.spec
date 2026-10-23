# GameLauncher-Setup.exe: the installer, with the zipped app carried inside it.
#
# One file, unlike the app: an installer runs once, so the unpack-to-temp cost that makes
# one-file wrong for the launcher is irrelevant here, and one file is the whole point.
#
# Nothing Qt-shaped is allowed in. The installer only needs the standard library, and
# bundling a second GUI toolkit would add tens of megabytes to a program that shows three
# message boxes.

import os

PROJECT = os.path.dirname(SPECPATH)
PAYLOAD = os.path.join(PROJECT, "build", "payload.zip")

if not os.path.isfile(PAYLOAD):
    raise SystemExit("build/payload.zip is missing -- run packaging/build.py, not this spec")

a = Analysis(
    [os.path.join(SPECPATH, "installer.py")],
    pathex=[SPECPATH],
    datas=[(PAYLOAD, ".")],
    excludes=[
        "PySide6", "shiboken6", "pygame", "pefile", "vdf",
        "win32com", "win32comext", "pythoncom", "pywintypes",
        "tkinter", "unittest", "pydoc_data", "test", "PyInstaller",
    ],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="GameLauncher-Setup",
    console=False,
    icon=os.path.join(PROJECT, "launcher.ico"),
)
