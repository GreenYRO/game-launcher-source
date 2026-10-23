"""Safety net: dependencies point one way only -- down the layers.

    .venv\\Scripts\\python.exe tests\\check_layers.py       (from the project folder)

The layers, top to bottom (docs/ARHITECTURA.md, section 2):

    entry points   launcher.py, scanner.py, compare_exports.py
    presentation   what the user sees and touches
    adapters       Qt glue that draws nothing: threads, the pad, watched folders, icons
    logic          the launcher's rules, no Qt
    providers      where installed games are read from
    web            the only code that talks to the internet
    data_access    the launcher's own files
    shared         the basics every layer uses

A module may import its own layer or any layer below it, never one above. Every import is
read from the source -- the ones inside functions too -- so a dependency that only exists
on the day somebody clicks a button is still seen. Skipping a layer (presentation reading
data_access directly) is allowed: that is relaxed layering, and it is counted, not failed.

And since Phase 67: the standard library's sqlite3 is imported in data_access/ and nowhere
else. Every SQL statement of the launcher lives there; a query in presentation/ or logic/
is a layering bug, and this net says so.
"""
from __future__ import annotations

import ast
import sys
from collections import Counter, defaultdict

import sources

ROOT = sources.ROOT
ORDER = ["entry", "presentation", "adapters", "logic", "providers", "web", "data_access", "shared"]
ENTRY = {"launcher", "scanner", "compare_exports", "reports"}  # compare_exports: Phase 81; reports: Phase 83
NOT_APP = {"tests", "packaging", "docs"}


def layer_of(module: str) -> str | None:
    top = module.split(".")[0]
    if top in ENTRY:
        return "entry"
    return top if top in ORDER else None


SQL_LAYER = "data_access"  # the only layer that may import sqlite3 (Phase 67)


def imports_in(source: str) -> list[tuple[int, str]]:
    """Every module a source file imports, with its line, the ones inside functions too."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.extend((node.lineno, a.name) for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.append((node.lineno, node.module))
    return found


def sql_outside(rel, here: str, source: str) -> list[str]:
    """An import of sqlite3 in any layer but data_access."""
    if here == SQL_LAYER:
        return []
    return [f"{rel}:{line}: {here} imports {target} -- SQL lives in {SQL_LAYER}/ only"
            for line, target in imports_in(source) if target.split(".")[0] == "sqlite3"]


def main() -> int:
    edges: Counter = Counter()
    upward: list[str] = []
    sql: list[str] = []
    graph: dict[str, set[str]] = defaultdict(set)
    modules = 0
    for path in sources.python_files():
        rel = path.relative_to(ROOT)
        if rel.parts[0] in NOT_APP:
            continue
        name = ".".join(rel.with_suffix("").parts).removesuffix(".__init__")
        here = layer_of(name)
        if here is None:
            print(f"   not in any layer: {rel}")
            upward.append(f"{rel}: not in any layer")
            continue
        modules += 1
        source = path.read_text(encoding="utf-8-sig")
        sql.extend(sql_outside(rel, here, source))
        for line, target in imports_in(source):
            there = layer_of(target)
            if there is None:
                continue  # the standard library or an installed package
            edges[(here, there)] += 1
            graph[name].add(target)
            if ORDER.index(there) < ORDER.index(here):
                upward.append(f"{rel}:{line}: {here} imports {target} ({there}, a layer above)")

    print(f"{modules} app modules in {len(ORDER)} layers")
    print("imports between layers (each line: from -> to: how many):")
    for (a, b), n in sorted(edges.items(), key=lambda kv: (ORDER.index(kv[0][0]), ORDER.index(kv[0][1]))):
        if a != b:
            kind = "UP" if ORDER.index(b) < ORDER.index(a) else "down"
            print(f"   {a:<13}-> {b:<13}{n:>4}   {kind}")
    within = sum(n for (a, b), n in edges.items() if a == b)
    print(f"   (and {within} imports inside a layer)")
    print(f"upward imports: {len(upward)}")
    for line in upward:
        print("   ", line)
    print(f"sqlite3 outside {SQL_LAYER}/: {len(sql)}")
    for line in sql:
        print("   ", line)
    return 1 if upward or sql else 0


if __name__ == "__main__":
    raise SystemExit(main())
