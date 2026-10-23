"""What the library is costing in disk space, grouped by the drive it sits on.

No Qt and no deleting: this module answers questions, and Phase 24 can do nothing else.

**Sizes come from the catalogue, not from the disk.** Walking 1 TB of games to add up
their bytes would take minutes and would happen every time the page opened; the scan has
already done that work and stored it. The consequence is that the page is only as current
as the last scan, which is why `scanned_at` is carried here and stated on the page rather
than left for the user to discover when a number looks stale.

**Free space, by contrast, is read live** through `shutil.disk_usage` -- it costs nothing,
it changes constantly, and a stale free-space figure is the one number on the page that
would actually mislead someone deciding what to delete.
"""

from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime

from data_access import catalog_io
from shared import rules

log = logging.getLogger(__name__)

SORT_SIZE = "size"
SORT_WEIGHTED = "weighted"
SORT_MODES = (SORT_SIZE, SORT_WEIGHTED)

UNKNOWN_DRIVE = "?"


@dataclass(frozen=True)
class GameSize:
    """One game's footprint, and how long it has sat there unplayed."""

    key: str
    name: str
    bytes: int
    last_played: datetime | None
    # Days since it was last played, or -- for a game never played -- days since the
    # launcher first saw it. Both come from overrides; neither is a guess about when the
    # game was installed, which nothing here knows.
    idle_days: int | None
    ever_played: bool

    @property
    def stale(self) -> bool:
        return self.idle_days is not None and self.idle_days >= rules.RECLAIM_STALE_DAYS

    @property
    def weight(self) -> float:
        """Size, pushed up by how long it has been sitting there.

        A game twice as cold as another of the same size sorts above it, but size still
        dominates: the question this page answers is "what frees the most room", and a
        200 MB game nobody has touched in a year does not answer it.
        """
        idle = self.idle_days or 0
        return self.bytes * (1.0 + idle / rules.RECLAIM_WEIGHT_DAYS)


@dataclass(frozen=True)
class Drive:
    letter: str
    total: int
    used: int
    free: int
    games: list[GameSize] = field(default_factory=list)
    # False when Windows would not answer for the drive -- an unplugged card reader, a
    # disconnected network path. The games are still listed; the capacity bar is not,
    # because a bar drawn from zeroes would read as a full disk.
    measured: bool = True

    @property
    def known_bytes(self) -> int:
        return sum(game.bytes for game in self.games)

    @property
    def other_used(self) -> int:
        """Used space that is not a game this launcher knows about."""
        return max(0, self.used - self.known_bytes)

    @property
    def biggest(self) -> int:
        return max((game.bytes for game in self.games), default=0)


@dataclass(frozen=True)
class Storage:
    drives: list[Drive] = field(default_factory=list)
    scanned_at: datetime | None = None
    missing_sizes: int = 0
    sort_mode: str = SORT_SIZE

    @property
    def games(self) -> list[GameSize]:
        return [game for drive in self.drives for game in drive.games]

    @property
    def known_bytes(self) -> int:
        return sum(drive.known_bytes for drive in self.drives)

    @property
    def reclaimable(self) -> list[GameSize]:
        return sorted((g for g in self.games if g.stale), key=lambda g: -g.bytes)

    @property
    def reclaimable_bytes(self) -> int:
        return sum(game.bytes for game in self.reclaimable)


def _worst(row: list[float], side: float) -> float:
    """The worst aspect ratio in a row laid along `side`. Lower is squarer."""
    if not row:
        return float("inf")
    total = sum(row)
    if total <= 0 or side <= 0:
        return float("inf")
    return max(
        (side * side * max(row)) / (total * total),
        (total * total) / (side * side * min(row)),
    )


def squarify(values, x: float, y: float, w: float, h: float) -> list[tuple]:
    """Squarified treemap (Bruls, Huizing and van Wijk): one rect per value, filling the box.

    `values` must be descending. Returns (x, y, w, h) tuples in the same order.

    **Two details are the whole algorithm, and getting either wrong produces stripes.**
    `side` is fixed for the length of a row -- recomputing it inside the row loop changes
    the basis mid-comparison, and the first attempt at this laid 13 of 21 games out as
    unlabelable bands because of it. And a row is laid along the *shorter* side of what is
    left, which is what keeps the rectangles square as the remaining area narrows.
    """
    out: list[tuple] = []
    values = list(values)
    total = sum(values)
    if total <= 0 or w <= 0 or h <= 0:
        return [(x, y, 0.0, 0.0) for _ in values]
    areas = [value * (w * h) / total for value in values]

    index = 0
    while index < len(areas):
        side = min(w, h)
        row = [areas[index]]
        end = index + 1
        while end < len(areas) and _worst(row + [areas[end]], side) <= _worst(row, side):
            row.append(areas[end])
            end += 1
        filled = sum(row)
        if w >= h:  # the row runs down the left edge
            row_w = filled / h if h else 0.0
            cursor = y
            for area in row:
                row_h = area / row_w if row_w else 0.0
                out.append((x, cursor, row_w, row_h))
                cursor += row_h
            x += row_w
            w -= row_w
        else:  # the row runs along the top edge
            row_h = filled / w if w else 0.0
            cursor = x
            for area in row:
                row_w = area / row_h if row_h else 0.0
                out.append((cursor, y, row_w, row_h))
                cursor += row_w
            y += row_h
            h -= row_h
        index = end
    return out


def drive_of(view) -> str:
    """The drive letter a game lives on, uppercase and with its colon."""
    target = view.entry.install_dir or view.launch_target or ""
    if not target:
        return UNKNOWN_DRIVE
    letter = os.path.splitdrive(os.path.abspath(target))[0]
    return letter.upper() if letter else UNKNOWN_DRIVE


def _disk_usage(letter: str):
    """(total, used, free, measured). Never raises: a drive that will not answer is not
    a reason for the page to fail."""
    if letter == UNKNOWN_DRIVE:
        return 0, 0, 0, False
    try:
        total, used, free = shutil.disk_usage(letter + os.sep)
    except OSError as exc:
        log.warning("could not measure %s: %s", letter, exc)
        return 0, 0, 0, False
    return total, used, free, True


def _idle_days(view, record: dict, now: datetime) -> tuple[int | None, bool]:
    played = view.last_played
    if played is not None:
        return max(0, (now - played).days), True
    raw = record.get("first_seen")
    if isinstance(raw, str):
        try:
            seen = datetime.fromisoformat(raw)
        except ValueError:
            log.warning("unreadable first_seen %r for %s", raw, view.key)
            return None, False
        if seen.tzinfo is None:
            seen = seen.astimezone()
        return max(0, (now - seen).days), False
    return None, False


def catalog_written_at(store=None) -> datetime | None:
    """When the sizes on this page were last measured."""
    # The store owns when the last scan was written (Phase 64): the newest scan's row in
    # the database (Phase 69), the catalogue's own time in the JSON store.
    return catalog_io.last_scan_time() if store is None else store.last_scan_time()


def gather(views, overrides, now: datetime | None = None, sort_mode: str = SORT_SIZE) -> Storage:
    """Group the visible library by drive, biggest first."""
    moment = now or datetime.now().astimezone()
    if sort_mode not in SORT_MODES:
        log.warning("unknown sort mode %r; falling back to %s", sort_mode, SORT_SIZE)
        sort_mode = SORT_SIZE

    # The same pool the grid shows, so the page never accounts for a game the user has
    # hidden and cannot see.
    by_drive: dict[str, list[GameSize]] = {}
    missing = 0
    for view in views:
        if view.hidden or view.is_non_game:
            continue
        size = max(0, view.entry.size_on_disk or 0)
        if not size:
            missing += 1
        record = overrides.get(view.key)
        idle, ever = _idle_days(view, record, moment)
        by_drive.setdefault(drive_of(view), []).append(
            GameSize(
                key=view.key,
                name=view.display_name,
                bytes=size,
                last_played=view.last_played,
                idle_days=idle,
                ever_played=ever,
            )
        )

    order = (lambda g: -g.weight) if sort_mode == SORT_WEIGHTED else (lambda g: -g.bytes)
    drives = []
    for letter in sorted(by_drive):
        total, used, free, measured = _disk_usage(letter)
        drives.append(
            Drive(
                letter=letter,
                total=total,
                used=used,
                free=free,
                games=sorted(by_drive[letter], key=order),
                measured=measured,
            )
        )
    # Drives holding the most of our games first; an unmeasurable one sinks to the bottom.
    drives.sort(key=lambda d: (not d.measured, -d.known_bytes))

    log.info(
        "storage: %d drive(s), %d games, %d bytes known, %d without a size",
        len(drives),
        sum(len(d.games) for d in drives),
        sum(d.known_bytes for d in drives),
        missing,
    )
    return Storage(
        drives=drives,
        scanned_at=catalog_written_at(overrides),
        missing_sizes=missing,
        sort_mode=sort_mode,
    )
