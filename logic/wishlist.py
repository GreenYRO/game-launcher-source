"""The Steam wishlist (Phase 86): what was said to be wanted, read from Steam, kept, and set
against what is played.

The shape is Steam's playtime's (logic/steam_time.py), with a network source:

  1. `due`, on the GUI thread, before a window scan: the accounts marked mine whose list was not
     read in the last rules.WISHLIST_READ_HOURS -- once a day. None with the network off.
  2. `read`, on the scan thread: web.steam_wishlist asks for each list, a request per account,
     a second apart, and the answers go to a hand-off file in cache/. A request with no answer
     is no reading: it is logged and asked again at the next scan.
  3. `land`, on the GUI thread, after the Steam projection and the prices: each answer into the
     database in one transaction (LibraryStore.land_wishlist), and what landed leaves the
     hand-off; one that did not stays for the next scan.

**Stated and revealed preference.** The wishlist is what the user said he wants; the hours are
what he chose to play. `fit` sets one against the other by content-based filtering: since Phase 89
each genre weighs by how rare it is among the apps the library knows (TF-IDF), a game is a vector of
its genres' weights, and the fit is the cosine of that vector and the one of the hours --
"33% like what you play · Strategy, Action". Phase 86 counted the share of the hours on games sharing
a genre, and with Action in 87% of the hours nearly every game read 87-99%. Used here only to order
a list the user already chose, never to guess what he would like. A game whose record has not been
fetched yet has no genres, and says so. No SQL here.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

from data_access import backups
from logic import alerts as alerts_module
from logic.fit import (NOT_FETCHED, NO_GENRE, NOTHING_PLAYED, Fit, fit, profile_of,  # noqa: F401
                       taste, vector, weights_of)
from shared import humanize
from shared import paths
from shared import rules
from web import steam_wishlist

log = logging.getLogger(__name__)


@dataclass
class Landed:
    """What one landing did, over every answer in the hand-off."""
    readings: int = 0  # answers now in the database
    added: int = 0  # games new on a list
    seen: int = 0  # games still on a list
    returned: int = 0  # games back on a list they had left
    removed: int = 0  # games a list no longer holds (removed_at set; nothing deleted)
    kept: int = 0  # answers left in the hand-off for the next scan


def due(store, allow_network: bool, say: bool = True) -> list[dict]:
    """The accounts whose list the next scan reads: {account_id, steam_id64}, once a day each.

    `say=False` is the tick's question (Phase 92): logged at debug, since no scan may follow."""
    tell = log.info if say else log.debug
    if not allow_network:
        tell("wishlist: none read with this scan -- the network is off")
        return []
    if not getattr(store, "keeps_wishlist", False):
        tell("wishlist: none read with this scan -- this library keeps no wishlist")
        return []
    found = store.wishlist_due(rules.WISHLIST_READ_HOURS)
    tell("wishlist: %d account(s) due for a read %s (once in %d hours)", len(found),
         "this scan" if say else "(the tick asked)", rules.WISHLIST_READ_HOURS)
    return found


def handoff_path(cache_dir: str) -> str:
    return os.path.join(cache_dir, rules.WISHLIST_HANDOFF_FILE)


def pending(cache_dir: str) -> list[dict]:
    """The answers the scan thread wrote and the window has not landed yet."""
    path = handoff_path(cache_dir)
    if not os.path.isfile(path):
        return []
    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("could not read %s (%s); those answers are lost -- the next scan asks again", path, exc)
        return []
    readings = payload.get("readings") if isinstance(payload, dict) else None
    return [r for r in readings if isinstance(r, dict)] if isinstance(readings, list) else []


def _keep(cache_dir: str, readings: list[dict]) -> bool:
    path = handoff_path(cache_dir)
    if not readings:
        try:
            if os.path.isfile(path):
                os.remove(path)
        except OSError as exc:
            log.error("could not empty %s: %s", path, exc)
            return False
        return True
    os.makedirs(cache_dir, exist_ok=True)
    return backups.atomic_write(Path(path), json.dumps({"readings": readings}, indent=1))


def read(accounts: list[dict], cache_dir: str | None = None) -> int:
    """The scan thread's half: one request per account, the answers to the hand-off.

    Never raises: a wishlist must not cost the scan its result. Returns how many answers were kept.
    """
    if not accounts:
        return 0
    cache_dir = str(paths.cache_dir()) if cache_dir is None else cache_dir
    try:
        readings = []
        for index, account in enumerate(accounts):
            if index:
                time.sleep(rules.STEAM_WEB_RATE_LIMIT_SECONDS)  # a second apart, as every Steam request
            answer = steam_wishlist.fetch(account["steam_id64"])
            if answer.state == steam_wishlist.FAILED:
                log.info("wishlist: account %s not read (%s); asked again at the next scan",
                         account["account_id"], answer.detail)
                continue
            readings.append({"account_id": account["account_id"],
                             "read_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                             "items": [dict(item) for item in answer.items]})
            log.info("wishlist: account %s -> %s", account["account_id"], answer.detail)
        if readings:
            _keep(cache_dir, pending(cache_dir) + readings)
        return len(readings)
    except Exception as exc:  # noqa: BLE001 -- see the docstring
        log.exception("reading the wishlists failed, the scan goes on without them: %s", exc)
        return 0


def land(store, cache_dir: str | None = None) -> Landed:
    """The window's half: every pending answer into the database, oldest first."""
    done = Landed()
    cache_dir = str(paths.cache_dir()) if cache_dir is None else cache_dir
    readings = pending(cache_dir)
    if not readings:
        return done
    if not getattr(store, "keeps_wishlist", False):
        done.kept = len(readings)
        log.info("wishlist: %d answer(s) wait -- this library keeps no wishlist", len(readings))
        return done
    remaining = []
    for reading in sorted(readings, key=lambda r: str(r.get("read_at", ""))):
        result = store.land_wishlist(reading)
        if result is None:
            remaining.append(reading)
            continue
        done.readings += result["read"]
        done.added += result["added"]
        done.seen += result["seen"]
        done.returned += result["returned"]
        done.removed += result["removed"]
    _keep(cache_dir, remaining)
    done.kept = len(remaining)
    log.info("wishlist: %d answer(s) landed -- %d game(s) added, %d still there, %d back, %d no longer on "
             "a list; %d kept for the next scan", done.readings, done.added, done.seen, done.returned,
             done.removed, done.kept)
    return done


# -- the fit line: stated against revealed preference (rarity-weighted since Phase 89) -----------
# The maths is logic/fit.py's since Phase 98, shared with For you; imported here under its old names.


def fits(source) -> dict[int, Fit]:
    """Every game on the wishlists of the accounts marked mine, with its fit -- from the queries
    in data_access/reports.py (read only)."""
    profile = profile_of(source.rows("wishlist_profile"))
    weights = weights_of(source.rows("wishlist_idf"))
    played = taste(profile, weights)
    genres: dict[int, list] = {}
    for row in source.rows("wishlist_genres"):
        genres.setdefault(row["appid"], []).append((row["genre_id"], row["name"]))
    return {row["appid"]: fit(genres.get(row["appid"], []), profile, bool(row["has_record"]), weights, played)
            for row in source.rows("wishlist_now")}


# -- the Wishlist page (Phase 87): every row's words, the order, what an empty page says ---------

NO_ACCOUNT = ("No Steam account is marked as yours, so no wishlist is read. Settings, Steam accounts: "
              "mark the ones that are yours.")
NOT_READ = "Your wishlists have not been read yet: they are read once a day, with a scan."
NETWORK_OFF = ("Your wishlists have not been read: network lookups are off (Settings, Artwork and the "
               "internet).")
NOTHING_TO_READ = ("Nothing to read: the wishlists of your accounts are private on Steam, or empty. "
                   "A private list answers exactly as an empty one does, and the launcher cannot change "
                   "a Steam profile setting.")
NOTHING_ON_LIST = "Nothing is on your wishlist now."
NOTHING_ON_SALE = "Nothing on your wishlist is on sale today."
NO_ALERTS = (f"No price alert in the last {rules.ALERT_KEEP_DAYS} days. A drop to the lowest price seen alerts by "
             "itself; for a price of your own, a game's menu: Alert me under...")
ALL, ON_SALE, ALERTS = "all", "on_sale", "alerts"  # the Alerts chip: Phase 101


@dataclass(frozen=True)
class Row:
    """One wished game as the page shows it: the facts, already in words; a part is empty when
    its data does not exist."""
    appid: int
    name: str
    price: str  # today's price, "Free", "Not sold", or "No price yet"
    was: str  # the price before the discount, struck through on the page; "" when not on sale
    discount: str  # "-50%", or ""
    lowest: str  # "lowest seen 27,99 € on 14 Sep", or ""
    prices: str  # "8 prices since 15 Oct", "1 price so far, 15 Oct", or ""
    lowest_now: bool  # today's price is the lowest seen (v_wishlist_now.is_lowest_now)
    fit: Fit
    played: str  # "Already played: 42 min", or ""
    added: str  # "Added 21 May 2016"
    accounts: str  # "On Alpha's list", only when more than one account is marked mine
    on_sale: bool
    percent: int  # the discount as a number, for the order
    removed: bool
    hidden: bool
    removed_at: str = ""  # when the last list let it go, for the order of that group
    series: tuple = ()  # its prices in cents, oldest first, in today's currency; drawn from WISHLIST_SERIES_MIN on (89)
    # Phase 101: the target in words ("Alert under 20,00 €", "Below your target since 18 Oct", or why it cannot
    # compare), drawn where the count of prices is; and, on the Alerts list, the alert this row stands for.
    target: str = ""
    alert: str = ""
    currency: str = ""  # today's price's currency, the target dialog's
    cents: int | None = None  # today's price, when it is priced
    lowest_cents: int | None = None  # the lowest the series has seen: the dialog starts there
    target_cents: int | None = None  # the target set, if any


@dataclass(frozen=True)
class Page:
    """What the page shows: the games on the lists now (in order), the ones no longer on any,
    the ones hidden from the page, why it is empty when it is, and a line about the reads."""
    rows: tuple = ()
    removed: tuple = ()
    hidden: tuple = ()
    empty: str = ""
    footnote: str = ""
    alerts: tuple = ()  # the alerts of the last ALERT_KEEP_DAYS, newest first: one row each (Phase 101)

    @property
    def on_sale(self) -> int:
        return sum(1 for row in self.rows if row.on_sale)

    @property
    def lowest_now(self) -> int:
        """How many are at their lowest price seen today: Phase 87's daily notice, a line on the page since 101."""
        return sum(1 for row in self.rows if row.lowest_now)

    def shown(self, choice: str) -> tuple:
        """The rows under the chip chosen: every one, the ones on sale today, or the alerts."""
        if choice == ALERTS:
            return self.alerts
        return self.rows if choice != ON_SALE else tuple(row for row in self.rows if row.on_sale)


def _moment(text: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(text) if text else None
    except ValueError:
        return None


def _day(text: str | None, year: bool | None = None) -> str:
    moment = _moment(text)
    return humanize.day(moment, year=year) if moment else ""


def _names(accounts: str | None) -> str:
    names = [name.strip() for name in (accounts or "").split(",") if name.strip()]
    if not names:
        return ""
    if len(names) == 1:
        return f"On {names[0]}'s list"
    return f"On the lists of {', '.join(names[:-1])} and {names[-1]}"


def series_of(rows) -> dict[int, list[tuple[str, int]]]:
    """The wishlist_series query's rows -- every priced observation of a wished game, oldest first -- by game."""
    found: dict[int, list] = {}
    for row in rows:
        found.setdefault(row["appid"], []).append((row["currency"], row["final_cents"]))
    return found


def row_of(view: dict, fit_line: Fit, hidden: bool, several_accounts: bool, series=(), target: dict | None = None,
           timed=()) -> Row:
    """One row of v_wishlist_now, in words. `series` is the game's (currency, cents) observations,
    oldest first; the row keeps the ones in today's currency, and only when there are enough to draw.
    `target` is its price_target row, if one is set, and `timed` its observations with their moments
    (observed_at, cents, currency), for the day it went under the target (Phase 101)."""
    kind, currency = view.get("kind"), view.get("currency") or rules.STEAM_STORE_CURRENCY
    percent = int(view.get("discount_percent") or 0) if kind == "priced" else 0
    on_sale = kind == "priced" and percent > 0
    if kind == "priced":
        price = humanize.money(view["final_cents"], currency)
    else:
        price = {"free": "Free", "unavailable": "Not sold"}.get(kind, "No price yet")
    was = humanize.money(view["initial_cents"], currency) if on_sale else ""
    observations = int(view.get("observations") or 0)
    lowest = prices = ""
    if kind == "priced" and observations >= 2:
        if view.get("lowest_cents") is not None and view["lowest_cents"] < view["final_cents"]:
            lowest = f"lowest seen {humanize.money(view['lowest_cents'], currency)} on {_day(view.get('lowest_on'))}"
        prices = f"{observations} prices since {_day(view.get('first_observed'))}"
    elif kind == "priced" and observations == 1:  # a game not sold has no price to count
        prices = f"1 price so far, {_day(view.get('first_observed'))}"
    minutes = view.get("minutes_played") or 0
    played = f"Already played: {humanize.playtime(round(minutes * 60))}" if minutes >= 1 else ""
    added = (f"Added {_day(view.get('date_added'), year=True)}" if view.get("date_added")
             else f"First seen {_day(view.get('first_seen'), year=True)}")
    name = view.get("name") or f"App {view['appid']}"
    line = tuple(cents for code, cents in series if code == currency) if kind == "priced" else ()
    return Row(appid=view["appid"], name=name, price=price, was=was, discount=f"-{percent}%" if on_sale else "",
               lowest=lowest, prices=prices, lowest_now=bool(view.get("is_lowest_now")), fit=fit_line,
               played=played, added=added, accounts=_names(view.get("accounts")) if several_accounts else "",
               on_sale=on_sale, percent=percent, removed=(view.get("lists") or 0) == 0, hidden=hidden,
               removed_at=view.get("removed_at") or "",
               series=line if len(line) >= rules.WISHLIST_SERIES_MIN else (),
               target=alerts_module.target_line(target, list(timed), kind, view.get("currency")),
               currency=currency, cents=view.get("final_cents") if kind == "priced" else None,
               lowest_cents=view.get("lowest_cents"), target_cents=target["cents"] if target else None)


def order(rows) -> tuple:
    """On sale first, the deepest discount first; then how well it fits what is played; then the name.
    The one ranking on the page, and it is said in words on every row (the discount, the fit line)."""
    return tuple(sorted(rows, key=lambda r: (not r.on_sale, -r.percent,
                                             -(r.fit.share if r.fit.share is not None else -1.0),
                                             r.name.casefold())))


def page(source, accounts: list[dict], hidden: set[int], allow_network: bool, alerts: bool = False,
         now: datetime | None = None) -> Page:
    """The page from the queries (source: data_access.reports.Reports, read only) and the accounts
    (LibraryStore.steam_accounts(), with their wishlist reads). `alerts`: the library keeps targets and
    the alert log (version 8, Phase 101) -- the rows' target words and the Alerts list."""
    mine = [a for a in accounts if a.get("is_mine")]
    if not mine:
        return Page(empty=NO_ACCOUNT)
    read = [a for a in mine if a.get("wishlist_read_at")]
    if not read:
        return Page(empty=NOT_READ if allow_network else NETWORK_OFF)
    views = source.rows("wishlist_now")
    found = fits(source)
    several = len(mine) > 1
    observed = source.rows("wishlist_series")
    series = series_of(observed)
    timed = alerts_module.series_of(observed)
    targets = {r["appid"]: dict(r) for r in source.rows("price_targets")} if alerts else {}
    rows = [row_of(v, found.get(v["appid"], Fit(None, NOT_FETCHED)), v["appid"] in hidden, several,
                   series.get(v["appid"], ()), targets.get(v["appid"]), timed.get(v["appid"], ())) for v in views]
    current = order(r for r in rows if not r.removed and not r.hidden)
    removed = tuple(sorted((r for r in rows if r.removed and not r.hidden), key=lambda r: (r.removed_at, r.appid),
                           reverse=True))
    hidden_rows = tuple(sorted((r for r in rows if r.hidden), key=lambda r: r.name.casefold()))
    with_items = [a for a in read if a.get("wishlist_state") == "items"]
    nothing = [a for a in read if a.get("wishlist_state") != "items"]
    if not with_items and not rows:
        empty = NOTHING_TO_READ
    elif not current:
        empty = NOTHING_ON_LIST
    else:
        empty = ""
    newest = max((a["wishlist_read_at"] for a in read), default=None)
    parts = [f"Read {_when(newest)}" + (f" from {_list_of(with_items)}" if with_items else "")]
    if nothing:
        parts.append(f"nothing to read from {_list_of(nothing)} (private on Steam, or empty)")
    parts.append("prices asked for every day")
    by_appid = {r.appid: r for r in rows}
    sent = alerts_module.drops(source.rows("price_alerts"), now) if alerts else []
    alert_rows = tuple(replace(by_appid[a["appid"]], alert=alerts_module.alert_line(a)) for a in sent
                       if a["appid"] in by_appid and not by_appid[a["appid"]].hidden)
    return Page(rows=current, removed=removed, hidden=hidden_rows, empty=empty, footnote=" · ".join(parts) + ".",
                alerts=alert_rows)


def _list_of(accounts: list[dict]) -> str:
    names = [a.get("persona") or f"Account {a['account_id']}" for a in accounts]
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"


def _when(text: str | None) -> str:
    moment = _moment(text)
    return humanize.when(moment) if moment else "at an unknown time"
