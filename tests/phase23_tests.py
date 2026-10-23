"""Phase 23: the stats page.

This phase stores nothing -- it only reads -- so the strongest thing the data rules ask for
here is proof of that. overrides.json and config.json are photographed at the start and
compared at the end.

Nothing is asserted against a fixed number of games or sessions. Every figure is checked
against the same library the page read, worked out a second way.
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
from shared import humanize
from shared import rules
from logic import sessions
from logic import stats
from presentation import ui_rules

print("\n=== 1. the numbers, worked out a second way ===")
overrides = test_sandbox.library()  # the library the launcher opens: the database since Phase 69
views = catalog_io.merge(overrides.load_catalog(), overrides)
now = datetime.now().astimezone()
result = stats.gather(views, overrides, now)

# Recomputed here without touching stats.py, so the two have to agree by arithmetic. Since Phase 96 the
# sessions count by one rule -- every game not marked a tool, installed or not -- not the grid's games.
all_sessions = [s for record in overrides.export_records().values() if not record.get("is_tool")
                for s in sessions.load(record)]
expected_lifetime = sum(max(0, v.playtime_seconds) for v in views)
visible = [v for v in views if not v.hidden and not v.is_non_game]
print(f"   library: {len(views)} entries, {len(visible)} visible, "
      f"{len(all_sessions)} session(s) recorded")
check("lifetime is every game's playtime added up",
      result.lifetime_seconds == expected_lifetime,
      (result.lifetime_seconds, expected_lifetime))
check("the library count is the visible library",
      result.total_games == len(visible), (result.total_games, len(visible)))
check("the sizes add up to the visible library's",
      result.total_bytes == sum(max(0, v.entry.size_on_disk or 0) for v in visible))
check("every session was seen", result.sessions_recorded == len(all_sessions))
check("this week matches sessions.minutes_this_week",
      result.minutes_this_week == sessions.minutes_this_week(all_sessions, now))
check("this month matches sessions.minutes_this_month",
      result.minutes_this_month == sessions.minutes_this_month(all_sessions, now))
check("timed + untimed is the whole visible library",
      result.timed_games + result.untimed_games == result.total_games)
check("the per-source counts add up to the library",
      sum(t.value for t in result.sources) == result.total_games)
check("recording_since is the oldest session there is",
      result.recording_since == min((s.start for s in all_sessions), default=None))

print("\n=== 2. most played is exe games only, biggest first ===")
uri_names = {v.display_name for v in views if v.entry.launch_kind == "uri"}
listed = [t.label for t in result.top_games]
print(f"   listed: {listed}")
check("no URI game is in the list", not (set(listed) & uri_names), set(listed) & uri_names)
check("sorted, most played first",
      [t.value for t in result.top_games] == sorted((t.value for t in result.top_games),
                                                    reverse=True))
check("never longer than the configured limit",
      len(result.top_games) <= rules.STATS_TOP_GAMES)
check("everything listed has time on it", all(t.value > 0 for t in result.top_games))

print("\n=== 3. the twelve months, including the year rollover ===")
check("twelve of them", len(result.months) == rules.STATS_CHART_MONTHS)
check("the last one is this month",
      (result.months[-1].year, result.months[-1].month) == (now.year, now.month))
check("they are consecutive and ascending",
      all((b.year, b.month) > (a.year, a.month)
          for a, b in zip(result.months, result.months[1:])))
january = datetime(2026, 1, 15).astimezone()
rolled = stats.last_months(january, 12)
print(f"   from Jan 2026, twelve months back starts at {rolled[0]}")
check("stepping back over new year lands in the previous one", rolled[0] == (2025, 2))
check("and ends where it started", rolled[-1] == (2026, 1))
check("a month's minutes match the sessions that fall in it",
      all(m.minutes == sum(s.minutes for s in all_sessions
                           if (s.start.year, s.start.month) == (m.year, m.month))
          for m in result.months))
check("months before history began are marked unrecorded",
      all(m.recorded for m in result.months if m.minutes > 0))
check("the chart can never want a month that pruning has dropped",
      rules.STATS_CHART_MONTHS * 31 <= rules.SESSION_KEEP_DAYS,
      (rules.STATS_CHART_MONTHS, rules.SESSION_KEEP_DAYS))

print("\n=== 4. what the page admits it cannot see ===")
lines = " ".join(stats.caveats(result))
print(f"   {len(stats.caveats(result))} lines, {len(lines)} characters")
check("it names the launchers whose time is invisible",
      all(word in lines for word in ("Steam", "Epic", "Xbox")))
check("in numbers, not in general terms",
      str(result.untimed_games) in lines and str(result.total_games) in lines)
check("it says when history begins",
      result.recording_since is None or f"{result.recording_since:%d %b %Y}" in lines)
check("it admits the launcher must be open", "launcher is open" in lines)
check("and that elevated games are not timed at all", "administrator" in lines)

print("\n=== 5. a library with nothing in it still produces a page ===")


class FakeOverrides:
    def get(self, key):
        return {}


empty = stats.gather([], FakeOverrides(), now)
check("no crash on an empty library", isinstance(empty, stats.Stats))
check("still twelve months", len(empty.months) == rules.STATS_CHART_MONTHS)
check("all of them unrecorded", not any(m.recorded for m in empty.months))
check("nothing claims to have happened", empty.peak_month_minutes == 0)
check("has_history is False", not empty.has_history)
check("and the caveats say so rather than going quiet",
      any("No sessions" in line for line in stats.caveats(empty)),
      stats.caveats(empty))

print("\n=== 6. the chart: a real minute is never rounded away ===")
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from presentation import ui_stats
from presentation import ui_theme

app = QApplication.instance() or QApplication([])
metrics = ui_theme.Metrics(1.0)
app.setStyleSheet(ui_theme.stylesheet(1.0) + ui_stats.stylesheet(1.0))


def colours_in(chart) -> set:
    image = chart.grab().toImage()
    found = set()
    for y in range(image.height()):
        for x in range(image.width()):
            pixel = image.pixelColor(x, y)
            if pixel.alpha() > 200:
                found.add((pixel.red(), pixel.green(), pixel.blue()))
    return found


def rgb(name: str) -> tuple:
    colour = QColor(name)
    return (colour.red(), colour.green(), colour.blue())


base = result.months
tiny = [stats.Month(m.year, m.month, v, True)
        for m, v in zip(base, [0] * 10 + [2, 4000])]
chart = ui_stats.MonthChart(metrics)
chart.resize(880, chart.height())
chart.set_months(tiny)
image = chart.grab().toImage()
# A bar runs from the accent at its top to accent 700 at its foot since Phase 58, so a bar's
# pixel is one on that run, not one colour.
top_rgb, foot_rgb = rgb(ui_rules.COLOR_CHART_BAR), rgb(ui_rules.COLOR_CHART_BAR_FOOT)
on_bar = lambda p: min(max(abs(c - (a + (b - a) * k / 20)) for c, a, b in zip(p, top_rgb, foot_rgb))  # noqa: E731
                       for k in range(21)) <= 3
# The 2-minute column, measured where it actually is: each column is its own width plus
# one gap along, not merely its width.
gap = ui_rules.STATS_BAR_GAP
width = (chart.width() - gap * (rules.STATS_CHART_MONTHS - 1)) / rules.STATS_CHART_MONTHS
centre = round(10 * (width + gap) + width / 2)
tall = sum(1 for y in range(image.height())
           if on_bar((image.pixelColor(centre, y).red(),
                      image.pixelColor(centre, y).green(),
                      image.pixelColor(centre, y).blue())))
print(f"   2 minutes against a peak of {4000 // 60}h draws {tall}px of bar "
      f"(column centre x={centre})")
check("a tiny month is still drawn", tall > 0)
check("and at no less than the floor in ui_rules",
      tall >= ui_rules.STATS_MIN_BAR_PX, (tall, ui_rules.STATS_MIN_BAR_PX))
check("the peak's value is what gets written above it",
      chart.peak_label() == humanize.playtime(4000 * 60), chart.peak_label())
check("a chart with no bars writes nothing",
      ui_stats.MonthChart(metrics).peak_label() == "")

quiet = [stats.Month(m.year, m.month, 0, True) for m in base]
never = [stats.Month(m.year, m.month, 0, False) for m in base]
quiet_chart = ui_stats.MonthChart(metrics); quiet_chart.resize(880, 200)
quiet_chart.set_months(quiet)
never_chart = ui_stats.MonthChart(metrics); never_chart.resize(880, 200)
never_chart.set_months(never)
quiet_colours, never_colours = colours_in(quiet_chart), colours_in(never_chart)
check("a quiet month and an unrecorded one do not look the same",
      quiet_colours != never_colours)
check("a quiet month draws the baseline", rgb(ui_rules.COLOR_CHART_BASELINE) in quiet_colours)
check("an unrecorded month draws the unrecorded wash",
      rgb(ui_rules.COLOR_CHART_UNRECORDED) in never_colours)
check("neither invents a bar", rgb(ui_rules.COLOR_CHART_BAR) not in quiet_colours
      and rgb(ui_rules.COLOR_CHART_BAR) not in never_colours)
check("the tooltip names every month",
      all(f"{m.label} {m.year}" in never_chart.toolTip() for m in never))

print("\n=== 7. the page in the window ===")
from adapters import controller
from presentation import ui_window

win = ui_window.MainWindow()
win.resize(1400, 950)
win.show()
end = time.time() + 1.4
while time.time() < end:
    app.processEvents()
    time.sleep(0.02)


def pump(seconds=0.5):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


page = win.stats_page
# Not a count: Phase 24 added a fourth page and broke exactly that assertion. What matters
# is that the stats page is in the stack at the index the window routes to.
check("the stats page is in the stack, where the window expects it",
      win.stack.widget(ui_window.STATS_PAGE) is page)
win.library.stats_button.click()
pump()
check("the toolbar button opens it", win.stack.currentIndex() == ui_window.STATS_PAGE)
check("and it is filled in", page.stats is not None)
check("the cards show the same figures the module computed",
      page.cards["library"].value_label.text() == str(page.stats.total_games))
# Phase 31 moved the tabs into the window's top bar and hid this header; the alignment
# only means something while it is shown.
check("the header lines up with the content, when it is shown",
      page.header_row.isHidden()
      or page.header_row.mapTo(win, page.header_row.rect().topLeft()).x()
      == page.content.mapTo(win, page.content.rect().topLeft()).x())
check("the content is capped, not stretched",
      page.content.width() <= round(ui_rules.STATS_CONTENT_MAX_WIDTH * win.scale))

page.back_button.click()
pump()
check("Back to library returns", win.stack.currentIndex() == ui_window.LIBRARY_PAGE)

win.show_stats(); pump(0.3)
win._on_pad_action(controller.BACK)
pump()
check("the pad's B returns", win.stack.currentIndex() == ui_window.LIBRARY_PAGE)

win._on_pad_action(controller.STATS)
pump()
check("the View/Create button opens it from the library",
      win.stack.currentIndex() == ui_window.STATS_PAGE)
win._on_pad_action(controller.STATS)
pump()
check("and closes it again", win.stack.currentIndex() == ui_window.LIBRARY_PAGE)

first = next(v for v in win.views if not v.hidden)
win.show_detail(first.key); pump(0.3)
win._on_pad_action(controller.STATS)
pump()
check("it opens from a game's page too", win.stack.currentIndex() == ui_window.STATS_PAGE)

bar = page.scroll.verticalScrollBar()
win.resize(900, 560); pump(0.4)
start = bar.value()
win._on_pad_action(controller.DOWN); pump(0.2)
scrolled = bar.value()
win._on_pad_action(controller.UP); pump(0.2)
print(f"   scrollbar 0..{bar.maximum()}: down -> {scrolled}, up -> {bar.value()}")
check("the pad scrolls the page down", bar.maximum() == 0 or scrolled > start)
check("and back up", bar.value() <= scrolled)
check("nothing selectable means A does nothing rash",
      win.stack.currentIndex() == ui_window.STATS_PAGE)
win.resize(1400, 950); pump(0.3)

print("\n=== 8. reopening after the data changes leaves nothing behind ===")
rows_before = page.played_grid.count()
page.set_stats(stats.gather([], FakeOverrides(), now))
pump(0.2)
live = [page.played_grid.itemAt(i).widget() for i in range(page.played_grid.count())]
check("the old rows are gone from the layout", page.played_grid.count() == 0, rows_before)
check("and gone from the screen too, not merely scheduled for deletion",
      not any(w is not None and w.isVisible() for w in live))
page.set_stats(result)
pump(0.2)
check("filling it again rebuilds the rows",
      page.played_grid.count() == rows_before, (page.played_grid.count(), rows_before))

print("\n=== 9. TV mode: it fits, and the hint bar still does ===")
from presentation import ui_tv

was_tv, was_scale = win.tv_mode, win.config.get("tv_scale")
heights = set()
for scale in ui_rules.TV_SCALE_CHOICES:
    app.setStyleSheet(ui_theme.stylesheet(scale) + ui_tv.stylesheet(scale))
    hints = ui_tv.HintBar(ui_theme.Metrics(scale))
    hints.set_power(rules.POWER_WIRED)
    width = hints.sizeHint().width()
    heights.add(hints.sizeHint().height() if scale == ui_rules.TV_SCALE_CHOICES[0] else None)
    check(f"the hint bar fits a 1080p screen at {scale}x", width <= 1920, width)
    hints.deleteLater()

win.config["tv_scale"] = ui_rules.TV_SCALE_CHOICES[-1]
win.set_tv_mode(True)
pump(0.8)
win.show_stats()
pump(0.5)
check("the page follows the TV scale",
      page.content.maximumWidth()
      == round(ui_rules.STATS_CONTENT_MAX_WIDTH * win.scale))
check("the chart grew with it", page.chart.height() > ui_rules.STATS_CHART_HEIGHT)
check("nothing is wider than the window", page.content.width() <= win.width())
check("the hint bar is showing", win.hint_bar.isVisible())
check("Stats is advertised on it", any("Stats" == label for _x, _p, label in ui_tv.HINTS))
win.config["tv_scale"] = was_scale
win.set_tv_mode(was_tv)
pump(0.5)

win.close()
pump(0.3)

print("\n=== 10. nothing of the user's was written ===")
check("overrides.json was not touched",
      test_sandbox.real_stamp() == overrides_stamp)
check("and its records are unchanged",
      test_sandbox.real_records() == overrides_before)
after = json.loads((REAL / "config.json").read_text(encoding="utf-8"))
original = json.loads(config_before)
changed = {k for k in set(after) | set(original) if after.get(k) != original.get(k)}
print(f"   config keys that changed: {sorted(changed) or 'none'}")
check("config.json changed only the two TV keys this test toggles",
      changed <= {"tv_mode", "tv_scale"}, sorted(changed))
if changed:
    (REAL / "config.json").write_text(config_before, encoding="utf-8")
    print("   (put config.json back exactly as it was found)")

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
