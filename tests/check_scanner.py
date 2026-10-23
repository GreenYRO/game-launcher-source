"""Safety net: the whole discovery back end, end to end, on the real library.

    .venv\\Scripts\\python.exe tests\\check_scanner.py save       (once, before a restructure)
    .venv\\Scripts\\python.exe tests\\check_scanner.py compare    (after every step)

Runs `scanner.py --out` from the project folder with the project's own Python -- the same
command before and after every move -- and compares every game field by field against the
saved run in tests/baseline/scanner.json. That file describes this machine's library, so
it is not in git.

A few fields drift on their own on a machine in use (a game updates, Steam records a play,
a walk takes a different number of milliseconds); those are listed but do not fail the
check. Everything else -- which games, their names, launch targets, working folders,
detection, alternatives, artwork paths, appids -- must be identical. The scanner only
reads: it writes the catalog to a temporary file and nothing to the project's data.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import sources

ROOT = sources.ROOT
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
BASELINE = ROOT / "tests" / "baseline" / "scanner.json"

VOLATILE_TOP = {"size_on_disk"}
VOLATILE_EXTRA = {"last_played_unix", "last_updated_unix", "state_flags", "build_id",
                  "walk", "files_seen", "exe_size"}


def scan() -> dict:
    out = Path(tempfile.mkdtemp(prefix="check_scanner_")) / "catalog.json"
    result = subprocess.run([str(PYTHON), "scanner.py", "--out", str(out)], cwd=ROOT,
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0 or not out.is_file():
        raise SystemExit(f"scanner.py failed ({result.returncode}):\n{result.stderr[-3000:]}")
    data = json.loads(out.read_text(encoding="utf-8"))
    out.unlink()
    out.parent.rmdir()
    data["_log_problems"] = [line for line in result.stderr.splitlines()
                             if line.startswith(("ERROR", "CRITICAL")) or "Traceback" in line]
    return data


def split(entry: dict) -> tuple[dict, dict]:
    extra = entry.get("extra", {})
    stable = {k: v for k, v in entry.items() if k not in VOLATILE_TOP and k != "extra"}
    stable["extra"] = {k: v for k, v in extra.items() if k not in VOLATILE_EXTRA}
    volatile = {k: entry.get(k) for k in VOLATILE_TOP}
    volatile.update({f"extra.{k}": extra.get(k) for k in VOLATILE_EXTRA if k in extra})
    return stable, volatile


def by_key(data: dict) -> dict:
    return {e.get("identity_key") or f"{e['source']}:{e['source_id']}": e for e in data["entries"]}


def save() -> int:
    data = scan()
    BASELINE.parent.mkdir(exist_ok=True)
    BASELINE.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    entries = data["entries"]
    count = lambda field: {v: sum(1 for e in entries if e[field] == v)  # noqa: E731
                           for v in sorted({e[field] for e in entries})}
    print(f"saved {len(entries)} games to {BASELINE}")
    print("  by source:   ", count("source"))
    print("  by detection:", count("detection"))
    print("  log problems:", data["_log_problems"] or "none")
    return 0


def compare() -> int:
    before = json.loads(BASELINE.read_text(encoding="utf-8"))
    after = scan()
    a, b = by_key(before), by_key(after)
    differences, drift = [], []
    for key in sorted(set(a) | set(b)):
        if key not in b:
            differences.append(f"GONE      {key}  ({a[key]['display_name']})")
            continue
        if key not in a:
            differences.append(f"NEW       {key}  ({b[key]['display_name']})")
            continue
        (sa, va), (sb, vb) = split(a[key]), split(b[key])
        if sa != sb:
            fields = sorted({k for k in set(sa) | set(sb) if k != "extra" and sa.get(k) != sb.get(k)}
                            | {f"extra.{k}" for k in set(sa["extra"]) | set(sb["extra"])
                               if sa["extra"].get(k) != sb["extra"].get(k)})
            differences.append(f"CHANGED   {key}  ({a[key]['display_name']}): {', '.join(fields)}")
        if va != vb:
            drift.append(f"{a[key]['display_name']}: "
                         + ", ".join(k for k in sorted(set(va) | set(vb)) if va.get(k) != vb.get(k)))
    print(f"{len(a)} games in the saved run, {len(b)} now")
    print(f"log problems now: {after['_log_problems'] or 'none'}")
    print(f"drift (allowed): {len(drift)}")
    for line in drift:
        print("   ", line)
    print(f"differences: {len(differences)}")
    for line in differences:
        print("   ", line)
    return 1 if differences or after["_log_problems"] else 0


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "compare"
    if mode not in ("save", "compare"):
        raise SystemExit("usage: check_scanner.py save|compare")
    raise SystemExit(save() if mode == "save" else compare())
