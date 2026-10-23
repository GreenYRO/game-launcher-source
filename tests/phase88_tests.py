"""Phase 88: release 1.2.4 -- the Steam wishlist and its tab go to the friends.

  1. the version: 1.2.4, newer than the 1.2.3 the friends have;
  2. what an update needs: the installer bundles every upgrade script, the wishlist's 006 among them;
     the friends' path is checked by check_installer.py --over the installer before this one;
  3. the documents: CITESTE-MA names 1.2.4 and the Wishlist page, and that the wishlist is read and
     never changed; DISTRIBUTIE lists 1.2.4; CLAUDE.md; the layers; the real data untouched.

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
# 1.2.4 or later: the wishlist is in every release after it (1.2.5, Phase 90, its three extensions).
check("version 1.2.4 or later", version.parse(version.APP_VERSION) >= (1, 2, 4), version.APP_VERSION)
check("newer than 1.2.3, so the friends' copies offer it", version.is_newer(version.APP_VERSION, "1.2.3"))

print("\n=== 2. what an update needs ===")
spec = (PROJECT / "packaging" / "app.spec").read_text(encoding="utf-8")
scripts = sorted(p.name for p in (PROJECT / "data_access" / "upgrades").glob("*.sql"))
check(f"the installer bundles the upgrade scripts ({len(scripts)}), the wishlist's 006 among them",
      '"data_access", "upgrades"' in spec and "006_wishlist.sql" in scripts, scripts)
installer_check = (PROJECT / "tests" / "check_installer.py").read_text(encoding="utf-8")
check("check_installer.py still takes the friends' path (--over)", '"--over"' in installer_check)

print("\n=== 3. the documents, the layers ===")
readme = (PROJECT / "docs" / "CITESTE-MA.md").read_text(encoding="utf-8")
distribution = (PROJECT / "docs" / "DISTRIBUTIE.md").read_text(encoding="utf-8")
claude = (PROJECT / "CLAUDE.md").read_text(encoding="utf-8")
check("CITESTE-MA names the version, the Wishlist page, and that the list is never changed",
      f"Versiunea {version.APP_VERSION}." in readme and "**Wishlist**" in readme and "nu o schimbă niciodată" in readme)
check("DISTRIBUTIE lists 1.2.4 and what it brings",
      "**1.2.4** (faza 88) aduce lista de dorințe Steam și pagina **Wishlist**" in distribution)
check("CLAUDE.md has the phase and its notes", "| 88 |" in claude and "## Phase 88 notes" in sources.build_log())
layers = subprocess.run([sys.executable, str(PROJECT / "tests" / "check_layers.py")], capture_output=True, text=True,
                        encoding="utf-8", errors="replace")
check("no import points up a layer; sqlite3 only in data_access/", layers.returncode == 0, layers.stdout[-300:])
check("nothing in this suite reached the network", attempts == [], attempts)

print("\n=== 4. the real library is exactly as it was found ===")
changed = box.finish()
check("config.json and the library database are unchanged", not changed, changed)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
