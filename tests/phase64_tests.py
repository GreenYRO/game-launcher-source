"""Phase 64: the places that reached into the store now ask it by name -- still on JSON.

The database (Phases 64-71) changes how the library is stored, never what the launcher does.
Its first step: nothing outside data_access/ may reach into `Overrides.games` or call
`save()` any more. Lineage's carry-over, the window's four, and Storage's "sizes as of"
time now go through operations on the store -- `values_of`, `uncarried`, `update_many`,
`carry`, `last_scan_time` -- so that later only the inside of the store changes.

Storage changes, behaviour does not. So this suite reads the code as it was at
before-phase-64 out of git and runs it beside the code as it is, on identical copies of
the real library, and asks for the same records, the same file bytes and the same answers.
The one difference on purpose: a carry that fails half way now changes nothing at all.
Runs on a throwaway copy of the data.
"""
import __future__
import ast
import copy
import dataclasses
import shutil
import subprocess
import sys
import types
from datetime import datetime
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))  # the project folder, one up from tests/
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
TAG = "before-phase-64"

import test_sandbox

box = test_sandbox.start(as_json=True)  # the library as JSON, as the code before the database read it
SANDBOX = box.folder
if (test_sandbox.REAL / "save_backups").is_dir():  # so earlier installs count their copies
    shutil.copytree(test_sandbox.REAL / "save_backups", SANDBOX / "save_backups")  # a copy, read only

import logging

logging.basicConfig(level=logging.ERROR)

from PySide6.QtWidgets import QApplication

app = QApplication([])

import sources
from data_access import catalog_io
from logic import lineage, saves, storage
from presentation import ui_window

passed = failed = 0
FUTURE = __future__.annotations.compiler_flag
NOW = datetime(2026, 10, 10, 20, 0, 0)


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"   PASS  {name}")
    else:
        failed += 1
        print(f"   FAIL  {name}   {detail}")


def old_source(relative: str) -> str:
    """A file as it was at the restore point, read out of git."""
    shown = subprocess.run(["git", "show", f"{TAG}:{relative}"], cwd=PROJECT, check=True,
                           capture_output=True).stdout
    return shown.decode("utf-8-sig").replace("\r\n", "\n")


def old_module(relative: str, name: str):
    module = types.ModuleType(name)
    module.__file__ = str(PROJECT / relative)
    sys.modules[name] = module  # dataclasses look their module up
    exec(compile(old_source(relative), f"{TAG}:{relative}", "exec"), module.__dict__)
    return module


def function_from(source: str, name: str, where: str, space: dict, cls: str | None = None):
    """One function (or one class's method) compiled out of a file, with a module's names."""
    body = ast.parse(source).body
    if cls is not None:
        body = next(n for n in body if isinstance(n, ast.ClassDef) and n.name == cls).body
    node = next(n for n in body if isinstance(n, ast.FunctionDef) and n.name == name)
    found: dict = {}
    exec(compile(ast.Module([node], []), f"{where}:{name}", "exec", flags=FUTURE, dont_inherit=True),
         space, found)
    return found[name]


def known_line(source: str):
    """The `known = ...` expression in MainWindow._on_scanned, compiled."""
    klass = next(n for n in ast.parse(source).body if isinstance(n, ast.ClassDef) and n.name == "MainWindow")
    method = next(n for n in klass.body if isinstance(n, ast.FunctionDef) and n.name == "_on_scanned")
    assign = next(n for n in ast.walk(method) if isinstance(n, ast.Assign)
                  and isinstance(n.targets[0], ast.Name) and n.targets[0].id == "known")
    return compile(ast.Expression(assign.value), "known", "eval")


def store_with(games: dict, name: str):
    """A store of its own in the sandbox, holding a copy of `games`, counting its writes from now."""
    store = test_sandbox.separate_store(f"store-{name}", games, kind="json")
    path = store.path
    writes = []
    real_save = store.save

    def counted():
        writes.append(1)
        return real_save()

    store.save = counted
    return store, writes, path


def outcome(carry, store, old_key, new_key, **kwargs):
    try:
        return ("carried", dataclasses.asdict(carry(store, old_key, new_key, now=NOW, **kwargs)))
    except (LookupError, ValueError) as exc:
        return (type(exc).__name__, str(exc))


class Window:
    """What the window's methods ask of `self`, and nothing else."""

    def __init__(self, store, views=(), by_key=None):
        self.overrides = store
        self.views = list(views)
        self.by_key = dict(by_key or {})
        self.repaints = 0
        self.library = types.SimpleNamespace(repaint_tiles=self._repainted)

    def _repainted(self):
        self.repaints += 1


# The library as the window has it: the catalogue less what has left the disk, merged.
entries, _gone = catalog_io.prune_missing(catalog_io.load_catalog(), catalog_io.Overrides())
base_store = catalog_io.Overrides()
views = catalog_io.merge(entries, base_store)
by_key = {view.key: view for view in views}
BASE = base_store.export_records()
print(f"the library: {len(BASE)} records, {len(views)} games showing")

old_lineage = old_module("logic/lineage.py", "logic.lineage_before_64")
WINDOW_OLD = old_source("presentation/ui_window.py")
WINDOW_NOW = (PROJECT / "presentation" / "ui_window.py").read_text(encoding="utf-8")
space = vars(ui_window)

print("\n=== 1. nothing outside data_access/ reaches into the store ===")


def reaches_in(source: str) -> list[tuple[int, str]]:
    """`<...>overrides.games` or `<...>overrides.save` anywhere in a file."""
    hits = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Attribute) and node.attr in ("games", "save"):
            inner = node.value
            if (inner.attr if isinstance(inner, ast.Attribute) else getattr(inner, "id", "")) == "overrides":
                hits.append((node.lineno, node.attr))
    return hits


app_files = [p for p in sources.python_files()
             if p.relative_to(PROJECT).parts[0] not in ("tests", "docs", "data_access")]
now_hits = {str(p.relative_to(PROJECT)): reaches_in(p.read_text(encoding="utf-8-sig")) for p in app_files}
now_hits = {name: hits for name, hits in now_hits.items() if hits}
print(f"   read {len(app_files)} app files outside data_access/")
check("no app file outside data_access/ touches overrides.games or calls overrides.save()",
      not now_hits, now_hits)
before = {name: reaches_in(old_source(name)) for name in ("logic/lineage.py", "presentation/ui_window.py")}
count = sum(len(hits) for hits in before.values())
print(f"   at {TAG}: {before}")
check("the same search finds the ten places it replaced in the code before", count == 10, count)

print("\n=== 2. carrying a history over: the same records, the same file ===")
pairs = [(view, earlier) for view in views
         for earlier in lineage.everything(view, base_store, by_key.keys())]
print(f"   {len(pairs)} pairs of a game showing and an earlier install, "
      f"{sum(1 for _v, e in pairs if e.why)} of them a likely match")
mismatch = None
written = []
for view, earlier in pairs:
    old_store, old_writes, old_path = store_with(BASE, "old")
    new_store, new_writes, new_path = store_with(BASE, "new")
    kwargs = dict(new_install_dir=view.entry.install_dir, old_name=earlier.name)
    said_old = outcome(old_lineage.carry_over, old_store, earlier.key, view.key, **kwargs)
    said_new = outcome(lineage.carry_over, new_store, earlier.key, view.key, **kwargs)
    same_file = (old_path.read_bytes() == new_path.read_bytes()) if old_path.exists() else not new_path.exists()
    written.append((len(old_writes), len(new_writes)))
    if said_old != said_new or old_store.export_records() != new_store.export_records() or not same_file:
        mismatch = (view.key, earlier.key, said_old, said_new, same_file)
        break
check(f"for all {len(pairs)} pairs the records, the message and the file are the same",
      bool(pairs) and mismatch is None, mismatch)
check("and every carry writes the store exactly once, as it did",
      bool(written) and all(w == (1, 1) for w in written), sorted(set(written)))

print("\n=== 3. refusals: the same answer, nothing written ===")
carried_key = next((k for k, r in BASE.items() if r.get("carried_to")), None)
some = views[0].key
cases = [("an install nothing is recorded for", "c:\\nowhere\\at all", some)]
if carried_key:
    cases.append(("one already carried over", carried_key, some))
cases.append(("a game onto itself", some, some))
for label, old_key, new_key in cases:
    old_store, old_writes, _ = store_with(BASE, "old")
    new_store, new_writes, _ = store_with(BASE, "new")
    said_old = outcome(old_lineage.carry_over, old_store, old_key, new_key)
    said_new = outcome(lineage.carry_over, new_store, old_key, new_key)
    check(f"{label}: {said_new[0]} both ways, nothing written, nothing changed",
          said_old == said_new and said_new[0] != "carried" and not old_writes and not new_writes
          and new_store.export_records() == BASE, (said_old, said_new, old_writes, new_writes))
if not carried_key:
    print("   (no record here was carried over yet, so that case was not tried)")

print("\n=== 4. a carry that fails half way changes nothing now ===")
subject = next(((v, e) for v, e in pairs if e.playtime_seconds > 0), None)
if subject is None:
    check("there is an earlier install with play time to try it on", False, "none here")
else:
    view, earlier = subject
    real_only = saves.only_save_folders

    def boom(_folders):
        raise RuntimeError("stopped half way, on purpose")

    saves.only_save_folders = boom
    try:
        results = {}
        for label, carry in (("old", old_lineage.carry_over), ("new", lineage.carry_over)):
            store, writes, _ = store_with(BASE, label)
            try:
                carry(store, earlier.key, view.key, new_install_dir=view.entry.install_dir, now=NOW)
            except RuntimeError:
                pass
            results[label] = (store.export_records() == BASE, len(writes))
    finally:
        saves.only_save_folders = real_only
    print(f"   {earlier.name} onto {view.display_name}: unchanged / writes -- "
          f"before {results['old']}, now {results['new']}")
    check("the code before left half a history in memory for the next write to keep",
          results["old"] == (False, 0), results["old"])
    check("now nothing has changed and nothing was written", results["new"] == (True, 0), results["new"])

print("\n=== 5. dropping folders that were never saves ===")
drop_old = function_from(WINDOW_OLD, "_drop_wrong_save_folders", "old", space, cls="MainWindow")
drop_new = ui_window.MainWindow._drop_wrong_save_folders
with_saves = [k for k, r in BASE.items() if r.get("save_dirs")]
planted = copy.deepcopy(BASE)
if len(with_saves) >= 2:
    first, second = with_saves[:2]
    planted[first]["save_dirs"] = planted[first]["save_dirs"] + [r"C:\Somewhere\CrashReports\queue"]
    planted[second]["save_dirs"] = [r"C:\Users\someone\AppData\Roaming\Mozilla\saved-telemetry-pings"]
for label, games in (("with two wrong folders planted", planted), ("on the library as it is", BASE)):
    old_store, old_writes, old_path = store_with(games, "old")
    new_store, new_writes, new_path = store_with(games, "new")
    drop_old(Window(old_store))
    drop_new(Window(new_store))
    same_file = (old_path.read_bytes() == new_path.read_bytes()) if old_path.exists() else not new_path.exists()
    check(f"{label}: the same records, the same file, {len(new_writes)} write(s) both ways",
          old_store.export_records() == new_store.export_records() and same_file and len(old_writes) == len(new_writes),
          (len(old_writes), len(new_writes), same_file))
new_store, new_writes, _p = store_with(planted, "new")
drop_new(Window(new_store))
if len(with_saves) >= 2:
    check("the planted folders went: one dropped from a list, one whole list gone",
          new_store.get(first)["save_dirs"] == BASE[first]["save_dirs"]
          and "save_dirs" not in new_store.get(second),
          (new_store.get(first).get("save_dirs"), new_store.get(second).get("save_dirs")))
else:
    check("there are two records with save folders to plant in", False, with_saves)

print("\n=== 6. the NEW tag taken off ===")
seen_old = function_from(WINDOW_OLD, "mark_seen", "old", space, cls="MainWindow")
seen_new = ui_window.MainWindow.mark_seen
tagged = copy.deepcopy(BASE)
key = views[0].key
tagged[key]["new"] = True
for label, games, target in (("a game tagged NEW", tagged, key),
                             ("a game not tagged", BASE, key),
                             ("a key nothing is recorded for", BASE, "c:\\nowhere\\at all")):
    old_store, old_writes, _ = store_with(games, "old")
    new_store, new_writes, _ = store_with(games, "new")
    old_window, new_window = Window(old_store), Window(new_store)
    seen_old(old_window, target)
    seen_new(new_window, target)
    check(f"{label}: the same records, {len(new_writes)} write(s), {new_window.repaints} repaint(s) both ways",
          old_store.export_records() == new_store.export_records() and len(old_writes) == len(new_writes)
          and old_window.repaints == new_window.repaints, (old_writes, new_writes))
new_store, _w, _p = store_with(tagged, "new")
seen_new(Window(new_store), key)
check("and the tagged one lost its tag, its record otherwise as it was",
      "new" not in new_store.get(key) and new_store.get(key) == BASE[key],
      new_store.get(key).get("new"))

print("\n=== 7. which games the launcher already knew, and every name it knows ===")
store, _w, _p = store_with(BASE, "now")
window = Window(store, views, by_key)
known_old = eval(known_line(WINDOW_OLD), space, {"self": window})
known_new = eval(known_line(WINDOW_NOW), space, {"self": window})
check(f"the games known before a scan: the same {len(known_new)} keys", known_old == known_new,
      known_old ^ known_new)
names_old = function_from(WINDOW_OLD, "other_game_names", "old", space, cls="MainWindow")(window)
names_new = ui_window.MainWindow.other_game_names(window)
check(f"every name for telling saves apart: the same {len(names_new)}", names_old == names_new,
      set(names_old) ^ set(names_new))

print("\n=== 8. earlier installs, as the game page and the menu find them ===")
store_old, _w, _p = store_with(BASE, "old")
store_new, _w, _p = store_with(BASE, "new")
found_old = [(e.key, e.name, e.copies, e.record) for e in old_lineage.earlier_installs(store_old, by_key.keys())]
found_new = [(e.key, e.name, e.copies, e.record) for e in lineage.earlier_installs(store_new, by_key.keys())]
check(f"the same {len(found_new)} earlier installs, in the same order, holding the same",
      found_old == found_new and bool(found_new), (len(found_old), len(found_new)))
check("each hands out the store's own record, which the page reads live",
      all(e.record is store_new.get(e.key) for e in lineage.earlier_installs(store_new, by_key.keys())))

print("\n=== 9. Storage's \"sizes as of\" ===")
when_old = function_from(old_source("logic/storage.py"), "catalog_written_at", "old", vars(storage))
said_old, said_new = when_old(), storage.catalog_written_at()
check("the time of the last scan is the same, and it is there",
      said_old == said_new and said_new is not None, (said_old, said_new))
catalog = catalog_io.CATALOG_PATH
aside = catalog.with_name("catalog.aside")
catalog.rename(aside)
try:
    check("with no catalogue, nothing either way", when_old() is None and storage.catalog_written_at() is None,
          (when_old(), storage.catalog_written_at()))
finally:
    aside.rename(catalog)

print("\n=== 10. the real library is exactly as it was found ===")
changed = box.finish()
check("overrides.json, config.json and catalog.json are byte for byte unchanged", not changed, changed)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
