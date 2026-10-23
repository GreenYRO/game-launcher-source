"""Phase 58: the Nocturne restyle, step 5 of 6 -- Stats, Storage, the menus, the buttons,
the message card and Settings.

The design (#1e and #1f, read from the mockup's markup) measured on the live window at
1280x820: both pages one column, 64 px in and 18 px under the top bar; Stats' four figures,
its chart (bars from the accent to accent 700 with their values over them, unrecorded months
a short stub, the months under a hairline), its two lists side by side with the games'
covers, the legend under the caveats; Storage's reclaim strip, each drive a card with its
capacity bar in three parts and a legend, the rows 38 high and 5 apart with the design's
glass and bar, a long-unplayed game's tag; a menu's chosen entry a dark accent, not a flood;
the message card on the surface; a dialog's buttons quiet outlines with the default one in
the accent; Settings' controls ringed outside, TV mode's thicker. Runs on a throwaway copy
of the data; nothing is started.
"""
import dataclasses
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))  # the project folder, one up from tests/
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import test_sandbox

box = test_sandbox.start()

import logging

logging.basicConfig(level=logging.ERROR)

from PySide6.QtCore import QEventLoop, QPoint, Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QComboBox, QMessageBox, QPushButton

app = QApplication([])

from logic import focus
from presentation import ui_actions, ui_rules as _ui_rules, ui_settings, ui_window


class _Rules:
    """ui_rules, with a name that does not exist read as 0 -- so the code before this
    phase can be judged check by check rather than crash at the first new name."""

    def __getattr__(self, name):
        return getattr(_ui_rules, name, 0)


ui_rules = _Rules()
passed = failed = 0


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"   PASS  {name}")
    else:
        failed += 1
        print(f"   FAIL  {name}   {detail}")


def settle(seconds):
    loop = QEventLoop()
    QTimer.singleShot(round(seconds * 1000), loop.quit)
    loop.exec()


def rgb(colour):
    colour = QColor(colour)
    return colour.red(), colour.green(), colour.blue()


def distance(a, b):
    return max(abs(x - y) for x, y in zip(a, b))


def at(image, point):
    return rgb(image.pixelColor(point.x(), point.y()))


def over(ground, colour):
    """`colour` (#AARRGGBB) laid over `ground`, as the page paints it."""
    top = QColor(colour)
    k = top.alpha() / 255
    return tuple(round(g + (c - g) * k) for g, c in zip(ground, (top.red(), top.green(), top.blue())))


def safely(make, fallback=None):
    try:
        return make()
    except Exception as error:  # the code before this phase lacks the names: judge, do not crash
        print(f"         ({type(error).__name__}: {error})")
        return fallback


SURFACE, BORDER = rgb("#232532"), rgb("#3f424d")

print("\n=== 1. the design's numbers ===")
check("both pages one column: 64 px in, 18 under the top bar, at most 1022 wide (the design's 1150 "
      "less 64 either side), placed as drawn at 1280",
      (ui_rules.PAGE_COLUMN_SIDE, ui_rules.PAGE_COLUMN_TOP, ui_rules.PAGE_COLUMN_FRAME,
       ui_rules.STATS_CONTENT_MAX_WIDTH, ui_rules.STORAGE_CONTENT_MAX_WIDTH) == (64, 18, 1280, 1022, 1022))
check("the figures: 14 apart, 18 x 20 inside, an 18 px icon, the value 32 px 0.02 em tighter on a 1.1 "
      "line, the caption 12.5 px in neutral 400",
      (ui_rules.STATS_CARD_SPACING, ui_rules.STATS_CARD_PADDING_Y, ui_rules.STATS_CARD_PADDING_X,
       ui_rules.STATS_ICON_PX, ui_rules.STATS_VALUE_PX, ui_rules.STATS_VALUE_TRACKING, ui_rules.STATS_VALUE_LINE,
       ui_rules.STATS_CAPTION_PX, ui_rules.COLOR_STATS_CAPTION)
      == (14, 18, 20, 18, 32, -0.02, 1.1, 12.5, "#b2b6ca"))
check("the chart: bars 12 apart in 170 px, the tallest 120, their values 8 above in 11 px, the months "
      "11 px under a hairline 8 below; unrecorded a 6 px stub",
      (ui_rules.STATS_BAR_GAP, ui_rules.STATS_CHART_HEIGHT, ui_rules.STATS_BAR_MAX, ui_rules.STATS_VALUE_ABOVE,
       ui_rules.STATS_AXIS_PX, ui_rules.STATS_AXIS_GAP, ui_rules.STATS_UNRECORDED_PX)
      == (12, 170, 120, 8, 11, 8, 6))
check("its colours: the accent to accent 700, the hairline neutral 800, values neutral 400, months 500",
      (ui_rules.COLOR_CHART_BAR, ui_rules.COLOR_CHART_BAR_FOOT, ui_rules.COLOR_CHART_UNRECORDED,
       ui_rules.COLOR_CHART_AXIS, ui_rules.COLOR_CHART_VALUE, ui_rules.COLOR_CHART_MONTH)
      == ("#9184d9", "#5d5294", "#3f424d", "#3f424d", "#b2b6ca", "#9397ab"))
check("the lists: 14 apart, 18 x 22 inside, rows 30 high and 4 apart, 13 px, a cover 18 x 27 with 3 px corners",
      (ui_rules.STATS_COLUMN_GAP, ui_rules.STATS_LIST_PADDING_Y, ui_rules.STATS_LIST_PADDING_X,
       ui_rules.STATS_LIST_ROW_PX, ui_rules.STATS_LIST_ROW_GAP, ui_rules.STATS_LIST_TEXT_PX,
       ui_rules.STATS_THUMB_WIDTH, ui_rules.STATS_THUMB_HEIGHT, ui_rules.STATS_THUMB_RADIUS)
      == (14, 18, 22, 30, 4, 13, 18, 27, 3))
check("the reclaim strip: 14 px corners, accent 900 edged in 800, a 22 px icon in 300, 14 px words in 100 "
      "over 12.5 px in 300",
      (ui_rules.STORAGE_RECLAIM_RADIUS, ui_rules.COLOR_RECLAIM, ui_rules.COLOR_RECLAIM_EDGE,
       ui_rules.STORAGE_RECLAIM_ICON_PX, ui_rules.COLOR_RECLAIM_ICON, ui_rules.STORAGE_RECLAIM_TITLE_PX,
       ui_rules.COLOR_RECLAIM_TITLE, ui_rules.STORAGE_RECLAIM_LINE_PX, ui_rules.COLOR_RECLAIM_LINE)
      == (14, "#2b2741", "#423a6a", 22, "#d2cefd", 14, "#f5f4ff", 12.5, "#d2cefd"))
check("a drive's card: 18 x 22 inside, 18 px name, a 14 px bar with 7 px corners in three parts 2 apart",
      (ui_rules.STORAGE_CARD_PADDING_Y, ui_rules.STORAGE_CARD_PADDING_X, ui_rules.STORAGE_DRIVE_PX,
       ui_rules.STORAGE_CAPACITY_BAR_HEIGHT, ui_rules.STORAGE_BAR_RADIUS, ui_rules.STORAGE_SEGMENT_GAP)
      == (18, 22, 18, 14, 7, 2))
check("the rows: 38 high, 5 apart, 8 px corners, 14 px in, columns 110 and 90, the text colour at 3%, "
      "the bar the accent at 16% (accent 400 at 22% when long unplayed)",
      (ui_rules.STORAGE_ROW_HEIGHT, ui_rules.STORAGE_ROW_GAP, ui_rules.STORAGE_ROW_RADIUS,
       ui_rules.STORAGE_ROW_PADDING, ui_rules.STORAGE_AGE_COLUMN, ui_rules.STORAGE_SIZE_COLUMN,
       ui_rules.COLOR_STORAGE_ROW, ui_rules.COLOR_STORAGE_BAR, ui_rules.COLOR_STORAGE_STALE_BAR)
      == (38, 5, 8, 14, 110, 90, "#08e9e9ed", "#299184d9", "#38b5abfc"))
check("menus, tooltips and the message card on the surface with a hairline; a chosen entry accent 900 "
      "with accent-100 words",
      (ui_rules.COLOR_MENU, ui_rules.COLOR_MENU_EDGE, ui_rules.COLOR_MENU_SELECTED,
       ui_rules.COLOR_MENU_SELECTED_TEXT, ui_rules.COLOR_TOAST, ui_rules.COLOR_TOAST_EDGE)
      == ("#232532", "#3f424d", "#2b2741", "#f5f4ff", "#232532", "#3f424d"))

w = ui_window.MainWindow()
w.resize(1280, 820)
w.move(app.primaryScreen().availableGeometry().topLeft())
w.show()
settle(2.0)
focus.bring_to_front(int(w.winId()))
settle(0.4)
bar_foot = w.top_bar.mapTo(w, QPoint(0, w.top_bar.height())).y()

print("\n=== 2. Stats ===")
w.show_stats()
settle(1.2)
stats = w.stats_page
cards = list(stats.cards.values())
first = cards[0].mapTo(w, QPoint(0, 0))
last = cards[-1].mapTo(w, QPoint(cards[-1].width(), 0))
# The column's first block is the Recap card since Phase 96, above the four figures.
top = stats.recap_card.mapTo(w, QPoint(0, 0))
check("the column starts 64 px in and 18 px under the top bar", (top.x(), top.y() - bar_foot) == (64, 18),
      (top.x(), top.y() - bar_foot))
check("and the four figures share its left edge", first.x() == top.x(), (first.x(), top.x()))
check("and is the design's 1022 wide at 1280", last.x() - first.x() == 1022, last.x() - first.x())
gaps = [b.mapTo(w, QPoint(0, 0)).x() - a.mapTo(w, QPoint(a.width(), 0)).x() for a, b in zip(cards, cards[1:])]
check("the four figures 14 apart", gaps == [14, 14, 14], gaps)
value = cards[0].value_label
check("their values 32 px, their captions 12.5 px", value.font().pixelSize() == 32
      and abs(cards[0].caption.font().pointSizeF() - 12.5 * 72 / 96) < 0.05,
      (value.font().pixelSize(), cards[0].caption.font().pointSizeF()))
check("every card's title is 15 px", all(c.title.font().pixelSize() == 15 for c in (
    stats.chart_card, stats.played_card, stats.library_card, stats.caveat_card)))

chart = stats.chart
# Read off the window, not the chart alone: the chart is see-through, and on its own the
# card behind it would not show.
window_shot = w.grab().toImage()
origin = chart.mapTo(w, QPoint(0, 0))
image = window_shot.copy(origin.x(), origin.y(), chart.width(), chart.height())
plot = round(170 * w.scale)
top_rgb, foot_rgb = rgb("#9184d9"), rgb("#5d5294")
on_bar = lambda p: min(max(abs(c - (a + (b - a) * k / 20)) for c, a, b in zip(p, top_rgb, foot_rgb))  # noqa: E731
                       for k in range(21)) <= 4
months = chart.months
recorded = [i for i, m in enumerate(months) if m.recorded and m.minutes > 0]
peak = max(recorded, key=lambda i: months[i].minutes) if recorded else None
box_of = getattr(chart, "column_box", None)
if peak is not None and box_of is not None:
    middle = round(box_of(peak).center().x())
    top = plot
    while top > 0 and on_bar(at(image, QPoint(middle, top - 1))):
        top -= 1
    check("the tallest bar is 120 px", plot - top == 120, plot - top)
    check("from the accent at its top", distance(at(image, QPoint(middle, top + 3)), rgb("#9184d9")) < 14,
          at(image, QPoint(middle, top + 3)))
    check("to accent 700 at its foot", distance(at(image, QPoint(middle, plot - 1)), rgb("#5d5294")) < 10,
          at(image, QPoint(middle, plot - 1)))
    ink = [at(image, QPoint(x, y)) for x in range(round(box_of(peak).left()), round(box_of(peak).right()))
           for y in range(max(0, top - 8 - 16), top - 8)]
    check("with its value written 8 px over it, in neutral 400",
          bool(ink) and min(distance(p, rgb("#b2b6ca")) for p in ink) < 30)
    others = [i for i in recorded if i != peak]
    check("and every other bar carries its value too",
          all(any(distance(at(image, QPoint(x, y)), SURFACE) > 30
                  for x in range(round(box_of(i).left()), round(box_of(i).right()))
                  for y in range(0, plot - max(4, round(120 * months[i].minutes / months[peak].minutes)) - 8))
              for i in others), others)
else:
    check("(no played month in this library to measure a bar on)", peak is None and box_of is not None,
          (peak, box_of))
unrecorded = [i for i, m in enumerate(months) if not m.recorded]
if unrecorded and box_of is not None:
    middle = round(box_of(unrecorded[0]).center().x())
    check("a month nobody recorded is a 6 px stub in the hairline colour",
          distance(at(image, QPoint(middle, plot - 3)), BORDER) < 6
          and distance(at(image, QPoint(middle, plot - 8)), SURFACE) < 6,
          (at(image, QPoint(middle, plot - 3)), at(image, QPoint(middle, plot - 8))))
check("the months stand under a hairline 8 px below the bars, 1 px of it",
      distance(at(image, QPoint(4, plot + 8)), BORDER) < 6
      and distance(at(image, QPoint(4, plot + 7)), SURFACE) < 6
      and distance(at(image, QPoint(4, plot + 9)), SURFACE) < 6,
      [at(image, QPoint(4, plot + d)) for d in (7, 8, 9)])

played, library = stats.played_card, stats.library_card
check("the two lists side by side, equal and 14 apart",
      abs(played.width() - library.width()) <= 1
      and library.mapTo(w, QPoint(0, 0)).x() - played.mapTo(w, QPoint(played.width(), 0)).x() == 14,
      (played.width(), library.width()))
grid = stats.played_grid
thumbs = [grid.itemAtPosition(r, 0).widget() for r in range(grid.rowCount()) if grid.itemAtPosition(r, 0)]
check("each most-played game with its cover, 18 x 27",
      bool(thumbs) and all(t.objectName() == "Thumb" and (t.width(), t.height()) == (18, 27) for t in thumbs),
      [(t.objectName(), t.width(), t.height()) for t in thumbs])
names = [grid.itemAtPosition(r, 1).widget() for r in range(grid.rowCount()) if grid.itemAtPosition(r, 1)]
pitch = [b.mapTo(w, QPoint(0, 0)).y() - a.mapTo(w, QPoint(0, 0)).y() for a, b in zip(names, names[1:])]
check("rows 30 high and 4 apart", bool(names) and names[0].height() == 30 and set(pitch) <= {34}, pitch)
check("and no rank numbers or share bars any more", grid.columnCount() <= 3, grid.columnCount())
legend = getattr(stats, "swatches", [])
check("the caveats name the chart's two colours, 10 px swatches",
      len(legend) == 2 and all(s.width() == s.height() == 10 for _, s in legend))
check("and say what the dimmed months are, in the caveat card, not under the chart",
      stats.caveat_card.isAncestorOf(stats.chart_caption))

print("\n=== 3. Storage ===")
w.show_storage()
settle(1.2)
page = w.storage_page
value = page.storage
column = page.content.mapTo(w, QPoint(0, 0))
check("the same column: 64 px in, 18 px under the top bar", (column.x(), column.y() - bar_foot) == (64, 18),
      (column.x(), column.y() - bar_foot))
# A game long unplayed, made so on the page only -- the page is read only and writes nothing.
stale_game = value.drives[0].games[-1]
cold = dataclasses.replace(stale_game, idle_days=400, ever_played=True)
drive = dataclasses.replace(value.drives[0], games=value.drives[0].games[:-1] + [cold])
page.set_storage(dataclasses.replace(value, drives=[drive] + value.drives[1:]))
settle(0.6)
shot = w.grab().toImage()
strip = page.reclaim
centre = strip.mapTo(w, QPoint(strip.width() // 2, 4))
check("with a game to reclaim, the strip is accent 900", distance(at(shot, centre), rgb("#2b2741")) < 8,
      at(shot, centre))
check("edged in accent 800", distance(at(shot, strip.mapTo(w, QPoint(strip.width() // 2, 0))), rgb("#423a6a")) < 12,
      at(shot, strip.mapTo(w, QPoint(strip.width() // 2, 0))))
check("saying what it takes, and naming the games on the line under it",
      cold.name in getattr(page, "reclaim_line", page.reclaim_label).text() and "take" in page.reclaim_label.text(),
      (page.reclaim_label.text(), getattr(page, "reclaim_line", page.reclaim_label).text()))

lst = page.list
header = lst.item(0)
head = lst.visualItemRect(header)
viewport = lst.viewport()
edge = viewport.mapTo(w, QPoint(head.left(), head.top() + 30))
inside = viewport.mapTo(w, QPoint(head.left() + 8, head.top() + 30))
check("each drive is a card: the hairline at its edge", distance(at(shot, edge), BORDER) < 12, at(shot, edge))
check("the surface inside it", distance(at(shot, inside), SURFACE) < 6, at(shot, inside))
games = [lst.item(r) for r in range(1, lst.count())]
rects = [lst.visualItemRect(i) for i in games]
check("its rows 38 high and 5 apart", len(rects) > 1 and rects[1].top() - rects[0].top() == 43,
      [r.top() for r in rects[:3]])
row = rects[1]
inset = round(22 * w.scale)
# Near a row's top edge, clear of its words.
glass_point = viewport.mapTo(w, QPoint(row.right() - inset - 30, row.top() + 3))
glass = over(SURFACE, "#08e9e9ed")
check("a row's empty end is the text colour at 3% over the card",
      distance(at(shot, glass_point), glass) < 5, (at(shot, glass_point), glass))
bar_point = viewport.mapTo(w, QPoint(row.left() + inset + 4, row.top() + 3))
filled = over(glass, "#299184d9")
check("its bar the accent at 16% over that", distance(at(shot, bar_point), filled) < 5,
      (at(shot, bar_point), filled))
cold_row = next(r for r in range(lst.count()) if lst.item(r).data(Qt.ItemDataRole.UserRole) == cold.key)
cold_rect = lst.visualItemRect(lst.item(cold_row))
lst.scrollToItem(lst.item(cold_row))
settle(0.4)
shot = w.grab().toImage()
cold_rect = lst.visualItemRect(lst.item(cold_row))
cold_point = viewport.mapTo(w, QPoint(cold_rect.left() + inset + 2, cold_rect.top() + 3))
check("a long-unplayed game's bar accent 400 at 22%",
      distance(at(shot, cold_point), over(glass, "#38b5abfc")) < 5, (at(shot, cold_point), over(glass, "#38b5abfc")))
tag_band = [at(shot, viewport.mapTo(w, QPoint(x, cold_rect.top() + 19 - 7)))
            for x in range(cold_rect.left() + inset, cold_rect.right() - inset - 200)]
check("and carries its outlined tag in the accent",
      sum(1 for p in tag_band if distance(p, rgb("#9184d9")) < 30) >= 8)
page.set_storage(value)
settle(0.3)

print("\n=== 4. a menu, the message card, a question ===")
view = w.by_key[w.library.visible_keys[0]]
w.show_library()
settle(0.6)
menu = ui_actions.build_menu(w, view)
menu.popup(w.mapToGlobal(QPoint(300, 300)))
settle(0.4)
entry = menu.actions()[1]
menu.setActiveAction(entry)
settle(0.3)
picture = menu.grab().toImage()
area = menu.actionGeometry(entry)
check("a menu is the surface", distance(at(picture, QPoint(area.left() + 3, area.top() - 3)), SURFACE) < 6,
      at(picture, QPoint(area.left() + 3, area.top() - 3)))
check("edged with the hairline", distance(at(picture, QPoint(picture.width() // 2, 0)), BORDER) < 8,
      at(picture, QPoint(picture.width() // 2, 0)))
check("its chosen entry accent 900, not a flood of the accent",
      distance(at(picture, QPoint(area.right() - 6, area.center().y())), rgb("#2b2741")) < 8,
      at(picture, QPoint(area.right() - 6, area.center().y())))
words = [at(picture, QPoint(x, y)) for x in range(area.left(), area.left() + 120)
         for y in range(area.top(), area.bottom())]
check("its words near white", max(words, key=sum) and distance(max(words, key=sum), rgb("#f5f4ff")) < 30,
      max(words, key=sum))
menu.close()
settle(0.2)

w.statusBar().showMessage("A message for the card", 6000)
settle(0.7)
shot = w.grab().toImage()
toast = w.toast
check("the message card is the surface", distance(at(shot, toast.mapTo(w, QPoint(toast.width() - 12, 4))), SURFACE) < 6,
      at(shot, toast.mapTo(w, QPoint(toast.width() - 12, 4))))
check("edged with the hairline",
      distance(at(shot, toast.mapTo(w, QPoint(toast.width() // 2, 0))), BORDER) < 5,
      at(shot, toast.mapTo(w, QPoint(toast.width() // 2, 0))))
w.statusBar().clearMessage()

question = QMessageBox(QMessageBox.Icon.Question, "Remove?", "Send it to the Recycle Bin?",
                       QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, w)
question.setDefaultButton(QMessageBox.StandardButton.Cancel)
question.show()
settle(0.6)
picture = question.grab().toImage()
yes, cancel = question.button(QMessageBox.StandardButton.Yes), question.button(QMessageBox.StandardButton.Cancel)
mid = lambda b, x: b.mapTo(question, QPoint(x, b.height() // 2))  # noqa: E731
check("a question's buttons are outlines, the ground showing inside",
      distance(at(picture, mid(yes, 4)), rgb("#161826")) < 8, at(picture, mid(yes, 4)))
check("the default one -- Cancel here -- outlined in the accent",
      distance(at(picture, mid(cancel, 0)), rgb("#9184d9")) < 30
      and distance(at(picture, mid(yes, 0)), rgb("#9184d9")) > 40,
      (at(picture, mid(cancel, 0)), at(picture, mid(yes, 0))))
question.close()
settle(0.2)

print("\n=== 5. Settings ===")
dialog = ui_settings.SettingsDialog(dict(w.config), w, known_keys=set())
dialog.show()
settle(0.7)
picture = dialog.grab().toImage()
ok = next(b for b in dialog.findChildren(QPushButton) if b.isDefault())
check("OK is the default, outlined in the accent",
      distance(at(picture, ok.mapTo(dialog, QPoint(0, ok.height() // 2))), rgb("#9184d9")) < 30,
      at(picture, ok.mapTo(dialog, QPoint(0, ok.height() // 2))))
out = 3  # the design's ring: 2 px wide and 2 px out, its middle 3 px from the edge
button = next(b for b in dialog.findChildren(QPushButton) if b.text() == "Open save backups")
button.setFocus(Qt.FocusReason.TabFocusReason)
settle(0.4)
picture = dialog.grab().toImage()
check("a button the keyboard or the pad is on is ringed 2 px outside it",
      distance(at(picture, button.mapTo(dialog, QPoint(-out, button.height() // 2))), rgb("#9184d9")) < 30
      and distance(at(picture, button.mapTo(dialog, QPoint(-1, button.height() // 2))), rgb("#9184d9")) > 40,
      (at(picture, button.mapTo(dialog, QPoint(-out, button.height() // 2))),
       at(picture, button.mapTo(dialog, QPoint(-1, button.height() // 2)))))
combo = dialog.findChildren(QComboBox)[0]
# The box in the middle of the view first: this checks the ring, not the scrolling. Left
# where the button above put it, on a 1032 px screen the box sat 2 px from the view's top,
# wholly in view, so Qt's ensureWidgetVisible kept no margin and the ring was cut off --
# a flaw of its own, on the list for the user since Phase 63, not this check's subject.
view = dialog.scroll
view.verticalScrollBar().setValue(combo.mapTo(view.widget(), combo.rect().center()).y()
                                  - view.viewport().height() // 2)
settle(0.2)
combo.setFocus(Qt.FocusReason.TabFocusReason)
settle(0.4)
picture = dialog.grab().toImage()
check("and so is a size box", distance(at(picture, combo.mapTo(dialog, QPoint(combo.width() // 2, -out))),
                                       rgb("#9184d9")) < 30,
      at(picture, combo.mapTo(dialog, QPoint(combo.width() // 2, -out))))
# The case above, on purpose: a box already wholly in view but 2 px from the view's top
# when the pad lands on it. The dialog is held short so it scrolls on any screen.
dialog.resize(dialog.width(), round(480 * dialog.scale))
button.setFocus(Qt.FocusReason.TabFocusReason)
settle(0.4)
view.verticalScrollBar().setValue(combo.mapTo(view.widget(), QPoint(0, 0)).y() - 2)
settle(0.2)
placed = combo.mapTo(view.viewport(), QPoint(0, 0)).y()
combo.setFocus(Qt.FocusReason.TabFocusReason)
settle(0.4)
picture = dialog.grab().toImage()
landed = combo.mapTo(view.viewport(), QPoint(0, 0)).y()
above = at(picture, combo.mapTo(dialog, QPoint(combo.width() // 2, -out)))
check("a size box the pad lands on at the view's edge is brought in, its ring whole",
      placed == 2 and landed >= round(20 * dialog.scale) and distance(above, rgb("#9184d9")) < 30,
      (f"placed {placed} px in, landed {landed} px in", above))
dialog.reject()
settle(0.3)
tv_dialog = ui_settings.SettingsDialog(dict(w.config, tv_mode=True), w, known_keys=set())
tv_dialog.show()
settle(0.8)
tv = float(w.config.get("tv_scale", _ui_rules.TV_SCALE_DEFAULT))
ring = getattr(tv_dialog, "focus_ring", None)
# Since Phase 99 the first control is the accent's row: the swatch chosen.
first = getattr(tv_dialog, "accent_swatches", {}).get(tv_dialog.accent()) if hasattr(tv_dialog, "accent") else None
check("in TV mode the first control is ringed, at TV mode's width",
      ring is not None and ring.target is (first or tv_dialog.reduce_box) and ring.isVisible()
      and ring.ring_width() == max(1, round(_ui_rules.TV_FOCUS_RING_WIDTH * tv)),
      (getattr(ring, "target", None), ring.ring_width() if ring is not None else None))
tv_dialog.reject()
settle(0.3)
w.close()

print("\n=== 6. the real library is exactly as it was found ===")
changed = box.finish()
check("overrides.json, config.json and catalog.json are byte for byte unchanged", not changed, changed)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
