"""Phase 102: "how was it?" -- one tap after a session, and report 10, Said and played.

  1. the rule (logic/rate.due): asked after a session of RATE_MIN_MINUTES or more, no game running, once a game a
     day, the switch on, never a tool; the words;
  2. the card in the window, on a copy of the real library: shown after a launched session and after one seen
     running, exactly when the rules hold and never otherwise; a star writes one row with the session's keys,
     Skip none, no answer none; the pad -- left and right along the stars, A rates, B skips -- and the TV's
     hints; it waits behind a dialog; a message floats above it; a game starting takes it away; in the tray the
     balloon, and its click the card; the switch off, nothing;
  3. later: a game's page shows each session's stars and five to click for one of the last RATE_LATE_DAYS, not
     older; the game's menu offers "Rate your last session..."; the store keeps a rating through a save that
     rewrites the sessions, lets it go with a pruned session, and moves it with a carried one; Settings'
     After a game;
  4. report 10's maths and words by hand: ranks with ties, Spearman, the words by the size; the worked example of
     docs/ANALIZA.md -- rho 0.30 between the stars and the hours, 0.50 between the fit (each game left out of its
     own taste) and the stars, the disagreements; a game with no hours shown as none, never 0;
  5. report 10 on the copy, against the ratings read through the store; the ten reports, under 50 ms; the
     Markdown; the Reports page's tenth card;
  6. the Settings zip's ratings.json: written, joined on import, twice adds nothing, a rating here kept, one with no
     session or nine stars skipped, an older bundle and a library that keeps none;
  7. the anonymous export's format 3 (the stars and the session's day, a mark's day), nothing personal; the
     comparison and compare_exports reading formats 2 and 3 -- a format-2 export never asked, never 0;
  8. the documents and the layers;
  9. the Phase 102 extension: a game's page shows its hours as the reports count them -- the launcher's own and
     Steam's on the accounts marked yours, an app once -- beside Last played and the size, none when unknown,
     and on a hover where they came from.

On a throwaway copy of the data; the network is blocked; the user's config and library are photographed at
the start and compared at the end.
"""
import copy
import sqlite3
import sys
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import sources  # the build log's notes (Phase 91)
import test_sandbox

# The question asked in this copy: every other suite's copy has it off (test_sandbox.ALWAYS_WRITTEN).
box = test_sandbox.start({"allow_network": False, "startup_scan": False, "tv_mode": False, "ask_rating": True})
attempts: list[str] = []


def no_network(request, *args, **kwargs):
    attempts.append(getattr(request, "full_url", str(request)))
    raise OSError("the network is blocked in this suite")


urllib.request.urlopen = no_network

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication, QDialog

app = QApplication([])

from adapters import controller
from logic import launch, observe, rate, sessions
from presentation import ui_rules, ui_settings, ui_tv, ui_window
from shared import humanize, rules

passed = failed = 0


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


def settle(seconds):
    loop = QEventLoop()
    QTimer.singleShot(int(seconds * 1000), loop.quit)
    loop.exec()


print("=== 1. the rule ===")
base = dict(enabled=True, running=False, asked_today=False, rated_today=False, is_tool=False)
check(f"asked after {rules.RATE_MIN_MINUTES} minutes", rate.due(rules.RATE_MIN_MINUTES, **base) == (True, ""))
check("not one minute less", not rate.due(rules.RATE_MIN_MINUTES - 1, **base)[0])
for name, change in (("the switch off", {"enabled": False}), ("a game still running", {"running": True}),
                     ("asked today already", {"asked_today": True}), ("rated today already", {"rated_today": True}),
                     ("a tool", {"is_tool": True})):
    check(f"not with {name}", not rate.due(60, **{**base, **change})[0], rate.due(60, **{**base, **change}))
ask = rate.Ask("k", "Max Payne 3", "2026-10-19T03:16:02+03:00", 83)
check("the words: the question, the balloon, the thanks",
      rate.question(ask) == f"Max Payne 3, {humanize.playtime(83 * 60)}. How was it?"
      and rate.balloon(ask) == "How was Max Payne 3? Click to rate" and rate.thanks(1) == "Thanks: 1 star")
now = datetime.now().astimezone()
check(f"a session of the last {rules.RATE_LATE_DAYS} days can be rated later; one older cannot",
      rate.rateable(now - timedelta(days=rules.RATE_LATE_DAYS - 1), now)
      and not rate.rateable(now - timedelta(days=rules.RATE_LATE_DAYS + 1), now))

print("\n=== 2. the card in the window ===")
try:
    window = ui_window.MainWindow()
    window.resize(1440, 900)
    window.show()
    settle(1.5)
    window._stop_watch()
    store = window.overrides
    check("the copy's library keeps ratings (version 8)", store.keeps_ratings)
    # Games nothing is rated for: the copy carries the user's own ratings (his first, CULTIC's, on 20 October),
    # and a game rated today is not asked again.
    games = [v for v in window.views if not v.is_non_game and v.entry.launch_kind == "exe"
             and not store.ratings_of(v.key)]
    check(f"{len(games)} exe games with no rating to work with", len(games) >= 17, len(games))
    game, other = games[0], games[1]

    def plant_session(view, minutes, days_ago=0.0, origin=rules.SESSION_LAUNCHED):
        """A session of `view`'s, written as the window writes one; answers its start as the row holds it."""
        start = (datetime.now().astimezone() - timedelta(days=days_ago, minutes=minutes)).replace(microsecond=0)
        record = store.get(view.key)
        entries = sessions.upsert(sessions.load(record), start, minutes, origin)
        store.update(view.key, **{rules.SESSIONS_KEY: sessions.dump(entries)})
        window.reload_views()
        return start

    def end_launched(view, minutes):
        """A launched session's end, through the playtime poll: the side effects of an end stood in for."""
        start = plant_session(view, minutes)
        window._live_sessions[view.key] = (start, minutes * 60)
        held = {name: getattr(window, name) for name in ("_queue_after_session", "_come_back_to_front",
                                                         "_run_wanted_scan", "_run_saves", "_bank_playtime")}
        real_poll = window.tracker.poll
        window.tracker.poll = lambda: [launch.Tick(view.key, view.display_name, 0, True, None, minutes * 60)]
        for name in held:
            setattr(window, name, lambda *a, **k: None)
        try:
            window._poll_playtime()
        finally:
            window.tracker.poll = real_poll
            for name, fn in held.items():
                setattr(window, name, fn)
        return rate.started_text(start)

    def ratings(view):
        return store.ratings_of(view.key)

    started = end_launched(game, 25)
    settle(0.4)
    card = window.rate_card
    check("a launched session of 25 minutes ends: the card asks, bottom-right",
          card.showing and card.question.text() == f"{game.display_name}, {humanize.playtime(25 * 60)}. How was it?"
          and card.geometry().right() > window.width() * 0.6, card.question.text())
    check("a message posted meanwhile floats above the card",
          window.toast.bottom_reserve >= card.height(), (window.toast.bottom_reserve, card.height()))
    window.tv_mode = True  # only the hint bar's choice is asked about here
    window._refresh_hints()
    hints = [label for _pad, label in ui_tv.HINT_SETS[ui_tv.RATE]]
    check("the TV's hints while it asks: Rate, Skip, Stars", window.hint_bar.hints == ui_tv.RATE
          and hints == ["Rate", "Skip", "Stars"], window.hint_bar.hints)
    window.tv_mode = False
    card.stars[3].click()
    settle(0.3)
    check("a tap on the fourth star: one row, the game's, the session's start, 4 stars", ratings(game) == {started: 4},
          ratings(game))
    check("and the card says thanks, then goes", card.question.text().startswith("Thanks") and not card.showing)
    settle(ui_rules.RATE_THANKS_MS / 1000 + 0.4)
    check("gone, and the message's room back", not card.isVisible() and window.toast.bottom_reserve == 0)

    end_launched(game, 40)
    settle(0.3)
    check("the same game again today: not asked", not card.showing)
    end_launched(other, rules.RATE_MIN_MINUTES - 1)
    settle(0.3)
    check(f"a session of {rules.RATE_MIN_MINUTES - 1} minutes: not asked", not card.showing)

    third, fourth, fifth = games[2], games[3], games[4]
    real_running = window.game_running
    window.game_running = lambda: True
    end_launched(third, 30)
    window.game_running = real_running
    settle(0.3)
    check("a game still running: not asked", not card.showing)
    window.config[rules.RATE_ASK_KEY] = False
    end_launched(fourth, 30)
    settle(0.3)
    check("the switch off: not asked, no balloon", not card.showing)
    window.config[rules.RATE_ASK_KEY] = True

    # Skip, and no answer: nothing written.
    started = end_launched(fourth, 30)
    settle(0.3)
    check("asked", card.showing)
    card.skip_button.click()
    settle(0.3)
    check("Skip: nothing written, the card gone", ratings(fourth) == {} and not card.isVisible())
    real_card_s = rules.RATE_CARD_S
    rules.RATE_CARD_S = 1
    started = end_launched(fifth, 30)
    for _ in range(40):  # one second asked, then its fade: waited for, not guessed (a busy PC is slower)
        settle(0.1)
        if not card.isVisible():
            break
    rules.RATE_CARD_S = real_card_s
    check("no answer: it goes by itself, nothing written", not card.isVisible() and ratings(fifth) == {})

    # The pad: right three times, A -- three stars; B skips.
    sixth, seventh = games[5], games[6]
    started = end_launched(sixth, 30)
    settle(0.3)
    for _ in range(3):
        window._on_pad_action(controller.RIGHT)
    lit = card.lit
    window._on_pad_action(controller.LEFT)
    window._on_pad_action(controller.RIGHT)
    window._on_pad_action(controller.ACTIVATE)
    settle(0.3)
    check("the pad: right moves along the stars, left back, A rates the lit one", lit == 3 and ratings(sixth) == {started: 3},
          (lit, ratings(sixth)))
    settle(ui_rules.RATE_THANKS_MS / 1000 + 0.3)
    end_launched(seventh, 30)
    settle(0.3)
    window._on_pad_action(controller.DOWN)
    still = card.showing
    window._on_pad_action(controller.BACK)
    settle(0.3)
    check("while it asks the pad moves nothing else; B skips", still and not card.isVisible() and ratings(seventh) == {})

    # Never over a dialog: it waits, and comes when the dialog has gone.
    eighth = games[7]
    dialog = QDialog(window)
    dialog.setModal(True)
    dialog.show()
    settle(0.2)
    started = end_launched(eighth, 30)
    settle(0.3)
    waited = not card.isVisible()
    dialog.reject()
    settle(rules.RATE_RETRY_MS / 1000 + 0.5)
    check("a dialog open: the card waits, and asks once it has closed", waited and card.showing, (waited, card.showing))
    window.begin_starting(window.by_key[eighth.key])  # Play pressed: the splash, Starting...
    gone_on_start = not card.isVisible()
    window.end_starting("the test")
    check("a game starting takes it away, nothing written", gone_on_start and ratings(eighth) == {})

    # An observed session's end.
    ninth = games[8]
    seen = observe.Seen(ninth.key, ninth.display_name, False, "exe", datetime.now().astimezone() - timedelta(minutes=22),
                        time.monotonic() - 22 * 60)
    seen.seconds = 22 * 60
    real_saves = window.save_job
    window.save_job = lambda *a, **k: None
    try:
        window._bank_observed(seen, final=True)
    finally:
        window.save_job = real_saves
    settle(0.4)
    check("a session seen running ends (22 min): the card asks too", card.showing
          and ninth.display_name in card.question.text(), card.question.text())
    card.stars[4].click()
    settle(0.3)
    check("and its five stars are its row", list(ratings(ninth).values()) == [5], ratings(ninth))
    settle(ui_rules.RATE_THANKS_MS / 1000 + 0.3)

    # In the tray: the balloon, and its click brings the card.
    tenth = games[9]
    said: list = []
    window._in_tray, real_tray = True, window.tray
    window.tray = type("Tray", (), {"say": lambda self, text, clicked=None: said.append((text, clicked)),
                                    "set_tooltip": lambda self, text: None})()
    try:
        started = end_launched(tenth, 30)
    finally:
        window._in_tray, window.tray = False, real_tray
    settle(0.3)
    check("hidden in the tray: the balloon, 'How was <game>? Click to rate', no card",
          said and said[0][0] == f"How was {tenth.display_name}? Click to rate" and not card.isVisible(), said)
    real_forward = window.bring_forward
    window.bring_forward = lambda: None
    said[0][1]()
    settle(rules.RATE_RETRY_MS / 4000 + 0.5)
    window.bring_forward = real_forward
    check("its click: the window, and the card in it", card.showing and tenth.display_name in card.question.text())
    card.stars[1].click()
    settle(0.3)
    check("rated from there: two stars", ratings(tenth) == {started: 2}, ratings(tenth))
    settle(ui_rules.RATE_THANKS_MS / 1000 + 0.3)
except Exception as exc:
    unreached("2", exc)

print("\n=== 3. later: the page, the menu, the store, the switch ===")
try:
    late = games[10]
    recent = plant_session(late, 35, days_ago=2)
    old = plant_session(late, 45, days_ago=rules.RATE_LATE_DAYS + 3)
    window.show_detail(late.key)
    settle(0.8)
    bars = window.detail.session_bars
    starts = window.detail._session_starts
    rows = dict(zip(starts, bars.stars))
    check(f"the page: five to click for a session two days old; none for one {rules.RATE_LATE_DAYS + 3} days old",
          rows.get(rate.started_text(recent)) == (None, True) and rows.get(rate.started_text(old)) == (None, False), rows)
    menu_words = [a.text() for a in __import__("presentation.ui_actions", fromlist=["x"]).build_menu(window, late).actions()]
    check("the game's menu offers Rate your last session...", "Rate your last session..." in menu_words, menu_words)
    bars.rateClicked.emit(starts.index(rate.started_text(recent)), 4)
    settle(0.4)
    rows = dict(zip(window.detail._session_starts, window.detail.session_bars.stars))
    check("a click on its fourth star rates it: the row shows 4, no longer to click",
          store.ratings_of(late.key) == {rate.started_text(recent): 4}
          and rows.get(rate.started_text(recent)) == (4, False), rows)
    menu_words = [a.text() for a in __import__("presentation.ui_actions", fromlist=["x"]).build_menu(window, late).actions()]
    check("then nothing left to rate: the menu offers it no more", "Rate your last session..." not in menu_words)
    bars.rateClicked.emit(window.detail._session_starts.index(rate.started_text(recent)), 2)
    settle(0.3)
    check("rated again: the stars replaced, one row", store.ratings_of(late.key) == {rate.started_text(recent): 2})
    window.show_library()
    settle(0.4)

    # The menu's way: the card for the game's last session still to rate.
    by_menu = games[11]
    menu_start = plant_session(by_menu, 50, days_ago=1)
    window.rate_last_session(window.by_key[by_menu.key])
    settle(0.4)
    check("Rate your last session...: the card for it, worked like any", window.rate_card.showing
          and by_menu.display_name in window.rate_card.question.text())
    window._on_pad_action(controller.ACTIVATE)
    settle(0.3)
    check("A: one star, its row", store.ratings_of(by_menu.key) == {rate.started_text(menu_start): 1})
    settle(ui_rules.RATE_THANKS_MS / 1000 + 0.3)

    # The store: a rating kept through a save that rewrites the sessions, gone with a pruned one, moved with a carry.
    key = late.key
    store.update(key, notes=(store.get(key).get(rules.NOTES_KEY) or "") + " ")
    check("a save of the rated game rewrites its sessions, and keeps the rating",
          store.ratings_of(key) == {rate.started_text(recent): 2})
    kept = [e for e in sessions.load(store.get(key)) if rate.started_text(e.start) != rate.started_text(recent)]
    store.update(key, **{rules.SESSIONS_KEY: sessions.dump(kept)})
    check("its session gone from the record (pruned): the rating goes with it, in the same save",
          store.ratings_of(key) == {})
    raw = sqlite3.connect(f"file:{box.path('library.db').as_posix()}?mode=ro", uri=True)
    check("and no rating names a missing session", raw.execute("PRAGMA foreign_key_check").fetchall() == [])
    raw.close()
    # A carry: the old record's sessions merged into a new one; the rating follows its session.
    old_key, new_key = games[12].key, games[13].key
    carried_start = plant_session(games[12], 60, days_ago=1)
    store.rate_session(old_key, rate.started_text(carried_start), 5)
    old_record, new_record = copy.deepcopy(store.get(old_key)), copy.deepcopy(store.get(new_key))
    merged = sessions.merge(sessions.load(new_record), sessions.load(old_record))
    new_record[rules.SESSIONS_KEY] = sessions.dump(merged)
    left = {k: v for k, v in old_record.items() if k == "first_seen"}
    left[rules.CARRIED_TO_KEY] = new_key
    left[rules.CARRIED_AT_KEY] = datetime.now().astimezone().isoformat(timespec="seconds")
    moved = store.carry(old_key, new_key, old_record=left, new_record=new_record)
    check("a carry to a reinstall: the rating moves with its session to the new game",
          moved and store.ratings_of(new_key).get(rate.started_text(carried_start)) == 5
          and store.ratings_of(old_key) == {}, (moved, store.ratings_of(new_key), store.ratings_of(old_key)))

    # Settings: After a game.
    dialog = ui_settings.SettingsDialog(dict(window.config), window, known_keys=set(), store=store)
    rows_text = [r.title.text() for r in dialog.findChildren(ui_settings.SettingRow) if hasattr(r, "title")]
    check("Settings: After a game, 'Ask how a session was', on", "Ask how a session was" in rows_text
          and dialog.rate_box.isChecked() and dialog.values()[rules.RATE_ASK_KEY] is True, rows_text[-6:])
    dialog.rate_box.setChecked(False)
    check("off, it says so in its answer", dialog.values()[rules.RATE_ASK_KEY] is False)
    dialog.reject()
except Exception as exc:
    unreached("3", exc)

print("\n=== 4. report 10's maths and words, worked out by hand ===")
try:
    from logic import reports as reports_module
    check("ranks: 1 the smallest, a tie shares the mean of its places", reports_module.ranks([10, 20, 20, 30])
          == [1.0, 2.5, 2.5, 4.0], reports_module.ranks([10, 20, 20, 30]))
    sp = reports_module.spearman
    check("Spearman: the same order 1, the reverse -1, a list all alike None",
          sp([1, 2, 3], [5, 6, 9]) == 1.0 and sp([1, 2, 3], [9, 6, 5]) == -1.0 and sp([2, 2, 2], [1, 2, 3]) is None)
    check("Spearman with a tie, by hand: Pearson on the ranks, 4.5 / sqrt(4.5 x 5) = 0.9487",
          abs(sp([1, 2, 2, 3], [1, 3, 2, 4]) - 4.5 / (4.5 * 5) ** 0.5) < 1e-12, sp([1, 2, 2, 3], [1, 3, 2, 4]))
    words = reports_module.correlation_words
    check("its words, honest about the size: under 5 none, under 10 a hint, then its strength and its way",
          words(None, 4, "the stars and the hours") == "4 games are too few to set the stars and the hours side by "
                                                        "side (it takes 5)"
          and words(0.4, 6, "x").endswith("— on so few, a hint and not a finding")
          and words(0.1, 12, "x").startswith("little or no rank correlation") and "rise" not in words(0.1, 12, "x")
          and words(0.5, 12, "x").startswith("a moderate") and words(0.5, 12, "x").endswith("they rise together")
          and words(-0.7, 12, "x").startswith("a strong") and words(-0.7, 12, "x").endswith("the other falls"),
          [words(None, 4, "the stars and the hours"), words(0.1, 12, "x"), words(-0.7, 12, "x")])

    # The worked example of docs/ANALIZA.md: five games rated twice, one once; genres 1 Action, 2 RPG, 3 Puzzle,
    # all weighing the same.
    planted_rows = [  # as said_played answers: by mean stars, then minutes
        {"name": "A", "appid": 1, "game_id": None, "minutes": 1800, "ratings": 2, "mean_stars": 5.0, "late": 0, "has_record": 1},
        {"name": "B", "appid": 2, "game_id": None, "minutes": 60, "ratings": 2, "mean_stars": 4.5, "late": 1, "has_record": 1},
        {"name": "E", "appid": 5, "game_id": None, "minutes": 1200, "ratings": 2, "mean_stars": 4.0, "late": 0, "has_record": 1},
        {"name": "C", "appid": 3, "game_id": None, "minutes": 720, "ratings": 2, "mean_stars": 3.0, "late": 0, "has_record": 1},
        {"name": "F", "appid": 6, "game_id": None, "minutes": 100, "ratings": 1, "mean_stars": 3.0, "late": 1, "has_record": 1},
        {"name": "D", "appid": 4, "game_id": None, "minutes": 900, "ratings": 2, "mean_stars": 2.0, "late": 0, "has_record": 1},
    ]
    hand = {"said_played": planted_rows,
            "concentration": [{"appid": r["appid"], "minutes": r["minutes"], "name": r["name"]} for r in planted_rows],
            "recommend_genres": [{"appid": a, "genre_id": g, "name": n} for a, g, n in
                                 ((1, 1, "Action"), (2, 2, "RPG"), (3, 1, "Action"), (3, 2, "RPG"), (4, 3, "Puzzle"),
                                  (5, 1, "Action"), (6, 2, "RPG"))],
            "wishlist_idf": [{"genre_id": g, "apps": 1, "corpus": 2} for g in (1, 2, 3)]}
    ten = reports_module.said_played(hand)
    check("report 10: number, key, title", (ten.number, ten.key, ten.title) == (10, "said_played", "Said and played"))
    check(f"its sentence: 11 ratings on 6 games, 5 twice; rho +0.30 and +0.50, each a hint on five: {ten.sentence!r}",
          ten.sentence.startswith("11 ratings on 6 games, 5 of them rated twice or more; ")
          and "the stars and the hours give ρ = +0.30 on 5 games" in ten.sentence
          and "the fit and the stars give ρ = +0.50 on 5 games" in ten.sentence
          and ten.sentence.count("a hint and not a finding") == 2, ten.sentence)
    table = next(p for p in ten.parts if p.heading == "Said and played")
    check("the table: the five rated twice, in the query's order, ranked 1 the best and the most played -- F, rated "
          "once, counted in the note", [(r[0], r[1], r[2], r[4], r[5]) for r in table.rows] ==
          [("A", "2", "5.0 of 5", "1", "1"), ("B", "2", "4.5 of 5", "2", "5"), ("E", "2", "4.0 of 5", "3", "2"),
           ("C", "2", "3.0 of 5", "4", "4"), ("D", "2", "2.0 of 5", "5", "3")]
          and "1 game rated once is not in it." in table.note, (table.rows, table.note))
    disagree = next(p for p in ten.parts if p.heading == "Where they disagree")
    check("where they disagree: B rated well and barely played, D played much and rated low",
          [(r[0], r[3]) for r in disagree.rows] == [("B", "rated well, barely played"), ("D", "played much, rated low")],
          disagree.rows)
    fitted = next(p for p in ten.parts if p.heading == "The fit against the stars")
    check("the fit, each game left out of its own taste: E 90%, A 84%, C 71%, B 17%, D unlike",
          [(r[0], r[1]) for r in fitted.rows] == [("E", "90%"), ("A", "84%"), ("C", "71%"), ("B", "17%"),
                                                    ("D", "unlike what you play")], fitted.rows)
    shares = {r[0]: r[1] for r in fitted.data}
    check("its scores as worked out in ANALIZA: 0.8361, 0.1658, 0.7125, 0, 0.8995",
          all(abs(shares[n] - v) < 1e-3 for n, v in (("A", 0.8361), ("B", 0.1658), ("C", 0.7125), ("D", 0.0),
                                                      ("E", 0.8995))), shares)
    whole = __import__("logic.fit", fromlist=["fit"])
    weights = whole.weights_of(hand["wishlist_idf"])
    with_itself = whole.share_of(whole.vector([1], weights), whole.taste(
        whole.profile_from(hand["concentration"], hand["recommend_genres"]), weights))
    check(f"and the twin: with A's own hours in the taste it would read {with_itself:.0%}, not 84%",
          round(with_itself, 2) == 0.95 and shares["A"] < with_itself - 0.1, with_itself)
    # A seventh game rated twice that report 1 has no hours for: shown without hours, never as 0, and left out of
    # what is set against them.
    lost = {"name": "G", "appid": 7, "game_id": None, "ratings": 2, "mean_stars": 4.0, "late": 0, "has_record": 0}
    seven = reports_module.said_played({**hand, "said_played": planted_rows + [lost]})
    seven_table = next(p for p in seven.parts if p.heading == "Said and played")
    g_row = next(r for r in seven_table.rows if r[0] == "G")
    check("a rated game with no hours report 1 counts: '—', not 0; the correlation still on the five",
          g_row[3] == "—" and g_row[5] == "—" and "ρ = +0.30 on 5 games" in seven.sentence
          and "1 game without hours report 1 counts" in seven_table.note, (g_row, seven_table.note))
    check("the caveat names the response bias, the one-a-day rule, the late ratings (1 of 11) and the size",
          all(w in ten.caveat for w in ("response bias", "One question a game a day", "(2 of 11 ratings did)",
                                        f"up to {rules.RATE_LATE_DAYS} days", "a finding only from 10")), ten.caveat)
    check("the idea names explicit and implicit feedback, rank correlation, response bias, rating sparsity",
          all(w in ten.concept for w in ("Explicit and implicit feedback", "Rank correlation", "Response bias",
                                         "Rating sparsity")), ten.concept)
    quiet = reports_module.said_played({**hand, "said_played": []})
    check("nothing rated: said in words, nothing drawn", quiet.empty and quiet.parts == ()
          and quiet.sentence.startswith("No session has been rated yet"), quiet.sentence)
    once = reports_module.said_played({**hand, "said_played": [planted_rows[4]]})
    check("one rating: 'none rated twice yet', no correlation", not once.empty
          and once.sentence == "1 rating on 1 game, none rated twice yet, which a game's mean takes.", once.sentence)
except Exception as exc:
    unreached("4", exc)

print("\n=== 5. report 10 on the copy, by two roads; the ten reports ===")
try:
    from data_access import reports as data_reports
    rated_now = 0
    for n, view in enumerate(games[14:17]):
        for days, stars in ((3, 5 - n), (1, 4 - n)):
            start = plant_session(view, 30 + 10 * n, days_ago=days)
            rated_now += store.rate_session(view.key, rate.started_text(start), stars)
    check("three more games rated twice each, through the store", rated_now == 6)
    source = store.reports()
    rows = source.rows("said_played")
    raw = sqlite3.connect(f"file:{box.path('library.db').as_posix()}?mode=ro", uri=True)
    ids = {key: (gid, appid) for gid, key, appid in raw.execute("SELECT id, identity_key, steam_appid FROM game")}
    raw.close()
    expected: dict = {}
    for key, given in store.all_ratings().items():
        gid, appid = ids[key]
        item = (appid, None) if appid is not None else (None, gid)
        for r in given:
            held = expected.setdefault(item, [0, 0, 0])
            held[0] += 1
            held[1] += r["stars"]
            held[2] += r["rated_at"][:10] > r["started_at"][:10]
    got = {(r["appid"], r["game_id"]): [r["ratings"], r["mean_stars"], r["late"]] for r in rows}
    check(f"said_played, against the ratings read through the store: {len(got)} games, counts, means, late ones",
          got.keys() == expected.keys()
          and all(got[k][0] == e[0] and abs(got[k][1] - e[1] / e[0]) < 1e-9 and got[k][2] == e[2]
                  for k, e in expected.items()), (got, expected))
    built = reports_module.build(source)
    first = {round(r["minutes"]) for r in source.rows("concentration")}
    table_now = next(p for p in built[9].parts if p.heading == "Said and played")
    check("and each rated game's hours are report 1's, or none", all(r[3] is None or r[3] in first
                                                                     for r in table_now.data), table_now.data)
    check("eleven reports (since Phase 103), the tenth Said and played", len(built) == 11 == len(reports_module.BUILDERS)
          and [r.key for r in built][8:10] == ["recommendation", "said_played"])
    tenth = built[9]
    judged_here = sum(1 for e in expected.values() if e[0] >= rules.REPORT_RATED_MIN)
    check(f"on the copy it answers: {tenth.sentence[:100]}", not tenth.empty and f"rated twice or more" in tenth.sentence
          and len(next(p for p in tenth.parts if p.heading == "Said and played").rows) == judged_here, tenth.sentence)
    timings = []
    for _ in range(5):
        began = time.perf_counter()
        reports_module.build(source)
        timings.append((time.perf_counter() - began) * 1000)
    check(f"the eleven reports together (since Phase 103): best of 5 {min(timings):.1f} ms, under 50", min(timings) < 50, timings)
    began = time.perf_counter()
    source.rows("said_played")
    print(f"      said_played alone: {(time.perf_counter() - began) * 1000:.1f} ms")
    md = reports_module.markdown(built, datetime.now(), data_reports.QUERIES)
    check("the Markdown carries ## 10. and its SQL", "## 10. Said and played" in md
          and data_reports.QUERIES["said_played"] in md)
    window.show_reports()
    settle(1.0)
    cards = [c for c in window.reports_page.cards if getattr(c, "report", None) is not None]
    check("the Reports page: eleven cards (since Phase 103), Said and played the tenth, its bars and tables drawn",
          len(cards) == 11 and cards[9].report.key == "said_played" and cards[9].bars and cards[9].tables,
          [c.report.key for c in cards])
    from presentation import ui_reports
    check("the page's intro says eleven questions (since Phase 103)", ui_reports.INTRO.startswith("Eleven questions"))
    window.show_library()
    settle(0.4)
except Exception as exc:
    unreached("5", exc)

print("\n=== 6. the Settings zip carries the ratings ===")
try:
    import json
    import tempfile
    import zipfile
    from data_access import catalog_io, library_db
    from logic import transfer
    work = Path(tempfile.mkdtemp(prefix="phase102_"))
    mine = store.all_ratings()
    total = sum(len(v) for v in mine.values())
    bundle = work / "export.gamelauncher.zip"
    report = transfer.export_bundle(bundle, store=store)
    with zipfile.ZipFile(bundle) as archive:
        names = set(archive.namelist())
        carried = json.loads(archive.read(rules.TRANSFER_RATINGS_MEMBER))["games"]
        manifest = json.loads(archive.read(rules.TRANSFER_MANIFEST))
    check(f"ratings.json holds every rating ({total}), by game: the session, the stars, the moment",
          carried == mine and report.ratings == total == manifest.get("ratings")
          and f"{total} session ratings" in report.message, report.message)
    other = library_db.LibraryStore(work / "other.db")
    imported = transfer.import_bundle(bundle, store=other)
    check("imported into another library: every rating joins, its session having come with the record",
          imported.ok and imported.ratings == total and other.all_ratings() == mine
          and f"{total} session ratings were added." in imported.message, imported.message)
    some_key = next(iter(mine))
    some_start = mine[some_key][0]["started_at"]
    other.rate_session(some_key, some_start, 1 if mine[some_key][0]["stars"] != 1 else 2)
    again = transfer.import_bundle(bundle, store=other)
    check("imported twice: nothing added, and a session rated there keeps its own stars",
          again.ok and again.ratings == 0 and other.ratings_of(some_key)[some_start] != mine[some_key][0]["stars"])
    older = work / "older.gamelauncher.zip"
    with zipfile.ZipFile(bundle) as source_zip, zipfile.ZipFile(older, "w") as target:
        for name in source_zip.namelist():
            if name != rules.TRANSFER_RATINGS_MEMBER:
                target.writestr(name, source_zip.read(name))
    check("a bundle from before ratings imports as before", transfer.import_bundle(older, store=other).ratings == 0)
    stray = work / "stray.gamelauncher.zip"
    with zipfile.ZipFile(bundle) as source_zip, zipfile.ZipFile(stray, "w") as target:
        for name in source_zip.namelist():
            body = source_zip.read(name)
            if name == rules.TRANSFER_RATINGS_MEMBER:
                body = json.dumps({"version": 1, "games": {some_key: [
                    {"started_at": "2001-01-01T10:00:00+02:00", "stars": 4, "rated_at": "2001-01-01T11:00:00+02:00"},
                    {"started_at": some_start, "stars": 9, "rated_at": "2026-10-20T10:00:00+03:00"}]}})
            target.writestr(name, body)
    odd = transfer.import_bundle(stray, store=other)
    check("a rating whose session is not there, and one of nine stars, are skipped and counted",
          odd.ok and odd.ratings == 0 and odd.ratings_skipped == 2 and "not imported" in odd.message, odd.message)
    other.close()
    json_store = catalog_io.Overrides(path=work / "json-library.json")
    skipped = transfer.import_bundle(bundle, store=json_store)
    check("into a library that keeps no ratings: the rest imports, and it says what it could not",
          skipped.ok and skipped.ratings_skipped == total and "not imported" in skipped.message, skipped.message)
except Exception as exc:
    unreached("6", exc)

print("\n=== 7. the anonymous export, format 3; the comparison reads 2 and 3 ===")
try:
    from logic import analysis, comparison, comparison_report
    from presentation import ui_actions
    marked_view = window.by_key[games[14].key]
    ui_actions.set_status(window, marked_view, rules.STATUSES[0])
    settle(0.3)
    data = analysis.build(store, "p-0123456789")
    check("format 3", data["version"] == rules.ANALYSIS_FORMAT_VERSION == 3)
    items = [g for g in data["games"] if g["ratings"]]
    exported = sum(len(g["ratings"]) for g in items)
    check(f"each rated game carries its ratings ({exported}): the stars and the session's day, nothing more",
          exported and all(set(r) == {"stars", "day"} and len(r["day"]) == 10 for g in items for r in g["ratings"])
          and exported == sum(len(v) for k, v in store.all_ratings().items()
                              if not window.by_key.get(k) or not window.by_key[k].is_non_game), exported)
    today = datetime.now().astimezone().date().isoformat()
    since = [g["status_since"] for g in data["games"] if g["status_since"]]
    check("a mark set today: its day, and only for a game that has a mark", today in since
          and all(g["status"] for g in data["games"] if g["status_since"]), since[:5])
    check("nothing personal in it: the last check passes", analysis.leaks(data, store.personal_values()) == [])
    check("the dialog's summary says so", any("session rating" in line and "never its time" in line
                                              for line in analysis.summary(data)), analysis.summary(data))
    folder = work / "exports"
    folder.mkdir()
    analysis.write(folder / "three.json", data, store.personal_values())
    two = copy.deepcopy(data)
    two.update(version=2, participant="p-aaaaaaaaaa", made_on="2026-10-01")
    for g in two["games"]:
        g.pop("ratings")
        g.pop("status_since")
    (folder / "two.json").write_text(json.dumps(two), encoding="utf-8")
    loaded = comparison.load([folder])
    by_code = {p.code: p for p in loaded.participants}
    check("both read: the format-2 one with no ratings (None, never 0), the format-3 one with its count",
          not loaded.skipped and by_code["p-aaaaaaaaaa"].ratings is None
          and by_code["p-0123456789"].ratings == exported, [(p.code, p.ratings) for p in loaded.participants])
    import compare_exports
    out = work / "comparison"
    compare_exports.main([str(folder), "--out", str(out), "--no-open"])
    page = (out / "index.html").read_text(encoding="utf-8")
    csv_rows = (out / "participants.csv").read_text(encoding="utf-8-sig").splitlines()
    check("compare_exports on both: the page says the format-2 one was never asked, the CSV leaves it empty",
          "Evaluări" in page and "— (format 2)" in page and f"{exported} pe " in page
          and csv_rows[0].split(";")[-3:] == ["ratings", "rated_games", "mean_stars"]
          and csv_rows[1].split(";")[-3:] == ["", "", ""], (csv_rows[:3],))
except Exception as exc:
    unreached("7", exc)

print("\n=== 8. the documents, the layers ===")
try:
    import re
    import subprocess

    def doc(rel):
        return (PROJECT / rel).read_text(encoding="utf-8").replace("\r\n", "\n")
    analysis_doc = doc("docs/ANALIZA.md")
    quoted = dict(re.findall(r"```sql\n-- (\w+)\n(.*?)\n```", analysis_doc, re.S))
    check("ANALIZA: unsprezece rapoarte (since Phase 103), report 10 in its contents and its section, its query as "
          "the code has it", analysis_doc.startswith("# Ce poate spune baza de date: unsprezece rapoarte")
          and "(#10-spus-și-jucat)" in analysis_doc and "## 10. Spus și jucat" in analysis_doc
          and quoted.get("said_played") == data_reports.QUERIES["said_played"])
    flat_analysis = " ".join(analysis_doc.split())  # as it reads, whatever the line breaks
    check("ANALIZA names the ideas and works the example by hand: rho 0.30 and 0.50",
          all(w in flat_analysis for w in ("explicit feedback", "implicit feedback", "Spearman's rank correlation",
                                          "response bias", "rating sparsity", "one-tap interaction", "leave-one-out",
                                          "**0,30**", "**0,50**")))
    readme = doc("docs/CITESTE-MA.md")
    check("CITESTE-MA: the question, Skip, the switch, the export's ratings, the reports, still one page",
          all(w in readme for w in ("**How was it?**", "**Skip**", "Settings → After a game", "unsprezece rapoarte",
                                    "ce note le-ai dat")) and len(readme.splitlines()) <= 110, len(readme.splitlines()))
    explained = doc("docs/explicatii/faza-102.md")
    check("docs/explicatii/faza-102.md: the shape, the five words", all(w in explained for w in (
        "## Ce s-a construit", "## De ce contează", "## Cum funcționează", "## Cinci cuvinte", "## Trei întrebări",
        "## Ce nu poate face", "explicit and implicit feedback", "rank correlation", "response bias",
        "rating sparsity", "one-tap interaction")) and "faza 102" in doc("docs/explicatii/CITESTE-MA.md"))
    arch = doc("docs/ARHITECTURA.md")
    check("ARHITECTURA: ui_rate and rate in the map, the walk from a session's end to the card (5.8)",
          "`ui_rate.py` *(Faza 102)*" in arch and "`rate.py` *(Faza 102)*" in arch and "### 5.8" in arch
          and "_ask_rating" in arch)
    check("BAZA_DE_DATE: rating is written now", "**scrisă din faza 102**" in doc("docs/BAZA_DE_DATE.md"))
    claude = doc("CLAUDE.md")
    check("CLAUDE.md: the row, the modules, the ten reports, and under its size", "| 102 |" in claude
          and "ui_rate.py" in claude and "the eleven reports from the command line" in claude
          and "the ten reports from the command line" not in claude
          and len(claude.encode("utf-8")) < 116581, len(claude.encode("utf-8")))
    layers = subprocess.run([sys.executable, str(PROJECT / "tests" / "check_layers.py")], capture_output=True,
                            text=True, encoding="utf-8", errors="replace")
    check("check_layers: no import points up a layer", layers.returncode == 0, layers.stdout[-300:])
except Exception as exc:
    unreached("8", exc)

print("\n=== 9. the Phase 102 extension: the hours pill ===")
try:
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QHelpEvent
    from presentation import ui_detail

    began = time.perf_counter()
    hours = store.hours()
    took = (time.perf_counter() - began) * 1000
    raw = sqlite3.connect(f"file:{box.path('library.db').as_posix()}?mode=ro", uri=True)
    by_app = {a: m for a, g, m in raw.execute("SELECT appid, game_id, minutes FROM v_hours") if a is not None}
    by_game = {g: m for a, g, m in raw.execute("SELECT appid, game_id, minutes FROM v_hours") if a is None}
    games_rows = raw.execute("SELECT identity_key, id, steam_appid FROM game").fetchall()
    raw.close()
    expected = {key: (by_app.get(appid) if appid is not None else by_game.get(gid)) for key, gid, appid in games_rows}
    check(f"the store's hours, one read for all {len(hours)} games in {took:.1f} ms: each game's row of v_hours, "
          "by its Steam app or its record", took < 10 and all(abs(hours[k]["minutes"] - (expected[k] or 0)) < 1e-9
                                                            for k in hours) and set(hours) <= set(expected), took)

    # A Steam game Steam counts hours for, given some of the launcher's too: the two added, and said apart.
    steam_games = [v for v in window.views if v.entry.source == "steam" and (hours.get(v.key) or {}).get("steam")]
    check(f"{len(steam_games)} Steam games with Steam's own hours to show", bool(steam_games))
    both = steam_games[0]
    store.update(both.key, playtime_seconds=(store.get(both.key).get("playtime_seconds") or 0) + 600)
    window.reload_views()
    page = window.detail
    pills_seen = {}
    for view in [v for v in window.views if not v.hidden]:
        page.set_view(view)
        played = page.pills["Played"]
        pills_seen[view.key] = (not played.isHidden(), played.text().strip(), played.toolTip())
    settle(0.3)

    def words_for(view):
        h = window.hours.get(view.key)
        seconds = round(h["minutes"] * 60) if h else 0
        if seconds > 0:
            return f"{humanize.playtime(seconds)} played"
        return "Not played yet" if view.entry.launch_kind == "exe" else None

    wrong = {k: (seen, words_for(window.by_key[k])) for k, seen in pills_seen.items()
             if (seen[1] if seen[0] else None) != words_for(window.by_key[k])}
    check(f"every game's page ({len(pills_seen)}): the pill is its hours as the reports count them; none when "
          "they are unknown, 'Not played yet' for a game the launcher starts", not wrong, wrong)
    steam_part = humanize.playtime(round(window.hours[both.key]["steam"] * 60))
    check(f"{both.display_name}: Steam's and the launcher's added, and on a hover said apart",
          pills_seen[both.key][2] == ui_detail.PLAYED_TIP_BOTH.format(steam=steam_part, launcher="10 min"),
          pills_seen[both.key])
    only_steam = next((v for v in steam_games[1:] if not window.hours[v.key]["launcher"]), None)
    check("one with Steam's alone says it is Steam's count", only_steam is None
          or pills_seen[only_steam.key][2] == ui_detail.PLAYED_TIP_STEAM, only_steam and pills_seen[only_steam.key])
    timed = next((v for v in window.views if v.entry.launch_kind == "exe" and v.playtime_seconds > 0
                  and not (window.hours.get(v.key) or {}).get("steam")), None)
    check("one the launcher alone timed says so", timed is not None
          and pills_seen[timed.key][2] == ui_detail.PLAYED_TIP_LAUNCHER, timed and pills_seen[timed.key])
    check("the twin: before the extension a Steam game had no pill -- now one with hours shows them",
          any(pills_seen[v.key][0] for v in steam_games))

    window.show_detail(both.key)
    settle(0.8)
    shown = sorted((p.y(), p.x(), f) for f, p in page.pills.items() if not p.isHidden())
    order = [f for _y, _x, f in shown]
    check("Last played, Played and the size side by side, in that order (the user's)",
          [f for f in order if f in ("Last played", "Played", "Installed")]
          == [f for f in ("Last played", "Played", "Installed") if f in order], order)
    played = page.pills["Played"]
    centre = played.geometry().center()
    QApplication.sendEvent(page.pill_row, QHelpEvent(QEvent.Type.ToolTip, centre, page.pill_row.mapToGlobal(centre)))
    settle(0.5)
    tips = [w.text() for w in QApplication.topLevelWidgets()
            if w.metaObject().className() == "QTipLabel" and w.isVisible()]
    check("a hover on the pill shows where its hours came from (the pill lets the mouse through; its row asks)",
          played.testAttribute(__import__("PySide6.QtCore", fromlist=["Qt"]).Qt.WidgetAttribute.WA_TransparentForMouseEvents)
          and played.toolTip() in tips, tips)
    corner = page.pill_row.rect().bottomRight()
    QApplication.sendEvent(page.pill_row, QHelpEvent(QEvent.Type.ToolTip, corner, page.pill_row.mapToGlobal(corner)))
    settle(0.4)
    check("and nothing between the pills", page.pill_at(corner) is None)
    window.show_library()
    settle(0.4)
    claude_text = (PROJECT / "CLAUDE.md").read_text(encoding="utf-8")
    page_text = (PROJECT / "docs" / "explicatii" / "faza-102-extensie.md").read_text(encoding="utf-8")
    check("the documents: CLAUDE.md's row, the explanation page in its shape, the index",
          "| 102 extension |" in claude_text and all(w in page_text for w in (
              "## Ce s-a construit", "## De ce contează", "## Cum funcționează", "## Cinci cuvinte",
              "## Trei întrebări", "## Ce nu poate face"))
          and "extensia fazei 102" in (PROJECT / "docs" / "explicatii" / "CITESTE-MA.md").read_text(encoding="utf-8")
          and "## Phase 102 extension notes" in sources.build_log())
except Exception as exc:
    unreached("9", exc)

if "window" in globals():
    window._stop_watch()
    window._shut_down = True
    window.overrides.close()
    settle(0.3)
changed = box.finish()
check("config.json, the library database and the Run key's value are unchanged", not changed, changed)
check("nothing in this suite reached the network", attempts == [], attempts)
print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
