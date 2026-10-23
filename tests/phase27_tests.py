"""Phase 27: where you are with a game, a note on it -- and a pad that can work a menu.

Runs entirely against a throwaway copy of the data (test_sandbox); the real files are
compared byte for byte at the end. A few real menus and one dialog appear briefly, because
the point is to prove the pad can work them.
"""
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # the project folder, one up from tests/
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import test_sandbox

box = test_sandbox.start()

import logging

logging.basicConfig(level=logging.ERROR)

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QInputDialog, QMenu, QPushButton

app = QApplication([])

from data_access import catalog_io
from adapters import controller
from logic import pick
from shared import rules
from presentation import ui_actions
from presentation import ui_library
from presentation import ui_rules
from presentation import ui_window

SHOTS = Path(tempfile.gettempdir()) / "phase27_renders"
SHOTS.mkdir(exist_ok=True)
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


def record(key):
    return test_sandbox.records().get(key, {})


def new_window():
    window = ui_window.MainWindow()
    window.resize(1280, 900)
    windows.append(window)
    return window


RETRY = "retry"


def run_chain(opener, steps, gap_ms=120, timeout=10.0):
    """Open something that blocks (a menu's exec()), then run steps one after another.

    Each step runs only after the previous one, and a step returning RETRY is tried
    again shortly -- so a press never lands before the menu it is meant for has opened.
    A first version on fixed timers passed, then missed a press on a slower run.
    """
    done = []
    queue = list(steps)
    deadline = time.monotonic() + timeout

    def next_step():
        if not queue or time.monotonic() > deadline:
            done.append(not queue)
            return
        if queue[0]() == RETRY:
            QTimer.singleShot(40, next_step)
            return
        queue.pop(0)
        QTimer.singleShot(gap_ms, next_step)

    QTimer.singleShot(0, opener)
    QTimer.singleShot(40, next_step)
    while not done and time.monotonic() < deadline + 1:
        app.processEvents()
        time.sleep(0.01)
    return bool(done and done[0])


def menu_open():
    return None if isinstance(QApplication.activePopupWidget(), QMenu) else RETRY


def submenu_open(title):
    def step():
        popup = QApplication.activePopupWidget()
        return None if isinstance(popup, QMenu) and popup.title() == title else RETRY
    return step


def menus_closed():
    return None if QApplication.activePopupWidget() is None else RETRY


print(f"\nsandbox data folder: {box.folder}")
print(f"renders:             {SHOTS}")

try:
    print("\n=== 0. the sandbox really is a sandbox ===")
    from data_access import config_io

    check("config.json resolves inside the sandbox", config_io.CONFIG_PATH.parent == box.folder)
    check("so does overrides.json", catalog_io.OVERRIDES_PATH.parent == box.folder)

    print("\n=== 1. what a mark and a note are ===")
    check("every status has a label and a colour",
          set(ui_rules.STATUS_LABELS) == set(rules.STATUSES) == set(ui_rules.STATUS_COLORS))
    held = test_sandbox.library()
    entry = held.load_catalog()[0]
    held.close()
    check("a status nobody chose reads as no mark",
          catalog_io.GameView(entry, {"status": "abandoned-ish"}).status == "")
    check("a real one reads back", catalog_io.GameView(entry, {"status": "finished"}).status == "finished")
    check("a note is read without stray whitespace",
          catalog_io.GameView(entry, {"notes": "  chapter 5 \n"}).notes == "chapter 5")
    check("and anything that is not text is no note", catalog_io.GameView(entry, {"notes": 42}).notes == "")

    print("\n=== 2. marking a game from its page ===")
    w = new_window()
    subject = next(v for v in w.views if not v.hidden and not v.is_non_game
                   and not v.status and not v.notes)
    key = subject.key
    print(f"   subject: {subject.display_name}")
    w.show_detail(key)
    buttons = w.detail.status_buttons
    check("none of the three is lit for an unmarked game",
          not any(b.isChecked() for b in buttons.values()))
    buttons["finished"].click()
    check("pressing Finished saves it", record(key).get(rules.STATUS_KEY) == "finished")
    check("and lights only Finished",
          [s for s, b in buttons.items() if b.isChecked()] == ["finished"])
    buttons["playing"].click()
    check("pressing Playing replaces it", record(key).get(rules.STATUS_KEY) == "playing")
    check("and moves the light",
          [s for s, b in buttons.items() if b.isChecked()] == ["playing"])
    buttons["playing"].click()
    check("pressing the lit one again clears the mark from overrides.json",
          rules.STATUS_KEY not in record(key))
    check("and nothing is lit", not any(b.isChecked() for b in buttons.values()))

    print("\n=== 3. a note, through the real dialog ===")

    def answer_note(text, accept=True):
        def step():
            dialog = QApplication.activeModalWidget()
            if isinstance(dialog, QInputDialog):
                dialog.setTextValue(text)
                dialog.accept() if accept else dialog.reject()
        return step

    note = "Chapter 5, the key is behind the clock.\nFSR on Quality looked best."
    QTimer.singleShot(200, answer_note(note))
    w.detail.notes_button.click()
    check("the note is saved", record(key).get(rules.NOTES_KEY) == note.strip())
    check("it shows on the page", w.detail.note.isVisibleTo(w.detail) and w.detail.note.text() == note)
    check("and the button now offers to edit it", w.detail.notes_button.text() == "Edit note...")
    tooltip = ui_library._tooltip(w.by_key[key])
    check("the tile's tooltip carries its first line", "Note: Chapter 5, the key is behind the clock." in tooltip,
          tooltip)

    QTimer.singleShot(200, answer_note("something I changed my mind about", accept=False))
    w.detail.notes_button.click()
    check("cancelling leaves the note as it was", record(key).get(rules.NOTES_KEY) == note.strip())

    markup = "<b>not bold</b> & <i>not italic</i>"
    QTimer.singleShot(200, answer_note(markup))
    w.detail.notes_button.click()
    check("a note is shown as plain text, never as markup", w.detail.note.text() == markup
          and w.detail.note.textFormat() == Qt.TextFormat.PlainText)

    QTimer.singleShot(200, answer_note("x" * (rules.NOTES_MAX_CHARS + 500)))
    w.detail.notes_button.click()
    check(f"a runaway paste is cut to {rules.NOTES_MAX_CHARS} characters",
          len(record(key).get(rules.NOTES_KEY, "")) == rules.NOTES_MAX_CHARS)

    QTimer.singleShot(200, answer_note("   "))
    w.detail.notes_button.click()
    check("emptying the box removes the note", rules.NOTES_KEY not in record(key))
    check("and hides it on the page", not w.detail.note.isVisibleTo(w.detail))

    print("\n=== 4. play something respects the mark ===")
    pool = [v for v in w.views if not v.hidden and not v.is_non_game]
    ui_actions.set_status(w, w.by_key[key], "dropped")
    check("a dropped game is never offered", key not in {v.key for v in pick.eligible(w.views)})
    rolls = {pick.choose(w.views, now=None).key for _ in range(400)}
    check("not once in 400 rolls", key not in rolls)
    ui_actions.set_status(w, w.by_key[key], "finished")
    weighed = pick.weigh(w.by_key[key])
    ui_actions.set_status(w, w.by_key[key], "")
    plain = pick.weigh(w.by_key[key])
    check("a finished one comes up half as often",
          abs(weighed.weight - plain.weight * rules.PICK_FINISHED_FACTOR) < 1e-9
          and "finished" in weighed.reasons, (weighed, plain))
    check("with no mark it is back in the pool", key in {v.key for v in pick.eligible(w.views)})

    print("\n=== 5. the right-click menu, driven by the pad ===")
    menu = ui_actions.build_menu(w, w.by_key[key])
    labels = [a.text() for a in menu.actions()]
    check("the menu offers the mark and the note", "Mark as" in labels and "Add a note..." in labels,
          labels)
    mark_menu = next(a.menu() for a in menu.actions() if a.text() == "Mark as")
    check("the mark's submenu lists all three and a way to clear it",
          [a.text() for a in mark_menu.actions() if a.text()] == ["Playing", "Finished", "Dropped", "No mark"])
    menu.deleteLater()

    w.show_library()
    w.library.select_key(key)
    grid_row = w.library.list.currentRow()
    point = QPoint(400, 400)
    seen = {}

    def open_menu():
        w._context_menu(key, point)  # blocks in the menu's own loop until it closes

    def press(name):
        return lambda: w._on_pad_action(name)

    def note_active(label):
        def step():
            popup = QApplication.activePopupWidget()
            action = popup.activeAction() if isinstance(popup, QMenu) else None
            seen[label] = action.text() if action is not None else None
        return step

    ok = run_chain(open_menu, [
        menu_open,
        press(controller.DOWN),  # Play
        press(controller.DOWN),  # Add to favorites
        press(controller.DOWN),  # Mark as
        note_active("on the submenu's entry"),
        press(controller.RIGHT),  # opens it, on Playing
        submenu_open("Mark as"),
        press(controller.DOWN),  # Finished
        note_active("inside the submenu"),
        press(controller.ACTIVATE),
        menus_closed,
        note_active("after choosing"),
    ])
    check("the script ran to the end", ok)
    check("down moves through the menu", seen.get("on the submenu's entry") == "Mark as", seen)
    check("right opens the submenu, and down moves inside it", seen.get("inside the submenu") == "Finished",
          seen)
    check("A picks it, and every menu closes", QApplication.activePopupWidget() is None
          and seen.get("after choosing") is None, seen)
    check("the game is now marked finished", record(key).get(rules.STATUS_KEY) == "finished")
    check("and the grid behind the menu never moved", w.library.list.currentRow() == grid_row,
          (grid_row, w.library.list.currentRow()))

    ok = run_chain(open_menu, [
        menu_open,
        press(controller.DOWN),
        press(controller.BACK),
        menus_closed,
        note_active("after B"),
    ])
    check("B closes the menu without choosing anything",
          ok and QApplication.activePopupWidget() is None and seen.get("after B") is None
          and record(key).get(rules.STATUS_KEY) == "finished")
    ui_actions.set_status(w, w.by_key[key], "")

    print("\n=== 6. what it looks like ===")
    others = [v for v in w.views if not v.hidden and not v.is_non_game and v.key != key][:3]
    marked = dict(zip(rules.STATUSES, others))
    for status, view in marked.items():
        w.overrides.update(view.key, **{rules.STATUS_KEY: status})
    w.overrides.update(others[0].key, **{rules.NOTES_KEY: note})
    w.reload_views()
    w.library.set_sort("Name")
    for view in others:
        w.library.select_key(view.key)
    pump(0.3)
    w.grab().save(str(SHOTS / "grid.png"))

    for status, view in marked.items():
        rows = w.library.visible_keys
        item = w.library.list.item(rows.index(view.key))
        # Scrolled into view first: since Phase 31's top bar and chips, a tile may sit below
        # the fold of this small test window, and grabbing it there grabs empty background.
        w.library.list.scrollToItem(item)
        pump(0.2)
        rect = w.library.list.visualItemRect(item)
        image = w.library.list.viewport().grab(rect).toImage()
        want = QColor(ui_rules.STATUS_COLORS[status])
        corner = 0
        for y in range(image.height() // 2, image.height()):
            for x in range(image.width() // 2, image.width()):
                c = image.pixelColor(x, y)
                if abs(c.red() - want.red()) < 14 and abs(c.green() - want.green()) < 14 \
                        and abs(c.blue() - want.blue()) < 14:
                    corner += 1
        check(f"the {status} mark is drawn in its tile's bottom-right, in its colour ({corner} px)",
              corner > 25)

    w.show_detail(others[0].key)
    pump(0.3)
    w.grab().save(str(SHOTS / "detail_playing_with_note.png"))
    w.showFullScreen = lambda: None
    w.showNormal = lambda: None
    w.set_tv_mode(True)
    w.resize(1920, 1080)
    pump(0.3)
    w.grab().save(str(SHOTS / "detail_tv.png"))
    w.set_tv_mode(False)

    print("\n=== 8. no button on a game's page is ever cut short (found while rendering this) ===")
    # Measured on a window that is really on screen, after a real layout pass: a hidden
    # window's buttons report sizes nobody will see.
    w = new_window()
    w.showFullScreen = lambda: None
    w.showNormal = lambda: None
    w.move(20, 20)
    w.show()
    folder_game = next(v for v in w.views if v.entry.source == "folders" and not v.hidden)
    steam_game = next((v for v in w.views if v.entry.source == "steam" and not v.hidden), None)
    subjects = [folder_game] + ([steam_game] if steam_game else [])
    for tv in (False, True):
        w.set_tv_mode(tv)
        w.resize(1600, 950)
        for view in subjects:
            w.show_detail(view.key)
            # A local loop: app.quit() in Qt 6 closes every window first (found in Phase 31),
            # so ending app.exec() that way measured a window that had just been closed.
            from PySide6.QtCore import QEventLoop

            loop = QEventLoop()
            QTimer.singleShot(400, loop.quit)
            loop.exec()
            d = w.detail
            # Every button with words on the page, wherever it sits. Phase 33 moved them
            # (the Play row, the switch, the floating buttons, the cards), so this asks the
            # page rather than naming a row that no longer exists.
            row = [b for b in d.findChildren(QPushButton) if b.isVisibleTo(d) and b.text()]
            short = [(b.text(), b.width(), b.sizeHint().width()) for b in row
                     if b.width() < b.sizeHint().width()]
            check(f"{'TV' if tv else 'normal'} mode, {view.entry.source} game "
                  f"('{d.uninstall_button.text()}'): every button gets its full width",
                  row and not short, short)
    w.set_tv_mode(False)
    w.close()

finally:
    for window in windows:
        try:
            window.close()
        except RuntimeError:
            pass
    print("\n=== 7. the real library is exactly as it was found ===")
    changed = box.finish()
    check("overrides.json, config.json and catalog.json are byte for byte unchanged", not changed,
          changed)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
