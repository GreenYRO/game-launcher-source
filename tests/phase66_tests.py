"""Phase 66: the tests read the library through the store, not its file.

The database, step 3 of 8. Before the library moves into a database (Phase 69), no test may
know how it is kept: what a test asserts was saved, the records it plants for its setup, a
library of its own, what a snapshot holds, the user's real library it promises to leave
alone -- all of it goes through five helpers in test_sandbox, and they go through the
store. When the store changes, test_sandbox is the one file in tests/ that has to.

This suite proves the helpers do what they say, and searches every file in tests/ for a
test that still opens overrides.json or reaches into a store's dict. The few places that
still may are listed below, each with the reason and the phase that takes it. Runs on a
throwaway copy of the data.
"""
import ast
import re
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))  # the project folder, one up from tests/
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
TAG = "before-phase-66"

import test_sandbox

box = test_sandbox.start()

import logging

logging.basicConfig(level=logging.ERROR)

from data_access import backups, catalog_io

passed = failed = 0


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"   PASS  {name}")
    else:
        failed += 1
        print(f"   FAIL  {name}   {detail}")


print("=== 1. the helpers read and write through the store ===")
library = test_sandbox.records()
key = next(iter(library))
print(f"   the copy holds {len(library)} records")
writer = test_sandbox.library()
writer.update(key, notes="Written by the store.")
writer.close()
check("records() is what was saved: a change written by any store is there",
      test_sandbox.records()[key].get("notes") == "Written by the store.")
copy_of = test_sandbox.records()
copy_of[key]["notes"] = "changed in the copy only"
check("and it is a copy: changing it changes nothing saved",
      test_sandbox.records()[key].get("notes") == "Written by the store.")

planted = {"c:\\games\\planted by a test": {"first_seen": "2026-10-10T12:00:00+03:00", "playtime_seconds": 60}}
test_sandbox.put_records(planted)
reader = test_sandbox.library()
check("put_records() plants into the library the app opens", reader.get(
    "c:\\games\\planted by a test") == planted["c:\\games\\planted by a test"])
reader.close()
live = test_sandbox.library()
test_sandbox.put_records({key: {"first_seen": "2026-08-01T10:00:00+03:00"}}, live)
check("into a live store, which shows it at once and has saved it",
      live.get(key) == {"first_seen": "2026-08-01T10:00:00+03:00"}
      and test_sandbox.records()[key] == {"first_seen": "2026-08-01T10:00:00+03:00"})

apart = test_sandbox.separate_store("a library apart", {"steam:1": {"first_seen": "2026-01-01T00:00:00+02:00"}})
check("separate_store() holds what it was given, saved where records(store) finds it",
      test_sandbox.records(apart) == {"steam:1": {"first_seen": "2026-01-01T00:00:00+02:00"}})
check("and the library the app opens has not heard of it", "steam:1" not in test_sandbox.records())
check("an empty one is empty", test_sandbox.records(test_sandbox.separate_store("nothing yet")) == {})

snap = backups.snapshot("phase66")
check("records_in() reads what a snapshot holds", snap is not None
      and test_sandbox.records_in(snap.path) == test_sandbox.records())

stamp = test_sandbox.real_stamp()
real = test_sandbox.real_records()
if (test_sandbox.REAL / "overrides.json").is_file():  # before the user's own switch
    raw = __import__("json").loads((test_sandbox.REAL / "overrides.json").read_text(encoding="utf-8"))["games"]
    check(f"real_records() is the real library ({len(real)} records), as its file holds it", real == raw)
else:  # after it: what the real database holds, read through a connection of this test's own
    check(f"real_records() is the real library ({len(real)} records), as its database holds it",
          real and test_sandbox.db_fingerprint(test_sandbox.REAL / test_sandbox.REAL_DB) == box.before_db)
check("and reading it writes nothing", test_sandbox.real_stamp() == stamp)

alone = subprocess.run(
    [sys.executable, "-c",
     "import sys; sys.path[:0] = [r'%s', r'%s']; import test_sandbox; "
     "print('data_access.catalog_io' in sys.modules, 'data_access.config_io' in sys.modules)"
     % (PROJECT / "tests", PROJECT)],
    capture_output=True, text=True)
check("importing test_sandbox loads no data module, so start()'s guard still holds",
      alone.stdout.strip() == "False False", (alone.stdout, alone.stderr[-300:]))

print("\n=== 2. no test opens the library's file or a store's dict ===")
READS = re.compile(r"read_text|read_bytes|write_text|write_bytes|json\.load|open\(|read_json\(")
# Still allowed, each for a reason and until a named phase.
ALLOWED = {
    "test_sandbox.py": "the one file that knows how the library is kept (Phase 66)",
    "check_paths.py": "the sandbox guard's own proof, a change planted in a stand-in copy (Phase 68)",
    "phase65_tests.py": "the old code's files byte for byte -- a proof of its own step, on JSON (Phase 69)",
    "phase66_tests.py": "proves real_records() against the file itself",
    "phase69_tests.py": "tests the migration itself: the JSON files before it, and where they went",
}


def offences(source: str) -> list[str]:
    found = []
    for number, line in enumerate(source.splitlines(), 1):
        code = line.split("#", 1)[0]
        if "overrides.json" in code and READS.search(code):
            found.append(f"{number}: reads the file")
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Attribute) and node.attr == "games":
            inner = node.value
            name = inner.attr if isinstance(inner, ast.Attribute) else getattr(inner, "id", "")
            if "overrides" in name or "store" in name:
                found.append(f"{node.lineno}: {name}.games")
    return found


tests = sorted((PROJECT / "tests").glob("*.py"))
now = {p.name: offences(p.read_text(encoding="utf-8-sig")) for p in tests}
now = {name: hits for name, hits in now.items() if hits}
print(f"   read {len(tests)} files in tests/")
for name, reason in ALLOWED.items():
    print(f"   allowed: {name} ({len(now.get(name, []))}) -- {reason}")
check("nothing outside the allowed few", set(now) <= set(ALLOWED),
      {name: hits for name, hits in now.items() if name not in ALLOWED})


def old(name: str) -> str:
    shown = subprocess.run(["git", "show", f"{TAG}:tests/{name}"], cwd=PROJECT, capture_output=True)
    return shown.stdout.decode("utf-8-sig") if shown.returncode == 0 else ""


before = {p.name: offences(old(p.name)) for p in tests if p.name not in ALLOWED}
before = {name: hits for name, hits in before.items() if hits}
print(f"   at {TAG}: {sum(len(h) for h in before.values())} places in {len(before)} files: {sorted(before)}")
check("the same search finds the places this phase moved, in the tests as they were",
      len(before) >= 8, sorted(before))

print("\n=== 3. the real library is exactly as it was found ===")
changed = box.finish()
check("overrides.json, config.json and catalog.json are byte for byte unchanged", not changed, changed)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
