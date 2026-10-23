"""Phase 35: the redesign's last step -- Stats, Storage and Settings to match, then TV mode.

Runs against a throwaway copy of the data (test_sandbox), with parts of the real cache
copied in read only so Steam pages look as they do on this machine. A window is shown
throughout. Nothing starts a game. The last section checks covers at the TV's 225% in a
second process, since the scale has to be set before Qt starts.
"""
import os
import re
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # the project folder, one up from tests/
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import sources
import test_sandbox

box = test_sandbox.start()
REAL_SHOTS = Path(__file__).resolve().parents[1] / "data" / "cache" / "screenshots"
box.copy_cache("steam_details", "steam_news.json", "steam_web.json",
               *[f"screenshots/{name}" for name in (os.listdir(REAL_SHOTS) if REAL_SHOTS.is_dir() else [])])
print(f"real screenshots copied into the sandbox: {len(list((Path(box.folder) / 'cache' / 'screenshots').glob('*')))}")

import logging

logging.basicConfig(level=logging.ERROR)

from PySide6.QtCore import QEventLoop, QPoint, Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QLabel

app = QApplication([])

from adapters import controller
from shared import rules
from presentation import ui_actions
from presentation import ui_cards
from presentation import ui_rules
from presentation import ui_settings
from presentation import ui_stats
from presentation import ui_theme
from presentation import ui_tv
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


def pixel(image, point):
    c = image.pixelColor(point)
    return c.red(), c.green(), c.blue()


def close_to(a, b, slack=6):
    return all(abs(x - y) <= slack for x, y in zip(a, b))


def brightness(rgb):
    return sum(rgb) / 3


# White until Phase 55; the accent since, the design's ring for every control.
FOCUS_RGB = (QColor(ui_rules.TILE_FOCUS_COLOR).red(), QColor(ui_rules.TILE_FOCUS_COLOR).green(),
             QColor(ui_rules.TILE_FOCUS_COLOR).blue())


played = []
real_play = ui_actions.play
ui_actions.play = lambda window, view: played.append(view.key)

print(f"\nsandbox data folder: {box.folder}")

try:
    w = ui_window.MainWindow()
    windows.append(w)
    w.showFullScreen = lambda: None  # TV mode is checked inside this window, not over the desk
    w.showNormal = lambda: None
    w.resize(1600, 950)
    w.move(app.primaryScreen().availableGeometry().topLeft())
    w.show()
    settle(1.6)
    lib = w.library
    plain = QColor(ui_rules.COLOR_BACKGROUND)
    plain_rgb = (plain.red(), plain.green(), plain.blue())

    print("\n=== 1. Stats and Storage keep the library's glow ===")
    # The design's backdrop (Phase 55) is faint -- the art at 35%, gone by 62% of the way
    # down -- and a dark cover's glow between two cards can be within a shade of the plain
    # colour. The brightest glow in the library keeps the see-through check able to tell.
    def glow_of(key):
        tiny = w.backdrop._tiny_for(w.by_key[key])
        return 0 if tiny is None else sum(QColor(tiny.pixel(x, y)).lightness()
                                          for x in range(tiny.width()) for y in range(tiny.height()))
    lib.select_key(max(lib.visible_keys, key=glow_of))
    settle(0.8)
    glow_key = lib.backdrop_key()
    check("the library shows a game's glow to begin with", w.backdrop.key == glow_key and glow_key)
    w.show_stats()
    settle(0.9)
    check("Stats keeps it", w.backdrop.key == glow_key, (w.backdrop.key, glow_key))
    stats = w.stats_page
    # Between the top two figures: the design's backdrop (Phase 55) has faded fully into the
    # ground by 62% of the way down, which is where Most played and its neighbour sit.
    left, right = stats.cards["week"], stats.cards["month"]
    gap = QPoint((left.mapTo(w.backdrop, QPoint(left.width(), 0)).x()
                  + right.mapTo(w.backdrop, QPoint(0, 0)).x()) // 2,
                 left.mapTo(w.backdrop, QPoint(0, left.height() // 2)).y())
    glow = pixel(w.backdrop._current.toImage(), gap)
    shot = w.grab().toImage()
    check("between two cards the glow is not the plain colour", not close_to(glow, plain_rgb, 2), glow)
    check("and the window shows it there -- the page is see-through",
          close_to(pixel(shot, w.backdrop.mapTo(w, gap)), glow), (pixel(shot, w.backdrop.mapTo(w, gap)), glow))
    w.show_storage()
    settle(0.9)
    check("Storage keeps it too", w.backdrop.key == glow_key, (w.backdrop.key, glow_key))
    w.show_detail(lib.visible_keys[5])
    settle(1.2)
    check("a game's page still glows in that game's colours",
          w.backdrop.key == lib.visible_keys[5], w.backdrop.key)
    w.show_stats()
    settle(0.9)
    check("and Stats afterwards goes back to the library's, not the page's",
          w.backdrop.key == lib.backdrop_key(), (w.backdrop.key, lib.backdrop_key()))

    print("\n=== 2. Stats is built from cards ===")
    for name, card in stats.cards.items():
        pixmap = card.icon.pixmap()
        check(f"the '{card.caption.text()}' card has its icon",
              card.icon.isVisibleTo(stats) and pixmap is not None and not pixmap.isNull())
    for card in (stats.chart_card, stats.played_card, stats.library_card, stats.caveat_card):
        check(f"'{card.title.text()}' is a card", isinstance(card, ui_cards.Card) and card.isVisibleTo(stats))
    # A bar beside each until Phase 58; the design lists each game with its cover instead.
    thumbs = [stats.played_grid.itemAtPosition(row, 0).widget()
              for row in range(stats.played_grid.rowCount())
              if stats.played_grid.itemAtPosition(row, 0) is not None]
    names = sum(1 for row in range(stats.played_grid.rowCount())
                if stats.played_grid.itemAtPosition(row, 1) is not None)
    check("every most-played game has its cover beside it",
          thumbs and len(thumbs) == names and all(t.objectName() == "Thumb" for t in thumbs),
          (len(thumbs), names))
    check("the design's 18 x 27",
          thumbs and all((t.width(), t.height()) == (round(ui_rules.STATS_THUMB_WIDTH * w.scale),
                                                     round(ui_rules.STATS_THUMB_HEIGHT * w.scale)) for t in thumbs),
          [(t.width(), t.height()) for t in thumbs])
    picture = thumbs[0].pixmap().toImage() if thumbs else None
    check("a cover is really drawn: its middle is lit, not see-through",
          picture is not None and picture.pixelColor(picture.width() // 2, picture.height() // 2).alpha() > 200)

    print("\n=== 3. Storage: glass rows, a white ring, a pill ===")
    # The rows first painted solid black: QColor reads #AARRGGBB but not a stylesheet's
    # rgba(...), and an unreadable colour is black. Every colour handed to QColor from
    # ui_rules is checked here, not just that one.
    bad = []
    read = uses = 0
    using = set()
    for source in sources.python_files():  # every file of the project, wherever it lives
        read += 1
        for name in re.findall(r"QColor\(ui_rules\.([A-Z_0-9]+)\)", source.read_text(encoding="utf-8")):
            uses += 1
            using.add(source.name)
            value = getattr(ui_rules, name, None)
            if not isinstance(value, str) or not QColor(value).isValid():
                bad.append(f"{source.name}:{name}={value!r}")
    print(f"         (read {read} source files: {uses} colours from ui_rules in {len(using)} files)")
    check("every colour painted from ui_rules is one QColor can read", not bad, bad)
    row_colour = QColor(ui_rules.COLOR_STORAGE_ROW)
    text_rgb = QColor(ui_rules.COLOR_TEXT).rgb()  # white until Phase 54, the text colour since
    check("the rows' glass is the text colour, faint -- not black",
          row_colour.isValid() and (row_colour.rgb() & 0xFFFFFF) == (text_rgb & 0xFFFFFF)
          and 0 < row_colour.alpha() < 60,
          row_colour.name(QColor.NameFormat.HexArgb))
    w.show_storage()
    settle(0.9)
    page = w.storage_page
    current = page.list.currentItem()
    check("the page opens with the first game picked -- and selected, so it is ringed",
          current is not None and current.isSelected()
          and page.list.row(current) == next(r for r in range(page.list.count())
                                             if page.list.item(r).flags() & Qt.ItemFlag.ItemIsSelectable),
          (page.list.currentRow(), [page.list.row(i) for i in page.list.selectedItems()]))
    shot = w.grab().toImage()
    first = page.list.visualItemRect(current)
    ring = max(1, round(page.focus_ring_width * w.scale))
    # Each drive is a card since Phase 58, its rows in from its sides by the card's padding.
    inset = round(ui_rules.STORAGE_CARD_PADDING_X * w.scale)
    middle = first.top() + round(ui_rules.STORAGE_ROW_HEIGHT * w.scale) // 2
    edge = page.list.viewport().mapTo(w, QPoint(first.left() + inset + ring // 2, middle))
    # The focus colour, as on the tiles: white until Phase 55, the accent since.
    check("its ring is the focus colour, as on the tiles", close_to(pixel(shot, edge), FOCUS_RGB, 30),
          pixel(shot, edge))
    second = page.list.visualItemRect(page.list.item(page.list.row(current) + 1))
    middle2 = second.top() + round(ui_rules.STORAGE_ROW_HEIGHT * w.scale) // 2
    edge2 = page.list.viewport().mapTo(w, QPoint(second.left() + inset + ring // 2, middle2))
    check("a row that is not picked has no ring", brightness(pixel(shot, edge2)) < 200, pixel(shot, edge2))
    empty = page.list.viewport().mapTo(w, QPoint(second.right() - inset - 4, middle2))
    check("the empty end of a row is glass over the glow, not black",
          brightness(pixel(shot, empty)) > brightness((0, 0, 0)) + 15, pixel(shot, empty))
    check("the sort box is the library's pill", page.sort_box.objectName() == "SortBox"
          and page.sort_box.height() == max(20, round(ui_rules.CHIP_HEIGHT * w.scale)),
          page.sort_box.height())

    print("\n=== 4. Settings: sections, switches, the same answers ===")
    w.show_library()
    settle(0.6)
    config = dict(w.config, reduce_animations=False, tv_mode=False, enable_controller=True,
                  startup_scan=False, watch_folders=True, backup_saves=False, allow_network=True,
                  ui_scale=1.0, tv_scale=0.85)
    dialog = ui_settings.SettingsDialog(config, w, known_keys=set())
    dialog.show()
    settle(0.5)
    sections = [label.text() for label in dialog.findChildren(QLabel)
                if label.objectName() == "SettingSection"]
    # Phase 75 added "Steam accounts", before the library's data; Phase 77 "About", last; Phase 92
    # "Running in the background", after the controller's; Phase 102 "After a game", after it.
    check("ten sections, in order", sections == ["Look and feel", "Controller and TV",
                                                "Running in the background", "After a game", "Finding games",
                                                "Saves", "Artwork and the internet", "Steam accounts",
                                                "Your library data", "About"], sections)
    # Phase 60 added the side rail's switch, "library_layout"; the sandbox opens on the top bar.
    switches = [dialog.reduce_box, dialog.rail_box, dialog.controller_box, dialog.tv_box,
                dialog.startup_scan_box, dialog.watch_box, dialog.saves_box, dialog.network_box]
    check("every on/off setting is a switch", all(isinstance(s, ui_cards.ToggleSwitch) for s in switches))
    values = dialog.values()
    # Phase 77 added the game folders, "roots"; Phase 92 "keep_running"; Phase 93 "watch_games".
    # Phase 99 added the accent, "accent"; Phase 102 the question after a game, "ask_rating".
    check("values() answers with exactly the keys it always did, the side rail's, the game folders', "
          "Keep running's and the accent's",
          set(values) == {"reduce_animations", "ui_scale", "enable_controller", "tv_mode", "tv_scale",
                          "startup_scan", "watch_folders", "backup_saves", "allow_network",
                          "steamgriddb_key", "library_layout", "roots", "keep_running", "watch_games",
                          "accent", "ask_rating"}, sorted(values))
    check("and with what it was opened with",
          [values[k] for k in ("reduce_animations", "enable_controller", "tv_mode", "startup_scan",
                               "watch_folders", "backup_saves", "allow_network", "library_layout")]
          == [False, True, False, False, True, False, True, "top"])
    check("the switches are drawn where they are: on is right, off is left",
          dialog.controller_box._position == 1.0 and dialog.startup_scan_box._position == 0.0)
    row = next(r for r in dialog.findChildren(ui_settings.SettingRow) if r.switch is dialog.watch_box)
    QTest.mouseClick(row.hint, Qt.MouseButton.LeftButton)
    settle(0.3)
    check("clicking a row's words flips its switch", dialog.watch_box.isChecked() is False)
    check("and a click leaves no ring on it", not dialog.watch_box.hasFocus())
    before = dialog.startup_scan_box.isChecked()
    dialog.startup_scan_box.toggle()
    check("a switch slides when animations are on",
          dialog.startup_scan_box._slide.state() != dialog.startup_scan_box._slide.State.Stopped
          and 0.0 <= dialog.startup_scan_box._position < 1.0)
    settle(ui_rules.SWITCH_MS / 1000 + 0.2)
    check("and lands", dialog.startup_scan_box._position == 1.0 and dialog.startup_scan_box.isChecked() != before)
    for combo in (dialog.scale_box, dialog.tv_scale_box):
        check(f"the size box reading {combo.currentText()} is a pill",
              combo.objectName() == "SortBox"
              and combo.height() == max(20, round(ui_rules.CHIP_HEIGHT * dialog.scale)), combo.height())
    ringed = dialog.reduce_box
    check("opened at a desk, nothing counts as reached by keyboard, so no ring",
          not dialog.testAttribute(Qt.WidgetAttribute.WA_KeyboardFocusChange))
    plain_switch = dialog.grab().toImage()
    dialog.setAttribute(Qt.WidgetAttribute.WA_KeyboardFocusChange, True)
    # Since Phase 99 the dialog opens on the accent's swatches, the row above: a real Tab reaches the switch,
    # as the pad's moves do (a focus set in code with a Tab reason does not count as a keyboard move).
    QTest.keyClick(dialog.focusWidget(), Qt.Key.Key_Tab)
    settle(0.1)
    if dialog.focusWidget() is not ringed:
        ringed.setFocus(Qt.FocusReason.TabFocusReason)
    ringed.update()
    settle(0.2)
    ring_switch = dialog.grab().toImage()
    # Inside the track until Phase 58; the design's ring since, drawn by the dialog: 2 px
    # wide and 2 px out, so its middle is 3 px above the track's top edge.
    track_top = (ringed.height() - ringed.sizeHint().height()) // 2
    probe = ringed.mapTo(dialog, QPoint(ringed.sizeHint().width() // 2, track_top - 3))
    check("reached by keyboard or pad, it wears a ring in the focus colour, outside it",
          close_to(pixel(ring_switch, probe), FOCUS_RGB, 30)
          and not close_to(pixel(plain_switch, probe), FOCUS_RGB, 40),
          (pixel(plain_switch, probe), pixel(ring_switch, probe)))
    dialog.reject()
    settle(0.2)

    reduced = ui_settings.SettingsDialog(dict(config, reduce_animations=True), w, known_keys=set())
    reduced.show()
    settle(0.3)
    reduced.watch_box.toggle()
    check("with Reduce animations a switch jumps, it does not slide",
          reduced.watch_box._position in (0.0, 1.0)
          and reduced.watch_box._slide.state() == reduced.watch_box._slide.State.Stopped)
    reduced.reject()
    settle(0.2)

    print("\n=== 5. Settings never outgrows the screen, and follows the focus ===")
    big = ui_settings.SettingsDialog(dict(config, tv_mode=True, tv_scale=ui_rules.TV_SCALE_CHOICES[-1]),
                                     w, known_keys=set())
    big.show()
    settle(0.5)
    room = round(big.screen().availableGeometry().height() * ui_rules.SETTINGS_SCREEN_FRACTION)
    bar = big.scroll.verticalScrollBar()
    check("at the largest TV size it is capped to the screen", big.height() <= room + 1, (big.height(), room))
    check("and the sections scroll instead", bar.maximum() > 0, bar.maximum())
    # Since Phase 99 the first control is the accent's row: the chosen swatch.
    check("in TV mode it opens with the first control in focus -- the accent chosen -- ringed",
          big.focusWidget() is big.accent_swatches[big.accent()]
          and big.testAttribute(Qt.WidgetAttribute.WA_KeyboardFocusChange),
          (type(big.focusWidget()).__name__, big.testAttribute(Qt.WidgetAttribute.WA_KeyboardFocusChange),
           big._pad_first))
    big.import_button.setFocus(Qt.FocusReason.TabFocusReason)
    settle(0.2)
    spot = big.import_button.mapTo(big.scroll.viewport(), QPoint(0, 0))
    check("moving to the last button scrolls it into view",
          bar.value() > 0 and 0 <= spot.y() and spot.y() + big.import_button.height()
          <= big.scroll.viewport().height(), (bar.value(), spot.y()))
    big.reject()
    settle(0.2)

    print("\n=== 6. the pad works Settings in TV mode ===")
    w.set_tv_mode(True)
    w.resize(1707, 960)
    settle(1.0)
    check("the library's hints to begin with",
          w.hint_bar.labels == [label for _pad, label in ui_tv.HINT_SETS[ui_tv.LIBRARY]], w.hint_bar.labels)
    pad = w._on_pad_action
    seen = {}

    def inside_settings():
        dialog = QApplication.activeModalWidget()
        seen["hints"] = list(w.hint_bar.labels)
        # Since Phase 99 it opens on the accent's swatch, the first row; down goes on to the first switch.
        seen["focus"] = dialog.focusWidget() is dialog.accent_swatches[dialog.accent()]
        pad(controller.DOWN)
        seen["focus"] = seen["focus"] and dialog.focusWidget() is dialog.reduce_box
        before = dialog.reduce_box.isChecked()
        pad(controller.ACTIVATE)
        seen["a_flips"] = dialog.reduce_box.isChecked() != before and dialog.isVisible()
        pad(controller.ACTIVATE)
        pad(controller.DOWN)
        seen["down"] = dialog.focusWidget() is dialog.scale_box
        start = dialog.scale_box.currentIndex()
        pad(controller.RIGHT)
        seen["right"] = dialog.scale_box.currentIndex() == start + 1
        pad(controller.LEFT)
        seen["left"] = dialog.scale_box.currentIndex() == start
        pad(controller.ACTIVATE)
        QTimer.singleShot(400, lambda: in_the_list(dialog, start))

    def in_the_list(dialog, start):
        seen["list_open"] = QApplication.activePopupWidget() is not None
        pad(controller.DOWN)
        pad(controller.ACTIVATE)
        QTimer.singleShot(400, lambda: after_the_list(dialog, start))

    def after_the_list(dialog, start):
        seen["list_closed"] = QApplication.activePopupWidget() is None and dialog.isVisible()
        seen["picked"] = dialog.scale_box.currentIndex() == start + 1
        pad(controller.BACK)

    QTimer.singleShot(700, inside_settings)
    config_before = dict(w.config)
    w.open_settings()  # blocks until B cancels it
    settle(0.4)
    check("while it is open, the hints are the dialog's",
          seen.get("hints") == [label for _pad, label in ui_tv.HINT_SETS[ui_tv.DIALOG]], seen.get("hints"))
    check("it opens on the accent's swatch, and down reaches the first switch", seen.get("focus"))
    check("A flips the switch it is on and leaves the dialog open", seen.get("a_flips"))
    check("down moves to the next setting", seen.get("down"))
    check("right makes a size bigger, left smaller, without opening the list",
          seen.get("right") and seen.get("left"))
    check("A opens a drop-down's list", seen.get("list_open"))
    check("down and A pick from it, and only the list closes",
          seen.get("list_closed") and seen.get("picked"))
    check("B cancels: nothing chosen is kept", w.config.get("ui_scale") == config_before.get("ui_scale")
          and w.config.get("reduce_animations") == config_before.get("reduce_animations"))
    check("and the hints go back to the library's",
          w.hint_bar.labels == [label for _pad, label in ui_tv.HINT_SETS[ui_tv.LIBRARY]], w.hint_bar.labels)

    print("\n=== 7. the hints follow the page, a menu, a dialog ===")
    menu_hints = {}

    def read_menu():
        menu_hints["open"] = QApplication.activePopupWidget() is not None
        menu_hints["labels"] = list(w.hint_bar.labels)
        pad(controller.BACK)

    QTimer.singleShot(500, read_menu)
    w._context_menu(lib.visible_keys[0], w.mapToGlobal(QPoint(300, 300)))
    settle(0.3)
    check("with a game's menu open, they say how to work a menu",
          menu_hints.get("open") and menu_hints.get("labels")
          == [label for _pad, label in ui_tv.HINT_SETS[ui_tv.MENU]], menu_hints)
    check("and B closes it and puts the library's back",
          QApplication.activePopupWidget() is None
          and w.hint_bar.labels == [label for _pad, label in ui_tv.HINT_SETS[ui_tv.LIBRARY]])
    for opener, name in ((lambda: w.show_detail(lib.visible_keys[1]), ui_tv.DETAIL),
                         (w.show_stats, ui_tv.STATS), (w.show_storage, ui_tv.STORAGE),
                         (w.show_library, ui_tv.LIBRARY)):
        opener()
        settle(0.9)
        check(f"on the {name} page they are the {name} set",
              w.hint_bar.labels == [label for _pad, label in ui_tv.HINT_SETS[name]], w.hint_bar.labels)
    check("a game's page says A plays, not 'Select'", "Play" in ui_tv.HINT_SETS[ui_tv.DETAIL][0])
    heights = set()
    for scale in ui_rules.TV_SCALE_CHOICES:
        app.setStyleSheet(ui_theme.stylesheet(scale) + ui_tv.stylesheet(scale))
        bar = ui_tv.HintBar(ui_theme.Metrics(scale))
        bar.set_power(rules.POWER_WIRED)
        widest = 0
        for name in ui_tv.HINT_SETS:
            bar.set_hints(name)
            widest = max(widest, bar.sizeHint().width())
            heights.add((scale, bar.sizeHint().height()))
        check(f"every set fits a 1080p screen at {scale}x", widest <= 1920, widest)
        bar.setParent(None)
        bar.deleteLater()
    app.setStyleSheet("")
    by_scale = {}
    for scale, height in heights:
        by_scale.setdefault(scale, set()).add(height)
    check("changing the set never changes the bar's height", all(len(h) == 1 for h in by_scale.values()),
          by_scale)
    w.set_tv_mode(False)
    settle(0.6)

    print("\n=== 8. covers are made at the screen's density ===")
    check("on this 100% screen, at 1x", w.covers.ratio == 1.0, w.covers.ratio)
    view = w.by_key[lib.visible_keys[0]]
    one = w.covers.cover(view, 150, 225)
    w.covers.ratio = 2.0  # as if the window had just been dragged onto a denser screen...
    w._follow_density()  # ...and the window noticed it was not
    check("the window puts its own screen's density back", w.covers.ratio == 1.0)
    w.covers.ratio = 2.25
    two = w.covers.cover(view, 150, 225)
    check("a cover made at 2.25x has 2.25x the pixels, for the same size on screen",
          two.width() == round(150 * 2.25) and abs(two.devicePixelRatio() - 2.25) < 0.01
          and one.width() == 150, (one.width(), two.width(), two.devicePixelRatio()))
    w.covers.ratio = 1.0
    w.covers.clear()
    w.close()

    print("\n=== 9. and on the TV: 225% for real ===")
    child = Path(tempfile.gettempdir()) / "phase35_tv_density.py"
    child.write_text(textwrap.dedent(f"""
        import sys
        sys.path[:0] = [{str(HERE)!r}, {str(HERE / "tests")!r}]
        import test_sandbox
        box = test_sandbox.start()
        from PySide6.QtCore import QEventLoop, QTimer
        from PySide6.QtWidgets import QApplication
        app = QApplication([])
        from presentation import ui_window

        def settle(s):
            loop = QEventLoop(); QTimer.singleShot(round(s * 1000), loop.quit); loop.exec()

        w = ui_window.MainWindow()
        w.resize(1707, 960)
        w.move(app.primaryScreen().availableGeometry().topLeft())
        w.show()
        settle(1.5)
        key = w.library.visible_keys[0]
        cover = w.covers.cover(w.by_key[key], 150, 225)
        w.show_detail(key)
        settle(1.2)
        frame = w.detail.banner._pixmap_for(0)
        print("DENSITY", round(w.devicePixelRatioF(), 2), round(w.covers.ratio, 2),
              round(cover.devicePixelRatio(), 2), cover.width(),
              round(frame.devicePixelRatio(), 2) if frame else 0,
              frame.width() if frame else 0, w.detail.banner.width())
        w.close()
        print("CHANGED", box.finish())
    """), encoding="utf-8")
    environment = dict(os.environ, QT_SCALE_FACTOR="2.25")
    result = subprocess.run([sys.executable, str(child)], capture_output=True, text=True,
                            env=environment, timeout=180, cwd=str(HERE))
    lines = {line.split()[0]: line.split()[1:] for line in result.stdout.splitlines()
             if line.startswith(("DENSITY", "CHANGED"))}
    density = lines.get("DENSITY")
    if density:
        screen, made, cover_dpr, cover_w, frame_dpr, frame_w, banner_w = (float(v) for v in density)
        check("the TV test really ran at 225%", abs(screen - 2.25) < 0.01, screen)
        check("the window made its covers for it", abs(made - 2.25) < 0.01, made)
        check("a 150-wide cover is 338 real pixels, one to one on that screen",
              abs(cover_dpr - 2.25) < 0.01 and cover_w == round(150 * 2.25), (cover_dpr, cover_w))
        check("the game page's picture is made at 225% too",
              abs(frame_dpr - 2.25) < 0.01 and abs(frame_w - round(banner_w * 2.25)) <= 2,
              (frame_dpr, frame_w, banner_w))
    else:
        check("the TV check ran", False, result.stderr[-800:])
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

check("nothing was started", not played, played)
print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
