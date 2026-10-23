"""Phase 95: release 1.2.6 -- the tray, games seen running and the sleep cap (Phases 92-94) go to the friends.

  1. the version: 1.2.6, newer than the 1.2.5 the friends have;
  2. what an update needs: 1.2.5 shipped schema version 6 and this one brings 7 (one script, 007, an added
     column), bundled with the installer; the friends' path is checked by check_installer.py --over the
     installer before this one, and the installed copy is asked to read the process list;
  3. the installer, when the launcher is open -- in the tray since 1.2.6 -- says how to quit it;
  4. the documents: CITESTE-MA names 1.2.6, the three switches and how to quit before an update, on its one
     page; DISTRIBUTIE lists 1.2.6 and what it brings; CLAUDE.md; the layers; the real data untouched.

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
# 1.2.6 or later: Phases 92-94 are in every release after it (1.2.7, Phase 97, the recap card).
check("version 1.2.6 or later", version.parse(version.APP_VERSION) >= (1, 2, 6), version.APP_VERSION)
check("newer than 1.2.5, so the friends' copies offer it", version.is_newer(version.APP_VERSION, "1.2.5"))

print("\n=== 2. what an update needs ===")
# What 1.2.5 shipped, read at its own commit (096f816).
RELEASE = "096f816"
shipped = sorted(git("ls-tree", "--name-only", f"{RELEASE}:data_access/upgrades").split())
scripts = sorted(p.name for p in (PROJECT / "data_access" / "upgrades").glob("*.sql"))
check("1.2.5 shipped schema version 6; this one brings 7, and the one new script is 007's",
      "SCHEMA_VERSION = 6 " in git("show", f"{RELEASE}:data_access/library_db.py")
      and "SCHEMA_VERSION = 7 " in git("show", "a3e4792:data_access/library_db.py")  # 1.2.6, as published
      and sorted(set(git("ls-tree", "--name-only", "a3e4792:data_access/upgrades").split()) - set(shipped))
      == ["007_observed.sql"],
      (shipped, scripts))
upgrade = (PROJECT / "data_access" / "upgrades" / "007_observed.sql").read_text(encoding="utf-8")
statements = [s.strip() for s in "\n".join(line for line in upgrade.splitlines()
                                            if not line.lstrip().startswith("--")).split(";") if s.strip()]
check("and it only adds: one column, every session that was there reading 'launched'",
      len(statements) == 1 and statements[0].upper().startswith("ALTER TABLE SESSION ADD COLUMN ORIGIN")
      and "DEFAULT 'launched'" in statements[0], statements)
spec = (PROJECT / "packaging" / "app.spec").read_text(encoding="utf-8")
check("the installer bundles the upgrade scripts", '"data_access", "upgrades"' in spec)
installer_check = (PROJECT / "tests" / "check_installer.py").read_text(encoding="utf-8")
check("check_installer.py still takes the friends' path (--over), and asks the installed copy to read "
      "the process list", '"--over"' in installer_check and "process watch: a look every" in installer_check)

print("\n=== 3. the installer, with the launcher open ===")
installer = (PROJECT / "packaging" / "installer.py").read_text(encoding="utf-8")
check("it says how to quit a launcher left in the tray", "right-click it and choose Quit" in installer)

print("\n=== 4. the documents, the layers ===")
readme = (PROJECT / "docs" / "CITESTE-MA.md").read_text(encoding="utf-8")
distribution = (PROJECT / "docs" / "DISTRIBUTIE.md").read_text(encoding="utf-8")
claude = (PROJECT / "CLAUDE.md").read_text(encoding="utf-8")
check("CITESTE-MA names 1.2.6 and the three switches", f"Versiunea {version.APP_VERSION}." in readme
      and all(w in readme for w in ("**Keep running when the window is closed**", "**Start with Windows**",
                                    "**Notice games started outside the launcher**")))
check("and says to quit from the tray before an update, still on one page",
      "clic dreapta → Quit),\napoi rulează noul" in readme.replace("\r\n", "\n") and len(readme.splitlines()) <= 110,
      len(readme.splitlines()))
check("DISTRIBUTIE lists 1.2.6 and what it brings", "**1.2.6** (faza 95) aduce viața lângă ceas" in distribution
      and f'"{version.APP_VERSION}"' in distribution)
check("CLAUDE.md has the phase and its notes", "| 95 |" in claude and "## Phase 95 notes" in sources.build_log())
layers = subprocess.run([sys.executable, str(PROJECT / "tests" / "check_layers.py")], capture_output=True, text=True,
                        encoding="utf-8", errors="replace")
check("no import points up a layer; sqlite3 only in data_access/", layers.returncode == 0, layers.stdout[-300:])
check("nothing in this suite reached the network", attempts == [], attempts)

print("\n=== 5. the real library is exactly as it was found ===")
changed = box.finish()
check("config.json and the library database are unchanged", not changed, changed)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
