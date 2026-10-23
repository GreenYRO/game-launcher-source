"""Phase 97: release 1.2.7 -- the recap card and the one counting rule (Phase 96) go to the friends.

  1. the version: 1.2.7, newer than the 1.2.6 the friends have;
  2. what an update needs: the schema 1.2.6 shipped is this one's (version 7, the last script 007), so a
     friend's library is not upgraded; the friends' path is checked by check_installer.py --over;
  3. the documents: CITESTE-MA names 1.2.7 and the Recap card, on its one page; DISTRIBUTIE lists 1.2.7 and
     what it brings, and the notes in two languages; CLAUDE.md; the layers; the real data untouched.

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
# 1.2.7 or later: the recap card is in every release after it (1.2.8, Phase 100).
check("version 1.2.7 or later", version.parse(version.APP_VERSION) >= (1, 2, 7), version.APP_VERSION)
check("newer than 1.2.6, so the friends' copies offer it", version.is_newer(version.APP_VERSION, "1.2.6"))

print("\n=== 2. what an update needs ===")
RELEASE = "a3e4792"  # 1.2.6, as published
shipped = sorted(git("ls-tree", "--name-only", f"{RELEASE}:data_access/upgrades").split())
scripts = sorted(p.name for p in (PROJECT / "data_access" / "upgrades").glob("*.sql"))
check("the schema 1.2.6 shipped is this one's: version 7, the last script 007, nothing to upgrade",
      "SCHEMA_VERSION = 7 " in git("show", f"{RELEASE}:data_access/library_db.py")
      and "SCHEMA_VERSION = 7 " in git("show", "c4127b2:data_access/library_db.py")  # 1.2.7, as published
      and shipped == sorted(git("ls-tree", "--name-only", "c4127b2:data_access/upgrades").split())
      and shipped[-1].startswith("007_"), (shipped, scripts))
check("and no upgrade script or schema line changed in it", git("diff", "--stat", RELEASE, "c4127b2", "--",
                                                                 "data_access/schema.sql", "data_access/upgrades") == "")
installer_check = (PROJECT / "tests" / "check_installer.py").read_text(encoding="utf-8")
check("check_installer.py still takes the friends' path (--over)", '"--over"' in installer_check)

print("\n=== 3. the documents, the layers ===")
readme = (PROJECT / "docs" / "CITESTE-MA.md").read_text(encoding="utf-8")
distribution = (PROJECT / "docs" / "DISTRIBUTIE.md").read_text(encoding="utf-8")
claude = (PROJECT / "CLAUDE.md").read_text(encoding="utf-8")
check("CITESTE-MA names 1.2.7 and the Recap card, still on one page", f"Versiunea {version.APP_VERSION}." in readme
      and "**Recap**" in readme and "Share as image" in readme and len(readme.splitlines()) <= 110,
      len(readme.splitlines()))
check("DISTRIBUTIE lists 1.2.7 and what it brings", "**1.2.7** (faza 97) aduce cardul **Recap**" in distribution
      and f'"{version.APP_VERSION}"' in distribution)
check("and says the notes go in Romanian and English", "notele sunt în română și în engleză" in distribution)
check("CLAUDE.md has the phase and its notes", "| 97 |" in claude and "## Phase 97 notes" in sources.build_log())
layers = subprocess.run([sys.executable, str(PROJECT / "tests" / "check_layers.py")], capture_output=True, text=True,
                        encoding="utf-8", errors="replace")
check("no import points up a layer; sqlite3 only in data_access/", layers.returncode == 0, layers.stdout[-300:])
check("nothing in this suite reached the network", attempts == [], attempts)

print("\n=== 4. the real library is exactly as it was found ===")
changed = box.finish()
check("config.json, the library database and the Run key's value are unchanged", not changed, changed)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
