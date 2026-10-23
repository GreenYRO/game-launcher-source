"""Missing covers, filled in one go (Phase 105): which games, the batch on SteamGridDB, and its words.

"Find online" finds one game's cover, picked by hand from a list. This does the same for every game the grid shows
without one -- not hidden, not marked a tool or a demo, no cover set by hand -- with the same gate and no picking:
the name must clear rules.SGDB_MATCH_RATIO (0.85, the gate that keeps Eden from becoming Tiny Eden, Phase 6), and
the cover is the first tall static grid, the image Find online downloads for a SteamGridDB match.

No Qt and no writing here: `run` is a plain loop that adapters/cover_fill_worker.py runs on a thread of its own,
handing each cover found back to the window, which writes it as Find online does. Paced: every request waits
rules.SGDB_REQUEST_GAP_SECONDS after the one before, and a name the cache already knows -- found or missed -- costs
none, nor does an image already on disk. SteamGridDB asking to slow down (HTTP 429) is honoured: its Retry-After,
or rules.SGDB_BACKOFF_SECONDS, then the request once more; a second 429, or a Retry-After longer than
SGDB_RETRY_AFTER_MAX_SECONDS, stops the batch, as does a SteamGridDB that gives no answer -- and nothing is cached
as a miss for an answer not given. Cancel lets the game under way finish, then stops; a wait ends at once.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable

from shared import rules
from web import steamgriddb

log = logging.getLogger(__name__)

UNMATCHED = "unmatched"  # no name on SteamGridDB close enough
NO_IMAGE = "no image"  # matched, with no tall cover there
CANCELLED = "cancelled"
SLOW_DOWN = "slow down"
UNREACHABLE = "unreachable"
KEY_REFUSED = "key"


@dataclass
class Outcome:
    """How a batch went: the names in each kind, why it stopped ("" when it ran to the end), its requests."""

    total: int
    found: list[str] = field(default_factory=list)
    unmatched: list[str] = field(default_factory=list)
    no_image: list[str] = field(default_factory=list)
    stopped: str = ""
    requests: int = 0

    @property
    def done(self) -> int:
        return len(self.found) + len(self.unmatched) + len(self.no_image)


class _Stop(Exception):
    def __init__(self, why: str) -> None:
        super().__init__(why)
        self.why = why


def missing(views) -> list:
    """The games the grid shows with no cover, by name: not hidden, not a tool or a demo, none set by hand (a
    chosen file since gone stays the user's, for Find online)."""
    return sorted((v for v in views if not v.hidden and not v.is_non_game and not v.cover_source
                   and not v.cover_chosen), key=lambda v: v.display_name.casefold())


def row_words(count: int, key_ok: bool, network_ok: bool) -> tuple[str, bool]:
    """Settings' Missing covers row: what it says, and whether its button can be pressed."""
    if not count:
        return "Every game has a cover.", False
    have = f"{count} game{'s' if count != 1 else ''} {'have' if count != 1 else 'has'} no cover."
    if not key_ok:
        return f"{have} Add a SteamGridDB key above to look them up.", False
    if not network_ok:
        return f"{have} Turn on Allow network lookups to look them up.", False
    return have, True


def run(games: list[tuple[str, str]], key: str, cache_dir: str, *, pause: Callable[[float], None],
        wait: Callable[[float], bool], stopped: Callable[[], bool],
        progress: Callable[[int, str], None] = lambda index, name: None,
        found: Callable[[str, str], None] = lambda game, path: None,
        missed: Callable[[str, str], None] = lambda game, why: None) -> Outcome:
    """Look each game up, in order: (identity key, name) pairs. `pause` keeps the gap between two requests, `wait`
    waits out a 429 and answers False when Cancel ended it, `stopped` says whether Cancel was pressed -- asked
    before each game. `found` gets (identity key, image path), `missed` (identity key, why)."""
    outcome = Outcome(total=len(games))

    def ask(call):
        """One request, paced; a 429 waited out and asked once more."""
        if outcome.requests:
            pause(rules.SGDB_REQUEST_GAP_SECONDS)
        outcome.requests += 1
        try:
            return call()
        except steamgriddb.RateLimited as first:
            seconds = first.retry_after if first.retry_after is not None else rules.SGDB_BACKOFF_SECONDS
            if seconds > rules.SGDB_RETRY_AFTER_MAX_SECONDS:
                log.warning("fill covers: SteamGridDB asked for %g s; stopping rather than waiting", seconds)
                raise _Stop(SLOW_DOWN) from None
            log.info("fill covers: SteamGridDB asked us to slow down; waiting %g s, then once more", seconds)
            if not wait(seconds):
                raise _Stop(CANCELLED) from None
            outcome.requests += 1
            try:
                return call()
            except steamgriddb.RateLimited:
                raise _Stop(SLOW_DOWN) from None
        except steamgriddb.NoAnswer as exc:
            raise _Stop(KEY_REFUSED if exc.why == "key" else UNREACHABLE) from None

    for index, (game, name) in enumerate(games):
        if stopped():
            outcome.stopped = CANCELLED
            break
        progress(index, name)
        try:
            game_id = steamgriddb.known_game_id(name, cache_dir)
            if game_id is None:
                game_id = ask(lambda: steamgriddb.resolve_game_id(name, key, cache_dir, strict=True))
            if not game_id:
                outcome.unmatched.append(name)
                missed(game, UNMATCHED)
                continue
            path = steamgriddb.cover_on_disk(game_id, cache_dir)
            if not path:
                url = ask(lambda: steamgriddb.cover_url(game_id, key, strict=True))
                path = ask(lambda: steamgriddb.download_cover(game_id, url, cache_dir)) if url else ""
            if not path:
                outcome.no_image.append(name)
                missed(game, NO_IMAGE)
                continue
            outcome.found.append(name)
            found(game, path)
        except _Stop as stop:
            outcome.stopped = stop.why
            break
    log.info("fill covers: %d of %d found, %d not matched, %d with no tall cover, %d request(s)%s",
             len(outcome.found), outcome.total, len(outcome.unmatched), len(outcome.no_image), outcome.requests,
             f"; stopped ({outcome.stopped})" if outcome.stopped else "")
    return outcome


def _names(names: list[str]) -> str:
    shown = names[: rules.FILL_COVERS_NAMED_MAX]
    more = len(names) - len(shown)
    text = ", ".join(shown)
    return f"{text} and {more} more" if more else text


def summary(outcome: Outcome) -> str:
    """The batch's last words, as the dialog shows them."""
    covers = len(outcome.found)
    found_line = f" Covers found for {covers}." if covers else ""
    if outcome.stopped == SLOW_DOWN:
        return f"SteamGridDB asked us to slow down; {outcome.done} done, try again later.{found_line}"
    if outcome.stopped == UNREACHABLE:
        return f"SteamGridDB could not be reached; {outcome.done} done, try again later.{found_line}"
    if outcome.stopped == KEY_REFUSED:
        return f"SteamGridDB refused the key; check it with Test.{found_line}"
    if outcome.stopped == CANCELLED:
        return f"Stopped after {outcome.done} of {outcome.total}.{found_line}"
    words = f"Found covers for {covers} of {outcome.total}."
    if outcome.unmatched:
        words += (f" Not matched: {_names(outcome.unmatched)} (name too unlike anything on SteamGridDB; try Find "
                  "online from the game's menu).")
    if outcome.no_image:
        words += (f" No tall cover on SteamGridDB for {_names(outcome.no_image)}; try Find online from the game's "
                  "menu.")
    return words
