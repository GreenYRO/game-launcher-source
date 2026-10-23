"""Phase 106: what's new -- an update explains itself, once, on the first start after it.

  1. the notes: docs/release-notes/<version>.md for 1.2.6 to 1.2.9, both headings and words under each; the English
     found under its heading, under the labels 1.2.6-1.2.9 were published with, and a one-language text whole; a
     version without its file, or with one language, is not ready -- and build.py refuses it before building;
  2. when: the version seen another one -- never the same, never none, never a first run;
  3. in the window, on a copy with 1.2.8 as the version seen: the notes a second after it appears, the version seen
     still the old one while they are open and written once they are closed; the tray offer only after them, a
     second later, never two dialogs at once; the next start, nothing; a window not to be seen waits;
  4. a start in the tray: nothing shown, nothing written, the tray's tooltip saying so -- until the window is shown;
  5. the dialog: its words the English of this version, a web link opened and nothing else, the pad's up and down
     scrolling and moving on, A closing;
  6. Settings, About: What's new for this version; Updates: "See what's new in" a newer one, from the notes the
     update check kept -- read off its answer, kept, read back;
  7. every test copy has seen this version; the documents, the layers, the network, the real data untouched.

On a throwaway copy of the data; the network is blocked.
"""
import json
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT / "packaging"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import sources  # the build log's notes (Phase 91)
import test_sandbox

box = test_sandbox.start({"allow_network": False, "startup_scan": False, "tv_mode": False,
                          "version_seen": "1.2.8", "tray_offer_shown": None})
attempts: list[str] = []


def no_network(request, *args, **kwargs):
    attempts.append(getattr(request, "full_url", str(request)))
    raise OSError("the network is blocked in this suite")


urllib.request.urlopen = no_network

from PySide6.QtCore import QEventLoop, QTimer, QUrl  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

from logic import whats_new  # noqa: E402
from shared import rules, version  # noqa: E402

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


def saved_seen():
    return json.loads((box.folder / "config.json").read_text(encoding="utf-8")).get(rules.VERSION_SEEN_KEY)


NOTES = PROJECT.joinpath(*rules.RELEASE_NOTES_DIR)

print("=== 1. the notes, and a build without them ===")
try:
    history = ["1.2.6", "1.2.7", "1.2.8", "1.2.9"]
    files = sorted(p.stem for p in NOTES.glob("*.md"))
    check("docs/release-notes holds 1.2.6 to 1.2.9 (and this version's)", set(history) <= set(files)
          and version.APP_VERSION in files, files)
    check("each with both headings, Romanian first as published, words under each",
          all(whats_new.ready(v)[0] for v in history)
          and all(whats_new.read(v).index("## Română") < whats_new.read(v).index("## English") for v in history))
    check("1.2.9's English begins as its page does",
          whats_new.english("1.2.9").startswith('**A question after you play: "How was it?".**')
          and "**O întrebare după joc" not in whats_new.english("1.2.9")
          and whats_new.section(whats_new.read("1.2.9"), whats_new.ROMANIAN).startswith("**O întrebare după joc"))
    published = "**Română**\n\nUn paragraf.\n\n---\n\n**English**\n\nA paragraph.\n"
    check("the labels 1.2.6-1.2.9 were published with are read too, the rule left out",
          whats_new.section(published) == "A paragraph." and whats_new.section(published, whats_new.ROMANIAN)
          == "Un paragraf.", repr(whats_new.section(published, whats_new.ROMANIAN)))
    check("a text in one language, as 1.2.0-1.2.5's, is shown whole; one with only Romanian has no English",
          whats_new.section("Fixed a thing.\n\n- and another") == "Fixed a thing.\n\n- and another"
          and whats_new.section("## Română\n\nDoar atât.") == "")
    folder = Path(tempfile.mkdtemp(dir=str(box.folder)))
    (folder / "9.9.9.md").write_text("## Română\n\nCeva.\n", encoding="utf-8")
    (folder / "9.9.8.md").write_text("## Română\n\nCeva.\n\n## English\n\n", encoding="utf-8")
    check("not ready: no file, one language, an empty English",
          not whats_new.ready("9.9.7", folder)[0] and "no release notes for 9.9.7" in whats_new.ready("9.9.7", folder)[1]
          and "no '## English' heading" in whats_new.ready("9.9.9", folder)[1]
          and "nothing under '## English'" in whats_new.ready("9.9.8", folder)[1])
    import build  # packaging/build.py -- imported, never run

    check("build.py refuses a version without notes, and passes this one -- without building",
          build.check_notes("9.9.7").startswith("no release notes for 9.9.7") and build.check_notes() == "",
          build.check_notes())
    source = (PROJECT / "packaging" / "build.py").read_text(encoding="utf-8")
    main = source[source.index("def main()"):]
    check("and it is the first thing its main() does, before anything is deleted or frozen",
          main.index("check_notes()") < main.index("shutil.rmtree") < main.index("run_pyinstaller"))
    spec = (PROJECT / "packaging" / "app.spec").read_text(encoding="utf-8")
    check("the build bundles the folder where What's new reads it",
          '(os.path.join(PROJECT, "docs", "release-notes"), os.path.join("docs", "release-notes"))' in spec
          and whats_new.notes_dir() == NOTES)
except Exception as exc:
    unreached("1", exc)


print("\n=== 2. when ===")
try:
    now = version.APP_VERSION
    check("the version seen another one: due", whats_new.due({rules.VERSION_SEEN_KEY: "1.2.8"}, False))
    check("the same, none, an empty one, or a first run: not",
          not whats_new.due({rules.VERSION_SEEN_KEY: now}, False) and not whats_new.due({}, False)
          and not whats_new.due({rules.VERSION_SEEN_KEY: " "}, False)
          and not whats_new.due({rules.VERSION_SEEN_KEY: "1.2.8"}, True))
except Exception as exc:
    unreached("2", exc)


print("\n=== 3. the first start after an update, in the window ===")
window = None
try:
    from adapters import controller
    from presentation import ui_offer, ui_tray, ui_whats_new, ui_window

    shown: list = []
    real_notes_exec, real_offer_exec = ui_whats_new.WhatsNewDialog.exec, ui_offer.TrayOfferDialog.exec

    def notes_exec(dialog):
        shown.append(("notes", time.monotonic(), saved_seen(), dialog.windowTitle(),
                      dialog.text.toMarkdown(), QApplication.activeModalWidget()))
        QTimer.singleShot(600, dialog.close_button.click)
        return real_notes_exec(dialog)

    def offer_exec(dialog):
        shown.append(("offer", time.monotonic(), saved_seen(), QApplication.activeModalWidget()))
        QTimer.singleShot(300, dialog.reject)
        return real_offer_exec(dialog)

    ui_whats_new.WhatsNewDialog.exec = notes_exec
    ui_offer.TrayOfferDialog.exec = offer_exec
    window = ui_window.MainWindow()
    window.resize(1280, 820)
    check("the window knows it is the first start after an update", window._whats_new)
    appeared = time.monotonic()
    window.show()
    settle(0.6)
    check("nothing at 0.6 s; the version seen still the old one", not shown and saved_seen() == "1.2.8")
    settle(4.5)
    window._stop_watch()
    kinds = [s[0] for s in shown]
    check("the notes, then the tray offer -- one of each", kinds == ["notes", "offer"], kinds)
    notes = next((s for s in shown if s[0] == "notes"), None)
    offer = next((s for s in shown if s[0] == "offer"), None)
    check(f"the notes a second after the window appeared ({(notes[1] - appeared) if notes else 0:.1f} s), "
          "the version seen still 1.2.8 while they are open",
          notes is not None and 0.9 <= notes[1] - appeared < 2.5 and notes[2] == "1.2.8", notes and notes[:3])
    check(f"titled What's new in {version.APP_VERSION}, its words this version's English",
          notes is not None and notes[3] == f"What's new in {version.APP_VERSION}"
          and whats_new.english().split(".**")[0].strip("*") in notes[4], notes and notes[3])
    check("the offer only once the notes were closed, a second later, with no other dialog up",
          offer is not None and offer[1] - notes[1] >= (600 + rules.TRAY_OFFER_DELAY_MS) / 1000 - 0.05
          and offer[2] == version.APP_VERSION and offer[3] is None, offer and (offer[1] - notes[1], offer[2]))
    check("the version seen written once they were closed", saved_seen() == version.APP_VERSION
          and window.config.get(rules.VERSION_SEEN_KEY) == version.APP_VERSION and not window._whats_new)
    shown.clear()
    window.show_whats_new()
    window.hide()
    window.show()
    settle(1.6)
    check("the next look -- or the next start, with this version seen -- shows nothing", shown == [], shown)
    window.close()
    window._shut_down = True
    window.overrides.close()
    window = None

    # A window not to be seen when the notes are due: they wait, and nothing is written.
    def plant_seen(value):
        settings = json.loads((box.folder / "config.json").read_text(encoding="utf-8"))
        settings[rules.VERSION_SEEN_KEY] = value
        (box.folder / "config.json").write_text(json.dumps(settings, indent=2), encoding="utf-8")

    plant_seen("1.2.8")
    window = ui_window.MainWindow()
    shown.clear()
    window.show_whats_new()
    check("a window not to be seen: the notes wait (tried again later), nothing shown, nothing written",
          shown == [] and window._whats_new and window._whats_new_tries == 1 and saved_seen() == "1.2.8")

    print("\n=== 4. a start in the tray ===")
    window.keep_running = True
    window._apply_keep_running()
    window.begin()  # what a --background start runs, the window never shown
    settle(0.3)
    check("--background: no notes, the version seen not written", shown == [] and saved_seen() == "1.2.8")
    tip = window.tray.icon.toolTip() if window.tray is not None else ""
    check("the tray's tooltip says it was updated", tip == ui_tray.UPDATED.format(version=version.APP_VERSION), tip)
    window._in_tray = False
    window.show()
    settle(2.2)
    window._stop_watch()
    check("shown at last: the notes, then the version seen written and the tooltip as it was",
          [s[0] for s in shown][:1] == ["notes"] and saved_seen() == version.APP_VERSION
          and window.tray.icon.toolTip() == ui_tray.TOOLTIP, ([s[0] for s in shown], window.tray.icon.toolTip()))
    check("the offer, on a copy whose switch is now on, not asked", [s[0] for s in shown] == ["notes"],
          [s[0] for s in shown])
    ui_whats_new.WhatsNewDialog.exec = real_notes_exec
    ui_offer.TrayOfferDialog.exec = real_offer_exec

    print("\n=== 5. the dialog ===")
    opened: list[str] = []
    real_open = ui_whats_new.QDesktopServices.openUrl
    ui_whats_new.QDesktopServices.openUrl = lambda url: opened.append(url.toString()) or True
    try:
        check("a web link opens the browser; a file or anything else does not",
              ui_whats_new.open_link(QUrl("https://example.com/notes"))
              and not ui_whats_new.open_link(QUrl("file:///C:/Windows/notepad.exe"))
              and opened == ["https://example.com/notes"], opened)
    finally:
        ui_whats_new.QDesktopServices.openUrl = real_open
    dialog = ui_whats_new.WhatsNewDialog("9.9.9", "## Heading\n\n- one\n- two\n\n[a link](https://example.com)\n\n"
                                         + "A long line of words. " * 400, 1.0, parent=window)
    dialog.show()
    settle(0.3)
    html = dialog.text.toHtml()
    check("Markdown drawn by Qt: a heading, a list, a link", "<h2" in html and "<li" in html
          and 'href="https://example.com"' in html)
    bar = dialog.text.verticalScrollBar()
    check("the words first: they have the focus", QApplication.focusWidget() is dialog.text)
    window._drive_dialog(dialog, controller.DOWN)
    moved = bar.value()
    check("the pad's down scrolls the words", moved > 0 and QApplication.focusWidget() is dialog.text, moved)
    window._drive_dialog(dialog, controller.UP)
    check("and up scrolls them back", bar.value() == 0)
    window._drive_dialog(dialog, controller.UP)
    settle(0.1)
    check("at the top, up goes on to the control before (Close, round the dialog)",
          QApplication.focusWidget() is dialog.close_button, QApplication.focusWidget())
    dialog.text.setFocus()
    window._drive_dialog(dialog, controller.ACTIVATE)
    settle(0.2)
    check("A on the words presses Close", not dialog.isVisible() and dialog.result() == 1, dialog.result())
    empty = ui_whats_new.WhatsNewDialog("9.9.7", "", 1.0, parent=window)
    check("no notes: it says so", "carries no notes for 9.9.7" in empty.text.toPlainText())
    empty.deleteLater()

    print("\n=== 6. Settings: What's new, and a newer one's notes ===")
    from presentation import ui_settings
    from web import updates

    seen_dialogs: list[tuple[str, str]] = []
    real_exec = ui_whats_new.WhatsNewDialog.exec

    def capture(dialog_):
        seen_dialogs.append((dialog_.windowTitle(), dialog_.text.toMarkdown()))
        return 0

    ui_whats_new.WhatsNewDialog.exec = capture
    settings = ui_settings.SettingsDialog(dict(window.config), window, store=window.overrides)
    check("About: What's new beside the version, on", settings.whats_new_button.text() == "What's new"
          and settings.whats_new_button.isEnabled() and settings.newer_notes_button is None)
    settings.whats_new_button.click()
    check("it opens this version's notes", seen_dialogs and seen_dialogs[-1][0] == f"What's new in {version.APP_VERSION}"
          and whats_new.english().split(".**")[0].strip("*") in seen_dialogs[-1][1], seen_dialogs[-1:])
    settings.reject()

    payload = {"tag_name": "v1.2.99", "name": "1.2.99", "draft": False, "prerelease": False,
               "published_at": "2026-11-01T10:00:00Z",
               "body": "## Română\n\nCeva nou.\n\n## English\n\n**Something new.** And [the page](https://example.com).\n"}
    answer = updates.read(payload, datetime.now(timezone.utc))
    check("the update check keeps the release's notes from its answer", answer.newer and answer.notes == payload["body"])
    updates._keep(updates.paths.cache_dir(), answer)
    kept = updates.last()
    old_style = updates.Answer.from_dict({"checked_at": "2026-10-20T10:00:00+00:00", "reached": True,
                                          "latest": "1.2.9", "title": "1.2.9"})
    check("kept and read back; an answer kept before them reads as none",
          kept is not None and kept.notes == payload["body"] and old_style is not None and old_style.notes == "")
    real_should = updates.should_check
    updates.should_check = lambda config: (True, "")  # as an installed copy, network on
    try:
        settings = ui_settings.SettingsDialog(dict(window.config), window, store=window.overrides)
    finally:
        updates.should_check = real_should
    button = settings.newer_notes_button
    check("Updates: 'See what's new in 1.2.99' beside the download page", button is not None
          and button.text() == "See what's new in 1.2.99" and button.parentWidget() is settings.update_page.parentWidget(),
          button.text() if button else None)
    seen_dialogs.clear()
    button.click()
    check("it shows that release's English, from the kept answer -- nothing fetched",
          seen_dialogs and seen_dialogs[-1][0] == "What's new in 1.2.99" and "Something new." in seen_dialogs[-1][1]
          and "Ceva nou" not in seen_dialogs[-1][1] and attempts == [], seen_dialogs[-1:])
    settings.reject()
    ui_whats_new.WhatsNewDialog.exec = real_exec
except Exception as exc:
    unreached("3-6", exc)
finally:
    if window is not None:
        window._shut_down = True
        if window.tray is not None:
            window.tray.remove()
        try:
            window.overrides.close()
        except Exception as exc:  # noqa: BLE001 -- the suite's end, said
            print(f"   (closing the store: {exc})")


print("\n=== 7. test copies, the documents, the layers ===")
try:
    check("every test copy has seen this version (no suite's window stands on What's new); the name is the rule's",
          test_sandbox._app_version() == version.APP_VERSION and test_sandbox.VERSION_SEEN == rules.VERSION_SEEN_KEY
          and "config[VERSION_SEEN] = _app_version()" in (PROJECT / "tests" / "test_sandbox.py").read_text(encoding="utf-8"))

    def doc(name: str) -> str:
        return (PROJECT / name).read_text(encoding="utf-8").replace("\r\n", "\n")

    claude = doc("CLAUDE.md")
    check("CLAUDE.md: the row, the modules, the notes folder, the release rule, under its size",
          "| 106 |" in claude and "whats_new.py" in claude and "ui_whats_new.py" in claude
          and "release-notes/" in claude and "docs/release-notes/<version>.md" in claude
          and len(claude.encode("utf-8")) < 116581, len(claude.encode("utf-8")))
    distribution = doc("docs/DISTRIBUTIE.md")
    check("DISTRIBUTIE: the release checklist writes the notes first; section 9 says where they show",
          "docs/release-notes/<versiune>.md" in distribution and "What's new" in distribution.split("## 9.")[1])
    readme = doc("docs/CITESTE-MA.md")
    check("CITESTE-MA: where what's new is, still on one page", "What's new" in readme
          and len(readme.splitlines()) <= 110, len(readme.splitlines()))
    page = doc("docs/explicatii/faza-106.md")
    check("the explanation page, in its shape, with the five words", all(w in page for w in (
        "## Ce s-a construit", "## De ce contează", "## Cum funcționează", "## Cinci cuvinte", "## Trei întrebări",
        "## Ce nu poate face", "*release notes*", "*changelog*", "*semantic versioning*", "*single source of truth*",
        "*first run*")) and "faza 106" in doc("docs/explicatii/CITESTE-MA.md"))
    check("ISTORIC has the phase's notes", "## Phase 106 notes" in sources.build_log())
    layers = subprocess.run([sys.executable, str(PROJECT / "tests" / "check_layers.py")], capture_output=True,
                            text=True, encoding="utf-8", errors="replace")
    check("no import points up a layer; sqlite3 only in data_access/", layers.returncode == 0, layers.stdout[-300:])
    check("nothing in this suite reached the network", attempts == [], attempts)
except Exception as exc:
    unreached("7", exc)

print("\n=== 8. the real library is exactly as it was found ===")
changed = box.finish()
check("config.json, the library database and the Run key's value are unchanged", not changed, changed)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
