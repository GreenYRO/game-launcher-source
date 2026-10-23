"""Phase 32: the library redesigned -- Continue playing, a backdrop from the art, new tiles.

Runs against a throwaway copy of the data (test_sandbox). A launcher window is shown for a
few seconds, because folding, focus and see-through painting only mean something on a real
window. Nothing here starts a game: Play and Stop are intercepted before ui_actions runs.
"""
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # the project folder, one up from tests/
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import sources
import test_sandbox

box = test_sandbox.start()

import logging

logging.basicConfig(level=logging.ERROR)

from PySide6.QtCore import QEventLoop, QPoint, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

app = QApplication([])

from adapters import controller
from shared import rules
from presentation import ui_actions
from presentation import ui_continue
from presentation import ui_library
from presentation import ui_rules
from presentation import ui_theme
from presentation import ui_window

SHOTS = Path(tempfile.gettempdir()) / "phase32_renders"
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
    """A local event loop -- never app.exec() ended by app.quit(), which closes every
    window in Qt 6 (the Phase 31 lesson)."""
    loop = QEventLoop()
    QTimer.singleShot(round(seconds * 1000), loop.quit)
    loop.exec()


def new_window():
    window = ui_window.MainWindow()
    windows.append(window)
    return window


def fake(name, *, played_days_ago=None, status="", hidden=False, non_game=False,
         kind="exe", source="folders", seconds=0, notes=""):
    """Just enough of a GameView for the card's and the tile's decisions."""
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        key=name.casefold(), display_name=name, hidden=hidden, is_non_game=non_game,
        last_played=None if played_days_ago is None else now - timedelta(days=played_days_ago),
        status=status, notes=notes, playtime_seconds=seconds,
        entry=SimpleNamespace(launch_kind=kind, source=source),
    )


def pixel(image, point):
    colour = image.pixelColor(point)
    return colour.red(), colour.green(), colour.blue()


def close_to(a, b, tolerance=4):
    return all(abs(x - y) <= tolerance for x, y in zip(a, b))


played, stopped, menus = [], [], []
real_play, real_stop = ui_actions.play, ui_actions.stop
ui_actions.play = lambda window, view: played.append(view.key)
ui_actions.stop = lambda window, view: stopped.append(view.key)

print(f"\nsandbox data folder: {box.folder}")
print(f"renders:             {SHOTS}")

try:
    print("\n=== 1. the shelves are gone ===")
    # Looked for as a file anywhere in the project, not as an importable name: once the ui_
    # modules left the root, asking for a top-level "ui_shelf" would pass whatever existed.
    shelf = [p for p in sources.python_files() if p.name == "ui_shelf.py"]
    check("there is no ui_shelf module any more", not shelf, shelf)
    check("and no shelf settings left in ui_rules",
          not [name for name in dir(ui_rules) if name.startswith("SHELF_")])
    check("the page has no shelves to hold",
          not any(hasattr(ui_library.LibraryPage, name)
                  for name in ("shelves", "open_shelves", "recent_shelf", "favorites_shelf")))

    print("\n=== 2. which game the card offers ===")
    older = fake("Older", played_days_ago=9, seconds=600)
    newest = fake("Newest", played_days_ago=1, seconds=6120)
    check("the most recently played game", ui_continue.pick([older, newest]) is newest)
    done = fake("Done", played_days_ago=0, status=rules.STATUS_FINISHED)
    quit_ = fake("Quit", played_days_ago=0, status=rules.STATUS_DROPPED)
    check("never one you marked Finished or Dropped",
          ui_continue.pick([older, done, quit_]) is older)
    still = fake("Still", played_days_ago=0, status=rules.STATUS_PLAYING)
    check("but one marked Playing is offered", ui_continue.pick([older, still]) is still)
    check("never a hidden game, or a demo or tool",
          ui_continue.pick([older, fake("H", played_days_ago=0, hidden=True),
                            fake("T", played_days_ago=0, non_game=True)]) is older)
    check("and no card at all when nothing has been played",
          ui_continue.pick([fake("New"), fake("Also new")]) is None)
    check("the line under the title says how long, for a game timed here",
          ui_continue.meta_line(newest).startswith("1h 42m played") and "yesterday" in
          ui_continue.meta_line(newest), ui_continue.meta_line(newest))
    steam = fake("Steamy", played_days_ago=3, kind="uri", source="steam")
    check("and names the store, never a time, for one Steam starts",
          ui_continue.meta_line(steam).startswith("Steam") and "played" in
          ui_continue.meta_line(steam) and "h " not in ui_continue.meta_line(steam),
          ui_continue.meta_line(steam))
    check("a game started but not yet timed does not read 'never played played'",
          "never" not in ui_continue.meta_line(fake("Fresh", played_days_ago=0)),
          ui_continue.meta_line(fake("Fresh", played_days_ago=0)))
    check("the first line of a note is quoted under it",
          ui_continue.note_line(fake("N", notes="\n  Chapter 5, the clock  \nmore")) == "“Chapter 5, the clock”")
    check("and nothing is shown without a note", ui_continue.note_line(fake("N")) == "")

    print("\n=== 3. the line under a tile's name ===")
    check("time played for a game timed here", ui_library.tile_subtitle(newest) == "1h 42m")
    check("'never played' for one not yet started", ui_library.tile_subtitle(fake("X")) == "never played")
    check("the store's name for one Steam starts -- its time is unknown, not zero",
          ui_library.tile_subtitle(steam) == "Steam")
    check("a hidden game says so", ui_library.tile_subtitle(fake("Z", hidden=True)).startswith("Hidden"))
    for scale in (1.0, 0.85, 1.6):
        metrics = ui_theme.Metrics(scale)
        # The design's sizes since Phase 55 (13 and 11.5 px): what each line is drawn in.
        name = QFont()
        name.setPointSizeF(ui_theme.px_to_pt(ui_rules.TILE_NAME_PX * scale))
        sub = QFont()
        sub.setPointSizeF(ui_theme.px_to_pt(ui_rules.TILE_SUB_PX * scale))
        needed = (round(ui_rules.TILE_NAME_GAP * scale)
                  + max(QFontMetrics(name).height(),
                        round(ui_rules.TILE_NAME_PX * ui_rules.TILE_LINE_HEIGHT * scale))
                  + round(ui_rules.TILE_SUB_GAP * scale)
                  + max(QFontMetrics(sub).height(),
                        round(ui_rules.TILE_SUB_PX * ui_rules.TILE_LINE_HEIGHT * scale)))
        check(f"both lines fit under the art at {scale:.0%}", needed <= metrics.tile_name_height,
              (needed, metrics.tile_name_height))

    print("\n=== 4. the card on the real library ===")
    w = new_window()
    w.resize(1500, 900)
    w.move(20, 20)
    w.show()
    settle(0.6)
    lib, card = w.library, w.library.card
    w.library.contextRequested.disconnect(w._context_menu)  # QMenu.exec would block the test
    w.library.contextRequested.connect(lambda key, _pos: menus.append(key))
    offered = ui_continue.pick(w.views)
    check("the card offers the game the rules pick", offered is not None
          and card.view is not None and card.view.key == offered.key,
          (offered and offered.display_name, card.view and card.view.display_name))
    check("and is on the page, at full height", card.present and card.isVisible()
          and card.height() == card.full_height(), (card.present, card.height(), card.full_height()))
    w.grab().save(str(SHOTS / "library.png"))
    lib.filter_box.setText(offered.display_name[:3])
    settle(0.2)
    check("a search takes it off the page", not card.present and not card.isVisible())
    lib.filter_box.clear()
    settle(0.2)
    check("and it is back when the search is cleared", card.present and card.isVisible())
    lib.chips["favorites"].click()
    settle(0.2)
    check("any chip but All games takes it away too", not card.present)
    lib.chips["all"].click()
    settle(0.3)
    check("All games brings it back", card.present)

    card.play_button.click()
    check("Play starts that game (through the same path as the game page)",
          played == [offered.key], played)
    card.details_button.click()
    settle(0.3)
    check("Details opens its page", w.stack.currentIndex() == ui_window.DETAIL_PAGE
          and w.detail.view.key == offered.key)
    w.show_library()
    settle(0.4)
    body = card.card_rect()
    QTest.mouseClick(card, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     QPoint(round(body.right()) - 60, round(body.center().y())))
    settle(0.3)
    check("clicking the art itself opens the page too", w.stack.currentIndex() == ui_window.DETAIL_PAGE)
    w.show_library()
    settle(0.4)

    real_running = w.tracker.is_running
    w.tracker.is_running = lambda key: key == offered.key
    w.library.is_running = w.tracker.is_running
    w.refresh_running_state()
    check("while that game runs, Play becomes Stop", card.running
          and "Stop" in card.play_button.text() and card.play_button.objectName() == "HeroStop")
    card.play_button.click()
    check("and Stop stops it, not starts it again", stopped == [offered.key] and len(played) == 1)
    w.tracker.is_running = real_running
    w.library.is_running = real_running
    w.refresh_running_state()
    check("then it is Play again", not card.running and card.play_button.objectName() == "HeroPlay")

    print("\n=== 5. the card folds away as the grid scrolls ===")
    bar = lib.list.verticalScrollBar()
    check("there is enough library here to scroll", bar.maximum() > 300, bar.maximum())
    lib.scroll_to(min(bar.maximum(), 600))
    settle(0.8)
    check("scrolled down, the card is folded away", card.collapsed and card.height() == 0
          and not card.isVisible(), (card.collapsed, card.height()))
    check("and the scroll stayed where it was put, not thrown back to the top",
          bar.value() > round(ui_rules.CONTINUE_FOLD_AT * lib.metrics.scale), bar.value())
    w.grab().save(str(SHOTS / "scrolled.png"))
    lib.scroll_to(0)
    settle(0.8)
    check("back at the top, it unfolds", not card.collapsed and card.height() == card.full_height())

    print("\n=== 6. the pad reaches the card, and comes back ===")
    top_row = lib.list.visualItemRect(lib.list.item(0)).top()
    third = 2 if lib.list.visualItemRect(lib.list.item(2)).top() == top_row else 0
    lib.select_key(lib.visible_keys[third])
    settle(0.2)
    w._on_pad_action(controller.UP)
    settle(0.2)
    check("up from the top row lands on the card's Play", lib.on_card
          and card.focused_index == ui_continue.PLAY)
    check("with one ring on screen, not two: no tile stays selected",
          lib.list.currentRow() == -1 and not lib.list.selectedItems())
    check("and the backdrop turns to the card's game", w.backdrop.key == offered.key, w.backdrop.key)
    w.grab().save(str(SHOTS / "card_focus.png"))
    w._on_pad_action(controller.RIGHT)
    check("right moves to Details", card.focused_index == ui_continue.DETAILS)
    w._on_pad_action(controller.RIGHT)
    check("and stops there", card.focused_index == ui_continue.DETAILS)
    w._on_pad_action(controller.LEFT)
    check("left comes back to Play", card.focused_index == ui_continue.PLAY)
    played.clear()
    w._on_pad_action(controller.ACTIVATE)
    check("A on Play starts the game", played == [offered.key], played)
    menus.clear()
    w._on_pad_action(controller.MENU)
    check("X opens that game's menu", menus == [offered.key], menus)
    w._on_pad_action(controller.DOWN)
    check("down goes back to the very tile it came up from",
          not lib.on_card and lib.list.currentRow() == third, lib.list.currentRow())
    w._on_pad_action(controller.RIGHT)
    check("and the pad carries on across the grid", lib.list.currentRow() == third + 1)
    check("with the backdrop following it straight away",
          w.backdrop.key == lib.current_key(), (w.backdrop.key, lib.current_key()))
    lib.select_key(lib.visible_keys[min(len(lib.visible_keys) - 1, 9)])
    before = lib.list.currentRow()
    w._on_pad_action(controller.UP)
    check("up from a lower row moves up a row, not onto the card",
          not lib.on_card and lib.list.currentRow() < before)
    lib.select_key(lib.visible_keys[0])
    w._on_pad_action(controller.UP)
    lib.filter_box.setText(offered.display_name[:3])
    settle(0.2)
    check("if the card goes while the pad is on it, focus is back on the grid",
          not lib.on_card and lib.ensure_focus() and lib.list.currentRow() >= 0)
    lib.filter_box.clear()
    settle(0.2)
    lib.select_key(lib.visible_keys[0])
    lib.chips["favorites"].click()
    settle(0.2)
    if lib.list.count():
        lib.list.setCurrentRow(0)
        w._on_pad_action(controller.UP)
        check("with no card on the page, up at the top row stays on the grid", not lib.on_card)
    lib.chips["all"].click()
    settle(0.3)

    print("\n=== 7. the backdrop ===")
    lib.select_key(lib.visible_keys[1])
    settle(0.7)
    target = w.by_key[lib.visible_keys[1]]
    check("it shows the game in focus", w.backdrop.key == target.key)
    art = w.backdrop._current.toImage()
    plain = QColor(ui_rules.COLOR_BACKGROUND)
    probe = QPoint(art.width() // 2, art.height() // 6)
    check("and is tinted by that game's art, not the plain background",
          not close_to(pixel(art, probe), (plain.red(), plain.green(), plain.blue()), 2),
          pixel(art, probe))
    hovered = lib.visible_keys[4]
    lib._hover(lib.list.model().index(4, 0))
    settle(0.1)
    check("the mouse passing over a tile does not change it at once", w.backdrop.key == target.key)
    settle(0.5)
    check("resting on one does", w.backdrop.key == hovered, w.backdrop.key)
    lib._hover(None)
    w.show_stats()
    settle(0.7)
    # Changed on purpose in Phase 35: Stats and Storage are tabs of the library's place and
    # keep its glow. This used to assert the plain colour, which was step 2's state.
    check("Stats keeps the library's glow (Phase 35)", w.backdrop.key == hovered, w.backdrop.key)
    lit = w.backdrop._current.toImage()
    check("so it is not the plain colour",
          not close_to(pixel(lit, probe), (plain.red(), plain.green(), plain.blue()), 2))
    w.show_library()
    settle(0.7)
    check("and the library's glow comes back with the library", w.backdrop.key == hovered)
    w.backdrop.reduce_animations = True
    lib.select_key(lib.visible_keys[5])
    check("with Reduce animations it changes at once, without a fade",
          w.backdrop.key == lib.visible_keys[5] and not w.backdrop.fading)
    w.backdrop.reduce_animations = w.reduce_animations

    print("\n=== 8. the grid and the chips are see-through ===")
    lib.list.clearSelection()
    lib.list.setCurrentRow(-1)
    lib._hover(None)
    settle(0.7)
    view = lib.list
    first = view.visualItemRect(view.item(0))
    gap = QPoint(first.right() + max(1, lib.metrics.grid_spacing // 2) + 1, first.top() + 4)
    # Since Phase 55 the gaps between covers are part of the tiles' cells (the list adds
    # none), so the point is in a cell -- but on no cover, where nothing is painted.
    check("a point between two tiles is on no cover",
          not any(r.contains(gap) for r in lib._painted.values()), gap)
    at = view.viewport().mapTo(w.backdrop, gap)
    under = pixel(w.backdrop._current.toImage(), at)
    # The glow of whichever game the backdrop follows can be dark at exactly this point -- after
    # the user's library changed in October the one it followed was -- and then the window would
    # read the same see-through or not. So the check glows a game whose art is not the plain
    # colour there, if the one it follows is (Phase 92: the same lesson as suite 56's in Phase 63).
    for key in lib.visible_keys:
        if not close_to(under, (plain.red(), plain.green(), plain.blue()), 2):
            break
        w.backdrop.set_view(w.by_key.get(key), animate=False)
        settle(0.1)
        under = pixel(w.backdrop._current.toImage(), at)
    shot = w.grab().toImage()
    check("the backdrop there is not the plain colour, so the check can tell",
          not close_to(under, (plain.red(), plain.green(), plain.blue()), 2), under)
    check("and the window shows the backdrop there, not an opaque grid",
          close_to(pixel(shot, view.viewport().mapTo(w, gap)), under), (pixel(shot, view.viewport().mapTo(w, gap)), under))
    chips_gap = lib.chips_bar.rect().center()
    check("the same between the chips and the sort box",
          close_to(pixel(shot, lib.chips_bar.mapTo(w, chips_gap)),
                   pixel(w.backdrop._current.toImage(), lib.chips_bar.mapTo(w.backdrop, chips_gap))))

    print("\n=== 9. the tiles ===")
    row = 1
    rect = view.visualItemRect(view.item(row))
    metrics = lib.metrics
    cover_left = rect.x() + (rect.width() - metrics.cover_width) // 2
    strip = (cover_left - 8, cover_left + 8, rect.y() + metrics.tile_padding + metrics.cover_height // 3,
             rect.y() + metrics.tile_padding + 2 * metrics.cover_height // 3)

    ring_colour = QColor(ui_rules.TILE_FOCUS_COLOR)  # white until Phase 54, accent 200 since
    ring_rgb = (ring_colour.red(), ring_colour.green(), ring_colour.blue())

    def ring_in_strip():
        image = view.viewport().grab().toImage()
        return sum(1 for x in range(strip[0], strip[1]) for y in range(strip[2], strip[3], 2)
                   if max(abs(a - b) for a, b in zip(pixel(image, QPoint(x, y)), ring_rgb)) < 20)

    view.setCurrentRow(3)
    settle(0.3)
    plain_edge = ring_in_strip()
    view.setCurrentRow(row)
    settle(0.3)
    ringed_edge = ring_in_strip()
    check("the focused tile wears a ring in the focus colour", ringed_edge > plain_edge + 20,
          (plain_edge, ringed_edge))
    view.setCurrentRow(3)
    settle(0.3)
    image = view.viewport().grab().toImage()
    below = QPoint(rect.center().x(), rect.y() + metrics.tile_padding + metrics.cover_height
                   + round(ui_rules.TILE_SHADOW_DY * metrics.scale) // 2 + 2)
    backdrop_there = pixel(w.backdrop._current.toImage(), view.viewport().mapTo(w.backdrop, below))
    tile_there = pixel(image, below)
    check("and every tile casts a shadow just under its art",
          sum(tile_there) < sum(backdrop_there) - 6, (tile_there, backdrop_there))
    view.viewport().grab().save(str(SHOTS / "tiles.png"))
    started = time.perf_counter()
    for _ in range(20):
        view.viewport().repaint()
    per_frame = (time.perf_counter() - started) / 20 * 1000
    print(f"         (a full repaint of the grid takes {per_frame:.1f} ms)")
    check("a full repaint of the grid fits well inside one frame", per_frame < 16, per_frame)

    print("\n=== 10. TV mode ===")
    w.showFullScreen = lambda: None
    w.showNormal = lambda: None
    w.set_tv_mode(True)
    w.resize(1920, 1080)
    settle(0.6)
    tv = float(w.config.get("tv_scale", ui_rules.TV_SCALE_DEFAULT))
    check("the card scales with TV mode's size",
          # No room for a shadow since Phase 56: the card is edged with a hairline instead.
          card.full_height() == round((ui_rules.CONTINUE_HEIGHT + ui_rules.CONTINUE_GAP) * tv)
          and card.height() == card.full_height(), (card.height(), card.full_height(), tv))
    # Drawn by the card outside its buttons since Phase 56, at the tiles' width.
    ring = max(1, round(ui_rules.TV_FOCUS_RING_WIDTH * tv))
    check("and its buttons get TV mode's thicker focus ring", card.ring_width() == ring,
          (card.ring_width(), ring))
    lib.select_key(lib.visible_keys[0])
    w._on_pad_action(controller.UP)
    settle(0.3)
    w.grab().save(str(SHOTS / "tv.png"))
    check("the pad reaches the card in TV mode too", lib.on_card)
    w._on_pad_action(controller.DOWN)
    w.set_tv_mode(False)
    w.close()

finally:
    ui_actions.play, ui_actions.stop = real_play, real_stop
    for window in windows:
        try:
            window.close()
        except RuntimeError:
            pass
    print("\n=== 11. the real library is exactly as it was found ===")
    changed = box.finish()
    check("overrides.json, config.json and catalog.json are byte for byte unchanged", not changed,
          changed)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
