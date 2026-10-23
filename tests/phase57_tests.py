"""Phase 57: the Nocturne restyle, step 4 of 6 -- a game's own page.

The design (#1d, read from the mockup's markup) measured on the live window at 1280x820:
the art's height and framing, with no shade laid over all of it; the floating buttons; a
170 px cover edged in neutral 500, 30 px from its title, 30 px above the first card, on
the cards' own left edge; the pills; the Play row and its gaps; the three marks as one
segmented switch, the chosen one ringed inside in the accent; the pad's ring 2 px outside
every other button; cards at the design's padding and type, the note's mark, About's line
height; the sessions' rows, columns and track; the design's day labels. Stats keeps its
own look until its step. Runs on a throwaway copy of the data; nothing is started.
"""
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))  # the project folder, one up from tests/
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import test_sandbox

box = test_sandbox.start()
REAL_SHOTS = PROJECT / "data" / "cache" / "screenshots"
box.copy_cache("steam_details", "steam_news.json", "steam_web.json",
               *[f"screenshots/{name}" for name in (os.listdir(REAL_SHOTS) if REAL_SHOTS.is_dir() else [])])

import logging

logging.basicConfig(level=logging.ERROR)

from PySide6.QtCore import QEventLoop, QPoint, Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QLabel

app = QApplication([])

from logic import focus, gamedetails, sessions
from presentation import ui_detail, ui_rules as _ui_rules, ui_window
from shared import rules


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


def safely(make, fallback=None):
    try:
        return make()
    except Exception as error:  # the code before this phase lacks the names: judge, do not crash
        print(f"         ({type(error).__name__}: {error})")
        return fallback


print("\n=== 1. the design's numbers ===")
check("the art: 435 high (430 and the 5 px on to the cards), or 54% of a taller window; "
      "fading from 35% down; the ground at 90% -> 25% -> none on the left; framed a quarter down",
      (ui_rules.DETAIL_HERO_HEIGHT, ui_rules.DETAIL_HERO_FRACTION, ui_rules.DETAIL_HERO_FADE_FROM,
       tuple(ui_rules.DETAIL_HERO_SIDE_SCRIM or ()), ui_rules.DETAIL_HERO_ANCHOR)
      == (435, 0.54, 0.35, ((0.0, 230), (0.5, 64), (1.0, 0)), 0.25))
check("no shade laid over all of the art any more", not hasattr(_ui_rules, "DETAIL_HERO_SHADE_ALPHA"))
check("the cover: 170 wide, corners 14, 30 from the words, a 40 px shadow dropped 16, edged in neutral 500",
      (ui_rules.DETAIL_COVER_WIDTH, ui_rules.DETAIL_COVER_RADIUS, ui_rules.DETAIL_COVER_GAP,
       ui_rules.DETAIL_COVER_SHADOW, ui_rules.DETAIL_COVER_SHADOW_DROP, ui_rules.COLOR_COVER_EDGE)
      == (170, 14, 30, 40, 16, "#9397ab"))
check("the title 46 px; the pills 30 high, 12.5 px words, 8 apart, 12 either side",
      (ui_rules.DETAIL_TITLE_PX, ui_rules.DETAIL_PILL_HEIGHT, ui_rules.DETAIL_PILL_PX,
       ui_rules.DETAIL_PILL_GAP, ui_rules.DETAIL_PILL_SIDE_PADDING) == (46, 30, 12.5, 8, 12))
check("the pills on the ground at 55%, their icons neutral 400, their words neutral 200, saves in accent 200",
      (ui_rules.COLOR_ON_ART_FAINT, ui_rules.COLOR_PILL_ICON, ui_rules.COLOR_PILL_TEXT, ui_rules.COLOR_PILL_SAVED)
      == ("rgba(22, 24, 38, 140)", "#b2b6ca", "#e4e7f5", "#e7e5fe"))
check("Play 170 x 48 with 16 px words; round buttons 44, icons 17 (19 for the dots); 10 apart, 18 before the switch",
      (ui_rules.DETAIL_PLAY_WIDTH, ui_rules.DETAIL_ACTION_HEIGHT, ui_rules.DETAIL_PLAY_PX,
       ui_rules.DETAIL_ROUND_BUTTON, ui_rules.DETAIL_ROUND_ICON_PX, ui_rules.DETAIL_MORE_ICON_PX,
       ui_rules.DETAIL_ACTION_GAP, ui_rules.DETAIL_SWITCH_GAP) == (170, 48, 16, 44, 17, 19, 10, 18))
check("the switch 40 high, 13 px words, 12 either side",
      (ui_rules.DETAIL_SEGMENT_HEIGHT, ui_rules.DETAIL_SEGMENT_PX, ui_rules.DETAIL_SEGMENT_SIDE_PADDING)
      == (40, 13, 12))
check("the floating buttons 36 high, 18 down and 24 in, 8 apart, 14 px words, 10 either side, the ground at 65%",
      (ui_rules.DETAIL_NAV_HEIGHT, ui_rules.DETAIL_NAV_TOP, ui_rules.DETAIL_NAV_SIDE, ui_rules.DETAIL_NAV_GAP,
       ui_rules.DETAIL_NAV_PX, ui_rules.DETAIL_NAV_SIDE_PADDING, ui_rules.COLOR_NAV)
      == (36, 18, 24, 8, 14, 10, "rgba(22, 24, 38, 166)"))
check("cards 18 x 20 inside, 18 apart, 15 px titles, 13.5 px words on a 1.6 line",
      (ui_rules.GAME_CARD_PADDING_Y, ui_rules.GAME_CARD_PADDING_X, ui_rules.GAME_CARD_GAP,
       ui_rules.GAME_CARD_TITLE_PX, ui_rules.GAME_CARD_TEXT_PX, ui_rules.GAME_CARD_TEXT_LINE)
      == (18, 20, 18, 15, 13.5, 1.6))
check("the note: neutral 200, a 2 px mark in accent 700, its words 12 px in",
      (ui_rules.COLOR_NOTE, ui_rules.COLOR_NOTE_MARK, ui_rules.NOTE_MARK, ui_rules.NOTE_INDENT)
      == ("#e4e7f5", "#5d5294", 2, 12))
check("sessions: 32 px rows, an 8 px bar on the raised surface, 12.5 px words, columns 86 / the rest / 62, 14 apart",
      (ui_rules.SESSION_ROW_HEIGHT, ui_rules.SESSION_BAR_HEIGHT, ui_rules.COLOR_SESSION_TRACK,
       ui_rules.SESSION_TEXT_PX, ui_rules.SESSION_DAY_WIDTH, ui_rules.SESSION_LENGTH_WIDTH,
       ui_rules.SESSION_COLUMN_GAP) == (32, 8, "#292b31", 12.5, 86, 62, 14))
# Stats kept its bars' old height until its own step; since Phase 58 it lists covers instead.
check("and Stats' share bars are gone with its own step", not hasattr(_ui_rules, "STATS_SHARE_BAR_HEIGHT"))

print("\n=== 2. the design's day labels ===")
day = getattr(ui_detail, "session_day", None)
today = date(2026, 10, 8)
local = lambda d, h=20: datetime(d.year, d.month, d.day, h, 30).astimezone()  # noqa: E731
labels = [day(local(today), today), day(local(today - timedelta(days=1)), today),
          day(local(date(2026, 10, 5)), today), day(local(date(2025, 10, 5)), today)] if day else []
check("Today, Yesterday, 'Mon 5 Oct', and the year when it is another one",
      labels == ["Today", "Yesterday", "Mon 5 Oct", "5 Oct 2025"], labels)

w = ui_window.MainWindow()
w.resize(1280, 820)
w.move(app.primaryScreen().availableGeometry().topLeft())
w.show()
settle(2.0)
focus.bring_to_front(int(w.winId()))
settle(0.4)
page = w.detail
shown = [v for v in w.views if not v.hidden and v.entry.launch_kind == "exe"]
subject = next((v for v in shown if sessions.load(v.data)
                and gamedetails.description(gamedetails.record_for(v))), None) or shown[0]
print(f"   the page shown: {subject.display_name}")
w.overrides.update(subject.key, **{rules.STATUS_KEY: "playing",
                                   rules.NOTES_KEY: "Brookhaven, 3rd floor -- the box puzzle is next."})
w.reload_views()
w.show_detail(subject.key)
settle(1.5)
content, viewport = page.content, page.scroll.viewport()


def in_window(widget, point=QPoint(0, 0)):
    return widget.mapTo(w, point)


print("\n=== 3. the art ===")
check("as tall as the design, or its share of the window", page.banner.height()
      == max(435, round(viewport.height() * 0.54)), (page.banner.height(), viewport.height()))
frame = page.banner._pixmap_for(0).toImage()
width, height = page.banner.width(), page.banner.height()
art = safely(lambda: (page.covers.banner(subject, width, height, 0.25) if not page.banner.frames[0]
                      else page.covers.image(page.banner.frames[0], width, height, 0.25)).toImage())
ratio = page.covers.ratio
spot = QPoint(round((width - 6) * ratio), round(6 * ratio))
check("framed a quarter of the way down, and nothing laid over its top right but the art itself",
      art is not None and distance(rgb(frame.pixelColor(spot)), rgb(art.pixelColor(spot))) <= 2,
      (rgb(frame.pixelColor(spot)), rgb(art.pixelColor(spot)) if art is not None else None))
foot = QPoint(spot.x(), frame.height() - 1)
check("its foot is see-through", frame.pixelColor(foot).alpha() < 8, frame.pixelColor(foot).alpha())

print("\n=== 4. the cover, the words and the cards on their edges ===")
cover = page.cover_art.cover_rect()
cover_left = page.cover_art.mapTo(content, cover.topLeft()).x()
cover_right = page.cover_art.mapTo(content, cover.topRight()).x() + 1
cover_foot = page.cover_art.mapTo(content, cover.bottomLeft()).y() + 1
check("the cover is 170 wide", cover.width() == 170, cover.width())
title_left = page.title_label.mapTo(content, QPoint(0, 0)).x()
check("its title starts 30 px after it", title_left - cover_right == 30, title_left - cover_right)
note_left = page.note_card.mapTo(content, QPoint(0, 0)).x()
note_top = page.note_card.mapTo(content, QPoint(0, 0)).y()
check("the cards start on the cover's own left edge, 48 px in (they sat 12 px further in before)",
      note_left == cover_left == 48, (note_left, cover_left))
check("and 30 px under its foot", note_top - cover_foot == 30, note_top - cover_foot)
play_foot = page.play_button.mapTo(content, QPoint(0, page.play_button.height())).y()
check("the Play row's foot stands 4 px above the cover's", cover_foot - play_foot == 4, cover_foot - play_foot)
shot = w.grab().toImage()
middle = page.cover_art.mapTo(w, QPoint(cover.left() - 1, cover.center().y()))
check("the cover is edged in neutral 500, just outside it", distance(at(shot, middle), rgb("#9397ab")) < 30,
      at(shot, middle))
check("the title is 46 px", page.title_label.font().pixelSize() == 46, page.title_label.font().pixelSize())

print("\n=== 5. the pills ===")
pills = [pill for pill in page.pills.values() if not pill.isHidden()]
check("30 high", bool(pills) and all(pill.height() == 30 for pill in pills), [p.height() for p in pills])
gaps = [b.x() - (a.x() + a.width()) for a, b in zip(pills, pills[1:]) if b.y() == a.y()]
check("8 apart", bool(gaps) and set(gaps) == {8}, gaps)
check("12.5 px words", all(abs(pill.font().pointSizeF() - 12.5 * 72 / 96) < 0.05 for pill in pills),
      [p.font().pointSizeF() for p in pills])
first = pills[0]
inks = [at(shot, in_window(first, QPoint(x, y))) for x in range(first.width()) for y in range(first.height())]
brightest = max(inks, key=sum)
check("the words neutral 200", distance(brightest, rgb("#e4e7f5")) < 24, brightest)
copied = dict(gamedetails.metadata(gamedetails.record_for(subject), subject)).get("Saves copied", "")
saves = page.pills["Saves copied"]
check("and only copied saves in the accent", saves.isHidden() or saves.property("tone")
      == ("saved" if copied and copied != "not yet" else ""), (copied, saves.property("tone")))

print("\n=== 6. the Play row ===")
play, star, folder, more = page.play_button, page.favorite_button, page.folder_button, page.more_button
check("Play is 170 x 48, its words 16 px", (play.width(), play.height(), play.font().pixelSize()) == (170, 48, 16),
      (play.width(), play.height(), play.font().pixelSize()))
check("the round buttons are 44", all((b.width(), b.height()) == (44, 44) for b in (star, folder, more)))
row_gaps = [b.x() - (a.x() + a.width()) for a, b in ((play, star), (star, folder), (folder, more))]
check("everything 10 apart", row_gaps == [10, 10, 10], row_gaps)
switch = page.segment_bar
check("and 18 before the switch, which is 40 high", (switch.x() - (more.x() + more.width()), switch.height())
      == (18, 40), (switch.x() - (more.x() + more.width()), switch.height()))
marks = page.status_buttons
widths = {status: button.width() for status, button in marks.items()}
check("each mark as wide as its own words, 12 px either side", all(
    button.width() == button.sizeHint().width() for button in marks.values()), widths)
lit = marks["playing"]
check("the chosen mark is the accent's words, ringed inside in the accent",
      lit.isChecked() and distance(at(shot, in_window(lit, QPoint(lit.width() // 2, 0))), rgb(_ui_rules.COLOR_ACCENT)) < 30,
      at(shot, in_window(lit, QPoint(lit.width() // 2, 0))))
inside = at(shot, in_window(lit, QPoint(4, lit.height() // 2)))
check("but not filled: the art shows inside it", distance(inside, rgb(_ui_rules.COLOR_ACCENT)) > 60
      and distance(inside, rgb(_ui_rules.COLOR_ACCENT_HOVER)) > 60, inside)
page.status_buttons["finished"].click()
settle(0.4)
check("choosing another changes no width", {s: b.width() for s, b in marks.items()} == widths,
      {s: b.width() for s, b in marks.items()})
page.status_buttons["playing"].click()
settle(0.4)

print("\n=== 7. the floating buttons ===")
back, prev, nxt = page.back_button, page.prev_button, page.next_button
room = page.width() - (page.scroll.verticalScrollBar().width()
                       if page.scroll.verticalScrollBar().isVisible() else 0)
check("36 high, Library 18 down and 24 in", (back.height(), back.x(), back.y()) == (36, 24, 18),
      (back.height(), back.x(), back.y()))
check("Next game ends 24 px from the right, Previous 8 px before it",
      (room - (nxt.x() + nxt.width()), nxt.x() - (prev.x() + prev.width())) == (24, 8),
      (room - (nxt.x() + nxt.width()), nxt.x() - (prev.x() + prev.width())))

print("\n=== 8. the pad's ring: 2 px outside the button it is on ===")
out = 3  # the design's: 2 px wide and 2 px out, so its middle is 3 px from the edge


def ringed(widget, point, expect=True):
    image = w.grab().toImage()
    colour = at(image, in_window(widget, point))
    hit = distance(colour, rgb(_ui_rules.TILE_FOCUS_COLOR)) < 34
    return hit == expect, colour


page.focus_play()
settle(0.4)
ok, colour = ringed(play, QPoint(-out, play.height() // 2))
check("Play, the button a page opens on", ok, colour)
ok, colour = ringed(play, QPoint(-1, play.height() // 2), expect=False)
check("with the gap between them not ringed", ok, colour)
star.setFocus(Qt.FocusReason.TabFocusReason)
settle(0.3)
ok, colour = ringed(star, QPoint(star.width() // 2, -out))
check("the star, round", ok, colour)
ok, colour = ringed(play, QPoint(-out, play.height() // 2), expect=False)
check("and Play's ring has gone", ok, colour)
back.setFocus(Qt.FocusReason.TabFocusReason)
settle(0.3)
ok, colour = ringed(back, QPoint(back.width() // 2, back.height() + out - 1))
check("Library, floating over the page", ok, colour)
mark = page.status_buttons["dropped"]
mark.setFocus(Qt.FocusReason.TabFocusReason)
settle(0.3)
ok, colour = ringed(mark, QPoint(mark.width() // 2, 1))
check("a mark is ringed inside, as the design rings a choice", ok, colour)
page.scroll.verticalScrollBar().setValue(120)
page.notes_button.setFocus(Qt.FocusReason.TabFocusReason)
settle(0.4)
ok, colour = ringed(page.notes_button, QPoint(-out, page.notes_button.height() // 2))
check("and the ring follows a button the page has scrolled", ok, colour)
page.scroll.verticalScrollBar().setValue(0)
settle(0.3)

print("\n=== 9. the cards ===")
check("18 px top and bottom, 20 either side", page.note_card.layout().contentsMargins().left() == 20
      and page.note_card.layout().contentsMargins().top() == 18)
check("15 px titles on the game page", page.note_card.title.font().pixelSize() == 15,
      page.note_card.title.font().pixelSize())
w.show_stats()
settle(0.8)
stats_title = w.stats_page.chart_card.title.font().pixelSize()
check("and Stats' titles are the design's 15 px too, since its own step (Phase 58)", stats_title == 15,
      stats_title)
w.show_detail(subject.key)
settle(1.2)
shot = w.grab().toImage()
check("the columns 18 apart", page.sessions_card.isHidden()
      or page.sessions_card.x() - (page.note_card.x() + page.note_card.width()) == 18,
      page.sessions_card.x() - (page.note_card.x() + page.note_card.width()))
note = page.note
mark_colour = at(shot, in_window(note, QPoint(0, note.height() // 2)))
check("the note's mark is accent 700", distance(mark_colour, rgb("#5d5294")) < 16, mark_colour)
ink = [x for x in range(1, 40) if any(sum(at(shot, in_window(note, QPoint(x, y)))) > 450
                                      for y in range(note.height()))]
check("and its words start 12 px in", bool(ink) and 12 <= ink[0] <= 14, ink[:3])
lines = page.description
if lines.isVisibleTo(page) and lines.width() > 0:
    plain = QLabel()
    plain.setFont(lines.font())
    plain.setWordWrap(True)
    plain.setText(gamedetails.description(gamedetails.record_for(subject)))
    tight = plain.heightForWidth(lines.width())
    check("About's lines are the design's 1.6 apart, not the font's own", lines.height() > tight * 1.2,
          (lines.height(), tight))
else:
    check("About's lines are the design's 1.6 apart (no description here to measure)", True)

print("\n=== 10. the sessions ===")
bars = page.session_bars
if bars.rows:
    check("32 px rows", bars.height() == 32 * len(bars.rows), (bars.height(), len(bars.rows)))
    box_rect = safely(lambda: bars.bar_box())
    check("the bars start after the 86 px day column and its 14 px gap, or a wider one",
          box_rect is not None and box_rect.left() >= 86 + 14, box_rect)
    shortest = min(range(len(bars.rows)), key=lambda i: bars.rows[i][1])
    if box_rect is not None:
        end = QPoint(round(box_rect.right()) - 6, round(32 * shortest + 16))
        track = at(w.grab().toImage(), in_window(bars, end))
        check("each lies on a track in the raised surface, the room's whole width",
              bars.rows[shortest][1] == max(r[1] for r in bars.rows) or distance(track, rgb("#292b31")) <= 3,
              track)
    check("days written the design's way", all(row[0] in ("Today", "Yesterday") or len(row[0].split()) == 3
                                               and " at " not in row[0] for row in bars.rows),
          [row[0] for row in bars.rows])
else:
    check("(no sessions in this library to measure)", True)

print("\n=== 11. TV mode's thicker ring ===")
w.set_tv_mode(True)
settle(1.5)
w.show_detail(subject.key)
settle(1.2)
page.focus_play()
settle(0.4)
tv = float(w.config.get("tv_scale", _ui_rules.TV_SCALE_DEFAULT))
ring = getattr(page, "focus_ring", None)
check("the page's ring is TV mode's width", ring is not None
      and ring.ring_width() == max(1, round(_ui_rules.TV_FOCUS_RING_WIDTH * tv)),
      ring.ring_width() if ring is not None else None)
check("and it is up, on Play", ring is not None and ring.isVisible() and ring.target is page.play_button)
w.set_tv_mode(False)
settle(1.0)
w.close()

print("\n=== 12. the real library is exactly as it was found ===")
changed = box.finish()
check("overrides.json, config.json and catalog.json are byte for byte unchanged", not changed, changed)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
