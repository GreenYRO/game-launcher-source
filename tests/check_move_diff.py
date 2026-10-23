"""Safety net for a move: nothing changed in the app except import lines.

    .venv\\Scripts\\python.exe tests\\check_move_diff.py before-phase-40       (from the project folder)

The restructure's rule is that files move and imports follow; logic does not change. This
compares the working tree with a restore point (moved files are matched to their old
selves) and sorts every changed line into one of three kinds:

  import  -- an `import ...` / `from ... import ...` line: what a move is allowed to change
  allowed -- a line in a file named with --allow FILE (a path line the step's plan lists)
  other   -- anything else in the app's code: the check fails and prints it

Tests, docs, packaging and CLAUDE.md are reported but never fail it: they describe the
layout and are expected to change with it. New files are listed by name.
"""
from __future__ import annotations

import re
import subprocess
import sys
from collections import defaultdict

import sources

ROOT = sources.ROOT
IMPORT = re.compile(r"^\s*(from\s+[\w.]+\s+import\s+[\w., *]+|import\s+[\w., ]+?(\s+as\s+\w+)?)\s*(#.*)?$")
NOT_APP = ("tests/", "docs/", "packaging/", "CLAUDE.md", ".gitignore")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", check=True).stdout


def main() -> int:
    args = sys.argv[1:]
    if not args or args[0].startswith("-"):
        raise SystemExit("usage: check_move_diff.py <restore point> [--allow FILE ...]")
    base, allowed = args[0], set()
    for flag, value in zip(args[1::2], args[2::2]):
        if flag != "--allow":
            raise SystemExit(f"unknown option {flag}")
        allowed.add(value.replace("\\", "/"))
    diff = git("diff", "-M", "--unified=0", "--no-color", base, "--")
    lines: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    current = None
    for row in diff.splitlines():
        if row.startswith("+++ "):
            current = row[6:] if row.startswith("+++ b/") else current
        elif row.startswith("--- "):
            current = row[6:] if row.startswith("--- a/") else None
        elif row.startswith(("+", "-")) and current:
            text = row[1:]
            if not text.strip():
                continue
            kind = "import" if IMPORT.match(text) else "allowed" if current in allowed else "other"
            lines[current][kind].append(row)
    renames = [r for r in git("diff", "-M", "--name-status", base, "--").splitlines() if r.startswith("R")]
    untracked = git("ls-files", "--others", "--exclude-standard").split()

    failing = 0
    for path in sorted(lines):
        kinds = lines[path]
        app = not path.startswith(NOT_APP)
        summary = ", ".join(f"{len(v)} {k}" for k, v in sorted(kinds.items()))
        print(f"{path}: {summary}{'' if app else '   (layout file, reported only)'}")
        if app and kinds.get("other"):
            failing += len(kinds["other"])
            for row in kinds["other"]:
                print(f"      NOT AN IMPORT  {row[:150]}")
    print(f"\nmoved: {len(renames)} file(s)")
    print(f"new, not yet in git: {len(untracked)} file(s)" + "".join(f"\n   {u}" for u in untracked))
    print(f"app lines that are not imports: {failing}")
    return 1 if failing else 0


if __name__ == "__main__":
    raise SystemExit(main())
