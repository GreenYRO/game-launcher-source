"""Price alerts on the wishlist (Phase 101): a target per wished game, and a message at each new drop.

The launcher reads every wished game's price once a day (Phase 86) and knew the lowest it had seen; this is
the action: when the prices of a scan land, each wished game still on a list and not hidden from the page is
judged on the price that has just arrived -- only that one, so setting a target never sets one off, and an old
price never does after the upgrade -- in two kinds:

  * 'lowest': strictly lower than every earlier price of the game in the same currency, when the series holds
    at least rules.ALERT_MIN_OBSERVATIONS prices with it. One or two prices are no reference yet: "lowest seen"
    is a reference point (an anchor) only once there is something to be lower than, and an alert on a series of
    one would be noise.
  * 'target': at or under the game's target, in the target's currency -- and the price before it was above the
    target, or above this one (a further drop). A price that stays under the target is silence; a currency the
    target was not set in alerts nothing, and the row says so.

Each (game, price, kind) alerts once: the price_alert log's key. The log is written before the message is shown
(LibraryStore.log_price_alerts answers what it wrote), so a failure can never repeat one. Several games in one
landing make one message. Who shows it -- the window's toast, or the tray's balloon when the window is hidden --
is the window's (presentation); here are the rules and the words. No Qt, no SQL.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from shared import humanize
from shared import rules

log = logging.getLogger(__name__)

LOWEST, TARGET = rules.ALERT_LOWEST, rules.ALERT_TARGET


@dataclass(frozen=True)
class Alert:
    """One alert: the game, the price that set it off (its moment in the series) and why."""
    appid: int
    name: str
    observed_at: str
    kind: str  # LOWEST or TARGET
    cents: int
    currency: str
    target_cents: int | None = None  # the target it met, for the words; not kept in the log


def series_of(rows) -> dict[int, list[tuple[str, int, str]]]:
    """The wishlist_series query's rows -- every priced observation of a wished game, oldest first -- by game,
    as (observed_at, cents, currency)."""
    found: dict[int, list] = {}
    for row in rows:
        found.setdefault(row["appid"], []).append((row["observed_at"], row["final_cents"], row["currency"]))
    return found


def decide(fresh, wished: dict[int, str], series: dict[int, list], targets: dict[int, dict],
           logged: set[tuple[int, str, str]]) -> list[Alert]:
    """The alerts the prices that have just landed set off. `fresh` is their (appid, observed_at) keys; `wished`
    the games still on a list and not hidden, by appid, with their names; `series` each game's priced
    observations, oldest first; `targets` each target row (cents, currency); `logged` the alerts already sent.
    Targets first in the answer, then the name: the order the message names them in."""
    found: list[Alert] = []
    newest: dict[int, str] = {}
    for appid, observed_at in fresh:
        if appid in wished and observed_at > newest.get(appid, ""):
            newest[appid] = observed_at
    for appid, observed_at in newest.items():
        prices = series.get(appid) or []
        at = next((i for i, (moment, _c, _cur) in enumerate(prices) if moment == observed_at), None)
        if at is None:
            continue  # free, not sold or refused: no price to judge
        _moment, cents, currency = prices[at]
        earlier = [c for moment, c, cur in prices[:at] if cur == currency]
        name = wished[appid]
        if (len(earlier) + 1 >= rules.ALERT_MIN_OBSERVATIONS and earlier and all(cents < c for c in earlier)
                and (appid, observed_at, LOWEST) not in logged):
            found.append(Alert(appid, name, observed_at, LOWEST, cents, currency))
        target = targets.get(appid)
        if target and target["currency"] == currency and cents <= target["cents"]:
            before = earlier[-1] if earlier else None
            crossed = before is None or before > target["cents"] or before > cents
            if crossed and (appid, observed_at, TARGET) not in logged:
                found.append(Alert(appid, name, observed_at, TARGET, cents, currency, target["cents"]))
    return sorted(found, key=lambda a: (a.kind != TARGET, a.name.casefold(), a.kind))


def _why(alerts: list[Alert]) -> str:
    """One game's reasons, in words: under the target, the lowest seen, or both."""
    target = next((a for a in alerts if a.kind == TARGET), None)
    parts = []
    if target is not None:
        parts.append(f"under your {humanize.money(target.target_cents, target.currency)} target")
    if any(a.kind == LOWEST for a in alerts):
        parts.append("the lowest seen")
    return " and ".join(parts)


def message(alerts: list[Alert]) -> str:
    """Every alert of one landing as one message: a game is named once, at most rules.ALERT_NAMED_MAX of them.
    "Hades II dropped to 19,99 € — under your 20,00 € target"; "3 wishlist games dropped: Hades II at 19,99 €,
    Silksong at 15,99 €, and 1 more"."""
    games: dict[int, list[Alert]] = {}
    for alert in alerts:
        games.setdefault(alert.appid, []).append(alert)
    if not games:
        return ""
    if len(games) == 1:
        [(_appid, mine)] = games.items()
        first = mine[0]
        return f"{first.name} dropped to {humanize.money(first.cents, first.currency)} \u2014 {_why(mine)}"
    named = list(games.values())[:rules.ALERT_NAMED_MAX]
    words = ", ".join(f"{m[0].name} at {humanize.money(m[0].cents, m[0].currency)}" for m in named)
    rest = len(games) - len(named)
    if rest:
        words += f", and {rest} more"
    return f"{len(games)} wishlist games dropped: {words}"


def _moment(text: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(text) if text else None
    except ValueError:
        return None


def target_line(target: dict | None, prices: list[tuple[str, int, str]], kind: str | None,
                currency: str | None) -> str:
    """The row's words for its target: "Alert under 20,00 €"; "Below your target since 18 Oct" when today's
    price is at or under it -- the day of the first price of the run that is still under it; or, when today's
    price is in another currency than the target's, that it cannot compare. Empty with no target."""
    if not target:
        return ""
    if kind == "priced" and currency and currency != target["currency"]:
        return f"Your target is in {target['currency']}; the price is now in {currency}"
    since = None
    if kind == "priced":
        for moment, cents, cur in reversed(prices):
            if cur != target["currency"] or cents > target["cents"]:
                break
            since = moment
    if since is not None:
        day = _moment(since)
        return f"Below your target since {humanize.day(day) if day else since[:10]}"
    return f"Alert under {humanize.money(target['cents'], target['currency'])}"


def recent(rows, now: datetime | None = None) -> list[dict]:
    """The alerts of the last rules.ALERT_KEEP_DAYS, newest first: the price_alerts query's rows."""
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=rules.ALERT_KEEP_DAYS)
    kept = [dict(r) for r in rows if (_moment(r["sent_at"]) or now) >= since]
    return sorted(kept, key=lambda r: (r["sent_at"], r["observed_at"]), reverse=True)


def drops(rows, now: datetime | None = None) -> list[dict]:
    """The Alerts list's lines: the alerts of the last rules.ALERT_KEEP_DAYS, one per drop -- a price that was
    both under the target and the lowest seen is one drop with its two kinds -- newest first."""
    found: dict[tuple, dict] = {}
    for row in recent(rows, now):
        drop = found.setdefault((row["appid"], row["observed_at"]), {**row, "kinds": []})
        drop["kinds"].append(row["kind"])
    return list(found.values())


def alert_line(drop: dict) -> str:
    """One drop as the Alerts list shows it: "18 Oct: 19,99 € — under your target and the lowest seen"."""
    day = _moment(drop["observed_at"])
    kinds = drop.get("kinds") or [drop["kind"]]
    why = " and ".join(words for kind, words in ((TARGET, "under your target"), (LOWEST, "the lowest seen"))
                       if kind in kinds)
    return (f"{humanize.day(day) if day else drop['observed_at'][:10]}: "
            f"{humanize.money(drop['final_cents'], drop['currency'])} — {why}")


def land(store, fresh, hidden: set[int], now: datetime | None = None) -> list[Alert]:
    """After the prices of a scan have landed (prices.land's `fresh`): the alerts they set off, written to the log
    and answered -- only the ones the log took, so a message never repeats one. Nothing below version 8, or with
    no new price."""
    if not fresh or not getattr(store, "keeps_alerts", False):
        return []
    source = store.reports()
    if source is None:
        return []
    try:
        wished = {r["appid"]: r["name"] or f"App {r['appid']}" for r in source.rows("wishlist_now")
                  if (r["lists"] or 0) > 0 and r["appid"] not in hidden}
        series = series_of(source.rows("wishlist_series"))
        targets = {r["appid"]: dict(r) for r in source.rows("price_targets")}
        logged = {(r["appid"], r["observed_at"], r["kind"]) for r in source.rows("price_alerts")}
    except Exception as exc:  # noqa: BLE001 -- an alert must never cost a scan its landing
        log.warning("price alerts: not worked out (%s)", exc)
        return []
    decided = decide(fresh, wished, series, targets, logged)
    if not decided:
        log.info("price alerts: %d new price(s) of wished games judged, nothing set off",
                 sum(1 for appid, _at in fresh if appid in wished))
        return []
    sent = store.log_price_alerts(decided, now)
    log.info("price alerts: %d set off, %d written to the log", len(decided), len(sent))
    return sent
