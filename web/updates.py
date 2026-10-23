"""Is there a newer Game Launcher? -- asked of GitHub, once a day, by an installed copy (Phase 79).

**The seventh endpoint, and a third host**: api.github.com, the releases of the public
repository that holds only the installers (`rules.UPDATE_REPOSITORY`; the code's own repository
is private). Anonymous, a read-only GET, no account and no key -- GitHub sees the connection's
address, as Steam does, and nothing else is sent.

Read off GitHub on 11 October 2026 before a line was written (tests/fixtures): the newest
release answers 200 with `tag_name` ("v4.1"), `name`, `draft`, `prerelease` and `published_at`;
a repository with no release yet answers **404** {"message": "Not Found"}, which is an answer --
"nothing newer" -- not a failure. GitHub's `latest` never returns a draft or a pre-release; a
release marked as either is refused here all the same.

It only ever tells. Nothing is downloaded or run: the window says a newer version is out, and
Settings opens the release page (`rules.UPDATE_PAGE_URL`, fixed) in the browser, where the new
Setup.exe is run over the old one like any update. No address is ever taken from the answer.

When it asks (`should_check`): an installed copy only -- one run from source, the developer's,
is always the newest -- with "Allow network lookups" on. How often (`check`): an answer is good
for `UPDATE_CHECK_HOURS`; a question nobody answered is asked again after `UPDATE_RETRY_HOURS`.
The last answer is kept in cache/update_check.json, which Settings reads -- since Phase 106 with the release's
notes (its `body`), which Settings shows as "See what's new in ..." before the update: the same answer, no more asked.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from shared import paths
from shared import rules
from shared import version

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Answer:
    """What GitHub last said, and when it was asked."""

    checked_at: datetime  # UTC
    reached: bool  # GitHub answered: a release, or "no release yet"
    latest: str | None = None  # the newest release's version, "1.3.0"; None when there is none
    published: datetime | None = None
    title: str = ""
    notes: str = ""  # the release's notes, its page's body as GitHub gave it (Phase 106): Settings shows them

    @property
    def newer(self) -> bool:
        """Newer than the copy running now -- so an answer kept from before an update says no."""
        return self.latest is not None and version.is_newer(self.latest)

    def to_dict(self) -> dict:
        return {"checked_at": self.checked_at.isoformat(timespec="seconds"), "reached": self.reached,
                "latest": self.latest, "title": self.title,
                "published": self.published.isoformat(timespec="seconds") if self.published else None,
                "notes": self.notes}

    @classmethod
    def from_dict(cls, data: dict) -> Answer | None:
        try:
            checked = _moment(data["checked_at"])
            if checked is None:
                return None
            latest = data.get("latest")
            return cls(checked, bool(data.get("reached")),
                       version_text(latest) if latest else None, _moment(data.get("published")),
                       str(data.get("title") or ""), str(data.get("notes") or ""))
        except (KeyError, TypeError, ValueError) as exc:
            log.warning("update check: the kept answer is unreadable (%s)", exc)
            return None


def version_text(tag: str) -> str | None:
    """"v1.3.0" -> "1.3.0"; "v4.1" -> "4.1.0"; anything that is not a version -> None."""
    numbers = version.parse(tag)
    return ".".join(str(n) for n in numbers) if numbers else None


def _moment(text) -> datetime | None:
    if not text:
        return None
    try:
        value = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def read(payload, checked_at: datetime) -> Answer:
    """GitHub's answer for the newest release, as an Answer. Reached either way: GitHub spoke."""
    if not isinstance(payload, dict):
        log.warning("update check: the answer is not an object")
        return Answer(checked_at, reached=False)
    if payload.get("draft") or payload.get("prerelease"):
        log.warning("update check: the newest release is a draft or a pre-release; not offered")
        return Answer(checked_at, reached=True)
    tag = str(payload.get("tag_name") or "")
    latest = version_text(tag)
    if latest is None:
        log.warning("update check: the newest release's tag %r is not a version; not offered", tag)
    return Answer(checked_at, reached=True, latest=latest, published=_moment(payload.get("published_at")),
                  title=str(payload.get("name") or tag), notes=str(payload.get("body") or ""))


def _get(url: str) -> tuple[int | None, bytes | None]:
    """One GET: (HTTP status, body). (404, body) is GitHub's "no release yet"; (None, None) is no answer."""
    request = urllib.request.Request(url, headers={"User-Agent": rules.UPDATE_USER_AGENT,
                                                   "Accept": rules.UPDATE_ACCEPT,
                                                   "X-GitHub-Api-Version": rules.UPDATE_API_VERSION})
    try:
        with urllib.request.urlopen(request, timeout=rules.UPDATE_TIMEOUT_SECONDS) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        # 404: no release published yet. 403 or 429: GitHub's limit for this connection.
        log.info("update check: %s -> HTTP %s", url, exc.code)
        return exc.code, None
    except urllib.error.URLError as exc:
        log.warning("update check: %s unreachable (%s)", url, exc.reason)
    except (TimeoutError, OSError, ValueError) as exc:
        log.warning("update check: %s failed: %s: %s", url, type(exc).__name__, exc)
    return None, None


def fetch(now: datetime | None = None) -> Answer:
    """Ask GitHub, once, for the newest release."""
    checked_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    status, body = _get(rules.UPDATE_LATEST_URL)
    if status == 404:
        log.info("update check: no release published yet")
        return Answer(checked_at, reached=True)
    if status != 200 or body is None:
        return Answer(checked_at, reached=False)
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        log.warning("update check: the answer was not JSON: %s", exc)
        return Answer(checked_at, reached=False)
    return read(payload, checked_at)


# -- the kept answer -------------------------------------------------------------------------


def _cache_path(cache_dir) -> str:
    return os.path.join(str(cache_dir), rules.UPDATE_CACHE_FILE)


def last(cache_dir=None) -> Answer | None:
    """The answer kept from the last check -- None if there has been none."""
    path = _cache_path(cache_dir if cache_dir is not None else paths.cache_dir())
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("update check: could not read %s (%s)", path, exc)
        return None
    return Answer.from_dict(data) if isinstance(data, dict) else None


def _keep(cache_dir, answer: Answer) -> None:
    path = _cache_path(cache_dir)
    try:
        os.makedirs(str(cache_dir), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(answer.to_dict(), handle, indent=2)
    except OSError as exc:
        log.error("update check: could not write %s: %s", path, exc)


def due(answer: Answer | None, now: datetime) -> bool:
    """Time to ask again? A day after an answer, a few hours after a question nobody answered."""
    if answer is None:
        return True
    wait = timedelta(hours=rules.UPDATE_CHECK_HOURS if answer.reached else rules.UPDATE_RETRY_HOURS)
    return now - answer.checked_at >= wait


def should_check(config: dict) -> tuple[bool, str]:
    """May this copy ask at all? (yes, "") -- or (no, why), for the log and for Settings."""
    if not paths.FROZEN:
        return False, "run from source"
    if not config.get("allow_network", rules.ALLOW_NETWORK_DEFAULT):
        return False, "network lookups are off"
    return True, ""


def check(cache_dir=None, now: datetime | None = None) -> tuple[Answer | None, bool]:
    """The newest release, asking GitHub only when the kept answer is due: (answer, asked now)."""
    cache_dir = cache_dir if cache_dir is not None else paths.cache_dir()
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    kept = last(cache_dir)
    if not due(kept, now):
        log.info("update check: asked %s, not again yet", kept.checked_at.isoformat(timespec="seconds"))
        return kept, False
    answer = fetch(now)
    _keep(cache_dir, answer)
    if answer.newer:
        log.info("update check: %s is out (this copy is %s)", answer.latest, version.APP_VERSION)
    elif answer.reached:
        log.info("update check: nothing newer than %s (newest release: %s)", version.APP_VERSION,
                 answer.latest or "none yet")
    return answer, True
