"""Everything that says "nothing broke", in one command.

    .venv\\Scripts\\python.exe tests\\run_all.py       (from the project folder)

In order: a fingerprint of the original launcher folder; the sixteen phase suites, one at
a time, the way CLAUDE.md says (22-25 through run_sandboxed.py, which keeps them off the
real data); then the safety nets -- every import resolves and loads once, no import points
up a layer, the quiet paths point where they should, the scanner finds the same library,
the library database built from a copy of the data reads back exactly (Phase 67), and the
original folder was not touched. Each suite's full output is kept in a temporary folder, named at the end.

One at a time on purpose: several suites drive real windows, and two at once take focus
and pad input from each other (the Phase 34 lesson).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import sources

ROOT = sources.ROOT
TESTS = ROOT / "tests"
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
SANDBOXED = range(22, 26)  # the suites that write real data by design
# Lines a suite prints about how much it looked at; shown so a quiet shrink is visible.
COVERAGE = re.compile(r"(copied into the sandbox: .*|\(read \d+ source files.*\))")


def run(args: list[str], log: Path, timeout: int = 1200) -> tuple[int | str, str]:
    environment = dict(os.environ, PYTHONIOENCODING="utf-8")
    try:
        result = subprocess.run([str(PYTHON), *args], cwd=ROOT, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=timeout, env=environment)
        text, code = result.stdout + "\n--- stderr ---\n" + result.stderr, result.returncode
    except subprocess.TimeoutExpired as exc:
        text, code = f"TIMEOUT after {timeout}s\n{exc.stdout or ''}", "timeout"
    log.write_text(text, encoding="utf-8")
    return code, text


def main() -> int:
    logs = Path(tempfile.mkdtemp(prefix="run_all_"))
    problems = []
    code, text = run(["tests/check_original.py", "save"], logs / "original_save.txt")
    print(text.split("\n--- stderr")[0].strip())

    total_passed = total_failed = 0
    # Every phaseNN_tests.py there is, so a new suite joins without anyone remembering to add it.
    for n in sorted(int(p.stem[len("phase"):-len("_tests")]) for p in TESTS.glob("phase*_tests.py")):
        suite = f"phase{n}_tests.py"
        args = ["tests/run_sandboxed.py", suite] if n in SANDBOXED else [f"tests/{suite}"]
        started = time.time()
        code, text = run(args, logs / f"phase{n}.txt")
        counts = re.findall(r"(\d+) passed, (\d+) failed", text)
        passed, failed = (int(c) for c in counts[-1]) if counts else (0, 0)
        total_passed += passed
        total_failed += failed
        notes = sorted(set(COVERAGE.findall(text)))
        flag = "" if code == 0 and counts else "   <-- " + ("REAL FILES CHANGED" if "REAL FILES CHANGED" in text
                                                         else f"exit {code}")
        print(f"phase{n}: {passed:>3} passed, {failed} failed  ({time.time() - started:.0f}s)"
              f"{'  ' + '; '.join(notes) if notes else ''}{flag}")
        if flag:
            problems.append(suite)
    print(f"suites: {total_passed} passed, {total_failed} failed")

    for name, args in (("imports", ["tests/check_imports.py"]),
                       ("layers", ["tests/check_layers.py"]),
                       ("paths", ["tests/check_paths.py"]),
                       ("scanner", ["tests/check_scanner.py", "compare"]),
                       ("migration", ["tests/check_migration.py"]),
                       ("original folder", ["tests/check_original.py", "compare"])):
        code, text = run(args, logs / f"check_{name.replace(' ', '_')}.txt")
        body = text.split("\n--- stderr")[0]
        keep = [line for line in body.splitlines()
                if re.match(r"(static|live|loaded|real files|\d+ passed|\d+ games|differences|drift|C:\\"
                            r"|upward|\d+ app modules)", line)
                or "FAIL" in line or "NOT AN IMPORT" in line or line.startswith("   ")]
        print(f"\n--- {name}: {'ok' if code == 0 else 'FAILED'}")
        for line in keep[:25]:
            print(f"    {line.strip()}")
        if code != 0:
            problems.append(name)

    print(f"\nfull output: {logs}")
    print("ALL GREEN" if not problems else f"NOT GREEN: {', '.join(problems)}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
