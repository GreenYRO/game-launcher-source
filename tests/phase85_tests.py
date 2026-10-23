"""Phase 85: release 1.2.3 -- the Reports tab goes to the friends.

  1. the version: 1.2.3, newer than the 1.2.2 the friends have;
  2. the Reports page as an installed copy shows it: a table cut short says how many rows more
     and, with no reports.py beside an installed copy, points to no command; from source it still
     names reports.py; the opening line says where the accounts are marked, and Settings has that
     section by that name;
  3. what an update needs: the installer bundles every upgrade script, the one that brings
     version 5 among them; check_installer.py can take the friends' path (--over the installer
     before this one);
  4. the documents: CITESTE-MA names 1.2.3 and the Reports page; DISTRIBUTIE lists 1.2.3, keeps
     the old installer aside before a build and describes the path over it; CLAUDE.md; the layers;
     the real data untouched.

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

import logging

logging.basicConfig(level=logging.CRITICAL)

from shared import paths, version

passed = failed = 0


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"   PASS  {name}")
    else:
        failed += 1
        print(f"   FAIL  {name}   {detail}")


def unreached(section: str, exc: Exception):
    check(f"section {section} runs to its end on this code", False, repr(exc))


print("\n=== 1. the version ===")
# 1.2.3 or later: the Reports tab is in every release after it (1.2.4, Phase 88, the wishlist).
check("version 1.2.3 or later", version.parse(version.APP_VERSION) >= (1, 2, 3), version.APP_VERSION)
check("newer than 1.2.2, so the friends' copies offer it", version.is_newer(version.APP_VERSION, "1.2.2"))

print("\n=== 2. the Reports page as an installed copy shows it ===")
try:
    from presentation import ui_reports

    rows = [(f"Game {n}", f"{n} hours") for n in range(15)]
    frozen = paths.FROZEN
    try:
        paths.FROZEN = True
        installed = ui_reports.table_html(("Game", "Hours"), rows, 10)
        paths.FROZEN = False
        source = ui_reports.table_html(("Game", "Hours"), rows, 10)
    finally:
        paths.FROZEN = frozen
    check("installed: the table says it is cut short, and how many more",
          "... and 5 more." in installed, installed[-160:])
    check("installed: no command named that an installed copy does not have",
          "reports.py" not in installed, installed[-160:])
    check("from source: it still names reports.py --csv", "reports.py --csv has them all" in source, source[-160:])
    check("a table that fits says nothing more", "more" not in ui_reports.table_html(("Game", "Hours"), rows[:3], 10))
    settings = (PROJECT / "presentation" / "ui_settings.py").read_text(encoding="utf-8")
    check("the opening line says where the accounts are marked, by the section's own name",
          "Settings, Steam accounts" in ui_reports.INTRO and '_section("Steam accounts")' in settings,
          ui_reports.INTRO)
except Exception as exc:
    unreached("2", exc)

print("\n=== 3. what an update needs ===")
try:
    spec = (PROJECT / "packaging" / "app.spec").read_text(encoding="utf-8")
    scripts = sorted(p.name for p in (PROJECT / "data_access" / "upgrades").glob("*.sql"))
    check(f"the installer bundles the upgrade scripts ({len(scripts)}), version 5's among them",
          '"data_access", "upgrades"' in spec and "005_hours.sql" in scripts, scripts)
    installer_check = (PROJECT / "tests" / "check_installer.py").read_text(encoding="utf-8")
    check("check_installer.py takes the friends' path: --over the installer before this one",
          '"--over"' in installer_check and "=== 8. a friend's copy of the version before" in installer_check
          and "the library database is at version {SCHEMA} now" in installer_check)
    # Only asked of a check that knows the option: one that does not would go on and install.
    if '"--over"' in installer_check:
        named = subprocess.run([sys.executable, str(PROJECT / "tests" / "check_installer.py"), "--over",
                                str(box.folder / "no such installer.exe")], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=60)
        refused = named.returncode != 0 and "--over names the installer" in (named.stderr + named.stdout)
    else:
        named, refused = None, False
    check("given an installer that is not there, it refuses before installing anything", refused,
          (named.returncode, named.stderr[-200:]) if named else "no --over")
except Exception as exc:
    unreached("3", exc)

print("\n=== 4. the documents, the layers ===")
try:
    claude = (PROJECT / "CLAUDE.md").read_text(encoding="utf-8")
    distribution = (PROJECT / "docs" / "DISTRIBUTIE.md").read_text(encoding="utf-8")
    readme = (PROJECT / "docs" / "CITESTE-MA.md").read_text(encoding="utf-8")
    check("CITESTE-MA names the version and the Reports page, in one sentence",
          f"Versiunea {version.APP_VERSION}." in readme and "Pagina\n**Reports** (după Storage)" in readme.replace("\r\n", "\n"))
    check("DISTRIBUTIE lists 1.2.3 and what it brings", "**1.2.3** (faza 85) aduce pagina **Reports**" in distribution)
    check("DISTRIBUTIE keeps the old installer aside before a build, and checks the path over it",
          "pui deoparte `dist\\GameLauncher-Setup.exe`" in distribution
          and "check_installer.py --over" in distribution and "8. **cu `--over" in distribution)
    check("CLAUDE.md has the phase and its notes", "| 85 |" in claude and "## Phase 85 notes" in sources.build_log())
    layers = subprocess.run([sys.executable, str(PROJECT / "tests" / "check_layers.py")], capture_output=True,
                            text=True, encoding="utf-8", errors="replace")
    check("no import points up a layer; sqlite3 only in data_access/", layers.returncode == 0, layers.stdout[-300:])
    check("nothing in this suite reached the network", attempts == [], attempts)
except Exception as exc:
    unreached("4", exc)

print("\n=== 5. the real library is exactly as it was found ===")
changed = box.finish()
check("config.json and the library database are unchanged", not changed, changed)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
