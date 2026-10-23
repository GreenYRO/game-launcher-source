"""Safety net for the thesis copy only: the original launcher folder is never touched.

    .venv\\Scripts\\python.exe tests\\check_original.py save       (before a run)
    .venv\\Scripts\\python.exe tests\\check_original.py compare    (after it)

This project folder is a copy of the user's daily launcher, which lives in ORIGINAL and is
read-only for the app, for every test and for whoever works here: this copy's
overrides.json points into the original's cache, so a careless write would land there.
The check records every file in the original -- path, size, time modified -- and later
lists anything added, removed or changed. It only reads.

If the user's own launcher was open during the run, its own writes (its log, its
overrides.json, its cache) show up here too; the list says which files, so it can be told
apart from a stray write by a test.
"""
from __future__ import annotations

import json
import os
import sys

import sources

ORIGINAL = r"C:\Users\andre\Game Launcher"
FINGERPRINT = sources.ROOT / "tests" / "baseline" / "original.json"


def fingerprint() -> dict:
    rows = {}
    for folder, _subfolders, files in os.walk(ORIGINAL):
        for name in files:
            path = os.path.join(folder, name)
            try:
                st = os.stat(path)
                rows[os.path.relpath(path, ORIGINAL)] = [st.st_size, st.st_mtime_ns]
            except OSError as exc:
                rows[os.path.relpath(path, ORIGINAL)] = ["unreadable", str(exc)]
    return rows


def main(mode: str) -> int:
    if not os.path.isdir(ORIGINAL):
        print(f"{ORIGINAL} is not here; nothing to guard")
        return 0
    if mode == "save":
        rows = fingerprint()
        FINGERPRINT.parent.mkdir(exist_ok=True)
        FINGERPRINT.write_text(json.dumps(rows, sort_keys=True), encoding="utf-8")
        print(f"recorded {len(rows)} files in {ORIGINAL}")
        return 0
    before = json.loads(FINGERPRINT.read_text(encoding="utf-8"))
    after = fingerprint()
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    changed = sorted(k for k in set(before) & set(after) if before[k] != after[k])
    print(f"{ORIGINAL}: {len(before)} files before, {len(after)} after; "
          f"added {len(added)}, removed {len(removed)}, changed {len(changed)}")
    for label, names in (("added", added), ("removed", removed), ("changed", changed)):
        for name in names[:40]:
            print(f"   {label:<8}{name}")
    return 1 if added or removed or changed else 0


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "compare"
    if mode not in ("save", "compare"):
        raise SystemExit("usage: check_original.py save|compare")
    raise SystemExit(main(mode))
