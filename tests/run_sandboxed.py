"""Run any phase test suite against a throwaway copy of the data.

    python tests\run_sandboxed.py phase24_tests.py      (from the project folder)

The suites up to Phase 25 write the real overrides.json and config.json by design, with
their own care to put things back. The launcher is usually open while tests run, holding
its own copy of those files in memory, so "put back" is not the same as "never touched".
Run through here, the app under test reads and writes a copy, and the real files are
checked byte for byte afterwards. Network lookups are off; the controller is left as the
real config has it, because the Phase 22 suite reads the real pad.
"""
import runpy
import sys
from pathlib import Path

import test_sandbox

if len(sys.argv) != 2:
    raise SystemExit("usage: run_sandboxed.py <suite.py>")

box = test_sandbox.start({"allow_network": False}, quiet=False)
suite = str(Path(__file__).resolve().parent / Path(sys.argv[1]).name)  # the suites sit beside it
sys.argv = [suite]
code = 0
try:
    runpy.run_path(suite, run_name="__main__")
except SystemExit as exc:
    code = exc.code if isinstance(exc.code, int) else 1
finally:
    changed = box.finish()
    if changed:
        print(f"\nREAL FILES CHANGED DURING THE RUN: {changed}")
        code = code or 1
raise SystemExit(code)
