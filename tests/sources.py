"""Where the project is, and every Python file in it, for checks that read source files.

A check that lists one folder passes with nothing to look at once the files have left that
folder (Phase 38 found two). Reading the whole project instead -- whatever the layout --
keeps such a check honest across moves, and the count of files it read is printed so a
change in what it covers is visible.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # the project folder, one up from tests/

# Folders that hold no source of the project's own: the interpreter, build output, data.
# ".claude": Claude's own working folders -- a task started from this session works in a git
# worktree under .claude/worktrees/, a whole other copy of the project (Phase 93 met one).
NOT_SOURCE = {".venv", ".git", ".claude", "build", "dist", "__pycache__", "data", "cache", "backups",
              "save_backups"}


def python_files() -> list[Path]:
    """Every .py file of the project, in a stable order."""
    found = []
    for folder, subfolders, files in os.walk(ROOT):
        subfolders[:] = sorted(d for d in subfolders if d not in NOT_SOURCE)
        found.extend(Path(folder) / name for name in sorted(files) if name.endswith(".py"))
    return found


def build_log() -> str:
    """The phase notes: docs/ISTORIC.md since Phase 91, which moved every "## Phase N notes" out of
    CLAUDE.md. A suite asks here whether its notes exist; its row stays in CLAUDE.md's table."""
    return (ROOT / "docs" / "ISTORIC.md").read_text(encoding="utf-8")
