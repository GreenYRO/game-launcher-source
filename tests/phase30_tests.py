"""Phase 30: putting a copy of a game's saves back.

Runs against a throwaway copy of the data (test_sandbox), on save folders this file makes
itself. Restoring sends the folder it replaces to the Recycle Bin; here that step is
redirected into a folder of the test's own, so your real Recycle Bin gains nothing. The
flags the real shell call would receive are checked separately, without deleting anything.
"""
import json
import os
import shutil
import sys
import tempfile
import time
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # the project folder, one up from tests/
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import test_sandbox

box = test_sandbox.start()

import logging

logging.basicConfig(level=logging.ERROR)

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

app = QApplication([])

from adapters import controller
from logic import removal
from logic import save_backup
from presentation import ui_actions
from presentation import ui_save_restore
from presentation import ui_window
from shared.models import GameEntry

passed = failed = 0
windows = []
TMP = Path(tempfile.mkdtemp(prefix="p30_"))
BIN = TMP / "the test's own recycle bin"
BIN.mkdir()
binned = []


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"   PASS  {name}")
    else:
        failed += 1
        print(f"   FAIL  {name}   {detail}")


def plant(path: Path, text: str, when=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if when is not None:
        os.utime(path, (when, when))
    return path


def fake_bin(path, hwnd=0, interactive=True, already_asked=False):
    binned.append((path, already_asked))
    shutil.move(path, BIN / f"{len(binned)}-{Path(path).name}")
    return True, "Moved to the Recycle Bin."


def tree(folder: Path) -> dict:
    return {str(p.relative_to(folder)): p.read_text(encoding="utf-8")
            for p in sorted(folder.rglob("*")) if p.is_file()}


real_bin = removal.send_to_recycle_bin
removal.send_to_recycle_bin = fake_bin

try:
    print("\n=== 1. the Recycle Bin call restoring makes (checked, not performed) ===")
    from win32com.shell import shell, shellcon

    seen_flags = []
    real_op = shell.SHFileOperation
    shell.SHFileOperation = lambda args: seen_flags.append(args[4]) or (0, False)
    try:
        victim = TMP / "flag probe"
        victim.mkdir()
        real_bin(str(victim), 0, interactive=True, already_asked=True)
        real_bin(str(victim), 0, interactive=True)
    finally:
        shell.SHFileOperation = real_op
    check("restoring asks the shell for undo-able deletion without a second question",
          seen_flags[:1] == [shellcon.FOF_ALLOWUNDO | shellcon.FOF_NOCONFIRMATION], seen_flags)
    check("and the uninstall path is exactly what Phase 25 made it: undo, nothing else",
          seen_flags[1:2] == [shellcon.FOF_ALLOWUNDO], seen_flags)

    print("\n=== 2. a copy goes back exactly as it was ===")
    saves_dir = TMP / "AppData" / "Pocket Quest" / "Saved" / "SaveGames"
    old = time.time() - 86400 * 3
    plant(saves_dir / "slot1.sav", "chapter one", when=old)
    plant(saves_dir / "profile" / "settings.cfg", "fov=90", when=old)
    key, name = str(TMP / "games" / "Pocket Quest"), "Pocket Quest"
    first = save_backup.back_up(key, name, [str(saves_dir)], "after playing")
    time.sleep(1.1)
    plant(saves_dir / "slot1.sav", "chapter five -- and then it went wrong")
    plant(saves_dir / "slot2.sav", "a newer slot the old copy never had")
    backup = next(b for b in save_backup.list_backups(key, name) if b.path == first.made)

    ok, message = save_backup.restore(backup, key=key, name=name, install_dir=key, interactive=False)
    check("the restore reports success", ok, message)
    check("the folder holds exactly what the copy held",
          tree(saves_dir) == {"slot1.sav": "chapter one", os.path.join("profile", "settings.cfg"): "fov=90"},
          tree(saves_dir))
    check("with the files' own dates, not today's",
          abs(os.path.getmtime(saves_dir / "slot1.sav") - old) < 3)
    check("what was there went to the Recycle Bin, as a whole folder, without a second question",
          binned and binned[-1] == (str(saves_dir), True), binned)
    before = [b for b in save_backup.list_backups(key, name) if b.manifest["reason"] == "before restoring"]
    check("and was copied first, newer slot and all", bool(before))
    if before:
        with zipfile.ZipFile(before[0].path) as archive:
            check("that copy holds the saves exactly as they were before the restore",
                  archive.read("0/slot2.sav").decode() == "a newer slot the old copy never had")

    print("\n=== 3. nothing is changed when anything is wrong ===")
    evil = TMP / "evil.zip"
    with zipfile.ZipFile(evil, "w") as archive:
        archive.writestr(save_backup.MANIFEST, json.dumps(
            {"game": name, "key": key, "made_at": "2026-09-01T10:00:00+03:00", "reason": "x",
             "folders": [str(saves_dir)], "fingerprints": []}))
        archive.writestr("0/../../escaped.txt", "should never land anywhere")
    snapshot, bins = tree(saves_dir), len(binned)
    bad = save_backup.Backup(evil, backup.made_at, evil.stat().st_size,
                             json.loads(zipfile.ZipFile(evil).read(save_backup.MANIFEST)))
    ok, message = save_backup.restore(bad, key=key, name=name, install_dir=key, interactive=False)
    check("a copy holding a path that climbs out of its folder is refused",
          not ok and "outside" in message, message)
    check("with the saves untouched and nothing binned",
          tree(saves_dir) == snapshot and len(binned) == bins
          and not (TMP / "AppData" / "escaped.txt").exists())

    real_back_up = save_backup.back_up
    plant(saves_dir / "slot3.sav", "something new, so a safety copy is needed")
    save_backup.back_up = lambda *a, **k: save_backup.Result(error="disk full, in a test")
    snapshot, bins = tree(saves_dir), len(binned)
    ok, message = save_backup.restore(backup, key=key, name=name, install_dir=key, interactive=False)
    save_backup.back_up = real_back_up
    check("if the saves there now cannot be copied first, nothing is changed",
          not ok and tree(saves_dir) == snapshot and len(binned) == bins, message)

    print("\n=== 4. a copy from an earlier install ===")
    old_home = TMP / "games" / "cultic.v1.0-p2p"
    new_home = TMP / "games" / "cultic.v2.1-p2p"
    plant(old_home / "CULTIC_Data" / "Saves" / "slot.sav", "the run from the old version")
    early = save_backup.back_up(str(old_home), "CULTIC", [str(old_home / "CULTIC_Data" / "Saves")],
                                "before uninstalling")
    plant(new_home / "CULTIC_Data" / "Saves" / "slot.sav", "a fresh start")
    save_backup.back_up(str(TMP / "games" / "Unrelated"), "Unrelated Game",
                        [str(saves_dir)], "after playing")
    offered = save_backup.choices(str(new_home), "CULTIC")
    check("the new install is offered the old install's copy, marked as such",
          len(offered) == 1 and offered[0][1] is True and offered[0][0].path == early.made, offered)
    places = save_backup.targets(offered[0][0], str(new_home))
    check("and a save folder that lived inside the old game folder follows the game",
          places == [str(new_home / "CULTIC_Data" / "Saves")], places)
    ok, message = save_backup.restore(offered[0][0], key=str(new_home), name="CULTIC",
                                      install_dir=str(new_home), interactive=False)
    check("restoring it puts the old run into the new install",
          ok and (new_home / "CULTIC_Data" / "Saves" / "slot.sav").read_text() ==
          "the run from the old version", message)
    check("and never recreates the old folder", not old_home.exists() or
          (old_home / "CULTIC_Data" / "Saves" / "slot.sav").read_text() == "the run from the old version")

    print("\n=== 5. from the launcher: the menu, the refusal, the pad, the questions ===")
    w = ui_window.MainWindow()
    windows.append(w)
    game_dir = TMP / "scan root" / "Pocket Quest"
    plant(game_dir / "PocketQuest.exe", "x" * 30_000)
    entry = GameEntry(
        source="folders", source_id=str(game_dir / "PocketQuest.exe"), display_name="Pocket Quest",
        install_dir=str(game_dir), launch_kind="exe", launch_target=str(game_dir / "PocketQuest.exe"),
        working_dir=str(game_dir), icon_hint="", size_on_disk=30_000, detection="heuristic",
    )
    w.overrides.update(entry.identity_key, save_dirs=[str(saves_dir)])
    w.entries = list(w.entries) + [entry]
    w.reload_views()
    quest = w.by_key[entry.identity_key]
    for n in range(3):
        plant(saves_dir / f"progress{n}.sav", f"step {n}")
        time.sleep(1.1)
        save_backup.back_up(quest.key, quest.display_name, [str(saves_dir)], "after playing")

    menu = ui_actions.build_menu(w, quest)
    check("the menu offers Restore saves... once copies exist",
          {a.text(): a.isEnabled() for a in menu.actions()}.get("Restore saves...") is True)
    menu.deleteLater()

    told = []
    real_info, real_warn = QMessageBox.information, QMessageBox.warning
    QMessageBox.information = lambda *a, **k: told.append(("info", a[2] if len(a) > 2 else ""))
    QMessageBox.warning = lambda *a, **k: told.append(("warning", a[2] if len(a) > 2 else ""))
    try:
        w.tracker.is_running = lambda k: k == quest.key
        ui_save_restore.restore_flow(w, quest)
        check("while the game is running it refuses, and says why",
              told and "running" in told[0][1], told)
        w.tracker.is_running = lambda k: False

        rows = []

        def drive_the_list():
            dialog = QApplication.activeModalWidget()
            if isinstance(dialog, ui_save_restore.SaveRestoreDialog):
                rows.append(dialog.list.currentRow())
                w._on_pad_action(controller.DOWN)
                rows.append(dialog.list.currentRow())
                dialog.accept()
            else:
                QTimer.singleShot(50, drive_the_list)

        def press_restore():
            box_ = QApplication.activeModalWidget()
            if isinstance(box_, QMessageBox):
                rows.append(("default", box_.defaultButton().text()))
                restore = next(b for b in box_.buttons() if b.text() == "Restore")
                restore.click()
            else:
                QTimer.singleShot(50, press_restore)

        told.clear()
        chosen_backup = save_backup.choices(quest.key, quest.display_name)[1][0]
        QTimer.singleShot(100, drive_the_list)
        QTimer.singleShot(400, press_restore)
        ui_save_restore.restore_flow(w, quest)
        check("the pad moves through the list of copies", rows[:2] == [0, 1], rows)
        check("the question's default answer is Cancel", ("default", "Cancel") in rows, rows)
        check("and the copy the pad landed on is the one that came back",
              told and told[-1][0] == "info" and chosen_backup.made_at.strftime("%d %b %Y, %H:%M")
              in told[-1][1], told)
    finally:
        QMessageBox.information, QMessageBox.warning = real_info, real_warn

finally:
    removal.send_to_recycle_bin = real_bin
    for window in windows:
        try:
            window.close()
        except RuntimeError:
            pass
    shutil.rmtree(TMP, ignore_errors=True)
    print("\n=== 6. the real library is exactly as it was found ===")
    changed = box.finish()
    check("overrides.json, config.json and catalog.json are byte for byte unchanged", not changed,
          changed)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
