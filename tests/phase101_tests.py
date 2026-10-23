"""Phase 101: schema version 8, planned for three phases at once; then price alerts on the wishlist.

  1. schema version 8 on a copy of the real library: the launcher's own door upgrades it, a snapshot of
     version 7 first; every old row as it was, in the columns it had; the two new columns NULL and the
     three new tables empty and STRICT; a fresh database the same schema; the script additions only, and
     undone by test_sandbox.undo_upgrades back to version 7's schema; the constraints refuse what they
     should; a rated game's sessions survive the store's delete-and-put-back (the rating's key checked at
     the commit), and a rated session gone at the commit is refused;
  2. the documents of the schema: BAZA_DE_DATE's version 8 whole, with what the later phases fill;
  3. the rules, on made-up series: 'lowest' strictly lower, from three prices, in its currency, once a drop, a
     further drop alerting, only the price just arrived judged, a hidden game not; 'target' crossing under it,
     at it, staying under it silent, a further drop, another currency nothing; the message for one game, both
     kinds, several games; the row's words; the Alerts list's 30 days and one line a drop;
  4. a target on a wished game in the window: the menu's entries, the dialog from the lowest seen in the
     game's currency, worked by the pad (right a step, B closes, nothing kept), Set alert, the row's and the
     status bar's words, a new target replacing the old, Remove alert, nothing in config.json;
  5. an alert end to end on a copy of the real library, a lower price planted: the log and the toast, silence
     on the same price, the page's "at its lowest" line (Phase 87's notice retired); in the tray the balloon,
     its click opening the Wishlist's Alerts; the real tray's click once; a hidden game not judged; report 6's
     sentence absent and present; the nine reports under 50 ms; a mark's date written;
  6. the documents and the layers; suites 22-25 refusing the real data.

On a throwaway copy of the data; the network is blocked; the user's config and library are photographed
at the start and compared at the end.
"""
import logging
import re
import sqlite3
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import sources  # the build log's notes (Phase 91)
import test_sandbox

box = test_sandbox.start({"allow_network": False, "startup_scan": False, "tv_mode": False}, migrate=False)
DATABASE = box.path("library.db")
# The upgrade is proven on the user's library as version 7 had it: after his next start the real one is at
# 8, so the copy is taken back first, as suites 86 and 93 do.
_raw = sqlite3.connect(DATABASE, isolation_level=None)
UNDONE = test_sandbox.undo_upgrades(_raw, 7) if _raw.execute("PRAGMA user_version").fetchone()[0] >= 8 else []
_raw.close()
attempts: list[str] = []


def no_network(request, *args, **kwargs):
    attempts.append(getattr(request, "full_url", str(request)))
    raise OSError("the network is blocked in this suite")


urllib.request.urlopen = no_network


class Lines(logging.Handler):
    def __init__(self):
        super().__init__(logging.INFO)
        self.lines: list[str] = []

    def emit(self, record):
        self.lines.append(record.getMessage())


lines = Lines()
logging.getLogger().addHandler(lines)
logging.getLogger().setLevel(logging.INFO)

from data_access import library_db
from logic import migration
from shared import rules

passed = failed = 0
NEW_TABLES = ("price_target", "price_alert", "rating")
NEW_COLUMNS = ("status_changed_at", "nudged_at")


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"   PASS  {name}")
    else:
        failed += 1
        print(f"   FAIL  {name}   {detail}")


def unreached(section, exc):
    global failed
    failed += 1
    print(f"   FAIL  section {section} runs to its end on this code   {exc!r}")


def git(*args) -> str:
    return subprocess.run(["git", *args], cwd=PROJECT, capture_output=True, text=True, encoding="utf-8").stdout


def schema_of(conn) -> list[tuple]:
    """sqlite_master as normalised SQL: comments and runs of white space dropped (suite 73's measure)."""
    return [(kind, name, re.sub(r"\s+", " ", re.sub(r"--[^\n]*", "", sql)).strip())
            for kind, name, sql in conn.execute("SELECT type, name, sql FROM sqlite_master WHERE sql IS NOT NULL "
                                                "ORDER BY type, name")]


def count(conn, table: str) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def refused(conn, sql: str, values=()) -> bool:
    try:
        conn.execute(sql, values)
    except sqlite3.IntegrityError:
        return True
    return False


print("=== 1. schema version 8 on a copy of the real library ===")
try:
    raw = sqlite3.connect(DATABASE, isolation_level=None)
    check("the copy starts at version 7" + (" (taken back from 8, as the user's own start had left it)" if UNDONE else ""),
          library_db.schema_version(raw) == 7, library_db.schema_version(raw))
    tables = [r[0] for r in raw.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name != 'meta' "
                                        "AND name NOT LIKE 'sqlite_%'")]
    before_rows = {t: test_sandbox.rows_in_old_columns(raw, t) for t in tables}
    before_meta = raw.execute("SELECT id, created_at, migrated_from, migrated_at FROM meta").fetchall()
    before_schema = schema_of(raw)
    raw.close()
    backups = box.folder / "backups"
    snapshots_before = {p.name for p in backups.glob("*")} if backups.is_dir() else set()
    lines.lines.clear()
    store = migration.open_library()
    check("the launcher's own door opens it at version 8", store.version == library_db.SCHEMA_VERSION == 8, store.version)
    store.close()
    held = []
    for folder in backups.glob("*") if backups.is_dir() else []:
        if folder.name not in snapshots_before and (folder / "library.db").is_file():
            snap = sqlite3.connect(f"file:{(folder / 'library.db').as_posix()}?mode=ro", uri=True)
            held.append(library_db.schema_version(snap))
            snap.close()
    check("a snapshot first, holding the library at version 7", 7 in held, held)
    check("the log says so", any("upgraded from version 7 to 8" in line for line in lines.lines)
          and any("is at version 8 now (snapshot" in line for line in lines.lines))
    raw = sqlite3.connect(DATABASE, isolation_level=None)
    raw.execute("PRAGMA foreign_keys = ON")
    # The Steam projection runs after an upgrade and may bring a record the cache has (suite 76's lesson).
    projected = {"steam_app", "genre", "steam_app_genre", "category", "steam_app_category", "company",
                 "steam_app_company", "price_snapshot"}
    kept = [t for t in tables if t in projected or test_sandbox.rows_in_old_columns(raw, t) == before_rows[t]]
    check(f"every row of the user's own tables as it was, in the columns it had ({len(tables)} tables)",
          len(kept) == len(tables), sorted(set(tables) - set(kept)))
    check("the price series and the Steam apps kept every row they had",
          set(before_rows["price_snapshot"]) <= set(test_sandbox.rows_in_old_columns(raw, "price_snapshot"))
          and len(before_rows["steam_app"]) <= count(raw, "steam_app"))
    check("meta: only the version moved",
          raw.execute("SELECT id, created_at, migrated_from, migrated_at FROM meta").fetchall() == before_meta
          and raw.execute("SELECT schema_version FROM meta").fetchone()[0] == 8
          and raw.execute("PRAGMA user_version").fetchone()[0] == 8)
    games = count(raw, "game")
    check(f"the two new columns NULL for every one of the {games} games",
          raw.execute("SELECT COUNT(*) FROM game WHERE status_changed_at IS NOT NULL OR nudged_at IS NOT NULL")
          .fetchone()[0] == 0 and [r[1] for r in raw.execute("PRAGMA table_info(game)")][-2:] == list(NEW_COLUMNS))
    check("the three new tables STRICT and empty",
          all(raw.execute("SELECT strict FROM pragma_table_list WHERE name = ?", (t,)).fetchone()[0] == 1
              and count(raw, t) == 0 for t in NEW_TABLES))
    later = {("table", "game")}  # its text is both added and removed: two columns, an addition all the same
    added = [row[:2] for row in schema_of(raw) if row not in before_schema and row[:2] not in later]
    gone = [row[:2] for row in before_schema if row not in schema_of(raw) and row[:2] not in later]
    check("additive only: the three tables added, nothing removed or changed", not gone
          and sorted(added) == sorted(("table", t) for t in NEW_TABLES), (added, gone))
    fresh = sqlite3.connect(":memory:", autocommit=True)
    library_db.create(fresh)
    check("a fresh database and the upgraded copy have the same schema", schema_of(fresh) == schema_of(raw),
          set(schema_of(fresh)) ^ set(schema_of(raw)))
    check("no foreign key broken, the file whole", raw.execute("PRAGMA foreign_key_check").fetchall() == []
          and raw.execute("PRAGMA integrity_check").fetchone()[0] == "ok")

    script = (PROJECT / "data_access" / "upgrades" / "008_alerts_ratings_marks.sql").read_text(encoding="utf-8")
    code = re.sub(r"--[^\n]*", "", script)
    check("008 only adds: three CREATE TABLE and two ADD COLUMN, no DROP, no other ALTER, no UPDATE or DELETE",
          len(re.findall(r"\bCREATE TABLE\b", code)) == 3 and len(re.findall(r"\bADD COLUMN\b", code)) == 2
          and not re.search(r"\b(DROP|UPDATE|DELETE|INSERT)\b", code)
          and len(re.findall(r"\bALTER\b", code)) == 2)

    # The constraints refuse what they should.
    appid = raw.execute("SELECT appid FROM steam_app LIMIT 1").fetchone()[0]
    observed = raw.execute("SELECT appid, observed_at FROM price_snapshot LIMIT 1").fetchone()
    utc, local = "2026-10-20T00:00:00+00:00", "2026-10-20T03:00:00+03:00"
    raw.execute("BEGIN")
    checks = {
        "a target of 0": refused(raw, "INSERT INTO price_target VALUES (?, 0, 'EUR', ?)", (appid, utc)),
        "a currency in small letters": refused(raw, "INSERT INTO price_target VALUES (?, 100, 'eur', ?)", (appid, utc)),
        "a target for an app not in steam_app": refused(raw, "INSERT INTO price_target VALUES (-5, 100, 'EUR', ?)", (utc,)),
        "a moment that is not UTC": refused(raw, "INSERT INTO price_target VALUES (?, 100, 'EUR', ?)", (appid, local)),
        "an alert naming no price of the series": refused(
            raw, "INSERT INTO price_alert VALUES (?, ?, 'lowest', 100, 'EUR', ?)", (appid, "1999-01-01T00:00:00+00:00", utc)),
        "an alert of another kind": refused(
            raw, "INSERT INTO price_alert VALUES (?, ?, 'cheap', 100, 'EUR', ?)", (observed[0], observed[1], utc)),
        "an alert sent before its price was seen": refused(
            raw, "INSERT INTO price_alert VALUES (?, ?, 'lowest', 100, 'EUR', '2000-01-01T00:00:00+00:00')", tuple(observed)),
        "six stars": refused(raw, "INSERT INTO rating VALUES (1, ?, 6, ?)", (local, local)),
        "a mark's date in another shape": refused(raw, "UPDATE game SET status_changed_at = '2026-10-20 03:00'"),
    }
    raw.execute("ROLLBACK")
    check("the constraints refuse: " + ", ".join(checks), all(checks.values()), [k for k, v in checks.items() if not v])

    # A rating names a session by its game and start; the store rewrites a game's sessions by deleting and putting
    # them back in one transaction, and the key, checked at the commit, holds through it.
    game_id, started = raw.execute("SELECT game_id, started_at FROM session ORDER BY started_at DESC LIMIT 1").fetchone()
    raw.execute("BEGIN")
    raw.execute("INSERT INTO rating VALUES (?, ?, 4, ?)", (game_id, started, local))
    raw.execute("COMMIT")
    raw.close()
    store = test_sandbox.library()
    key = store._conn.execute("SELECT identity_key FROM game WHERE id = ?", (game_id,)).fetchone()[0]
    record = store.get(key)
    store.update(key, notes=(record.get("notes") or "") + " ")  # a save of the whole record, sessions rewritten
    survived = store._conn.execute("SELECT stars FROM rating WHERE game_id = ? AND started_at = ?",
                                   (game_id, started)).fetchone()
    store.update(key, notes=record.get("notes"))
    store.close()
    check("a rated game saved through the store: its sessions rewritten, the rating kept", survived == (4,), survived)
    raw = sqlite3.connect(DATABASE, isolation_level=None)
    raw.execute("PRAGMA foreign_keys = ON")
    raw.execute("BEGIN")
    raw.execute("DELETE FROM session WHERE game_id = ? AND started_at = ?", (game_id, started))
    try:
        raw.execute("COMMIT")
        gone_refused = False
    except sqlite3.IntegrityError:
        raw.execute("ROLLBACK")
        gone_refused = True
    check("a rated session gone at the commit is refused (Phase 102 takes the rating with it)", gone_refused)
    raw.execute("DELETE FROM rating")
    check("the copy's rating taken away again", count(raw, "rating") == 0)

    # Undone: back to version 7's schema exactly, as the upgrade script read before Phase 101 left it.
    raw.execute("BEGIN")
    undone = test_sandbox.undo_upgrades(raw, 7)
    raw.execute("COMMIT")
    v7 = sqlite3.connect(":memory:", autocommit=True)
    v7.executescript(git("show", "before-phase-101:data_access/schema.sql"))
    check("undo_upgrades takes the three tables and the two columns off: version 7's schema again",
          sorted(undone) == sorted([("table", t) for t in NEW_TABLES] + [("column", f"game.{c}") for c in NEW_COLUMNS])
          and schema_of(raw) == schema_of(v7) and library_db.schema_version(raw) == 7, undone)
    raw.close()
except Exception as exc:
    unreached("1", exc)

print("\n=== 2. the documents of the schema ===")
try:
    def doc(name):
        return (PROJECT / name).read_text(encoding="utf-8").replace("\r\n", "\n")

    baza = doc("docs/BAZA_DE_DATE.md")
    check("BAZA_DE_DATE: version 8 whole -- its section, the two alert tables, rating, the game's two dates",
          "### Versiunea 8 (faza 101)" in baza and "### `price_target` și `price_alert`" in baza
          and "### `rating`" in baza and "**Datele semnului (versiunea 8, faza 101).**" in baza
          and "**Azi schema are versiunea 8**" in baza)
    check("and says what the later phases fill: rating Phase 102's, nudged_at Phase 103's",
          "o scrie faza 102" in baza and "`nudged_at` faza 103" in baza)
    schema = doc("data_access/schema.sql")
    check("schema.sql says version 8 at its top and holds the three tables",
          schema.startswith("-- Game Launcher: the library database, schema version 8")
          and all(f"CREATE TABLE {t} (" in schema for t in NEW_TABLES))
except Exception as exc:
    unreached("2", exc)

print("\n=== 3. the rules, on made-up series ===")
try:
    from logic import alerts

    def obs(*prices, currency="EUR", start=10):
        return [(f"2026-10-{start + i:02d}T12:00:00+00:00", cents, currency) for i, cents in enumerate(prices)]

    def judge(prices, target=None, logged=(), wished=None, appid=7):
        series = {appid: prices}
        fresh = [(appid, prices[-1][0])]
        return alerts.decide(fresh, wished if wished is not None else {appid: "Game"}, series,
                             {appid: target} if target else {}, set(logged))

    kinds = lambda found: [a.kind for a in found]  # noqa: E731
    check("'lowest': strictly below every earlier price, with three prices, alerts",
          kinds(judge(obs(3000, 3000, 2500))) == ["lowest"])
    check("an equal price is silence", judge(obs(3000, 2500, 2500)) == [])
    check("a series of two is no reference yet: silence", judge(obs(3000, 2500)) == [])
    check("a price of another currency is no earlier price", judge(obs(3000, 3000) + obs(2500, currency="PLN", start=20)) == [])
    first = judge(obs(3000, 3000, 2500))
    check("once per drop: the same price and kind already in the log is silence",
          judge(obs(3000, 3000, 2500), logged={(7, first[0].observed_at, "lowest")}) == [])
    check("a further drop alerts again", kinds(judge(obs(3000, 3000, 2500, 2000))) == ["lowest"])
    risen = obs(3000, 3000, 2500, 2600)  # the third was a new lowest; the fourth, just arrived, is not
    check("only the price that has just arrived is judged: an earlier drop never alerts later",
          alerts.decide([(7, risen[3][0])], {7: "Game"}, {7: risen}, {}, set()) == []
          and kinds(alerts.decide([(7, risen[2][0])], {7: "Game"}, {7: risen}, {}, set())) == ["lowest"])
    check("a game hidden from the page, or no longer on a list, is not judged", judge(obs(3000, 3000, 2500), wished={}) == [])
    t = {"cents": 2000, "currency": "EUR"}
    check("'target': a price crossing under the target alerts, even on a series of one",
          kinds(judge(obs(1900), target=t)) == ["target"] and kinds(judge(obs(2500, 1900), target=t)) == ["target"])
    check("at the target counts", kinds(judge(obs(2500, 2000), target=t)) == ["target"])
    check("staying under it is silence", judge(obs(2500, 1900, 1900), target=t) == [])
    check("a further drop under it alerts again (and is a new lowest besides)",
          kinds(judge(obs(2500, 1900, 1800), target=t)) == ["target", "lowest"])
    check("a target in another currency alerts nothing", judge(obs(2500, 1900), target={"cents": 2000, "currency": "PLN"}) == [])
    both = judge(obs(3000, 3000, 1900), target=t)
    check("a drop to a new lowest under the target: both kinds, the target first", kinds(both) == ["target", "lowest"])

    a = alerts.Alert(1, "Hades II", "x", "target", 1999, "EUR", 2000)
    b = alerts.Alert(2, "Silksong", "x", "lowest", 1599, "EUR")
    c = alerts.Alert(3, "Outbound", "x", "lowest", 999, "EUR")
    from shared import humanize
    eur = lambda cents: humanize.money(cents, "EUR")  # noqa: E731 -- "19,99 €", a no-break space before the sign
    check("one game: its name, its price and why",
          alerts.message([a]) == f"Hades II dropped to {eur(1999)} — under your {eur(2000)} target", alerts.message([a]))
    check("one game, both kinds: named once", alerts.message([a, alerts.Alert(1, "Hades II", "x", "lowest", 1999, "EUR")])
          == f"Hades II dropped to {eur(1999)} — under your {eur(2000)} target and the lowest seen")
    check("three games: one message, two named and the rest counted",
          alerts.message([a, b, c]) == f"3 wishlist games dropped: Hades II at {eur(1999)}, Silksong at {eur(1599)}, and 1 more",
          alerts.message([a, b, c]))
    check("the target's words on a row", alerts.target_line(t, obs(2500), "priced", "EUR") == f"Alert under {eur(2000)}"
          and alerts.target_line(t, obs(2500, 1900, 1950), "priced", "EUR").startswith("Below your target since 11")
          and alerts.target_line({"cents": 2000, "currency": "PLN"}, obs(2500), "priced", "EUR")
          == "Your target is in PLN; the price is now in EUR" and alerts.target_line(None, obs(2500), "priced", "EUR") == "")
    now = datetime(2026, 11, 20, 12, tzinfo=timezone.utc)
    sent = [{"appid": 1, "name": "A", "observed_at": "2026-10-19T12:00:00+00:00", "kind": "lowest", "final_cents": 1,
             "currency": "EUR", "sent_at": "2026-10-19T12:00:05+00:00"},
            {"appid": 2, "name": "B", "observed_at": "2026-11-18T12:00:00+00:00", "kind": "target", "final_cents": 1,
             "currency": "EUR", "sent_at": "2026-11-18T12:00:05+00:00"},
            {"appid": 3, "name": "C", "observed_at": "2026-11-19T12:00:00+00:00", "kind": "lowest", "final_cents": 1,
             "currency": "EUR", "sent_at": "2026-11-19T12:00:05+00:00"}]
    check(f"the Alerts list: the last {rules.ALERT_KEEP_DAYS} days only, newest first",
          [r["appid"] for r in alerts.recent(sent, now)] == [3, 2])
    twice = sent + [dict(sent[2], kind="target")]
    lines = [alerts.alert_line(d) for d in alerts.drops(twice, now)]
    check("one line a drop: a price both under the target and the lowest seen is one line with both",
          lines == [f"19 Nov: {eur(1)} — under your target and the lowest seen", f"18 Nov: {eur(1)} — under your target"],
          lines)
except Exception as exc:
    unreached("3", exc)

print("\n=== 4. a target on a wished game, in the window ===")
try:
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication, QDialog, QMenu

    app = QApplication.instance() or QApplication([])
    from adapters import controller
    from logic import alerts, wishlist
    from presentation import ui_actions, ui_alert, ui_tray, ui_window
    from shared import humanize

    def settle(seconds):
        loop = QEventLoop()
        QTimer.singleShot(int(seconds * 1000), loop.quit)
        loop.exec()

    window = ui_window.MainWindow()
    window.resize(1440, 900)
    window.show()
    settle(1.5)
    window._stop_watch()
    # After the start's own writes: a start on a new version writes version_seen (Phase 99), as on 1.2.9's day.
    config_before = (box.folder / "config.json").read_bytes()
    store = window.overrides
    check("the window's library keeps targets and alerts (version 8)", store.keeps_alerts and store.version == 8)
    model = window.wishlist_model()
    # A game whose price leaves room under it for a target and two drops (Police Shootout is 1,03 €).
    priced = [r for r in model.rows if r.cents is not None and r.cents >= 1000 and len(r.series) >= 2]
    check(f"the copy's wishlist: {len(model.rows)} games, {len(priced)} priced with a series", bool(priced))
    game = priced[0]
    window.show_wishlist()
    settle(0.5)

    shown_menus: list[list[str]] = []

    def read_menu():
        """The game's menu opened as the pad's X opens it; its entries read off the screen, then closed."""
        def look():
            popup = QApplication.activePopupWidget()
            if popup is not None:
                shown_menus.append([x.text() for x in popup.actions() if x.text()])
                popup.close()
        QTimer.singleShot(400, look)
        QTimer.singleShot(3000, lambda: QApplication.activePopupWidget() and QApplication.activePopupWidget().close())
        window._wishlist_menu(game.appid, window.mapToGlobal(window.rect().center()))

    read_menu()
    check("its menu offers Alert me under..., and no Remove alert before one is set",
          shown_menus and "Alert me under..." in shown_menus[-1] and "Remove alert" not in shown_menus[-1], shown_menus)

    # The dialog, worked by the pad: it opens on the lowest seen; right raises it a step; B closes, nothing kept.
    seen = {}

    def work_dialog():
        dialog = QApplication.activeModalWidget()
        seen["dialog"] = dialog
        # A watchdog: if B never reaches it, the dialog is closed here, and the check below says so.
        QTimer.singleShot(3000, lambda: (seen.__setitem__("watchdog", True), dialog.reject())
                          if dialog is not None and dialog.isVisible() else None)
        seen["start"] = dialog.cents() if isinstance(dialog, ui_alert.TargetDialog) else None
        seen["title"] = dialog.windowTitle() if dialog else None
        window._on_pad_action(controller.RIGHT)
        QTimer.singleShot(200, step_two)

    def step_two():
        dialog = seen["dialog"]
        seen["after_right"] = dialog.cents() if isinstance(dialog, ui_alert.TargetDialog) else None
        window._on_pad_action(controller.BACK)

    QTimer.singleShot(600, work_dialog)
    window.set_price_alert(game.appid)
    settle(0.3)
    start = game.lowest_cents or game.cents
    check("Alert me under... opens on the lowest price seen, in the game's own currency",
          seen.get("title", "").startswith(ui_alert.TITLE) and seen.get("start") == start
          and seen["dialog"].currency == game.currency, seen)
    check("the pad: right raises the amount a step; B closes it, and nothing is kept",
          seen.get("after_right") == start + rules.ALERT_TARGET_STEP_CENTS and not seen.get("watchdog")
          and store.reports().rows("price_targets") == [], seen)

    real_dialog_exec = ui_alert.TargetDialog.exec

    def accept_at(cents):
        def run(dialog):
            dialog.amount.setValue(cents / 100)
            return int(QDialog.DialogCode.Accepted)
        return run

    under = start - 500
    ui_alert.TargetDialog.exec = accept_at(under)
    try:
        window.set_price_alert(game.appid)
    finally:
        ui_alert.TargetDialog.exec = real_dialog_exec
    targets = [dict(r) for r in store.reports().rows("price_targets")]
    row = window.wishlist_page.row_for(game.appid)
    check("Set alert keeps one target, in cents and the game's currency",
          [(t["appid"], t["cents"], t["currency"]) for t in targets] == [(game.appid, under, game.currency)], targets)
    check("the row says it where the count of prices was: 'Alert under ...'",
          row.target == f"Alert under {humanize.money(under, game.currency)}", row.target)
    check("and the status bar, in words", window.statusBar().currentMessage()
          == f"Alert set: {game.name} under {humanize.money(under, game.currency)}", window.statusBar().currentMessage())
    ui_alert.TargetDialog.exec = accept_at(start)
    try:
        window.set_price_alert(game.appid)
    finally:
        ui_alert.TargetDialog.exec = real_dialog_exec
    row = window.wishlist_page.row_for(game.appid)
    check("a new target replaces the old: one row; met by today's price, 'Below your target since ...'",
          len(store.reports().rows("price_targets")) == 1 and row.target.startswith("Below your target since "), row.target)
    shown_menus.clear()
    read_menu()
    check("with a target, the menu says Change alert... and Remove alert",
          shown_menus and {"Change alert...", "Remove alert"} <= set(shown_menus[-1]), shown_menus)
    window.remove_price_alert(game.appid)
    row = window.wishlist_page.row_for(game.appid)
    check("Remove alert takes it away: no target, the row's words back to the count of prices",
          store.reports().rows("price_targets") == [] and row.target == "", row.target)
    check("nothing about a target in config.json", (box.folder / "config.json").read_bytes() == config_before)
except Exception as exc:
    unreached("4", exc)

print("\n=== 5. an alert, end to end on the copy: a lower price planted ===")
try:
    from datetime import datetime, timedelta, timezone

    def plant(appid, cents, currency, minutes=0):
        at = (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat(timespec="seconds")
        landed, refused = store.add_observations([{"appid": appid, "observed_at": at, "kind": "priced",
                                                   "currency": currency, "initial_cents": cents + 1000,
                                                   "final_cents": cents, "discount_percent": 10}])
        return (appid, at)

    posted: list[str] = []
    real_queue = window.queue_status
    window.queue_status = lambda text, ms: posted.append(text)
    low = min(c for c in game.series) - 100
    first = plant(game.appid, low, game.currency)
    window._price_alerts([first])
    logged = [dict(r) for r in store.reports().rows("price_alerts")]
    check("a new lowest price of a wished game: one alert in the log, 'lowest'",
          [(r["appid"], r["observed_at"], r["kind"], r["final_cents"]) for r in logged]
          == [(game.appid, first[1], "lowest", low)], logged)
    check("and one message, through the window's toast (the status queue) while it is shown",
          posted == [f"{game.name} dropped to {humanize.money(low, game.currency)} — the lowest seen"], posted)
    window._price_alerts([first])
    check("the same price judged again: silence", len(posted) == 1 and len(store.reports().rows("price_alerts")) == 1)
    model = window.wishlist_model()
    check("the page's line counts it: '1 at its lowest price seen' (Phase 87's notice, retired, is a line now)",
          model.lowest_now >= 1 and not hasattr(wishlist, "notice") and not hasattr(window, "_wishlist_notice"))

    # In the tray: the balloon, and its click opening the Wishlist tab on the Alerts.
    said: list = []
    window._in_tray, real_tray = True, window.tray
    window.tray = type("Tray", (), {"say": lambda self, text, clicked=None: said.append((text, clicked))})()
    second = plant(game.appid, low - 100, game.currency, minutes=1)
    try:
        window._price_alerts([second])
    finally:
        window._in_tray, window.tray = False, real_tray
    check("a further drop while the window is in the tray: the balloon, not the toast",
          len(said) == 1 and len(posted) == 1 and said[0][0].startswith(f"{game.name} dropped to "), (said, posted))
    window.show_stats()
    settle(0.3)
    said[0][1]()
    settle(0.5)
    page = window.wishlist_page
    check("its click: the window on the Wishlist tab, its Alerts showing, the newest first",
          window.stack.currentWidget() is page and page.choice == wishlist.ALERTS
          and [r.appid for r in page.model.alerts][:2] == [game.appid, game.appid]
          and page.model.alerts[0].alert.endswith("the lowest seen"), (page.choice, [r.alert for r in page.model.alerts]))
    check("the chip remembered stays the user's own", window.config.get(rules.WISHLIST_FILTER_SETTING) != wishlist.ALERTS)
    names = [page.choice]
    for _ in range(3):
        page.toggle_choice()
        names.append(page.choice)
    check("Y walks the three chips: Alerts, All, On sale, Alerts", names == [wishlist.ALERTS, wishlist.ALL, wishlist.ON_SALE,
                                                                            wishlist.ALERTS], names)
    page.choose(wishlist.ALL)

    # The real tray icon: a balloon's click does what that balloon asked, once; a later balloon asks for nothing.
    clicks: list[str] = []
    tray = ui_tray.Tray(window)
    tray.say("an alert", clicked=lambda: clicks.append("opened"))
    tray.icon.messageClicked.emit()
    tray.icon.messageClicked.emit()
    tray.say("the recap is ready")
    tray.icon.messageClicked.emit()
    tray.remove()
    check("the tray's balloon: its click runs what it asked for, once; another balloon's click, nothing",
          clicks == ["opened"], clicks)

    hidden_game = next((r for r in priced[1:] if r.currency == game.currency), None)
    if hidden_game is not None:
        hidden_key = plant(hidden_game.appid, min(hidden_game.series) - 100, hidden_game.currency)
        check("a game hidden from the page is not judged",
              alerts.land(store, [hidden_key], {hidden_game.appid}) == [])
    window.queue_status = real_queue

    # Report 6, and the nine reports' time.
    from logic import reports as reports_module
    money = next(r for r in reports_module.build(store.reports()) if "money" in r.queries[0])
    wish_note = next(p.note for p in money.parts if p.heading == "Your wishlist at today's prices")
    check("report 6 says nothing of targets when none is set", "with a target" not in wish_note, wish_note)
    store.set_price_target(game.appid, low - 100, game.currency)
    money = next(r for r in reports_module.build(store.reports()) if "money" in r.queries[0])
    wish_note = next(p.note for p in money.parts if p.heading == "Your wishlist at today's prices")
    check("and, with one: 'You watch 1 wished game with a target; 1 is below it today.'",
          wish_note.endswith("You watch 1 wished game with a target; 1 is below it today."), wish_note)
    import time as _time
    timings = []
    for _ in range(5):
        began = _time.perf_counter()
        reports_module.build(store.reports())
        timings.append((_time.perf_counter() - began) * 1000)
    check(f"the eleven reports (since Phase 103) still under 50 ms ({min(timings):.1f} ms at best of five)", min(timings) < 50, timings)
    store.remove_price_target(game.appid)

    # The mark's date: set from now on, with the mark.
    view = next(v for v in window.views if not v.status)
    key = view.key
    import copy as _copy
    kept_record = _copy.deepcopy(store.get(key))
    try:
        ui_actions.set_status(window, view, "playing")
        stamped = store.get(key).get(rules.STATUS_CHANGED_KEY)
        check("a mark set writes when (status_changed_at, local time with its offset)",
              bool(re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d", stamped or "")), stamped)
    finally:
        store.update(key, **{rules.STATUS_KEY: kept_record.get(rules.STATUS_KEY),  # the mark as it was
                             rules.STATUS_CHANGED_KEY: kept_record.get(rules.STATUS_CHANGED_KEY)})
except Exception as exc:
    unreached("5", exc)

if "window" in globals():
    window._stop_watch()
    window._shut_down = True
    window.overrides.close()
    settle(0.3)

print("\n=== 6. the documents, the layers, the guard ===")
try:
    claude = doc("CLAUDE.md")
    row = next(line for line in claude.splitlines() if line.startswith("| 101 |"))
    # Its two steps' row condensed to one in Phase 103 (CLAUDE.md's room); the whole story is in ISTORIC.
    check("CLAUDE.md: row 101 has both steps done, the layout the two new modules",
          (("**1 of 2 done**" in row and "**2 of 2 done**" in row) or ("**done**" in row and "logic/alerts.py" in row))
          and "  alerts.py  " in claude and "  ui_alert.py  " in claude and "008_alerts_ratings_marks.sql" in claude)
    analysis = doc("docs/ANALIZA.md")
    from data_access import reports as queries
    check("ANALIZA quotes the alerts' two queries and report 6's, exactly as the code has them",
          all(f"-- {n}\n{queries.QUERIES[n]}\n" in analysis for n in ("price_targets", "price_alerts", "money_wishlist"))
          and "punct de referință" in analysis.casefold() and "**Alertele de preț (faza 101).**" in analysis)
    readme = doc("docs/CITESTE-MA.md")
    check("CITESTE-MA: the alert in the friends' words, still on its one page",
          "**Alert me under...**" in readme and len(readme.splitlines()) <= 110, len(readme.splitlines()))
    page = doc("docs/explicatii/faza-101.md")
    sections = ("## Ce s-a construit", "## De ce contează pentru lucrare", "## Cum funcționează",
                "## Cinci cuvinte", "## Trei întrebări ale comisiei", "## Ce nu poate face")
    words = ("reference point, anchoring", "price series", "threshold alert", "idempotent notification", "schema migration")
    check("docs/explicatii/faza-101.md: the six parts, the five words, no file names or code",
          all(h in page for h in sections) and all(f"(*{w}*)" in page for w in words) and ".py" not in page
          and "`" not in page and "faza 101" in doc("docs/explicatii/CITESTE-MA.md"))
    log = sources.build_log()
    check("the build log has Phase 101's notes, both commits, above Phase 100's",
          "## Phase 101 notes" in log and "**Commit 1, the schema**" in log and "**Commit 2, the alerts**" in log
          and log.index("## Phase 101 notes") < log.index("## Phase 100 notes"))
    layers = subprocess.run([sys.executable, str(PROJECT / "tests" / "check_layers.py")], capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    check("no import points up a layer; sqlite3 only in data_access/", layers.returncode == 0, layers.stdout[-300:])
    code = (PROJECT / "logic" / "alerts.py").read_text(encoding="utf-8")
    check("the alert's rules in logic, no Qt and no SQL there", "PySide6" not in code and "SELECT" not in code
          and "execute(" not in code)
    import os
    bare = subprocess.run([sys.executable, str(PROJECT / "tests" / "phase24_tests.py")], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    check("suites 22-25 refuse the real data when run bare (test_sandbox.require_sandbox)",
          bare.returncode == 1 and "run_sandboxed.py phase24_tests.py" in bare.stdout + bare.stderr
          and all("test_sandbox.require_sandbox(__file__)" in (PROJECT / "tests" / f"phase{n}_tests.py")
                  .read_text(encoding="utf-8") for n in (22, 23, 24, 25)), (bare.returncode, bare.stderr[-200:]))
except Exception as exc:
    unreached("6", exc)

changed = box.finish()
check("config.json, the library database and the Run key's value are unchanged", not changed, changed)
check("nothing in this suite reached the network", attempts == [], attempts)
print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
