"""Phase 84: the Reports tab -- the seven reports as a page of the launcher.

  1. the tab: in the top bar and the side rail after Storage, with its icon; clicking either opens
     the page; the page keeps the library's glow, as Stats and Storage do;
  2. the pad: from the library View opens Stats, then right walks Storage and Reports and stops
     there, left walks back to Stats and on to the library; on Reports up and down scroll, B and
     View go back -- pressed the way the controller hub sends them, from inside a timer;
  3. the hints: a set for Reports, the tab walk said on Stats and Storage, every set inside 1920 at
     every TV size;
  4. the cards: seven, each with its sentence, its parts (the Lorenz curve, the bars, the tables),
     its caveat and its idea; an empty library's seven saying so in words; a library that cannot
     answer, one card saying what to do; equal answers rebuild nothing, a new answer rebuilds;
     every name escaped in a table;
  5. the time: the queries well inside 50 ms, a second visit building nothing;
  6. rendered at 100% and in TV mode: the column inside the window, nothing to scroll sideways, the
     cards on the window, the bars drawn; Escape goes back;
  7. CLAUDE.md, the layers; the real data untouched.

On a throwaway copy of the data; the network is blocked.
"""
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import sources  # the build log's notes (Phase 91)
import test_sandbox

box = test_sandbox.start()
attempts: list[str] = []


def no_network(request, *args, **kwargs):
    attempts.append(getattr(request, "full_url", str(request)))
    raise OSError("the network is blocked in this suite")


urllib.request.urlopen = no_network

import logging

logging.basicConfig(level=logging.CRITICAL)

from PySide6.QtCore import QEvent, QEventLoop, Qt, QTimer
from PySide6.QtGui import QColor, QKeyEvent
from PySide6.QtWidgets import QApplication, QLabel

app = QApplication(sys.argv)

from adapters import controller
from data_access import library_db
from shared import rules

try:
    from logic import reports as reports_module
    from presentation import ui_reports
except ImportError:  # the code before this phase has neither
    reports_module = ui_reports = None
from presentation import ui_icons, ui_rail, ui_rules, ui_topbar, ui_tv, ui_window

passed = failed = 0


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


def settle(seconds: float = 0.4) -> None:
    loop = QEventLoop()
    QTimer.singleShot(int(seconds * 1000), loop.quit)
    loop.exec()


def press(window, name: str, wait: float = 0.6) -> None:
    """A button as the hub sends it: emitted from inside a timer, queued to the window."""
    QTimer.singleShot(0, lambda: window.pads.action.emit(name))
    settle(wait)


def page(window) -> int:
    return window.stack.currentIndex()


window = ui_window.MainWindow()
window.resize(1280, 820)
window.show()
settle(1.0)
REPORTS = getattr(ui_window, "REPORTS_PAGE", -1)

print("=== 1. the tab ===")
try:
    names = [n for n, _l in ui_topbar.TABS]  # since Phase 87 the Wishlist follows Reports
    check("the top bar has Reports after Storage", names[names.index("storage") + 1] == "reports"
          and window.top_bar.tabs["reports"].text() == "Reports")
    check("and so has the side rail, with an icon of its own",
          [n for n, _l, _g in ui_rail.NAV][names.index("reports")] == "reports" and "reports" in ui_icons.PHOSPHOR
          and ui_icons.PHOSPHOR["reports"][1] == "presentation-chart")
    window.top_bar.tabs["reports"].click()
    settle(0.6)
    check("the top bar's tab opens the page", page(window) == REPORTS, page(window))
    check("its tab is lit, and the library's glow stays behind it",
          window.top_bar.tabs["reports"].isChecked()
          and window.backdrop._view is window.by_key.get(window.library.backdrop_key()))
    window.show_library()
    settle(0.6)
    window.config["library_layout"] = ui_rules.LAYOUT_RAIL
    window._apply_layout()
    settle(0.3)
    window.rail.places["reports"].click()
    settle(0.6)
    check("the rail's place opens it too, lit, the page carrying its name",
          page(window) == REPORTS and window.rail.places["reports"].isChecked()
          and window.reports_page.page_title.isVisible() and window.reports_page.page_title.text() == "Reports")
    window.config["library_layout"] = ui_rules.LAYOUT_TOP
    window._apply_layout()
    window.show_library()
    settle(0.6)
except Exception as exc:
    unreached("1", exc)

print("\n=== 2. the pad ===")
try:
    walk = []
    press(window, controller.STATS)
    walk.append(page(window))
    for _ in range(2):  # past Reports is the Wishlist since Phase 87 (its suite walks the five)
        press(window, controller.RIGHT)
        walk.append(page(window))
    check("View opens Stats; right walks Storage, then Reports",
          walk == [ui_window.STATS_PAGE, ui_window.STORAGE_PAGE, REPORTS], walk)
    bar = window.reports_page.scroll.verticalScrollBar()
    bar.setValue(0)
    press(window, controller.DOWN, 0.3)
    down = bar.value()
    press(window, controller.PAGE_DOWN, 0.3)
    paged = bar.value()
    press(window, controller.UP, 0.3)
    check("on Reports, down scrolls, a page down further, up back", 0 < down < paged and bar.value() < paged,
          (down, paged, bar.value()))
    back = []
    for _ in range(4):  # For you between Stats and the library since Phase 98
        press(window, controller.LEFT)
        back.append(page(window))
    check("left walks back: Storage, Stats, For you, the library",
          back == [ui_window.STORAGE_PAGE, ui_window.STATS_PAGE, getattr(ui_window, "FORYOU_PAGE", -1),
                   ui_window.LIBRARY_PAGE], back)
    window.show_reports()
    settle(0.6)
    press(window, controller.BACK)
    check("B goes back to the library", page(window) == ui_window.LIBRARY_PAGE, page(window))
    window.show_reports()
    settle(0.6)
    press(window, controller.STATS)
    check("and View does, as on Stats", page(window) == ui_window.LIBRARY_PAGE, page(window))
except Exception as exc:
    unreached("2", exc)

print("\n=== 3. the hints ===")
try:
    check("a set of its own: back, the tab walk, scroll, the library, settings",
          [label for _pad, label in ui_tv.HINT_SETS[ui_tv.REPORTS]]
          == ["Back", "Storage / Wishlist", "Scroll", "Library", "Settings"])  # the Wishlist since Phase 87
    check("Stats and Storage say where left and right go now",
          (ui_tv.ACROSS, "For you / Storage") in ui_tv.HINT_SETS[ui_tv.STATS]  # For you on its left since Phase 98
          and (ui_tv.ACROSS, "Stats / Reports") in ui_tv.HINT_SETS[ui_tv.STORAGE])
    window.set_tv_mode(True)
    settle(1.0)
    window.show_reports()
    settle(0.6)
    check("in TV mode, on the page, the bar shows the Reports set", window.hint_bar.hints == ui_tv.REPORTS,
          window.hint_bar.hints)
    widest, worst = 0, ""
    was = window.config.get("tv_scale")
    for scale in ui_rules.TV_SCALE_CHOICES:
        window.config["tv_scale"] = scale
        window.set_tv_mode(False)
        window.set_tv_mode(True)
        settle(0.2)
        for name in ui_tv.HINT_SETS:
            window.hint_bar.set_hints(name)
            app.processEvents()
            if window.hint_bar.sizeHint().width() > widest:
                widest, worst = window.hint_bar.sizeHint().width(), f"{name} at {scale}x"
    check(f"every set fits 1920 at every TV size (widest {widest} px: {worst})", widest <= 1920, widest)
    if was is None:  # the copy's config names no TV size: the default, as before
        window.config.pop("tv_scale", None)
    else:
        window.config["tv_scale"] = was
    window.set_tv_mode(False)
    settle(0.6)
except Exception as exc:
    unreached("3", exc)

print("\n=== 4. the cards ===")
try:
    window.show_reports()
    settle(0.6)
    reports_page = window.reports_page
    keys = [c.report.key for c in reports_page.cards]
    check("eleven cards (the eighth since Phase 89, the ninth since 98, the tenth since 102, the eleventh since 103), "
          "in the reports' order",
          keys == ["concentration", "abandonment", "profiles", "backlog", "sessions", "money", "quality", "preference",
                   "recommendation", "said_played", "finishing"],
          keys)
    check("each with its question, its sentence, what it cannot see and the idea",
          all(c.question.text() and c.sentence.text() and "What it cannot see." in c.caveat.text()
              and "The idea." in c.concept.text() for c in reports_page.cards))
    concentration = reports_page.card("concentration")
    check("the concentration card draws its Lorenz curve, from (0,0) to (1,1)",
          concentration.curve is not None and concentration.curve.points[0] == (0.0, 0.0)
          and concentration.curve.points[-1] == (1.0, 1.0))
    shares = [b for c in reports_page.cards for b in c.bars]
    check(f"{len(shares)} lists of shares drawn as bars; each bar as long as its share",
          len(shares) >= 8 and all(abs(b.bar_width(i) - b.bar_box().width() * row[1]) < 0.5
                                   for b in shares for i, row in enumerate(b.rows)))
    tables = [t for c in reports_page.cards for t in c.tables]
    check(f"{len(tables)} small tables, one label each", len(tables) >= 8 and all(t.textFormat() == Qt.TextFormat.RichText
                                                                                 for t in tables))
    built = reports_page.rebuilt
    window.show_stats()
    settle(0.4)
    window.show_reports()
    settle(0.4)
    check("shown again with the same answers: nothing rebuilt", reports_page.rebuilt == built,
          (built, reports_page.rebuilt))

    empty_store = library_db.LibraryStore(Path(tempfile.mkdtemp(prefix="phase84_")) / "empty.db")
    empty = reports_module.build(empty_store.reports())
    reports_page.set_reports(empty)
    settle(0.3)
    check("an empty library: eleven cards, each saying so in words, nothing else drawn",
          len(reports_page.cards) == 11 and all(c.report.empty and c.sentence.text() and not c.bars and not c.tables
                                               for c in reports_page.cards)
          and reports_page.rebuilt == built + 1)
    empty_store.close()
    reports_page.set_reports(None)
    settle(0.3)
    words = " ".join(label.text() for label in reports_page.cards[0].findChildren(QLabel))
    check("a library that cannot answer: one card saying what to do", len(reports_page.cards) == 1
          and "start the launcher again" in words, words)
    planted = reports_module.Report(1, "concentration", "Concentration", "q?", "s.", "c.", "i.", parts=(
        reports_module.Part("Planted", ("Game", "Hours"), (("<b>bold</b> & <script>x</script>", "1 h"),)),))
    reports_page.set_reports([planted])
    settle(0.3)
    html_text = reports_page.cards[0].tables[0].text()
    check("a name in a table is shown, never read as markup", "&lt;b&gt;bold&lt;/b&gt;" in html_text
          and "<script>" not in html_text, html_text[:200])
    window.show_reports()
    settle(0.6)
except Exception as exc:
    unreached("4", exc)

print("\n=== 5. the time ===")
try:
    source = window.overrides.reports()
    timings = []
    for _ in range(3):
        started = time.perf_counter()
        reports_module.build(source)
        timings.append(1000 * (time.perf_counter() - started))
    check(f"the eleven (since Phase 103) worked out in {min(timings):.0f} ms (best of 3), under 50", min(timings) < 50,
          timings)
    started = time.perf_counter()
    window.show_reports()
    app.processEvents()
    again = 1000 * (time.perf_counter() - started)
    check(f"a visit with nothing new: {again:.0f} ms, no card built", again < 150, again)
except Exception as exc:
    unreached("5", exc)

print("\n=== 6. rendered, at 100% and in TV mode ===")
try:
    for label, tv in (("100%", False), ("TV", True)):
        window.set_tv_mode(tv)
        settle(1.0)
        window.show_reports()
        settle(0.8)
        reports_page = window.reports_page
        viewport = reports_page.scroll.viewport()
        bar = reports_page.scroll.horizontalScrollBar()
        cards = reports_page.cards
        inside = all(c.mapTo(viewport, c.rect().topRight()).x() <= viewport.width() for c in cards)
        check(f"{label}: the cards inside the window, nothing to scroll sideways", inside and bar.maximum() == 0,
              (bar.maximum(), [c.width() for c in cards][:2], viewport.width()))
        picture = window.grab().toImage()
        first = cards[0]
        corner = first.mapTo(window, first.rect().center())
        ground = QColor(ui_rules.COLOR_BACKGROUND)
        sample = picture.pixelColor(corner.x(), corner.y())
        check(f"{label}: the first card drawn on the window, its surface not the ground",
              abs(sample.red() - ground.red()) + abs(sample.green() - ground.green()) > 6, (sample.name(), ground.name()))
        shares = cards[0].bars[0]
        middle = shares.mapTo(window, shares.bar_box().topLeft()).x() + 2
        row_y = shares.mapTo(window, shares.rect().topLeft()).y() + round(ui_rules.REPORT_BAR_ROW_HEIGHT * shares.scale / 2)
        lit = picture.pixelColor(int(middle), int(row_y))
        check(f"{label}: the first bar painted in the bars' colours", lit.blue() > lit.red() and lit.blue() > 80,
              lit.name())
        window.grab().save(str(Path(tempfile.gettempdir()) / f"phase84_{label.replace('%', '')}.png"))
    window.set_tv_mode(False)
    settle(0.8)
    window.show_reports()
    settle(0.5)
    QApplication.sendEvent(window.reports_page, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
    settle(0.6)
    check("Escape goes back to the library", page(window) == ui_window.LIBRARY_PAGE, page(window))
except Exception as exc:
    unreached("6", exc)

print("\n=== 7. the documents, the layers ===")
try:
    import subprocess
    claude = (PROJECT / "CLAUDE.md").read_text(encoding="utf-8")
    check("CLAUDE.md has the phase and its notes", "| 84 |" in claude and "## Phase 84 notes" in sources.build_log())
    layers = subprocess.run([sys.executable, str(PROJECT / "tests" / "check_layers.py")], capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    check("no import points up a layer; sqlite3 only in data_access/", layers.returncode == 0, layers.stdout[-300:])
    check("nothing in this suite reached the network", attempts == [], attempts)
except Exception as exc:
    unreached("7", exc)

while window.worker is not None and window.worker.isRunning():
    settle(0.2)
window.close()
settle(0.3)
window.overrides.close()

print("\n=== 8. the real library is exactly as it was found ===")
changed = box.finish()
check("config.json and the library database are unchanged", not changed, changed)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
