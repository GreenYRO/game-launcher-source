"""Safety net: every import of a project module resolves, and every module loads once.

    .venv\\Scripts\\python.exe tests\\check_imports.py       (from the project folder)

Two halves, because a move can break an import in two ways.

Static: every `import` / `from ... import` in every project file -- including the ones
inside functions, which only run on the day somebody clicks that button -- must name a
module that exists, and a name that module defines (or a submodule of it). Nothing is
executed for this half.

Live: every module of the app is imported for real, inside a sandbox, and no file may end
up loaded under two names. That is the "paths and shared.paths" trap: Python would load
the file twice, the sandbox would patch one copy and the app would use the other.

Imports written inside strings (the child processes of suites 28, 34 and 35) are not seen
here; those suites fail on their own if such an import goes stale.
"""
from __future__ import annotations

import ast
import importlib
import importlib.util
import os
import sys
from pathlib import Path

import sources

ROOT = sources.ROOT
TESTS = ROOT / "tests"
# Scripts run on their own, never imported by the app: not importable from the root.
NOT_APP = {"tests", "packaging", "docs"}


def module_name(path: Path, base: Path) -> str:
    parts = list(path.relative_to(base).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


FILES = sources.python_files()
APP = {module_name(p, ROOT): p for p in FILES if p.relative_to(ROOT).parts[0] not in NOT_APP}
TEST_MODULES = {module_name(p, TESTS): p for p in FILES if p.parent == TESTS}
PACKAGES = {name for name, p in APP.items() if p.name == "__init__.py"}


def top_level_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    names: set[str] = set()

    def visit(body):
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(node.name)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    names.update(n.id for n in ast.walk(target) if isinstance(n, ast.Name))
            elif isinstance(node, (ast.AnnAssign, ast.AugAssign)) and isinstance(node.target, ast.Name):
                names.add(node.target.id)
            elif isinstance(node, ast.Import):
                names.update((a.asname or a.name).split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                names.update(a.asname or a.name for a in node.names)
            elif isinstance(node, (ast.If, ast.Try, ast.With, ast.For, ast.While)):
                for field in ("body", "orelse", "finalbody"):
                    visit(getattr(node, field, None) or [])
                for handler in getattr(node, "handlers", None) or []:
                    visit(handler.body)

    visit(tree.body)
    return names


_outside: dict[str, bool] = {}


def exists_outside(top: str) -> bool:
    """Whether a top-level module name is the standard library's or installed in the venv."""
    if top not in _outside:
        try:
            spec = importlib.util.find_spec(top)
        except (ImportError, ValueError):
            spec = None
        # Found only because it is a project file still sitting where the name points is
        # not "outside"; the project's own names are checked against the project instead.
        # Built-in and frozen modules report "built-in" / "frozen", not a path.
        origin = Path(spec.origin).resolve() if spec and spec.has_location and spec.origin else None
        _outside[top] = spec is not None and not (
            origin is not None and origin.is_relative_to(ROOT) and ".venv" not in origin.parts)
    return _outside[top]


def static() -> int:
    known = {**APP}
    problems, lines, lazy = [], set(), set()
    for path in FILES:
        rel = path.relative_to(ROOT)
        # A test sees the root's modules and its neighbours in tests/; anything else only the root's.
        visible = {**APP, **TEST_MODULES} if path.parent == TESTS else known
        tops = {name.split(".")[0] for name in visible}
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}

        def inside_function(node) -> bool:
            node = parents.get(node)
            while node is not None:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                    return True
                node = parents.get(node)
            return False

        for node in ast.walk(tree):
            targets = []
            if isinstance(node, ast.Import):
                targets = [(a.name, None) for a in node.names if a.name.split(".")[0] in tops]
                outside = [a.name for a in node.names if a.name.split(".")[0] not in tops]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module \
                    and node.module.split(".")[0] in tops:
                targets = [(node.module, a.name) for a in node.names]
                outside = []
            elif isinstance(node, ast.ImportFrom) and node.level:
                problems.append(f"{rel}:{node.lineno}: relative import -- the project uses absolute ones")
                outside = []
            else:
                outside = [node.module] if isinstance(node, ast.ImportFrom) and node.module else []
            # A name that is not the project's must at least exist outside it. A module that
            # moved leaves its old bare name behind in any line nobody rewrote, and that name
            # is no longer the project's -- so without this, a stale `import stats as s`
            # inside a function passes here and fails only on the day it runs (Phase 44).
            for name in outside:
                if not exists_outside(name.split(".")[0]):
                    problems.append(f"{rel}:{node.lineno}: {name} -- not in the project, not installed")
            if not targets:
                continue
            lines.add((rel, node.lineno))
            if inside_function(node):
                lazy.add((rel, node.lineno))
            for module, name in targets:
                if module not in visible:
                    problems.append(f"{rel}:{node.lineno}: {module} -- no such module")
                elif name and name != "*" and f"{module}.{name}" not in visible \
                        and name not in top_level_names(visible[module]):
                    problems.append(f"{rel}:{node.lineno}: from {module} import {name} -- not defined there")

    print(f"static: {len(FILES)} files, {len(lines)} project import lines, "
          f"{len(lazy)} of them inside functions in {len({f for f, _ in lazy})} files")
    for rel, lineno in sorted(lazy):
        print(f"   inside a function: {rel}:{lineno}")
    print(f"static problems: {len(problems)}")
    for line in problems:
        print("   ", line)
    return len(problems)


def live() -> int:
    import test_sandbox

    box = test_sandbox.start(migrate=False)
    failed = []
    for name in sorted(APP):
        try:
            importlib.import_module(name)
        except Exception as exc:  # report every one, not only the first
            failed.append(f"{name}: {type(exc).__name__}: {exc}")
    loaded: dict[str, list[str]] = {}
    for name, module in list(sys.modules.items()):
        file = getattr(module, "__file__", None)
        if not file or not Path(file).is_file():
            continue  # built-in helpers report files that are not on disk
        resolved = Path(file).resolve()
        if resolved.is_relative_to(ROOT) and ".venv" not in resolved.parts:
            loaded.setdefault(os.path.normcase(str(resolved)), []).append(name)
    twice = {f: names for f, names in loaded.items() if len(names) > 1}
    changed = box.finish()
    print(f"live: imported {len(APP)} app modules; {len(loaded)} project files loaded")
    print(f"live failures: {len(failed)}")
    for line in failed:
        print("   ", line)
    print(f"loaded under two names: {len(twice)}")
    for file, names in twice.items():
        print("   ", file, names)
    print(f"real files changed: {changed or 'none'}")
    return len(failed) + len(twice) + len(changed)


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    raise SystemExit(1 if static() + live() else 0)
