"""Phase 104: release 1.2.9 -- price alerts (Phase 101), the session rating and report 10 (Phase 102), the hours
pill (its extension), Left behind and report 11 (Phase 103) go to the friends.

  1. the version: 1.2.9, newer than the 1.2.8 the friends have;
  2. what an update needs: the schema 1.2.8 shipped was version 7 (the last script 007); this one is 8, and 008
     is the one script a friend's library runs at its first start, a snapshot first -- additions only;
     check_installer.py --over checks the upgrade, the snapshot holding 7 and every view, then plants a price
     alert and reads Settings' After a game row off the installed copy's screen;
  3. the planted alert itself, on a copy here: check_installer's own plant_alert run against this schema and
     landed by the program's own code -- one 'target' alert, and the same price again sets nothing off;
  4. the documents: CITESTE-MA names 1.2.9 and what it brings, on its one page; DISTRIBUTIE lists 1.2.9 and the
     check's new steps; the explanation page; CLAUDE.md, its version line and its size; the layers; the real data
     untouched.

On a throwaway copy of the data; the network is blocked.
"""
import ast
import json
import sqlite3
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import sources  # the build log's notes (Phase 91)
import test_sandbox

box = test_sandbox.start({"allow_network": False, "startup_scan": False})
attempts: list[str] = []


def no_network(request, *args, **kwargs):
    attempts.append(getattr(request, "full_url", str(request)))
    raise OSError("the network is blocked in this suite")


urllib.request.urlopen = no_network

from data_access import library_db
from logic import alerts, migration, prices
from shared import paths, rules, version

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


PUBLISHED_128 = "176b287"  # 1.2.8, as published

print("=== 1. the version ===")
# Its release's own version, read at its publish commit (311c3a2): a later release raises it (Phase 107: 1.2.10).
check("version 1.2.9 at its release", 'APP_VERSION = "1.2.9"' in git("show", "311c3a2:shared/version.py"),
      version.APP_VERSION)
check("newer than 1.2.8, so the friends' copies offer it", version.is_newer(version.APP_VERSION, "1.2.8")
      and 'APP_VERSION = "1.2.8"' in git("show", f"{PUBLISHED_128}:shared/version.py"))
check("version.py's history names 1.2.9 and what it brings",
      "1.2.9 (Phase 104)" in (PROJECT / "shared" / "version.py").read_text(encoding="utf-8"))

print("\n=== 2. what an update needs ===")
shipped = sorted(git("ls-tree", "--name-only", f"{PUBLISHED_128}:data_access/upgrades").split())
scripts = sorted(p.name for p in (PROJECT / "data_access" / "upgrades").glob("*.sql"))
new = [name for name in scripts if name not in shipped]
check("1.2.8 shipped schema version 7, the last script 007",
      "SCHEMA_VERSION = 7 " in git("show", f"{PUBLISHED_128}:data_access/library_db.py")
      and shipped[-1].startswith("007_"), shipped)
check("this one is version 8, and 008 the one new script a friend's library runs",
      library_db.SCHEMA_VERSION == 8 and new == ["008_alerts_ratings_marks.sql"], (library_db.SCHEMA_VERSION, new))
upgrade = (PROJECT / "data_access" / "upgrades" / new[0]).read_text(encoding="utf-8").upper() if new else ""
statements = [line.strip() for line in upgrade.splitlines() if line.strip() and not line.strip().startswith("--")]
check("and it only adds: tables, an index or a column -- no DROP, DELETE or UPDATE",
      upgrade and not any(word in line for line in statements for word in ("DROP ", "DELETE ", "UPDATE "))
      and "ALTER TABLE GAME ADD COLUMN" in upgrade, [s for s in statements if "DROP" in s or "DELETE" in s][:3])
check("and no script 1.2.8 shipped changed since", git("diff", "--stat", PUBLISHED_128, "--",
                                                       *[f"data_access/upgrades/{n}" for n in shipped]) == "")
installer_check = (PROJECT / "tests" / "check_installer.py").read_text(encoding="utf-8")
check("check_installer.py takes the friends' path (--over) and checks the upgrade with its snapshot",
      '"--over"' in installer_check and "a snapshot first, holding the library at version {old_schema}"
      in installer_check and "every view of this version answers on it" in installer_check)
check("and plants a price alert there: one set off, written once, said in words, the same price silent",
      "observed = plant_alert(old_target)" in installer_check and "plant_alert(old_target, again=True)"
      in installer_check and '"price alerts: 1 set off"' in installer_check
      and "under your 20,00\\u00a0\\u20ac target" in installer_check
      and 'f"SELECT COUNT(*) FROM price_alert WHERE appid = {WISHED}")[0][0] == 1' in installer_check)
settings_source = (PROJECT / "presentation" / "ui_settings.py").read_text(encoding="utf-8")
check("and reads the After a game row off the installed copy's screen, as 1.2.8's Accent row",
      '"After a game" in names and "Ask how a session was" in names' in installer_check
      and installer_check.count("shows_whats_new(app,") == 2
      and '"After a game"' in settings_source and '"Ask how a session was"' in settings_source)

print("\n=== 3. the planted alert, on a copy here ===")
tree = ast.parse(installer_check)
chunk = "\n\n".join(ast.get_source_segment(installer_check, node) for node in tree.body
                    if isinstance(node, ast.FunctionDef) and node.name in ("plant_alert", "read_db"))
values = {node.targets[0].id: ast.literal_eval(node.value) for node in tree.body
          if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
          and node.targets[0].id in ("WISHED", "WISHED_ACCOUNT")}
planted = {"json": json, "sqlite3": sqlite3, "time": time, "rules": rules, "Path": Path, **values}
exec(compile("from __future__ import annotations\n" + chunk, "check_installer.plant_alert", "exec"), planted)
target = Path(paths.data_dir())
WISHED = values.get("WISHED")
store = migration.open_library()
try:
    observed = planted["plant_alert"](target)
    landed = prices.land(store, str(target / "cache"))
    sent = alerts.land(store, landed.fresh, set())
    check("the plant fits this schema and the price lands: one new observation",
          landed.landed == 1 and landed.fresh == [(WISHED, observed)] and not landed.refused,
          (landed.landed, landed.fresh, landed.refused))
    check("one alert, 'target', at 19,99 under the 20,00 target -- not 'lowest' on two prices",
          [(a.kind, a.cents, a.target_cents) for a in sent] == [(rules.ALERT_TARGET, 1999, 2000)],
          [(a.kind, a.cents) for a in sent])
    words = alerts.message(sent) if sent else ""
    check("its words: under your 20,00 € target", "under your 20,00 € target" in words, words)
    planted["plant_alert"](target, again=True)
    landed = prices.land(store, str(target / "cache"))
    again = alerts.land(store, landed.fresh, set())
    logged = planted["read_db"](target / rules.LIBRARY_DB_FILE,
                                f"SELECT kind, final_cents FROM price_alert WHERE appid = {WISHED}")
    check("the same price again: landed as there already, nothing set off, one row in the log",
          landed.landed == 1 and landed.fresh == [] and again == [] and logged == [(rules.ALERT_TARGET, 1999)],
          (landed.fresh, again, logged))
finally:
    store.close()

print("\n=== 4. the documents, the layers ===")
readme = (PROJECT / "docs" / "CITESTE-MA.md").read_text(encoding="utf-8").replace("\r\n", "\n")
distribution = (PROJECT / "docs" / "DISTRIBUTIE.md").read_text(encoding="utf-8").replace("\r\n", "\n")
claude = (PROJECT / "CLAUDE.md").read_text(encoding="utf-8").replace("\r\n", "\n")
check("CITESTE-MA names 1.2.9 and what it brings, still on one page", f"Versiunea {version.APP_VERSION}." in readme
      and all(w in readme for w in ("**Alert me under...**", "**How was it?**", "**Skip**",
                                    "Settings → After a game", "**Left behind**", "unsprezece rapoarte"))
      and len(readme.splitlines()) <= 110, len(readme.splitlines()))
check("DISTRIBUTIE lists 1.2.9 and what it brings", "**1.2.9**\n(faza 104) aduce alertele de preț" in distribution
      and f'"{version.APP_VERSION}"' in distribution and f"Game Launcher {version.APP_VERSION}, built" in distribution
      and f"„Game Launcher {version.APP_VERSION}”" in distribution)
check("and the check's two new steps: the After a game row, the planted alert",
      "**ce aduce 1.2.9** (faza 104)" in distribution and "**o alertă de preț, cum o întâlnește un prieten**"
      in distribution)
explained = PROJECT / "docs" / "explicatii" / "faza-104.md"
check("the explanation page is there", explained.is_file()
      and "1.2.9" in explained.read_text(encoding="utf-8"))
check("CLAUDE.md has the phase, its notes and the version's line", "| 104 |" in claude
      and "## Phase 104 notes" in sources.build_log() and "1.2.9, Phase 104" in claude)
old = git("show", "before-phase-91:CLAUDE.md").replace("\r\n", "\n")
check("CLAUDE.md under a quarter of its size before Phase 91 (suite 91), with this phase in it",
      len(claude.encode("utf-8")) < len(old.encode("utf-8")) / 4,
      (len(claude.encode("utf-8")), len(old.encode("utf-8")) / 4))
layers = subprocess.run([sys.executable, str(PROJECT / "tests" / "check_layers.py")], capture_output=True, text=True,
                        encoding="utf-8", errors="replace")
check("no import points up a layer; sqlite3 only in data_access/", layers.returncode == 0, layers.stdout[-300:])
check("nothing in this suite reached the network", attempts == [], attempts)

print("\n=== 5. the real library is exactly as it was found ===")
changed = box.finish()
check("config.json, the library database and the Run key's value are unchanged", not changed, changed)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
