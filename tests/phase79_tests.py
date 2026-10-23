"""Phase 79: is a newer version out (GitHub, once a day, installed copies only) -- and, on a first
run, a second question: a SteamGridDB key.

The version comparison; GitHub's answers as they really came on 11 October (tests/fixtures) and
every way one can go wrong -- no release yet, a draft, a tag that is not a version, not JSON,
no answer, GitHub's limit -- with the request itself (the address, the headers, a GET); the
kept answer and the once-a-day rule (a few hours after no answer); who asks -- a copy run from
source never, an installed one (stood in) a few seconds after its window appears, on another
thread, with the network on only; the message card, once; Settings' Updates row in each state,
and its button opening the one fixed page, with the mouse and with the pad; the key question --
after the folders, the first scan already running behind it, its page opened, its Test, its key
written alone and never logged, skipped and closed writing nothing, on a couch the pad starting on
Skip -- and the key kept out of the diagnostics bundle; the documents, and the internet still
only in web/.

On a throwaway copy of the data. The network is blocked; GitHub's answers are handed in.
"""
import json
import re
import sys
import threading
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import test_sandbox

box = test_sandbox.start()
SANDBOX = box.folder
CONFIG = SANDBOX / "config.json"

attempts: list[str] = []


def no_network(request, *args, **kwargs):
    attempts.append(getattr(request, "full_url", str(request)))
    raise OSError("the network is blocked in this suite")


urllib.request.urlopen = no_network

import logging

lines: list[str] = []


class Keep(logging.Handler):
    def emit(self, record):
        lines.append(f"{record.name}: {record.getMessage()}")


logging.basicConfig(level=logging.CRITICAL)
logging.getLogger().addHandler(Keep(level=logging.INFO))
logging.getLogger().setLevel(logging.INFO)

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)

from adapters import controller
from logic import diagnostics, first_run
from presentation import ui_first_run, ui_settings, ui_window
from shared import paths, rules, version

try:
    from web import updates
    from web import steamgriddb
except ImportError:  # the code before this phase has no web/updates.py
    updates = steamgriddb = None
REAL_GET = updates._get if updates else None  # stood in for below, put back for the request's check

passed = failed = 0
FIXTURES = PROJECT / "tests" / "fixtures"
RELEASE = json.loads((FIXTURES / "github_release_latest_2026-10-11.json").read_text(encoding="utf-8"))
NEWER = dict(RELEASE, tag_name="v9.0.0", name="9.0.0", html_url="https://evil.example/not-this")
UTC = timezone.utc


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"   PASS  {name}")
    else:
        failed += 1
        print(f"   FAIL  {name}   {detail}")


def unreached(section: str, exc: Exception):
    check(f"section {section} runs to its end on this code", False, repr(exc))


def settle(seconds: float = 0.3) -> None:
    loop = QEventLoop()
    QTimer.singleShot(int(seconds * 1000), loop.quit)
    loop.exec()


def modal():
    return QApplication.activeModalWidget()


def run(steps, notes: dict, limit_ms: int = 60_000) -> None:
    """Each step after the last, a step tried again until it says it is done; a watchdog closes
    whatever is still open if the chain gets stuck (a dialog runs its own loop inside it)."""
    position = [0]
    loop = QEventLoop()
    # Once this chain's loop has ended its watchdog stands down: left armed, it fired a minute
    # later into the next window and closed its first-run question (found in Phase 86, when the
    # scans grew by the wishlist's few seconds and that minute fell on the TV window's question).
    ended = [False]

    def advance():
        if position[0] >= len(steps):
            loop.quit()
            return
        QTimer.singleShot(200, advance)
        try:
            if steps[position[0]]():
                position[0] += 1
        except Exception as exc:  # noqa: BLE001
            notes.setdefault("errors", []).append(f"step {position[0]}: {exc!r}")
            position[0] += 1

    def watchdog():
        if ended[0]:
            return
        for widget in (QApplication.activePopupWidget(), QApplication.activeModalWidget()):
            if widget is not None:
                widget.close()
        notes["watchdog"] = True
        loop.quit()

    QTimer.singleShot(200, advance)
    QTimer.singleShot(limit_ms, watchdog)
    loop.exec()
    ended[0] = True
    settle(0.3)


calls: list[tuple[str, str]] = []  # (address asked, thread that asked)


def github(*replies):
    """A stand-in for updates._get answering these, in turn (the last one again after that)."""
    queue = list(replies)

    def answer(url):
        calls.append((url, threading.current_thread().name))
        reply = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(reply, dict):
            return 200, json.dumps(reply).encode("utf-8")
        return reply
    return answer


def close(window) -> None:
    while window.worker is not None and window.worker.isRunning():
        settle(0.2)
    window.close()
    settle(0.3)
    window.overrides.close()


print("=== 1. the version ===")
try:
    cases = [("1.2.0", "1.1.0", True), ("1.10.0", "1.9.0", True), ("v1.3.0", "1.2.0", True),
             ("1.2", "1.1.9", True), ("2.0.0", "1.99.99", True), ("1.2.0", "1.2.0", False),
             ("v1.2.0", "1.2.0", False), ("1.1.9", "1.2.0", False), ("1.3.0-beta", "1.2.0", False),
             ("nightly", "1.2.0", False), ("", "1.2.0", False), ("1.3.0", "not a version", False)]
    wrong = [(a, b) for a, b, expected in cases if version.is_newer(a, b) != expected]
    check(f"is a version newer: {len(cases)} pairs, compared as numbers, never as text", not wrong, wrong)
    check(f"this one is {version.APP_VERSION}: raised for the update check, 1.2.0 or later",
          (version.parse(version.APP_VERSION) or (0,)) >= (1, 2, 0))
    check("with no second version named, it is this copy's -- read when asked",
          version.is_newer("99.0.0") and not version.is_newer(version.APP_VERSION))
except Exception as exc:
    unreached("1", exc)

print("\n=== 2. GitHub's answers, as they came ===")
try:
    now = datetime(2026, 10, 11, 20, 0, tzinfo=UTC)
    real = updates.read(RELEASE, now)
    check("a real release (rsms/inter, kept from 11 October): its tag read as a version, its day and name",
          real.reached and real.latest == "4.1.0" and real.title == "4.1"
          and real.published == datetime(2024, 11, 16, 0, 27, 7, tzinfo=UTC), real)
    meta = json.loads((FIXTURES / "github_no_release_2026-10-11.meta.json").read_text(encoding="utf-8"))
    check("our repository with no release yet answered 404, kept as it came",
          meta["status"] == 404 and meta["url"] == rules.UPDATE_LATEST_URL, meta)
    updates._get = github((404, None))
    none_yet = updates.fetch(now)
    check("404 is an answer -- no release yet, nothing newer -- not a failure",
          none_yet.reached and none_yet.latest is None and not none_yet.newer, none_yet)
    for label, payload in (("a draft", dict(NEWER, draft=True)), ("a pre-release", dict(NEWER, prerelease=True)),
                           ("a tag that is not a version", dict(NEWER, tag_name="nightly"))):
        answer = updates.read(payload, now)
        check(f"{label} is never offered", answer.reached and answer.latest is None and not answer.newer, answer)
    for label, reply in (("not JSON", (200, b"<html>oops</html>")), ("no answer at all", (None, None)),
                         ("GitHub's limit (403)", (403, None)), ("a server error (500)", (500, None))):
        updates._get = github(reply)
        answer = updates.fetch(now)
        check(f"{label}: not reached, asked again in a few hours", not answer.reached and answer.latest is None)
    newer = updates.read(NEWER, now)
    check("a newer release is newer than this copy", newer.newer and newer.latest == "9.0.0")
    check("the answer's own address is never kept: there is nowhere to take it from",
          "evil" not in json.dumps(newer.to_dict()) and not hasattr(newer, "html_url"))

    seen = []

    def recorder(request, timeout=None):
        seen.append((request, timeout))
        raise urllib.error.URLError("offline")

    urllib.request.urlopen = recorder
    updates._get = REAL_GET
    reply = updates._get(rules.UPDATE_LATEST_URL)
    request, timeout = seen[0]
    check("the one request: a GET of the public repository's latest release on api.github.com",
          request.full_url == "https://api.github.com/repos/GreenYRO/game-launcher-releases/releases/latest"
          and request.get_method() == "GET" and request.data is None, request.full_url)
    check("anonymous: a plain name for the program, GitHub's format, no key and no account",
          request.get_header("User-agent") == rules.UPDATE_USER_AGENT
          and request.get_header("Accept") == "application/vnd.github+json"
          and not request.get_header("Authorization") and "version" not in rules.UPDATE_USER_AGENT.split("(")[0],
          request.header_items())
    check(f"given up after {rules.UPDATE_TIMEOUT_SECONDS} s; offline is no answer", timeout ==
          rules.UPDATE_TIMEOUT_SECONDS and reply == (None, None))
    urllib.request.urlopen = no_network
except Exception as exc:
    urllib.request.urlopen = no_network
    unreached("2", exc)

print("\n=== 3. once a day ===")
try:
    base = datetime(2026, 10, 11, 12, 0, tzinfo=UTC)
    kept_in = SANDBOX / "cache-79"
    calls.clear()
    updates._get = github(NEWER)
    first, asked = updates.check(kept_in, base)
    check("the first time it asks, and says 9.0.0 is out", asked and len(calls) == 1 and first.newer)
    kept = json.loads((kept_in / rules.UPDATE_CACHE_FILE).read_text(encoding="utf-8"))
    # Since Phase 106 also the release's notes, its page's body: Settings shows them before the update.
    check("the answer kept: when, reached, which version, its day, name and notes -- and nothing else",
          kept == first.to_dict() and set(kept) == {"checked_at", "reached", "latest", "published", "title", "notes"}
          and kept["notes"].startswith("## Changes"), sorted(kept))
    again, asked = updates.check(kept_in, base + timedelta(hours=23))
    check("23 hours later: not asked again, the kept answer used", not asked and len(calls) == 1
          and again.latest == "9.0.0")
    _, asked = updates.check(kept_in, base + timedelta(hours=25))
    check("a day later: asked again", asked and len(calls) == 2)
    lost_in = SANDBOX / "cache-79-offline"
    updates._get = github((None, None))
    calls.clear()
    _, asked = updates.check(lost_in, base)
    _, five = updates.check(lost_in, base + timedelta(hours=5))
    _, seven = updates.check(lost_in, base + timedelta(hours=7))
    check(f"no answer: asked again after {rules.UPDATE_RETRY_HOURS} hours, not before",
          asked and not five and seven and len(calls) == 2, calls)
    (lost_in / rules.UPDATE_CACHE_FILE).write_text("not json", encoding="utf-8")
    _, asked = updates.check(lost_in, base + timedelta(hours=7, minutes=1))
    check("a kept answer that cannot be read: asked again", asked)
    real_version = version.APP_VERSION
    version.APP_VERSION = "9.0.0"
    after_update = updates.last(kept_in)
    newer_then = after_update.newer  # asked while this copy is 9.0.0, before the number is put back
    version.APP_VERSION = real_version
    check("after updating to it, the same kept answer says nothing newer", after_update.latest == "9.0.0"
          and not newer_then and after_update.newer, (after_update, newer_then))
except Exception as exc:
    unreached("3", exc)

print("\n=== 4. who asks: never from source, an installed copy a few seconds after it opens ===")
messages: list[str] = []
try:
    frozen = paths.FROZEN
    check("run from source: never", updates.should_check({"allow_network": True}) == (False, "run from source"))
    paths.FROZEN = True
    check("installed, with network lookups off: never",
          updates.should_check({"allow_network": False}) == (False, "network lookups are off"))
    check("installed, network on: yes", updates.should_check({"allow_network": True}) == (True, ""))
    paths.FROZEN = frozen

    (SANDBOX / "cache" / rules.UPDATE_CACHE_FILE).unlink(missing_ok=True)
    calls.clear()
    updates._get = github(NEWER)
    window = ui_window.MainWindow()
    window.resize(1280, 820)
    window.show()
    window.config["allow_network"] = True  # in memory: an installed copy's default
    settle(rules.UPDATE_CHECK_DELAY_MS / 1000 + 2)
    check("this PC's copy, run from source: GitHub never asked", not calls and window.update_worker is None
          and any("update check: not asked (run from source)" in line for line in lines), calls)
    close(window)

    window = ui_window.MainWindow()
    window.resize(1280, 820)
    window.statusBar().messageChanged.connect(lambda text: messages.append(text))
    window.show()
    settle(0.5)
    paths.FROZEN = True  # an installed copy, from here: after the window is up, before its check
    window.config["allow_network"] = True
    settle(rules.UPDATE_CHECK_DELAY_MS / 1000 + 2)
    while window.update_worker is not None and window.update_worker.isRunning():
        settle(0.2)
    settle(0.5)
    check("an installed copy asks, once, a few seconds after its window appears",
          len(calls) == 1 and calls[0][0] == rules.UPDATE_LATEST_URL, calls)
    check("on a thread of its own, never the window's", calls and calls[0][1] != threading.main_thread().name, calls)
    check("the window holds the answer", window.update_answer is not None and window.update_answer.latest == "9.0.0")
    out = [m for m in messages if "9.0.0 is out" in m]
    check("a message card says so, and where to get it",
          out == [f"{version.APP_NAME} 9.0.0 is out. Settings, under About, has the download page."], out)
    close(window)

    messages.clear()
    window = ui_window.MainWindow()
    window.statusBar().messageChanged.connect(lambda text: messages.append(text))
    window.show()
    window.config["allow_network"] = True
    window._check_for_updates()
    while window.update_worker is not None and window.update_worker.isRunning():
        settle(0.2)
    settle(0.5)
    check("started again the same day: GitHub not asked, and the card not shown again",
          len(calls) == 1 and not any("is out" in m for m in messages), (calls, messages))
    check("though the window still knows -- Settings will say", window.update_answer is not None
          and window.update_answer.newer)
    window.config["allow_network"] = False
    (SANDBOX / "cache" / rules.UPDATE_CACHE_FILE).unlink(missing_ok=True)
    window._check_for_updates()
    settle(0.5)
    check("with network lookups off: not asked", len(calls) == 1
          and any("update check: not asked (network lookups are off)" in line for line in lines))
    close(window)
except Exception as exc:
    unreached("4", exc)
finally:
    paths.FROZEN = False

print("\n=== 5. Settings: the Updates row ===")
opened: list[str] = []
try:
    now = datetime.now(UTC)
    words = {
        "from source": ui_settings.update_text(None, False, "run from source"),
        "network off": ui_settings.update_text(None, False, "network lookups are off"),
        "not yet": ui_settings.update_text(None, True, ""),
        "newer": ui_settings.update_text(updates.Answer(now, True, "9.0.0", now - timedelta(days=1), "9.0.0"), True, ""),
        "newest": ui_settings.update_text(updates.Answer(now, True, version.APP_VERSION), True, ""),
        "none yet": ui_settings.update_text(updates.Answer(now, True, None), True, ""),
        "no answer": ui_settings.update_text(updates.Answer(now, False), True, ""),
    }
    for state, text in words.items():
        print(f"         {state}: {text}")
    check("each state in its own words",
          "runs from source" in words["from source"] and "Allow network lookups is off" in words["network off"]
          and "Not checked yet" in words["not yet"] and words["newer"].startswith("Version 9.0.0 is out, published")
          and words["newest"].startswith("You have the newest version. Checked today at")
          and words["none yet"] == words["newest"] and words["no answer"].startswith("GitHub could not be reached"))

    ui_settings.open_in_browser = lambda url: opened.append(url) or True
    window = ui_window.MainWindow()
    dialog = ui_settings.SettingsDialog(window.config, window, store=window.overrides)
    check("from source, the row says this copy never asks", "runs from source" in dialog.update_row.hint.text())
    dialog.update_page.click()
    check("its button opens the one page the installers are on, in the browser",
          opened == ["https://github.com/GreenYRO/game-launcher-releases/releases/latest"]
          and opened[0] == rules.UPDATE_PAGE_URL, opened)
    dialog.reject()
    paths.FROZEN = True
    updates._keep(paths.cache_dir(), updates.Answer(now, True, "9.0.0", None, "9.0.0"))
    dialog = ui_settings.SettingsDialog(dict(window.config, allow_network=True), window, store=window.overrides)
    check("an installed copy that knows of 9.0.0 says so, beside its own version",
          dialog.update_row.hint.text().startswith("Version 9.0.0 is out")
          and dialog.version_row.title.text() == f"{version.APP_NAME} {version.APP_VERSION}", dialog.update_row.hint.text())
    dialog.show()
    settle(0.3)
    dialog.update_page.setFocus()
    window._drive_dialog(dialog, controller.ACTIVATE)
    settle(0.2)
    check("the pad's A on the button opens the same page, never one from GitHub's answer",
          opened[1:] == [rules.UPDATE_PAGE_URL], opened)
    dialog.reject()
    paths.FROZEN = False
    (SANDBOX / "cache" / rules.UPDATE_CACHE_FILE).unlink(missing_ok=True)
    close(window)
except Exception as exc:
    unreached("5", exc)
finally:
    paths.FROZEN = False

print("\n=== 6. the first run's second question: a SteamGridDB key ===")
real_candidates, real_xbox = first_run.candidates, first_run.xbox_found
tested: list[str] = []
KEY = "0123456789abcdef0123456789abcdef"


def without_version(written):
    """A first run's config.json less the version that ran, which its answer carries since Phase 99."""
    if not isinstance(written, dict):
        return written
    return {k: v for k, v in written.items() if k != "version_seen"}


try:
    first_run.candidates = lambda roots=None: []
    first_run.xbox_found = lambda roots=None: False
    steamgriddb.check_key = lambda key: (tested.append(key) or (True, "Key works."))
    opened.clear()

    CONFIG.unlink()
    window = ui_window.MainWindow()
    window.resize(1280, 820)
    notes: dict = {}

    def on_key():
        dialog = modal()
        if not isinstance(dialog, ui_first_run.KeyDialog):
            return False
        notes.update(title=dialog.windowTitle(), field=dialog.focusWidget() is dialog.key,
                     empty_save=dialog.save_button.isEnabled(), scanning=window.worker is not None,
                     folders_written=json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.is_file() else None)
        dialog.open_button.click()
        dialog.key.setText(f"  {KEY}  ")
        notes.update(save=dialog.save_button.isEnabled())
        dialog.test_button.click()
        notes.update(status=dialog.status.text())
        dialog.save_button.click()
        return True

    run([lambda: window.show() or True,
         lambda: isinstance(modal(), ui_first_run.FirstRunDialog) and (modal().continue_button.click() or True),
         on_key, lambda: notes.update(closed=modal() is None) or True], notes)
    saved = json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.is_file() else None
    check("after the folders comes the key question", notes.get("title") == ui_first_run.KEY_TITLE, notes)
    check("by then the folders are written and the first scan is running behind it",
          without_version(notes.get("folders_written")) == {"roots": [], "enable_xbox": False} and notes.get("scanning"),
          notes)
    check("at a desk it opens on the field, ready for a paste; Save waits for a key",
          notes.get("field") and notes.get("empty_save") is False and notes.get("save") is True, notes)
    check("Open steamgriddb.com opens SteamGridDB's own page for keys, in the browser",
          opened == [rules.SGDB_KEY_PAGE_URL] and opened[0].startswith("https://www.steamgriddb.com/profile/"), opened)
    check("Test asks SteamGridDB with the key as pasted, less its spaces, and says so",
          tested == [KEY] and notes.get("status") == "✓  Key works.", (tested, notes.get("status")))
    check("Save key: written beside the answer to the folders, the folders kept",
          notes.get("closed") and without_version(saved) == {"roots": [], "enable_xbox": False, "steamgriddb_key": KEY},
          saved)
    check("and in use at once: the window and the game page have it",
          window.config.get("steamgriddb_key") == KEY and window.detail.steamgriddb_key == KEY)
    check("the log says a key was added -- and never the key",
          any("first run: a SteamGridDB key was added" in line for line in lines)
          and not any(KEY in line for line in lines))
    close(window)

    zipped = SANDBOX / "diagnostics-79.zip"
    store = test_sandbox.library()
    diagnostics.write(zipped, store)
    store.close()
    with zipfile.ZipFile(zipped) as bundle:
        everything = b"".join(bundle.read(name) for name in bundle.namelist())
        settings = json.loads(bundle.read("config.json"))
    check("the diagnostics bundle carries no key: not in its settings, not anywhere",
          KEY.encode() not in everything and "steamgriddb_key" not in settings, sorted(settings)[:6])

    for how in ("Skip", "closed"):
        CONFIG.unlink()
        window = ui_window.MainWindow()
        notes = {}
        run([lambda: window.show() or True,
             lambda: isinstance(modal(), ui_first_run.FirstRunDialog) and (modal().continue_button.click() or True),
             lambda: isinstance(modal(), ui_first_run.KeyDialog) and (
                 modal().key.setText("typed, then thought better of it") or
                 (modal().skip_button.click() if how == "Skip" else modal().reject()) or True),
             lambda: notes.update(closed=modal() is None) or True], notes)
        saved = json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.is_file() else None
        check(f"{how}: nothing written for the key, the folders' answer kept",
              notes.get("closed") and without_version(saved) == {"roots": [], "enable_xbox": False}, saved)
        close(window)

    CONFIG.unlink()
    window = ui_window.MainWindow()
    window.set_tv_mode(True)
    notes = {}

    def press(name):
        window.pads.action.emit(name)

    run([lambda: isinstance(modal(), ui_first_run.FirstRunDialog) and (modal().continue_button.click() or True),
         lambda: isinstance(modal(), ui_first_run.KeyDialog),
         lambda: notes.update(scale=modal().scale, on_skip=modal().focusWidget() is modal().skip_button) or True,
         lambda: press(controller.DOWN) or True,
         lambda: notes.update(moved=modal().focusWidget() is not modal().skip_button) or True,
         lambda: press(controller.UP) or True,
         lambda: notes.update(back=modal().focusWidget() is modal().skip_button) or True,
         lambda: press(controller.ACTIVATE) or True,
         lambda: notes.update(closed=modal() is None) or True], notes)
    saved = json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.is_file() else None
    check("on a couch, at TV size, the pad starts on Skip -- nothing can be typed there",
          notes.get("scale") == float(ui_settings.ui_rules.TV_SCALE_DEFAULT) and notes.get("on_skip"), notes)
    check("down and up move between its buttons; A on Skip skips",
          notes.get("moved") and notes.get("back") and notes.get("closed")
          and without_version(saved) == {"roots": [], "enable_xbox": False}, (notes, saved))
    check("no watchdog and no error", not notes.get("watchdog") and not notes.get("errors"), notes.get("errors"))
    close(window)
    installer_test = (PROJECT / "tests" / "check_installer.py").read_text(encoding="utf-8")
    check("the installer test looks for this question by its title",
          f'KEY_QUESTION = "{ui_first_run.KEY_TITLE}"' in installer_test)
except Exception as exc:
    unreached("6", exc)
finally:
    first_run.candidates, first_run.xbox_found = real_candidates, real_xbox

print("\n=== 7. the documents, and the internet still only in web/ ===")
try:
    claude = (PROJECT / "CLAUDE.md").read_text(encoding="utf-8")
    check("CLAUDE.md lists the seventh address, api.github.com, for installed copies",
          "7. **The update check**" in claude and "api.github.com" in claude
          and "Anything beyond these " in claude and "needs asking first" in claude)  # eight since Phase 86
    readme = (PROJECT / "docs" / "CITESTE-MA.md").read_text(encoding="utf-8")
    flat = " ".join(readme.split()).lower()  # as it reads, whatever the line breaks
    check("CITESTE-MA.md: the version, GitHub once a day, the key question",
          f"Versiunea {version.APP_VERSION}" in readme and "github" in flat and "o dată pe zi" in flat
          and "steamgriddb" in flat and "a doua întrebare" in flat)
    plan = (PROJECT / "docs" / "DISTRIBUTIE.md").read_text(encoding="utf-8")
    nine = plan.split("## 9.")[1].split("## 10.")[0]
    check("DISTRIBUTIE.md section 9 is written, no longer a placeholder",
          "încă negândit" not in nine and "api.github.com" in nine and rules.UPDATE_REPOSITORY in nine)
    outside = []
    for path in PROJECT.rglob("*.py"):
        part = path.relative_to(PROJECT).parts[0]
        if part in ("web", "tests", ".venv", ".claude", "build", "dist", "docs", "packaging"):
            continue
        text = path.read_text(encoding="utf-8-sig")
        if "urlopen" in text or "urllib.request" in text or "api.github.com" in text and part != "shared":
            outside.append(str(path.relative_to(PROJECT)))
    check("nothing outside web/ talks to the internet; GitHub's address lives in rules.py", not outside, outside)
    import subprocess

    layers = subprocess.run([sys.executable, str(PROJECT / "tests" / "check_layers.py")], cwd=PROJECT,
                            capture_output=True, text=True, timeout=120)
    check("no import points up a layer", "upward imports: 0" in layers.stdout, layers.stdout[-200:])
    asked_out = [a for a in attempts if "github" in a]
    check("and nothing in this suite reached GitHub for real", not asked_out, asked_out)
except Exception as exc:
    unreached("7", exc)

print("\n=== 8. the real library is exactly as it was found ===")
changed = box.finish()
check("config.json and the library database are unchanged", not changed, changed)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
