"""Recent update posts for a game, from Steam's news service.

**A different host from everything else in this project.** Every other Steam call goes to
store.steampowered.com; this one is api.steampowered.com. Still anonymous, still a
read-only GET, still no account and no key -- but it is a separate service and is listed
separately in CLAUDE.md.

Two things about the feed, both established by probing it rather than assuming:

* **Only the publisher's own announcements are wanted.** Each item carries a `feed_type`,
  and 1 with `feedname == "steam_community_announcements"` is the developer posting to
  their own game. Anything else is syndicated press -- Left 4 Dead 2's recent feed is 3
  publisher posts and 2 news articles, LEGO Batman's is 2 and 3. Patch notes only ever
  live in the publisher feed, and a magazine review is not an update.
* **The contents are BBCode, not HTML.** `[h1=x]`, `[list]`, `[*]`, `[b]`, `[url=...]`.
  Steam strips it for us *only when it truncates*: ask for `maxlength` and a long post
  comes back cut and clean, while a short one comes back raw. So the stripping here is not
  belt and braces, it is the only thing handling short posts.

A missing or unknown appid answers **HTTP 403**, not an empty list, so that is cached as a
miss like any other.
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from shared import rules

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class NewsItem:
    title: str
    url: str
    posted: datetime | None
    snippet: str


# -- turning BBCode into a sentence ----------------------------------------------------------

# Same shape as the HTML handling in gamedetails: anything that means "new line" becomes a
# single space, everything else disappears. Replacing every tag with a space instead turns
# "[b]Fixed[/b]," into "Fixed ," which is what that rule exists to prevent.
_BREAKS = re.compile(r"\[/?(?:br|p|list|olist|hr|h1|h2|h3|\*)(?:=[^\]]*)?\]", re.IGNORECASE)
_TAGS = re.compile(r"\[/?[a-z0-9]+(?:=[^\]]*)?\]", re.IGNORECASE)
_SPACE_BEFORE_PUNCTUATION = re.compile(r"\s+([,.;:!?])")
_WHITESPACE = re.compile(r"\s+")


def strip_bbcode(text: str) -> str:
    if not text:
        return ""
    cleaned = _BREAKS.sub(" ", text)
    cleaned = _TAGS.sub("", cleaned)
    cleaned = _WHITESPACE.sub(" ", cleaned)
    cleaned = _SPACE_BEFORE_PUNCTUATION.sub(r"\1", cleaned)
    return cleaned.strip()


def snippet(text: str, limit: int = rules.STEAM_NEWS_SNIPPET_CHARS) -> str:
    """A readable opening, cut on a word boundary rather than mid-syllable."""
    cleaned = strip_bbcode(text)
    if len(cleaned) <= limit:
        return cleaned
    cut = cleaned[:limit].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return cut + "..."


def is_publisher_post(item: dict) -> bool:
    return (
        item.get("feed_type") == rules.STEAM_NEWS_PUBLISHER_FEED_TYPE
        or str(item.get("feedname", "")) == rules.STEAM_NEWS_PUBLISHER_FEEDNAME
    )


def parse(payload: dict, limit: int = rules.STEAM_NEWS_SHOW) -> list[NewsItem]:
    raw = payload.get("appnews", {}).get("newsitems", []) if isinstance(payload, dict) else []
    items: list[NewsItem] = []
    for entry in raw:
        if not isinstance(entry, dict) or not is_publisher_post(entry):
            continue
        stamp = entry.get("date")
        posted = None
        if isinstance(stamp, int) and stamp > 0:
            try:
                posted = datetime.fromtimestamp(stamp).astimezone()
            except (OSError, OverflowError, ValueError) as exc:
                log.warning("unreadable news date %r: %s", stamp, exc)
        items.append(
            NewsItem(
                title=strip_bbcode(str(entry.get("title", ""))) or "Update",
                url=str(entry.get("url", "")),
                posted=posted,
                snippet=snippet(str(entry.get("contents", ""))),
            )
        )
        if len(items) >= limit:
            break
    return items


# -- the cache ---------------------------------------------------------------------------------


def _cache_path(cache_dir: str) -> str:
    return os.path.join(cache_dir, rules.STEAM_NEWS_CACHE_FILE)


def _load_cache(cache_dir: str) -> dict:
    path = _cache_path(cache_dir)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("could not read %s (%s); starting empty", path, exc)
        return {}
    apps = payload.get("apps") if isinstance(payload, dict) else None
    return apps if isinstance(apps, dict) else {}


def _save_cache(cache_dir: str, apps: dict) -> None:
    path = _cache_path(cache_dir)
    try:
        os.makedirs(cache_dir, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"apps": apps}, handle, indent=2)
    except OSError as exc:
        log.error("could not write %s: %s", path, exc)


def _fresh(record: dict) -> bool:
    stamp = record.get("fetched_at")
    try:
        fetched = datetime.fromisoformat(stamp) if stamp else None
    except (TypeError, ValueError):
        return False
    if fetched is None:
        return False
    # A miss is kept longer than a hit: a game with no announcements today is unlikely to
    # have any tomorrow, while a game that does post wants checking again soon.
    days = rules.STEAM_NEWS_CACHE_DAYS if record.get("items") else rules.STEAM_NEWS_MISS_CACHE_DAYS
    age = datetime.now(timezone.utc) - fetched.astimezone(timezone.utc)
    return age <= timedelta(days=days)


def _to_record(items: list[NewsItem]) -> dict:
    return {
        "fetched_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "items": [
            {
                "title": item.title,
                "url": item.url,
                "posted": item.posted.isoformat() if item.posted else "",
                "snippet": item.snippet,
            }
            for item in items
        ],
    }


def _from_record(record: dict) -> list[NewsItem]:
    items = []
    for raw in record.get("items", []):
        posted = None
        if raw.get("posted"):
            try:
                posted = datetime.fromisoformat(raw["posted"])
            except ValueError:
                posted = None
        items.append(
            NewsItem(
                title=raw.get("title", ""),
                url=raw.get("url", ""),
                posted=posted,
                snippet=raw.get("snippet", ""),
            )
        )
    return items


# -- the one request ------------------------------------------------------------------------------


def fetch_for(appid: str, cache_dir: str, allow_network: bool = True) -> list[NewsItem]:
    """Recent publisher posts for one game. Never raises; returns [] when there are none."""
    if not appid:
        return []
    apps = _load_cache(cache_dir)
    record = apps.get(str(appid))
    if isinstance(record, dict) and _fresh(record):
        log.debug("news for %s served from cache", appid)
        return _from_record(record)

    if not allow_network:
        log.info("network lookups are off; no news for %s", appid)
        return _from_record(record) if isinstance(record, dict) else []

    query = urllib.parse.urlencode(
        {
            "appid": appid,
            "count": rules.STEAM_NEWS_FETCH_COUNT,
            "maxlength": rules.STEAM_NEWS_MAXLENGTH,
            "format": "json",
        }
    )
    url = f"{rules.STEAM_NEWS_URL}?{query}"
    blob = _get(url)
    if blob is None:
        # Cache the miss too, so a game with no news is not asked about on every page open.
        apps[str(appid)] = _to_record([])
        _save_cache(cache_dir, apps)
        return []

    try:
        payload = json.loads(blob.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        log.warning("steam news for %s was not JSON: %s", appid, exc)
        return []

    items = parse(payload)
    apps[str(appid)] = _to_record(items)
    _save_cache(cache_dir, apps)
    log.info("steam news: %s -> %d publisher post(s)", appid, len(items))
    return items


def _get(url: str) -> bytes | None:
    request = urllib.request.Request(url, headers={"User-Agent": rules.STEAM_USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=rules.STEAM_WEB_TIMEOUT_SECONDS) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        # 403 is what an unknown appid answers -- not an empty list, and not a 404.
        log.info("steam news: %s -> HTTP %s", url, exc.code)
    except urllib.error.URLError as exc:
        log.warning("steam news: %s unreachable (%s)", url, exc.reason)
    except (TimeoutError, OSError, ValueError) as exc:
        log.warning("steam news: %s failed: %s: %s", url, type(exc).__name__, exc)
    return None
