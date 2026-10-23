"""Phase 105's click-through: the launcher on a throwaway copy of your library, with planted games that have no
cover, to try Settings -> Fill missing covers... before it ever touches your own library.

    & .venv\\Scripts\\python.exe tests\\try_fill_covers.py        (PowerShell, from the project folder)

A launcher window opens on the copy -- your own launcher in the tray is not disturbed: the copy has its own data
folder, so its own lock. Five planted games without a cover lead the grid (NEW): four real titles SteamGridDB knows,
and one name nothing is like. In Settings -> Artwork and the internet, Missing covers says how many; Fill missing
covers... looks them up on the real SteamGridDB with your key, as your click asks. Close the window when done: the
copy is thrown away, and the last lines here say whether your real config, library and Run value are as they were.

Nothing of yours is written: the covers land in the copy's own cache, the backup in the copy's own backups.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import test_sandbox  # noqa: E402 -- before anything that reads the data

# No scan at the start: a scan would replace the planted games with what is really on disk. Network lookups on, as
# yours are: a test copy turns them off, and the button needs them.
box = test_sandbox.start({"startup_scan": False, "allow_network": True})

from PySide6.QtWidgets import QApplication  # noqa: E402

PLANTED = ("Hollow Knight", "Celeste", "Hades", "Stardew Valley", "Zzqx Planted Game")


def main() -> int:
    from presentation import ui_window
    from shared.models import GameEntry

    app = QApplication.instance() or QApplication(sys.argv)
    window = ui_window.MainWindow()
    window.show()
    entries = []
    for name in PLANTED:
        folder = Path(box.folder) / "planted games" / name
        folder.mkdir(parents=True, exist_ok=True)
        entries.append(GameEntry(source="folders", source_id=str(folder / f"{name}.exe"), display_name=name,
                                 install_dir=str(folder), launch_kind="exe", launch_target=str(folder / f"{name}.exe"),
                                 working_dir=str(folder), icon_hint="", size_on_disk=0, detection="heuristic"))
    window.entries.extend(entries)
    window.reload_views()
    window.statusBar().showMessage(f"A throwaway copy: {len(PLANTED)} planted games without a cover. "
                                   "Settings -> Artwork and the internet -> Fill missing covers...", 15000)
    print(f"A copy of your library, with {len(PLANTED)} planted games without a cover: {', '.join(PLANTED)}.")
    print("Settings -> Artwork and the internet -> Missing covers -> Fill missing covers... -> Look them up.")
    print("Close the window when done.")
    return app.exec()


if __name__ == "__main__":
    code = 1
    try:
        code = main()
    finally:
        changed = box.finish()
        print("Your real config, library and Run value: " + ("unchanged." if not changed else f"CHANGED: {changed}"))
    raise SystemExit(code)
