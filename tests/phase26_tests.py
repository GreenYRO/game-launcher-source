"""Phase 26: the small fixes -- choices that stick, new games that stand out, and a log.

**Nothing here touches the real library.** Before a single project module is imported,
paths.data_dir is pointed at a throwaway copy of the data folder, so every window built
below reads and writes that copy. The real overrides.json, config.json and catalog.json
are photographed at the start and compared byte for byte at the end.

The artwork paths inside the copied overrides still point into the real cache; those files
are only ever read. The folder watch is exercised on a scan root this file creates.
"""
import json
import logging
import logging.handlers
import os
import re
import shutil
import sys
import tempfile
import threading
import time
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # the project folder, one up from tests/
os.chdir(Path(__file__).resolve().parents[1])
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import test_sandbox  # the helpers only; this suite keeps its own sandbox

REAL = test_sandbox.REAL  # the real data, in its own folder since Phase 48
REAL_FILES = test_sandbox.REAL_FILES
# What is there now: since the switch (Phase 69) overrides.json and catalog.json are in
# data/migrated/ and the library is library.db, copied read only below.
real_before = {name: test_sandbox.read_real(name) for name in REAL_FILES}

SANDBOX = Path(tempfile.mkdtemp(prefix="p26_data_"))
ROOT = Path(tempfile.mkdtemp(prefix="p26_root_"))  # a stand-in scan root for the watcher
GAMES = SANDBOX / "games"  # fabricated game folders, so a pruned catalogue keeps them
SHOTS = Path(tempfile.gettempdir()) / "phase26_renders"
SHOTS.mkdir(exist_ok=True)
FAKE_KEY = "p26-not-a-real-key-0123456789abcdef"

sandbox_config = json.loads(real_before["config.json"])
sandbox_config.update({
    "allow_network": False,  # nothing leaves the machine from a test
    "enable_controller": False,  # and the real pad is left alone
    "startup_scan": False,
    "watch_folders": False,  # the watcher is exercised on its own root below
    "steamgriddb_key": FAKE_KEY,  # to prove a key never reaches the log
    **test_sandbox.ALWAYS_WRITTEN,  # Phase 99: the one question as asked, as every copy has it
})
for key in ("library_sort", "window_geometry"):
    sandbox_config.pop(key, None)
(SANDBOX / "config.json").write_text(json.dumps(sandbox_config, indent=2), encoding="utf-8")
for name in ("overrides.json", "catalog.json"):
    if real_before[name] is not None:
        (SANDBOX / name).write_bytes(real_before[name])
real_db_before = test_sandbox.copy_real_db(SANDBOX / test_sandbox.REAL_DB)

from shared import paths

paths.data_dir = lambda: SANDBOX

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

app = QApplication([])

from data_access import catalog_io
from data_access import config_io
from adapters import folder_watch
import launcher
from shared import rules
from logic import storage
from logic import transfer
from presentation import ui_actions
from presentation import ui_rules
from presentation import ui_settings
from presentation import ui_window
from shared import walk
from logic.launch import LaunchResult, Tick
from shared.models import GameEntry

# Everything this run logs goes to the sandbox's log file, so the key check at the end
# covers every window built here. The console handler is dropped to keep the output
# readable; the file is what is under test.
LOG_PATH = SANDBOX / rules.LOG_FILENAME
launcher.configure_logging(False, LOG_PATH)
root_logger = logging.getLogger()
for handler in list(root_logger.handlers):
    if not isinstance(handler, logging.FileHandler):
        root_logger.removeHandler(handler)

passed = failed = 0
windows = []


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"   PASS  {name}")
    else:
        failed += 1
        print(f"   FAIL  {name}   {detail}")


def pump(seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


def wait_for(predicate, timeout):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    app.processEvents()
    return bool(predicate())


def read_config():
    return json.loads((SANDBOX / "config.json").read_text(encoding="utf-8"))


def read_overrides():
    return test_sandbox.records()


def new_window():
    window = ui_window.MainWindow()
    windows.append(window)
    return window


def geometry(window):
    g = window.geometry()
    return g.x(), g.y(), g.width(), g.height()


def fake_entry(name, **extra):
    folder = GAMES / name
    folder.mkdir(parents=True, exist_ok=True)
    exe = folder / "game.exe"
    exe.write_bytes(b"MZ" + b"\0" * 64)
    return GameEntry(
        source="folders", source_id=str(exe), display_name=name, install_dir=str(folder),
        launch_kind="exe", launch_target=str(exe), working_dir=str(folder),
        icon_hint=str(exe), size_on_disk=66, detection="heuristic", extra=dict(extra),
    )


def now_iso(offset_days=0.0):
    moment = datetime.now().astimezone() + timedelta(days=offset_days)
    return moment.isoformat(timespec="seconds")


print(f"\nsandbox data folder: {SANDBOX}")
print(f"sandbox scan root:   {ROOT}")
print(f"renders:             {SHOTS}")

try:
    print("\n=== 0. the sandbox really is a sandbox ===")
    check("config.json resolves inside the sandbox", config_io.CONFIG_PATH.parent == SANDBOX,
          config_io.CONFIG_PATH)
    check("so does overrides.json", catalog_io.OVERRIDES_PATH.parent == SANDBOX,
          catalog_io.OVERRIDES_PATH)
    check("and catalog.json", catalog_io.CATALOG_PATH.parent == SANDBOX, catalog_io.CATALOG_PATH)

    print("\n=== 1. the grid's sort survives a restart ===")
    w = new_window()
    check("with nothing saved, the grid starts on Name", w.library.sort_box.currentText() == "Name")
    before_choice = read_config()
    w.library.sort_box.setCurrentText("Recently added")  # exactly what a click does
    saved = read_config()
    check("choosing a sort writes it to config.json", saved.get("library_sort") == "Recently added")
    check("and nothing else in config.json moved",
          {k: v for k, v in saved.items() if k != "library_sort"} == before_choice)
    w.close()

    written = (SANDBOX / "config.json").read_bytes()
    w = new_window()
    check("a new window opens on the remembered sort",
          w.library.sort_box.currentText() == "Recently added")
    stamps = [w.by_key[key].first_seen for key in w.library.visible_keys]
    stamps = [s for s in stamps if s is not None]
    check("and the grid really is newest first", all(a >= b for a, b in zip(stamps, stamps[1:])))
    check("putting the sort back did not write config.json",
          (SANDBOX / "config.json").read_bytes() == written)
    w.close()

    config = read_config()
    config["library_sort"] = "Alphabetical by vibes"
    (SANDBOX / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    written = (SANDBOX / "config.json").read_bytes()
    w = new_window()
    check("a sort this version does not know falls back to Name",
          w.library.sort_box.currentText() == "Name")
    check("without rewriting the file", (SANDBOX / "config.json").read_bytes() == written)
    w.library.sort_box.setCurrentText("Recently added")
    w.close()

    print("\n=== 2. the storage sort no longer carries TV mode with it ===")
    w = new_window()
    tv_before = read_config().get("tv_mode")
    w.config["tv_mode"] = True  # what starting from the TV shortcut leaves in memory
    other = next(mode for mode in storage.SORT_MODES if mode != w.storage_sort)
    w.set_storage_sort(other)
    after = read_config()
    check("the storage sort is saved", after.get("storage_sort") == other)
    check("and config.json's TV mode is untouched", after.get("tv_mode") == tv_before,
          (tv_before, after.get("tv_mode")))
    w.config["tv_mode"] = tv_before
    w.close()

    print("\n=== 3. the window opens where it was left ===")
    w = new_window()
    w.setGeometry(140, 160, 1111, 777)
    w._shown = True  # as if it had been on screen, without flashing one at you
    w.close()
    check("closing remembers the window", bool(read_config().get("window_geometry")))
    w = new_window()
    check("a new window opens at the same place and size",
          geometry(w) == (140, 160, 1111, 777), geometry(w))
    w.close()  # never shown: must not overwrite what the last one saved

    kept = read_config().get("window_geometry")
    w = new_window()
    w.setGeometry(10, 10, 500, 400)
    w.close()
    check("a window that was never on screen saves nothing",
          read_config().get("window_geometry") == kept)

    w = new_window()
    w.setGeometry(150, 150, 1000, 700)
    w.setWindowState(Qt.WindowState.WindowMaximized)
    w._shown = True
    w.close()
    w = new_window()
    check("a maximised window comes back maximised",
          bool(w.windowState() & Qt.WindowState.WindowMaximized), w.windowState())
    w.close()

    w = new_window()
    w.setWindowState(Qt.WindowState.WindowNoState)
    w.showFullScreen = lambda: None  # nothing appears on your screen during a test
    w.showNormal = lambda: None
    w.setGeometry(200, 210, 1000, 700)
    w._shown = True
    w.set_tv_mode(True)
    w.setGeometry(0, 0, 3000, 1800)  # what fullscreen would have done
    w.close()
    w = new_window()
    check("closing from TV mode remembers the ordinary window, not the TV",
          geometry(w) == (200, 210, 1000, 700), geometry(w))
    check("and does not come back fullscreen",
          not (w.windowState() & Qt.WindowState.WindowFullScreen))
    w.close()

    w = new_window()
    w.setGeometry(-7000, -7000, 900, 600)
    w._shown = True
    w.close()
    w = new_window()
    on_screen = any(screen.availableGeometry().intersects(w.geometry()) for screen in app.screens())
    check("a window left on a screen that is gone comes back onto one that is",
          on_screen, geometry(w))
    w.close()

    print("\n=== 4. the NEW tag: when it is given, and when it lapses ===")
    store = test_sandbox.separate_store("tag_test_overrides")
    first = [fake_entry("Alpha"), fake_entry("Beta"), fake_entry("Gamma")]
    views = catalog_io.merge(first, store)
    check("a first look at a library stamps first_seen on everything",
          all(view.first_seen is not None for view in views))
    check("but tags nothing NEW -- a wall of tags would say nothing",
          not any(view.is_new for view in views)
          and not any(record.get(rules.NEW_KEY) for record in test_sandbox.records(store).values()))

    delta = fake_entry("Delta")
    views = {view.display_name: view for view in catalog_io.merge(first + [delta], store)}
    check("a game found afterwards is tagged NEW", views["Delta"].is_new)
    check("and the games already known are not",
          not any(views[name].is_new for name in ("Alpha", "Beta", "Gamma")))
    stored = test_sandbox.records(store)
    check("the tag is kept in overrides.json",
          stored[delta.identity_key].get(rules.NEW_KEY) is True)

    store.update(delta.identity_key, first_seen=now_iso(-(rules.NEW_BADGE_DAYS + 1)))
    check(f"after {rules.NEW_BADGE_DAYS} days the tag lapses",
          not catalog_io.GameView(delta, store.get(delta.identity_key)).is_new)
    catalog_io.merge(first + [delta], store)
    stored = test_sandbox.records(store)
    check("and the next merge takes it out of overrides.json",
          rules.NEW_KEY not in stored[delta.identity_key])

    echo = fake_entry("Echo", last_played_unix=int(time.time()) + 5)
    views = {view.display_name: view for view in catalog_io.merge(first + [delta, echo], store)}
    check("a game already played elsewhere since it arrived is not NEW (Steam's LastPlayed)",
          not views["Echo"].is_new)

    w = new_window()
    subjects = [v for v in w.views if not v.hidden and not v.is_non_game
                and v.entry.launch_kind == "exe"][:3]
    for view in subjects:
        w.overrides.update(view.key, **{rules.NEW_KEY: True, "first_seen": now_iso()})
    w.reload_views()
    check("tagging a real game in the sandbox makes it NEW", w.by_key[subjects[0].key].is_new)
    w.show_detail(subjects[0].key)
    check("opening its page takes the tag off",
          not w.by_key[subjects[0].key].is_new
          and rules.NEW_KEY not in read_overrides()[subjects[0].key])

    original_launch = ui_actions.launch.launch_game
    original_critical = ui_actions.QMessageBox.critical
    ui_actions.QMessageBox.critical = lambda *args, **kwargs: None
    try:
        ui_actions.launch.launch_game = lambda view: LaunchResult(False, error="refused in a test")
        ui_actions.play(w, w.by_key[subjects[1].key])
        check("a start that fails leaves the tag on",
              read_overrides()[subjects[1].key].get(rules.NEW_KEY) is True)
        ui_actions.launch.launch_game = lambda view: LaunchResult(True)
        ui_actions.play(w, w.by_key[subjects[1].key])
        check("starting it from the menu takes the tag off",
              rules.NEW_KEY not in read_overrides()[subjects[1].key])
    finally:
        ui_actions.launch.launch_game = original_launch
        ui_actions.QMessageBox.critical = original_critical
    w.close()

    print("\n=== 5. what the tag looks like ===")
    w = new_window()
    w.resize(1280, 820)
    w.library.set_sort("Recently added")
    picks = [v for v in w.views if not v.hidden and not v.is_non_game][:4]
    for view in picks[:3]:
        w.overrides.update(view.key, **{rules.NEW_KEY: True, "first_seen": now_iso()})
    w.overrides.update(picks[0].key, favorite=True)  # the star and the tag on one tile
    w.reload_views()
    w.library.set_sort("Name")
    w.library.set_sort("Recently added")
    pump(0.3)
    w.grab().save(str(SHOTS / "grid_normal.png"))

    grid = w.library.list
    first_item = grid.item(0)
    tagged_key = w.library.visible_keys[0]
    rect = grid.visualItemRect(first_item)
    with_tag = grid.viewport().grab(rect).toImage()
    w.overrides.update(tagged_key, **{rules.NEW_KEY: None})
    w.library.repaint_tiles()
    pump(0.1)
    without_tag = grid.viewport().grab(rect).toImage()
    w.overrides.update(tagged_key, **{rules.NEW_KEY: True})
    w.library.repaint_tiles()
    accent = QColor(ui_rules.NEW_BADGE_COLOR)

    def badge_pixels(image):
        count = 0
        for y in range(image.height() // 4):
            for x in range(image.width() // 2):
                colour = image.pixelColor(x, y)
                if (abs(colour.red() - accent.red()) < 12 and abs(colour.green() - accent.green()) < 12
                        and abs(colour.blue() - accent.blue()) < 12):
                    count += 1
        return count

    tagged_px, untagged_px = badge_pixels(with_tag), badge_pixels(without_tag)
    print(f"   badge-coloured pixels in the tile's top-left: {tagged_px} tagged, {untagged_px} not")
    check("the tag is drawn in the tile's top-left corner", tagged_px > 200 and untagged_px < tagged_px / 5)

    w.showFullScreen = lambda: None
    w.showNormal = lambda: None
    for scale in (ui_rules.TV_SCALE_DEFAULT, max(ui_rules.TV_SCALE_CHOICES)):
        w.config["tv_scale"] = scale
        w.set_tv_mode(True)
        w.resize(1920, 1080)
        pump(0.3)
        w.grab().save(str(SHOTS / f"grid_tv_{round(scale * 100)}.png"))
    w.set_tv_mode(False)
    w.close()

    print("\n=== 6. what a scan says, and when it rebuilds nothing ===")
    w = new_window()
    rebuilds = []
    real_reload = w.reload_views
    w.reload_views = lambda: (rebuilds.append(1), real_reload())
    posted = []
    w.queue_status = lambda text, ms: posted.append(text)
    shown = []
    w.statusBar().messageChanged.connect(lambda text: shown.append(text))

    w.scan_was_quiet, w.scan_was_background = True, True
    w._on_scanned(list(w.entries))
    check("a background scan that found nothing new rebuilds nothing", not rebuilds)
    check("and says nothing", not posted, posted)

    w.scan_was_quiet, w.scan_was_background = True, False
    w._on_scanned(list(w.entries))
    check("the startup scan still says the library is up to date",
          any(text.startswith("Library up to date") for text in posted), posted)

    arrival = fake_entry("Phase Twenty Six Arrival")
    posted.clear()
    w.scan_was_quiet, w.scan_was_background = True, True
    w._on_scanned(list(w.entries) + [arrival])
    check("a new game rebuilds the grid", rebuilds)
    check("it arrives tagged NEW", w.by_key[arrival.identity_key].is_new)
    check("and the message names it", posted == ["New game: Phase Twenty Six Arrival"], posted)

    demo = fake_entry("Phase Twenty Six Demo", app_type="demo")
    posted.clear()
    w._on_scanned(list(w.entries) + [demo])
    check("a demo arriving is not announced as a new game",
          posted and not any("Demo" in text for text in posted), posted)

    second = fake_entry("Second Arrival")
    shown.clear()
    w.scan_was_quiet, w.scan_was_background = False, False
    w._on_scanned(list(w.entries) + [second])
    check("a Rescan you pressed names it too",
          any(text.endswith("New game: Second Arrival") and text.startswith("Found") for text in shown),
          shown)

    class Named:
        def __init__(self, name):
            self.display_name = name

    check("several arrivals are counted and the rest summarised",
          ui_window._arrivals_text([Named(n) for n in "ABCDE"]) == "5 new games: A, B, C and 2 more",
          ui_window._arrivals_text([Named(n) for n in "ABCDE"]))
    w.close()

    print("\n=== 7. a scan the watch asks for waits for your game, and for other scans ===")
    w = new_window()
    started = []
    w.start_scan = lambda quiet=False, background=False: started.append(background) or True
    w.tracker.running.append(object())
    w._watch_wants_scan("test")
    check("while a game started from here is running, the scan waits", not started and w._scan_wanted)
    w.tracker.running.clear()
    w.tracker.poll = lambda: [Tick("p26:finished", "A Finished Game", 3, finished=True,
                                   started_at=None, total_seconds=3)]
    w._poll_playtime()
    check("and runs the moment the game closes", started == [True], started)

    class FakeWorker:
        def __init__(self):
            self.running = True

        def isRunning(self):
            return self.running

        def wait(self, *args):
            return True

    w.worker = FakeWorker()
    w._watch_wants_scan("test while scanning")
    check("while another scan is running, it waits for that too", started == [True], started)
    w.worker.running = False
    w._scan_thread_done()
    check("and follows it straight away", started == [True, True], started)
    w.worker = None
    w.close()

    print("\n=== 8. the folder watch, on a root made for this test ===")
    rules.WATCH_DEBOUNCE_MS = 100
    rules.WATCH_SETTLE_POLL_MS = 300
    rules.WATCH_SETTLE_CHECKS = 2
    rules.WATCH_FOLLOW_UP_S = 8
    watcher = folder_watch.FolderWatcher()
    asked = []
    watcher.scanWanted.connect(lambda reason: asked.append((time.monotonic(), reason)))
    watcher.watch([str(ROOT), str(ROOT / "does not exist")])
    check("the root is watched, and a missing one is skipped without fuss",
          watcher.roots == [os.path.normpath(str(ROOT))], watcher.roots)

    slow = ROOT / "Slow Install"
    slow.mkdir()
    last_write = 0.0
    for index in range(10):  # two seconds of an installer writing
        (slow / f"part{index}.bin").write_bytes(os.urandom(200_000))
        last_write = time.monotonic()
        pump(0.2)
    check("nothing is asked for while files are still arriving", not asked, asked)
    check("the scan is asked for once the folder has gone quiet", wait_for(lambda: asked, 6))
    if asked:
        gap = asked[0][0] - last_write
        print(f"   asked {gap:.2f}s after the last write: {asked[0][1]}")
        check("and not before it had been quiet for a full measurement round",
              gap >= rules.WATCH_SETTLE_POLL_MS / 1000, gap)

    held = ROOT / "held.bin"
    with open(held, "wb") as handle:
        handle.write(os.urandom(4_000_000))
        handle.flush()
        listed = next(e for e in os.scandir(ROOT) if e.name == "held.bin").stat().st_size
        direct = os.stat(held).st_size
        print(f"   a file still open for writing: the listing says {listed:,} bytes, "
              f"the file itself {direct:,}")
        check("the measurement sees the bytes of a file still being written",
              walk.fingerprint(str(ROOT))[1] >= 4_000_000)

    asked.clear()
    (ROOT / "Some Game.rar").write_bytes(os.urandom(100_000))
    pump(1.2)
    check("an archive landing beside the games is not waited on",
          not asked and not any(p.endswith(".rar") for p in watcher.arrivals), (asked, watcher.arrivals))

    asked.clear()
    (ROOT / "Tiny Game.exe").write_bytes(b"MZ" + os.urandom(50_000))
    check("a loose exe is reported once it has settled",
          wait_for(lambda: any("Tiny Game.exe" in reason for _t, reason in asked), 6), asked)

    asked.clear()
    paused = ROOT / "Paused Install"
    paused.mkdir()
    (paused / "first.bin").write_bytes(os.urandom(1000))
    wait_for(lambda: asked, 6)
    asked.clear()
    (paused / "second.bin").write_bytes(os.urandom(500_000))  # the installer wakes up again
    check("a folder that changes again after settling is reported again",
          wait_for(lambda: any("Paused Install" in reason for _t, reason in asked), 6), asked)

    asked.clear()
    shutil.rmtree(slow)
    check("a removed folder is reported straight away",
          wait_for(lambda: any(reason.startswith("removed") for _t, reason in asked), 3), asked)

    (ROOT / "Still Arriving").mkdir()
    wait_for(lambda: any("Still Arriving" in p for p in watcher.arrivals), 3)
    before_rewatch = sorted(watcher.arrivals)
    watcher.watch([str(ROOT)])
    check("watching the same folders again forgets nothing half-installed",
          sorted(watcher.arrivals) == before_rewatch)

    watcher.watch([])
    asked.clear()
    (ROOT / "After Switching Off").mkdir()
    pump(1.2)
    check("switched off, nothing is noticed", not asked and not watcher.roots, asked)
    watcher.stop()

    w = new_window()
    check("switched off in config.json, the window watches nothing", not w.watcher.roots)
    w.config["watch_folders"] = True
    w.config["roots"] = [str(ROOT)]
    w._arm_watcher()
    check("switched on, it watches the scan folders",
          w.watcher.roots == [os.path.normpath(str(ROOT))], w.watcher.roots)
    w.close()

    dialog = ui_settings.SettingsDialog({"watch_folders": False})
    check("Settings shows the switch as saved", not dialog.watch_box.isChecked())
    dialog.watch_box.setChecked(True)
    check("and hands it back", dialog.values()["watch_folders"] is True)
    check("it is on unless someone turned it off", ui_settings.SettingsDialog({}).watch_box.isChecked())
    dialog.deleteLater()

    print("\n=== 9. moving to another PC leaves the window behind ===")
    config = read_config()
    config.update({"window_geometry": "THIS-PC", "library_sort": "Last played"})
    (SANDBOX / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    bundle = SANDBOX / f"export{rules.TRANSFER_SUFFIX}"
    report = transfer.export_bundle(bundle, include_key=False)
    check("the export was written", report.ok, report.message)
    with zipfile.ZipFile(bundle) as archive:
        bundled = json.loads(archive.read(rules.TRANSFER_CONFIG_MEMBER))
    check("it leaves this PC's window size and place behind", "window_geometry" not in bundled)
    check("but carries the sort, which is a preference", bundled.get("library_sort") == "Last played")
    transfer._merge_config({"window_geometry": "OTHER-PC", "library_sort": "Name"})
    config = read_config()
    check("an import never takes another PC's window", config.get("window_geometry") == "THIS-PC")
    check("but does take its preferences", config.get("library_sort") == "Name")

    print("\n=== 10. the log file ===")
    logging.getLogger("p26").info("hello from the phase 26 test")
    launcher.install_crash_logging()
    try:
        raise ValueError("boom in the test")
    except ValueError:
        sys.excepthook(*sys.exc_info())

    def bad_slot():
        raise RuntimeError("boom inside a Qt slot")

    # Under a real event loop, app.exec(), exactly as launcher.main runs it. There the
    # slot's error goes to sys.excepthook and the loop carries on -- checked separately.
    # processEvents() called from Python behaves differently: it hands the error straight
    # back to its caller, which is a property of this harness, not of the launcher.
    QTimer.singleShot(0, bad_slot)
    QTimer.singleShot(300, app.quit)
    app.exec()

    def bad_thread():
        raise KeyError("boom in a thread")

    thread = threading.Thread(target=bad_thread, name="p26-thread")
    thread.start()
    thread.join()

    for handler in root_logger.handlers:
        handler.flush()
    text = LOG_PATH.read_text(encoding="utf-8")
    check("the log file exists, with a time on every line",
          re.search(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d{3} INFO ", text, re.M) is not None)
    check("an uncaught error is written, traceback and all",
          "uncaught exception" in text and "ValueError: boom in the test" in text)
    check("so is one raised inside a Qt slot, which used to vanish under pythonw",
          "RuntimeError: boom inside a Qt slot" in text)
    check("and one raised in a thread", "boom in a thread" in text and "p26-thread" in text)
    expected_lines = (
        "watching for new games in",  # the watch switching on
        "waiting for it to finish arriving",  # a new folder being noticed
        "the folder watch asked for a scan",  # the window hearing about it
        "holding the folder watch's scan until the game closes",
    )
    missing = [line for line in expected_lines if line not in text]
    check("the folder watch and the windows above were logged too", not missing, missing)
    logged = "".join(p.read_text(encoding="utf-8") for p in SANDBOX.glob(rules.LOG_FILENAME + "*"))
    check("the SteamGridDB key never appears in it", FAKE_KEY not in logged)

    file_handler = next(h for h in root_logger.handlers
                        if isinstance(h, logging.handlers.RotatingFileHandler))
    file_handler.maxBytes = 20_000
    for index in range(800):
        logging.getLogger("p26").info("filler line %04d %s", index, "x" * 60)
    file_handler.flush()
    rotated = sorted(p.name for p in SANDBOX.glob(rules.LOG_FILENAME + "*"))
    check("it rotates, keeping exactly two old copies",
          rotated == ["launcher.log", "launcher.log.1", "launcher.log.2"], rotated)

    launcher.configure_logging(False, SANDBOX)  # a folder: cannot be opened as a file
    check("a log file that cannot be opened does not stop the launcher", True)

finally:
    for window in windows:
        try:
            window.close()
        except RuntimeError:
            pass  # already deleted
    logging.shutdown()
    for handler in list(logging.getLogger().handlers):
        handler.close()
        logging.getLogger().removeHandler(handler)

    print("\n=== 11. the real library is exactly as it was found ===")
    for name in REAL_FILES:
        same = test_sandbox.read_real(name) == real_before[name]
        check(f"{name} is byte for byte unchanged", same)
    check("and the library database holds what it held",
          test_sandbox.db_fingerprint(REAL / test_sandbox.REAL_DB) == real_db_before)
    test_sandbox._let_go(SANDBOX)
    shutil.rmtree(SANDBOX, ignore_errors=True)
    shutil.rmtree(ROOT, ignore_errors=True)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
