"""A dry run: each game's stored playtime against the sum of its sessions. Reads, never writes.

    .venv\\Scripts\\python.exe tests\\playtime_report.py            (from the project folder)
    .venv\\Scripts\\python.exe tests\\playtime_report.py FILE       (another overrides.json,
                                                                   e.g. one in data\\backups)

Until Phase 53 every 3-second poll dropped the fraction of a second it had measured, so a
stored total reads about 16% under the time really played, while each session's length was
measured from its start and is right. This lists, per game, the stored total, the sum of
its sessions, and the difference, so a repair rule can be chosen from the real numbers. It
changes nothing: the file is read once, in binary, and its fingerprint is compared after.

Not every difference is the drift, and the notes column says which:
- sessions are kept in whole minutes, rounded down, and one under a minute is not kept at
  all -- so the sum of sessions itself reads up to a minute low per session;
- session history only began with Phase 20 (14 August 2026): a game played before that has
  time in its total that no session accounts for;
- a game carried over from an earlier install (Phase 36) holds that install's time and
  sessions too.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # the project folder
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from logic import sessions
from shared import paths, rules

# The day Phase 20 shipped: no session was recorded before it (git: f0ab705, 2026-08-14).
SESSIONS_BEGAN = datetime(2026, 8, 14).astimezone()


def span(seconds: int) -> str:
    sign = "-" if seconds < 0 else ""
    seconds = abs(seconds)
    return f"{sign}{seconds // 3600}h {seconds % 3600 // 60:02d}m {seconds % 60:02d}s"


def notes(record: dict, entries: list, stored: int) -> str:
    said = []
    first_seen = record.get("first_seen")
    try:
        seen = datetime.fromisoformat(first_seen) if first_seen else None
    except ValueError:
        seen = None
    if seen is not None and seen.tzinfo is None:
        seen = seen.astimezone()
    if seen is not None and seen < SESSIONS_BEGAN:
        said.append("known before session history began (14 Aug)")
    if record.get("earlier_keys"):
        said.append("carried over from an earlier install")
    if stored and not entries:
        said.append("time but no sessions")
    return "; ".join(said)


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else paths.data_dir() / "overrides.json"
    raw = path.read_bytes()
    fingerprint = hashlib.sha256(raw).hexdigest()
    games = json.loads(raw.decode("utf-8-sig")).get("games", {})

    rows = []
    for key, record in games.items():
        stored = int(record.get("playtime_seconds", 0) or 0)
        entries = sessions.load(record)
        if not stored and not entries:
            continue
        summed = sum(entry.minutes for entry in entries) * 60
        name = record.get("known_as") or record.get("name") or Path(key).name or key
        rows.append((name, stored, len(entries), summed, stored - summed,
                     notes(record, entries, stored)))
    rows.sort(key=lambda row: -row[3])

    print(f"{path}  ({len(games)} records, {len(rows)} with time or sessions)\n")
    head = f"{'game':<34} {'stored':>13} {'n':>4} {'sum of sessions':>16} {'difference':>14} {'stored/sum':>10}  notes"
    print(head)
    print("-" * len(head))
    for name, stored, count, summed, diff, note in rows:
        ratio = f"{100 * stored / summed:.1f}%" if summed else "-"
        print(f"{name[:34]:<34} {span(stored):>13} {count:>4} {span(summed):>16} "
              f"{span(diff):>14} {ratio:>10}  {note}")
    total_stored = sum(row[1] for row in rows)
    total_summed = sum(row[3] for row in rows)
    print("-" * len(head))
    print(f"{'all games':<34} {span(total_stored):>13} {sum(row[2] for row in rows):>4} "
          f"{span(total_summed):>16} {span(total_stored - total_summed):>14} "
          f"{(f'{100 * total_stored / total_summed:.1f}%' if total_summed else '-'):>10}")
    clean = [row for row in rows if row[3] and not row[5]]
    if clean:
        print(f"\nGames with sessions and no note ({len(clean)}): stored is "
              f"{100 * sum(r[1] for r in clean) / sum(r[3] for r in clean):.1f}% of their sessions. "
              "Each session reads up to a minute low (whole minutes, rounded down).")

    unchanged = hashlib.sha256(path.read_bytes()).hexdigest() == fingerprint
    print(f"\nnothing written: {path.name} is {'unchanged' if unchanged else 'CHANGED BY SOMETHING ELSE'} "
          f"(sha256 {fingerprint[:12]}...)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
