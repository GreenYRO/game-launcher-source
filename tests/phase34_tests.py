"""Phase 34: motion -- pages that arrive, a cover that flies, tiles that arrive, focus that glides.

Runs against a throwaway copy of the data (test_sandbox). A window is shown throughout,
because nothing here means anything on a hidden one: motion only runs where it can be seen.
Nothing starts a game. The last section measures frames at the TV's 225% in a second
process, since the scale has to be set before Qt starts.
"""
import os
import subprocess
import sys
import tempfile
import textwrap
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # the project folder, one up from tests/
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import test_sandbox

box = test_sandbox.start()
# The real cache, read only, so Steam pages have their descriptions and screenshots and some
# pages are long enough to scroll their cover out of sight (the Phase 33 approach).
REAL_SHOTS = Path(__file__).resolve().parents[1] / "data" / "cache" / "screenshots"
box.copy_cache("steam_details", "steam_news.json", "steam_web.json",
               *[f"screenshots/{name}" for name in (os.listdir(REAL_SHOTS) if REAL_SHOTS.is_dir() else [])])
print(f"real screenshots copied into the sandbox: {len(list((Path(box.folder) / 'cache' / 'screenshots').glob('*')))}")

import logging

logging.basicConfig(level=logging.ERROR)

from PySide6.QtCore import QEventLoop, QPoint, QRect, Qt, QTimer
from PySide6.QtWidgets import QApplication

app = QApplication([])

from adapters import controller
from logic import gamedetails
from presentation import ui_actions
from presentation import ui_motion
from presentation import ui_rules
from presentation import ui_window

HERE = Path(__file__).resolve().parents[1]
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


def near(a: QRect, b: QRect, slack=2):
    return (abs(a.x() - b.x()) <= slack and abs(a.y() - b.y()) <= slack
            and abs(a.width() - b.width()) <= slack and abs(a.height() - b.height()) <= slack)


def cost_ms(action, n=10):
    action()
    start = time.perf_counter()
    for _ in range(n):
        action()
    return (time.perf_counter() - start) / n * 1000


TRANSITION = ui_rules.PAGE_TRANSITION_MS / 1000 + 0.25
FLIGHT = ui_rules.COVER_FLIGHT_MS / 1000 + 0.3
WAVE = (ui_rules.TILE_ENTRANCE_STAGGERED * ui_rules.TILE_ENTRANCE_STAGGER_MS
        + ui_rules.TILE_ENTRANCE_MS) / 1000 + 0.3

played = []
real_play = ui_actions.play
ui_actions.play = lambda window, view: played.append(view.key)

print(f"\nsandbox data folder: {box.folder}")

try:
    w = ui_window.MainWindow()
    windows.append(w)
    w.resize(1500, 900)
    w.move(20, 20)
    w.show()
    settle(WAVE + 0.8)
    lib, page, shell = w.library, w.detail, w.centralWidget()

    print("\n=== 1. pages arrive across, from the side their tab is on ===")
    w.library.stats_button.click()
    motion = w.page_motion
    check("Stats is the current page at once -- only a picture of it is still moving",
          w.stack.currentIndex() == ui_window.STATS_PAGE and motion.running)
    check("it comes in from the right, the side its tab is on", motion.kind == ui_motion.FROM_RIGHT)
    stack_box = QRect(w.stack.mapTo(w.backdrop, QPoint(0, 0)), w.stack.size())
    check("the moving picture covers exactly the pages", motion.geometry() == stack_box,
          (motion.geometry(), stack_box))
    check("it is opaque, so nothing beneath it is drawn, and it never takes a click",
          motion.testAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
          and motion.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents))
    settle(0.06)
    travel = w.stack.width() * ui_rules.PAGE_SLIDE_FRACTION
    check("partway, it is partway across", motion.running and 0 < motion.offset().x() < travel,
          (motion.offset().x(), travel))
    frame = cost_ms(motion.repaint)
    print(f"         (one frame of it costs {frame:.1f} ms at this screen's scale)")
    check("a frame of it fits well inside one refresh", frame < 16, frame)
    order = shell.children()
    check("the message card stays above anything moving",
          order.index(w.toast) > order.index(motion) and order.index(w.toast) > order.index(w.flight))
    settle(TRANSITION)
    check("and then it is gone, leaving the real page", not motion.running)
    w._on_pad_action(controller.RIGHT)
    check("the pad's right to Storage comes in from the right too",
          w.stack.currentIndex() == ui_window.STORAGE_PAGE and motion.kind == ui_motion.FROM_RIGHT)
    settle(TRANSITION)
    w.library.stats_button.click()
    check("back to Stats comes in from the left", motion.kind == ui_motion.FROM_LEFT)
    w.top_bar.tabs["library"].click()
    check("a switch mid-way simply starts over for the newest page",
          motion.running and motion.kind == ui_motion.FROM_LEFT
          and w.stack.currentIndex() == ui_window.LIBRARY_PAGE)
    settle(TRANSITION + 0.3)

    print("\n=== 2. into a game from its tile: the cover flies ===")
    row = 2
    lib.list.setCurrentRow(row)
    settle(0.4)
    item = lib.list.item(row)
    key = item.data(Qt.ItemDataRole.UserRole)
    painted = lib._painted.get(row)
    viewport = lib.list.viewport()
    tile = QRect(viewport.mapTo(w.backdrop, painted.topLeft()), painted.size())
    lib._activate(item)
    flight = w.flight
    check("clicking a tile opens its page with the cover in the air",
          w.stack.currentIndex() == ui_window.DETAIL_PAGE and flight.flying)
    check("taking off from exactly where the tile drew it",
          near(flight._from.toAlignedRect(), tile), (flight._from, tile))
    check("while the page rises into place around it", motion.kind == ui_motion.RISE)
    check("and the page's own cover waits, so there is only ever one",
          page.cover_art.in_flight)
    settle(0.12)
    mid = flight.current().toAlignedRect()
    check("partway, it is between the two",
          tile.x() != mid.x() and flight.progress > 0 and flight.progress < 1, flight.progress)
    region = cost_ms(lambda: flight.repaint(flight._bounds()), n=5)
    print(f"         (repainting the ground a flying cover covers: {region:.1f} ms)")
    settle(FLIGHT)
    target = page.cover_rect_in(w.backdrop)
    check("it lands exactly on the page's cover", near(flight._to.toAlignedRect(), target),
          (flight._to, target))
    check("and then the page's cover is the one showing",
          not flight.flying and not page.cover_art.in_flight)

    print("\n=== 3. back out: home into its tile, when that tile is in view ===")
    page.scroll.verticalScrollBar().setValue(0)
    settle(0.2)
    start = page.cover_rect_in(w.backdrop)
    w.show_library()
    check("Back sends the cover home", flight.flying and near(flight._from.toAlignedRect(), start),
          (flight._from, start))
    check("the grid leaves that tile's cover out until it lands", lib.flying_key == key)
    check("and the grid fades in where it is, rather than sliding",
          motion.kind == ui_motion.FADE)
    settle(FLIGHT)
    home = lib.tile_cover_rect(key, w.backdrop)
    check("it lands exactly on the tile", home is not None and near(flight._to.toAlignedRect(), home),
          (flight._to, home))
    check("and the tile has its cover back", not flight.flying and lib.flying_key == "")
    long_page = next((v for v in w.views if v.key in lib.visible_keys and gamedetails.screenshots(
        gamedetails.record_for(v), ui_rules.SCREENSHOT_MAX_PER_GAME)), None)
    if long_page is not None:
        w.show_detail(long_page.key)
        settle(TRANSITION + 0.3)
        page.scroll.verticalScrollBar().setValue(page.scroll.verticalScrollBar().maximum())
        settle(0.2)
        check("(a long page, scrolled to its foot, has its cover out of sight)",
              not page.cover_on_screen(), page.scroll.verticalScrollBar().maximum())
        w.show_library()
        check("with the cover out of sight, nothing flies home -- it would come in from nowhere",
              not flight.flying and lib.flying_key == "")
    else:
        print("         (no page here is long enough to scroll its cover away; skipped)")
    settle(TRANSITION)

    print("\n=== 4. other ways into a game arrive without a flight ===")
    lib.select_key(lib.visible_keys[0])
    settle(0.3)
    w._on_pad_action(controller.ACTIVATE)
    check("A on a tile flies its cover too, from the couch as from the desk", flight.flying)
    settle(FLIGHT)
    w.show_library()
    settle(FLIGHT)
    if lib.card.view is not None and lib.card.present:
        lib.card.details_button.click()
        check("the Continue playing card's Details opens the page without one",
              w.stack.currentIndex() == ui_window.DETAIL_PAGE and not flight.flying
              and motion.kind == ui_motion.RISE)
        settle(TRANSITION)
        w.show_library()
        settle(FLIGHT)
    w.play_something()
    check("and so does Play something", not flight.flying and not page.cover_art.in_flight)
    settle(TRANSITION)
    first = page.view.key
    w._on_pad_action(controller.RIGHT)
    check("the next game slides in from the right", motion.running and motion.kind == ui_motion.FROM_RIGHT
          and page.view.key != first)
    check("with the glow switched at once underneath, not fading as well",
          not w.backdrop.fading)
    settle(TRANSITION)
    w._on_pad_action(controller.LEFT)
    check("the previous one from the left", motion.kind == ui_motion.FROM_LEFT and page.view.key == first)
    settle(TRANSITION)
    w.show_library()
    settle(FLIGHT)
    lib.list.setCurrentRow(row)
    settle(0.3)
    lib._activate(lib.list.item(row))
    settle(0.05)
    before = QRect(flight._from.toAlignedRect())
    lib._activate(lib.list.item(row))  # the second half of a double click
    check("a double click opens the page once and does not start a second flight",
          flight.flying and near(flight._from.toAlignedRect(), before))
    settle(FLIGHT)
    w.show_library()
    settle(FLIGHT)

    print("\n=== 5. the tiles arrive in a wave ===")
    lib.chips["favorites"].click()
    lib.chips["all"].click()
    check("changing the chip brings the tiles in again", lib.entrance_running)
    settle(0.12)
    now = [lib.appear_progress(r) for r in (0, 6, 12)]
    check("in a wave: the first tiles are further in than the later ones",
          now[0] >= now[1] >= now[2] and now[0] > now[2], now)
    during = cost_ms(viewport.repaint, n=6)
    print(f"         (a frame of the grid mid-wave: {during:.1f} ms)")
    check("a frame of the wave is as cheap as any other", during < 16, during)
    settle(WAVE)
    check("and then every tile is fully there", not lib.entrance_running
          and all(lib.appear_progress(r) == 1.0 for r in range(lib.list.count())))
    lib.sort_box.setCurrentText("Name" if lib.sort_box.currentText() != "Name" else "Last played")
    check("picking a sort does too", lib.entrance_running)
    settle(WAVE)
    lib.set_sort("Recently added")
    check("putting a remembered sort back does not", not lib.entrance_running)
    lib.list.setCurrentRow(1)
    settle(0.4)
    w.reload_views()
    check("nor does a background refresh -- the kind that runs every minute during a game",
          not lib.entrance_running)
    check("and the focused tile stays put through it, rather than dropping and rising again",
          lib.focus_progress(lib.list.currentRow()) == 1.0)
    fresh = ui_window.MainWindow()
    windows.append(fresh)
    fresh.resize(1200, 800)
    fresh.show()
    settle(0.1)
    check("a window's first appearance brings them in", fresh.library.entrance_running)
    fresh.close()

    print("\n=== 6. focus glides ===")
    lib.list.setCurrentRow(2)
    settle(0.4)
    width_before = lib._painted[3].width()
    w._on_pad_action(controller.RIGHT)
    # Watched, not sampled once: a single look 30 ms in failed twice in full runs, on a busy
    # machine, before the glide's first tick had come round -- and passed every run alone.
    # What matters is that both tiles pass through the middle, not when the look lands.
    gliding = False
    seen_values = []
    for _ in range(max(2, ui_rules.FOCUS_DURATION_MS // 2 // 10)):
        settle(0.01)
        seen_values.append((round(lib.focus_progress(3), 2), round(lib.focus_progress(2), 2)))
        if 0 < lib.focus_progress(3) < 1 and 0 < lib.focus_progress(2) < 1:
            gliding = True
            break
    check("moving right, the new tile is on its way in and the old one on its way out",
          gliding, seen_values[-5:])
    settle(ui_rules.FOCUS_DURATION_MS / 1000 + 0.2)
    check("and then it has arrived, and the old one has settled",
          lib.focus_progress(3) == 1.0 and lib.focus_progress(2) == 0.0)
    check("the tile it reached has grown", lib._painted[3].width() > width_before,
          (width_before, lib._painted[3].width()))
    w.show_detail(lib.visible_keys[5])
    settle(TRANSITION)
    w._on_pad_action(controller.RIGHT)  # the next game, which moves the grid's selection too
    check("moved while the grid is out of sight, focus is simply there, nothing replays",
          lib.list.currentRow() == 6 and lib.focus_progress(6) == 1.0 and not lib._focus,
          (lib.list.currentRow(), dict(lib._focus)))
    settle(TRANSITION)
    w.show_library()
    settle(FLIGHT)

    print("\n=== 7. Reduce animations turns all of it off ===")
    w.reduce_animations = True
    w.set_tv_mode(False)
    settle(0.3)
    w.library.stats_button.click()
    check("pages simply appear", not motion.running and w.stack.currentIndex() == ui_window.STATS_PAGE)
    w.show_library()
    lib.list.setCurrentRow(1)
    lib._activate(lib.list.item(1))
    check("covers do not fly", not flight.flying and not page.cover_art.in_flight)
    w.show_library()
    check("nor home", not flight.flying and lib.flying_key == "")
    lib.chips["favorites"].click()
    lib.chips["all"].click()
    check("tiles are simply there", not lib.entrance_running and lib.appear_progress(0) == 1.0)
    lib.list.setCurrentRow(0)
    w._on_pad_action(controller.RIGHT)
    check("and focus jumps straight to the next tile", lib.focus_progress(1) == 1.0
          and lib.focus_progress(0) == 0.0)
    w.reduce_animations = False
    w.set_tv_mode(False)
    settle(0.5)

    print("\n=== 8. a resize ends any motion at once ===")
    w.library.stats_button.click()
    w.resize(1400, 880)
    settle(0.05)
    check("a page mid-arrival just arrives", not motion.running)
    w.show_library()
    settle(TRANSITION)
    lib.list.setCurrentRow(1)
    settle(0.3)
    lib._activate(lib.list.item(1))
    w.resize(1500, 900)
    settle(0.05)
    check("a cover in flight lands, and the page's own is shown",
          not flight.flying and not page.cover_art.in_flight)
    w.show_library()
    settle(FLIGHT)
    w.close()

    print("\n=== 9. and on the TV: frames at 225% ===")
    child = Path(tempfile.gettempdir()) / "phase34_tv_frames.py"
    child.write_text(textwrap.dedent(f"""
        import sys, time
        sys.path[:0] = [{str(HERE)!r}, {str(HERE / "tests")!r}]
        import test_sandbox
        box = test_sandbox.start()
        from PySide6.QtCore import QEventLoop, QTimer
        from PySide6.QtWidgets import QApplication
        app = QApplication([])
        from presentation import ui_window

        def settle(s):
            loop = QEventLoop(); QTimer.singleShot(round(s * 1000), loop.quit); loop.exec()

        def cost(action, n=8):
            action()
            start = time.perf_counter()
            for _ in range(n):
                action()
            return (time.perf_counter() - start) / n * 1000

        w = ui_window.MainWindow()
        w.resize(1707, 960)
        # On the main monitor, whatever window place the real config remembers: if that is
        # the TV, its own 225% multiplies with this one (a run measured at 5.06x that way).
        w.move(app.primaryScreen().availableGeometry().topLeft())
        w.show()
        settle(1.5)
        w.library.stats_button.click()
        page = cost(w.page_motion.repaint)
        settle(0.6)
        w.show_library()
        settle(0.6)
        lib = w.library
        lib.list.setCurrentRow(2)
        settle(0.3)
        lib._activate(lib.list.item(2))
        flight = cost(lambda: w.flight.repaint(w.flight._bounds()))
        settle(0.8)
        w.show_library()
        settle(0.8)
        lib.chips["favorites"].click()
        lib.chips["all"].click()
        settle(0.05)
        wave = cost(lib.list.viewport().repaint)
        print("FRAMES", round(w.devicePixelRatioF(), 2), round(page, 1), round(flight, 1), round(wave, 1))
        w.close()
        print("CHANGED", box.finish())
    """), encoding="utf-8")
    environment = dict(os.environ, QT_SCALE_FACTOR="2.25")
    result = subprocess.run([sys.executable, str(child)], capture_output=True, text=True,
                            env=environment, timeout=180, cwd=str(HERE))
    lines = {line.split()[0]: line.split()[1:] for line in result.stdout.splitlines()
             if line.startswith(("FRAMES", "CHANGED"))}
    frames = lines.get("FRAMES")
    if frames:
        ratio, page_ms, flight_ms, wave_ms = (float(value) for value in frames)
        print(f"         (at {ratio}x: a page arriving {page_ms} ms, a cover flying {flight_ms} ms, "
              f"the tile wave {wave_ms} ms per frame)")
        check("the TV test really ran at 225%", abs(ratio - 2.25) < 0.01, ratio)
        check("a page arriving stays above 30 frames a second there", page_ms < 33, page_ms)
        check("a flying cover costs a small part of a frame there", flight_ms < 16, flight_ms)
        check("and the tile wave stays above 50 frames a second", wave_ms < 20, wave_ms)
    else:
        check("the TV measurement ran", False, result.stderr[-800:])
    check("and it touched nothing real either", lines.get("CHANGED") == ["[]"], lines.get("CHANGED"))
    child.unlink(missing_ok=True)

finally:
    ui_actions.play = real_play
    for window in windows:
        try:
            window.close()
        except RuntimeError:
            pass
    print("\n=== 10. the real library is exactly as it was found ===")
    changed = box.finish()
    check("overrides.json, config.json and catalog.json are byte for byte unchanged", not changed,
          changed)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
