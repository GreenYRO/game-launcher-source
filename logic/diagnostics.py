"""A diagnostics bundle for support (Phase 77): one zip a friend can send when something is wrong.

"It does not find my game" cannot be answered without seeing what the scan saw, so the bundle
holds exactly that, and the log, and nothing else of the user's:

  about.txt       the version, the build, Windows, Python, where the data folder is
  config.json     the settings as saved -- the SteamGridDB key taken out (it says whether one
                  is set, never what it is)
  scan.json       when the last scan ran, the folders it looks in (which are there, which are
                  not), and every game it found: source, ids, name, folder, what starts it, how
                  the exe was chosen, the exes it passed over, what the store's files said, and
                  the exe the user picked by hand, if any
  summary.txt     the same, as a table to read -- what scanner.py --summary shows
  launcher.log    and its two older copies

Paths are in it on purpose: a folder game is found by its path, and a wrong one is the usual
answer. Nothing else personal is: no sessions, no playtime, no notes or marks, no purchases or
prices, no Steam accounts. The log can name a Steam account in a rare line (a counter that went
down, a file that did not read); in the copy every account id and SteamID64 the library knows
becomes "steam-account-1", "-2", ..., and the key, should a line ever carry it, is removed too.

No Qt here: the Settings button asks where to save and calls write().
"""

from __future__ import annotations

import json
import logging
import os
import platform
import re
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from data_access import config_io
from logic import first_run
from shared import humanize
from shared import paths
from shared import rules
from shared import version

log = logging.getLogger(__name__)

KEY_SETTING = "steamgriddb_key"
KEY_REMOVED = "<SteamGridDB key removed>"


@dataclass
class Bundle:
    path: Path
    members: list[str] = field(default_factory=list)
    installs: int = 0
    scrubbed: int = 0  # Steam account ids and keys replaced in the log copies


def _log_files() -> list[Path]:
    base = paths.data_dir() / rules.LOG_FILENAME
    names = [base] + [base.with_name(f"{base.name}.{n}") for n in range(1, rules.LOG_BACKUP_COUNT + 1)]
    return [p for p in names if p.is_file()]


def _scrubber(store, key: str):
    """A function that takes the Steam accounts and the key out of a text, and counts them."""
    accounts = []
    if getattr(store, "keeps_steam_time", False):
        accounts = sorted(store.steam_accounts(), key=lambda a: a["account_id"])
    patterns = []
    for number, account in enumerate(accounts, 1):
        label = f"steam-account-{number}"
        for value in (account["steam_id64"], account["account_id"]):  # the longer first
            if value:
                patterns.append((re.compile(rf"(?<!\d){value}(?!\d)"), label))
    count = [0]

    def scrub(text: str) -> str:
        if key:
            count[0] += text.count(key)
            text = text.replace(key, KEY_REMOVED)
        for pattern, label in patterns:
            text, n = pattern.subn(label, text)
            count[0] += n
        return text

    return scrub, count


def _about(extra: dict) -> str:
    lines = [
        version.describe(),
        f"Windows: {platform.platform()}",
        f"Python: {platform.python_version()}",
        f"Running: {'an installed copy' if paths.FROZEN else 'from source'}",
        f"Data folder: {paths.data_dir()}",
        f"Bundle made: {datetime.now().astimezone().isoformat(timespec='seconds')}",
    ]
    lines += [f"{name}: {value}" for name, value in extra.items()]
    return "\n".join(lines) + "\n"


def _summary(installs: list[dict], roots: list[str], last_scan) -> str:
    width = max((len(i["display_name"]) for i in installs), default=10)
    lines = [f"{len(installs)} games; last scan {last_scan or 'never'}; game folders: "
             f"{', '.join(roots) if roots else 'none chosen'}", ""]
    header = f"{'NAME'.ljust(width)}  {'SOURCE':<8} {'HOW FOUND':<16} {'SIZE':>9}  LAUNCHES"
    lines += [header, "-" * len(header)]
    for i in installs:
        size = humanize.size(i["size_on_disk"]) if i.get("size_on_disk") else "?"
        target = i.get("chosen_exe") or i["launch_target"]
        lines.append(f"{i['display_name'].ljust(width)}  {i['source']:<8} {i['detection']:<16} {size:>9}  {target}"
                     + ("   (picked by hand)" if i.get("chosen_exe") else ""))
    return "\n".join(lines) + "\n"


def write(target: Path, store, *, about_extra: dict | None = None) -> Bundle:
    """Write the bundle to `target`, whole or not at all. Raises OSError if it cannot be written."""
    target = Path(target)
    saved = config_io.load_saved()
    key = str(saved.get(KEY_SETTING) or "")
    # Nor the code of the anonymous export (Phase 80): this bundle has paths, and the two must
    # not be joinable.
    settings = {k: v for k, v in saved.items() if k not in (KEY_SETTING, rules.ANALYSIS_ID_SETTING)}
    settings[f"{KEY_SETTING} (set?)"] = bool(key)
    roots = list(config_io.load_config().get("roots", rules.DEFAULT_ROOTS))
    here, gone = first_run.reachable(roots)
    last = store.last_scan_time()
    installs = []
    for entry in store.load_catalog():
        row = entry.to_dict()
        row["chosen_exe"] = (store.get(entry.identity_key) or {}).get("exe") or None
        installs.append(row)
    scan = {"last_scan": last.isoformat(timespec="seconds") if last else None,
            "game_folders": roots, "game_folders_there": here, "game_folders_missing": gone,
            "installs": installs}
    scrub, count = _scrubber(store, key)

    bundle = Bundle(path=target, installs=len(installs))
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(prefix=".diagnostics-", suffix=".zip", dir=target.parent)
    os.close(handle)
    try:
        with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            def put(name: str, text: str) -> None:
                archive.writestr(name, scrub(text))
                bundle.members.append(name)

            put("about.txt", _about(about_extra or {}))
            put("config.json", json.dumps(settings, indent=2, ensure_ascii=False) + "\n")
            put("scan.json", json.dumps(scan, indent=2, ensure_ascii=False) + "\n")
            put("summary.txt", _summary(installs, roots, scan["last_scan"]))
            for path in _log_files():
                put(path.name, path.read_text(encoding="utf-8", errors="replace"))
        os.replace(temp, target)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise
    bundle.scrubbed = count[0]
    log.info("diagnostics: %s written -- %d game(s), %s; %d account id(s) or key(s) taken out of the logs",
             target, len(installs), ", ".join(bundle.members), bundle.scrubbed)
    return bundle
