"""Phase 1 CLI: scan the configured roots and print the catalog.

JSON goes to stdout, all logging goes to stderr, so `python scanner.py > catalog.json`
produces a clean file. Reading only -- nothing is written unless you pass --write-config.

It observes no prices (Phase 73): the weekly price observation belongs to the window's scans,
which hand their findings to the library database; this command writes no database at all.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

from data_access import config_io
from logic import discovery
from shared import paths
from shared import rules
from providers.folders import FolderProvider

log = logging.getLogger("scanner")

DEFAULT_CONFIG = paths.data_dir() / "config.json"


def load_config(path: Path) -> dict:
    """Read config.json if it is there; otherwise fall back to the defaults in rules.py."""
    defaults = {
        "roots": list(rules.DEFAULT_ROOTS),
        "max_depth": rules.MAX_DEPTH,
        "exclusions": [],
    }
    if not path.is_file():
        log.info("no config at %s; using defaults %s", path, defaults["roots"])
        return defaults
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.error("could not read %s (%s); using defaults", path, exc)
        return defaults
    if not isinstance(loaded, dict):
        log.error("%s is not a JSON object; using defaults", path)
        return defaults
    defaults.update(loaded)
    return defaults


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scanner.py", description="Scan folders for installed games."
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--roots", nargs="+", metavar="DIR", help="override the configured roots")
    parser.add_argument("--max-depth", type=int, help="override the depth cap")
    parser.add_argument("--indent", type=int, default=2)
    parser.add_argument(
        "--out",
        type=Path,
        metavar="FILE",
        help="write the JSON here instead of stdout. Prefer this on PowerShell, whose > "
        "redirect prepends a UTF-8 BOM that most JSON parsers reject.",
    )
    parser.add_argument(
        "--summary", action="store_true", help="print a readable table instead of JSON"
    )
    parser.add_argument("--progress", action="store_true", help="show directories as they scan")
    parser.add_argument(
        "--folders-only",
        action="store_true",
        help="scan the roots only, skipping Steam and other launcher manifests",
    )
    parser.add_argument("--write-config", action="store_true", help="save the config and exit")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("-q", "--quiet", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    level = logging.DEBUG if args.verbose else logging.ERROR if args.quiet else logging.INFO
    logging.basicConfig(
        stream=sys.stderr, level=level, format="%(levelname)-7s %(name)s: %(message)s"
    )
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    config = load_config(args.config)
    roots = args.roots or config["roots"]
    max_depth = args.max_depth or config.get("max_depth", rules.MAX_DEPTH)

    if args.write_config:
        # Merged, not rewritten: the GUI's settings dialog stores appearance preferences in
        # this same file, and rewriting it from the scan keys alone would erase them.
        payload = {
            "roots": roots,
            "max_depth": max_depth,
            "exclusions": config["exclusions"],
            "allow_network": config.get("allow_network", rules.ALLOW_NETWORK_DEFAULT),
            "enable_xbox": config.get("enable_xbox", rules.XBOX_ENABLED_DEFAULT),
        }
        if not config_io.save_config(payload, args.config):
            return 1
        log.info("wrote %s", args.config)
        return 0

    progress = _make_progress() if args.progress else None
    # Start from the whole config and layer the command-line overrides on top. Building a
    # fresh dict of just the scan keys silently dropped allow_network and enable_xbox, so
    # the CLI ignored both and produced a different catalogue than the GUI did.
    scan_config = dict(config)
    scan_config.update({"roots": roots, "max_depth": max_depth})
    providers: list = []

    started = time.perf_counter()
    entries = discovery.run_discovery(
        scan_config, progress=progress, providers_out=providers, folders_only=args.folders_only
    )
    elapsed = time.perf_counter() - started
    provider = next((p for p in providers if isinstance(p, FolderProvider)), None)
    if progress is not None:
        sys.stderr.write("\r" + " " * 100 + "\r")

    entries.sort(key=lambda e: e.display_name.casefold())

    if args.summary:
        print_summary(entries, provider, roots, elapsed)
        return 0

    catalog = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "roots": roots,
        "max_depth": max_depth,
        "entry_count": len(entries),
        "entries": [entry.to_dict() for entry in entries],
    }
    text = json.dumps(catalog, indent=args.indent, ensure_ascii=False)
    if args.out is None:
        sys.stdout.write(text + "\n")
        return 0

    try:
        args.out.write_text(text + "\n", encoding="utf-8", newline="\n")
    except OSError as exc:
        log.error("could not write %s: %s", args.out, exc)
        return 1
    log.info("wrote %d entries to %s", len(entries), args.out)
    return 0


def _make_progress():
    last = [0.0]

    def report(directory: str) -> None:
        now = time.perf_counter()
        if now - last[0] < 0.05:
            return
        last[0] = now
        sys.stderr.write("\r" + directory[:96].ljust(96))

    return report


def print_summary(entries, provider, roots, elapsed: float) -> None:
    width = max((len(e.display_name) for e in entries), default=10)
    print(f"{len(entries)} games in {', '.join(roots)} plus launcher manifests  ({elapsed:.1f}s)\n")
    header = f"{'NAME'.ljust(width)}  {'SOURCE':<8} {'HOW FOUND':<10} {'SIZE':>9}  LAUNCHES"
    print(header)
    print("-" * len(header))
    for entry in entries:
        target = entry.launch_target
        if target.lower().startswith(entry.install_dir.lower()):
            target = "..." + target[len(entry.install_dir) :]
        print(
            f"{entry.display_name.ljust(width)}  {entry.source:<8} {entry.detection:<10} "
            f"{_human_size(entry.size_on_disk):>9}  {target}"
        )

    ignored = getattr(provider, "empty_folders", [])
    if ignored:
        print(f"\nNo game found in {len(ignored)} folder(s):")
        for path, why in ignored:
            print(f"  {path}  ({why})")


def _human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.0f} {unit}" if unit in ("B", "KB") else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


if __name__ == "__main__":
    raise SystemExit(main())
