"""Phase 81: comparing the friends' anonymous exports, for the thesis.

Small exports made by hand, whose answers are worked out here independently -- which files are
read and which are left out, and why; the newest of a participant's files kept under the label of
their first; P1, P2, ... in order; each participant's measures; the shares of the hours, weekdays
and genres (a game's minutes split among its genres) adding up to 100; Jaccard between every pair;
the games played by more than one -- then the report: a page that parses, every chart with its
table, every name escaped (a game called <script> stays text), the file names only where it says
so, the CSV files readable as Excel in Romanian reads them; the command, from the command line
and with no export at all; and an export of the real library (from a copy) read back to the same
sums. On a throwaway copy of the data; nothing is fetched.
"""
import csv
import json
import subprocess
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import test_sandbox

box = test_sandbox.start()

from logic import analysis
from shared import rules

try:
    from logic import comparison, comparison_report
    import compare_exports
except ImportError:  # the code before this phase has none of them
    comparison = comparison_report = compare_exports = None

passed = failed = 0
SCRATCH = Path(tempfile.mkdtemp(prefix="phase81_"))
EVIL = "<script>alert('x')</script>"


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


def export(code, made_on, games=(), history=(), by_hour=None, by_weekday=None, accounts=1, paid=False):
    by_hour = by_hour or {}
    by_weekday = by_weekday or {}
    minutes = sum(by_hour.values())
    return {"format": rules.ANALYSIS_FORMAT, "version": 1, "app_version": "1.2.1", "made_on": made_on,
            "participant": code, "about": [], "never_in_it": [], "paid_included": paid, "left_out": {},
            "games": list(games),
            "sessions": {"count": 10 if minutes else 0, "minutes": minutes, "first_month": "2026-09",
                         "last_month": "2026-10", "by_month": {"2026-10": minutes},
                         "by_hour": {str(h): by_hour.get(h, 0) for h in range(24)},
                         "by_weekday": {d: by_weekday.get(d, 0) for d in rules.ANALYSIS_WEEKDAYS}},
            "steam": {"accounts": [{"account": chr(65 + n), "minutes": 1, "apps_with_time": 1, "last_read": "2026-10"}
                                   for n in range(accounts)], "history": list(history)}}


def game(appid, name, source="steam", installed=True, launcher=None, steam=None, genres=(), status=None, paid=None):
    item = {"source": source, "installed": installed, "name": name, "steam_appid": appid, "steam_type": "game",
            "genres": list(genres), "first_seen": "2026-08", "last_played": "2026-10", "status": status,
            "favorite": False, "launcher_minutes": launcher, "sessions": 1 if launcher else 0,
            "session_minutes": launcher or 0, "steam_minutes": steam, "steam_accounts": 1 if steam else 0}
    if paid is not None:
        item["paid"] = paid
    return item


def app(appid, name, minutes, genres=()):
    return {"steam_appid": appid, "name": name, "steam_type": "game", "genres": list(genres), "minutes": minutes,
            "accounts": 1, "last_played": "2026-10"}


A_OLD = export("p-aaaaaaaaaa", "2026-10-10", games=[game(10, "Ten", launcher=60)], history=[app(10, "Ten", 100)])
A = export("p-aaaaaaaaaa", "2026-10-15",
           games=[game(10, "Ten", launcher=120, steam=300, genres=["Action"], status="finished"),
                  game(None, None, source="folders", launcher=60),
                  game(20, "Twenty", installed=False, steam=600, genres=["Action", "Indie"])],
           history=[app(10, "Ten", 300, ["Action"]), app(20, "Twenty", 600, ["Action", "Indie"]), app(30, "Thirty", 0)],
           by_hour={20: 90, 21: 30}, by_weekday={"Fri": 120})
B = export("p-bbbbbbbbbb", "2026-10-11",
           games=[game(40, "Forty", source="gog", launcher=30, genres=["RPG"], paid=[{"amount_cents": 999,
                                                                                    "currency": "EUR", "store": "GOG",
                                                                                    "month": "2026-10"}])],
           history=[app(20, "Twenty", 60, ["Action", "Indie"]), app(30, EVIL, 40, ["Strategy"])],
           by_hour={9: 30}, by_weekday={"Mon": 30}, accounts=2, paid=True)
C = export("p-cccccccccc", "2026-10-12", games=[game(None, None, source="folders", installed=True)])
EXPORTS = SCRATCH / "exports"
EXPORTS.mkdir()
for name, data in (("Mihai-old.json", A_OLD), ("Mihai.json", A), ("b.json", B), ("c.json", C)):
    (EXPORTS / name).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
(EXPORTS / "not-json.json").write_text("{oops", encoding="utf-8")
(EXPORTS / "other.json").write_text(json.dumps({"format": "something-else"}), encoding="utf-8")
# One version past what this tool reads -- 3 since Phase 93 made 2 the current one.
(EXPORTS / "future.json").write_text(json.dumps(dict(B, version=rules.ANALYSIS_FORMAT_VERSION + 1,
                                                       participant="p-dddddddddd")), encoding="utf-8")
(EXPORTS / "nocode.json").write_text(json.dumps(dict(B, participant="Mihai")), encoding="utf-8")
(EXPORTS / "readme.txt").write_text("not an export", encoding="utf-8")

print("=== 1. which files are read ===")
loaded = people = None
try:
    loaded = comparison.load([EXPORTS])
    people = {p.label: p for p in loaded.participants}
    reasons = dict(loaded.skipped)
    check("three participants out of nine files (a .txt is not even looked at)", len(loaded.participants) == 3
          and "readme.txt" not in reasons, [p.file for p in loaded.participants])
    check("left out, each with its reason: not JSON, not an export, a newer format, no code",
          set(reasons) == {"not-json.json", "other.json", "future.json", "nocode.json"}
          and "could not be read" in reasons["not-json.json"] and "not an anonymous export" in reasons["other.json"]
          and "newer than this tool reads" in reasons["future.json"] and "no participant code" in reasons["nocode.json"],
          reasons)
    check("two files from one participant: the newer one kept", loaded.replaced == [("Mihai-old.json", "Mihai.json")]
          and people["P1"].file == "Mihai.json", loaded.replaced)
    check("P1, P2, P3 by the day of each one's first file -- the newer file keeps its sender P1",
          [people[k].code for k in ("P1", "P2", "P3")] == ["p-aaaaaaaaaa", "p-bbbbbbbbbb", "p-cccccccccc"])
except Exception as exc:
    unreached("1", exc)

print("\n=== 2. each participant's measures ===")
try:
    a, b, c = people["P1"], people["P2"], people["P3"]
    check("games, installed, by store; launcher and Steam minutes kept apart",
          (a.games, a.installed, a.by_source, a.launcher_minutes, a.steam_minutes) == (3, 2, {"steam": 1, "folders": 1},
                                                                                     180, 900), vars(a))
    check("Steam apps played (minutes above zero), accounts, nameless games, marks",
          (a.steam_apps_played, a.accounts, a.nameless, a.status) == (2, 1, 1, {"finished": 1}))
    check("played: the Steam numbers with any time, from the games and from Steam's history",
          a.played == {10, 20} and b.played == {20, 30, 40} and c.played == set(), (a.played, b.played))
    check("hours by the hour of day: 75% at 20:00 and 25% at 21:00, adding up to 100",
          round(a.hour_share[20], 6) == 75 and round(a.hour_share[21], 6) == 25
          and round(sum(a.hour_share.values()), 6) == 100)
    check("by weekday: all of A's on Friday; nobody's share is invented for C (no sessions: all 0)",
          a.weekday_share["Fri"] == 100 and sum(c.weekday_share.values()) == 0)
    check("genres by Steam time, a game's minutes split among its genres: Action 600 of 900, Indie 300",
          round(a.genre_share["Action"], 4) == round(100 * 600 / 900, 4)
          and round(a.genre_share["Indie"], 4) == round(100 * 300 / 900, 4)
          and round(sum(a.genre_share.values()), 6) == 100, a.genre_share)
    check("what was paid only for whoever included it: B, 9,99 EUR in one purchase",
          b.paid_included and b.paid == {"EUR": 999} and b.purchases == 1 and not a.paid_included and a.paid == {})
except Exception as exc:
    unreached("2", exc)

print("\n=== 3. between them ===")
try:
    sim = comparison.similarity(loaded.participants)
    check("Jaccard: A and B share 20 of {10, 20, 30, 40} -- 0,25 -- both ways round",
          sim[("P1", "P2")] == sim[("P2", "P1")] == 0.25)
    check("with someone who played nothing: 0 against A, none against itself",
          sim[("P1", "P3")] == 0.0 and sim[("P3", "P3")] is None and sim[("P1", "P1")] == 1.0)
    check("Jaccard of two empty sets is no number at all", comparison.jaccard(set(), set()) is None)
    common = comparison.common_games(loaded.participants)
    check("games played by more than one: only Twenty, by P1 and P2, 600 + 60 minutes",
          [(r["steam_appid"], r["participants"], r["minutes"]) for r in common] == [(20, ["P1", "P2"], 660)], common)
    check("the genres set side by side: the largest shares across everyone, never '(fără gen)'",
          comparison.genres_compared(loaded.participants)[:2] == ["Action", "Indie"]
          and comparison.NO_GENRE not in comparison.genres_compared(loaded.participants))
except Exception as exc:
    unreached("3", exc)

print("\n=== 4. the report ===")
try:
    out = SCRATCH / "report"
    index = comparison_report.write(loaded, out)
    page = index.read_text(encoding="utf-8")

    class Shape(HTMLParser):
        def __init__(self):
            super().__init__()
            self.tags, self.open = {}, []

        def handle_starttag(self, tag, attrs):
            self.tags[tag] = self.tags.get(tag, 0) + 1

    shape = Shape()
    shape.feed(page)
    check("a whole page, in Romanian, its style and script inline, nothing fetched",
          page.startswith("<!doctype html>") and 'lang="ro"' in page and "http://" not in page
          and "https://" not in page and "<script src" not in page)
    check(f"{shape.tags.get('svg', 0)} charts, each with its numbers as a table ({shape.tags.get('details', 0)})",
          shape.tags.get("svg", 0) >= 5 and shape.tags.get("details", 0) >= 5 and shape.tags.get("table", 0) >= 8, shape.tags)
    check("every participant on it", all(f">{label}<" in page for label in ("P1", "P2", "P3")))
    check("a game's name is text, never markup: <script> arrives escaped",
          EVIL not in page and "&lt;script&gt;" in page)
    files_at = page.index("<h2>Fișierele</h2>")
    check("the file names only in the files section, which warns about them",
          page.count("Mihai.json") == page[files_at:].count("Mihai.json") >= 1 and "nu copia" in page[files_at:])
    check("light and dark: the palette both ways, validated colours", rules.REPORT_SERIES_LIGHT[0] in page
          and rules.REPORT_SERIES_DARK[0] in page and "prefers-color-scheme:dark" in page)

    def rows(name):
        with open(out / name, encoding="utf-8-sig", newline="") as handle:
            return list(csv.reader(handle, delimiter=";"))

    expected = {"participants.csv": 3, "games.csv": 5, "steam_history.csv": 5, "hours.csv": 72, "weekdays.csv": 21,
                "similarity.csv": 3, "common_games.csv": 1}
    counts = {name: len(rows(name)) - 1 for name in expected}
    check("eight CSV files, each row where it should be", counts == expected
          and (out / "genres.csv").is_file(), counts)
    shares = {(r[0], r[1]): r[3] for r in rows("hours.csv")[1:]}
    check("for Excel in Romanian: semicolons between fields, a decimal comma, the UTF-8 mark",
          shares[("P1", "20")] == "75,0" and (out / "hours.csv").read_bytes().startswith(b"\xef\xbb\xbf"))
    check("the similarity CSV keeps three decimals", rows("similarity.csv")[1][2] == "0,250", rows("similarity.csv"))
except Exception as exc:
    unreached("4", exc)

print("\n=== 5. the command ===")
try:
    done = subprocess.run([sys.executable, str(PROJECT / "compare_exports.py"), str(EXPORTS), "--out",
                           str(SCRATCH / "cli"), "--no-open"], capture_output=True, text=True, encoding="utf-8",
                          cwd=PROJECT, timeout=120)
    check("from the command line: three compared, the left-out files named, the report written",
          done.returncode == 0 and "3 participant(s) compared" in done.stdout and "left out  future.json" in done.stdout
          and (SCRATCH / "cli" / "index.html").is_file(), done.stdout[-400:] + done.stderr[-400:])
    empty = SCRATCH / "empty"
    empty.mkdir()
    nothing = subprocess.run([sys.executable, str(PROJECT / "compare_exports.py"), str(empty), "--no-open"],
                             capture_output=True, text=True, encoding="utf-8", cwd=PROJECT, timeout=120)
    check("with no export: says where to put them, writes nothing, ends with 1",
          nothing.returncode == 1 and "No export to compare" in nothing.stdout and not (empty / "comparison").exists())
    code = compare_exports.main(["--no-open"])
    default = box.folder / rules.COMPARISON_DIRNAME
    check("with no folder named: the data folder's exports folder, made if missing", code == 1 and default.is_dir())
except Exception as exc:
    unreached("5", exc)

print("\n=== 6. the real library's export, read back ===")
try:
    store = test_sandbox.library()
    real = analysis.build(store, "p-0123456789")
    store.close()
    folder = SCRATCH / "real"
    folder.mkdir()
    (folder / "mine.json").write_text(json.dumps(real, ensure_ascii=False), encoding="utf-8")
    twin = json.loads(json.dumps(real))
    twin["participant"] = "p-9876543210"
    twin["steam"]["history"] = twin["steam"]["history"][::2]
    (folder / "twin.json").write_text(json.dumps(twin, ensure_ascii=False), encoding="utf-8")
    both = comparison.load([folder])
    me = next(p for p in both.participants if p.code == "p-0123456789")
    # Since Phase 83 Spacewar and Source SDK Base 2007 are set aside (rules.STEAM_NOT_GAMES): the export
    # keeps them, the comparison's Steam minutes leave them out and say how much that was.
    aside = sum(h["minutes"] or 0 for h in real["steam"]["history"] if h.get("steam_appid") in rules.STEAM_NOT_GAMES)
    check("its sums as the export's own: launcher minutes, Steam minutes (less what is set aside), games, sessions",
          me.launcher_minutes == sum(g["launcher_minutes"] or 0 for g in real["games"])
          and me.steam_minutes + me.set_aside_minutes == sum(h["minutes"] or 0 for h in real["steam"]["history"])
          and me.set_aside_minutes == aside
          and me.games == len(real["games"]) and me.sessions == real["sessions"]["count"],
          (me.steam_minutes, me.set_aside_minutes, aside))
    sim = comparison.similarity(both.participants)
    labels = [p.label for p in both.participants]
    value = sim[(labels[0], labels[1])]
    check(f"against a twin with half its Steam history: alike but not the same ({value:.2f})", value is not None
          and 0 < value < 1)
    page = comparison_report.page(both)
    check("its report is written, and no path of this PC is in it", ":\\" not in page and "\\Users" not in page)
except Exception as exc:
    unreached("6", exc)

print("\n=== 7. the layers ===")
try:
    layers = subprocess.run([sys.executable, str(PROJECT / "tests" / "check_layers.py")], cwd=PROJECT,
                            capture_output=True, text=True, timeout=120)
    check("compare_exports.py is an entry point; no import points up a layer", "upward imports: 0" in layers.stdout
          and "compare_exports" in (PROJECT / "tests" / "check_layers.py").read_text(encoding="utf-8"), layers.stdout[-200:])
    ignored = subprocess.run(["git", "check-ignore", "-q", "data/exports/friend.json"], cwd=PROJECT)
    check("the friends' files never reach git", ignored.returncode == 0)
    claude = (PROJECT / "CLAUDE.md").read_text(encoding="utf-8")
    plan = (PROJECT / "docs" / "DISTRIBUTIE.md").read_text(encoding="utf-8")
    check("CLAUDE.md and DISTRIBUTIE.md have it", "| 81 |" in claude and "compare_exports.py" in plan)
except Exception as exc:
    unreached("7", exc)

import shutil

shutil.rmtree(SCRATCH, ignore_errors=True)
print("\n=== 8. the real library is exactly as it was found ===")
changed = box.finish()
check("config.json and the library database are unchanged", not changed, changed)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
