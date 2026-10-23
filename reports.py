"""The reports from the command line (Phase 83): what the library database can say, one query at a time.

    reports.py --markdown              every report, its rows and the day, printed
    reports.py --markdown --sql        the same, each report followed by the SQL it is built from
    reports.py --markdown --out FILE   written to FILE instead
    reports.py --csv FOLDER            one CSV file per report, for Excel (semicolons, decimal commas)
    reports.py --library FILE ...      another library database than this PC's data\\library.db

The same eleven reports as the launcher's Reports tab (logic/reports.py, data_access/reports.py).
The file is opened read-only: nothing here can write it, and it may be read while the launcher is
open. **The Markdown is what refreshes the figures in docs/ANALIZA.md** -- when the thesis needs
them again, in June, run `reports.py --markdown --out <file>` and carry its numbers into each
report's "Răspunsul" there.

A database older than version 5 has no v_hours yet: start the launcher once and it upgrades it.
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

from data_access import reports as queries
from logic import reports
from shared import paths, rules


def _plain(value) -> str:
    """A value as Excel in Romanian reads it: decimal commas, no thousands mark, nothing for None."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "da" if value else "nu"
    if isinstance(value, float):
        return f"{value:.4f}".rstrip("0").rstrip(".").replace(".", ",")
    return str(value)


def write_csv(found: list, folder: Path) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    written = []
    for report in found:
        target = folder / f"{report.number}-{report.key}.csv"
        with target.open("w", encoding="utf-8-sig", newline="") as handle:
            out = csv.writer(handle, delimiter=";")
            out.writerow([f"{report.number}. {report.title}", report.question])
            for heading, columns, rows in reports.tables(report):
                out.writerow([])
                out.writerow([f"# {heading}"])
                out.writerow(columns)
                for row in rows:
                    out.writerow([_plain(v) for v in row])
        written.append(target)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="The library database's reports.")
    parser.add_argument("--markdown", action="store_true", help="print every report as Markdown")
    parser.add_argument("--sql", action="store_true", help="with --markdown: each report's SQL too")
    parser.add_argument("--out", type=Path, help="with --markdown: write it to this file")
    parser.add_argument("--csv", type=Path, metavar="FOLDER", help="write one CSV file per report into FOLDER")
    parser.add_argument("--library", type=Path, default=paths.data_dir() / rules.LIBRARY_DB_FILE,
                        help="the library database to read (default: this PC's)")
    args = parser.parse_args(argv)
    if not (args.markdown or args.csv):
        parser.print_help()
        return 2
    try:
        source = queries.open_read_only(args.library)
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"reports: {exc}", file=sys.stderr)
        return 1
    try:
        found = reports.build(source)
    finally:
        source.conn.close()
    if args.markdown:
        text = reports.markdown(found, datetime.now(), queries.QUERIES if args.sql else None)
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(text, encoding="utf-8")
            print(f"wrote {args.out}")
        else:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            print(text)
    if args.csv:
        for target in write_csv(found, args.csv):
            print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
