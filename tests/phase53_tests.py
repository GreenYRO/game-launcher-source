"""Phase 53: a game's total playtime agrees with its session, however the timer ticks.

Reported from use: a game's total read 15-20% under the sum of its sessions. The window's
3-second timer fires a hair either side of 3 s (measured: 2.993-3.012 s), each poll counted
`int(now - last_tick)` and moved `last_tick` to now, and the window added those whole
seconds up -- so every tick that came in just under 3 s counted 2, and the fraction of every
tick was dropped. The session's own length was always measured from its start, which is
why the two disagreed. Now the total is the total at the session's start plus the session's
elapsed time, measured from its start at every tick and at every once-a-minute write.

This suite plays one-hour sessions on a fake clock -- the real tracker, the real window, the
real banking into overrides.json -- with the poll arriving at irregular intervals, and
checks that the stored total and the session agree within a second at every write and at
the end. Runs on a throwaway copy of the data; nothing is started.
"""
import random
import sys
import time as real_time
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))  # the project folder, one up from tests/
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import test_sandbox

box = test_sandbox.start()

import logging

logging.basicConfig(level=logging.ERROR)

from PySide6.QtWidgets import QApplication

app = QApplication([])

from logic import launch, sessions
from presentation import ui_window

passed = failed = 0
HOUR = 3600.0
EXTRA = 500  # seconds something else adds to the game while it runs (a carry-over)


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
        self.now = 50_000.0

    def monotonic(self):
        return self.now

    def perf_counter(self):  # what the tracker read before this phase
        return self.now

    def __getattr__(self, name):
        return getattr(real_time, name)


class RunsUntilQuit:
    """A started process, as the tracker's liveness check sees one."""

    def __init__(self):
        self.code = None

    def poll(self):
        return self.code


clock = FakeClock()
launch.time = clock
ui_window.time = clock  # before the window exists: it reads the clock as it is built

w = ui_window.MainWindow()
w.timer.stop()  # the polls are the test's, on the fake clock
# What follows a session but is not about time: the saves search (which walks the real
# disk), coming back to the front, a scan held back while the game ran.
w._queue_after_session = lambda tick: None
w._come_back_to_front = lambda: None
w._run_saves = lambda: None
w._run_wanted_scan = lambda: None

seen = []
real_poll = w.tracker.poll


def watched_poll():
    ticks = real_poll()
    seen.extend(ticks)
    return ticks


w.tracker.poll = watched_poll
subject = next(e for e in w.entries if e.launch_kind == "exe")
KEY = subject.identity_key


def stored():
    return int(w.overrides.get(KEY).get("playtime_seconds", 0))


def play_an_hour(interval, extra_at=None):
    """One session of an hour, polled every interval(); returns what to judge it by."""
    before = stored()
    start = clock.now
    game = launch.RunningGame(key=KEY, name=subject.display_name, started=clock.monotonic(),
                              process=RunsUntilQuit())
    w.tracker.add(game)
    seen.clear()
    added = writes = 0
    worst = 0.0  # the furthest the total ever was from the time really played, at a write
    last = before
    while clock.now - start < HOUR:
        clock.now += interval()
        if extra_at is not None and not added and clock.now - start >= extra_at:
            w.overrides.update(KEY, playtime_seconds=stored() + EXTRA)
            added, last = EXTRA, last + EXTRA
        w._poll_playtime()
        if stored() != last:
            writes += 1
            last = stored()
            worst = max(worst, abs((last - before - added) - (clock.now - start)))
    clock.now += interval()
    game.process.code = 0  # the game quits
    w._poll_playtime()
    finished = [t for t in seen if t.finished]
    entries = sessions.load(w.overrides.get(KEY))
    mine = [s for s in entries if s.start == sessions.at_second(game.started_at)]
    return {
        "elapsed": clock.now - start,
        "gained": stored() - before - added,
        "kept": stored() - before,
        "session": finished[-1].total_seconds if finished else None,
        "minutes": mine[0].minutes if mine else None,
        "writes": writes,
        "worst": worst,
        "polls": len(seen),
    }


def judge(label, result, carried=False):
    r = result
    print(f"   ({r['polls']} polls; played {r['elapsed']:.1f}s, the session says {r['session']}s, "
          f"the total gained {r['gained']}s; worst at a write {r['worst']:.2f}s)")
    # A write waits for the first poll after 60 s, so polls every 3.4 s write every 61.2 s:
    # 58 in an hour, not 60.
    check(f"{label}: about once a minute the total was written", 55 <= r["writes"] <= 61, r["writes"])
    check(f"{label}: at every write, the total was within 1 s of the time played",
          r["worst"] < 1.0, f"{r['worst']:.2f}s off")
    check(f"{label}: at the end, the total and the session's length agree within 1 s",
          r["session"] is not None and abs(r["gained"] - r["session"]) <= 1,
          (r["gained"], r["session"]))
    check(f"{label}: and both are the time really played, within 1 s",
          abs(r["gained"] - r["elapsed"]) < 1.0, (r["gained"], round(r["elapsed"], 2)))
    check(f"{label}: the session in the list is that length in whole minutes",
          r["session"] is not None and r["minutes"] == r["session"] // 60,
          (r["minutes"], r["session"]))
    if carried:
        check(f"{label}: time added by something else while it ran is still there",
              r["kept"] - r["gained"] == EXTRA, (r["kept"], r["gained"]))


print("\n=== 1. an hour, the poll every 3.4 s ===")
judge("every 3.4 s", play_an_hour(lambda: 3.4))

print("\n=== 2. an hour like the real timer: a hair either side of 3 s (measured 2.993-3.012) ===")
near = random.Random(53)
judge("either side of 3 s", play_an_hour(lambda: near.uniform(2.990, 3.015)))

print("\n=== 3. an hour at irregular intervals, 2.9-4.7 s, and a carry-over while it runs ===")
rough = random.Random(5353)
judge("irregular", play_an_hour(lambda: rough.uniform(2.9, 4.7), extra_at=1234.5), carried=True)

print("\n=== 4. two sessions in a row: the second starts from nothing banked ===")
first = play_an_hour(lambda: 3.4)
second = play_an_hour(lambda: 3.1)
check("each session's total gain agrees with its own length within 1 s",
      abs(first["gained"] - first["session"]) <= 1 and abs(second["gained"] - second["session"]) <= 1,
      (first["gained"], first["session"], second["gained"], second["session"]))
left = (w._unbanked, getattr(w, "_banked", {}))  # getattr: so the code before the fix can be judged
check("nothing is left over from either session", not left[0] and not left[1], left)

launch.time = real_time
ui_window.time = real_time
w.tracker.poll = real_poll
w.close()
print("\n=== 5. the real library is exactly as it was found ===")
changed = box.finish()
check("overrides.json, config.json and catalog.json are byte for byte unchanged", not changed, changed)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
