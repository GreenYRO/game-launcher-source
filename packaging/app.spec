# The launcher itself, frozen into a folder of files with GameLauncher.exe at the top.
#
# A folder, not a single file: a one-file build unpacks its whole 136 MB into a temp
# directory on every start, which turns a two-second launch into ten. The folder is what
# the installer ships.

import os

from PyInstaller.utils.hooks import collect_submodules

PROJECT = os.path.dirname(SPECPATH)

hidden = collect_submodules("providers") + collect_submodules("web") + [
    # Reached through COM, so the import graph cannot see them.
    "win32com.shell",
    "win32com.shell.shell",
    "win32comext.propsys",
    "win32comext.propsys.propsys",
    "win32comext.propsys.pscon",
    # pywin32 imports this one lazily, from inside pywintypes, the first time a COM call
    # returns a time. Leaving it out builds cleanly and then fails at run time -- which is
    # exactly what happened: reading a shortcut raised ModuleNotFoundError.
    "win32timezone",
    # Imported inside a function in launcher.py, only when --uninstall is passed.
    "logic.uninstall",
]

# Qt ships far more than this app touches; it imports QtCore, QtGui and QtWidgets, nothing
# else. Dropping the rest is most of the difference between a 400 MB build and a 136 MB one.
QT_UNUSED = [
    "PySide6.Qt3DAnimation", "PySide6.Qt3DCore", "PySide6.Qt3DExtras", "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic", "PySide6.Qt3DRender", "PySide6.QtBluetooth", "PySide6.QtCharts",
    "PySide6.QtDataVisualization", "PySide6.QtDesigner", "PySide6.QtHelp",
    "PySide6.QtLocation", "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets",
    "PySide6.QtNfc", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets", "PySide6.QtPdf",
    "PySide6.QtPdfWidgets", "PySide6.QtPositioning", "PySide6.QtQml", "PySide6.QtQuick",
    "PySide6.QtQuick3D", "PySide6.QtQuickControls2", "PySide6.QtQuickWidgets",
    "PySide6.QtRemoteObjects", "PySide6.QtScxml", "PySide6.QtSensors", "PySide6.QtSerialBus",
    "PySide6.QtSerialPort", "PySide6.QtSpatialAudio", "PySide6.QtSql", "PySide6.QtStateMachine",
    "PySide6.QtTest", "PySide6.QtTextToSpeech", "PySide6.QtWebChannel", "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineQuick", "PySide6.QtWebEngineWidgets", "PySide6.QtWebSockets",
    "PySide6.QtXml",
]

a = Analysis(
    [os.path.join(PROJECT, "launcher.py")],
    pathex=[PROJECT],
    datas=[
        (os.path.join(PROJECT, "launcher.ico"), "."),
        # Read through paths.resource_dir(), which is _internal/ in the installed copy: the
        # database's schema (Phase 67) and the bundled fonts -- Inter and Phosphor, with their
        # licences (Phases 54, 59, 62). Without them the installed program fell back to
        # Windows' own fonts and icons, and could not create its database.
        (os.path.join(PROJECT, "data_access", "schema.sql"), "data_access"),
        (os.path.join(PROJECT, "data_access", "upgrades"), os.path.join("data_access", "upgrades")),
        (os.path.join(PROJECT, "presentation", "fonts"), os.path.join("presentation", "fonts")),
        # Each version's release notes (Phase 106): What's new reads this version's from here; build.py refuses a
        # version without its own.
        (os.path.join(PROJECT, "docs", "release-notes"), os.path.join("docs", "release-notes")),
    ],
    hiddenimports=hidden,
    excludes=QT_UNUSED + ["tkinter", "unittest", "pydoc_data", "test", "PyInstaller"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="GameLauncher",
    console=False,
    icon=os.path.join(PROJECT, "launcher.ico"),
)
coll = COLLECT(exe, a.binaries, a.datas, name="GameLauncher")
