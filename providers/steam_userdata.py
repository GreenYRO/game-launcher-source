"""Steam's own playtime, read from its files (Phase 75): the accounts and their counters.

Two of the Steam client's files, read only, from the folder providers.steam finds in the
registry (a folder that is not found reads nothing -- never a guessed path):

  <Steam>\\config\\loginusers.vdf         the accounts that have logged in here, keyed by SteamID64,
                                          with AccountName, PersonaName, Timestamp (and on some
                                          clients MostRecent -- absent on this machine)
  <Steam>\\userdata\\<id>\\config\\localconfig.vdf
                                          per account: UserLocalConfigStore -> Software -> Valve
                                          -> Steam -> apps -> <appid> -> Playtime (lifetime
                                          minutes), Playtime2wks, PlaytimeDisconnected,
                                          LastPlayed (unix seconds)

Every key is looked up case-insensitively: on this machine three files say "apps" and one says
"Apps", and a case-sensitive read takes that account for one with nothing. The userdata folder
name is the account id, the low 32 bits of the SteamID64 -- one person, three spellings, joined
here (entity resolution).

A localconfig.vdf that does not parse -- Steam rewrites it while it runs, and a read caught
half way is cut off -- or has no UserLocalConfigStore at all is not a reading: nothing for that
account this time, a line in the log, never an error. Nothing here touches the network, the
database or another program's files beyond these two.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import vdf

from shared import rules

log = logging.getLogger(__name__)


def lookup(mapping, name: str):
    """A key, whatever its case; None if absent or `mapping` is not a mapping."""
    if not isinstance(mapping, dict):
        return None
    if name in mapping:
        return mapping[name]
    folded = name.casefold()
    for key, value in mapping.items():
        if str(key).casefold() == folded:
            return value
    return None


def _whole(value) -> int | None:
    text = str(value).strip() if value is not None else ""
    return int(text) if text.isdigit() else None


def _instant(seconds: float) -> str:
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat(timespec="seconds")


def _local(seconds: int) -> str | None:
    """Unix seconds as local time with its offset, as install.store_last_played is kept; 0 is none."""
    return datetime.fromtimestamp(seconds).astimezone().isoformat(timespec="seconds") if seconds > 0 else None


def login_users(steam_root: str) -> dict[int, dict]:
    """The accounts loginusers.vdf lists, by account id. {} when the file is missing or unreadable."""
    path = os.path.join(steam_root, *rules.STEAM_LOGIN_USERS_FILE)
    if not os.path.isfile(path):
        log.info("steam time: no %s", path)
        return {}
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            data = vdf.load(handle)
    except Exception as exc:  # noqa: BLE001 -- the vdf package raises SyntaxError and ValueError variants
        log.info("steam time: %s does not read (%s: %s); no names this time", path, type(exc).__name__, exc)
        return {}
    found: dict[int, dict] = {}
    for steam_id, info in (lookup(data, "users") or {}).items():
        sid = _whole(steam_id)
        if sid is None or sid <= rules.STEAM_ID64_BASE or not isinstance(info, dict):
            continue
        stamp = _whole(lookup(info, "Timestamp"))
        recent = _whole(lookup(info, "MostRecent"))
        found[sid - rules.STEAM_ID64_BASE] = {
            "steam_id64": sid,
            "account_name": lookup(info, "AccountName") or None,
            "persona": lookup(info, "PersonaName") or None,
            "most_recent": recent if recent in (0, 1) else None,
            "last_login": _instant(stamp) if stamp else None,
        }
    return found


def read_account(path: str, account_id: int, read_at: str) -> dict | None:
    """One account's localconfig.vdf as a reading -- None if it does not parse."""
    try:
        modified = os.path.getmtime(path)
        with open(path, encoding="utf-8", errors="replace") as handle:
            data = vdf.load(handle)
    except Exception as exc:  # noqa: BLE001 -- a file caught half written; see the module docstring
        log.info("steam time: account %s's localconfig.vdf does not read (%s: %s); skipped this time",
                 account_id, type(exc).__name__, exc)
        return None
    if lookup(data, rules.STEAM_LOCALCONFIG_APPS[0]) is None:
        log.info("steam time: account %s's localconfig.vdf holds no %s; skipped this time", account_id,
                 rules.STEAM_LOCALCONFIG_APPS[0])
        return None
    node = data
    for name in rules.STEAM_LOCALCONFIG_APPS:
        node = lookup(node, name)
        if node is None:
            break
    apps = node if isinstance(node, dict) else {}
    values = []
    in_file = with_time = shortcuts = 0
    for appid, block in apps.items():
        if str(appid).startswith("-") and str(appid)[1:].isdigit():
            shortcuts += 1  # a non-Steam game added to Steam: a negative id, no store app behind it
            continue
        if not str(appid).isdigit() or not isinstance(block, dict):
            continue
        in_file += 1
        found = {field: lookup(block, key) for field, key in rules.STEAM_TIME_KEYS.items()}
        if found["minutes_total"] is not None:
            with_time += 1
        if all(value is None for value in found.values()):
            continue  # a block with only cloud flags or badge data: nothing about time
        last = _whole(found["last_played"])
        values.append({
            "appid": int(appid),
            "minutes_total": _whole(found["minutes_total"]),
            "minutes_2wks": _whole(found["minutes_2wks"]),
            "minutes_disconnected": _whole(found["minutes_disconnected"]),
            "last_played": _local(last) if last is not None else None,
        })
    return {"account_id": account_id, "read_at": read_at, "file_modified": _instant(modified),
            "apps_in_file": in_file, "apps_with_time": with_time, "values": values,
            "shortcuts_skipped": shortcuts}


def localconfig_files(steam_root: str | None) -> list[str]:
    """Every account's localconfig.vdf on this PC -- for a look at when they were last written (Phase 92)."""
    folder = os.path.join(steam_root, rules.STEAM_USERDATA_DIRNAME) if steam_root else ""
    if not folder or not os.path.isdir(folder):
        return []
    found = []
    try:
        names = sorted(os.listdir(folder))
    except OSError as exc:
        log.info("steam time: %s could not be listed (%s)", folder, exc)
        return []
    for name in names:
        path = os.path.join(folder, name, *rules.STEAM_LOCALCONFIG_FILE)
        if name.isdigit() and int(name) > 0 and os.path.isfile(path):
            found.append(path)
    return found


def read_all(steam_root: str | None) -> dict:
    """Every account's reading, at one moment: {"accounts": [...], "reads": [...]}.

    An account is every userdata\\<id> folder with a localconfig.vdf that reads, named from
    loginusers.vdf when it lists it. No Steam folder, nothing.
    """
    if not steam_root or not os.path.isdir(steam_root):
        return {"accounts": [], "reads": []}
    read_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    users = login_users(steam_root)
    folder = os.path.join(steam_root, rules.STEAM_USERDATA_DIRNAME)
    accounts, reads = [], []
    for name in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
        if not name.isdigit() or int(name) <= 0:
            continue
        path = os.path.join(folder, name, *rules.STEAM_LOCALCONFIG_FILE)
        if not os.path.isfile(path):
            continue
        account_id = int(name)
        reading = read_account(path, account_id, read_at)
        if reading is None:
            continue
        known = users.get(account_id, {})
        accounts.append({"account_id": account_id,
                         "steam_id64": known.get("steam_id64") or account_id + rules.STEAM_ID64_BASE,
                         "account_name": known.get("account_name"), "persona": known.get("persona"),
                         "most_recent": known.get("most_recent"), "last_login": known.get("last_login")})
        reads.append(reading)
    log.info("steam time: %d account(s) read, %d value(s), at %s", len(reads),
             sum(len(r["values"]) for r in reads), read_at)
    return {"accounts": accounts, "reads": reads}
