"""Reading the stored Steam record and turning it into things a page can show.

Pure functions over a record that is already on disk -- nothing here touches the network.
A game with no appid has no record, every function returns empty, and the page collapses
the blocks that have nothing in them.
"""

from __future__ import annotations

import html
import logging
import re
from datetime import date, datetime

from shared import paths
from shared import rules
from web import steam_web

log = logging.getLogger(__name__)

CACHE_DIR = str(paths.cache_dir())

# Tags that mean "new line" become a space; every other tag simply disappears. Replacing
# all of them with a space instead turns "English<strong>*</strong>, French" into
# "English * , French" -- spaces adrift in the middle of words and before punctuation.
_BREAK = re.compile(r"<\s*(?:br|/p|/div|/li|/h[1-6])[^>]*>", re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"\s+")
_SPACE_BEFORE_PUNCTUATION = re.compile(r"\s+([,.;:!?%)\]])")

# How the game page (Phase 33) sorts the rows of metadata(): these four are shown as
# pills under the title rather than repeated in the Details card, and these two are
# paths -- the one kind of value with no spaces to wrap at, so they get the wide column.
SUMMARY_FACTS = ("Played", "Last played", "Installed", "Saves copied")
PATH_FACTS = ("Runs", "Saves")

# Records are read once and kept; they never change without a rescan.
_loaded: dict[str, dict] = {}


def record_for(view) -> dict:
    """The stored Steam record for this game, or {} if it has none."""
    appid = str(view.entry.extra.get("appid") or "")
    if not appid:
        return {}
    if appid not in _loaded:
        _loaded[appid] = steam_web.load_details(CACHE_DIR, appid)
    return _loaded[appid]


def forget() -> None:
    """Drop the in-memory copies, so a rescan's new records are picked up."""
    _loaded.clear()


def clean_text(value: str) -> str:
    """Strip tags and entities from a store string.

    Steam's own fields contain markup: descriptions carry <br> and <strong>, and the
    language list is riddled with it. Left alone it renders as literal angle brackets.
    """
    if not value:
        return ""
    text = _BREAK.sub(" ", str(value))
    text = _TAG.sub("", text)
    text = html.unescape(text)
    text = _WHITESPACE.sub(" ", text)
    return _SPACE_BEFORE_PUNCTUATION.sub(r"\1", text).strip()


def description(record: dict) -> str:
    return clean_text(record.get("short_description", ""))


def metadata(record: dict, view, money: dict | None = None,
             steam: dict | None = None) -> list[tuple[str, str]]:
    """Label/value rows for the facts block, in display order.

    Rows with nothing to say are simply absent, so an entry with no Steam record still
    produces a sensible short block rather than a column of dashes. `steam` is Steam's own
    counter for the game on the accounts marked mine (Phase 76), "On Steam", right after the
    source; `money` is the store's answer for the game (Phase 74): its four facts follow, each
    only when it has something to say.
    """
    from shared import humanize

    rows: list[tuple[str, str]] = []

    def add(label: str, value: str) -> None:
        if value:
            rows.append((label, value))

    add("Developer", ", ".join(_strings(record.get("developers"))))
    add("Publisher", ", ".join(_strings(record.get("publishers"))))
    add("Released", _release_date(record))
    add("Genres", ", ".join(_descriptions(record.get("genres"))))

    add("Played", humanize.playtime(view.playtime_seconds))
    add("Last played", humanize.when(view.last_played))
    add("Installed", humanize.size(view.entry.size_on_disk) if view.entry.size_on_disk else "")
    add("Source", _source_label(view))
    for label, value in steam_time_facts(steam):
        add(label, value)
    for label, value in money_facts(money):
        add(label, value)
    add("Runs", view.launch_target)
    add("Saves", _saves_where(view))
    add("Saves copied", _saves_copied(view))
    return rows


STEAM_FACT = "On Steam"


def steam_time_facts(steam: dict | None) -> list[tuple[str, str]]:
    """What Steam's own counter says of the game on the accounts marked mine (Phase 76).

    `steam` is the store's answer for the game (`LibraryStore.steam_times()[key]`), present
    only when an account marked mine holds it. "23h 30m, last played 1 Sep"; held by more
    than one: "33h 30m on 2 accounts, last played 1 Sep". Steam counts whole minutes, so 0
    with a last played is under a minute, and 0 without one is never played. Accounts that
    hold only a last played give that alone. Nothing to say, no fact.
    """
    from shared import humanize

    if not steam:
        return []
    parts = []
    minutes, last = steam.get("minutes"), steam.get("last_played")
    if minutes is not None:
        if minutes > 0:
            time = humanize.playtime(int(minutes) * 60)
        else:
            time = "under a minute" if last else "never played"
        accounts = steam.get("accounts") or 0
        parts.append(f"{time} on {accounts} accounts" if accounts > 1 else time)
    if last:
        parts.append(f"last played {humanize.day(datetime.fromisoformat(last))}")
    return [(STEAM_FACT, ", ".join(parts))] if parts else []


MONEY_FACTS = ("List price", "Lowest seen", "Paid", "Cost per hour")


def money_facts(money: dict | None) -> list[tuple[str, str]]:
    """What the game's page says about money (Phase 74), from the store's `money(key)`.

    - List price: the newest observation -- "59,99 € on Steam, as of 11 Oct" (with the
      discount when there is one), "free", or "not sold here".
    - Lowest seen: only when the series has more than one observation and its lowest price is
      not what the game costs now -- "29,99 € on 20 Dec".
    - Paid: one purchase "12,50 €, key reseller, 3 May 2026"; several, the total and how many;
      in more than one currency, never added up.
    - Cost per hour: what was paid over the launcher's hours, only where both exist.
    No purchase is "unknown", never "free": the fact is simply absent.
    """
    from shared import humanize

    if not money:
        return []
    rows: list[tuple[str, str]] = []
    latest = money.get("latest")
    priced_now = None
    if latest:
        if latest["kind"] == "priced":
            priced_now = latest["final_cents"]
            off = f", {latest['discount_percent']}% off" if latest.get("discount_percent") else ""
            when = humanize.day(datetime.fromisoformat(latest["observed_at"]))
            rows.append(("List price", f"{humanize.money(latest['final_cents'], latest['currency'])} on Steam"
                                       f"{off}, as of {when}"))
        else:
            rows.append(("List price", "free" if latest["kind"] == "free" else "not sold here"))
    span = money.get("range")
    if (span and (span.get("observations") or 0) > 1 and span.get("lowest_cents") is not None
            and span["lowest_cents"] != priced_now):
        rows.append(("Lowest seen", f"{humanize.money(span['lowest_cents'], span['lowest_currency'])} on "
                                    f"{humanize.day(datetime.fromisoformat(span['lowest_on']))}"))
    bought = money.get("purchases") or []
    if len(bought) == 1:
        one = bought[0]
        parts = [humanize.money(one["paid_cents"], one["currency"]), one["store"]]
        if one.get("bought_on"):
            parts.append(humanize.day(date.fromisoformat(one["bought_on"]), year=True))
        rows.append(("Paid", ", ".join(parts)))
    elif bought:
        if money.get("paid_cents") is not None:
            rows.append(("Paid", f"{humanize.money(money['paid_cents'], money['paid_currency'])} "
                                 f"in {len(bought)} purchases"))
        else:
            rows.append(("Paid", f"{len(bought)} purchases, in more than one currency"))
    if money.get("cents_per_hour") is not None and money.get("paid_currency"):
        rows.append(("Cost per hour", f"{humanize.money(int(money['cents_per_hour']), money['paid_currency'])} an hour"))
    return rows


def _saves_where(view) -> str:
    """Where the game keeps its saves, one place per line -- for games the launcher times."""
    if view.entry.launch_kind != "exe":
        return ""
    folders = [f for f in view.data.get(rules.SAVE_DIRS_KEY) or [] if isinstance(f, str)]
    if folders:
        return "\n".join(folders)
    if view.data.get(rules.SAVE_DIRS_CHECKED_KEY):
        return "none found yet"
    return ""


def _saves_copied(view) -> str:
    if not view.data.get(rules.SAVE_DIRS_KEY):
        return ""
    from shared import humanize
    from logic import save_backup

    # The newest copy of this game's saves -- including those of an earlier install whose
    # history was carried over to it (Phase 36), which are this game's saves just the same.
    found = [save_backup.latest(view.key, view.display_name)]
    found += [save_backup.latest(key, "") for key in view.data.get(rules.EARLIER_KEYS_KEY) or []]
    found = [backup for backup in found if backup is not None]
    if not found:
        return "not yet"
    latest = max(found, key=lambda backup: backup.made_at)
    return f"{humanize.when(latest.made_at)}  ({humanize.size(latest.size)})"


def _source_label(view) -> str:
    # "folders" is what the scanner calls itself; the stats page's names read better.

    source = rules.SOURCE_LABELS.get(view.entry.source, view.entry.source)
    kind = view.app_type
    if kind and kind not in rules.STEAM_GAME_TYPES:
        return f"{source} · Steam calls this a {kind}"
    return source


def _release_date(record: dict) -> str:
    date = record.get("release_date")
    if not isinstance(date, dict):
        return ""
    if date.get("coming_soon"):
        return f"{clean_text(date.get('date', ''))} (not out yet)".strip()
    return clean_text(date.get("date", ""))


def _strings(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [clean_text(v) for v in value if isinstance(v, str) and v.strip()]


def _descriptions(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [
        clean_text(item.get("description", ""))
        for item in value
        if isinstance(item, dict) and item.get("description")
    ]


def has_full_controller_support(record: dict) -> bool:
    """Two independent signals; a game may carry either, both or neither."""
    if str(record.get("controller_support", "")).casefold() == rules.STEAM_CONTROLLER_FULL_VALUE:
        return True
    wanted = rules.STEAM_CATEGORY_FULL_CONTROLLER
    return any(name.casefold() == wanted for name in _descriptions(record.get("categories")))


def screenshots(record: dict, limit: int) -> list[tuple[str, str]]:
    """(thumbnail url, full url) pairs, capped. Literal URLs from the record, never derived."""
    items = record.get("screenshots")
    if not isinstance(items, list):
        return []
    pairs = []
    for shot in items:
        if not isinstance(shot, dict):
            continue
        thumb = str(shot.get("path_thumbnail") or "")
        full = str(shot.get("path_full") or thumb)
        if thumb:
            pairs.append((thumb, full))
        if len(pairs) >= limit:
            break
    return pairs
