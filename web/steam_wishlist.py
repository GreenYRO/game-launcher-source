"""A Steam account's public wishlist, from Steam's wishlist service (Phase 86).

The eighth sanctioned address: IWishlistService/GetWishlist on **api.steampowered.com**, the news
service's host (web/steam_news.py), another service. Anonymous, a read-only GET, no account and
no key; one request per account marked mine, and only what the user's own profile shows the world.

Read off Steam on 15 October 2026, one request for each of the four accounts marked mine, the
shapes this module reads:

* a public list -- HTTP 200 `{"response":{"items":[{"appid":296470,"priority":0,
  "date_added":1463944159}, ...]}}`, `date_added` in unix seconds, `priority` 0 for all 16 items;
* everything else -- HTTP 200 `{"response":{}}`. One of the three accounts that answered so is the
  one signed in to the client, whose store page shows "Wishlist 6": a private list answers
  exactly as an empty one would. So an answer with no items is **nothing to read**, never "the
  list is empty" -- the landing takes nothing off the list for it.

Nothing here writes to Steam, signs in, or changes a list. The answer is shaped and handed back;
logic/wishlist.py keeps it.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone

from shared import rules

log = logging.getLogger(__name__)

ITEMS, NOTHING, FAILED = "items", "nothing", "failed"


@dataclass(frozen=True)
class Answer:
    """One account's answer: a list read (ITEMS), nothing to read (NOTHING), or no answer (FAILED)."""
    state: str
    items: tuple = field(default_factory=tuple)  # dicts: appid, priority, date_added (UTC text or None)
    detail: str = ""


def _moment(seconds) -> str | None:
    if not isinstance(seconds, int) or isinstance(seconds, bool) or seconds <= 0:
        return None
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat(timespec="seconds")


def parse(body: bytes | str | None) -> Answer:
    """What Steam answered, shaped -- never raises."""
    if body is None:
        return Answer(FAILED, detail="no answer")
    try:
        payload = json.loads(body)
    except (ValueError, TypeError):
        return Answer(FAILED, detail="not JSON")
    response = payload.get("response") if isinstance(payload, dict) else None
    if not isinstance(response, dict):
        return Answer(FAILED, detail="no response object")
    raw = response.get("items")
    if raw is None or raw == []:
        return Answer(NOTHING, detail="no items: a private list or an empty one")
    if not isinstance(raw, list):
        return Answer(FAILED, detail="items is not a list")
    items, skipped = {}, 0
    for item in raw:
        appid = item.get("appid") if isinstance(item, dict) else None
        if not isinstance(appid, int) or isinstance(appid, bool) or appid <= 0:
            skipped += 1
            continue
        priority = item.get("priority")
        items[appid] = {"appid": appid,
                        "priority": priority if isinstance(priority, int) and not isinstance(priority, bool)
                        and priority >= 0 else None,
                        "date_added": _moment(item.get("date_added"))}
    if not items:
        # Items there but none readable: not a reading of the list -- nothing may be taken off it.
        return Answer(FAILED, detail=f"{skipped} item(s), none readable")
    if skipped:
        log.warning("steam wishlist: %d item(s) not readable, left out", skipped)
    return Answer(ITEMS, tuple(items.values()), f"{len(items)} item(s)")


def fetch(steam_id64: int) -> Answer:
    """One account's list, one GET. Never raises; a failure is an answer with no reading in it."""
    url = rules.STEAM_WISHLIST_URL.format(steamid=int(steam_id64))
    return parse(_get(url))


def _get(url: str) -> bytes | None:
    # The address names the account, so it is never logged: the log goes into diagnostics bundles.
    request = urllib.request.Request(url, headers={"User-Agent": rules.STEAM_USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=rules.STEAM_WEB_TIMEOUT_SECONDS) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        log.info("steam wishlist: HTTP %s", exc.code)
    except urllib.error.URLError as exc:
        log.warning("steam wishlist: unreachable (%s)", exc.reason)
    except (TimeoutError, OSError, ValueError) as exc:
        log.warning("steam wishlist: failed: %s: %s", type(exc).__name__, exc)
    return None
