"""Resolving a game's name to a Steam appid, for the entries that have none.

Folder, GOG, Epic and Xbox entries arrive with a name and no appid, so nothing downstream
can fetch art or ask what kind of app they are. This module finds the appid; everything
after that is the pipeline that already exists.

The matching is deliberately timid. A missing cover is a small annoyance; the wrong game's
cover on your library is worse, because it looks like the launcher is confused about what
you have installed. So a candidate has to be near-identical to be accepted automatically,
short tool names are never auto-matched at all, and anything rejected simply keeps its
generated cover and can be resolved by hand from the right-click menu.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from shared import naming
from shared import rules
from shared.models import ArtCandidate
from web import steam_web

log = logging.getLogger(__name__)

SOURCE = "steam"
CACHE_FILE = "steam_search.json"
_PUNCTUATION = re.compile(r"[^\w\s]+")


class NameCache:
    """Resolved (and unresolved) name lookups, persisted between runs."""

    def __init__(self, cache_dir: str) -> None:
        self.cache_dir = cache_dir
        self.path = os.path.join(cache_dir, CACHE_FILE)
        self.records: dict[str, dict] = {}
        self._dirty = False
        self._load()

    def _load(self) -> None:
        if not os.path.isfile(self.path):
            return
        try:
            with open(self.path, encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("could not read %s (%s); starting empty", self.path, exc)
            return
        records = payload.get("names") if isinstance(payload, dict) else None
        if isinstance(records, dict):
            self.records = {k: v for k, v in records.items() if isinstance(v, dict)}
            log.info("name cache: %d record(s) loaded", len(self.records))

    def fresh(self, key: str) -> dict | None:
        record = self.records.get(key)
        if not record:
            return None
        try:
            fetched = datetime.fromisoformat(record.get("fetched_at", ""))
        except (TypeError, ValueError):
            return None
        days = (
            rules.STEAM_SEARCH_CACHE_DAYS
            if record.get("appid")
            else rules.STEAM_SEARCH_MISS_CACHE_DAYS
        )
        if datetime.now(timezone.utc) - fetched.astimezone(timezone.utc) > timedelta(days=days):
            return None
        return record

    def put(self, key: str, **values) -> None:
        record = self.records.setdefault(key, {})
        record.update(values)
        record["fetched_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self._dirty = True

    def save(self) -> None:
        if not self._dirty:
            return
        try:
            os.makedirs(self.cache_dir, exist_ok=True)
            temp = self.path + ".tmp"
            with open(temp, "w", encoding="utf-8") as handle:
                json.dump({"names": self.records}, handle, indent=2)
            os.replace(temp, self.path)
            self._dirty = False
        except OSError as exc:
            log.error("could not write %s: %s", self.path, exc)


# -- searching ----------------------------------------------------------------------------


def search(term: str, budget=None) -> list[ArtCandidate]:
    """Raw storefront search, scored against `term`. No gating -- the picker shows these."""
    if budget is not None and not budget.take():
        log.warning("search budget exhausted before %r", term)
        return []

    url = rules.STEAM_SEARCH_URL.format(term=urllib.parse.quote(term))
    blob = _get(url)
    if blob is None:
        return []
    try:
        payload = json.loads(blob.decode("utf-8", "replace"))
    except json.JSONDecodeError as exc:
        log.warning("search for %r returned unparseable JSON: %s", term, exc)
        return []

    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        log.info("search for %r returned no items", term)
        return []

    candidates = []
    for item in items[: rules.STEAM_SEARCH_MAX_CANDIDATES]:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        name = str(item.get("name") or "")
        candidates.append(
            ArtCandidate(
                source=SOURCE,
                ident=str(item["id"]),
                name=name,
                thumbnail=str(item.get("tiny_image") or ""),
                ratio=naming.similarity(name, term),
            )
        )
    # Steam's own ranking is not ours; the exact match is often not first.
    candidates.sort(key=lambda c: c.ratio, reverse=True)
    return candidates


def candidates_for(name: str, budget=None) -> list[ArtCandidate]:
    """Everything worth showing a human for this name, best first."""
    found = search(name, budget)
    if not found and rules.STEAM_SEARCH_PUNCTUATION_RETRY:
        stripped = _PUNCTUATION.sub(" ", name).strip()
        if stripped and stripped.casefold() != name.casefold():
            log.info("no results for %r; retrying as %r", name, stripped)
            found = search(stripped, budget)
    return found


def auto_match(name: str, detection: str, budget=None) -> ArtCandidate | None:
    """The candidate good enough to accept without asking, or None."""
    if detection in rules.STEAM_SEARCH_SKIP_DETECTIONS:
        log.info("not auto-matching %r: detection %r is too weak a signal", name, detection)
        return None

    for candidate in candidates_for(name, budget):
        if candidate.ratio >= rules.STEAM_SEARCH_MATCH_RATIO:
            log.info(
                "matched %r to %r (appid %s, ratio %.2f)",
                name,
                candidate.name,
                candidate.ident,
                candidate.ratio,
            )
            return candidate
        log.info(
            "best candidate for %r was %r at %.2f, below the %.2f gate",
            name,
            candidate.name,
            candidate.ratio,
            rules.STEAM_SEARCH_MATCH_RATIO,
        )
        break
    return None


# -- the discovery-time pass ------------------------------------------------------------------


def resolve_missing(entries: list, cache_dir: str) -> dict:
    """Give every appid-less entry an appid where one can be found, then fetch its art.

    Returns a small report so the caller can say what happened in plain language.
    """
    started = time.perf_counter()
    cache = NameCache(cache_dir)
    budget = steam_web.make_budget()
    report = {"matched": [], "unmatched": [], "skipped": []}
    newly_matched = []

    for entry in entries:
        if entry.extra.get("appid"):
            continue
        name = entry.display_name
        key = naming.normalize(name) or name.casefold()

        record = cache.fresh(key)
        if record is None:
            if entry.detection in rules.STEAM_SEARCH_SKIP_DETECTIONS:
                report["skipped"].append((name, "looks like a tool, not a game"))
                continue
            candidate = auto_match(name, entry.detection, budget)
            cache.put(
                key,
                appid=candidate.ident if candidate else "",
                matched_name=candidate.name if candidate else "",
                ratio=round(candidate.ratio, 3) if candidate else 0.0,
            )
            record = cache.records[key]

        appid = record.get("appid")
        if not appid:
            report["unmatched"].append((name, "no close enough match on Steam"))
            continue

        entry.extra["appid"] = appid
        entry.extra["appid_source"] = rules.APPID_SOURCE_SEARCH
        entry.extra["matched_name"] = record.get("matched_name", "")
        newly_matched.append(entry)
        report["matched"].append((name, record.get("matched_name", ""), appid))

    cache.save()
    if newly_matched:
        # Same pipeline as Steam's own entries: art, banner, and the game/tool type.
        steam_web.enrich(newly_matched, cache_dir, budget=budget)
        for entry in newly_matched:
            if entry.extra.get("artwork"):
                entry.icon_hint = entry.extra["artwork"]

    log.info(
        "storefront search: %d matched, %d unmatched, %d skipped in %.2fs",
        len(report["matched"]),
        len(report["unmatched"]),
        len(report["skipped"]),
        time.perf_counter() - started,
    )
    return report


def _get(url: str) -> bytes | None:
    request = urllib.request.Request(url, headers={"User-Agent": rules.STEAM_USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=rules.STEAM_WEB_TIMEOUT_SECONDS) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        log.info("search: %s -> HTTP %s", url, exc.code)
    except urllib.error.URLError as exc:
        log.warning("search: %s unreachable (%s)", url, exc.reason)
    except (TimeoutError, OSError, ValueError) as exc:
        log.warning("search: %s failed: %s: %s", url, type(exc).__name__, exc)
    return None

