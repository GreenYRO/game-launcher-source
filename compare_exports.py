"""Compare the friends' anonymous exports, for the thesis (Phase 81).

    .venv\\Scripts\\python.exe compare_exports.py

reads every export in data\\exports\\ (put the files the friends send there -- git ignores the
folder), writes the comparison into data\\exports\\comparison\\ (index.html and CSV files for
Excel) and opens the page in the browser. Other places can be named:

    .venv\\Scripts\\python.exe compare_exports.py FILE_OR_FOLDER ... --out FOLDER --no-open

Your own library is a participant like any other: make its export in Settings, Anonymous
export..., and save it into the same folder. Nothing is fetched and nothing is sent.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from logic import comparison
from logic import comparison_report
from shared import paths
from shared import rules


def main(argv: list[str] | None = None) -> int:
    default_in = paths.data_dir() / rules.COMPARISON_DIRNAME
    parser = argparse.ArgumentParser(description="Compare anonymous Game Launcher exports for the thesis.")
    parser.add_argument("sources", nargs="*", type=Path, help=f"export files or folders (default: {default_in})")
    parser.add_argument("--out", type=Path, help="where the report goes (default: <first folder>\\comparison)")
    parser.add_argument("--no-open", action="store_true", help="do not open the report in the browser")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    sources = args.sources or [default_in]
    if not args.sources:
        default_in.mkdir(parents=True, exist_ok=True)
    loaded = comparison.load(sources)
    for name, why in loaded.skipped:
        print(f"  left out  {name}: {why}")
    for old, new in loaded.replaced:
        print(f"  replaced  {old} by the newer {new}")
    if not loaded.participants:
        print(f"No export to compare in {', '.join(str(s) for s in sources)}.\n"
              "Put the files the friends sent there (and your own: Settings, Anonymous export...), then run this again.")
        return 1
    first_folder = next((s for s in sources if s.is_dir()), sources[0].parent)
    out = args.out or first_folder / rules.COMPARISON_REPORT_DIRNAME
    index = comparison_report.write(loaded, out)
    for p in loaded.participants:
        print(f"  {p.label}  {p.games} games, {comparison_report.hours(p.launcher_minutes)} h through the launcher, "
              f"{comparison_report.hours(p.steam_minutes)} h on Steam  ({p.file})")
    print(f"{len(loaded.participants)} participant(s) compared. The report: {index}")
    if not args.no_open:
        try:
            os.startfile(index)  # the default browser, as a double click would
        except OSError as exc:
            print(f"(could not open it: {exc}; open the file above by double-clicking it)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
