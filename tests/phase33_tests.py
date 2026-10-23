"""Phase 33: a game's own page, redesigned -- the art edge to edge, pills, one Play row, cards.

Runs against a throwaway copy of the data (test_sandbox), with the Steam records,
update posts and screenshots the real cache already holds copied in, read only, so the
page has something to show. Nothing here starts a game, opens a folder or a menu: those
are intercepted before they would reach the desktop.
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # the project folder, one up from tests/
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import test_sandbox

box = test_sandbox.start()
REAL_SHOTS = Path(__file__).resolve().parents[1] / "data" / "cache" / "screenshots"
box.copy_cache("steam_details", "steam_news.json", "steam_web.json",
               *[f"screenshots/{name}" for name in (os.listdir(REAL_SHOTS) if REAL_SHOTS.is_dir() else [])])
print(f"real screenshots copied into the sandbox: {len(list((Path(box.folder) / 'cache' / 'screenshots').glob('*')))}")

import logging

logging.basicConfig(level=logging.ERROR)

from PySide6.QtCore import QEventLoop, QPoint, Qt, QTimer
from PySide6.QtGui import QColor, QPixmap, QRegion
from PySide6.QtWidgets import QApplication, QPushButton, QWidget

app = QApplication([])

from adapters import controller
from logic import gamedetails
from logic import removal
from shared import rules
from logic import sessions
from presentation import ui_actions
from presentation import ui_rules
from presentation import ui_window

SHOTS = Path(tempfile.gettempdir()) / "phase33_renders"
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


def settle(seconds=0.4):
    """A local event loop -- never app.exec() ended by app.quit() (the Phase 31 lesson)."""
    loop = QEventLoop()
    QTimer.singleShot(round(seconds * 1000), loop.quit)
    loop.exec()


def pixel(image, point):
    colour = image.pixelColor(point)
    return colour.red(), colour.green(), colour.blue()


def close_to(a, b, tolerance=4):
    return all(abs(x - y) <= tolerance for x, y in zip(a, b))


def squeezed(page):
    """Every button with words on the page that has been given less than it asks for."""
    buttons = [b for b in page.findChildren(QPushButton) if b.isVisibleTo(page) and b.text()]
    return buttons, [(b.text(), b.width(), b.sizeHint().width()) for b in buttons
                     if b.width() < b.sizeHint().width()]


calls = {"play": [], "stop": [], "folder": []}
real = (ui_actions.play, ui_actions.stop, ui_actions.open_folder)
ui_actions.play = lambda window, view: calls["play"].append(view.key)
ui_actions.stop = lambda window, view: calls["stop"].append(view.key)
ui_actions.open_folder = lambda window, view: calls["folder"].append(view.key)

print(f"\nsandbox data folder: {box.folder}")
print(f"renders:             {SHOTS}")

try:
    w = ui_window.MainWindow()
    windows.append(w)
    w.showFullScreen = lambda: None
    w.showNormal = lambda: None
    w.resize(1600, 950)
    w.move(20, 20)
    w.show()
    settle(0.8)
    page = w.detail
    menus = []
    page.menuRequested.disconnect()  # the window's handler would open a real, blocking menu
    page.menuRequested.connect(lambda key, pos: menus.append((key, pos)))
    w._context_menu = lambda key, pos: menus.append((key, pos))  # and so would the pad's

    shown = [v for v in w.views if not v.hidden]
    # The subject is a game timed here whose page is longer than the window, because section
    # 4 scrolls it. "The first timed game" was one until the user installed BloodBorne, whose
    # page -- no Steam record, so no About, no screenshots -- fits the window and cannot
    # scroll (Phase 63). So each candidate's page is opened and measured, never assumed.
    candidates = [v for v in shown if v.entry.launch_kind == "exe" and sessions.load(v.data)
                  and v.playtime_seconds > 0]
    timed = None
    for candidate in candidates:
        w.show_detail(candidate.key)
        settle(0.6)
        if page.scroll.verticalScrollBar().maximum() > 0:
            timed = candidate
            break
    if timed is None and candidates:
        print("   no timed game here has a page long enough to scroll; section 4 cannot pass")
        timed = candidates[0]
    w.show_library()
    settle(0.6)
    uri = next((v for v in shown if v.entry.launch_kind != "exe"), None)
    subject = timed or next(v for v in shown if v.entry.launch_kind == "exe")
    print(f"   a timed game whose page scrolls: {subject.display_name} (of {len(candidates)} timed);  "
          f"one Steam or Xbox starts: {uri.display_name if uri else '(none here)'}")

    print("\n=== 1. the picture runs edge to edge and fades into the page ===")
    w.show_detail(subject.key)
    settle(1.0)
    viewport = page.scroll.viewport()
    check("it is as wide as the page", page.banner.width() == viewport.width(),
          (page.banner.width(), viewport.width()))
    check("and takes the share of the height it asks for, or more",
          page.banner.height() >= round(viewport.height() * ui_rules.DETAIL_HERO_FRACTION) - 1,
          (page.banner.height(), viewport.height()))
    frame = page.banner._pixmap_for(0).toImage()
    middle = frame.width() // 2
    check("its top is solid", frame.pixelColor(middle, 2).alpha() == 255)
    check("and its foot is truly see-through, not a fade to a flat colour",
          frame.pixelColor(middle, frame.height() - 1).alpha() < 8,
          frame.pixelColor(middle, frame.height() - 1).alpha())
    check("the window glows in this game's own colours behind its page",
          w.backdrop.key == subject.key, w.backdrop.key)
    content = page.content
    cover_edge = page.cover_art.mapTo(content, page.cover_art.cover_rect().topLeft()).x()
    card_edge = page.note_card.mapTo(content, QPoint(0, 0)).x()
    check("the cover's edge lines up with the cards under it", abs(cover_edge - card_edge) <= 1,
          (cover_edge, card_edge))
    play_foot = page.play_button.mapTo(content, QPoint(0, page.play_button.height())).y()
    cover_foot = page.cover_art.mapTo(content, page.cover_art.cover_rect().bottomLeft()).y()
    # Level until Phase 57; the design stands the Play row 4 px above the cover's foot.
    check("and the Play row's foot just above the cover's, as the design has it",
          abs(cover_foot + 1 - play_foot - round(ui_rules.DETAIL_INFO_FOOT * w.metrics.scale)) <= 1,
          (play_foot, cover_foot + 1))
    w.grab().save(str(SHOTS / "page.png"))

    print("\n=== 2. the facts worth seeing first, as pills ===")
    facts = page.facts()
    pills = {fact: pill for fact, pill in page.pills.items() if not pill.isHidden()}
    check("a game timed here says how long", "Played" in pills and "played" in pills["Played"].text(),
          {f: p.text() for f, p in pills.items()})
    check("and when", ("Last played" in pills) == (subject.last_played is not None))
    check("and how big, when that is known",
          ("Installed" in pills) == bool(subject.entry.size_on_disk))
    check("the same facts are not repeated in the Details card",
          not any(label in gamedetails.SUMMARY_FACTS
                  for label in (page.facts_grid.itemAtPosition(r, 0).widget().text()
                                for r in range(page.facts_grid.rowCount())
                                if page.facts_grid.itemAtPosition(r, 0))))
    check("the path it runs goes in the Files card", facts.get("Runs") == subject.launch_target)
    check("a pill is not a button: the mouse goes through it, and so does Tab",
          all(p.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
              and p.focusPolicy() == Qt.FocusPolicy.NoFocus for p in page.pills.values()))
    if uri is not None:
        w.show_detail(uri.key)
        settle(0.6)
        # Since the Phase 102 extension the pill is the game's hours as the reports count them: a store game
        # shows Steam's own count when there is one, and still none when its time is unknown -- never 0.
        known = round((w.hours.get(uri.key) or {}).get("minutes", 0) * 60) > 0
        check(f"a game Steam or Xbox starts has a 'played' pill exactly when its hours are known ({known}), never 0",
              page.pills["Played"].isHidden() != known
              and (not known or "played" in page.pills["Played"].text()))
        check("and no sessions card", page.sessions_card.isHidden())
        w.show_detail(subject.key)
        settle(0.6)

    print("\n=== 3. the Play row ===")
    page.play_button.click()
    check("Play starts it", calls["play"] == [subject.key], calls["play"])
    real_running = w.tracker.is_running
    w.tracker.is_running = lambda key: key == subject.key
    w.refresh_running_state()
    check("while it runs, Play becomes Stop", page.running and "Stop" in page.play_button.text()
          and page.play_button.objectName() == "HeroStop")
    page.play_button.click()
    check("and Stop stops it", calls["stop"] == [subject.key])
    w.tracker.is_running = real_running
    w.refresh_running_state()
    check("then Play is back, still the big one", page.play_button.objectName() == "HeroPlay"
          and page.play_button.property("variant") == "large")
    page.play_button.ensurePolished()
    check("and its larger style really applies (it once named its tag 'size', which every "
          "widget already has, so the style never matched)",
          page.play_button.font().pixelSize() == round(ui_rules.DETAIL_PLAY_PX * w.metrics.scale),
          page.play_button.font().pixelSize())
    was = subject.favorite
    page.favorite_button.click()
    settle(0.2)
    check("the star stars it", w.by_key[subject.key].favorite != was
          and page.favorite_button.isChecked() != was)
    page.favorite_button.click()
    settle(0.2)
    check("and again unstars it", w.by_key[subject.key].favorite == was)
    page.folder_button.click()
    check("the folder button opens its folder", calls["folder"] == [subject.key])
    menus.clear()
    page.more_button.click()
    check("'...' opens the game's menu, just under the button",
          len(menus) == 1 and menus[0][0] == subject.key
          and abs(menus[0][1].y() - page.more_button.mapToGlobal(
              QPoint(0, page.more_button.height())).y()) <= 1, menus)
    labels = [a.text() for a in ui_actions.build_menu(w, w.by_key[subject.key]).actions()]
    check("and that menu holds what the page's old buttons did: art, hide, uninstall",
          "Cover" in labels and "Banner" in labels and ("Hide" in labels or "Unhide" in labels)
          and labels[-1].endswith("..."), labels)
    segments = page.status_buttons
    widths_before = {s: b.width() for s, b in segments.items()}
    before = w.by_key[subject.key].status
    target = next(s for s in rules.STATUSES if s != before)
    segments[target].click()
    settle(0.2)
    check("a mark is one press", w.by_key[subject.key].status == target
          and [s for s, b in segments.items() if b.isChecked()] == [target])
    segments[target].click()
    settle(0.2)
    check("and pressing the lit one clears it", not w.by_key[subject.key].status
          and not any(b.isChecked() for b in segments.values()))
    if before:
        segments[before].click()
        settle(0.2)
    # One width for all three until Phase 57; the design sizes each to its words, so the
    # property that matters is the one kept: lighting a mark never changes a width.
    widths = {s: b.width() for s, b in segments.items()}
    check("each mark as wide as its words, and lighting one never makes it bigger",
          widths == widths_before and all(b.width() == b.sizeHint().width() for b in segments.values()),
          (widths_before, widths))

    print("\n=== 4. Back, Previous and Next float, and stay put ===")
    bar = page.scroll.verticalScrollBar()
    top_place = page.back_button.pos()
    check("at the top of the page nothing darkens the picture", page.top_fade.isHidden())
    bar.setValue(bar.maximum())
    settle(0.3)
    check("scrolled to the bottom, Back is exactly where it was",
          page.back_button.pos() == top_place and page.back_button.isVisible())
    check("with a dark fade under the buttons now", not page.top_fade.isHidden()
          and page.top_fade.strength == 1.0)
    w.grab().save(str(SHOTS / "scrolled.png"))
    page.next_button.click()
    settle(0.5)
    check("Next game moves on", page.view.key == w.library.neighbour(subject.key, 1))
    check("and the next game's page starts at its top", bar.value() == 0)
    page.prev_button.click()
    settle(0.5)
    check("Previous game comes back", page.view.key == subject.key)
    page.back_button.click()
    settle(0.4)
    check("Back goes to the library", w.stack.currentIndex() == ui_window.LIBRARY_PAGE)

    print("\n=== 5. the cards: there when they have something to say ===")
    mismatched = []
    for view in shown[:30]:
        w.show_detail(view.key)
        settle(0.15)
        record = gamedetails.record_for(view)
        wanted = {
            "about": bool(gamedetails.description(record)),
            "screenshots": bool(gamedetails.screenshots(record, ui_rules.SCREENSHOT_MAX_PER_GAME)),
            # Since Phase 93 every game with sessions shows them: a Steam game's are the ones seen running.
            "sessions": bool(sessions.load(view.data)),
        }
        got = {
            "about": page.about_card.isVisibleTo(page),
            "screenshots": page.shots_card.isVisibleTo(page),
            "sessions": page.sessions_card.isVisibleTo(page),
        }
        if wanted != got:
            mismatched.append((view.display_name, wanted, got))
    described = sum(1 for v in shown[:30] if gamedetails.description(gamedetails.record_for(v)))
    print(f"         ({len(shown[:30])} games looked at, {described} with a Steam description)")
    check("About, Screenshots and Recent sessions each appear exactly when there is something",
          not mismatched, mismatched[:3])
    check("the Details card is always there, and ends with the uninstall button",
          page.details_card.isVisibleTo(page) and page.uninstall_button.isVisibleTo(page))
    w.show_detail(subject.key)
    settle(0.5)
    check("that button says what this game's source allows (Phase 25)",
          page.uninstall_button.text().startswith(removal.plan(subject, w.config, w.tracker).button))
    if timed is not None:
        recent = sessions.recent(sessions.load(timed.data), ui_rules.SESSIONS_SHOWN)
        check("recent sessions are drawn as one bar each", len(page.session_bars.rows) == len(recent))
    note_before = w.by_key[subject.key].notes
    w.overrides.update(subject.key, **{rules.NOTES_KEY: None})
    w.reload_views()
    check("with no note, the note card asks for one",
          page.note_prompt.isVisibleTo(page) and not page.note.isVisibleTo(page)
          and page.notes_button.text() == "Add a note...")
    w.overrides.update(subject.key, **{rules.NOTES_KEY: "Chapter 5 -- the clock in the lobby"})
    w.reload_views()
    check("with one, it shows it, as plain text", page.note.isVisibleTo(page)
          and not page.note_prompt.isVisibleTo(page) and page.note.text().startswith("Chapter 5")
          and page.note.textFormat() == Qt.TextFormat.PlainText
          and page.notes_button.text() == "Edit note...")
    w.overrides.update(subject.key, **{rules.NOTES_KEY: note_before or None})
    w.reload_views()
    many = next((v for v in shown if len(gamedetails.screenshots(
        gamedetails.record_for(v), ui_rules.SCREENSHOT_MAX_PER_GAME)) >= 6), None)
    if many is not None:
        w.resize(1100, 800)
        w.show_detail(many.key)
        settle(0.8)
        strip = page.strip
        thumb = max(t.height() for t in strip.thumbs.values())
        check("screenshots too many for one row wrap onto another, never widening the page",
              strip.height() >= thumb * 2 and page.content.width() <= page.scroll.viewport().width() + 1,
              (strip.height(), thumb, page.content.width(), page.scroll.viewport().width()))
        w.resize(1600, 950)
        settle(0.3)

    print("\n=== 6. the pad ===")
    w.show_detail(subject.key)
    settle(0.5)
    calls["play"].clear()
    w._on_pad_action(controller.ACTIVATE)
    check("A plays", calls["play"] == [subject.key])
    menus.clear()
    w._on_pad_action(controller.MENU)
    check("X opens the menu under '...', where the mouse would open it",
          menus and menus[0][0] == subject.key and menus[0][1] == page.menu_position(), menus)
    bar.setValue(0)
    w._on_pad_action(controller.DOWN)
    settle(0.1)
    after_down = bar.value()
    check("down reads down the page", after_down > 0, after_down)
    w._on_pad_action(controller.PAGE_DOWN)
    check("a shoulder moves a screen at a time", bar.value() >= min(bar.maximum(), after_down + bar.pageStep() - 1))
    w._on_pad_action(controller.UP)
    check("up comes back up", bar.value() < max(after_down + bar.pageStep(), 1))
    w._on_pad_action(controller.RIGHT)
    settle(0.4)
    check("right is the next game, as before", page.view.key == w.library.neighbour(subject.key, 1))
    w._on_pad_action(controller.LEFT)
    settle(0.4)
    check("and left the previous", page.view.key == subject.key)
    w._on_pad_action(controller.BACK)
    settle(0.3)
    check("B goes back to the library", w.stack.currentIndex() == ui_window.LIBRARY_PAGE)

    print("\n=== 7. nothing is squeezed, at any size ===")
    steam_game = next((v for v in shown if v.entry.source == "steam"), None)
    for label, size, tv in (("a 1600x950 window", (1600, 950), False),
                            ("a narrow 1100x760 window", (1100, 760), False),
                            ("TV mode at 1920x1080", (1920, 1080), True)):
        w.set_tv_mode(tv)
        w.resize(*size)
        for view in [subject] + ([steam_game] if steam_game else []):
            w.show_detail(view.key)
            settle(0.6)
            buttons, short = squeezed(page)
            check(f"{label}, {view.entry.source} game: every button gets its full width",
                  buttons and not short, short)
        if label.startswith("a narrow"):
            w.grab().save(str(SHOTS / "narrow.png"))
        if tv:
            w.grab().save(str(SHOTS / "tv.png"))
    w.set_tv_mode(False)
    w.resize(1600, 950)

    print("\n=== 8. the page is see-through to its glow ===")
    w.show_detail(subject.key)
    settle(1.0)
    left = page.note_card
    right = page.details_card if page.sessions_card.isHidden() else page.sessions_card
    gap_x = (left.mapTo(w.backdrop, QPoint(left.width(), 0)).x()
             + right.mapTo(w.backdrop, QPoint(0, 0)).x()) // 2
    gap = QPoint(gap_x, left.mapTo(w.backdrop, QPoint(0, left.height() // 2)).y())
    shot = w.grab().toImage()
    glow = pixel(w.backdrop._current.toImage(), gap)
    plain = QColor(ui_rules.COLOR_BACKGROUND)
    # Until Phase 55 the glow there differed from the plain colour, so the window's pixel
    # could tell a see-through page from an opaque one. The design's glow has faded fully
    # into the ground by 62% of the way down, where the cards sit -- so the page itself is
    # asked: drawn on its own onto nothing, it must leave the gap between the columns empty.
    alone = QPixmap(page.size())
    alone.fill(Qt.GlobalColor.transparent)
    page.render(alone, QPoint(), QRegion(), QWidget.RenderFlag.DrawChildren)
    inside = page.mapFrom(w.backdrop, gap)
    empty = alone.toImage().pixelColor(inside).alpha()
    check("between the two columns of cards the page draws nothing -- whatever glows behind shows",
          empty == 0, empty)
    check("and the window shows the glow there, not an opaque page",
          close_to(pixel(shot, w.backdrop.mapTo(w, gap)), glow), (pixel(shot, w.backdrop.mapTo(w, gap)), glow))
    w.show_stats()
    settle(0.7)
    # Step 5 (Phase 35) gave Stats the library's glow; this used to assert the plain colour.
    check("Stats wears the library's glow, not this game's",
          w.backdrop.key == w.library.backdrop_key(), (w.backdrop.key, w.library.backdrop_key()))
    w.close()

finally:
    ui_actions.play, ui_actions.stop, ui_actions.open_folder = real
    for window in windows:
        try:
            window.close()
        except RuntimeError:
            pass
    print("\n=== 9. the real library is exactly as it was found ===")
    changed = box.finish()
    check("overrides.json, config.json and catalog.json are byte for byte unchanged", not changed,
          changed)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
