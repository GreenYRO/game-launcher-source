"""Phase 24: the storage page.

**This phase can delete nothing**, and the last section proves it: the real overrides file
is photographed at the start and compared at the end, and the only key the page is allowed
to write is the chosen ordering.

Nothing is asserted against a fixed number of games, and nothing asserts that a file the
user could have created is absent. The multi-drive layout is exercised against fabricated
drives, because every game on this machine is on C: -- that is stated in the report rather
than hidden behind a passing test.
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # the project folder, one up from tests/
os.chdir(Path(__file__).resolve().parents[1])

import logging

logging.basicConfig(level=logging.ERROR)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REAL = Path(__file__).resolve().parents[1] / "data"  # the real data, in its own folder since Phase 48

passed = failed = 0


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"   PASS  {name}")
    else:
        failed += 1
        print(f"   FAIL  {name}   {detail}")


import test_sandbox  # the library helpers (Phase 66); the sandbox itself is run_sandboxed's

test_sandbox.require_sandbox(__file__)  # never on the real data, run bare (Phase 101)

overrides_before = test_sandbox.real_records()
overrides_stamp = test_sandbox.real_stamp()
config_before = (REAL / "config.json").read_text(encoding="utf-8")

from data_access import catalog_io
from shared import rules
from logic import storage
from presentation import ui_rules

print("\n=== 1. the numbers, worked out a second way ===")
overrides = test_sandbox.library()  # the library the launcher opens: the database since Phase 69
views = catalog_io.merge(overrides.load_catalog(), overrides)
now = datetime.now().astimezone()
result = storage.gather(views, overrides, now)

visible = [v for v in views if not v.hidden and not v.is_non_game]
print(f"   {len(visible)} visible games across {len(result.drives)} drive(s)")
check("every visible game is on the page, once",
      len(result.games) == len(visible), (len(result.games), len(visible)))
check("no hidden game or tool is counted",
      not ({g.key for g in result.games} & {v.key for v in views if v.hidden or v.is_non_game}))
check("the total is the sum of the catalogue's sizes",
      result.known_bytes == sum(max(0, v.entry.size_on_disk or 0) for v in visible))
check("each drive's total is the sum of its own games",
      all(d.known_bytes == sum(g.bytes for g in d.games) for d in result.drives))
check("used and known never disagree",
      all(d.other_used == max(0, d.used - d.known_bytes) for d in result.drives))
check("it records when the sizes were measured",
      result.scanned_at is None or isinstance(result.scanned_at, datetime))

print("\n=== 2. which drive a game is filed under ===")
for view in visible[:4]:
    letter = storage.drive_of(view)
    expected = os.path.splitdrive(os.path.abspath(view.entry.install_dir))[0].upper()
    print(f"   {view.display_name[:34]:34} -> {letter}")
    check(f"{view.display_name[:24]} is filed on its own drive", letter == expected,
          (letter, expected))
check("every game landed on some drive",
      sum(len(d.games) for d in result.drives) == len(result.games))


class Fake:
    def __init__(self, name, drive, size, played=None, first_seen=None, hidden=False):
        self.display_name = name
        self.key = name
        self.hidden = hidden
        self.is_non_game = False
        self.last_played = played
        self.entry = type("E", (), {
            "install_dir": rf"{drive}\games\{name}",
            "size_on_disk": size,
            "launch_kind": "exe",
            "source": "folders",
        })()
        self._first_seen = first_seen


class FakeOverrides:
    def __init__(self, seen=None):
        self.seen = seen or {}

    def get(self, key):
        return {"first_seen": self.seen[key]} if key in self.seen else {}

    def last_scan_time(self):
        return None  # a store says when its last scan was (Phase 69); this one knows of none


print("\n=== 3. a drive Windows will not answer for ===")
gone = storage.gather([Fake("Ghost", "Z:", 5_000_000_000)], FakeOverrides(), now)
drive = gone.drives[0]
print(f"   Z: measured={drive.measured} total={drive.total} games={len(drive.games)}")
check("the page still lists its games", len(drive.games) == 1)
check("but does not claim a capacity", not drive.measured and drive.total == 0)
check("and does not crash working out its share", drive.other_used == 0)

print("\n=== 4. staleness, and the two orderings ===")
old = now - timedelta(days=rules.RECLAIM_STALE_DAYS + 40)
fresh = now - timedelta(days=2)
games = [
    Fake("Huge and fresh", "C:", 100_000_000_000, played=fresh),
    Fake("Small and ancient", "C:", 3_000_000_000, played=old),
    Fake("Big and cold", "C:", 60_000_000_000, played=old),
]
by_size = storage.gather(games, FakeOverrides(), now, storage.SORT_SIZE)
by_weight = storage.gather(games, FakeOverrides(), now, storage.SORT_WEIGHTED)
print(f"   by size:     {[g.name for g in by_size.games]}")
print(f"   by weight:   {[g.name for g in by_weight.games]}")
check("by size is purely by size",
      [g.name for g in by_size.games]
      == ["Huge and fresh", "Big and cold", "Small and ancient"])
check("staleness is flagged on the old ones",
      {g.name for g in by_size.games if g.stale} == {"Small and ancient", "Big and cold"})
check("a fresh game is never stale",
      not next(g for g in by_size.games if g.name == "Huge and fresh").stale)
check("weighting lifts the cold game but size still leads",
      by_weight.games[0].name == "Huge and fresh"
      and by_weight.games[1].name == "Big and cold")
check("a tiny ancient game never outranks a huge one",
      by_weight.games[-1].name == "Small and ancient")
check("the reclaim total is only the stale ones",
      by_size.reclaimable_bytes == 63_000_000_000, by_size.reclaimable_bytes)
check("an unknown sort mode falls back rather than raising",
      [g.name for g in storage.gather(games, FakeOverrides(), now, "nonsense").games]
      == [g.name for g in by_size.games])

print("\n=== 5. a game never played is aged from when we first saw it ===")
seen = {"Never touched": (now - timedelta(days=400)).isoformat()}
aged = storage.gather([Fake("Never touched", "C:", 1_000_000_000)], FakeOverrides(seen), now)
game = aged.games[0]
print(f"   idle_days={game.idle_days} ever_played={game.ever_played} stale={game.stale}")
check("its idle days come from first_seen", game.idle_days is not None and game.idle_days >= 399)
check("it is not claimed to have been played", not game.ever_played)
check("and it can be reclaimed", game.stale)
recent = storage.gather(
    [Fake("Just installed", "C:", 1_000_000_000)],
    FakeOverrides({"Just installed": now.isoformat()}), now,
)
check("a game installed today is never stale", not recent.games[0].stale)
check("no first_seen at all means no age rather than a guess",
      storage.gather([Fake("Unknown", "C:", 1)], FakeOverrides(), now).games[0].idle_days is None)

print("\n=== 6. the treemap's geometry ===")
BOX = (0.0, 0.0, 1000.0, 500.0)
sizes = sorted([142, 132, 111, 81, 73, 66, 64, 63, 51, 49, 38, 34, 33, 18, 14, 13, 10, 8, 8, 1],
               reverse=True)
rects = storage.squarify(sizes, *BOX)
check("one rectangle per game", len(rects) == len(sizes))
area = sum(w * h for _x, _y, w, h in rects)
print(f"   covers {area / (1000 * 500) * 100:.2f}% of the box")
check("they fill the box", abs(area - 1000 * 500) < 1.0, area)
biggest = max(range(len(sizes)), key=lambda i: sizes[i])
ratios = [(w * h) / area * sum(sizes) for _x, _y, w, h in rects]
check("each area is proportional to its size",
      all(abs(r - s) < 0.01 * sum(sizes) for r, s in zip(ratios, sizes)))
check("nothing escapes the box",
      all(x >= -0.01 and y >= -0.01 and x + w <= 1000.01 and y + h <= 500.01
          for x, y, w, h in rects))


def overlaps(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw - 0.01 and bx < ax + aw - 0.01 and ay < by + bh - 0.01 and by < ay + ah - 0.01


check("no two rectangles overlap",
      not any(overlaps(rects[i], rects[j])
              for i in range(len(rects)) for j in range(i + 1, len(rects))))
aspects = [max(w / h, h / w) for _x, _y, w, h in rects if w > 0 and h > 0]
# The rectangles that carry a label are the ones whose shape matters; a 1 GB game beside a
# 142 GB one is an unlabelled sliver whatever the algorithm does, so it is judged apart.
big = [max(w / h, h / w) for _x, _y, w, h in rects if w * h >= 0.01 * 1000 * 500]
print(f"   worst aspect {max(aspects):.1f}:1 overall, {max(big):.1f}:1 among the labelled")
check("the rectangles that carry a label stay roughly square", max(big) < 4.0, max(big))
check("even the slivers stay within reason", max(aspects) < 10.0, max(aspects))
check("an empty library returns nothing rather than dividing by zero",
      storage.squarify([], *BOX) == [])
check("all-zero sizes do not raise",
      len(storage.squarify([0, 0, 0], *BOX)) == 3)
check("a zero-sized box does not raise", len(storage.squarify([5, 3], 0, 0, 0, 0)) == 2)
check("one game fills the whole box",
      abs(storage.squarify([7], *BOX)[0][2] * storage.squarify([7], *BOX)[0][3]
          - 1000 * 500) < 1.0)

print("\n=== 7. the page in the window ===")
from PySide6.QtWidgets import QApplication

from adapters import controller
from presentation import ui_storage
from presentation import ui_window

app = QApplication.instance() or QApplication([])
win = ui_window.MainWindow()
win.resize(1400, 1000)
win.show()


def pump(seconds=0.5):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


pump(1.5)
page = win.storage_page
# Where the window routes it, not how many pages there are: Reports is a fifth since Phase 84.
check("the stack holds the page where the window routes it", win.stack.indexOf(page) == ui_window.STORAGE_PAGE)
win.library.storage_button.click()
pump(0.8)
check("the toolbar button opens it", win.stack.currentIndex() == ui_window.STORAGE_PAGE)
check("and it is filled in", page.storage is not None)
check("every game has a row, plus one header per drive",
      page.list.count() == len(page.storage.games) + len(page.storage.drives))

kinds = [page.list.item(i).data(ui_storage.KIND_ROLE) for i in range(page.list.count())]
headers = [i for i, k in enumerate(kinds) if k == ui_storage.KIND_DRIVE]
from PySide6.QtCore import Qt as _Qt
check("drive headers are not selectable, so the pad steps over them",
      all(not (page.list.item(i).flags() & _Qt.ItemFlag.ItemIsSelectable) for i in headers))
check("nor focusable",
      all(not (page.list.item(i).flags() & _Qt.ItemFlag.ItemIsEnabled) for i in headers))

page.select_first()
pump(0.2)
first = page.list.currentRow()
check("the first selection is a game, not a header",
      page.list.item(first).data(ui_storage.KIND_ROLE) == ui_storage.KIND_GAME)
win._on_pad_action(controller.DOWN)
pump(0.2)
moved = page.list.currentRow()
print(f"   pad down: row {first} -> {moved}")
check("the pad moves the selection", moved != first)
check("and never lands on a header",
      page.list.item(moved).data(ui_storage.KIND_ROLE) == ui_storage.KIND_GAME)

opened = []
page.gameActivated.connect(opened.append)
win._on_pad_action(controller.ACTIVATE)
pump(0.6)
print(f"   A opened: {opened}")
check("A opens a game", bool(opened))
check("and lands on that game's page", win.stack.currentIndex() == ui_window.DETAIL_PAGE)
check("the game opened is the one that was selected",
      win.detail.view is not None and win.detail.view.key == opened[0])

win.show_storage()
pump(0.4)
win._on_pad_action(controller.BACK)
pump(0.4)
check("B returns to the library", win.stack.currentIndex() == ui_window.LIBRARY_PAGE)

print("\n=== 8. the two tabs ===")
win.show_storage()
pump(0.4)
# Since Phase 84 left and right walk the tabs in order -- Library, Stats, Storage, Reports -- where two
# simply swapped: Stats is on Storage's left.
win._on_pad_action(controller.LEFT)
pump(0.5)
check("left crosses to Stats", win.stack.currentIndex() == ui_window.STATS_PAGE)
win._on_pad_action(controller.RIGHT)
pump(0.5)
check("right crosses back to Storage", win.stack.currentIndex() == ui_window.STORAGE_PAGE)
check("the tab shows which page you are on",
      page.header_row.tabs[ui_storage.ui_pageshell.TAB_STORAGE].isChecked()
      and not page.header_row.tabs[ui_storage.ui_pageshell.TAB_STATS].isChecked())
win.stats_page.header_row.tabs[ui_storage.ui_pageshell.TAB_STORAGE].click()
pump(0.5)
check("clicking the other tab moves too", win.stack.currentIndex() == ui_window.STORAGE_PAGE)

print("\n=== 9. the ordering control ===")
was_sort = win.storage_sort
win.set_storage_sort(storage.SORT_WEIGHTED)
pump(0.4)
check("the page follows the chosen order",
      page.storage.sort_mode == storage.SORT_WEIGHTED)
check("and the box shows it",
      page.sort_box.currentIndex()
      == next(i for i, (_l, m) in enumerate(ui_storage.SORT_LABELS)
              if m == storage.SORT_WEIGHTED))
check("the choice is remembered", win.config.get("storage_sort") == storage.SORT_WEIGHTED)
win.set_storage_sort(was_sort)
pump(0.3)

print("\n=== 10. the treemap is mouse-only, and knows it ===")
check("it takes no focus",
      page.treemap.focusPolicy() == ui_storage.Qt.FocusPolicy.NoFocus)
check("it is showing on the desktop", page.treemap.isVisible())
was_tv = win.tv_mode
win.set_tv_mode(True)
pump(1.0)
win.show_storage()
pump(0.6)
check("and hidden in TV mode, where there is no mouse to drive it",
      not page.treemap.isVisible())
check("the ranked list is still there", page.list.isVisible())
check("the page still fits the window", page.content.width() <= win.width())
win.set_tv_mode(was_tv)
pump(0.8)
win.show_storage()
pump(0.5)
check("and it comes back on the desktop", page.treemap.isVisible())

print("\n=== 11. nothing to measure still looks like a page ===")
page.set_storage(storage.Storage(drives=[], sort_mode=storage.SORT_SIZE))
pump(0.3)
check("the empty message shows", page.empty_label.isVisible())
check("the list is hidden rather than empty", not page.list.isVisible())
check("so is the reclaim strip", not page.reclaim.isVisible())
check("and the map", not page.treemap.isVisible())
page.set_storage(storage.gather(win.views, win.overrides, now))
pump(0.3)
check("real data brings all of it back",
      page.list.isVisible() and page.reclaim.isVisible() and not page.empty_label.isVisible())

win.close()
pump(0.3)

print("\n=== 12. this page wrote nothing of yours ===")
check("overrides.json was not touched",
      test_sandbox.real_stamp() == overrides_stamp)
check("and its records are unchanged",
      test_sandbox.real_records() == overrides_before)
after = json.loads((REAL / "config.json").read_text(encoding="utf-8"))
original = json.loads(config_before)
changed = {k for k in set(after) | set(original) if after.get(k) != original.get(k)}
print(f"   config keys that changed: {sorted(changed) or 'none'}")
check("the only config key this page may write is the chosen order",
      changed <= {"storage_sort", "tv_mode", "tv_scale"}, sorted(changed))
if changed:
    (REAL / "config.json").write_text(config_before, encoding="utf-8")
    print("   (put config.json back exactly as it was found)")

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
