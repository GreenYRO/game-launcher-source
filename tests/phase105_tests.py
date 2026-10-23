"""Phase 105: fill the missing covers in one go, from SteamGridDB, with the user's key.

  1. SteamGridDB told apart: a match, a miss (cached), and no answer -- a 429 with its Retry-After (seconds or a
     date), a refused key, unreachable -- raised with `strict`, the old empty answers without; no miss ever cached
     for an answer not given; Test's words for each;
  2. which games: the grid's games with no cover -- the covered, the hand-set (a file since gone too), the hidden
     and the tools left out; the row's words and its button, by the key and the network switch;
  3. the batch on a fake SteamGridDB, its waits recorded: the gate (Eden is not Tiny Eden), the pacing (a gap
     before every request but the first; a name or an image already cached costs none), the misses cached, a 429
     waited out (its Retry-After, or the backoff) and asked once more, a second one stopping it, a Retry-After over
     the cap stopping at once, Cancel (the game under way finishes; a wait ends at once), unreachable and a refused
     key stopping, the last words;
  4. in the window, on a copy with planted games: Settings' row and its button; the dialog -- the backup before
     the first write, the covers in the cover slot only (a banner untouched, a hand-set cover kept), the grid
     redrawn, a scan held back and run after, the misses cached; Cancel and Escape while it runs; a scan under way
     waited for; the restore bringing the library back; the key never in the log;
  5. the documents, the layers, the real data untouched.

On a throwaway copy of the data, its own cache; SteamGridDB is a fake answering in this process -- no request
leaves it.
"""
import email.message
import io
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import sources  # the build log's notes (Phase 91)
import test_sandbox

FAKE_KEY = "fake-sgdb-key-105-0123456789abcdef"
box = test_sandbox.start({"allow_network": False, "startup_scan": False, "tv_mode": False,
                          "steamgriddb_key": FAKE_KEY})

from shared import rules  # noqa: E402

CDN = "https://cdn2.steamgriddb.com/grid/"
REAL_CACHE = PROJECT / "data" / "cache"


def real_art() -> tuple:
    """The user's own SteamGridDB cache, photographed: the names file's bytes, and every picture by name and size."""
    names = REAL_CACHE / rules.SGDB_NAME_CACHE_FILE
    folder = REAL_CACHE / "sgdb_art"
    return (names.read_bytes() if names.is_file() else b"",
            sorted((p.name, p.stat().st_size) for p in folder.iterdir()) if folder.is_dir() else [])


real_art_before = real_art()


class Answer:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def read(self) -> bytes:
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        return None


class FakeSGDB:
    """SteamGridDB as this suite plays it: searches, tall grids, the image server; a 429 queued, down, refusing."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.names: dict[str, list[tuple[int, str]]] = {}
        self.grids: dict[int, bool] = {}
        self.limits: list[str | None] = []
        self.down = False
        self.refuse = False
        self.calls: list[str] = []
        self.keys: list[str] = []

    def urlopen(self, request, *args, **kwargs):
        url = getattr(request, "full_url", str(request))
        if not (url.startswith(rules.SGDB_BASE) or url.startswith(CDN)):
            outside.append(url)
            raise OSError("the network is blocked in this suite")
        self.calls.append(url)
        if url.startswith(CDN):
            return Answer(IMAGE)
        self.keys.append(dict(request.header_items()).get("Authorization", ""))
        if self.down:
            raise urllib.error.URLError("no route (the fake is down)")
        if self.limits:
            value = self.limits.pop(0)
            headers = email.message.Message()
            if value is not None:
                headers["Retry-After"] = value
            raise urllib.error.HTTPError(url, 429, "Too Many Requests", headers, io.BytesIO(b"slow down"))
        if self.refuse:
            raise urllib.error.HTTPError(url, 401, "Unauthorized", email.message.Message(), io.BytesIO(b"{}"))
        if "/search/autocomplete/" in url:
            term = urllib.parse.unquote(url.rsplit("/", 1)[1])
            data = [{"id": game_id, "name": name} for game_id, name in self.names.get(term, [])]
            return Answer(json.dumps({"success": True, "data": data}).encode())
        if "/grids/game/" in url:
            game_id = int(url.split("/grids/game/")[1].split("?")[0])
            data = [{"url": f"{CDN}{game_id}.jpg", "thumb": f"{CDN}thumb/{game_id}.jpg"}] if self.grids.get(game_id) else []
            return Answer(json.dumps({"success": True, "data": data}).encode())
        return Answer(b'{"success": false}')


fake = FakeSGDB()
outside: list[str] = []
urllib.request.urlopen = fake.urlopen

# Every line logged, to look for the key in (it must never be there).
logged: list[str] = []


class Keep(logging.Handler):
    def emit(self, record) -> None:
        try:
            logged.append(record.getMessage())
        except Exception as exc:  # noqa: BLE001 -- a record that cannot be formatted is kept as such
            logged.append(f"<unformattable record: {exc}>")


logging.getLogger().addHandler(Keep(level=logging.DEBUG))
if logging.getLogger().level > logging.INFO:
    logging.getLogger().setLevel(logging.INFO)

from PySide6.QtCore import QBuffer, QByteArray, QEventLoop, QIODevice, QTimer  # noqa: E402
from PySide6.QtGui import QColor, QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])


def make_image() -> bytes:
    """A real picture, big enough to pass the size check (rules.STEAM_ARTWORK_MIN_BYTES)."""
    import random

    noise = random.Random(105)
    image = QImage(60, 90, QImage.Format.Format_RGB32)
    for x in range(60):
        for y in range(90):
            image.setPixelColor(x, y, QColor(noise.randrange(256), noise.randrange(256), noise.randrange(256)))
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(data)


IMAGE = make_image()
assert len(IMAGE) >= rules.STEAM_ARTWORK_MIN_BYTES, len(IMAGE)  # a picture the size check lets through

from data_access import backups, catalog_io  # noqa: E402
from logic import fill_covers  # noqa: E402
from shared import paths  # noqa: E402
from shared.models import GameEntry  # noqa: E402
from web import steamgriddb  # noqa: E402

passed = failed = 0


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"   PASS  {name}")
    else:
        failed += 1
        print(f"   FAIL  {name}   {detail}")


def unreached(section: str, exc: Exception) -> None:
    global failed
    failed += 1
    import traceback

    print(f"   FAIL  section {section} did not finish: {type(exc).__name__}: {exc}")
    traceback.print_exc()


def settle(seconds: float) -> None:
    loop = QEventLoop()
    QTimer.singleShot(int(seconds * 1000), loop.quit)
    loop.exec()


def fresh_cache() -> str:
    return tempfile.mkdtemp(prefix="sgdb-", dir=str(box.folder))


def names_in(cache: str) -> dict:
    path = Path(cache) / rules.SGDB_NAME_CACHE_FILE
    return json.loads(path.read_text(encoding="utf-8"))["names"] if path.is_file() else {}


print("=== 1. SteamGridDB told apart: a match, a miss, no answer ===")
try:
    fake.reset()
    fake.names["Hollow Knight"] = [(1001, "Hollow Knight")]
    fake.limits = ["7"]
    try:
        steamgriddb.search("Hollow Knight", FAKE_KEY, with_thumbnails=False, strict=True)
        raised = None
    except steamgriddb.RateLimited as exc:
        raised = exc.retry_after
    check("a 429 with Retry-After: 7 is raised with strict, its seven seconds read", raised == 7.0, raised)
    later = datetime.now(timezone.utc) + timedelta(seconds=40)
    seconds = steamgriddb._retry_after(format_datetime(later, usegmt=True))
    check("a Retry-After that is a date: the seconds until it", seconds is not None and 37 <= seconds <= 40, seconds)
    check("none, or one unreadable: None -- never a guess",
          steamgriddb._retry_after(None) is None and steamgriddb._retry_after("soon") is None)
    fake.limits = [None]
    check("without strict, a 429 is the empty answer it always was",
          steamgriddb.search("Hollow Knight", FAKE_KEY, with_thumbnails=False) == [])
    cache = fresh_cache()
    fake.limits = [None]
    check("a name looked up during a 429 caches nothing (it was cached as a miss for 7 days before)",
          steamgriddb.resolve_game_id("Hollow Knight", FAKE_KEY, cache) == "" and names_in(cache) == {}
          and steamgriddb.known_game_id("Hollow Knight", cache) is None, names_in(cache))
    fake.down = True
    check("nor one looked up with SteamGridDB unreachable",
          steamgriddb.resolve_game_id("Hollow Knight", FAKE_KEY, cache) == "" and names_in(cache) == {})
    try:
        steamgriddb.resolve_game_id("Hollow Knight", FAKE_KEY, cache, strict=True)
        why = None
    except steamgriddb.NoAnswer as exc:
        why = exc.why
    check("and with strict it says why: unreachable", why == "unreachable", why)
    fake.down = False
    check("an answer is cached: a match ...",
          steamgriddb.resolve_game_id("Hollow Knight", FAKE_KEY, cache) == "1001"
          and steamgriddb.known_game_id("Hollow Knight", cache) == "1001")
    fake.names["Eden"] = [(2002, "Tiny Eden")]
    check("... and a miss: Eden is not Tiny Eden (0.67 under the 0.85 gate), cached as one",
          steamgriddb.resolve_game_id("Eden", FAKE_KEY, cache) == ""
          and steamgriddb.known_game_id("Eden", cache) == "" and names_in(cache).get("eden", {}).get("game_id") == "",
          names_in(cache))
    before = len(fake.calls)
    check("a name the cache knows costs no request", steamgriddb.resolve_game_id("Eden", FAKE_KEY, cache) == ""
          and len(fake.calls) == before)
    fake.limits = [None]
    words = steamgriddb.check_key(FAKE_KEY)
    fake.down = True
    down_words = steamgriddb.check_key(FAKE_KEY)
    fake.down, fake.refuse = False, True
    refused_words = steamgriddb.check_key(FAKE_KEY)
    fake.refuse = False
    check("Test says which: slowed down, unreachable, refused, works",
          words[1].startswith("SteamGridDB asked to slow down") and down_words[1] == "SteamGridDB could not be reached."
          and refused_words[1].startswith("That key was refused") and steamgriddb.check_key(FAKE_KEY) == (True, "Key works."),
          (words, down_words, refused_words))
    check("the key went only to SteamGridDB, as its own header", fake.keys and all(
        k == f"Bearer {FAKE_KEY}" for k in fake.keys) and not any(FAKE_KEY in url for url in fake.calls))
except Exception as exc:
    unreached("1", exc)


print("\n=== 2. which games, and the row's words ===")
try:
    art = Path(box.folder) / "art"
    art.mkdir(exist_ok=True)
    covered = art / "covered.jpg"
    covered.write_bytes(IMAGE)

    def entry(name: str, icon: str = "") -> GameEntry:
        folder = Path(box.folder) / "planted" / name
        folder.mkdir(parents=True, exist_ok=True)
        return GameEntry(source="folders", source_id=str(folder / f"{name}.exe"), display_name=name,
                         install_dir=str(folder), launch_kind="exe", launch_target=str(folder / f"{name}.exe"),
                         working_dir=str(folder), icon_hint=icon, size_on_disk=0, detection="heuristic")

    views = [
        catalog_io.GameView(entry("Zeta Uncovered")),
        catalog_io.GameView(entry("alpha uncovered")),
        catalog_io.GameView(entry("Has Art", str(covered))),
        catalog_io.GameView(entry("Hand Set"), {"cover": str(covered)}),
        catalog_io.GameView(entry("Hand Set Gone"), {"cover": str(art / "gone.jpg")}),
        catalog_io.GameView(entry("Hidden One"), {"hidden": True}),
        catalog_io.GameView(entry("A Tool"), {"is_tool": True}),
    ]
    listed = [v.display_name for v in fill_covers.missing(views)]
    check("the grid's games with no cover, by name: the covered, hand-set (a file gone too), hidden and tools out",
          listed == ["alpha uncovered", "Zeta Uncovered"], listed)
    check("the row's words: the count; Every game has a cover; what is missing to look them up",
          fill_covers.row_words(9, True, True) == ("9 games have no cover.", True)
          and fill_covers.row_words(1, True, True) == ("1 game has no cover.", True)
          and fill_covers.row_words(0, True, True) == ("Every game has a cover.", False)
          and fill_covers.row_words(3, False, True) == ("3 games have no cover. Add a SteamGridDB key above to "
                                                       "look them up.", False)
          and fill_covers.row_words(3, True, False) == ("3 games have no cover. Turn on Allow network lookups to "
                                                       "look them up.", False))
except Exception as exc:
    unreached("2", exc)


print("\n=== 3. the batch, on the fake, its waits recorded ===")


def batch(games, cache, stop_after: int | None = None, wait_answer: bool = True):
    pauses, waits, seen = [], [], {"found": [], "missed": [], "progress": []}

    def wait(seconds):
        waits.append(seconds)
        return wait_answer

    outcome = fill_covers.run(
        [(f"key-{name}", name) for name in games], FAKE_KEY, cache, pause=pauses.append, wait=wait,
        stopped=lambda: stop_after is not None and len(seen["progress"]) >= stop_after,
        progress=lambda index, name: seen["progress"].append(name),
        found=lambda game, path: seen["found"].append((game, path)),
        missed=lambda game, why: seen["missed"].append((game, why)))
    return outcome, pauses, waits, seen


try:
    fake.reset()
    fake.names.update({"Hollow Knight": [(1001, "Hollow Knight")], "Eden": [(2002, "Tiny Eden")],
                       "Celeste": [(3003, "Celeste")], "No Art Game": [(4004, "No Art Game")]})
    fake.grids.update({1001: True, 3003: True, 4004: False})
    cache = fresh_cache()
    outcome, pauses, waits, seen = batch(["Hollow Knight", "Eden", "No Art Game", "Celeste"], cache)
    check("each kind: found, not matched (the gate), matched with no tall cover",
          outcome.found == ["Hollow Knight", "Celeste"] and outcome.unmatched == ["Eden"]
          and outcome.no_image == ["No Art Game"] and not outcome.stopped, outcome)
    check("the covers are the first tall grid, kept where Find online keeps them, real pictures",
          [Path(p).name for _g, p in seen["found"]] == ["1001.jpg", "3003.jpg"]
          and all(Path(p).parent == Path(cache) / steamgriddb.ART_DIRNAME and Path(p).read_bytes() == IMAGE
                  for _g, p in seen["found"]))
    check("the tall static grids asked for, the 600x900 of Find online",
          all("dimensions=600x900&types=static" in u for u in fake.calls if "/grids/game/" in u))
    # Hollow Knight: search, grids, image; Eden: search; No Art Game: search, grids; Celeste: search, grids, image.
    check(f"paced: 9 requests, a gap of {rules.SGDB_REQUEST_GAP_SECONDS} s before each but the first",
          outcome.requests == 9 and len(fake.calls) == 9 and pauses == [rules.SGDB_REQUEST_GAP_SECONDS] * 8 and not waits,
          (outcome.requests, len(fake.calls), pauses))
    check("the misses cached as misses, the matches as matches",
          steamgriddb.known_game_id("Eden", cache) == "" and steamgriddb.known_game_id("Celeste", cache) == "3003")
    check("the last words", fill_covers.summary(outcome) == (
        "Found covers for 2 of 4. Not matched: Eden (name too unlike anything on SteamGridDB; try Find online from "
        "the game's menu). No tall cover on SteamGridDB for No Art Game; try Find online from the game's menu."),
        fill_covers.summary(outcome))
    calls = len(fake.calls)
    again, pauses, waits, seen = batch(["Hollow Knight", "Eden", "Celeste"], cache)
    check("a second run is cheap: the names cached, the images on disk -- no request at all",
          len(fake.calls) == calls and again.requests == 0 and again.found == ["Hollow Knight", "Celeste"]
          and again.unmatched == ["Eden"], (len(fake.calls) - calls, again))

    fake.reset()
    fake.names["Hollow Knight"] = [(1001, "Hollow Knight")]
    fake.grids[1001] = True
    fake.limits = ["7"]
    outcome, pauses, waits, seen = batch(["Hollow Knight"], fresh_cache())
    check("a 429: its Retry-After waited out, the request asked once more, the game found",
          waits == [7.0] and outcome.found == ["Hollow Knight"] and outcome.requests == 4 and not outcome.stopped,
          (waits, outcome))
    fake.limits = [None]
    outcome, pauses, waits, seen = batch(["Hollow Knight"], fresh_cache())
    check(f"one naming no wait: the backoff, {rules.SGDB_BACKOFF_SECONDS} s",
          waits == [float(rules.SGDB_BACKOFF_SECONDS)] and outcome.found == ["Hollow Knight"], waits)
    fake.names.update({"Celeste": [(3003, "Celeste")]})
    fake.grids[3003] = True
    fake.limits = ["1", "1"]
    cache = fresh_cache()
    outcome, pauses, waits, seen = batch(["Hollow Knight", "Celeste"], cache)
    check("a second 429 in a row stops the batch, nothing cached for the name it was asking about",
          outcome.stopped == fill_covers.SLOW_DOWN and outcome.done == 0 and waits == [1.0]
          and steamgriddb.known_game_id("Hollow Knight", cache) is None, (outcome, waits))
    check("and says so in the brief's words", fill_covers.summary(outcome) ==
          "SteamGridDB asked us to slow down; 0 done, try again later.", fill_covers.summary(outcome))
    fake.limits = [str(rules.SGDB_RETRY_AFTER_MAX_SECONDS + 60)]
    outcome, pauses, waits, seen = batch(["Hollow Knight"], fresh_cache())
    check(f"a Retry-After over {rules.SGDB_RETRY_AFTER_MAX_SECONDS} s stops it at once, without waiting",
          outcome.stopped == fill_covers.SLOW_DOWN and waits == [], (outcome, waits))
    fake.limits = []
    outcome, pauses, waits, seen = batch(["Hollow Knight", "Celeste"], fresh_cache(), stop_after=1)
    check("Cancel: the game under way finishes, the next is not begun",
          outcome.stopped == fill_covers.CANCELLED and outcome.found == ["Hollow Knight"]
          and seen["progress"] == ["Hollow Knight"], outcome)
    check("and its words", fill_covers.summary(outcome) == "Stopped after 1 of 2. Covers found for 1.",
          fill_covers.summary(outcome))
    fake.limits = ["20"]
    outcome, pauses, waits, seen = batch(["Hollow Knight", "Celeste"], fresh_cache(), wait_answer=False)
    check("Cancel during a wait: the wait ends at once, the batch stops", outcome.stopped == fill_covers.CANCELLED
          and waits == [20.0] and outcome.done == 0, outcome)
    fake.limits = []
    fake.down = True
    cache = fresh_cache()
    outcome, pauses, waits, seen = batch(["Hollow Knight", "Celeste"], cache)
    check("SteamGridDB unreachable stops it -- no miss cached for every game left",
          outcome.stopped == fill_covers.UNREACHABLE and outcome.done == 0 and names_in(cache) == {}
          and fill_covers.summary(outcome) == "SteamGridDB could not be reached; 0 done, try again later.", outcome)
    fake.down, fake.refuse = False, True
    outcome, pauses, waits, seen = batch(["Hollow Knight"], fresh_cache())
    check("a refused key stops it, and says where to look", outcome.stopped == fill_covers.KEY_REFUSED
          and fill_covers.summary(outcome) == "SteamGridDB refused the key; check it with Test.", outcome)
    fake.refuse = False
    many = fill_covers.Outcome(total=8, found=["F"], unmatched=[f"Game {n}" for n in range(7)])
    check(f"the words name {rules.FILL_COVERS_NAMED_MAX} a kind, then how many more",
          "Not matched: Game 0, Game 1, Game 2, Game 3, Game 4 and 2 more (" in fill_covers.summary(many),
          fill_covers.summary(many))
except Exception as exc:
    unreached("3", exc)


print("\n=== 4. in the window, on a copy with planted games ===")
window = None
try:
    from presentation import ui_fill_covers, ui_window
    from presentation.ui_settings import SettingsDialog

    window = ui_window.MainWindow()
    window.resize(1280, 820)
    window.show()
    settle(1.5)
    window._stop_watch()
    store = window.overrides
    real_before = sorted(v.key for v in window.missing_covers())
    check("the copy of the user's library: every game in the grid has a cover (the four without are tools)",
          real_before == [], real_before)

    banner = Path(box.folder) / "art" / "banner.jpg"
    banner.write_bytes(IMAGE)
    planted = {name: entry(name) for name in ("Hollow Knight", "Eden", "Celeste", "Banner Kept", "Hand Picked")}
    window.entries.extend(planted.values())
    window.reload_views()
    keys = {name: e.identity_key for name, e in planted.items()}
    store.update(keys["Banner Kept"], banner=str(banner))
    store.update(keys["Hand Picked"], cover=str(Path(box.folder) / "art" / "covered.jpg"))
    window.reload_views()
    listed = [v.display_name for v in window.missing_covers()]
    check("planted: four without a cover in the list; the hand-picked one not in it",
          listed == ["Banner Kept", "Celeste", "Eden", "Hollow Knight"], listed)

    settings = SettingsDialog(dict(window.config), window, store=window.overrides, covers=window)
    settings.show()
    settle(0.4)
    check("Settings, Artwork and the internet: Missing covers, its count, the button off with the network off",
          settings.fill_covers_button is not None and settings.fill_covers_button.text() == "Fill missing covers..."
          and settings.covers_status.text() == "4 games have no cover. Turn on Allow network lookups to look them up."
          and not settings.fill_covers_button.isEnabled(), settings.covers_status.text())
    settings.network_box.setChecked(True)
    check("network lookups on (in this window, not yet saved): the button on",
          settings.fill_covers_button.isEnabled() and settings.covers_status.text() == "4 games have no cover.")
    settings.sgdb_key.setText("")
    check("no key: off again, and the row says to add one", not settings.fill_covers_button.isEnabled()
          and settings.covers_status.text().endswith("Add a SteamGridDB key above to look them up."))
    settings.sgdb_key.setText(FAKE_KEY)
    check("a SettingsDialog opened without the window has no such row", SettingsDialog(
        dict(window.config), window, store=window.overrides).fill_covers_button is None)

    fake.reset()
    fake.names.update({"Hollow Knight": [(1001, "Hollow Knight")], "Eden": [(2002, "Tiny Eden")],
                       "Celeste": [(3003, "Celeste")], "Banner Kept": [(5005, "Banner Kept")]})
    fake.grids.update({1001: True, 3003: True, 5005: True})
    snapshots_before = {s.stamp for s in backups.list_snapshots()}
    real_start = window.start_scan
    scans: list[tuple[bool, dict]] = []

    def recording_scan(**kwargs):
        scans.append((window._filling, kwargs))
        return real_start(**kwargs) if window._filling else True  # held, or recorded: no real scan in this suite

    window.start_scan = recording_scan
    seen: dict = {}

    def drive():
        dialog = QApplication.activeModalWidget()
        seen["dialog"] = dialog
        if not isinstance(dialog, ui_fill_covers.FillCoversDialog):
            return
        seen["names"] = [dialog.list.item(i).text() for i in range(dialog.list.count())]
        seen["focus"] = QApplication.focusWidget() is dialog.look_button
        dialog.look_button.click()
        seen["held"] = window.start_scan(trigger="manual")
        began = time.monotonic()

        def wait_end():
            if dialog.outcome is None and time.monotonic() - began < 30:
                QTimer.singleShot(100, wait_end)
                return
            seen["status"] = dialog.status.text()
            seen["marks"] = [dialog.list.item(i).text() for i in range(dialog.list.count())]
            seen["button"] = dialog.cancel_button.text()
            seen["outcome"] = dialog.outcome
            QTimer.singleShot(0, dialog.cancel_button.click)

        QTimer.singleShot(100, wait_end)

    QTimer.singleShot(300, drive)
    watchdog_done = {"over": False}

    def watchdog():
        if not watchdog_done["over"]:
            dialog = QApplication.activeModalWidget()
            if isinstance(dialog, ui_fill_covers.FillCoversDialog):
                print("   (the watchdog closed the dialog)")
                dialog.done(0)

    QTimer.singleShot(45000, watchdog)
    settings._fill_covers()
    watchdog_done["over"] = True
    outcome = seen.get("outcome")
    check("the dialog lists them by name, Look them up in focus", seen.get("names") == [
        "·  Banner Kept", "·  Celeste", "·  Eden", "·  Hollow Knight"] and seen.get("focus"), seen.get("names"))
    check("each line marked as it is answered",
          seen.get("marks") == ["✓  Banner Kept", "✓  Celeste", "✕  Eden — no close match", "✓  Hollow Knight"],
          seen.get("marks"))
    new = [s for s in backups.list_snapshots() if s.stamp not in snapshots_before]
    held = (new[0].stamp if new else backups.list_snapshots()[0].stamp)
    check("a backup first, named in the last words, which say how to undo it",
          outcome is not None and seen.get("status", "").startswith("Found covers for 3 of 4. Not matched: Eden (")
          and f"A backup was taken first ({held})" in seen.get("status", "") and "Restore..." in seen.get("status", ""),
          seen.get("status"))
    records = {name: store.get(key) for name, key in keys.items()}
    art_dir = Path(paths.cache_dir()) / steamgriddb.ART_DIRNAME
    check("the covers written in the cover slot, from the copy's own cache",
          records["Hollow Knight"].get("cover") == str(art_dir / "1001.jpg")
          and records["Celeste"].get("cover") == str(art_dir / "3003.jpg")
          and records["Banner Kept"].get("cover") == str(art_dir / "5005.jpg") and not records["Eden"].get("cover"),
          {n: r.get("cover") for n, r in records.items()})
    check("the banner untouched, the hand-picked cover kept",
          records["Banner Kept"].get("banner") == str(banner)
          and records["Hand Picked"].get("cover") == str(Path(box.folder) / "art" / "covered.jpg"))
    settle(rules.FILL_COVERS_REFRESH_MS / 1000 + 0.3)
    shown = {v.display_name: v.cover_source for v in window.library.views if v.display_name in planted}
    check("the grid redrawn: its tiles draw the covers found",
          shown.get("Hollow Knight") == str(art_dir / "1001.jpg") and shown.get("Eden") == ""
          and window.missing_covers() and [v.display_name for v in window.missing_covers()] == ["Eden"], shown)
    check("a scan asked for meanwhile is held back, and runs once the dialog is closed",
          seen.get("held") is False and scans[:1] == [(True, {"trigger": "manual"})]
          and scans[1:] == [(False, {"quiet": False, "background": False, "trigger": "manual"})], scans)
    check("the miss cached in the copy's cache, never the user's",
          steamgriddb.known_game_id("Eden", str(paths.cache_dir())) == ""
          and Path(paths.cache_dir()).resolve() != (PROJECT / "data" / "cache").resolve())
    settings._update_covers_row()
    check("the row counts again: one game left", settings.covers_status.text() == "1 game has no cover.",
          settings.covers_status.text())

    # Cancel and Escape while it runs, and a scan under way waited for -- the dialog on its own, a stand-in host.
    class Host:
        def __init__(self, scanning: int = 0) -> None:
            self.scanning = scanning
            self.written: list[str] = []
            self.worker = None

        def scan_running(self) -> bool:
            self.scanning -= 1
            return self.scanning >= 0

        def fill_backup(self) -> str:
            return "a-backup"

        def cover_found(self, game: str, path: str) -> None:
            self.written.append(game)

        def track_fill(self, worker) -> None:
            self.worker = worker

    fake.reset()
    names = [f"Planted {n}" for n in range(6)]
    for n, name in enumerate(names):
        fake.names[name] = [(7000 + n, name)]
        fake.grids[7000 + n] = True
    host = Host()
    dialog = ui_fill_covers.FillCoversDialog([(f"k{n}", name) for n, name in enumerate(names)], FAKE_KEY, host, 1.0,
                                             parent=window)
    dialog.show()
    settle(0.2)
    dialog.look()
    settle(0.3)
    dialog.reject()  # Escape
    escaped_open = dialog.isVisible() and dialog.cancel_button.text() == ui_fill_covers.STOPPING
    began = time.monotonic()
    while dialog.outcome is None and time.monotonic() - began < 20:
        settle(0.1)
    check("Escape while it runs is Cancel: the dialog stays, says Stopping..., the game under way finishes",
          escaped_open and dialog.outcome is not None and dialog.outcome.stopped == fill_covers.CANCELLED
          and 1 <= dialog.outcome.done < len(names) and host.written == [f"k{n}" for n in range(dialog.outcome.done)],
          (escaped_open, dialog.outcome))
    check("and then Close closes it", dialog.cancel_button.text() == ui_fill_covers.CLOSE
          and (dialog.reject() or True) and not dialog.isVisible())

    fake.reset()
    fake.names["Planted 0"] = [(7000, "Planted 0")]
    fake.grids[7000] = True
    host = Host(scanning=3)
    dialog = ui_fill_covers.FillCoversDialog([("k0", "Planted 0")], FAKE_KEY, host, 1.0, parent=window)
    dialog.show()
    dialog.look()
    waiting = dialog.status.text()
    began = time.monotonic()
    while dialog.outcome is None and time.monotonic() - began < 20:
        settle(0.1)
    check("a scan under way is waited for, then the lookup runs", waiting == ui_fill_covers.WAITING
          and dialog.outcome is not None and dialog.outcome.found == ["Planted 0"], (waiting, dialog.outcome))
    dialog.reject()

    class NoBackup(Host):
        def fill_backup(self) -> str:
            return ""

    host = NoBackup()
    calls = len(fake.calls)
    dialog = ui_fill_covers.FillCoversDialog([("k0", "Planted 0")], FAKE_KEY, host, 1.0, parent=window)
    dialog.show()
    dialog.look()
    settle(0.3)
    check("no backup, no lookup: nothing asked, and it says why", dialog.status.text() == ui_fill_covers.NO_BACKUP
          and dialog.worker is None and len(fake.calls) == calls)
    dialog.reject()
    settings.reject()

    # The undo: the backup restored, as Settings' Restore... does it.
    snap = next(s for s in backups.list_snapshots() if s.stamp == held)
    ok, message = backups.restore(snap)
    window.reload_after_restore(message)
    settle(0.5)
    restored = {name: window.overrides.get(key).get("cover") for name, key in keys.items()}
    check("the restore brings the library back: no cover the batch wrote, the hand-picked one kept",
          ok and not restored["Hollow Knight"] and not restored["Celeste"] and not restored["Banner Kept"]
          and restored["Hand Picked"] == str(Path(box.folder) / "art" / "covered.jpg"), (ok, message, restored))
    lines = "\n".join(logged)
    check("the key never in the log; the batch's requests logged by count",
          FAKE_KEY not in lines and "fill covers: 3 of 4 found, 1 not matched, 0 with no tall cover, " in lines
          and "request(s)" in lines)
    check("the real key either: the copy's config held a stand-in", (lambda real: not real or real not in lines)(
        str(json.loads((PROJECT / "data" / "config.json").read_text(encoding="utf-8")).get("steamgriddb_key") or "")))
except Exception as exc:
    unreached("4", exc)
finally:
    if window is not None:
        window.start_scan = window.__class__.start_scan.__get__(window)
        window._shut_down = True
        try:
            window.overrides.close()
        except Exception as exc:  # noqa: BLE001 -- the suite's end, said
            print(f"   (closing the store: {exc})")


print("\n=== 5. the documents, the layers ===")
try:
    def doc(name: str) -> str:
        return (PROJECT / name).read_text(encoding="utf-8").replace("\r\n", "\n")

    claude = doc("CLAUDE.md")
    check("CLAUDE.md: the row, the three modules in the layout, the batch in endpoint 5's paragraph, under its size",
          "| 105 |" in claude and "cover_fill_worker.py" in claude and "fill_covers.py" in claude
          and "ui_fill_covers.py" in claude and "Fill missing covers" in claude
          and len(claude.encode("utf-8")) < 116581, len(claude.encode("utf-8")))
    arch = doc("docs/ARHITECTURA.md")
    check("ARHITECTURA: the batch's path (5.9) and the three modules in the maps",
          "### 5.9" in arch and "`cover_fill_worker.py`" in arch and "`fill_covers.py`" in arch
          and "`ui_fill_covers.py`" in arch)
    readme = doc("docs/CITESTE-MA.md")
    check("CITESTE-MA: the button in the friends' words, still on one page", "**Fill missing covers...**" in readme
          and len(readme.splitlines()) <= 110, len(readme.splitlines()))
    page = doc("docs/explicatii/faza-105.md")
    check("the explanation page, in its shape, with the five words", all(w in page for w in (
        "## Ce s-a construit", "## De ce contează", "## Cum funcționează", "## Cinci cuvinte", "## Trei întrebări",
        "## Ce nu poate face", "*rate limiting*", "*idempotent batch*", "*match threshold*", "*negative cache*",
        "*snapshot as undo*")) and "faza 105" in doc("docs/explicatii/CITESTE-MA.md"))
    check("ISTORIC has the phase's notes", "## Phase 105 notes" in sources.build_log())
    layers = subprocess.run([sys.executable, str(PROJECT / "tests" / "check_layers.py")], capture_output=True,
                            text=True, encoding="utf-8", errors="replace")
    check("no import points up a layer; sqlite3 only in data_access/", layers.returncode == 0, layers.stdout[-300:])
    check("nothing in this suite went past the fake SteamGridDB", outside == [], outside)
except Exception as exc:
    unreached("5", exc)

print("\n=== 6. the real library is exactly as it was found ===")
changed = box.finish()
check("config.json, the library database and the Run key's value are unchanged", not changed, changed)
check("and the user's own SteamGridDB cache: the names file byte for byte, every picture as it was",
      real_art() == real_art_before)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
