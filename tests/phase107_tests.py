"""Phase 107: release 1.2.10 -- the missing covers in one go (Phase 105) and What's new (Phase 106) go to the friends.

  1. the version: 1.2.10, newer than the 1.2.9 the friends have; its notes written first, as the rule since Phase 106
     says -- docs/release-notes/1.2.10.md, both languages, what the build asks for and what What's new will show;
  2. what an update needs: the schema 1.2.9 shipped is this one's (version 8, the last script 008), so nothing in a
     friend's library is upgraded; check_installer.py --over meets What's new first on the friend's path, then the
     one question, and finds this version's notes in the build;
  3. the documents: CITESTE-MA names 1.2.10 and what it brings, on its one page; DISTRIBUTIE lists 1.2.10, the
     check's new step, the Sandbox list's version; the explanation page; CLAUDE.md, its version line and its size; the
     layers; the real data untouched.

On a throwaway copy of the data; the network is blocked.
"""
import subprocess
import sys
import urllib.request
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT / "packaging"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import sources  # the build log's notes (Phase 91)
import test_sandbox

box = test_sandbox.start()
attempts: list[str] = []


def no_network(request, *args, **kwargs):
    attempts.append(getattr(request, "full_url", str(request)))
    raise OSError("the network is blocked in this suite")


urllib.request.urlopen = no_network

from data_access import library_db  # noqa: E402
from logic import whats_new  # noqa: E402
from shared import version  # noqa: E402

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


PUBLISHED_129 = "311c3a2"  # 1.2.9, as published

print("=== 1. the version, and its notes first ===")
check("version 1.2.10", version.APP_VERSION == "1.2.10", version.APP_VERSION)
check("newer than 1.2.9, so the friends' copies offer it -- as a number, not as text",
      version.is_newer(version.APP_VERSION, "1.2.9") and not version.is_newer("1.2.9", version.APP_VERSION)
      and 'APP_VERSION = "1.2.9"' in git("show", f"{PUBLISHED_129}:shared/version.py"))
check("version.py's history names 1.2.10 and what it brings",
      "1.2.10 (Phase 107)" in (PROJECT / "shared" / "version.py").read_text(encoding="utf-8"))
import build  # packaging/build.py -- imported, never run

notes = whats_new.read(version.APP_VERSION)
english = whats_new.english()
check("docs/release-notes/1.2.10.md: ready for the build, both languages", whats_new.ready(version.APP_VERSION)[0]
      and build.check_notes() == "", build.check_notes())
check("what What's new will show: this version's name, Fill missing covers, the fix -- in English",
      "**What's new in 1.2.10**" in english and "**Fill missing covers...**" in english
      and "Test button" in english and "## Română" not in english and "Coperțile" not in english, english[:120])
check("and the Romanian under its own heading, first, for the GitHub page",
      notes.index("## Română") < notes.index("## English")
      and "**Fill missing covers...**" in whats_new.section(notes, whats_new.ROMANIAN))
check("the notes say the library does not change, and how to update",
      "does not change in this version" in english and "over the old one" in english)

print("\n=== 2. what an update needs ===")
shipped = sorted(git("ls-tree", "--name-only", f"{PUBLISHED_129}:data_access/upgrades").split())
scripts = sorted(p.name for p in (PROJECT / "data_access" / "upgrades").glob("*.sql"))
check("the schema 1.2.9 shipped is this one's: version 8, the last script 008, nothing to upgrade",
      "SCHEMA_VERSION = 8 " in git("show", f"{PUBLISHED_129}:data_access/library_db.py")
      and library_db.SCHEMA_VERSION == 8 and shipped == scripts and shipped[-1].startswith("008_"), (shipped, scripts))
check("and no upgrade script or schema line changed since", git("diff", "--stat", PUBLISHED_129, "--",
                                                                "data_access/schema.sql", "data_access/upgrades") == "")
installer_check = (PROJECT / "tests" / "check_installer.py").read_text(encoding="utf-8")
over = installer_check[installer_check.index("=== 8. a friend's copy"):]
check("check_installer.py's friends' path meets What's new first, then the one question",
      "meets_whats_new(app, old_target, old_version)" in over
      and over.index("meets_whats_new(app, old_target, old_version)") < over.index("answer_offer(app, old_target)")
      and "WHATS_NEW = ui_whats_new.TITLE.format(version=version.APP_VERSION)" in installer_check)
check("and asks the version seen before while it is open, this one once it is closed, its title read off the screen",
      "while it is open the version seen is still" in installer_check and "read off the screen: its title and Close"
      in installer_check and "closed: the version seen is" in installer_check)
check("and finds this version's notes in the build, byte for byte",
      "this version's release notes, {notes.name}, byte for byte" in installer_check)

print("\n=== 3. the documents, the layers ===")


def doc(name: str) -> str:
    return (PROJECT / name).read_text(encoding="utf-8").replace("\r\n", "\n")


readme = doc("docs/CITESTE-MA.md")
distribution = doc("docs/DISTRIBUTIE.md")
claude = doc("CLAUDE.md")
check("CITESTE-MA names 1.2.10 and what it brings, still on one page", f"Versiunea {version.APP_VERSION}." in readme
      and "**Fill missing covers...**" in readme and "**What's new**" in readme and len(readme.splitlines()) <= 110,
      len(readme.splitlines()))
check("DISTRIBUTIE lists 1.2.10 and what it brings", "**1.2.10** (faza 107) aduce" in distribution
      and f'"{version.APP_VERSION}"' in distribution and f"Game Launcher {version.APP_VERSION}, built" in distribution
      and f"„Game Launcher {version.APP_VERSION}”" in distribution)
check("and the check's new step", "**What's new** (faza 107, pentru 1.2.10)" in distribution)
page = PROJECT / "docs" / "explicatii" / "faza-107.md"
check("the explanation page is there, in its shape", page.is_file() and all(
    w in page.read_text(encoding="utf-8") for w in ("1.2.10", "## Ce s-a construit", "## Cinci cuvinte",
                                                    "## Trei întrebări", "## Ce nu poate face"))
      and "faza 107" in doc("docs/explicatii/CITESTE-MA.md"))
check("CLAUDE.md has the phase, its notes and the version's line", "| 107 |" in claude
      and "## Phase 107 notes" in sources.build_log() and "1.2.10, Phase 107" in claude)
old = git("show", "before-phase-91:CLAUDE.md").replace("\r\n", "\n")
check("CLAUDE.md under a quarter of its size before Phase 91 (suite 91), with this phase in it",
      len(claude.encode("utf-8")) < len(old.encode("utf-8")) / 4,
      (len(claude.encode("utf-8")), len(old.encode("utf-8")) / 4))
layers = subprocess.run([sys.executable, str(PROJECT / "tests" / "check_layers.py")], capture_output=True, text=True,
                        encoding="utf-8", errors="replace")
check("no import points up a layer; sqlite3 only in data_access/", layers.returncode == 0, layers.stdout[-300:])
check("nothing in this suite reached the network", attempts == [], attempts)

print("\n=== 4. the real library is exactly as it was found ===")
changed = box.finish()
check("config.json, the library database and the Run key's value are unchanged", not changed, changed)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
