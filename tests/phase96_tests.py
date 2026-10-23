"""Phase 96: the recap card -- a month, and a year, in review as an image to share.

  1. the period arithmetic: half-open, local wall time; 23:59 on the last day is in, 00:00 the next
     day is not; a month boundary across the year;
  2. the figures of a planted month, worked out by hand: hours, sessions, games, the top three (a tie
     to the name), the longest session, the part of the day and the weekday, the new games, what was
     paid, the wishlist's largest drop, the comparison, the footer;
  3. one rule: the card's month equals Stats' month and the sessions reports' counts -- on the
     planted library and on the copy of the user's;
  4. the quiet month (one session) with every absent line left out and no zero drawn; a month with
     none says so;
  5. nothing personal on the card: no backslash path, no drive letter, no "@", no account name;
  6. one image: RECAP_IMAGE_WIDTH x RECAP_IMAGE_HEIGHT at device pixel ratio 1, the same pixels from a
     second process at QT_SCALE_FACTOR=2.25;
  7. Copy hands the image to the clipboard; Save writes a PNG QImage reopens at that size;
  8. the dialog: the chooser changes the period, the pad drives it; A on Stats opens it; the Stats
     card's line is the dialog's month;
  9. the render's time, the reports' time, the layers;
 10. the year: its period, its card (top five, the twelve months as Stats draws them, the busiest named,
     the games played at least once), its chooser entries, its room on the card;
 11. the offer: once a month for a month with sessions, never for one without, never twice, the year's
     from 15 December and through January, never in a first run; a toast, or the tray's balloon;
 12. the documents; the real data, config and Run key unchanged.

On a throwaway copy of the data; the network is blocked; the user's clipboard is never touched.
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import sources  # the build log's notes (Phase 91)
import test_sandbox

box = test_sandbox.start({"allow_network": False, "startup_scan": False, "tv_mode": False})
attempts: list[str] = []


def no_network(request, *args, **kwargs):
    attempts.append(getattr(request, "full_url", str(request)))
    raise OSError("the network is blocked in this suite")


urllib.request.urlopen = no_network

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

app = QApplication([])

from adapters import controller
from data_access import library_db
from data_access import recap as recap_queries
from data_access import reports as data_reports
from logic import recap
from logic import reports as reports_module
from logic import saves
from logic import stats
from presentation import ui_recap, ui_rules, ui_tv, ui_window
from shared import humanize, rules

passed = failed = 0
WORK = Path(box.folder) / "p96"
WORK.mkdir(exist_ok=True)
NOW = datetime(2026, 10, 18, 17, 30).astimezone()  # a fixed moment, after the planted months


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"   PASS  {name}")
    else:
        failed += 1
        print(f"   FAIL  {name}   {detail}")


def unreached(section, exc):
    import traceback
    traceback.print_exc()
    check(f"section {section} ran to its end", False, repr(exc))


def settle(seconds):
    loop = QEventLoop()
    QTimer.singleShot(int(seconds * 1000), loop.quit)
    loop.exec()


def picture(path: Path, width: int, height: int, colour: str) -> None:
    """A cover image of our own, noisy enough to pass the artwork size floor."""
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor(colour))
    painter = QPainter(image)
    for i in range(0, width, 7):
        painter.fillRect(i, (i * 13) % height, 5, height // 3, QColor((i * 37) % 255, (i * 11) % 255, 120))
    painter.end()
    image.save(str(path), quality=95)


class Made:
    """A fresh library database (the current version) with rows put in by hand, on a scratch file."""

    def __init__(self, name: str) -> None:
        self.path = WORK / f"{name}.db"
        self.path.unlink(missing_ok=True)
        self.store = library_db.LibraryStore(self.path)
        self.c = self.store._conn
        self.scan = None

    def game(self, key, name, first_seen="2026-08-01T10:00:00+03:00", appid=None, tool=None, source="folders",
             cover=None, installed=True, kind="exe"):
        if appid is not None:
            self.c.execute("INSERT OR IGNORE INTO steam_app (appid, has_record, name, app_type) VALUES (?, 1, ?, 'game')",
                           (appid, name))
        gid = self.c.execute(
            "INSERT INTO game (identity_key, source, known_as, name_origin, steam_appid, appid_source, is_tool, "
            "first_seen, cover_path) VALUES (?, ?, ?, 'scan', ?, ?, ?, ?, ?)",
            (key, source, name if name != key else None, appid, "search" if appid else None, tool, first_seen, cover)
        ).lastrowid
        if name == key:  # a record with no name of its own: v_library falls back to the identity key
            self.c.execute("UPDATE game SET name_origin = 'none' WHERE id = ?", (gid,))
        if installed:
            if self.scan is None:
                self.scan = self.c.execute("INSERT INTO scan (finished_at, entry_count, trigger) VALUES (?, 0, 'manual')",
                                           ("2026-10-01T10:00:00+03:00",)).lastrowid
            position = self.c.execute("SELECT COUNT(*) FROM install").fetchone()[0]
            self.c.execute("INSERT INTO install (game_id, position, display_name, install_dir, launch_kind, "
                           "launch_target, working_dir, icon_hint, size_on_disk, detection, scan_id) "
                           "VALUES (?, ?, ?, ?, ?, 'x', 'x', 'x', 1000, 'heuristic', ?)",
                           (gid, position, name if name != key else "x", f"C:\\made\\{gid}", kind, self.scan))
        return gid

    def session(self, gid, started, minutes, origin="launched"):
        self.c.execute("INSERT INTO session (game_id, started_at, minutes, origin) VALUES (?, ?, ?, ?)",
                       (gid, started, minutes, origin))

    def purchase(self, gid, cents, bought_on, currency="EUR"):
        self.c.execute("INSERT INTO purchase (game_id, paid_cents, currency, store, bought_on, recorded_at) "
                       "VALUES (?, ?, ?, 'Steam', ?, '2026-09-25T10:00:00+03:00')", (gid, cents, currency, bought_on))

    def account(self, account_id, persona, login):
        self.c.execute("INSERT INTO steam_account (account_id, steam_id64, account_name, persona, is_mine, first_seen, "
                       "last_seen) VALUES (?, ?, ?, ?, 1, ?, ?)",
                       (account_id, account_id + 76561197960265728, login, persona, "2026-08-01", "2026-10-01"))

    def wish(self, account_id, appid, name, read_at="2026-08-20T10:00:00+00:00"):
        self.c.execute("INSERT OR IGNORE INTO steam_app (appid, has_record, name, app_type) VALUES (?, 1, ?, 'game')",
                       (appid, name))
        self.c.execute("INSERT OR IGNORE INTO wishlist_read (account_id, read_at, state, items) VALUES (?, ?, 'items', 1)",
                       (account_id, read_at))
        self.c.execute("INSERT INTO wishlist (account_id, appid, priority, first_seen, last_seen) VALUES (?, ?, 0, ?, ?)",
                       (account_id, appid, read_at, read_at))

    def price(self, appid, observed, cents, name="app"):
        self.c.execute("INSERT OR IGNORE INTO steam_app (appid, has_record, name, app_type) VALUES (?, 1, ?, 'game')",
                       (appid, name))
        self.c.execute("INSERT INTO price_snapshot (appid, observed_at, kind, currency, initial_cents, final_cents, "
                       "discount_percent) VALUES (?, ?, 'priced', 'EUR', ?, ?, 0)", (appid, observed, cents, cents))

    def done(self):
        self.c.commit()
        return self.store


print("=== 1. the period arithmetic ===")
try:
    september = recap.Period(2026, 9)
    check("a month is [the 1st 00:00, the next 1st 00:00), local wall time",
          september.bounds()["start"] == "2026-09-01T00:00:00" and september.bounds()["end"] == "2026-10-01T00:00:00")
    check("a session at 23:59 on the last day belongs to the month", september.holds(datetime(2026, 9, 30, 23, 59)))
    check("one at 00:00 on the 1st of the next does not", not september.holds(datetime(2026, 10, 1, 0, 0)))
    check("and one at 00:00 on its own 1st does", september.holds(datetime(2026, 9, 1, 0, 0)))
    december = recap.Period(2026, 12)
    check("December ends on 1 January of the next year, and January's month before is December",
          december.end == datetime(2027, 1, 1) and recap.Period(2027, 1).previous() == december
          and december.following() == recap.Period(2027, 1))
    check("the purchase days are half-open too", september.bounds()["start_day"] == "2026-09-01"
          and september.bounds()["end_day"] == "2026-10-01")
    utc = september.bounds()["start_utc"]
    check(f"the price bounds are UTC text, as price_snapshot keeps them ({utc})",
          utc.endswith("+00:00") and datetime.fromisoformat(utc) == datetime(2026, 9, 1).astimezone())
    check("this month and last month from a moment", recap.this_month(NOW) == recap.Period(2026, 10)
          and recap.last_month(NOW) == september)
    check("the chooser: This month, Last month, This year", [w for w, _ in recap.choices(NOW)]
          == ["This month", "Last month", "This year"])
    january = recap.choices(datetime(2027, 1, 5).astimezone())
    check("and in January, Last year too: the year just ended", [w for w, _ in january][-1] == "Last year"
          and january[-1][1] == recap.Period(2026), january)
    year = recap.Period(2026)
    check("a year is [1 January, the next 1 January), its label the year, its months twelve",
          (year.start, year.end, year.label, year.key, len(year.months())) ==
          (datetime(2026, 1, 1), datetime(2027, 1, 1), "2026", "2026", 12) and year.previous() == recap.Period(2025))
    check("the saved file's name", september.file_name == "Game Launcher - September 2026.png", september.file_name)
except Exception as exc:
    unreached("1", exc)

print("\n=== 2. a planted month, worked out by hand ===")
try:
    cache = WORK / "cache"
    (cache / "steam_art").mkdir(parents=True, exist_ok=True)
    picture(WORK / "alpha.jpg", 600, 900, "#7a3b8f")
    picture(WORK / "bravo_wide.jpg", 920, 430, "#2f6f8f")  # landscape: shown whole, on its own backdrop
    picture(cache / "steam_art" / "555.jpg", 600, 900, "#8f6a2f")  # Charlie's cover, uninstalled, from the cache
    m = Made("planted")
    a = m.game("c:\\games\\alpha", "Alpha", cover=str(WORK / "alpha.jpg"))
    b = m.game("steam:100", "Bravo", appid=100, source="steam", cover=str(WORK / "bravo_wide.jpg"), kind="uri")
    c = m.game("c:\\games\\charlie", "Charlie", appid=555, installed=False)
    d = m.game("c:\\games\\delta", "Delta", tool=1)
    e = m.game("c:\\games\\echo", "Echo", first_seen="2026-09-10T12:00:00+03:00")
    m.game("c:\\games\\foxtrot-old", "foxtrot", first_seen="2026-08-02T12:00:00+03:00", installed=False)
    m.game("c:\\games\\foxtrot", "Foxtrot", first_seen="2026-09-11T12:00:00+03:00")  # a name seen before
    m.game("xbox:no-name", "xbox:no-name", first_seen="2026-09-12T12:00:00+03:00", source="xbox",
           installed=False)  # no name of its own, not even a scan's: its key only
    h0 = m.game("c:\\games\\hotel-1", "Hotel One", first_seen="2026-08-03T12:00:00+03:00", installed=False)
    h = m.game("c:\\games\\hotel-2", "Hotel Two", first_seen="2026-09-13T12:00:00+03:00")
    m.c.execute("INSERT INTO lineage (game_id, earlier_id, relation, position) VALUES (?, ?, 'carried_from', 0)", (h, h0))
    m.game("c:\\games\\juliet", "Juliet", first_seen="2026-09-14T12:00:00+03:00")  # new, not played
    m.session(a, "2026-07-10T20:00:00+03:00", 30)    # July: history begins before August
    m.session(a, "2026-08-31T23:59:00+03:00", 45)    # August's last minute: not September's
    m.session(a, "2026-09-01T00:00:00+03:00", 60)    # September's first: Tuesday, after midnight
    m.session(a, "2026-09-15T20:30:00+03:00", 90)    # Tuesday evening
    m.session(b, "2026-09-30T23:59:00+03:00", 120)   # Wednesday, the month's last minute: in
    m.session(b, "2026-10-01T00:00:00+03:00", 30)    # October's first: out
    m.session(c, "2026-09-05T02:00:00+03:00", 200)   # Saturday night, uninstalled since: the longest
    m.session(d, "2026-09-10T10:00:00+03:00", 500)   # a tool: never counted
    m.session(e, "2026-09-12T21:00:00+03:00", 120, origin="observed")  # Saturday evening, seen running
    m.purchase(a, 1999, "2026-09-03")
    m.purchase(b, 999, None)            # no day: belongs to no month
    m.purchase(c, 2999, "2026-10-01")   # October's
    m.purchase(e, 500, "2026-09-20", currency="RON")
    m.account(7, "Persona Secreta", "login_secret")
    m.wish(7, 200, "Wished Small")
    m.wish(7, 300, "Wished Big")
    for observed, cents in (("2026-08-25T09:00:00+00:00", 2999), ("2026-09-10T09:00:00+00:00", 1999),
                            ("2026-09-20T09:00:00+00:00", 1499), ("2026-10-02T09:00:00+00:00", 499)):
        m.price(200, observed, cents, "Wished Small")
    for observed, cents in (("2026-09-01T09:00:00+00:00", 5000), ("2026-09-15T09:00:00+00:00", 3000)):
        m.price(300, observed, cents, "Wished Big")
    for observed, cents in (("2026-09-01T09:00:00+00:00", 9999), ("2026-09-16T09:00:00+00:00", 999)):
        m.price(400, observed, cents, "Not Wished")
    planted = m.done()
    source = planted.recap()
    card = recap.build(source, september, NOW)
    check("590 minutes, 5 sessions, 4 games, 1 watched -- the tool's 500 and August's and October's minutes left out",
          (card.minutes, card.sessions, card.games, card.observed) == (590, 5, 4, 1),
          (card.minutes, card.sessions, card.games, card.observed))
    check("the big number: 9.8 h", (card.headline, card.unit) == ("9.8", "h"), (card.headline, card.unit))
    check("the counts", card.counts == ("5 sessions", "across 4 games"), card.counts)
    check("the top three, a tie at 120 minutes going to the name (Bravo before Echo)",
          [(g.name, g.minutes) for g in card.top] == [("Charlie", 200), ("Alpha", 150), ("Bravo", 120)],
          [(g.name, g.minutes) for g in card.top])
    check("each with its share of the first", [round(g.share, 3) for g in card.top] == [1.0, 0.75, 0.6])
    facts = {f.kind: f for f in card.facts}
    check("the longest session: Charlie's 200 minutes, Sat 5 Sep",
          facts[recap.LONGEST].value == humanize.playtime(200 * 60)
          and facts[recap.LONGEST].detail == "Sat 5 Sep, Charlie", facts[recap.LONGEST])
    check("most starts in the evening (3 of 5), most time on Saturdays (320 minutes)",
          facts[recap.WHEN].value == "In the evening" and facts[recap.WHEN].detail == "Most time on Saturdays",
          facts[recap.WHEN])
    check("new this month: Echo and Juliet -- not a name seen before, a record with no name, or a later install",
          facts[recap.NEW].names == ("Echo", "Juliet") and facts[recap.NEW].value == "2 games", facts[recap.NEW])
    check("what was paid, by the day bought, each currency on its own",
          facts[recap.MONEY].value == humanize.money(1999, "EUR") + " + " + humanize.money(500, "RON")
          and facts[recap.MONEY].detail.startswith("2 purchases"), facts[recap.MONEY])
    check("the wishlist's largest drop seen in the month: Wished Big, 50 to 30 (not October's, not an unwished game)",
          card.raw["drop"]["name"] == "Wished Big" and (card.raw["drop"]["before_cents"], card.raw["drop"]["final_cents"])
          == (5000, 3000) and "Wished Big fell" in facts[recap.MONEY].detail, card.raw["drop"])
    check("a past month never says what is on sale today", card.raw["on_sale"] == 0)
    check("the comparison: 9 h more than in August (590 against 45, August recorded whole)",
          card.comparison == "9 h more than in August", card.comparison)
    check("the footer: how the sessions were measured, and nothing of Steam's own time",
          card.footer[0] == "From 5 sessions the launcher timed or watched; 1 was watched, each end within 5 s."
          and card.footer[-1] == recap.STEAM_LINE, card.footer)
    august = recap.build(source, recap.Period(2026, 8), NOW)
    check("August: no comparison (July only from the 10th), and the footer says when history begins",
          august.comparison == "" and any("Recorded from" in line for line in august.footer) is False
          and august.minutes == 45, (august.comparison, august.footer))
    july = recap.build(source, recap.Period(2026, 7), NOW)
    check("July, the month history began in, says it was recorded from the 10th",
          any(line.startswith("Recorded from 10 Jul") for line in july.footer), july.footer)
    running = recap.build(source, recap.Period(2026, 10), datetime(2026, 10, 18).astimezone())
    check("October, still running: 'Month so far', no comparison", running.running and running.title == "Month so far"
          and running.comparison == "")
except Exception as exc:
    unreached("2", exc)

print("\n=== 3. one rule: the card, Stats and the sessions reports count the same sessions ===")
try:
    oracle = stats.gather([], planted, NOW)
    by_month = {(x.year, x.month): x.minutes for x in oracle.months}
    rows = {(r["year"], r["month"]): r["minutes"] for r in planted.reports().rows("stats_months")}
    check("September: the card's 590 = Stats' month = the reports' stats_months",
          card.minutes == by_month[(2026, 9)] == rows[(2026, 9)], (card.minutes, by_month[(2026, 9)], rows))
    months = [recap.Period(2026, k) for k in (7, 8, 9, 10)]
    totals = [recap.build(source, p, NOW) for p in months]
    summary = planted.reports().one("session_summary")
    check("the months add up to report 5's sessions and minutes, every one counted once",
          sum(t.sessions for t in totals) == summary["sessions"] and sum(t.minutes for t in totals) == summary["minutes"],
          ([(t.sessions, t.minutes) for t in totals], summary))
    check("and the tool's session counted nowhere", summary["minutes"] == 30 + 45 + 590 + 30)
    check("Stats' this month is the card's This month",
          stats.gather([], planted, datetime(2026, 10, 18).astimezone()).minutes_this_month == totals[-1].minutes == 30)
    window = ui_window.MainWindow()
    window.detail.allow_network = False
    window.resize(1200, 820)
    window.show()
    settle(1.0)
    window._stop_watch()
    real = window.overrides.recap()
    real_stats = stats.gather(window.views, window.overrides)
    real_rows = {(r["year"], r["month"]): r["minutes"] for r in window.overrides.reports().rows("stats_months")}
    agree = []
    for month in real_stats.months:
        if not month.recorded:
            continue
        built = recap.build(real, recap.Period(month.year, month.month))
        agree.append((month.year, month.month, built.minutes, month.minutes, real_rows.get((month.year, month.month), 0)))
    check(f"on the copy of the user's library, every recorded month: the card = Stats = stats_months ({len(agree)} months)",
          agree and all(x == y == z for _, _, x, y, z in agree), agree)
except Exception as exc:
    unreached("3", exc)

print("\n=== 4. the quiet month, and the month with none ===")
try:
    q = Made("quiet")
    only = q.game("c:\\games\\quiet", "Quiet Game", first_seen="2026-08-01T10:00:00+03:00")
    q.session(only, "2026-11-08T19:30:00+02:00", 47)
    quiet_store = q.done()
    quiet = recap.build(quiet_store.recap(), recap.Period(2026, 11), datetime(2026, 12, 2).astimezone())
    check("one session: one game, its lines beside its cover, and no facts about sessions",
          len(quiet.top) == 1 and quiet.single and not quiet.facts, (quiet.single, quiet.facts))
    check("in its own words: 47 min in one sitting, on Sunday 8 November in the evening",
          quiet.single[0] == "47 min, in one sitting" and quiet.single[1] == "Sunday 8 November, in the evening",
          quiet.single)
    art = ui_recap.Art(None, {}, cache_dir=str(cache))
    drawn = ui_recap.paint(quiet, art).drawn
    zero = [s for s in drawn if s.strip() in ("0", "0 h", "0 min") or re.match(r"^0\b", s.strip())]
    check("no zero is drawn anywhere on it", not zero, zero)
    check("and nothing absent is drawn: no longest session, no new games, no money",
          not any(s in drawn for s in ("LONGEST SESSION", "NEW THIS MONTH", "SPENT", "YOUR WISHLIST")), drawn)
    none = recap.build(quiet_store.recap(), recap.Period(2026, 6), datetime(2026, 12, 2).astimezone())
    drawn_none = ui_recap.paint(none, art).drawn
    check("a month with no sessions: a card that says so", none.empty and "No sessions recorded" in drawn_none
          and "The launcher saw no sessions in June 2026." in drawn_none, drawn_none)
    check("and draws no number at all", not any(re.search(r"\d+ (h|min|sessions?)\b", s) for s in drawn_none), drawn_none)
except Exception as exc:
    unreached("4", exc)

print("\n=== 5. nothing personal on the card ===")
try:
    art = ui_recap.Art(None, {}, cache_dir=str(cache))
    drawn = ui_recap.paint(card, art).drawn
    every = drawn + recap.strings(card)
    bad = [s for s in every if "\\" in s or re.search(r"(?<![A-Za-z])[A-Za-z]:", s) or "@" in s
           or "Persona Secreta" in s or "login_secret" in s or "made" in s.lower()]
    check(f"{len(every)} strings drawn or handed to the card: no path, no drive letter, no '@', no account name",
          every and not bad, bad)
    check("the cover paths and the planted install folders are nowhere in it",
          not any(str(WORK) in s or "C:\\made" in s for s in every))
except Exception as exc:
    unreached("5", exc)

print("\n=== 6. one image, the same pixels at 225% ===")
try:
    began = time.perf_counter()
    image = ui_recap.render(card, ui_recap.Art(None, {}, cache_dir=str(cache)))
    here = WORK / "here.png"
    image.save(str(here))
    check(f"{image.width()} x {image.height()} at device pixel ratio {image.devicePixelRatio()}",
          (image.width(), image.height(), image.devicePixelRatio())
          == (ui_rules.RECAP_IMAGE_WIDTH, ui_rules.RECAP_IMAGE_HEIGHT, 1.0))
    child = WORK / "child.py"
    child.write_text(f'''import sys
from datetime import datetime
from pathlib import Path
sys.path.insert(0, {str(PROJECT)!r})
from shared import paths
paths.data_dir = lambda: Path({str(box.folder)!r})
from PySide6.QtWidgets import QApplication
app = QApplication([])
from data_access import library_db
from logic import recap
from presentation import ui_recap
store = library_db.LibraryStore(Path({str(m.path)!r}))
card = recap.build(store.recap(), recap.Period(2026, 9), datetime(2026, 10, 18, 17, 30).astimezone())
image = ui_recap.render(card, ui_recap.Art(None, {{}}, cache_dir={str(cache)!r}))
image.save({str(WORK / "there.png")!r})
print(app.primaryScreen().devicePixelRatio())
store.close()
''', encoding="utf-8")
    env = dict(os.environ, QT_SCALE_FACTOR="2.25")
    run = subprocess.run([sys.executable, str(child)], capture_output=True, text=True, env=env, timeout=120)
    ratio = (run.stdout.strip().splitlines() or ["?"])[-1]
    check(f"a second process at QT_SCALE_FACTOR=2.25 (its screen's ratio {ratio}) ran", run.returncode == 0
          and float(ratio) >= 2.25, run.stderr[-500:])
    there = QImage(str(WORK / "there.png"))
    check("and made the same pixels, every one", there == QImage(str(here)), (there.size(), image.size()))
except Exception as exc:
    unreached("6", exc)

print("\n=== 7. Copy and Save ===")
try:
    handed = []

    class Clipboard:
        def setImage(self, image):  # noqa: N802 -- Qt's name
            handed.append(QImage(image))

    real_clipboard = ui_recap.QGuiApplication.clipboard
    ui_recap.QGuiApplication.clipboard = staticmethod(lambda: Clipboard())
    real_save_dialog = ui_recap.QFileDialog.getSaveFileName
    target = WORK / "saved card"
    asked = []
    ui_recap.QFileDialog.getSaveFileName = staticmethod(lambda *a: (asked.append(a[2]) or str(target), "PNG image (*.png)"))
    try:
        dialog = ui_recap.RecapDialog(source, ui_recap.Art(None, {}, cache_dir=str(cache)), None, now=NOW)
        dialog.group.button(1).setChecked(True)  # Last month: September
        dialog.copy()
        check("Copy hands the card itself to the clipboard, full size (the user's own clipboard untouched)",
              len(handed) == 1 and handed[0] == dialog.image and handed[0].width() == ui_rules.RECAP_IMAGE_WIDTH)
        dialog.save()
        saved = Path(str(target) + ".png")
        reopened = QImage(str(saved))
        check("Save writes one PNG where it is told, and QImage reopens it at the card's size",
              saved.is_file() and (reopened.width(), reopened.height())
              == (ui_rules.RECAP_IMAGE_WIDTH, ui_rules.RECAP_IMAGE_HEIGHT), saved)
        pictures = saves.known_folder(rules.RECAP_SAVE_FOLDER)
        check(f"it offers the Pictures folder Windows names ({pictures}), and the period's own file name",
              pictures and asked and asked[0] == os.path.join(pictures, "Game Launcher - September 2026.png"), asked)
        dialog.deleteLater()
    finally:
        ui_recap.QGuiApplication.clipboard = real_clipboard
        ui_recap.QFileDialog.getSaveFileName = real_save_dialog
except Exception as exc:
    unreached("7", exc)

print("\n=== 8. the dialog, the pad, the Stats card ===")
try:
    made = []
    real_exec = ui_recap.RecapDialog.exec
    ui_recap.RecapDialog.exec = lambda self: made.append(self) or 0
    try:
        window.show_stats()
        settle(0.5)
        window._on_pad_action(controller.ACTIVATE)
        check("A on the Stats page opens the recap's dialog", len(made) == 1)
        window.stats_page.share_button.click()
        check("and so does the Recap card's button", len(made) == 2)
    finally:
        ui_recap.RecapDialog.exec = real_exec
    this = recap.build(real, recap.this_month())
    line = window.stats_page.recap_line.text()
    check(f"the Stats card's line is the dialog's This month: {line!r}", line == recap.summary(this), line)
    check("and the dialog opens on This month", made and made[0].period == recap.this_month()
          and made[0].recap.minutes == this.minutes)
    dialog = made[0]
    dialog.show()
    settle(0.3)
    dialog.group.button(0).setFocus()
    window._drive_dialog(dialog, controller.RIGHT)
    settle(0.2)
    check("right on the chooser moves the period to Last month, and the card follows",
          dialog.group.checkedId() == 1 and dialog.recap.period == recap.last_month(), dialog.group.checkedId())
    window._drive_dialog(dialog, controller.LEFT)
    settle(0.2)
    check("left moves it back", dialog.group.checkedId() == 0 and dialog.recap.period == recap.this_month())
    window._drive_dialog(dialog, controller.DOWN)
    settle(0.1)
    check("down leaves the chooser for the buttons", dialog.focusWidget() is dialog.copy_button, dialog.focusWidget())
    window._drive_dialog(dialog, controller.BACK)
    settle(0.2)
    check("B closes it", not dialog.isVisible())
    check("the TV hint bar says A shares", any(words == "Share as image" for _key, words in ui_tv.HINT_SETS[ui_tv.STATS]))
except Exception as exc:
    unreached("8", exc)

print("\n=== 9. time, the layers, the real data ===")
try:
    art = ui_recap.Art(window.icons, window.by_key)
    busiest = max((recap.build(real, recap.Period(x.year, x.month)) for x in real_stats.months if x.recorded),
                  key=lambda r: r.minutes)
    times = []
    for _ in range(3):
        began = time.perf_counter()
        ui_recap.render(busiest, art)
        times.append((time.perf_counter() - began) * 1000)
    check(f"painting the busiest month ({busiest.period.label}): best of 3 {min(times):.0f} ms, under "
          f"{ui_rules.RECAP_RENDER_MAX_MS}", min(times) < ui_rules.RECAP_RENDER_MAX_MS, times)
    built = []
    for _ in range(5):
        began = time.perf_counter()
        reports_module.build(data_reports.Reports(window.overrides._conn))
        built.append((time.perf_counter() - began) * 1000)
    check(f"the reports (eleven since Phase 103): best of 5 {min(built):.1f} ms, under 50", min(built) < 50, built)
    check("the recap's queries are in data_access, read-only, each one named", set(recap_queries.QUERIES)
          and all(q.lstrip().upper().startswith(("WITH", "SELECT")) for q in recap_queries.QUERIES.values()))
    layers = subprocess.run([sys.executable, str(PROJECT / "tests" / "check_layers.py")], capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    check("no import points up a layer; sqlite3 only in data_access/; logic/recap.py imports no Qt",
          layers.returncode == 0 and "PySide6" not in (PROJECT / "logic" / "recap.py").read_text(encoding="utf-8"),
          layers.stdout[-300:])
except Exception as exc:
    unreached("9", exc)

print("\n=== 10. the year ===")
try:
    yearly = recap.build(source, recap.Period(2026), NOW)
    check("2026 on the planted library: 695 minutes, 8 sessions, 4 games -- the tool still nowhere",
          (yearly.minutes, yearly.sessions, yearly.games) == (695, 8, 4), (yearly.minutes, yearly.sessions, yearly.games))
    check("'Year so far', and the games counted as played at least once",
          yearly.title == "Year so far" and yearly.counts == ("8 sessions", "4 games played at least once"), yearly.counts)
    check("the top five, here the four there are, the most time first",
          [(g.name, g.minutes) for g in yearly.top] == [("Alpha", 225), ("Charlie", 200), ("Bravo", 150), ("Echo", 120)],
          [(g.name, g.minutes) for g in yearly.top])
    bars = {b.label: (b.minutes, b.recorded) for b in yearly.months}
    check("twelve months, as Stats draws them: before history and after today not recorded, faint",
          len(yearly.months) == 12 and bars["Jun"] == (0, False) and bars["Jul"] == (30, True)
          and bars["Sep"] == (590, True) and bars["Oct"] == (30, True) and bars["Nov"] == (0, False), bars)
    check("the busiest month named, with when in the day and the week beside it",
          yearly.busiest == f"Busiest: September, {humanize.playtime(590 * 60)}. Mostly in the evening, most time "
                            "on Saturdays", yearly.busiest)
    kinds = [f.kind for f in yearly.facts]
    check("its facts: the longest session, the year's new games, what was paid (when you played is by the months)",
          kinds == [recap.LONGEST, recap.NEW, recap.MONEY], kinds)
    new = next(f for f in yearly.facts if f.kind == recap.NEW)
    check("new this year: a name the library did not know, after its first day (Hotel One and foxtrot "
          "came on 3 and 2 August)", new.label == "New this year" and new.names == ("Echo", "foxtrot", "Hotel One", "Juliet"),
          new.names)
    money = next(f for f in yearly.facts if f.kind == recap.MONEY)
    check("the year's money: three purchases, two currencies, the wishlist's largest drop of the year",
          money.value == humanize.money(1999 + 2999, "EUR") + " + " + humanize.money(500, "RON")
          and money.detail.startswith("3 purchases") and yearly.raw["drop"]["name"] == "Wished Big"
          and money.short == "3 purchases", money)
    painted = ui_recap.paint(yearly, ui_recap.Art(None, {}, cache_dir=str(cache)))
    check("the year's card: the card's size, and its content clear of the footer",
          (painted.image.width(), painted.image.height()) == (ui_rules.RECAP_IMAGE_WIDTH, ui_rules.RECAP_IMAGE_HEIGHT)
          and painted.bottom < painted.footer_top, (painted.bottom, painted.footer_top))
    check("the month's card too", ui_recap.paint(card, ui_recap.Art(None, {}, cache_dir=str(cache))).bottom
          < ui_recap.paint(card, ui_recap.Art(None, {}, cache_dir=str(cache))).footer_top)
    roomy = []
    for period in [recap.Period(x.year, x.month) for x in real_stats.months if x.recorded] + [recap.this_year()]:
        made = ui_recap.paint(recap.build(real, period), art)
        roomy.append((period.label, round(made.bottom), round(made.footer_top)))
    check(f"on the user's library, every recorded month and this year: the content clear of the footer {roomy}",
          all(b < f for _, b, f in roomy), roomy)
    split = Made("split")
    one = split.game("c:\\games\\x-1", "Game X", installed=False)
    two = split.game("c:\\games\\x-2", "Game X")
    other = split.game("c:\\games\\y", "Game Y")
    split.session(one, "2026-09-02T20:00:00+03:00", 100)
    split.session(two, "2026-09-03T20:00:00+03:00", 50)
    split.session(other, "2026-09-04T20:00:00+03:00", 120)
    split_store = split.done()
    joined = recap.build(split_store.recap(), september, NOW)
    check("one game installed twice is one game on the card: its records' time together, the installed one's key",
          [(g.name, g.minutes) for g in joined.top] == [("Game X", 150), ("Game Y", 120)] and joined.games == 2
          and joined.top[0].identity_key == "c:\\games\\x-2", [(g.name, g.minutes, g.identity_key) for g in joined.top])
except Exception as exc:
    unreached("10", exc)

print("\n=== 11. the offer ===")
try:
    counted = lambda period: source.one("recap_totals", **period.bounds()).get("sessions") or 0  # noqa: E731
    november = datetime(2026, 11, 2, 9).astimezone()
    first = recap.offers(november, None, None, counted)
    check("on 2 November, October's recap is offered: it holds a session", first ==
          [(rules.RECAP_OFFERED_KEY, "2026-10", "Your October recap is ready: Stats, Share as image")], first)
    check("never twice", recap.offers(november, "2026-10", None, counted) == [])
    check("never for a month without sessions (November, on 2 December)",
          recap.offers(datetime(2026, 12, 2).astimezone(), None, None, counted) == [])
    check("the year's not before 15 December", not [o for o in recap.offers(datetime(2026, 12, 14).astimezone(), "2026-11",
                                                                           None, counted) if o[0] == rules.RECAP_YEAR_OFFERED_KEY])
    on_day = recap.offers(datetime(2026, 12, 15).astimezone(), "2026-11", None, counted)
    check("from 15 December, once", on_day == [(rules.RECAP_YEAR_OFFERED_KEY, "2026", "Your 2026 recap is ready: Stats, "
                                                "Share as image")] and recap.offers(
        datetime(2026, 12, 20).astimezone(), "2026-11", "2026", counted) == [], on_day)
    check("and in January for the year just ended, if December's offer never came",
          (rules.RECAP_YEAR_OFFERED_KEY, "2026", "Your 2026 recap is ready: Stats, Share as image")
          in recap.offers(datetime(2027, 1, 10).astimezone(), "2026-12", None, counted))
    check("a quiet sandbox copy starts with the offers already shown: no suite's window gains a toast",
          window.config.get(rules.RECAP_OFFERED_KEY) == recap.last_month().key)
    said, balloons = [], []
    real_queue = window.queue_status
    window.queue_status = lambda text, ms: said.append(text)
    try:
        window.config[rules.RECAP_OFFERED_KEY] = "2000-01"
        window.first_run = True
        window.offer_recap()
        check("never in a first run", said == [] and window.config[rules.RECAP_OFFERED_KEY] == "2000-01")
        window.first_run = False
        window.offer_recap()
        saved = json.loads((Path(box.folder) / "config.json").read_text(encoding="utf-8"))
        check(f"a toast once the month has ended: {said}", said == [f"Your {recap.last_month().name} recap is ready: "
                                                                    "Stats, Share as image"]
              and saved.get(rules.RECAP_OFFERED_KEY) == recap.last_month().key, (said, saved.get(rules.RECAP_OFFERED_KEY)))
        window.offer_recap()
        check("and not again at the next start or tick", len(said) == 1, said)

        class Tray:
            def say(self, text):
                balloons.append(text)

        real_tray, real_in_tray = window.tray, window._in_tray
        window.tray, window._in_tray = Tray(), True
        try:
            window.config[rules.RECAP_OFFERED_KEY] = "2000-01"
            window.offer_recap()
        finally:
            window.tray, window._in_tray = real_tray, real_in_tray
        check("with the window in the tray, the tray's balloon says it instead", balloons and len(said) == 1, balloons)
    finally:
        window.queue_status = real_queue
except Exception as exc:
    unreached("11", exc)

print("\n=== 12. the documents ===")
try:
    def doc(rel):
        return (PROJECT / rel).read_text(encoding="utf-8")
    claude = doc("CLAUDE.md")
    check("CLAUDE.md has the phase and the three modules", "| 96 |" in claude and "ui_recap.py" in claude
          and claude.count("recap.py") >= 3, claude.count("recap.py"))
    check("ARHITECTURA has the recap in its maps and the one rule in a sentence",
          "ui_recap.py" in doc("docs/ARHITECTURA.md") and "logic/recap.py" in doc("docs/ARHITECTURA.md")
          and "aceeași regulă" in doc("docs/ARHITECTURA.md"))
    check("ANALIZA has its Recapitularea", "## Recapitularea" in doc("docs/ANALIZA.md"))
    readme = doc("docs/CITESTE-MA.md")
    check("CITESTE-MA tells the friends where the button is and what the image never holds, on its one page",
          "Share as image" in readme and "căi" in readme and len(readme.splitlines()) <= 110, len(readme.splitlines()))
    explained = doc("docs/explicatii/faza-96.md")
    check("docs/explicatii/faza-96.md, the same shape as the others",
          all(w in explained for w in ("## Ce s-a construit", "## De ce contează", "## Cum funcționează",
                                       "## Cinci cuvinte", "## Trei întrebări", "## Ce nu poate face")))
    check("the build log has the phase's notes", "## Phase 96 notes" in sources.build_log())
    check("nothing in this suite reached the network", attempts == [], attempts)
except Exception as exc:
    unreached("12", exc)

for store in ("planted", "quiet_store", "split_store"):
    if store in globals():
        globals()[store].close()
if "window" in globals():
    window._shut_down = True
    window.overrides.close()
changed = box.finish()
check("config.json, the library database and the Run key's value are unchanged", not changed, changed)
print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
