"""Phase 106's click-through: the launcher on a throwaway copy of your library, started as the first start after an
update -- What's new, then the tray question -- before it ever happens on your own library.

    & .venv\\Scripts\\python.exe tests\\try_whats_new.py        (PowerShell, from the project folder)

The copy says the version seen last was 1.2.8, so this version is "just updated": a second after the window
appears, "What's new in <this version>" opens -- the English of its notes, scrolling, Close. A second after you close
it, the tray question of Phase 99 (planted as not yet asked), never both at once. Then Settings -> About: What's new
opens the same notes; and Updates shows "See what's new in" the next version, from a sample answer planted for this
try -- not a real release: a copy run from source never asks GitHub. Close the window when done: the copy is thrown
away, and the last line says whether your real config, library and Run value are as they were. Nothing is asked of
the network.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import test_sandbox  # noqa: E402 -- before anything that reads the data

box = test_sandbox.start({"startup_scan": False, "allow_network": False, "version_seen": "1.2.8",
                          "tray_offer_shown": None})

import urllib.request  # noqa: E402


def _no_network(request, *args, **kwargs):
    raise OSError("this try asks nothing of the network")


urllib.request.urlopen = _no_network

from PySide6.QtWidgets import QApplication  # noqa: E402

from shared import version as _version  # noqa: E402 -- the next version, for the sample: never a real one

_major, _minor, _patch = _version.parse(_version.APP_VERSION)
NEXT = f"{_major}.{_minor}.{_patch + 1}"
SAMPLE = {"tag_name": f"v{NEXT}", "name": NEXT, "draft": False, "prerelease": False,
          "published_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
          "body": "## Română\n\nUn exemplu, pus doar pentru această încercare.\n\n## English\n\n"
                  "**A sample, planted for this try -- not a real release.** This is where the next version's own "
                  "notes would be: what it adds, in the friends' words, before they install it."}


def main() -> int:
    from presentation import ui_window
    from web import updates

    updates._keep(updates.paths.cache_dir(), updates.read(SAMPLE, datetime.now(timezone.utc)))
    updates.should_check = lambda config: (True, "")  # as an installed copy would, for the Updates row only
    app = QApplication.instance() or QApplication(sys.argv)
    window = ui_window.MainWindow()
    window.show()
    print(f"A copy of your library, its version seen 1.2.8: What's new in {_version.APP_VERSION} opens in a second, "
          f"then the tray question. Then Settings -> About: What's new, and Updates: See what's new in {NEXT} (a sample).")
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
