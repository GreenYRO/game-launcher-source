"""Phase 36: a new version of a game you had -- its history and its save copies follow it.

Asked for after The Witcher 3 was reinstalled from a newer build: the launcher treated it
as a new game, with none of the 5 hours played, and the copies of its saves made before
the uninstall could not be restored to it.

Runs against a throwaway copy of the data (test_sandbox) -- the real overrides, catalog
and save copies are copied in and only ever read. A window is shown throughout. Nothing
starts a game, and the Recycle Bin is a folder of the test's own.
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
HERE = Path(__file__).resolve().parents[1]
REAL_SHOTS = HERE / "data" / "cache" / "screenshots"
box.copy_cache("steam_details", "steam_news.json", "steam_web.json",
               *[f"screenshots/{name}" for name in (os.listdir(REAL_SHOTS) if REAL_SHOTS.is_dir() else [])])
print(f"real screenshots copied into the sandbox: {len(list((Path(box.folder) / 'cache' / 'screenshots').glob('*')))}")
SANDBOX = Path(box.folder)
if (HERE / "data" / "save_backups").is_dir():
    shutil.copytree(HERE / "data" / "save_backups", SANDBOX / "save_backups")  # a copy, read only
print(f"save copies copied into the sandbox: {len(list((SANDBOX / 'save_backups').glob('*')))} game folders")

import logging

logging.basicConfig(level=logging.ERROR)

from PySide6.QtCore import QEventLoop, QPoint, QTimer
from PySide6.QtWidgets import QApplication

app = QApplication([])

from data_access import backups
from data_access import catalog_io
from adapters import controller
from logic import lineage
from shared import naming
from logic import removal
from shared import rules
from logic import save_backup
from adapters import save_worker
from logic import saves
from logic import stats as stats_module
from presentation import ui_actions
from presentation import ui_earlier
from presentation import ui_save_restore
from presentation import ui_tv
from presentation import ui_window
from shared.models import GameEntry

TMP = Path(tempfile.mkdtemp(prefix="phase36-"))
BIN = TMP / "recycle bin"
BIN.mkdir()
passed = failed = 0
windows = []
binned = []


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"   PASS  {name}")
    else:
        failed += 1
        print(f"   FAIL  {name}   {detail}")


def settle(seconds=0.4):
    """A local event loop -- never app.exec() ended by app.quit() (the Phase 31 lesson)."""
    loop = QEventLoop()
    QTimer.singleShot(round(seconds * 1000), loop.quit)
    loop.exec()


def plant(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def fake_bin(path, hwnd=0, interactive=True, already_asked=False):
    binned.append(path)
    shutil.move(path, BIN / f"{len(binned)}-{Path(path).name}")
    return True, "Moved to the Recycle Bin."


real_bin = removal.send_to_recycle_bin
removal.send_to_recycle_bin = fake_bin
played = []
real_play = ui_actions.play
ui_actions.play = lambda window, view: played.append(view.key)

NEW = r"c:\games\the witcher 3"
OLD = r"c:\games\the witcher 3 wild hunt goty"

print(f"\nsandbox data folder: {box.folder}")

try:
    print("\n=== 1. which names are one game ===")
    pairs = [
        ("The Witcher 3", "The Witcher 3: Wild Hunt - Game of the Year Edition", True),
        ("S.T.A.L.K.E.R. 2", "S T A L K E R 2 Heart Of Chornobyl", True),
        ("S.T.A.L.K.E.R. 2 Heart of Chornobyl", "S T A L K E R 2 Heart Of Chornobyl Ultimate Editon", True),
        ("The Blood of Dawnwalker", "The Blood Of Dawnwalker", True),
        ("Marvel's Spider-Man 2", "Marvels Spiderman 2", True),
        ("Forza Horizon 5", "Forza Horizon 5 Premium Edition", True),
        ("BeamNG.drive", "Beamng Drive", True),
        ("Silent Hill 2", "Silent Hill f", False),
        ("Silent Hill 2", "Silent Hill 3", False),
        ("Far Cry", "Far Cry 3", False),
        ("Grand Theft Auto", "Grand Theft Auto V", False),
        ("Control Resonant", "Control", False),
        ("Cyberpunk 2077", "Counter-Strike 2", False),
    ]
    wrong = [(a, b) for a, b, want in pairs if naming.same_title(a, b) != want]
    check(f"all {len(pairs)} pairs judged right -- an edition or a subtitle is the same game, "
          "a sequel and a look-alike are not", not wrong, wrong)
    check("dotted initials read as one word",
          naming.title_words("S.T.A.L.K.E.R. 2") == ["stalker", "2"], naming.title_words("S.T.A.L.K.E.R. 2"))

    print("\n=== 2. what is never a save folder ===")
    report = r"C:\Users\x\AppData\Local\REDEngine\ReportQueue\Witcher3_20260930_214632444"
    telemetry = r"C:\Users\x\AppData\Roaming\Mozilla\Firefox\Profiles\a.default\saved-telemetry-pings"
    real_ones = [r"C:\Users\x\Documents\The Witcher 3\gamesaves",
                 r"C:\Users\x\AppData\Roaming\GSE Saves\2215200",
                 r"C:\games\CULTIC\CULTIC_Data\Saves"]
    check("a crash reporter's queue is not a save folder", not saves.could_be_save_folder(report))
    check("nor is a browser's telemetry", not saves.could_be_save_folder(telemetry))
    check("real save folders still are", all(saves.could_be_save_folder(p) for p in real_ones))
    check("Firefox's profile is not even walked", all(
        "Mozilla" in rules.SAVES_WALK_SKIP[base] for base in ("FOLDERID_LocalAppData", "FOLDERID_RoamingAppData")))
    base = TMP / "LocalAppData"
    plant(base / "REDEngine" / "ReportQueue" / "Witcher3_1" / "autosave_1.sav", "a copy")
    plant(base / "Witcher Game" / "gamesaves" / "AutoSave_1.sav", "the real one")
    index = saves.build_index([("FOLDERID_LocalAppData", str(base))])
    check("the walk notes the save folder and not the crash report beside it",
          list(index.folders) == [str(base / "Witcher Game" / "gamesaves")], list(index.folders))

    good = TMP / "Docs" / "My Game" / "Saves"
    plant(good / "slot1.sav", "progress")
    bogus = TMP / "Local" / "Engine" / "ReportQueue" / "Crash_1"
    plant(bogus / "slot1.sav", "a copy")
    made = save_backup.back_up(str(TMP / "games" / "My Game"), "My Game", [str(good), str(bogus)], "test")
    with zipfile.ZipFile(made.made) as archive:
        kept = json.loads(archive.read("manifest.json"))["folders"]
    check("a copy of the saves never takes a crash report's folder along", kept == [str(good)], kept)
    real_known = saves.known_folders
    saves.known_folders = lambda: [("FOLDERID_Documents", str(TMP / "Docs"))]
    try:
        job = save_worker.Job(key=str(TMP / "games" / "My Game"), name="My Game", appid="",
                              install_dir="", windows=[(time.time() - 60, time.time() + 60)],
                              known=[str(bogus), str(good)], back_up=False, reason="test")
        outcome = save_worker.run_jobs([job], ())[0]
    finally:
        saves.known_folders = real_known
    check("a wrong folder recorded earlier is dropped by the next look for saves",
          str(bogus) not in outcome.folders and str(good) in outcome.folders, outcome.folders)

    # A copy made before this phase, holding a crash report's folder too.
    old_copy = TMP / "old copy.zip"
    target_good = TMP / "restore" / "Saves"
    target_bogus = TMP / "restore" / "ReportQueue" / "Crash_9"
    with zipfile.ZipFile(old_copy, "w") as archive:
        archive.writestr("manifest.json", json.dumps({
            "game": "My Game", "key": str(TMP / "games" / "Old My Game"), "made_at": "2026-09-30T10:00:00+03:00",
            "reason": "before uninstalling", "folders": [str(target_good), str(target_bogus)]}))
        archive.writestr("0/slot1.sav", "the old run")
        archive.writestr("1/.ready", "send me")
    backup = save_backup.Backup(old_copy, save_backup.datetime.fromisoformat("2026-09-30T10:00:00+03:00"),
                                old_copy.stat().st_size, json.loads(zipfile.ZipFile(old_copy).read("manifest.json")))
    ok, message = save_backup.restore(backup, key=str(TMP / "games" / "My Game"), name="My Game",
                                      install_dir="", interactive=False)
    check("restoring an older copy puts the saves back", ok and (target_good / "slot1.sav").read_text() == "the old run",
          message)
    check("and leaves the crash report out -- it would only queue a stale report to send",
          not target_bogus.exists())

    print("\n=== 3. the launcher opens: wrong folders forgotten, names kept ===")
    raw = test_sandbox.records()
    wrong_before = {k: [p for p in r.get(rules.SAVE_DIRS_KEY) or [] if not saves.could_be_save_folder(p)]
                    for k, r in raw.items()}
    wrong_before = {k: v for k, v in wrong_before.items() if v}
    before_old = json.loads(json.dumps(raw.get(OLD, {})))
    before_new = json.loads(json.dumps(raw.get(NEW, {})))
    w = ui_window.MainWindow()
    windows.append(w)
    w.resize(1600, 950)
    w.move(app.primaryScreen().availableGeometry().topLeft())
    w.show()
    settle(1.5)
    left = {k: [p for p in (w.overrides.get(k).get(rules.SAVE_DIRS_KEY) or [])
                if not saves.could_be_save_folder(p)] for k in wrong_before}
    print(f"         (records holding a folder that was never a save: {len(wrong_before)})")
    check("every folder that was never a save is gone from the records",
          not any(left.values()), left)
    check("the save folders that are real stay", all(
        all(saves.could_be_save_folder(p) and p in (w.overrides.get(k).get(rules.SAVE_DIRS_KEY) or [])
            for p in raw[k].get(rules.SAVE_DIRS_KEY) or [] if saves.could_be_save_folder(p))
        for k in wrong_before))
    check("every game's record now keeps the name it goes by",
          all(w.overrides.get(v.key).get(rules.KNOWN_AS_KEY) == v.entry.display_name for v in w.views))

    if NEW not in w.by_key:
        # The copy's catalogue is the user's last scan. On 11 October he was copying in a newer
        # build (The Witcher 3 Wild Hunt -- Remastered) while the launcher scanned, so the copy
        # knew neither install; a scan here sees the disk as it is now. Read only.
        w.start_scan(quiet=True)
        deadline = time.monotonic() + 120
        while w.worker is not None and w.worker.isRunning() and time.monotonic() < deadline:
            settle(0.2)
        settle(0.5)
    has_witcher = NEW in w.by_key and OLD in raw and OLD not in w.by_key
    newer = [k for k in w.by_key if k != NEW and "witcher 3" in k]
    # A third install: the history went from the GOG one (OLD) to NEW, and NEW is gone in turn.
    third = (not has_witcher and newer and raw.get(OLD, {}).get(rules.CARRIED_TO_KEY) == NEW
             and NEW not in w.by_key)
    # The user carries it over himself, on the real machine, after this phase ships -- and
    # did, three days later, which failed nine checks here that assumed he had not. So the
    # library is taken as it is: before the carry-over, the question is asked and answered;
    # after it, the result is checked instead (the no-assumed-state rule, again).
    already = raw.get(OLD, {}).get(rules.CARRIED_TO_KEY) == NEW
    print("\n=== 4. The Witcher 3: the page asks ===")
    if third:
        newest = newer[0]
        print(f"         (a newer build is installed since -- {w.by_key[newest].display_name}; "
              "checking the chain instead)")
        installed = set(w.by_key)
        offers = lineage.offers(w.by_key[newest], w.overrides, installed)
        check("the newer build is offered the install that holds the history, not the one carried into it",
              [o.key for o in offers] == [NEW], [(o.key, o.why) for o in offers])
        check("named as that install was known", offers and offers[0].name == raw[NEW].get(rules.KNOWN_AS_KEY),
              offers and offers[0].name)
        check("the first install is never offered again, to anything",
              not any(o.key == OLD for v in w.views for o in lineage.offers(v, w.overrides, installed)))
        w.show_detail(newest)
        settle(1.2)
        page = w.detail
        check("its page shows the question first", page.earlier_card.isVisible()
              and page.left_column.indexOf(page.earlier_card) == 0)
        before_mid = json.loads(json.dumps(w.overrides.get(NEW)))
        before_newest = json.loads(json.dumps(w.overrides.get(newest)))

        print("\n=== 5. ...and carries it over, the whole history ===")
        page.carry_button.click()
        settle(1.0)
        rec = w.overrides.get(newest)
        mid = w.overrides.get(NEW)
        check("the play time is added up", rec.get("playtime_seconds") == int(before_mid.get("playtime_seconds") or 0)
              + int(before_newest.get("playtime_seconds") or 0), rec.get("playtime_seconds"))
        check("every session comes across, none twice",
              {s["start"] for s in rec.get(rules.SESSIONS_KEY) or []}
              == {s["start"] for s in (before_mid.get(rules.SESSIONS_KEY) or []) + (before_newest.get(rules.SESSIONS_KEY) or [])})
        check("it carries on from both installs before it", {NEW, OLD} <= set(rec.get(rules.EARLIER_KEYS_KEY) or []),
              rec.get(rules.EARLIER_KEYS_KEY))
        check("the middle record keeps only its dates, its name and where it went",
              set(mid) <= {"first_seen", rules.KNOWN_AS_KEY, rules.CARRIED_TO_KEY, rules.CARRIED_AT_KEY}
              and mid[rules.CARRIED_TO_KEY] == newest, mid)
        check("and the question has gone", not page.earlier_card.isVisible()
              and not lineage.offers(w.by_key[newest], w.overrides, set(w.by_key)))
    elif not has_witcher:
        check("the real library still has both Witcher 3 installs to test with", False,
              "skipped: the old one or the new one is not in this copy")
    elif already:
        print("         (carried over already on this machine -- checking the result instead)")
        installed = set(w.by_key)
        copies = len(list((SANDBOX / "save_backups").glob(f"* - {save_backup._hash(OLD)}/*.zip")))
        new = w.overrides.get(NEW)
        old = w.overrides.get(OLD)
        check("the new install carries on from the old one", OLD in (new.get(rules.EARLIER_KEYS_KEY) or []))
        check("the old record keeps only its dates, its name and where it went",
              set(old) <= {"first_seen", rules.KNOWN_AS_KEY, rules.CARRIED_TO_KEY, rules.CARRIED_AT_KEY}
              and old[rules.CARRIED_TO_KEY] == NEW, old)
        check("so it is never offered again, to anything",
              not any(o.key == OLD for v in w.views for o in lineage.offers(v, w.overrides, installed)))
        check("and its old name no longer counts as another game when saves are sorted out",
              not any("Goty" in n or "Game of the Year" in n for n in w.other_game_names()))
        w.show_detail(NEW)
        settle(1.2)
        page = w.detail
        check("its page asks nothing", not page.earlier_card.isVisible())
        check("and shows the time it carried over", "h" in page.facts().get("Played", ""),
              page.facts().get("Played"))
        restorable = save_backup.choices(*ui_save_restore.choice_args(w, w.by_key[NEW]))
        earlier = [(b, e) for b, e in restorable if e]
        from_old = [b for b, _e in earlier if b.manifest.get("key") == OLD]
        # Not "exactly the old one's": on 11 October the user installed a newer build, played it,
        # and went back -- that build's copy is an earlier install's too, and offered, rightly.
        check(f"the old install's {copies} copies of its saves are offered for restoring",
              len(from_old) == copies, (len(from_old), len(earlier)))
        check("and every other copy offered is an earlier install's -- never one still installed",
              all(b.manifest.get("key") not in installed for b, _e in earlier))
        check("the list says which game each earlier copy was made for",
              earlier and all(f"from an earlier install ({b.manifest.get('game')})" in ui_save_restore.describe(b, e)
                              for b, e in earlier)
              and all("(The Witcher 3: Wild Hunt" in ui_save_restore.describe(b, True) for b in from_old))
        try:
            lineage.carry_over(w.overrides, OLD, NEW)
            again = "no refusal"
        except ValueError as exc:
            again = str(exc)
        check("carrying it over a second time is refused", "already carried" in again, again)
    else:
        installed = set(w.by_key)
        offers = lineage.offers(w.by_key[NEW], w.overrides, installed)
        copies = len(list((SANDBOX / "save_backups").glob(f"* - {save_backup._hash(OLD)}/*.zip")))
        check("the new install is offered the old one, by its name",
              [o.key for o in offers] == [OLD] and offers[0].why == lineage.SAME_NAME,
              [(o.key, o.why) for o in offers])
        check("named as the copies of its saves call it, not by its folder",
              offers and offers[0].name.startswith("The Witcher 3: Wild Hunt"), offers and offers[0].name)
        check(f"and it knows the {copies} copies of its saves", offers and offers[0].copies == copies,
              offers and offers[0].copies)
        every = [o for v in w.views for o in lineage.offers(v, w.overrides, installed)]
        check("no game is ever offered an install that is still installed",
              not any(o.key in installed for o in every))
        restorable = save_backup.choices(*ui_save_restore.choice_args(w, w.by_key[NEW]))
        check("its saves' copies can be restored to it even before carrying over -- the old "
              "letter-for-letter name rule offered none",
              sum(1 for _b, e in restorable if e) == copies, len(restorable))
        check("the list says which game each earlier copy was made for",
              restorable and "(The Witcher 3: Wild Hunt" in ui_save_restore.describe(*restorable[0]),
              restorable and ui_save_restore.describe(*restorable[0]))

        w.show_detail(NEW)
        settle(1.2)
        page = w.detail
        check("its page shows the question first", page.earlier_card.isVisible()
              and page.left_column.indexOf(page.earlier_card) == 0)
        text = page.earlier_text.text()
        check("in words: which game, what it holds, and the question",
              "The Witcher 3: Wild Hunt" in text and "played" in text and "Carry all of that over" in text, text)
        check("both answers fit their buttons", all(
            b.width() >= b.sizeHint().width() for b in (page.carry_button, page.not_same_button)),
            [(b.width(), b.sizeHint().width()) for b in (page.carry_button, page.not_same_button)])
        lifetime_before = stats_module.gather(w.views, w.overrides).lifetime_seconds
        records_before = test_sandbox.records()

        print("\n=== 5. ...and carries it over ===")
        page.carry_button.click()
        settle(1.0)
        new = w.overrides.get(NEW)
        old = w.overrides.get(OLD)
        old_sessions = {s["start"] for s in before_old.get(rules.SESSIONS_KEY) or []}
        new_sessions = {s["start"] for s in before_new.get(rules.SESSIONS_KEY) or []}
        check("the play time is added up",
              new.get("playtime_seconds") == int(before_old.get("playtime_seconds") or 0)
              + int(before_new.get("playtime_seconds") or 0), new.get("playtime_seconds"))
        check("every session comes across, none twice",
              {s["start"] for s in new.get(rules.SESSIONS_KEY) or []} == old_sessions | new_sessions)
        check("the latest 'last played' wins", new.get("last_played") == max(
            t for t in (before_old.get("last_played"), before_new.get("last_played")) if t))
        real_old_saves = [p for p in before_old.get(rules.SAVE_DIRS_KEY) or [] if saves.could_be_save_folder(p)]
        check("its save folder comes across, the crash report does not",
              all(p in new.get(rules.SAVE_DIRS_KEY, []) for p in real_old_saves)
              and all(saves.could_be_save_folder(p) for p in new.get(rules.SAVE_DIRS_KEY, [])),
              new.get(rules.SAVE_DIRS_KEY))
        check("the cover you picked for the new one stays", new.get("cover") == before_new.get("cover"))
        check("it remembers which install it carries on from", new.get(rules.EARLIER_KEYS_KEY) == [OLD])
        check("the old record keeps only its dates, its name and where it went",
              set(old) == {"first_seen", rules.KNOWN_AS_KEY, rules.CARRIED_TO_KEY, rules.CARRIED_AT_KEY}
              and old[rules.CARRIED_TO_KEY] == NEW, old)
        check("so it is never offered again, to anything",
              not any(o.key == OLD for v in w.views for o in lineage.offers(v, w.overrides, set(w.by_key))))
        check("and its old name no longer counts as another game when saves are sorted out",
              not any("Goty" in n or "Game of the Year" in n for n in w.other_game_names()))
        check("the question has gone from the page", not page.earlier_card.isVisible())
        check("the pills now show the time played", "5h" in page.facts().get("Played", ""),
              page.facts().get("Played"))
        check("and that its saves have been copied, by the earlier install",
              page.facts().get("Saves copied", "not yet") != "not yet", page.facts().get("Saves copied"))
        message = w.statusBar().currentMessage()
        check("a message says what came across", message.startswith("Carried over from The Witcher 3")
              and "session" in message, message)
        lifetime_after = stats_module.gather(w.views, w.overrides).lifetime_seconds
        check("Stats counts the old install's time now -- it was invisible while the game was gone",
              lifetime_after - lifetime_before == int(before_old.get("playtime_seconds") or 0),
              (lifetime_before, lifetime_after))
        newest = backups.list_snapshots()[0]
        check("a snapshot of the data from just before is kept, which is the undo",
              test_sandbox.records_in(newest.path) == records_before)
        restorable = save_backup.choices(*ui_save_restore.choice_args(w, w.by_key[NEW]))
        check("and the old copies are still offered for restoring, now by right of the carry-over",
              sum(1 for _b, e in restorable if e) == copies, len(restorable))
        try:
            lineage.carry_over(w.overrides, OLD, NEW)
            again = "no refusal"
        except ValueError as exc:
            again = str(exc)
        check("carrying the same install over twice is refused", "already carried" in again, again)

    print("\n=== 6. what comes across, field by field ===")
    old_home = TMP / "games" / "Quest Saga v1.0"
    new_home = TMP / "games" / "Quest Saga v1.1"
    inside = old_home / "Data" / "Saves"
    plant(inside / "a.sav", "x")
    cover = plant(TMP / "art" / "quest.jpg", "not really a jpeg")
    a, b = str(old_home).lower(), str(new_home).lower()
    test_sandbox.put_records({a: {
        "first_seen": "2026-08-01T10:00:00+03:00", rules.KNOWN_AS_KEY: "Quest Saga",
        "playtime_seconds": 3600, "last_played": "2026-09-01T10:00:00+03:00",
        rules.SESSIONS_KEY: [{"start": "2026-09-01T09:00:00+03:00", "minutes": 60},
                             {"start": "2026-09-02T09:00:00+03:00", "minutes": 5}],
        "favorite": True, rules.STATUS_KEY: "playing", rules.NOTES_KEY: "Act 2, the bridge.",
        "cover": str(cover), "args": "-dx11", "exe": str(old_home / "quest.exe"), "hidden": True,
        rules.SAVE_DIRS_KEY: [str(inside), report],
    }, b: {
        "first_seen": "2026-10-01T10:00:00+03:00", "playtime_seconds": 60,
        "last_played": "2026-10-02T10:00:00+03:00",
        rules.SESSIONS_KEY: [{"start": "2026-09-02T09:00:00+03:00", "minutes": 5}],
        rules.STATUS_KEY: "finished", rules.NOTES_KEY: "New build.",
    }}, w.overrides)
    carried = lineage.carry_over(w.overrides, a, b, new_install_dir=str(new_home))
    rec = w.overrides.get(b)
    check("time is summed, sessions merged without the shared one twice",
          rec["playtime_seconds"] == 3660 and len(rec[rules.SESSIONS_KEY]) == 2, rec)
    check("the newer 'last played' is kept", rec["last_played"] == "2026-10-02T10:00:00+03:00")
    check("a star on the old one stays", rec.get("favorite") is True)
    check("this game's own mark wins over the old one", rec[rules.STATUS_KEY] == "finished")
    check("two notes are both kept, this game's first",
          rec[rules.NOTES_KEY] == "New build.\n\nAct 2, the bridge.", rec[rules.NOTES_KEY])
    check("a chosen cover and launch arguments come across where this game has none",
          rec.get("cover") == str(cover) and rec.get("args") == "-dx11")
    check("nothing about the old folder does: not its exe, not the hidden flag",
          "exe" not in rec and "hidden" not in rec)
    check("a save folder inside the old game folder moves into the new one",
          rec[rules.SAVE_DIRS_KEY] == [str(new_home / "Data" / "Saves")], rec[rules.SAVE_DIRS_KEY])
    check("the message lists the rest", {"star", "note", "cover", "launch arguments"} <= set(carried.fields),
          carried.fields)

    print("\n=== 7. 'Not the same game', the menu, and the pad ===")
    game_dir = TMP / "scan root" / "Moon Garden Remastered"
    plant(game_dir / "MoonGarden.exe", "x" * 30_000)
    entry = GameEntry(
        source="folders", source_id=str(game_dir / "MoonGarden.exe"), display_name="Moon Garden Remastered",
        install_dir=str(game_dir), launch_kind="exe", launch_target=str(game_dir / "MoonGarden.exe"),
        working_dir=str(game_dir), icon_hint="", size_on_disk=30_000, detection="heuristic",
    )
    gone = str(TMP / "scan root" / "moon garden").lower()
    test_sandbox.put_records({gone: {"first_seen": "2026-08-01T10:00:00+03:00", rules.KNOWN_AS_KEY: "Moon Garden",
                                     "playtime_seconds": 7200, "last_played": "2026-08-20T10:00:00+03:00"}},
                             w.overrides)
    w.entries = list(w.entries) + [entry]
    w.reload_views()
    garden = w.by_key[entry.identity_key]
    w.show_detail(garden.key)
    settle(1.0)
    check("a remaster of a game you had is asked about", w.detail.earlier_card.isVisible()
          and w.detail.offer is not None and w.detail.offer.key == gone)

    w.set_tv_mode(True)
    w.resize(1707, 960)
    settle(1.0)
    check("in TV mode the answers still fit", all(
        b.width() >= b.sizeHint().width() for b in (w.detail.carry_button, w.detail.not_same_button)))
    w.detail.grab().save(str(TMP / "offer_tv.png"))
    w.set_tv_mode(False)
    settle(0.8)

    w.detail.not_same_button.click()
    settle(0.4)
    check("'Not the same game' takes the question away", not w.detail.earlier_card.isVisible())
    check("and remembers it", gone in (w.overrides.get(garden.key).get(rules.NOT_SAME_KEY) or [])
          and not lineage.offers(garden, w.overrides, set(w.by_key)))
    check("the time stays where it was", w.overrides.get(gone).get("playtime_seconds") == 7200)

    menu = ui_actions.build_menu(w, garden)
    item = next((a for a in menu.actions() if a.text() == "Same game as an earlier install..."), None)
    check("the menu offers to join it by hand anyway", item is not None and item.isEnabled())
    everything = lineage.everything(garden, w.overrides, set(w.by_key))
    check("its list holds every earlier install, the likely ones first",
          everything and everything[0].key == gone and all(not e.why for e in everything[1:]),
          [(e.name, e.why) for e in everything[:3]])

    seen = {}

    def in_dialog():
        dialog = QApplication.activeModalWidget()
        seen["hints"] = list(w.hint_bar.labels)
        seen["open"] = dialog is not None and dialog.list.currentRow() == 0
        w._on_pad_action(controller.DOWN)
        w._on_pad_action(controller.UP)
        seen["back"] = dialog.list.currentRow() == 0
        w._on_pad_action(controller.ACTIVATE)

    w.set_tv_mode(True)
    settle(0.8)
    QTimer.singleShot(600, in_dialog)
    ui_earlier.pick_flow(w, garden)  # blocks until the pad answers it
    settle(0.6)
    check("the pad moves through the list", seen.get("open") and seen.get("back"))
    check("with the dialog's hints showing",
          seen.get("hints") == [label for _pad, label in ui_tv.HINT_SETS[ui_tv.DIALOG]], seen.get("hints"))
    check("and A carries it over", w.overrides.get(garden.key).get("playtime_seconds") == 7200
          and w.overrides.get(gone).get(rules.CARRIED_TO_KEY) == garden.key)
    check("which also lifts the earlier 'not the same'",
          gone not in (w.overrides.get(garden.key).get(rules.NOT_SAME_KEY) or []))
    w.set_tv_mode(False)
    settle(0.6)

    print("\n=== 8. a name alone never pulls in an installed game's copies ===")
    installed_key, other_key, me = str(TMP / "g" / "foo bar"), str(TMP / "g" / "foo bar v0"), str(TMP / "g" / "foo bar v2")
    folder = TMP / "foo saves"
    plant(folder / "save1.sav", "x")
    save_backup.back_up(installed_key, "Foo Bar", [str(folder)], "test")
    save_backup.back_up(other_key, "Foo Bar Deluxe Edition", [str(folder)], "test")
    offered = save_backup.choices(me, "Foo Bar", (), (installed_key, me))
    check("copies of a game that is still installed are not offered to another",
          [b.manifest["key"] for b, _e in offered] == [other_key], [b.manifest["key"] for b, _e in offered])
    w.close()

finally:
    ui_actions.play = real_play
    removal.send_to_recycle_bin = real_bin
    for window in windows:
        try:
            window.close()
        except RuntimeError:
            pass
    shutil.rmtree(TMP, ignore_errors=True)
    print("\n=== 9. the real library is exactly as it was found ===")
    changed = box.finish()
    check("overrides.json, config.json and catalog.json are byte for byte unchanged", not changed,
          changed)

check("nothing was started", not played, played)
print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
