"""Phase 65: export and import go through the store -- the same bundle, the same merge.

The database, step 2 of 8. `transfer.py` used to open overrides.json and config.json itself;
now the records come from the store (`export_records`) and go back through it
(`import_records`), the settings through `config_io.load_saved`, and Settings hands the
window's own store down to both. The bundle's format and the import's rules -- imported
wins, two session lists combine, nothing is deleted, a backup first -- do not change.

So this suite reads transfer.py as it was at before-phase-65 out of git and runs it beside
today's, on identical copies of the real library: the same members in the bundle, byte for
byte; the same files after an import; the same report. The one difference on purpose: an
import whose write fails now leaves the window's store as it was, not only the file.
Runs on a throwaway copy of the data.
"""
import ast
import dataclasses
import json
import shutil
import subprocess
import sys
import types
import zipfile
from datetime import datetime
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))  # the project folder, one up from tests/
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
TAG = "before-phase-65"

import test_sandbox

box = test_sandbox.start(as_json=True)  # the library as JSON, as the code before the database read it
SANDBOX = box.folder

import logging

logging.basicConfig(level=logging.ERROR)

from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

app = QApplication([])

from data_access import backups, catalog_io, config_io
from logic import transfer
from presentation import ui_settings, ui_transfer, ui_window
from shared import rules

passed = failed = 0
NOW = datetime(2026, 10, 10, 21, 0, 0)


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"   PASS  {name}")
    else:
        failed += 1
        print(f"   FAIL  {name}   {detail}")


def unreached(section: str, exc: Exception):
    """A section that could not run to its end on this code counts as one failure."""
    check(f"section {section} runs to its end on this code", False, repr(exc))


def old_source(relative: str) -> str:
    shown = subprocess.run(["git", "show", f"{TAG}:{relative}"], cwd=PROJECT, check=True,
                           capture_output=True).stdout
    return shown.decode("utf-8-sig").replace("\r\n", "\n")


def old_module(relative: str, name: str):
    module = types.ModuleType(name)
    module.__file__ = str(PROJECT / relative)
    sys.modules[name] = module  # dataclasses look their module up
    exec(compile(old_source(relative), f"{TAG}:{relative}", "exec"), module.__dict__)
    return module


def members(bundle: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(bundle) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


START = {name: (SANDBOX / name).read_bytes() for name in ("overrides.json", "config.json")}
IMPORTED_ART = SANDBOX / "cache" / rules.IMPORTED_ART_DIRNAME


def reset():
    """The sandbox as it was when the suite began: the two files, no imported art, no backups."""
    for name, data in START.items():
        (SANDBOX / name).write_bytes(data)
    shutil.rmtree(IMPORTED_ART, ignore_errors=True)
    shutil.rmtree(SANDBOX / rules.BACKUP_DIRNAME, ignore_errors=True)


def state():
    art = {p.name: p.read_bytes() for p in IMPORTED_ART.glob("*")} if IMPORTED_ART.is_dir() else {}
    return ((SANDBOX / "overrides.json").read_bytes(), (SANDBOX / "config.json").read_bytes(), art)


# Fields a report gained after this phase, each with the value it must hold for a library that
# has none of what it counts -- the JSON these comparisons run on (Phase 74: purchases; Phase 102: ratings).
LATER_FIELDS = {"purchases": 0, "purchases_skipped": 0, "ratings": 0, "ratings_skipped": 0}


def said(report) -> dict:
    """A report as plain values, the backup's time stamp taken out (two runs, two seconds).

    A field the report gained later is taken out too, once it is checked to say nothing --
    the old code's report has no such field, and on this JSON library there is nothing for it
    to count. Anything else it said would make the two reports differ, as it should.
    """
    values = dataclasses.asdict(report)
    values.pop("path", None)
    for name, nothing in LATER_FIELDS.items():
        if name in values and values[name] == nothing:
            values.pop(name)
    stamp = values.pop("backup", "")
    if stamp:
        values["message"] = values["message"].replace(stamp, "<stamp>")
    values["backed_up"] = bool(stamp)
    return values


old_transfer = old_module("logic/transfer.py", "logic.transfer_before_65")
entries, _gone = catalog_io.prune_missing(catalog_io.load_catalog(), catalog_io.Overrides())
known = {entry.identity_key for entry in entries}
records = test_sandbox.records()
print(f"the library: {len(records)} records, {len(known)} games installed")

print("\n=== 1. transfer.py opens none of the launcher's files ===")


def file_calls(source: str) -> list[tuple[int, str]]:
    return [(n.lineno, n.attr) for n in ast.walk(ast.parse(source))
            if isinstance(n, ast.Attribute) and n.attr in ("data_dir", "atomic_write", "read_text")]


now_calls = file_calls((PROJECT / "logic" / "transfer.py").read_text(encoding="utf-8-sig"))
old_calls = file_calls(old_source("logic/transfer.py"))
check("no data_dir(), atomic_write or read_text in transfer.py any more", not now_calls, now_calls)
check("the same search finds them in the code before", len(old_calls) == 4, old_calls)

print("\n=== 2. export: the same bundle, member by member ===")
try:
    for include_key in (True, False):
        for label, store in (("as saved", None), ("from the window's store", catalog_io.Overrides())):
            old_path, new_path = SANDBOX / "old.zip", SANDBOX / "new.zip"
            old_report = old_transfer.export_bundle(old_path, include_key=include_key, now=NOW)
            new_report = transfer.export_bundle(new_path, include_key=include_key, now=NOW, store=store)
            old_members, new_members = members(old_path), members(new_path)
            differ = sorted(n for n in set(old_members) | set(new_members)
                            if old_members.get(n) != new_members.get(n))
            check(f"key {'in' if include_key else 'left out'}, {label}: the same {len(new_members)} members, "
                  f"byte for byte, and the same report",
                  not differ and said(old_report) == said(new_report) and new_report.ok, (differ[:3], said(new_report)))
    check("the store's copy is a copy: changing it changes nothing in the store",
          (lambda s: (s.export_records().clear(), bool(s.export_records()))[1])(catalog_io.Overrides()))
except Exception as exc:
    unreached("2", exc)

print("\n=== 3. import: the same files and the same report afterwards ===")
try:
    plain = SANDBOX / "plain.zip"
    transfer.export_bundle(plain, include_key=False, now=NOW)
    games = json.loads(members(plain)[rules.TRANSFER_RECORDS_MEMBER])
    timed = next(k for k, r in games["games"].items() if r.get("sessions") and k in known)
    mine = games["games"][timed]
    mine["notes"] = "Written on another PC."
    mine["sessions"] = mine["sessions"][:1] + [{"start": "2026-09-01T21:00:00+03:00", "minutes": 30}]
    newcomer = "c:\\games\\a game from another pc"
    games["games"][newcomer] = {"first_seen": "2026-09-01T20:00:00+03:00", "playtime_seconds": 600,
                                "sessions": [{"start": "2026-09-01T20:05:00+03:00", "minutes": 10}]}
    settings = json.loads(members(plain)[rules.TRANSFER_CONFIG_MEMBER])
    settings.update({"library_sort": "Name", "window_geometry": "ANOTHER-PC",
                     "roots": list(settings.get("roots", [])) + ["D:\\more games"]})
    bundle = SANDBOX / f"from-another-pc{rules.TRANSFER_SUFFIX}"
    with zipfile.ZipFile(plain) as source, zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as target:
        for name in source.namelist():
            data = source.read(name)
            if name == rules.TRANSFER_RECORDS_MEMBER:
                data = json.dumps(games, indent=2, ensure_ascii=False).encode("utf-8")
            elif name == rules.TRANSFER_CONFIG_MEMBER:
                data = json.dumps(settings, indent=2).encode("utf-8")
            target.writestr(name, data)
    print(f"   a bundle of {len(games['games'])} records: one changed ({timed}), one new, "
          f"{len(members(bundle)) - 3} artwork files")

    results = {}
    for label in ("old", "new, as saved", "new, the window's store"):
        reset()
        if label == "old":
            report = old_transfer.import_bundle(bundle, known)
        elif label == "new, as saved":
            report = transfer.import_bundle(bundle, known)
        else:
            store = catalog_io.Overrides()
            report = transfer.import_bundle(bundle, known, store=store)
            check("the window's store holds exactly what was written",
                  store.export_records() == test_sandbox.records())
        results[label] = (said(report), state())
    old_said, old_state = results["old"]
    for label in ("new, as saved", "new, the window's store"):
        new_said, new_state = results[label]
        check(f"{label}: overrides.json, config.json and the unpacked artwork are byte for byte the old code's",
              new_state == old_state, [i for i in range(3) if new_state[i] != old_state[i]])
        check(f"{label}: the same report", new_said == old_said, (new_said, old_said))
    after = json.loads(old_state[0])["games"]
    starts = {s["start"] for s in after[timed]["sessions"]}
    check("and the import did what it says: one added, the changed game replaced, its sessions combined",
          old_said["added"] == 1 and timed in old_said["overwritten"] and newcomer in after
          and "2026-09-01T21:00:00+03:00" in starts
          and all(s["start"] in starts for s in json.loads(START["overrides.json"])["games"][timed]["sessions"]),
          (old_said["added"], len(starts)))
    check("a backup was taken first, each time", all(r[0]["backed_up"] for r in results.values()))
except Exception as exc:
    unreached("3", exc)

print("\n=== 4. an import whose write fails ===")
try:
    real_write = backups.atomic_write


    def refuse_overrides(path, text):
        return False if Path(path).name == "overrides.json" else real_write(path, text)


    reset()
    store = catalog_io.Overrides()
    held = store.export_records()
    backups.atomic_write = refuse_overrides
    try:
        old_report = old_transfer.import_bundle(bundle, known)
        old_files = state()
        reset()
        new_report = transfer.import_bundle(bundle, known, store=store)
        new_files = state()
    finally:
        backups.atomic_write = real_write
    check("both say it could not be saved", not new_report.ok and said(old_report) == said(new_report),
          (old_report.message, new_report.message))
    check("and the two files are as they were, both ways",
          old_files[:2] == new_files[:2] == (START["overrides.json"], START["config.json"]))
    check("the window's store is as it was too -- the new game gone again, the changed one put back",
          store.export_records() == held and newcomer not in store.export_records())
except Exception as exc:
    unreached("4", exc)

print("\n=== 5. Settings hands the window's store down ===")
try:
    reset()
    w = ui_window.MainWindow()
    seen = {}


    class Recorder:
        def __init__(self, config, parent=None, known_keys=None, store=None, focus=None,
                     covers=None):  # focus: Phase 77; covers: Phase 105
            seen["dialog"] = store
            self.accentChosen = types.SimpleNamespace(connect=lambda slot: None)  # the swatches' signal (Phase 99)

        def exec(self):
            return int(QDialog.DialogCode.Rejected)


    real_dialog = ui_window.SettingsDialog
    ui_window.SettingsDialog = Recorder
    try:
        w.open_settings()
    finally:
        ui_window.SettingsDialog = real_dialog
    check("opening Settings gives it the window's store", seen.get("dialog") is w.overrides, seen)

    dialog = ui_settings.SettingsDialog(dict(w.config), w, known_keys=set(), store=w.overrides)
    real_flows = ui_transfer.export_flow, ui_transfer.import_flow
    ui_transfer.export_flow = lambda parent, config, store=None: seen.__setitem__("export", store)
    ui_transfer.import_flow = lambda parent, keys, store=None: seen.__setitem__("import", store)
    try:
        dialog._export()
        dialog._import()
    finally:
        ui_transfer.export_flow, ui_transfer.import_flow = real_flows
    dialog.reject()
    check("Settings passes it to export and to import",
          seen.get("export") is w.overrides and seen.get("import") is w.overrides, seen)


    class Files:
        @staticmethod
        def getSaveFileName(*_args, **_kwargs):
            return str(SANDBOX / "chosen.zip"), ""

        @staticmethod
        def getOpenFileName(*_args, **_kwargs):
            return str(bundle), ""


    class Box:
        StandardButton = QMessageBox.StandardButton

        @staticmethod
        def question(*_args, **_kwargs):
            return QMessageBox.StandardButton.Yes

        @staticmethod
        def warning(*_args, **_kwargs):
            return None

        information = warning


    class Options:
        def __init__(self, *_args):
            self.include_key = types.SimpleNamespace(isChecked=lambda: False)

        def exec(self):
            return QDialog.DialogCode.Accepted


    sentinel = object()
    real = (ui_transfer.QFileDialog, ui_transfer.QMessageBox, ui_transfer.ExportDialog,
            transfer.export_bundle, transfer.import_bundle)
    ui_transfer.QFileDialog, ui_transfer.QMessageBox, ui_transfer.ExportDialog = Files, Box, Options
    transfer.export_bundle = lambda *a, store=None, **k: (seen.__setitem__("bundle out", store),
                                                          transfer.ExportReport(False, "stub"))[1]
    transfer.import_bundle = lambda *a, store=None, **k: (seen.__setitem__("bundle in", store),
                                                          transfer.ImportReport(False, "stub"))[1]
    try:
        ui_transfer.export_flow(None, {}, store=sentinel)
        ui_transfer.import_flow(None, set(), store=sentinel)
    finally:
        (ui_transfer.QFileDialog, ui_transfer.QMessageBox, ui_transfer.ExportDialog,
         transfer.export_bundle, transfer.import_bundle) = real
    check("and export and import hand it to transfer",
          seen.get("bundle out") is sentinel and seen.get("bundle in") is sentinel,
          (seen.get("bundle out"), seen.get("bundle in")))
    w.close()
except Exception as exc:
    unreached("5", exc)

print("\n=== 6. the real library is exactly as it was found ===")
changed = box.finish()
check("overrides.json, config.json and catalog.json are byte for byte unchanged", not changed, changed)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
