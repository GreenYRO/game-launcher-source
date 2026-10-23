"""The one place this project touches the network.

Two things cannot be known from Steam's local files, and the user approved fetching both:

  * whether an installed app is a game, a demo, a tool, a soundtrack or a server binary,
    which lives in the store's appdetails endpoint; and
  * cover art for games whose art was never cached locally.

Everything is cached on disk with a long expiry, so a normal rescan makes no requests at
all. Requests are anonymous read-only GETs -- no account, no key, nothing about the user is
sent. Every failure mode here is non-fatal: if the network is down, or Steam throttles us,
or a response is malformed, the catalogue is simply built without the extra information.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

from shared import rules
from shared.models import ROLE_BANNER

log = logging.getLogger(__name__)

CACHE_FILE = "steam_web.json"
ART_DIRNAME = "steam_art"


class SteamWebCache:
    """appdetails results and downloaded artwork, persisted between runs."""

    def __init__(self, cache_dir: str) -> None:
        self.cache_dir = cache_dir
        self.art_dir = os.path.join(cache_dir, ART_DIRNAME)
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
            log.warning("could not read %s (%s); starting with an empty cache", self.path, exc)
            return
        records = payload.get("apps") if isinstance(payload, dict) else None
        if isinstance(records, dict):
            self.records = {k: v for k, v in records.items() if isinstance(v, dict)}
            log.info("steam web cache: %d record(s) loaded", len(self.records))

    def fresh(self, appid: str) -> dict | None:
        record = self.records.get(appid)
        if not record:
            return None
        stamp = record.get("fetched_at")
        try:
            fetched = datetime.fromisoformat(stamp) if stamp else None
        except (TypeError, ValueError):
            fetched = None
        if fetched is None:
            return None
        days = rules.STEAM_WEB_CACHE_DAYS if record.get("app_type") else rules.STEAM_WEB_MISS_CACHE_DAYS
        if datetime.now(timezone.utc) - fetched.astimezone(timezone.utc) > timedelta(days=days):
            log.debug("cache entry for %s is stale", appid)
            return None
        return record

    def put(self, appid: str, **values) -> None:
        record = self.records.setdefault(appid, {})
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
                json.dump({"apps": self.records}, handle, indent=2)
            os.replace(temp, self.path)
            self._dirty = False
        except OSError as exc:
            log.error("could not write %s: %s", self.path, exc)


class _Budget:
    """Caps requests per scan and keeps them politely spaced."""

    def __init__(self, limit: int) -> None:
        self.remaining = limit
        self._last = 0.0

    def take(self) -> bool:
        if self.remaining <= 0:
            return False
        self.remaining -= 1
        gap = time.monotonic() - self._last
        if gap < rules.STEAM_WEB_RATE_LIMIT_SECONDS:
            time.sleep(rules.STEAM_WEB_RATE_LIMIT_SECONDS - gap)
        self._last = time.monotonic()
        return True


def make_budget() -> "_Budget":
    """A request allowance that several stages of one scan can share."""
    return _Budget(rules.STEAM_WEB_MAX_REQUESTS_PER_SCAN)


def fetch_for(appid: str, cache_dir: str, role: str) -> str:
    """Download just one slot's artwork for an appid. Returns a path, or "" if absent.

    Split per role so that choosing a banner never overwrites the cover, and vice versa.
    """
    cache = SteamWebCache(cache_dir)
    budget = make_budget()
    record = cache.fresh(appid)
    if record is None:
        record = _fetch_details(appid, budget, cache_dir) or {}
        if record:
            cache.put(appid, **record)

    if role == ROLE_BANNER:
        path = _ensure_banner(appid, cache, budget)
    else:
        path = _ensure_artwork(appid, record, cache, budget)
    cache.save()
    return path


def fetch_art_for(appid: str, cache_dir: str) -> tuple[str, str]:
    """Both slots at once. Still used where both are wanted together."""
    return fetch_for(appid, cache_dir, ROLE_COVER), fetch_for(appid, cache_dir, ROLE_BANNER)


def enrich(entries: list, cache_dir: str, budget: "_Budget | None" = None) -> None:
    """Add app_type and, where missing, cover art. Modifies entries in place."""
    started = time.perf_counter()
    cache = SteamWebCache(cache_dir)
    budget = budget if budget is not None else make_budget()
    fetched = 0

    for entry in entries:
        appid = str(entry.extra.get("appid") or "")
        if not appid:
            continue

        record = cache.fresh(appid)
        # Records written before the widened call have no "has_details" key at all. Those
        # are re-fetched once, here, during a scan -- so opening a game's page never waits
        # on the network. Delisted apps get has_details=False and are not retried.
        outdated = record is not None and "has_details" not in record
        if record is None or outdated:
            fresh_record = _fetch_details(appid, budget, cache_dir)
            if fresh_record is not None:
                cache.put(appid, **fresh_record)
                record = cache.records[appid]
                fetched += 1
            elif record is None:
                record = cache.records.get(appid) or {}

        app_type = record.get("app_type")
        if app_type:
            entry.extra["app_type"] = app_type
            entry.extra["is_game"] = app_type in rules.STEAM_GAME_TYPES

        if not entry.extra.get("artwork"):
            art = _ensure_artwork(appid, record, cache, budget)
            if art:
                entry.icon_hint = art
                entry.extra["artwork"] = art
                entry.extra["artwork_source"] = "downloaded"

        if not entry.extra.get("banner"):
            banner = _ensure_banner(appid, cache, budget)
            if banner:
                entry.extra["banner"] = banner
                entry.extra["banner_source"] = "downloaded"

    fetched += _mend_currency(cache, budget)
    cache.save()
    log.info(
        "steam web: %d live request batch(es), %d cached, %.2fs",
        fetched,
        len(entries) - fetched,
        time.perf_counter() - started,
    )


def _mend_currency(cache: SteamWebCache, budget: _Budget) -> int:
    """Fetch again, once, a stored record priced in another country's currency (Phase 70).

    Until the address named the country, the store answered for wherever a request seemed to
    come from, and two records here came back in Polish zloty. A stored record whose price is
    not in rules.STEAM_STORE_CURRENCY, and which was not fetched for rules.STEAM_STORE_COUNTRY,
    is fetched again -- installed or not: the database keeps the record of a game gone too --
    and marked either way, so it is asked for once whatever the store answers. A store that no
    longer sells it there leaves its record as it was; a request with no answer is tried at the
    next scan. Records priced in euros, and free ones, are never fetched for this.
    """
    fetched = 0
    for appid in stored_detail_ids(cache.cache_dir):
        if (cache.records.get(appid) or {}).get("details_cc") == rules.STEAM_STORE_COUNTRY:
            continue
        currency = (load_details(cache.cache_dir, appid).get("price_overview") or {}).get("currency")
        if currency in (None, rules.STEAM_STORE_CURRENCY):
            continue
        found = _fetch_details(appid, budget, cache.cache_dir)
        if found is None:
            continue
        if found.get("has_details"):
            cache.put(appid, **found)
            fetched += 1
            log.info("steam web: appid %s fetched again for %s; it was priced in %s",
                     appid, rules.STEAM_STORE_COUNTRY, currency)
        else:
            cache.put(appid, details_cc=rules.STEAM_STORE_COUNTRY)
            log.info("steam web: appid %s has no store entry for %s; its record is kept as it was",
                     appid, rules.STEAM_STORE_COUNTRY)
    return fetched


# -- the Steam history's records (Phase 75) ------------------------------------------------


def fetch_records(appids: list, cache_dir: str, limit: int) -> int:
    """Fetch the full record of apps in the Steam history that the launcher has none of.

    The scan thread's, for the apps on the accounts marked mine, the most played first (the
    caller's order): at most `limit` requests, a second apart. An app whose cached summary is
    still fresh -- a record already fetched, or a miss cached (a delisted app answers "no store
    entry", and is asked again only when that miss goes stale) -- is not asked again. Writes the
    cache as any fetch does; the Steam projection after the scan puts the records in the
    database. Returns how many records were fetched.
    """
    if not appids:
        return 0
    cache = SteamWebCache(cache_dir)
    budget = _Budget(limit)
    fetched = asked = 0
    for appid in (str(a) for a in appids):
        if cache.fresh(appid) is not None and (has_details(cache_dir, appid)
                                               or cache.records[appid].get("has_details") is False):
            continue
        if not budget.take():
            break
        asked += 1
        found = _fetch_record(appid, cache_dir)
        if found is None:
            continue
        cache.put(appid, **found)
        fetched += 1 if found.get("has_details") else 0
    cache.save()
    log.info("steam history: %d record(s) asked for, %d fetched (at most %d a scan)", asked, fetched, limit)
    return fetched


def _fetch_record(appid: str, cache_dir: str) -> dict | None:
    """One appdetails request. The caller's allowance has already counted it and spaced it a
    second from the last; this one-request allowance only lets _fetch_details through."""
    return _fetch_details(appid, _Budget(1), cache_dir)


# -- the price series (Phase 73) -----------------------------------------------------------


def price_observation(appid: str, answer, observed_at: str, *, free_hint: bool = False) -> dict | None:
    """One observation of an app's price, from the store's answer for it -- None if it is not one.

    The three shapes the store gave on 11 October 2026 (one batched request: 730, 550, 1):
      {"success": true, "data": {"price_overview": {...}}}   priced
      {"success": true, "data": []}                           no price: free, or nothing on sale
      {"success": false}                                      not sold here (or no such app)
    With filters=price_overview the second shape cannot tell a free game from a playtest
    nobody sells, so the cached full record's is_free (`free_hint`) decides. A whole cached
    record reads the same way, as {"success": True, "data": record}: a price projected from
    the cache and a price fetched this week go through this one function and cannot drift.
    Anything else -- a price missing a figure, a figure that is not a whole number -- is no
    observation at all: None, and the caller logs it.
    """
    if not isinstance(answer, dict) or not isinstance(answer.get("success"), bool):
        return None
    row = {"appid": int(appid), "observed_at": observed_at, "kind": "unavailable", "currency": None,
           "initial_cents": None, "final_cents": None, "discount_percent": None}
    if not answer["success"]:
        return row
    data = answer.get("data")
    if isinstance(data, list) and not data:
        data = {}
    if not isinstance(data, dict):
        return None
    price = data.get("price_overview")
    if price is None:
        row["kind"] = "free" if (data.get("is_free") is True or free_hint) else "unavailable"
        return row
    if not isinstance(price, dict):
        return None
    currency = price.get("currency")
    figures = (price.get("initial"), price.get("final"), price.get("discount_percent"))
    if not (isinstance(currency, str) and len(currency) == 3
            and all(isinstance(v, int) and not isinstance(v, bool) and v >= 0 for v in figures)
            and figures[2] <= 100):
        return None
    row.update(kind="priced", currency=currency, initial_cents=figures[0], final_cents=figures[1],
               discount_percent=figures[2])
    return row


def observe_prices(appids: list, cache_dir: str, budget: "_Budget | None" = None) -> int:
    """Ask the store for each app's price now, a batch per request; write what it answered.

    The scan thread's half of the weekly observation (Phase 73): files only, never the
    database. At most rules.PRICE_REQUESTS_PER_SCAN requests, a second apart, the oldest-due
    apps first (the caller's order). A request that fails -- no answer, an unreadable body --
    is not an observation and writes nothing; an app missing from an answer, or answered in a
    shape the store does not give, is skipped and logged, and never costs the others. Every
    observation goes to the hand-off file for the window to put into the database. Returns
    how many were written.
    """
    budget = budget if budget is not None else _Budget(rules.PRICE_REQUESTS_PER_SCAN)
    written = 0
    for start in range(0, len(appids), rules.PRICE_BATCH_SIZE):
        batch = [str(appid) for appid in appids[start:start + rules.PRICE_BATCH_SIZE]]
        if not budget.take():
            log.info("steam prices: request allowance used; %d app(s) wait for the next scan",
                     len(appids) - start)
            break
        observed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        raw = _get(rules.STEAM_PRICES_URL.format(appids=",".join(batch)))
        if raw is None:
            continue
        try:
            payload = json.loads(raw.decode("utf-8", "replace"))
        except json.JSONDecodeError as exc:
            log.warning("steam prices: an unreadable answer for %d app(s), nothing recorded: %s", len(batch), exc)
            continue
        if not isinstance(payload, dict):
            log.warning("steam prices: an answer that is not a list of apps, nothing recorded")
            continue
        rows = []
        for appid in batch:
            row = price_observation(appid, payload.get(appid), observed_at,
                                    free_hint=load_details(cache_dir, appid).get("is_free") is True)
            if row is None:
                log.warning("steam prices: no usable answer for appid %s: %.200r", appid, payload.get(appid))
                continue
            if row["currency"] not in (None, rules.STEAM_STORE_CURRENCY):
                log.info("steam prices: appid %s is priced in %s, kept as given", appid, row["currency"])
            rows.append(row)
        if rows and write_price_handoff(cache_dir, price_handoff(cache_dir) + rows):
            written += len(rows)
    log.info("steam prices: %d app(s) due, %d observation(s) recorded for the window", len(appids), written)
    return written


def price_handoff_path(cache_dir: str) -> str:
    return os.path.join(cache_dir, rules.PRICE_HANDOFF_FILE)


def price_handoff(cache_dir: str) -> list[dict]:
    """The observations the scan thread wrote and the window has not put in the database yet."""
    path = price_handoff_path(cache_dir)
    if not os.path.isfile(path):
        return []
    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("could not read %s (%s); its observations are lost", path, exc)
        return []
    rows = payload.get("observations") if isinstance(payload, dict) else None
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def write_price_handoff(cache_dir: str, rows: list[dict]) -> bool:
    """Replace the hand-off with `rows`, atomically; an empty list removes the file."""
    path = price_handoff_path(cache_dir)
    try:
        if not rows:
            if os.path.isfile(path):
                os.remove(path)
            return True
        os.makedirs(cache_dir, exist_ok=True)
        temp = path + ".tmp"
        with open(temp, "w", encoding="utf-8") as handle:
            json.dump({"observations": rows}, handle, indent=1)
        os.replace(temp, path)
    except OSError as exc:
        log.error("could not write %s: %s", path, exc)
        return False
    return True


def details_path(cache_dir: str, appid: str) -> str:
    return os.path.join(cache_dir, rules.STEAM_DETAILS_DIRNAME, f"{appid}.json")


def stored_detail_ids(cache_dir: str) -> list[str]:
    """Every appid with a full record on disk, for the migration (Phase 67). Disk only."""
    folder = os.path.join(cache_dir, rules.STEAM_DETAILS_DIRNAME)
    if not os.path.isdir(folder):
        return []
    return sorted((name[:-5] for name in os.listdir(folder)
                   if name.endswith(".json") and name[:-5].isdigit()), key=int)


def details_fetched_at(cache_dir: str, records: dict[str, dict] | None = None) -> dict[str, str]:
    """When each stored full record was fetched, by appid (Phase 70). Disk only.

    The summary's `details_at`, written with the record; for a record fetched before it was
    written, the time its file was last written -- the fetch itself, since nothing else
    writes that file. Never the summary's `fetched_at`, which every cached picture moves on:
    Slow Roads' says 6 October, and its record was fetched on 30 September.
    """
    records = SteamWebCache(cache_dir).records if records is None else records
    moments: dict[str, str] = {}
    for appid in stored_detail_ids(cache_dir):
        stamp = (records.get(appid) or {}).get("details_at")
        if not stamp:
            try:
                written = os.path.getmtime(details_path(cache_dir, appid))
            except OSError as exc:
                log.warning("could not tell when the record for %s was fetched: %s", appid, exc)
                continue
            stamp = datetime.fromtimestamp(written, timezone.utc).isoformat(timespec="seconds")
        moments[appid] = stamp
    return moments


def has_details(cache_dir: str, appid: str) -> bool:
    return os.path.isfile(details_path(cache_dir, appid))


def load_details(cache_dir: str, appid: str) -> dict:
    """The stored full record for one game. Disk only -- never fetches."""
    path = details_path(cache_dir, appid)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as handle:
            record = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("could not read %s: %s", path, exc)
        return {}
    return record if isinstance(record, dict) else {}


def _store_details(cache_dir: str, appid: str, data: dict) -> bool:
    path = details_path(cache_dir, appid)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        temp = path + ".tmp"
        with open(temp, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False)
        os.replace(temp, path)
    except OSError as exc:
        log.error("could not write %s: %s", path, exc)
        return False
    return True


def _fetch_details(appid: str, budget: _Budget, cache_dir: str = "") -> dict | None:
    if not budget.take():
        log.warning("steam web: request budget exhausted, skipping appid %s", appid)
        return None

    url = rules.STEAM_APPDETAILS_URL.format(appid=appid)
    raw = _get(url)
    if raw is None:
        return None
    try:
        payload = json.loads(raw.decode("utf-8", "replace"))
    except json.JSONDecodeError as exc:
        log.warning("steam web: appid %s returned unparseable JSON: %s", appid, exc)
        return None

    node = payload.get(appid) if isinstance(payload, dict) else None
    if not isinstance(node, dict) or not node.get("success"):
        log.info("steam web: appid %s has no store entry (delisted or region-locked)", appid)
        return {"app_type": "", "header_image": "", "has_details": False}

    data = node.get("data") or {}
    app_type = str(data.get("type") or "").casefold()
    found = {
        "app_type": app_type,
        "header_image": str(data.get("header_image") or ""),
        "has_details": bool(cache_dir),
    }
    if cache_dir:
        # The whole record goes to its own file; only the two hot fields stay in the
        # shared cache that every scan reads -- and, since Phase 70, the moment the record
        # was fetched. The summary's own fetched_at moves whenever a picture is cached, so
        # it cannot say how old a record is.
        if _store_details(cache_dir, appid, data):
            found["details_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            found["details_cc"] = rules.STEAM_STORE_COUNTRY  # the country the address asked for
    log.info(
        "steam web: appid %s is type %r (%d fields stored)", appid, app_type or "unknown", len(data)
    )
    return found


def _ensure_artwork(appid: str, record: dict, cache: SteamWebCache, budget: _Budget) -> str:
    """Return a local artwork path, downloading it if needed. Empty string if unavailable."""
    existing = record.get("art_file")
    if existing and os.path.isfile(existing):
        return existing
    if record.get("art_missing"):
        return ""

    target = os.path.join(cache.art_dir, f"{appid}.jpg")
    if os.path.isfile(target) and os.path.getsize(target) >= rules.STEAM_ARTWORK_MIN_BYTES:
        cache.put(appid, art_file=target)
        return target

    # Portrait capsule first, to match the shape of the locally cached art. It serves a
    # ~1.6 KB placeholder for some newer titles, which the size check below rejects.
    candidates = [rules.STEAM_CAPSULE_URL.format(appid=appid)]
    if record.get("header_image"):
        candidates.append(record["header_image"])

    for url in candidates:
        if not budget.take():
            log.warning("steam web: request budget exhausted before artwork for %s", appid)
            return ""
        blob = _get(url)
        if blob is None:
            continue
        if len(blob) < rules.STEAM_ARTWORK_MIN_BYTES:
            log.debug("steam web: %s is %d bytes, a placeholder not art", url, len(blob))
            continue
        if _write(target, blob):
            log.info("steam web: cached %d KB of artwork for appid %s", len(blob) // 1024, appid)
            cache.put(appid, art_file=target)
            return target

    log.info("steam web: no usable artwork published for appid %s", appid)
    cache.put(appid, art_missing=True)
    return ""


def _ensure_banner(appid: str, cache: SteamWebCache, budget: _Budget) -> str:
    """Wide banner for the detail page. Same rules as the cover: cached, size-checked."""
    record = cache.records.get(appid, {})
    existing = record.get("banner_file")
    if existing and os.path.isfile(existing):
        return existing
    if record.get("banner_missing"):
        return ""

    target = os.path.join(cache.art_dir, f"{appid}_hero.jpg")
    if os.path.isfile(target) and os.path.getsize(target) >= rules.STEAM_ARTWORK_MIN_BYTES:
        cache.put(appid, banner_file=target)
        return target

    if not budget.take():
        log.warning("steam web: request budget exhausted before banner for %s", appid)
        return ""

    blob = _get(rules.STEAM_HERO_URL.format(appid=appid))
    if blob is not None and len(blob) >= rules.STEAM_ARTWORK_MIN_BYTES and _write(target, blob):
        log.info("steam web: cached %d KB banner for appid %s", len(blob) // 1024, appid)
        cache.put(appid, banner_file=target)
        return target

    log.info("steam web: no usable banner published for appid %s", appid)
    cache.put(appid, banner_missing=True)
    return ""


def fetch_image(url: str) -> bytes | None:
    """One image, for the cover picker's thumbnails. Returns None on any failure."""
    return _get(url) if url else None


def capsule_path(cache_dir: str, appid: int) -> str:
    """Where an app's portrait cover lives in the cache -- the same file a scan downloads for an
    installed game -- or "" when it is not there (or is a placeholder)."""
    target = os.path.join(cache_dir, ART_DIRNAME, f"{int(appid)}.jpg")
    return target if os.path.isfile(target) and os.path.getsize(target) >= rules.STEAM_ARTWORK_MIN_BYTES else ""


def fetch_capsule(appid: int, cache_dir: str) -> str:
    """The portrait cover of a wished game (Phase 87): the cached file, or one request to the
    appid-keyed CDN (endpoint 2), size-checked as every cover is, into the same cache. Writes
    only the image, never steam_web.json -- a scan may be writing that on its own thread.
    Returns the path, or "" when Steam publishes none or the request failed."""
    found = capsule_path(cache_dir, appid)
    if found:
        return found
    blob = _get(rules.STEAM_CAPSULE_URL.format(appid=int(appid)))
    if blob is None or len(blob) < rules.STEAM_ARTWORK_MIN_BYTES:
        return ""
    target = os.path.join(cache_dir, ART_DIRNAME, f"{int(appid)}.jpg")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    return target if _write(target, blob) else ""


def _get(url: str) -> bytes | None:
    request = urllib.request.Request(url, headers={"User-Agent": rules.STEAM_USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=rules.STEAM_WEB_TIMEOUT_SECONDS) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        log.info("steam web: %s -> HTTP %s", url, exc.code)
    except urllib.error.URLError as exc:
        log.warning("steam web: %s unreachable (%s)", url, exc.reason)
    except (TimeoutError, OSError, ValueError) as exc:
        log.warning("steam web: %s failed: %s: %s", url, type(exc).__name__, exc)
    return None


def _write(path: str, blob: bytes) -> bool:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(blob)
        return True
    except OSError as exc:
        log.error("could not write artwork %s: %s", path, exc)
        return False
