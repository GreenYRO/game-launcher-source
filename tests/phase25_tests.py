"""Phase 25: uninstalling, tiered by who owns the install.

**Nothing in this file touches a real game, and nothing runs a real store uninstaller.**
Every destructive step operates on folders this file creates inside its own sandbox root,
and the sandbox is photographed before and after. The real library is read to check that
the *tiers* come out right -- which is a pure calculation -- and is never acted on.

The one genuinely destructive check sends a fabricated folder to the Recycle Bin and
confirms it arrived, by counting the bin before and after with SHQueryRecycleBin.
"""
import copy
import ctypes
import json
import os
import shutil
import sys
import tempfile
import time
from ctypes import wintypes
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # the project folder, one up from tests/
os.chdir(Path(__file__).resolve().parents[1])

import logging

logging.basicConfig(level=logging.ERROR)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REAL = Path(__file__).resolve().parents[1] / "data"  # the real data, in its own folder since Phase 48

passed = failed = 0


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"   PASS  {name}")
    else:
        failed += 1
        print(f"   FAIL  {name}   {detail}")


import test_sandbox  # the library helpers (Phase 66); the sandbox itself is run_sandboxed's

test_sandbox.require_sandbox(__file__)  # never on the real data, run bare (Phase 101)

overrides_before = test_sandbox.real_records()
overrides_stamp = test_sandbox.real_stamp()
config_before = (REAL / "config.json").read_text(encoding="utf-8")

from data_access import catalog_io
from data_access import config_io
from logic import removal
from shared import rules


class SHQUERYRBINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("i64Size", ctypes.c_int64),
        ("i64NumItems", ctypes.c_int64),
    ]


def bin_state(drive="C:\\"):
    info = SHQUERYRBINFO()
    info.cbSize = ctypes.sizeof(SHQUERYRBINFO)
    hr = ctypes.windll.shell32.SHQueryRecycleBinW(ctypes.c_wchar_p(drive), ctypes.byref(info))
    return (info.i64NumItems, info.i64Size) if hr == 0 else (None, None)


class FakeEntry:
    def __init__(self, source, install_dir, source_id="", size=0):
        self.source = source
        self.install_dir = install_dir
        self.source_id = source_id
        self.size_on_disk = size
        self.launch_kind = "exe" if source == "folders" else "uri"
        self.launch_target = os.path.join(install_dir, "game.exe")


class FakeView:
    def __init__(self, name, source, install_dir, source_id="", size=0):
        self.display_name = name
        self.key = install_dir or f"{source}:{source_id}"
        self.entry = FakeEntry(source, install_dir, source_id, size)


class FakeTracker:
    def __init__(self, running=()):
        self._running = set(running)

    def is_running(self, key):
        return key in self._running


# A sandbox root that stands in for a configured scan root. Nothing real is inside it.
SANDBOX = Path(tempfile.mkdtemp(prefix="p25_root_", dir="C:\\"))
subject_key = ""
subject_record = None
SANDBOX_CONFIG = {"roots": [str(SANDBOX)]}
print(f"\nsandbox scan root: {SANDBOX}")


def plant(name, files=(("game.exe", 40_000),), extra_root_files=()):
    """Create a fabricated game folder inside the sandbox and return its path."""
    folder = SANDBOX / name
    (folder / "Data").mkdir(parents=True, exist_ok=True)
    for rel, size in files:
        target = folder / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(os.urandom(size))
    for rel in extra_root_files:
        (folder / rel).write_bytes(os.urandom(1000))
    return folder


try:
    print("\n=== 1. the tiers, against the real library (calculated, never acted on) ===")
    config = config_io.load_config()
    held = test_sandbox.library()
    views = catalog_io.merge(held.load_catalog(), held)
    held.close()
    visible = [v for v in views if not v.hidden and not v.is_non_game]
    tiers = {}
    for view in visible:
        tiers.setdefault(removal.plan(view, config).tier, []).append(view)
    print("   " + ", ".join(f"{t}: {len(v)}" for t, v in sorted(tiers.items())))

    deleting = tiers.get(rules.TIER_DELETE, [])
    check("only folder-scanner games reach the deleting tier",
          all(v.entry.source == "folders" for v in deleting),
          {v.entry.source for v in deleting})
    check("every Steam game is handed to Steam",
          all(removal.plan(v, config).tier == rules.TIER_STORE
              for v in visible if v.entry.source == "steam"))
    check("and by its own uninstall URI",
          all(removal.plan(v, config).target
              == rules.STEAM_UNINSTALL_URI.format(appid=v.entry.source_id)
              for v in visible if v.entry.source == "steam"))
    for source in ("epic", "xbox", "ubisoft"):
        those = [v for v in visible if v.entry.source == source]
        if those:
            plan = removal.plan(those[0], config)
            print(f"   {source}: {plan.tier} -> {plan.button}")
            check(f"a {source} game only opens its owner", plan.tier == rules.TIER_OWNER)
            check(f"   and the {source} button does not claim to uninstall",
                  "uninstall" not in plan.button.casefold(), plan.button)
    check("every deleting target is inside a configured scan root",
          all(removal.under_scan_root(removal.plan(v, config).target, config)
              for v in deleting))

    print("\n=== 2. the safety rules refuse, one at a time ===")
    inside = plant("A Fabricated Game")
    good = FakeView("A Fabricated Game", "folders", str(inside), size=41_000)
    check("a folder game inside the root is allowed",
          removal.plan(good, SANDBOX_CONFIG).tier == rules.TIER_DELETE)

    outside_dir = Path(tempfile.mkdtemp(prefix="p25_outside_"))
    outside = FakeView("Outside", "folders", str(outside_dir))
    plan = removal.plan(outside, SANDBOX_CONFIG)
    print(f"   outside a scan root -> {plan.tier}: {plan.blocked[:60]}")
    check("a folder outside every scan root refuses", plan.tier == rules.TIER_BLOCKED)
    check("and says so in terms of the folder", str(outside_dir) in plan.blocked)

    as_root = FakeView("Loose exe", "folders", str(SANDBOX))
    plan = removal.plan(as_root, SANDBOX_CONFIG)
    print(f"   the scan root itself -> {plan.tier}")
    check("an entry that IS a scan root refuses -- one loose exe must not take the lot",
          plan.tier == rules.TIER_BLOCKED)

    running = removal.plan(good, SANDBOX_CONFIG, FakeTracker({good.key}))
    print(f"   while running -> {running.tier}: {running.blocked[:60]}")
    check("a running game refuses", running.tier == rules.TIER_BLOCKED)
    check("and tells you to stop it first", "Stop it first" in running.blocked)
    check("the same game not running is allowed again",
          removal.plan(good, SANDBOX_CONFIG, FakeTracker()).tier == rules.TIER_DELETE)

    missing = FakeView("Gone", "folders", str(SANDBOX / "not here"))
    check("a folder already gone refuses rather than pretending",
          removal.plan(missing, SANDBOX_CONFIG).tier == rules.TIER_BLOCKED)

    for source in ("steam", "epic", "xbox", "ubisoft", "gog"):
        other = FakeView(source, source, str(inside), source_id="1")
        check(f"a {source} game never reaches the deleting tier",
              removal.plan(other, SANDBOX_CONFIG).tier != rules.TIER_DELETE)
        check(f"   and perform() would not delete for {source}",
              not removal.plan(other, SANDBOX_CONFIG).deletes)

    print("\n=== 3. an uninstaller at the folder root wins over deleting ===")
    with_unins = plant("Has An Uninstaller", extra_root_files=("unins000.exe",))
    view = FakeView("Has An Uninstaller", "folders", str(with_unins))
    plan = removal.plan(view, SANDBOX_CONFIG)
    print(f"   -> {plan.tier}: {plan.button} ({os.path.basename(plan.target)})")
    check("its own uninstaller is offered first", plan.tier == rules.TIER_UNINSTALLER)
    check("and that tier does not delete anything itself", not plan.deletes)
    check("the target is the uninstaller that was found",
          os.path.basename(plan.target).casefold() == "unins000.exe")

    nested = plant("Uninstaller One Level Down")
    (nested / "Uninstall").mkdir(exist_ok=True)
    (nested / "Uninstall" / "unins000.exe").write_bytes(b"x")
    check("an uninstaller in a subfolder is NOT used -- only the root is trusted",
          removal.plan(FakeView("n", "folders", str(nested)), SANDBOX_CONFIG).tier
          == rules.TIER_DELETE)
    check("uninstaller_at_root ignores a non-exe of the same name",
          removal.uninstaller_at_root(str(plant("Dat Only", extra_root_files=("unins000.dat",))))
          is None)

    print("\n=== 4. GOG's recorded uninstaller, read off this machine ===")
    gog = [v for v in visible if v.entry.source == "gog"]
    if gog:
        found = removal.gog_uninstall_command(gog[0].entry.source_id)
        print(f"   {gog[0].display_name}: {found}")
        check("GOG records one for the installed game", bool(found))
        check("and the file it names is really there", found and os.path.isfile(found))
        check("so GOG gets the uninstaller tier, not a 'open the client' fallback",
              removal.plan(gog[0], config).tier == rules.TIER_UNINSTALLER)
    check("an unknown GOG id yields nothing rather than a guess",
          removal.gog_uninstall_command("0000000000") is None)
    check("an empty id is not looked up at all",
          removal.gog_uninstall_command("") is None)

    print("\n=== 5. the delete itself: a fabricated folder to the Recycle Bin ===")
    victim = plant("Doomed Fabrication",
                   files=(("game.exe", 120_000), ("Data/assets.pak", 380_000)))
    planted = sum(f.stat().st_size for f in victim.rglob("*") if f.is_file())
    before_n, before_b = bin_state()
    print(f"   planted {victim} ({planted:,} bytes); bin holds {before_n} items")

    view = FakeView("Doomed Fabrication", "folders", str(victim), size=planted)
    plan = removal.plan(view, SANDBOX_CONFIG)
    check("it is the deleting tier", plan.tier == rules.TIER_DELETE)
    # interactive=False only so this never blocks on a dialog nobody is here to click.
    ok, message = removal.perform(plan, interactive=False)
    after_n, after_b = bin_state()
    print(f"   perform -> ok={ok} {message!r}; bin now {after_n} items "
          f"(+{after_b - before_b:,} bytes)")
    check("it reported success", ok, message)
    check("the folder is gone from disk", not victim.exists())
    check("it went to the Recycle Bin, not into thin air", after_n > before_n)
    check("and the bin grew by what was planted", after_b - before_b == planted,
          (after_b - before_b, planted))
    check("the sandbox root itself is untouched", SANDBOX.is_dir())
    check("its siblings are untouched", (SANDBOX / "A Fabricated Game").is_dir())

    print("\n=== 6. nothing here can permanently delete ===")
    # Grepping the file text matches removal.py's own docstring, which names the very
    # things it promises not to do. Strip comments and strings first, then read the code.
    import tokenize

    code_only = []
    with open(removal.__file__, "rb") as fh:  # the file actually imported, wherever it lives
        for tok in tokenize.tokenize(fh.readline):
            if tok.type not in (tokenize.COMMENT, tokenize.STRING):
                code_only.append(tok.string)
    code = " ".join(code_only)
    for forbidden in ("rmtree", "unlink", "rmdir"):
        check(f"no {forbidden} anywhere in the code", forbidden not in code, forbidden)
    check("shutil is not even imported, so rmtree is out of reach",
          not hasattr(removal, "shutil"))

    # The flag that makes this recoverable, checked from what the shell is actually handed
    # rather than from how the source happens to read.
    captured = []
    real_op = removal.shell.SHFileOperation

    def spy(args):
        captured.append(args)
        return (0, False)

    decoy = plant("Flag Spy")
    removal.shell.SHFileOperation = spy
    try:
        for interactive in (True, False):
            captured.clear()
            removal.send_to_recycle_bin(str(decoy), interactive=interactive)
            flags = captured[0][4]
            undo = bool(flags & removal.shellcon.FOF_ALLOWUNDO)
            print(f"   interactive={interactive}: flags=0x{flags:x} ALLOWUNDO={undo}")
            check(f"the undo flag is set with interactive={interactive}", undo)
            check(f"   and the operation is a delete with interactive={interactive}",
                  captured[0][1] == removal.shellcon.FO_DELETE)
        captured.clear()
        removal.send_to_recycle_bin(str(decoy), interactive=True)
        check("the app's own path sets no silencing flags, so Windows can still warn",
              not (captured[0][4] & removal.shellcon.FOF_NOCONFIRMATION))
    finally:
        removal.shell.SHFileOperation = real_op
    check("a missing folder is refused before the shell is called",
          removal.send_to_recycle_bin(str(SANDBOX / "nope"), interactive=False)[0] is False)
    check("an empty path is refused too",
          removal.send_to_recycle_bin("", interactive=False)[0] is False)

    print("\n=== 7. the confirmation, and the three surfaces ===")
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QMessageBox

    from presentation import ui_actions
    from presentation import ui_removal
    from presentation import ui_window

    app = QApplication.instance() or QApplication([])
    win = ui_window.MainWindow()
    win.resize(1400, 950)
    win.show()

    def pump(seconds=0.5):
        end = time.time() + seconds
        while time.time() < end:
            app.processEvents()
            time.sleep(0.02)

    pump(1.5)
    # A folder game with no customisation of its own, so nothing chosen by hand is ever
    # the subject of a destructive-looking test. Section 9 starts a real process under this
    # game's key, which banks playtime against it, so its whole record is deep-copied here
    # and put back in the finally -- the rule this project learned the hard way, twice.
    CUSTOM_KEYS = {"cover", "banner", "name", "exe", "args", "favorite", "is_tool"}
    candidates = [
        v for v in win.views
        if v.entry.source == "folders" and not v.hidden and not v.is_non_game
        and not (CUSTOM_KEYS & set(win.overrides.get(v.key)))
    ]
    subject = candidates[0] if candidates else next(
        v for v in win.views
        if v.entry.source == "folders" and not v.hidden and not v.is_non_game
    )
    subject_key = subject.key
    subject_record = copy.deepcopy(win.overrides.get(subject_key))
    print(f"   subject for the dialog checks: {subject.display_name}")
    print(f"   its record before: {subject_record}")

    seen = {}

    attempts = {"n": 0}

    def inspect_and_cancel():
        box = QApplication.activeModalWidget()
        if not isinstance(box, QMessageBox):
            # Bounded, never open-ended: an unbounded retry turns "the dialog did not
            # appear" into a hang instead of a failure.
            attempts["n"] += 1
            if attempts["n"] < 30:
                QTimer.singleShot(100, inspect_and_cancel)
            return
        seen["text"] = box.text() + " " + box.informativeText()
        seen["default"] = box.defaultButton().text() if box.defaultButton() else ""
        seen["escape"] = box.escapeButton().text() if box.escapeButton() else ""
        seen["focus"] = box.focusWidget().text() if box.focusWidget() else ""
        seen["buttons"] = [b.text() for b in box.buttons()]
        for button in box.buttons():
            if button.text() == "Cancel":
                button.click()
                return
        box.reject()

    QTimer.singleShot(300, inspect_and_cancel)
    ui_removal.uninstall(win, subject)
    pump(1.2)

    print(f"   dialog buttons: {seen.get('buttons')}")
    print(f"   default={seen.get('default')!r} escape={seen.get('escape')!r} "
          f"focus={seen.get('focus')!r}")
    check("the dialog names the game", subject.display_name in seen.get("text", ""))
    check("it shows the full path",
          subject.entry.install_dir in seen.get("text", ""), seen.get("text", "")[:120])
    check("it shows the size on disk",
          not subject.entry.size_on_disk
          or "GB" in seen.get("text", "") or "MB" in seen.get("text", ""))
    check("it promises playtime and artwork are kept",
          "playtime" in seen.get("text", "").casefold())
    check("Cancel is the default button", seen.get("default") == "Cancel")
    check("Cancel is what Escape does", seen.get("escape") == "Cancel")
    check("and Cancel is what has the focus, so a stray pad A does nothing",
          seen.get("focus") == "Cancel")
    check("cancelling left the folder alone", os.path.isdir(subject.entry.install_dir))

    menu = ui_actions.build_menu(win, subject)
    labels = [a.text() for a in menu.actions()]
    print(f"   menu ends with: {labels[-1]!r}")
    check("the right-click menu offers it", any("..." in l for l in labels[-1:]))
    check("labelled with the tier, not a flat 'Uninstall'",
          labels[-1].startswith(removal.plan(subject, win.config, win.tracker).button))

    win.show_detail(subject.key)
    pump(0.6)
    button = win.detail.uninstall_button
    print(f"   detail button reads: {button.text()!r}")
    check("the detail page has the button",
          button.isVisible() and bool(button.text()))
    check("and it says what this game's source actually allows",
          button.text().startswith(removal.plan(subject, win.config, win.tracker).button))

    steam = next((v for v in win.views if v.entry.source == "steam" and not v.hidden), None)
    if steam is not None:
        win.show_detail(steam.key)
        pump(0.5)
        print(f"   a Steam game's button reads: {win.detail.uninstall_button.text()!r}")
        check("a Steam game's button promises only what Steam allows",
              "Steam" in win.detail.uninstall_button.text())
    xbox = next((v for v in win.views if v.entry.source == "xbox" and not v.hidden), None)
    if xbox is not None:
        win.show_detail(xbox.key)
        pump(0.5)
        print(f"   an Xbox game's button reads: {win.detail.uninstall_button.text()!r}")
        check("an Xbox game's button offers to open Windows, not to uninstall",
              "Open" in win.detail.uninstall_button.text())

    print("\n=== 8. the storage page offers it on a row ===")
    win.show_storage()
    pump(0.8)
    page = win.storage_page
    page.select_first()
    pump(0.2)
    # The window's own slot opens a real context menu, and QMenu.exec blocks until
    # something dismisses it -- which in a test is nothing, so it hangs. Take the window's
    # handler off first and listen for the signal alone.
    page.contextRequested.disconnect()
    captured = []
    page.contextRequested.connect(lambda key, _pos: captured.append(key))
    page.context_for_current()
    pump(0.3)
    print(f"   the pad's Menu on a storage row asked for: {captured}")
    check("a storage row raises the same menu", bool(captured))
    check("for a real game", captured and captured[0] in win.by_key)

    print("\n=== 9. a running game is refused all the way through the UI ===")
    from logic import launch

    script = SANDBOX / "busy.bat"
    script.write_text("@echo off\r\nping 127.0.0.1 -n 60 >nul\r\n", encoding="ascii")
    handle, _pid, job = launch._spawn_in_job(f'"{script}"', str(SANDBOX))
    win.tracker.add(launch.RunningGame(key=subject.key, name=subject.display_name,
                                       started=time.perf_counter(), handle=handle, job=job,
                                       tracks_tree=job is not None))
    win.show_detail(subject.key)
    pump(0.5)
    print(f"   while running, the button reads: {win.detail.uninstall_button.text()!r}")
    check("the plan refuses while it runs",
          removal.plan(subject, win.config, win.tracker).tier == rules.TIER_BLOCKED)

    told = {}

    tries = {"n": 0}

    def read_refusal():
        box = QApplication.activeModalWidget()
        if not isinstance(box, QMessageBox):
            tries["n"] += 1
            if tries["n"] < 30:
                QTimer.singleShot(100, read_refusal)
            return
        told["text"] = box.text()
        box.accept()

    QTimer.singleShot(300, read_refusal)
    ui_removal.uninstall(win, subject)
    pump(1.2)
    print(f"   it explained: {told.get('text', '')[:70]}")
    check("the user is told why rather than nothing happening",
          "running" in told.get("text", "").casefold())
    check("and the folder is still there", os.path.isdir(subject.entry.install_dir))

    win.tracker.stop(subject.key)
    for _ in range(20):
        win._poll_playtime()
        pump(0.2)
        if not win.tracker.is_running(subject.key):
            break
    win.close()
    pump(0.4)

finally:
    shutil.rmtree(SANDBOX, ignore_errors=True)
    try:
        shutil.rmtree(outside_dir, ignore_errors=True)
    except NameError:
        pass
    print(f"\nsandbox removed: {not SANDBOX.exists()}")
    # Put the subject's record back exactly as it was found, whatever went wrong above.
    # Section 9 runs a real process under its key, which banks playtime against it.
    if subject_key and subject_record is not None:
        store = test_sandbox.library()
        if store.get(subject_key) != subject_record:
            test_sandbox.put_records({subject_key: subject_record}, store)
            print(f"restored {subject_key} to the record it had before this run")
        else:
            print("the subject's record was never disturbed")
        store.close()

print("\n=== 10. the real library is exactly as it was found ===")
# Section 9 starts a real process under the subject's key, so playtime genuinely is banked
# and the file genuinely is written. Asserting the mtime never moves would be asserting
# that the launcher failed to do its job. What must hold is that every record came back
# exactly as it was found.
written = test_sandbox.real_stamp() != overrides_stamp
print(f"   overrides.json was written during this run: {written}")
now_records = test_sandbox.real_records()
check("every record is exactly as it was found", now_records == overrides_before)
differing = [
    key for key in set(now_records) | set(overrides_before)
    if now_records.get(key) != overrides_before.get(key)
]
check("no game's record differs, not even by a second of playtime", not differing, differing)
after = json.loads((REAL / "config.json").read_text(encoding="utf-8"))
original = json.loads(config_before)
changed = {k for k in set(after) | set(original) if after.get(k) != original.get(k)}
print(f"   config keys that changed: {sorted(changed) or 'none'}")
check("config.json is unchanged", changed <= {"storage_sort", "tv_mode", "tv_scale"},
      sorted(changed))
if changed:
    (REAL / "config.json").write_text(config_before, encoding="utf-8")
    print("   (put config.json back exactly as it was found)")

still_here = [v for v in catalog_io.merge(catalog_io.load_catalog(), catalog_io.Overrides())
              if v.entry.source == "folders" and v.entry.install_dir]
gone = [v.display_name for v in still_here if not os.path.isdir(v.entry.install_dir)]
print(f"   folder games whose directory is missing: {gone or 'none'}")
check("no real game folder was removed by this test run", not gone, gone)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
