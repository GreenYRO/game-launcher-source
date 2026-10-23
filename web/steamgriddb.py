"""SteamGridDB, for the games Steam's own store cannot match at all.

Optional and entirely off unless the user has pasted a key into Settings. Without one, every
function here returns nothing and the launcher behaves exactly as it did before.

This is the only endpoint in the project that involves a credential. The key is the user's
own, from their own free account; it is stored in config.json, sent only to
steamgriddb.com, and never logged -- `_redact` exists so a failed request can be reported
without putting the key in the log file.

Three answers are told apart (Phase 105): a match, a search that answered with nothing like the
name (a miss, cached), and no answer at all -- unreachable, refused, or asked to slow down (HTTP
429). The last is never cached as a miss. `strict=True` raises it (`NoAnswer`, `RateLimited`) for
the batch that fills missing covers; every other caller gets the empty answer it always had.
"""

from __future__ import annotations

import email.utils
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from shared import naming
from shared import rules
from shared.models import ROLE_BANNER, ROLE_COVER, ArtCandidate
from web import steam_web

log = logging.getLogger(__name__)

SOURCE = "steamgriddb"
ART_DIRNAME = "sgdb_art"


def configured(key: str) -> bool:
    return bool(key and key.strip())


def _redact(text: str, key: str) -> str:
    return text.replace(key, "<key>") if key else text


class RateLimited(Exception):
    """SteamGridDB answered HTTP 429, asking to slow down (Phase 105). `retry_after`: how many seconds its
    Retry-After header asked for, or None when it named none."""

    def __init__(self, retry_after: float | None) -> None:
        super().__init__("asked to slow down" + (f", Retry-After {retry_after:g} s" if retry_after is not None else ""))
        self.retry_after = retry_after


class NoAnswer(Exception):
    """No answer to go on (Phase 105): `why` is "key" (the key was refused), "unreachable" or "error"."""

    def __init__(self, why: str) -> None:
        super().__init__(why)
        self.why = why


def _retry_after(value, now: datetime | None = None) -> float | None:
    """A Retry-After header in seconds: a number of seconds, or an HTTP date to wait until. None when absent or
    unreadable -- never a guess."""
    if value is None or not str(value).strip():
        return None
    text = str(value).strip()
    try:
        return max(0.0, float(text))
    except ValueError:
        pass
    try:
        moment = email.utils.parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return max(0.0, (moment - (now or datetime.now(timezone.utc))).total_seconds())


def _request(url: str, key: str, strict: bool = False) -> dict | None:
    """One authenticated GET. Returns the decoded payload, or None on any failure -- with `strict`, the failure
    is raised instead: RateLimited for a 429, NoAnswer for everything else (Phase 105)."""
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": rules.STEAM_USER_AGENT,
            "Authorization": f"Bearer {key.strip()}",
        },
    )
    why = "error"
    try:
        with urllib.request.urlopen(request, timeout=rules.STEAM_WEB_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace")[:200]
        except Exception as read_exc:  # noqa: BLE001 -- the body only adds detail to the line below
            log.debug("SteamGridDB: the error's body could not be read (%s)", read_exc)
        if exc.code == 429:
            wait = _retry_after(exc.headers.get("Retry-After") if exc.headers is not None else None)
            log.warning("SteamGridDB asked us to slow down (HTTP 429%s)",
                        f", Retry-After {wait:g} s" if wait is not None else ", no Retry-After")
            if strict:
                raise RateLimited(wait) from None
            return None
        if exc.code == 401:
            log.error("SteamGridDB rejected the key: %s", detail or "unauthorised")
            why = "key"
        else:
            log.warning("SteamGridDB %s -> HTTP %s %s", _redact(url, key), exc.code, detail)
        if strict:
            raise NoAnswer(why) from None
        return None
    except urllib.error.URLError as exc:
        log.warning("SteamGridDB unreachable (%s)", exc.reason)
        if strict:
            raise NoAnswer("unreachable") from None
        return None
    except (TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        log.warning("SteamGridDB request failed: %s: %s", type(exc).__name__, exc)
        if strict:
            raise NoAnswer("unreachable" if isinstance(exc, (TimeoutError, OSError)) else "error") from None
        return None

    if not isinstance(payload, dict) or not payload.get("success"):
        log.warning("SteamGridDB returned an unsuccessful payload: %s", str(payload)[:160])
        if strict:
            raise NoAnswer("error")
        return None
    return payload


def check_key(key: str) -> tuple[bool, str]:
    """Is this key usable? Returns (ok, message) for showing in the settings dialog."""
    if not configured(key):
        return False, "No key set."
    try:
        _request(rules.SGDB_SEARCH_URL.format(term=urllib.parse.quote("portal")), key, strict=True)
    except RateLimited:
        return False, "SteamGridDB asked to slow down. Try again in a minute."
    except NoAnswer as exc:
        if exc.why == "unreachable":
            return False, "SteamGridDB could not be reached."
        return False, "That key was refused. Check it was copied whole."
    return True, "Key works."


def search(
    term: str, key: str, role: str = ROLE_COVER, with_thumbnails: bool = True, strict: bool = False
) -> list[ArtCandidate]:
    """Games matching this name, best first, each with a thumbnail for the wanted slot.

    The thumbnail comes from the endpoint that matches the slot -- grids for a cover,
    heroes for a banner -- so what you see in the picker is what you get. `strict`: no
    answer is raised, not returned as an empty list (Phase 105).
    """
    if not configured(term and key):
        return []

    payload = _request(rules.SGDB_SEARCH_URL.format(term=urllib.parse.quote(term)), key, strict)
    if payload is None:
        return []

    games = payload.get("data")
    if not isinstance(games, list):
        log.warning("SteamGridDB search returned no data list")
        return []

    scored = []
    for game in games:
        if not isinstance(game, dict) or game.get("id") is None:
            continue
        name = str(game.get("name") or "")
        scored.append((naming.similarity(name, term), str(game["id"]), name))
    scored.sort(reverse=True)

    candidates: list[ArtCandidate] = []
    for ratio, game_id, name in scored[: rules.SGDB_PICKER_CANDIDATES]:
        thumbnail = _first_for_role(game_id, key, role, thumb=True) if with_thumbnails else ""
        candidates.append(
            ArtCandidate(
                source=SOURCE,
                ident=game_id,
                name=name,
                thumbnail=thumbnail,
                ratio=ratio,
                role=role,
            )
        )
    log.info("SteamGridDB: %d %s candidate(s) for %r", len(candidates), role, term)
    return candidates


def _first_for_role(game_id: str, key: str, role: str, thumb: bool = False) -> str:
    url = rules.SGDB_HEROES_URL if role == ROLE_BANNER else rules.SGDB_GRIDS_URL
    return _first_url(_request(url.format(game_id=game_id), key), thumb)


def _first_url(payload: dict | None, thumb: bool) -> str:
    if payload is None:
        return ""
    items = payload.get("data")
    if not isinstance(items, list) or not items:
        return ""
    first = items[0]
    if not isinstance(first, dict):
        return ""
    return str(first.get("thumb" if thumb else "url") or "")


class _NameCache:
    """name -> SteamGridDB game id, so a page open does not re-search every time."""

    def __init__(self, cache_dir: str) -> None:
        self.path = os.path.join(cache_dir, rules.SGDB_NAME_CACHE_FILE)
        self.cache_dir = cache_dir
        self.records: dict[str, dict] = {}
        if os.path.isfile(self.path):
            try:
                with open(self.path, encoding="utf-8") as handle:
                    payload = json.load(handle)
                if isinstance(payload, dict) and isinstance(payload.get("names"), dict):
                    self.records = {
                        k: v for k, v in payload["names"].items() if isinstance(v, dict)
                    }
            except (OSError, json.JSONDecodeError) as exc:
                log.warning("could not read %s: %s", self.path, exc)

    def fresh(self, key: str) -> dict | None:
        record = self.records.get(key)
        if not record:
            return None
        try:
            fetched = datetime.fromisoformat(record.get("fetched_at", ""))
        except (TypeError, ValueError):
            return None
        days = (
            rules.SGDB_NAME_CACHE_DAYS
            if record.get("game_id")
            else rules.SGDB_NAME_MISS_CACHE_DAYS
        )
        if datetime.now(timezone.utc) - fetched.astimezone(timezone.utc) > timedelta(days=days):
            return None
        return record

    def put(self, key: str, game_id: str, matched: str) -> None:
        self.records[key] = {
            "game_id": game_id,
            "matched_name": matched,
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        try:
            os.makedirs(self.cache_dir, exist_ok=True)
            temp = self.path + ".tmp"
            with open(temp, "w", encoding="utf-8") as handle:
                json.dump({"names": self.records}, handle, indent=2)
            os.replace(temp, self.path)
        except OSError as exc:
            log.error("could not write %s: %s", self.path, exc)


def _name_key(name: str) -> str:
    return naming.normalize(name) or name.casefold()


def known_game_id(name: str, cache_dir: str) -> str | None:
    """What the name cache already says about this name, without a request (Phase 105): the game id, "" for a
    miss still fresh, or None when it has to be asked."""
    if not name:
        return None
    record = _NameCache(cache_dir).fresh(_name_key(name))
    return None if record is None else str(record.get("game_id") or "")


def resolve_game_id(name: str, key: str, cache_dir: str, strict: bool = False) -> str:
    """The SteamGridDB game id for this name, gated by the same similarity threshold.

    Cached, misses included, so a game that is simply not on SteamGridDB is not searched
    for on every page open. Only an answer is cached: a search that got none -- unreachable,
    refused, asked to slow down -- caches nothing (Phase 105), and with `strict` says so.
    """
    if not configured(key) or not name:
        return ""
    cache = _NameCache(cache_dir)
    cache_key = _name_key(name)

    record = cache.fresh(cache_key)
    if record is not None:
        return str(record.get("game_id") or "")

    try:
        candidates = search(name, key, with_thumbnails=False, strict=True)
    except (RateLimited, NoAnswer) as exc:
        log.info("SteamGridDB: %r not looked up (%s); nothing cached", name, exc)
        if strict:
            raise
        return ""
    best = ""
    matched = ""
    for candidate in candidates:
        if candidate.ratio >= rules.SGDB_MATCH_RATIO:
            best, matched = candidate.ident, candidate.name
            log.info("SteamGridDB: %r resolves to game %s (%r)", name, best, matched)
        else:
            log.info(
                "SteamGridDB: best for %r was %r at %.2f, below the %.2f gate",
                name,
                candidate.name,
                candidate.ratio,
                rules.SGDB_MATCH_RATIO,
            )
        break
    cache.put(cache_key, best, matched)
    return best


def hero_urls(game_id: str, key: str, limit: int) -> list[str]:
    """Several hero images for one game, for the banner cycle."""
    payload = _request(rules.SGDB_HEROES_URL.format(game_id=game_id), key)
    if payload is None:
        return []
    items = payload.get("data")
    if not isinstance(items, list):
        return []
    urls = []
    for item in items:
        if isinstance(item, dict) and item.get("url"):
            urls.append(str(item["url"]))
        if len(urls) >= limit:
            break
    log.info("SteamGridDB: %d hero(es) for game %s", len(urls), game_id)
    return urls


def iter_hero_paths(name: str, key: str, cache_dir: str, limit: int):
    """Download heroes for a game, yielding each local path as it lands.

    Blocking by design -- it is driven from a worker thread so a page open never waits.
    """
    game_id = resolve_game_id(name, key, cache_dir)
    if not game_id:
        return
    art_dir = os.path.join(cache_dir, ART_DIRNAME)
    for index, url in enumerate(hero_urls(game_id, key, limit)):
        target = os.path.join(art_dir, f"{game_id}_cycle{index}.jpg")
        path = _download(url, target)
        if path:
            yield path
        time.sleep(rules.SGDB_REQUEST_GAP_SECONDS)


def fetch_for(game_id: str, key: str, cache_dir: str, role: str) -> str:
    """Download one slot's image: a 600x900 grid for a cover, a hero for a banner."""
    if not configured(key):
        return ""

    art_dir = os.path.join(cache_dir, ART_DIRNAME)
    suffix = "_hero" if role == ROLE_BANNER else ""
    path = _download(
        _first_for_role(game_id, key, role), os.path.join(art_dir, f"{game_id}{suffix}.jpg")
    )
    if not path:
        log.info("SteamGridDB has no usable %s image for game %s", role, game_id)
    return path


def cover_url(game_id: str, key: str, strict: bool = False) -> str:
    """The first tall static grid of a SteamGridDB game, as `fetch_for` picks it for the cover -- "" when it has
    none (Phase 105). One request; with `strict`, no answer is raised."""
    if not configured(key) or not game_id:
        return ""
    return _first_url(_request(rules.SGDB_GRIDS_URL.format(game_id=game_id), key, strict), thumb=False)


def cover_on_disk(game_id: str, cache_dir: str) -> str:
    """The cover `fetch_for` would download for this game, when it is already in the cache -- "" otherwise."""
    target = os.path.join(cache_dir, ART_DIRNAME, f"{game_id}.jpg")
    return target if os.path.isfile(target) and os.path.getsize(target) >= rules.STEAM_ARTWORK_MIN_BYTES else ""


def download_cover(game_id: str, url: str, cache_dir: str) -> str:
    """The image at `url` into the file `fetch_for` keeps a game's cover in, size-checked: the path, or ""."""
    return _download(url, os.path.join(cache_dir, ART_DIRNAME, f"{game_id}.jpg"))


def fetch_art(game_id: str, key: str, cache_dir: str) -> tuple[str, str]:
    """Both slots at once."""
    return (
        fetch_for(game_id, key, cache_dir, ROLE_COVER),
        fetch_for(game_id, key, cache_dir, ROLE_BANNER),
    )


def _download(url: str, target: str) -> str:
    if not url:
        return ""
    if os.path.isfile(target) and os.path.getsize(target) >= rules.STEAM_ARTWORK_MIN_BYTES:
        return target
    blob = steam_web.fetch_image(url)  # plain GET, no key needed on the CDN
    if blob is None or len(blob) < rules.STEAM_ARTWORK_MIN_BYTES:
        log.info("SteamGridDB image %s was missing or too small to use", url)
        return ""
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as handle:
            handle.write(blob)
    except OSError as exc:
        log.error("could not write %s: %s", target, exc)
        return ""
    log.info("SteamGridDB: cached %d KB to %s", len(blob) // 1024, os.path.basename(target))
    return target
