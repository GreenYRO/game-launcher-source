"""Phase 29: finding where games save, and keeping copies of the saves.

Runs against a throwaway copy of the data (test_sandbox): every backup this writes lands in
the copy's own save_backups folder. The real save folders are only ever *read* -- the
save search walks them, and the first-look backups copy from them -- and nothing is
uninstalled: the uninstall checks stop at the confirmation, or before it.
"""
import json
import os
import shutil
import sys
import tempfile
import time
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # the project folder, one up from tests/
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import test_sandbox

box = test_sandbox.start()

import logging

logging.basicConfig(level=logging.ERROR)

from PySide6.QtWidgets import QApplication, QMessageBox

app = QApplication([])

from data_access import catalog_io
from shared import rules
from logic import save_backup
from adapters import save_worker
from logic import saves
from presentation import ui_actions
from presentation import ui_removal
from presentation import ui_window
from shared.models import GameEntry

passed = failed = 0
windows = []
TMP = Path(tempfile.mkdtemp(prefix="p29_"))


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"   PASS  {name}")
    else:
        failed += 1
        print(f"   FAIL  {name}   {detail}")


def wait_for(predicate, timeout):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    return bool(predicate())


def plant(path: Path, size=1000, when=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(os.urandom(size))
    if when is not None:
        os.utime(path, (when, when))
    return path


print(f"\nsandbox data folder: {box.folder}")

try:
    print("\n=== 1. what a save looks like ===")
    root = saves.save_root
    check("Unreal: <project>\\Saved\\SaveGames",
          root(["Rehaunted", "Saved", "SaveGames"], "slot.sav", "FOLDERID_LocalAppData")
          == ["Rehaunted", "Saved", "SaveGames"])
    check("but not Unreal's Saved\\Config", root(["Rehaunted", "Saved", "Config", "Windows"], "Game.ini",
                                                "FOLDERID_LocalAppData") is None)
    check("an emulator's save goes to its game's numbered folder, not the emulator's",
          root(["GSE Saves", "3357650", "remote", "win64_save"], "data", "FOLDERID_RoamingAppData")
          == ["GSE Saves", "3357650"])
    check("the RUNE layout in Public Documents too",
          root(["Steam", "RUNE", "1465360", "remote"], "x", "FOLDERID_PublicDocuments")
          == ["Steam", "RUNE", "1465360"])
    check("Saved Games: publisher and game",
          root(["CD Projekt Red", "Cyberpunk 2077", "AutoSave-12"], "sav.dat", "FOLDERID_SavedGames")
          == ["CD Projekt Red", "Cyberpunk 2077"])
    check("never a whole known folder, for a file sitting loose in it",
          root([], "save.dat", "FOLDERID_LocalAppData") is None
          and root([], "x", "FOLDERID_SavedGames") is None)
    check("a file named like a save counts, one merely containing the word does not",
          root(["Unity", "Game"], "save0.dat", "FOLDERID_LocalAppDataLow") == ["Unity", "Game"]
          and root(["ChainedTogether", "HID"], "GameSaveConfig.json", "FOLDERID_LocalAppData") is None)

    print("\n=== 2. which save-shaped folders belong to which game ===")
    now = time.time()
    session = (now - 3600, now - 1800)  # half an hour, an hour ago
    during, outside = now - 2400, now - 600
    local, roaming, docs = TMP / "Local", TMP / "Roaming", TMP / "Documents"
    bases = [("FOLDERID_LocalAppData", str(local)), ("FOLDERID_RoamingAppData", str(roaming)),
             ("FOLDERID_Documents", str(docs))]
    plant(local / "Tiny Knight" / "Saved" / "SaveGames" / "slot1.sav", when=during)
    plant(local / "Ride" / "Saved" / "SaveGames" / "a.sav", when=during)
    plant(local / "Ride" / "Saved" / "SaveGames" / "b.sav", when=during)
    for n in range(6):  # a background program's saves, written all the time
        plant(local / "Busy Thing" / "saves" / f"w{n}.dat", when=outside - n * 60)
    plant(local / "Busy Thing" / "saves" / "during.dat", when=during)
    plant(local / "Lone" / "Saves" / "one.dat", when=during)  # one write is not evidence
    plant(roaming / "GSE Saves" / "4242" / "remote" / "s.dat", when=during)
    plant(roaming / "GSE Saves" / "settings" / "account_name.txt", when=during)
    plant(docs / "Another Game" / "Saves" / "x.sav", when=during)
    plant(docs / "Another Game" / "Saves" / "y.sav", when=during)
    plant(local / "NVIDIA" / "DXCache" / "cache.bin", when=during)
    for stamp in ("2026.09.01", "2026.09.02"):
        plant(local / "Tiny Knight" / "Saved" / "Backups" / stamp / "save.sav", when=during)

    index = saves.build_index(bases)
    found = saves.find(index, bases, name="Tiny Knight", appid="4242", install_dir="",
                       windows=[session], other_names=("Another Game",))
    got = {os.path.relpath(f.path, TMP) for f in found}
    print("   found:", sorted(got))
    check("its own named folder", os.path.join("Local", "Tiny Knight", "Saved", "SaveGames") in got)
    check("an internal project name, taken because only this game wrote it",
          os.path.join("Local", "Ride", "Saved", "SaveGames") in got)
    check("its emulator folder, by its Steam number", os.path.join("Roaming", "GSE Saves", "4242") in got)
    check("dated backup siblings folded into their parent",
          os.path.join("Local", "Tiny Knight", "Saved", "Backups") in got)
    check("not a background program's saves, written mostly while it was not running",
          not any("Busy Thing" in g for g in got))
    check("not a folder on one stray write", not any("Lone" in g for g in got))
    check("not the emulator's whole folder", os.path.join("Roaming", "GSE Saves") not in got)
    check("not a folder named after a different game", not any("Another Game" in g for g in got))
    check("not a driver cache", not any("NVIDIA" in g for g in got))
    ignored = saves.find(index, bases, name="Tiny Knight", appid="4242", install_dir="",
                         windows=[session], other_names=("Another Game",),
                         ignored=(str(local / "Ride" / "Saved" / "SaveGames"),))
    check("a folder the user ruled out stays out", not any("Ride" in f.path for f in ignored))

    print("\n=== 3. copies of the saves ===")
    source = TMP / "MySaves"
    plant(source / "slot1.sav", 5000)
    plant(source / "profiles" / "p.dat", 300)
    key, name = str(TMP / "games" / "My Game"), "My Game"
    first = save_backup.back_up(key, name, [str(source)], "test")
    check("a first backup is written", first.made is not None and first.made.exists())
    with zipfile.ZipFile(first.made) as archive:
        listed = sorted(archive.namelist())
        manifest = json.loads(archive.read(save_backup.MANIFEST))
    check("it holds every file, numbered by folder, plus a manifest",
          listed == sorted(["manifest.json", "0/slot1.sav", "0/profiles/p.dat"]), listed)
    check("the manifest says where each folder came from",
          manifest["folders"] == [str(source)] and manifest["game"] == name and manifest["reason"] == "test")
    check("no half-written file is left behind", not list(first.made.parent.glob("*.tmp")))
    again = save_backup.back_up(key, name, [str(source)], "test")
    check("unchanged saves are not copied again", again.skipped_unchanged and again.made is None)
    time.sleep(1.1)
    plant(source / "slot2.sav", 700)
    changed = save_backup.back_up(key, name, [str(source)], "test")
    check("a new save is copied", changed.made is not None and changed.made != first.made)
    backups = save_backup.list_backups(key, name)
    check("backups are listed newest first", [b.path for b in backups[:2]] == [changed.made, first.made])
    check("a renamed game still finds its backups",
          save_backup.game_folder(key, "My Renamed Game") == first.made.parent)

    keep = rules.SAVES_BACKUP_KEEP
    rules.SAVES_BACKUP_KEEP = 3
    for n in range(4):
        time.sleep(1.1)
        plant(source / f"more{n}.sav", 100)
        save_backup.back_up(key, name, [str(source)], "test")
    check("only the newest few are kept", len(save_backup.list_backups(key, name)) == 3)
    rules.SAVES_BACKUP_KEEP = keep

    biggest = rules.SAVES_BACKUP_MAX_BYTES
    rules.SAVES_BACKUP_MAX_BYTES = 1000
    big = save_backup.back_up(str(TMP / "games" / "Big"), "Big", [str(source)], "test")
    rules.SAVES_BACKUP_MAX_BYTES = biggest
    check("a folder too big to be a save is left out, and said so",
          big.made is None and big.too_big == (str(source),))
    gone = save_backup.back_up(str(TMP / "games" / "Gone"), "Gone", [str(TMP / "nope")], "test")
    check("a folder that is gone is reported, not an error", gone.missing and not gone.error)

    print("\n=== 4. this machine, read only: nothing wrong is ever claimed ===")
    w = ui_window.MainWindow()
    windows.append(w)
    jobs = [job for view in w.views
            for job in [w.save_job(view, reason="test", back_up=False)] if job is not None]
    started = time.monotonic()
    outcomes = save_worker.run_jobs(jobs, w.other_game_names())
    print(f"   {len(jobs)} played games searched in {time.monotonic() - started:.1f}s")
    claims = {o.key: o.folders for o in outcomes}
    everything = [f for folders in claims.values() for f in folders]
    for view in w.views:
        if claims.get(view.key):
            print(f"   {view.display_name}: {claims[view.key]}")
    noise = ("NVIDIA", "D3DSCache", "Claude", "Google", "Microsoft", "Packages", "WeMod", "imput")
    check("no save folder is a cache, a browser or another app",
          not any(any(f"\\{n}\\" in f for n in noise) for f in everything))
    check("every one has a save's shape",
          all(any(saves._is_save_word(p) or p.isdigit() for p in f.split(os.sep))
              or "Saved Games" in f for f in everything), everything)
    check("no folder is claimed by two installed games", len(everything) == len(set(everything)))
    views_by_name = {v.display_name: v for v in w.views}
    cultic = views_by_name.get("CULTIC")
    if cultic is not None and claims.get(cultic.key):
        check("CULTIC's saves are found inside its own game folder",
              any(f.lower().startswith(cultic.entry.install_dir.lower()) for f in claims[cultic.key]))
    spider = views_by_name.get("Marvel's Spider-Man 2")
    if spider is not None:
        check("Spider-Man 2 does not claim another game's Saved Games folder",
              not any("Last of Us" in f for f in claims.get(spider.key, [])))

    print("\n=== 5. the window: a first look, after a session, and never during one ===")
    w.config["backup_saves"] = True
    # The real launcher has run its own first look since this was written, so the copied
    # records already say "looked at". Clear that here, in the sandbox only, or there is
    # nothing left for the first look to do -- the test must not depend on history.
    w.overrides.update_many({key: {rules.SAVE_DIRS_CHECKED_KEY: None, rules.SAVE_DIRS_KEY: None}
                             for key in w.overrides.export_records()})
    started_jobs = []
    real_start = save_worker.SaveWorker.start
    w._startup_saves()
    check("the first look starts in the background", w.save_worker is not None)
    wait_for(lambda: w.save_worker is not None and not w.save_worker.isRunning() and not w._save_jobs, 120)
    wait_for(lambda: all(w.overrides.get(j.key).get(rules.SAVE_DIRS_CHECKED_KEY) for j in jobs), 10)
    check("every played game is marked as looked at",
          all(w.overrides.get(j.key).get(rules.SAVE_DIRS_CHECKED_KEY) for j in jobs))
    with_saves = [k for k, folders in claims.items() if folders]
    copied = [k for k in with_saves if save_backup.latest(k, w.by_key[k].display_name) is not None]
    check(f"and a copy exists for every game with saves found ({len(copied)} of {len(with_saves)})",
          len(copied) == len(with_saves))
    check("all of it inside the sandbox", str(save_backup.backups_root()).startswith(str(box.folder)))
    jobs_before = len(w._save_jobs)
    w._startup_saves()
    check("the first look never runs twice", len(w._save_jobs) == jobs_before and
          (w.save_worker is None or not w.save_worker.isRunning()))

    if with_saves:
        subject = w.by_key[with_saves[0]]
        w.tracker.running.append(object())
        w._save_jobs.append(w.save_job(subject, reason="after playing"))
        previous_worker = w.save_worker
        w._run_saves()
        check("while a game started from here runs, the save work waits",
              w.save_worker is previous_worker and w._save_jobs)
        w.tracker.running.clear()
        w._run_saves()
        wait_for(lambda: not w._save_jobs and not w.save_worker.isRunning(), 60)
        check("and runs once it has closed", not w._save_jobs)

        w.show_detail(subject.key)
        # Every fact the page shows, by label, wherever Phase 33 put it -- a pill under the
        # title, the Details card or the Files card.
        facts = w.detail.facts()
        check("the game's page says where its saves are", claims[subject.key][0] in facts.get("Saves", ""),
              facts.get("Saves"))
        check("and when they were last copied", "ago" in facts.get("Saves copied", "") or
              "now" in facts.get("Saves copied", ""), facts.get("Saves copied"))
        menu = ui_actions.build_menu(w, subject)
        texts = {a.text(): a.isEnabled() for a in menu.actions()}
        check("the menu offers to open the saves folder, and to copy them now",
              texts.get("Open saves folder") is True and "Back up saves now" in texts, texts)
        menu.deleteLater()
        w.back_up_now(subject)
        check("backing up by hand answers, even when nothing changed",
              "not changed" in w.statusBar().currentMessage() or "copied" in w.statusBar().currentMessage(),
              w.statusBar().currentMessage())

    print("\n=== 6. uninstalling copies the saves first -- and stops if it cannot ===")
    games_root = TMP / "scan root"
    game_dir = games_root / "Pocket Quest"
    plant(game_dir / "PocketQuest.exe", 30_000)
    started_at = datetime.now().astimezone() - timedelta(minutes=20)
    plant(game_dir / "PocketQuest_Data" / "Saves" / "slot.sav", 2000,
          when=(started_at + timedelta(minutes=5)).timestamp())
    entry = GameEntry(
        source="folders", source_id=str(game_dir / "PocketQuest.exe"), display_name="Pocket Quest",
        install_dir=str(game_dir), launch_kind="exe", launch_target=str(game_dir / "PocketQuest.exe"),
        working_dir=str(game_dir), icon_hint="", size_on_disk=32_000, detection="heuristic",
    )
    w.overrides.update(entry.identity_key, sessions=[
        {"start": started_at.isoformat(timespec="seconds"), "minutes": 10}])
    w.entries = list(w.entries) + [entry]
    w.config["roots"] = [str(games_root)]
    w.reload_views()
    quest = w.by_key[entry.identity_key]

    asked, removed, warned = [], [], []
    real_confirm, real_perform, real_warning = ui_removal.confirm, ui_removal.removal.perform, QMessageBox.warning
    ui_removal.confirm = lambda window, view, plan, line="": asked.append(line) or False
    ui_removal.removal.perform = lambda plan, hwnd=0: removed.append(plan) or (True, "")
    ui_removal.QMessageBox.warning = lambda *a, **k: warned.append(a)
    try:
        ui_removal.uninstall(w, quest)
        check("the saves were found and copied before the question was asked",
              save_backup.latest(quest.key, quest.display_name) is not None)
        check("the question says they live inside the folder, and that a copy exists",
              asked and "inside this folder" in asked[0] and "copy" in asked[0], asked)
        check("and answering Cancel removes nothing", not removed)

        real_back_up = save_backup.back_up
        save_backup.back_up = lambda *a, **k: save_backup.Result(error="disk full, in a test")
        asked.clear()
        ui_removal.uninstall(w, quest)
        save_backup.back_up = real_back_up
        check("when the copy fails, nothing is removed and the question is never asked",
              not removed and not asked and warned, (removed, asked, len(warned)))
        check("and the folder is still there", game_dir.is_dir())
    finally:
        ui_removal.confirm, ui_removal.removal.perform = real_confirm, real_perform
        ui_removal.QMessageBox.warning = real_warning

finally:
    for window in windows:
        try:
            window.close()
        except RuntimeError:
            pass
    shutil.rmtree(TMP, ignore_errors=True)
    print("\n=== 7. the real library is exactly as it was found ===")
    changed = box.finish()
    check("overrides.json, config.json and catalog.json are byte for byte unchanged", not changed,
          changed)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
