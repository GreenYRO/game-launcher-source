"""Small formatters for the numbers shown on a tile."""

from __future__ import annotations

from datetime import date, datetime, timezone

from shared import rules


def playtime(seconds: int) -> str:
    if seconds <= 0:
        return "never played"
    if seconds < 60:
        return "under a minute"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} min"
    hours, remainder = divmod(minutes, 60)
    if hours < 100:
        return f"{hours}h {remainder:02d}m"
    return f"{hours} hours"


def when(moment: datetime | None) -> str:
    if moment is None:
        return "never"
    now = datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.astimezone()
    delta = now - moment.astimezone(timezone.utc)
    days = delta.days
    if days < 0:
        return moment.strftime("%d %b %Y")
    if days == 0:
        hours = delta.seconds // 3600
        if hours < 1:
            return "just now"
        return f"{hours}h ago"
    if days == 1:
        return "yesterday"
    if days < 30:
        return f"{days} days ago"
    if days < 365:
        months = days // 30
        return f"{months} month{'s' if months != 1 else ''} ago"
    return moment.strftime("%b %Y")


def moment(value: datetime) -> str:
    """An exact date and time, for lists where "2 days ago" is not precise enough.

    `when` is right on a tile, where the gist is all that matters. Choosing which backup to
    restore is the opposite: two snapshots twenty minutes apart both read "2h ago".
    """
    today = datetime.now().date()
    if value.date() == today:
        return value.strftime("Today at %H:%M")
    if (today - value.date()).days == 1:
        return value.strftime("Yesterday at %H:%M")
    return value.strftime("%d %b %Y at %H:%M")


def size(num_bytes: int) -> str:
    value = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024:
            return f"{value:.0f} {unit}" if unit in ("B", "KB") else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


NO_BREAK = "\u00a0"  # between an amount and its currency sign: a space that never breaks a line


def money(cents: int, currency: str) -> str:
    """An amount, the one way it is written everywhere (Phase 74): "59,99 €", "1.299,00 €", "12,50 lei".

    As the store writes it for Romania -- a decimal comma, a dot between thousands -- with the
    currency's sign after the number, joined to it by a space that does not break, so "€"
    never wraps onto a line of its own. A currency without a sign of its own keeps its code
    ("12,50 USD"). Cents and a currency in, text out; nothing is ever converted.
    """
    whole, part = divmod(abs(int(cents)), 100)
    digits = f"{whole:,}".replace(",", ".")
    sign = "-" if cents < 0 else ""
    return f"{sign}{digits},{part:02d}{NO_BREAK}{rules.CURRENCY_SIGNS.get(currency, currency)}"


def day(value: date | datetime, year: bool | None = None) -> str:
    """A date as the game's page writes it: "11 Oct", or "11 Oct 2025" in another year.

    `year` True always writes it ("3 May 2026", for a purchase, which is read long after);
    a moment with an offset is read in local time first.
    """
    if isinstance(value, datetime):
        value = (value.astimezone() if value.tzinfo else value).date()
    show_year = year if year is not None else value.year != date.today().year
    return f"{value.day} {value:%b}" + (f" {value.year}" if show_year else "")
