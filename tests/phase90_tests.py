"""Phase 90: release 1.2.5 -- the wishlist's three extensions (Phase 89) go to the friends.

  1. the version: 1.2.5, newer than the 1.2.4 the friends have;
  2. what an update needs: the schema is the one 1.2.4 left (no upgrade script added), and the
     friends' path is checked by check_installer.py --over the installer before this one;
  3. the documents: CITESTE-MA names 1.2.5 and the eight reports; DISTRIBUTIE lists 1.2.5 and what it
     brings; CLAUDE.md; the layers; the real data untouched.

On a throwaway copy of the data; the network is blocked.
"""
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
from logic import reports
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


print("=== 1. the version ===")
# 1.2.5 or later: Phase 89 is in every release after it (1.2.6, Phase 95, the tray and the watch).
check("version 1.2.5 or later", version.parse(version.APP_VERSION) >= (1, 2, 5), version.APP_VERSION)
check("newer than 1.2.4, so the friends' copies offer it", version.is_newer(version.APP_VERSION, "1.2.4"))

print("\n=== 2. what an update needs ===")
# What 1.2.5 shipped, read at its own commit (096f816): Phase 93 brought version 7 after it.
RELEASE = "096f816"
shipped = subprocess.run(["git", "show", f"{RELEASE}:data_access/library_db.py"], cwd=PROJECT, capture_output=True,
                         text=True, encoding="utf-8").stdout
scripts = sorted(subprocess.run(["git", "ls-tree", "--name-only", f"{RELEASE}:data_access/upgrades"], cwd=PROJECT,
                                capture_output=True, text=True, encoding="utf-8").stdout.split())
check("the schema 1.2.5 shipped is 1.2.4's: version 6, the last script 006, nothing to upgrade",
      "SCHEMA_VERSION = 6 " in shipped and scripts and scripts[-1].startswith("006_"), scripts)
check("eight reports in 1.2.5, the eighth Stated and revealed (a ninth since Phase 98)", len(reports.BUILDERS) >= 8
      and reports.BUILDERS[7].__name__ == "preference")
installer_check = (PROJECT / "tests" / "check_installer.py").read_text(encoding="utf-8")
check("check_installer.py still takes the friends' path (--over)", '"--over"' in installer_check)

print("\n=== 3. the documents, the layers ===")
readme = (PROJECT / "docs" / "CITESTE-MA.md").read_text(encoding="utf-8")
distribution = (PROJECT / "docs" / "DISTRIBUTIE.md").read_text(encoding="utf-8")
claude = (PROJECT / "CLAUDE.md").read_text(encoding="utf-8")
check("CITESTE-MA names the current version and the reports (eight, nine since Phase 98, ten since 102, eleven since 103)",
      f"Versiunea {version.APP_VERSION}." in readme
      and any(f"{n} rapoarte" in readme for n in ("opt", "nouă", "zece", "unsprezece"))
      and "șapte rapoarte" not in readme)
check("DISTRIBUTIE lists 1.2.5 and what it brings", "**1.2.5** (faza 90) aduce potrivirea mai precisă" in distribution
      and f'"{version.APP_VERSION}"' in distribution)
check("CLAUDE.md has the phase and its notes", "| 90 |" in claude and "## Phase 90 notes" in sources.build_log())
layers = subprocess.run([sys.executable, str(PROJECT / "tests" / "check_layers.py")], capture_output=True, text=True,
                        encoding="utf-8", errors="replace")
check("no import points up a layer; sqlite3 only in data_access/", layers.returncode == 0, layers.stdout[-300:])
check("nothing in this suite reached the network", attempts == [], attempts)

print("\n=== 4. the real library is exactly as it was found ===")
changed = box.finish()
check("config.json and the library database are unchanged", not changed, changed)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
