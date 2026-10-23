"""Phase 100: release 1.2.8 -- For you and report 9 (Phase 98), the one question, the accent, Starting and the
genre pill (Phase 99) go to the friends.

  1. the version: 1.2.8, newer than the 1.2.7 the friends have;
  2. what an update needs: the schema 1.2.7 shipped is this one's (version 7, the last script 007), so a
     friend's library is not upgraded; the friends' path is checked by check_installer.py --over, which now
     answers the one question a friend meets at the start after the update and reads, the way a screen reader
     does, the For you place and Settings' Accent row on the installed copy's own screen;
  3. the icon: launcher.ico is the one the user gave on 19 October, and check_installer.py looks for it in the
     build and in the program's and the installer's own icons;
  4. the documents: CITESTE-MA names 1.2.8 and what it brings, on its one page; DISTRIBUTIE lists 1.2.8 and
     what it brings, and the notes in two languages; CLAUDE.md, its version line and its size; the layers; the
     real data untouched.

On a throwaway copy of the data; the network is blocked.
"""
import hashlib
import subprocess
import sys
import urllib.request
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import sources  # the build log's notes (Phase 91)
import test_sandbox

box = test_sandbox.start()
attempts: list[str] = []


def no_network(request, *args, **kwargs):
    attempts.append(getattr(request, "full_url", str(request)))
    raise OSError("the network is blocked in this suite")


urllib.request.urlopen = no_network

from data_access import library_db
from presentation import ui_offer, ui_rules
from shared import version

passed = failed = 0


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"   PASS  {name}")
    else:
        failed += 1
        print(f"   FAIL  {name}   {detail}")


def git(*args) -> str:
    return subprocess.run(["git", *args], cwd=PROJECT, capture_output=True, text=True, encoding="utf-8").stdout


print("=== 1. the version ===")
# Its release's own version, read at its publish commit (176b287): a later release raises it (Phase 104: 1.2.9).
check("version 1.2.8 at its release", 'APP_VERSION = "1.2.8"' in git("show", "176b287:shared/version.py"),
      version.APP_VERSION)
check("newer than 1.2.7, so the friends' copies offer it", version.is_newer(version.APP_VERSION, "1.2.7"))

print("\n=== 2. what an update needs ===")
RELEASE = "c4127b2"  # 1.2.7, as published
shipped = sorted(git("ls-tree", "--name-only", f"{RELEASE}:data_access/upgrades").split())
scripts = sorted(p.name for p in (PROJECT / "data_access" / "upgrades").glob("*.sql"))
check("the schema 1.2.7 shipped is this one's: version 7, the last script 007, nothing to upgrade",
      "SCHEMA_VERSION = 7 " in git("show", f"{RELEASE}:data_access/library_db.py")
      and "SCHEMA_VERSION = 7 " in git("show", "176b287:data_access/library_db.py")  # 1.2.8, as published
      and shipped == sorted(git("ls-tree", "--name-only", "176b287:data_access/upgrades").split())
      and shipped[-1].startswith("007_"), (shipped, scripts))
check("and no upgrade script or schema line changed in it", git("diff", "--stat", RELEASE, "176b287", "--",
                                                                 "data_access/schema.sql", "data_access/upgrades") == "")
installer_check = (PROJECT / "tests" / "check_installer.py").read_text(encoding="utf-8")
check("check_installer.py still takes the friends' path (--over)", '"--over"' in installer_check)
check("and meets the one question by its own title, at the start after a first run's and after the update",
      "OFFER = ui_offer.TITLE" in installer_check and installer_check.count("answer_offer(app,") == 2
      and ui_offer.TITLE == "Keep Game Launcher running?")
check("and reads For you and the Accent row with its colours off the installed copy's screen",
      installer_check.count("shows_whats_new(app,") == 2 and '"For you" in names' in installer_check
      and 'f"{name} accent" for name in ui_rules.ACCENTS' in installer_check and len(ui_rules.ACCENTS) == 5)
check("through Windows' UI Automation from PowerShell: no new dependency",
      "UIAutomationClient" in installer_check and '"powershell"' in installer_check)

print("\n=== 3. the icon (the user's, 19 October) ===")
icon = (PROJECT / "launcher.ico").read_bytes()
count = int.from_bytes(icon[4:6], "little")
sizes = sorted(icon[6 + 16 * i] or 256 for i in range(count))
pngs = all(icon[int.from_bytes(icon[18 + 16 * i:22 + 16 * i], "little"):][:8] == b"\x89PNG\r\n\x1a\n" for i in range(count))
check("launcher.ico is the one the user gave, from 16 to 256 pixels in nine PNG pictures",
      hashlib.sha256(icon).hexdigest().startswith("4ff3efdd08cc0258") and sizes == [16, 20, 24, 32, 40, 48, 64, 128, 256]
      and pngs, (sizes, pngs))
check("and check_installer.py looks for it in the build, the program's icon and the installer's",
      "icon_images(PROJECT / \"launcher.ico\")" in installer_check)

print("\n=== 4. the documents, the layers ===")
readme = (PROJECT / "docs" / "CITESTE-MA.md").read_text(encoding="utf-8").replace("\r\n", "\n")
distribution = (PROJECT / "docs" / "DISTRIBUTIE.md").read_text(encoding="utf-8").replace("\r\n", "\n")
claude = (PROJECT / "CLAUDE.md").read_text(encoding="utf-8").replace("\r\n", "\n")
check("CITESTE-MA names 1.2.8 and what it brings, still on one page", f"Versiunea {version.APP_VERSION}." in readme
      and all(w in readme for w in ("**For you**", "Settings → Accent", "**Starting…**", "după gen",
                                    "te întreabă o dată"))
      and len(readme.splitlines()) <= 110, len(readme.splitlines()))
check("DISTRIBUTIE lists 1.2.8 and what it brings", "**1.2.8** (faza 100) aduce locul **For you**" in distribution
      and f'"{version.APP_VERSION}"' in distribution and f"Game Launcher {version.APP_VERSION}, built" in distribution)
check("and says the notes go in Romanian and English", "notele sunt în română și în engleză" in distribution)
check("CLAUDE.md has the phase, its notes and the version's line", "| 100 |" in claude
      and "## Phase 100 notes" in sources.build_log() and "1.2.8, Phase 100" in claude)
old = git("show", "before-phase-91:CLAUDE.md").replace("\r\n", "\n")
check("CLAUDE.md under a quarter of its size before Phase 91 (suite 91), with this phase in it",
      len(claude.encode("utf-8")) < len(old.encode("utf-8")) / 4, (len(claude.encode("utf-8")), len(old.encode("utf-8")) / 4))
layers = subprocess.run([sys.executable, str(PROJECT / "tests" / "check_layers.py")], capture_output=True, text=True,
                        encoding="utf-8", errors="replace")
check("no import points up a layer; sqlite3 only in data_access/", layers.returncode == 0, layers.stdout[-300:])
check("nothing in this suite reached the network", attempts == [], attempts)

print("\n=== 5. the real library is exactly as it was found ===")
changed = box.finish()
check("config.json, the library database and the Run key's value are unchanged", not changed, changed)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
