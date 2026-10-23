"""Phase 94: a PC that sleeps with a game open does not count the sleep as play.

Found at Phase 93's step 0 (18 October): the tracker measured a session from its start with
time.monotonic(), which on this Windows reads QueryPerformanceCounter -- a clock reported to
keep counting through a sleep. Nothing looks while the PC sleeps, the game's processes are
still there when it wakes, so the first look after waking added the whole sleep to the game's
total and to the session's minutes. Now each gap between two looks counts at most
rules.PLAYTIME_GAP_MAX_S, three looks' worth (9 s), and a longer one is said in the log.

When nothing sleeps every gap is one look, so nothing is cut: Phase 53's promise -- the total
and the session agree within a second -- is checked again here at three paces, the slowest
just under the cap.

Played on a fake clock, as suite 53 does: the real tracker, the real window, the real banking
into a throwaway copy of the library. A sleep is the clock jumping with no look in between.
Nothing is started.
"""
import logging
import random
import sys
import time as real_time
from datetime import datetime, timedelta
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))  # the project folder, one up from tests/
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import test_sandbox

box = test_sandbox.start({"tv_mode": False})

logging.basicConfig(level=logging.ERROR)

from PySide6.QtWidgets import QApplication

app = QApplication([])

from logic import launch, sessions
from presentation import ui_window
from shared import rules

passed = failed = 0
CAP = 9  # three looks of 3 s: what the phase promises, so the code before it can be judged too
GAP_MAX = getattr(rules, "PLAYTIME_GAP_MAX_S", None)
POLL_MS = getattr(rules, "PLAYTIME_POLL_MS", None)
HOUR = 3600.0


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"   PASS  {name}")
    else:
        failed += 1
        print(f"   FAIL  {name}   {detail}")


class FakeClock:
    """`time` as launch.py and ui_window.py see it: the monotonic clock is the test's."""

    def __init__(self):
        self.now = 80_000.0

    def monotonic(self):
        return self.now

    def __getattr__(self, name):
        return getattr(real_time, name)


class RunsUntilQuit:
    """A started process, as the tracker's liveness check sees one."""

    def __init__(self):
        self.code = None

    def poll(self):
        return self.code


class Said(logging.Handler):
    """What the tracker says about a gap it cut short."""

    def __init__(self):
        super().__init__(logging.DEBUG)
        self.lines = []

    def emit(self, record):
        message = record.getMessage()
        if "between two looks" in message:
            self.lines.append((record.levelno, message))


said = Said()
tracker_log = logging.getLogger("logic.launch")
tracker_log.setLevel(logging.DEBUG)
tracker_log.propagate = False
tracker_log.addHandler(said)

clock = FakeClock()
launch.time = clock
ui_window.time = clock  # before the window exists: it reads the clock as it is built


# -- the tracker alone ---------------------------------------------------------------------

def looks(gaps, games=1, quit_at_last=False):
    """A fresh tracker and `games` games started now, looked at after each gap in turn."""
    tracker = launch.PlaytimeTracker()
    running = [launch.RunningGame(key=f"p94 {n}", name=f"p94 game {n}", started=clock.monotonic(),
                                  process=RunsUntilQuit()) for n in range(games)]
    for game in running:
        tracker.add(game)
    ticks = []
    for i, gap in enumerate(gaps):
        clock.now += gap
        if quit_at_last and i == len(gaps) - 1:
            for game in running:
                game.process.code = 0
        ticks.append(tracker.poll())
    return ticks


def last_totals(ticks):
    return [tick.total_seconds for tick in ticks[-1]]


print("\n=== 1. the rule: three looks' worth, and only in rules.py ===")
check("rules.PLAYTIME_POLL_MS is the window's 3 s look", POLL_MS == 3000, POLL_MS)
check("rules.PLAYTIME_GAP_MAX_S is three looks' worth, 9 s",
      GAP_MAX is not None and POLL_MS is not None and GAP_MAX == 3 * POLL_MS // 1000 == CAP, GAP_MAX)
check("the window keeps no look interval of its own", not hasattr(ui_window, "POLL_INTERVAL_MS"))

print("\n=== 2. one gap, measured by the tracker alone ===")
said.lines.clear()
check("a gap just under the cap (8.9 s) counts in full: 3 + 3 + 8.9 -> 14 s",
      last_totals(looks([3, 3, 8.9])) == [14], last_totals(looks([3, 3, 8.9])))
check("a gap of exactly the cap counts in full: 3 + 3 + 9 -> 15 s", last_totals(looks([3, 3, 9])) == [15])
check("and neither is said in the log", not said.lines, said.lines)
check("a gap just over the cap (10.5 s) counts as the cap: -> 15 s, not 16",
      last_totals(looks([3, 3, 10.5])) == [15], last_totals(looks([3, 3, 10.5])))
said.lines.clear()
slept = looks([3, 3, 7200, 3])
check("a two-hour sleep between two looks counts 9 s: 3 + 3 + 9 + 3 -> 18 s",
      last_totals(slept) == [18], last_totals(slept))
check("it is said once, at info (so launcher.log holds it), naming the gap and what it counted",
      len(said.lines) == 1 and said.lines[0][0] == logging.INFO
      and "7200s" in said.lines[0][1] and f"counted as {CAP}s" in said.lines[0][1], said.lines)
check("a sleep before the first look, right after the start: an hour -> 9 s",
      last_totals(looks([3600])) == [9], last_totals(looks([3600])))
night = looks([3] * 10 + [86_400] + [3] * 10)
check("a day's hibernation in the middle: 30 + 9 + 30 -> 69 s", last_totals(night) == [69], last_totals(night))
woken = looks([3, 3, 3600], quit_at_last=True)
check("a game closed while the PC slept is found ended at the first look, with 9 s for the gap",
      [(t.finished, t.total_seconds) for t in woken[-1]] == [(True, 15)],
      [(t.finished, t.total_seconds) for t in woken[-1]])
two = looks([3, 3, 5400, 3], games=2)
check("two games open through one sleep: each counts it as 9 s", last_totals(two) == [18, 18], last_totals(two))
rough = random.Random(94)
gaps = [rough.uniform(2.9, 4.7) for _ in range(300)] + [12_345.6] + \
       [rough.uniform(2.9, 4.7) for _ in range(300)] + [600.25] + [rough.uniform(2.9, 4.7) for _ in range(50)]
ticks = looks(gaps)
added = sum(t.seconds for step in ticks for t in step)
check("the ticks' seconds still add up to the total, two sleeps and all (no fraction lost, Phase 53)",
      added == ticks[-1][0].total_seconds, (added, ticks[-1][0].total_seconds))
awake = sum(g for g in gaps if g <= CAP)
check("and the total is the time awake plus 9 s per sleep, within a second",
      abs(ticks[-1][0].total_seconds - (awake + 2 * CAP)) < 1.0, (ticks[-1][0].total_seconds, awake + 2 * CAP))


# -- through the window: the real banking into the library ---------------------------------

w = ui_window.MainWindow()
w.timer.stop()  # the looks are the test's, on the fake clock
# What follows a session but is not about time: the saves search (which walks the real disk),
# coming back to the front, a scan held back while the game ran.
w._queue_after_session = lambda tick: None
w._come_back_to_front = lambda: None
w._run_saves = lambda: None
w._run_wanted_scan = lambda: None

subject = next(e for e in w.entries if e.launch_kind == "exe")
KEY = subject.identity_key
played_before = 0


def stored():
    return int(w.overrides.get(KEY).get("playtime_seconds", 0))


def play(segments, interval):
    """One session: ("play", s) looked at every interval(), ("sleep", s) with no look at all.

    The game quits at the look after the last segment. Returns what to judge it by.
    """
    global played_before
    played_before += 1
    before = stored()
    start = clock.now
    slept = 0.0
    # A start time of its own, a day apart, so no two sessions of this suite share a second.
    started_at = (datetime.now().astimezone() - timedelta(days=played_before)).replace(microsecond=0)
    game = launch.RunningGame(key=KEY, name=subject.display_name, started=clock.monotonic(),
                              started_at=started_at, process=RunsUntilQuit())
    w.tracker.add(game)
    said.lines.clear()
    state = {"writes": 0, "over": 0.0, "under": 0.0, "biggest": 0, "last": before,
             "woke": False, "live": None, "finished": None}

    def look():
        w._poll_playtime()
        played = clock.now - start - slept  # the time the game was really being played
        if stored() != state["last"]:
            state["writes"] += 1
            state["biggest"] = max(state["biggest"], stored() - state["last"])
            state["last"] = stored()
            off = (state["last"] - before) - played
            state["over"], state["under"] = max(state["over"], off), min(state["under"], off)
        if state["woke"]:
            state["woke"] = False
            if KEY in w._live_sessions:  # what the tray's "Playing ... for" reads (Phase 92)
                state["live"] = (w._live_sessions[KEY][1], played)

    for kind, seconds in segments:
        if kind == "sleep":
            clock.now += seconds
            slept += seconds
            state["woke"] = True
            continue
        end = clock.now + seconds
        while clock.now < end:
            clock.now += interval()
            look()
    clock.now += interval()
    game.process.code = 0  # the game quits
    look()
    entries = sessions.load(w.overrides.get(KEY))
    mine = [s for s in entries if s.start == sessions.at_second(started_at)]
    return {
        "elapsed": clock.now - start,
        "played": clock.now - start - slept,
        "gained": stored() - before,
        "minutes": mine[0].minutes if mine else None,
        "said": list(said.lines),
        **state,
    }


def judge(label, r, sleeps):
    print(f"   (played {r['played']:.1f}s of {r['elapsed']:.1f}s; the total gained {r['gained']}s; "
          f"the session says {r['minutes']} min; {r['writes']} writes, the biggest {r['biggest']}s)")
    check(f"{label}: the total gained the time played, plus at most {CAP} s a sleep",
          r["played"] - 1 < r["gained"] <= r["played"] + sleeps * CAP, (r["gained"], round(r["played"], 1)))
    check(f"{label}: no write ever held the sleep: within {CAP} s of the time played at every one",
          r["over"] <= sleeps * CAP and r["under"] > -1, (round(r["over"], 2), round(r["under"], 2)))
    check(f"{label}: no single write added more than a minute's play and the cap",
          r["biggest"] <= rules.PLAYTIME_WRITE_INTERVAL_S + 5 + CAP, r["biggest"])
    check(f"{label}: the session in the list is the time counted, in whole minutes",
          r["minutes"] == r["gained"] // 60, (r["minutes"], r["gained"]))
    check(f"{label}: the log said it {sleeps} time(s)", len(r["said"]) == sleeps, r["said"])


print("\n=== 3. half an hour, two hours asleep, half an hour: the window and the library ===")
pace = random.Random(9494)
r = play([("play", 1800), ("sleep", 7200), ("play", 1800)], lambda: pace.uniform(2.9, 4.7))
judge("a sleep mid-session", r, sleeps=1)
check("right after waking, the tray's 'Playing ... for' was the time played, not the night",
      r["live"] is not None and r["live"][0] <= r["live"][1] + CAP, r["live"])

print("\n=== 4. two sleeps in one evening, the poll a hair either side of 3 s ===")
near = random.Random(4949)
r = play([("play", 1200), ("sleep", 2400), ("play", 900), ("sleep", 600), ("play", 600)],
         lambda: near.uniform(2.990, 3.015))
judge("two sleeps", r, sleeps=2)

print("\n=== 5. twenty minutes, then a night's hibernation; the game found closed on waking ===")
r = play([("play", 1200), ("sleep", 36_000)], lambda: 3.0)
judge("closed while hibernating", r, sleeps=1)
check("the session still ended, at the first look after waking", r["minutes"] is not None, r["minutes"])

print("\n=== 6. nothing sleeps: Phase 53's promise at three paces, the slowest just under the cap ===")
for label, interval in (("either side of 3 s", lambda rnd=random.Random(53): rnd.uniform(2.990, 3.015)),
                        ("irregular, 2.9-4.7 s", lambda rnd=random.Random(5353): rnd.uniform(2.9, 4.7)),
                        ("late every time, 8.9 s", lambda: 8.9)):
    r = play([("play", HOUR)], interval)
    print(f"   (played {r['played']:.1f}s; the total gained {r['gained']}s; the session {r['minutes']} min)")
    check(f"{label}: the total gained the time played, within 1 s",
          abs(r["gained"] - r["played"]) < 1.0, (r["gained"], round(r["played"], 2)))
    check(f"{label}: at every write the total was within 1 s of the time played",
          r["over"] < 1.0 and r["under"] > -1.0, (round(r["over"], 2), round(r["under"], 2)))
    check(f"{label}: the session in the list is that length in whole minutes",
          r["minutes"] == r["gained"] // 60, (r["minutes"], r["gained"]))
    check(f"{label}: nothing was cut, and the log said nothing", not r["said"], r["said"])
left = (w._unbanked, w._banked, w._live_sessions)
check("nothing is left over from any session", not any(left), left)

launch.time = real_time
ui_window.time = real_time
tracker_log.removeHandler(said)
tracker_log.propagate = True
w.close()
print("\n=== 7. the real library is exactly as it was found ===")
changed = box.finish()
check("overrides.json, config.json, catalog.json and the library are unchanged", not changed, changed)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
