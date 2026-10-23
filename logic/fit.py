"""How like what is played a game is (Phase 89; shared since Phase 98): content-based filtering on genres.

The one place the maths lives. The Wishlist page (logic/wishlist.py) orders a list the user already chose
by it; For you (logic/recommend.py) ranks what is installed and not started yet by it. Both say the same
words, because they are the same function.

Each genre weighs by how rare it is among the apps the library knows -- its inverse document frequency
(TF-IDF): a genre most games have says little about a game. A game is the vector of its genres' weights,
of length 1; what is played is one such vector, every game's weighted by its minutes and summed (`taste`);
the fit is the cosine of the two -- 1 the same mix of genres as the hours, 0 none in common. Before Phase
89 the share of the hours on games sharing a genre was used, and with Action in 87% of the hours nearly
every game read 87-99%. **A fit is similarity of genre mix, never a forecast of liking.** A game whose
record has not been fetched has no genres, and says so: unknown is not zero. No SQL here, no Qt.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from shared import rules


@dataclass(frozen=True)
class Fit:
    """How like what is played a game is: a score from 0 to 1 (None when it cannot be said) and its words."""
    share: float | None
    words: str


NOT_FETCHED = "not fetched yet"
NO_GENRE = "no genre to compare"
NOTHING_PLAYED = "nothing played to compare with"


def profile_of(rows) -> dict[int, tuple[float, frozenset]]:
    """The wishlist_profile query's rows -- a game, its minutes, one of its genres -- by game."""
    minutes, genres = {}, {}
    for row in rows:
        appid = row["appid"]
        minutes[appid] = float(row["minutes"] or 0)
        genres.setdefault(appid, set()).add(row["genre_id"])
    return {appid: (minutes[appid], frozenset(genres[appid])) for appid in minutes}


def profile_from(games, genre_rows) -> dict[int, tuple[float, frozenset]]:
    """The same profile as `profile_of` makes of the wishlist_profile query, from rows that already hold each
    played app's minutes -- report 1's, the same games (GAMES, minutes over 0) -- and the genre rows of the
    apps (the ones never compared left out). Report 9 is built beside report 1 and need not read the hours a
    second time: the reports must stay under 50 ms together (Phase 98; a test holds the two equal)."""
    genres: dict[int, set] = {}
    for row in genre_rows:
        genres.setdefault(row["appid"], set()).add(row["genre_id"])
    return {g["appid"]: (float(g["minutes"] or 0), frozenset(genres[g["appid"]])) for g in games
            if g["appid"] is not None and (g["minutes"] or 0) > 0 and g["appid"] in genres}


def weights_of(rows) -> dict[int, float]:
    """Each genre's weight, from the wishlist_idf query: ln(apps with any genre / apps with this one),
    the inverse document frequency (IDF). A genre every app has weighs nothing; one few have, much."""
    return {row["genre_id"]: math.log(row["corpus"] / row["apps"]) for row in rows
            if row["apps"] and row["corpus"]}


def vector(genres, weights: dict[int, float]) -> dict[int, float]:
    """A game's genres as a vector of their weights, of length 1 -- empty when they weigh nothing."""
    weighed = {g: weights.get(g, 0.0) for g in genres}
    norm = math.sqrt(sum(x * x for x in weighed.values()))
    return {g: x / norm for g, x in weighed.items() if x} if norm else {}


def taste(profile: dict[int, tuple[float, frozenset]], weights: dict[int, float]) -> dict[int, float]:
    """What is played as one vector: every game's genre vector times its minutes, summed, of length 1."""
    total: dict[int, float] = {}
    for minutes, genres in profile.values():
        for g, x in vector(genres, weights).items():
            total[g] = total.get(g, 0.0) + minutes * x
    norm = math.sqrt(sum(x * x for x in total.values()))
    return {g: x / norm for g, x in total.items()} if norm else {}


def like_words(score: float, what: str = "what you play") -> str:
    """A score in words: "72% like what you play", "under 1% like ...", "unlike ..." -- never "0%"."""
    if score <= 0:
        return f"unlike {what}"
    if score < 0.005:
        return f"under 1% like {what}"
    return f"{round(score * 100)}% like {what}"


def fit(item_genres, profile: dict[int, tuple[float, frozenset]], has_record: bool, weights: dict[int, float],
        played: dict[int, float] | None = None) -> Fit:
    """One game against what is played. `item_genres` is its (genre id, name) pairs.

    Content-based filtering with TF-IDF and cosine similarity: the game's genre vector (each genre
    its rarity weight, the vector of length 1) dotted with the vector of what is played (`taste`,
    every game's vector times its minutes). 1 is the same mix of genres as the hours; 0 none in
    common. A genre most games have counts for little -- Action was 87% of the hours, and every
    Action game read 87-99% before (Phase 89). The genres that add the most are named.
    """
    if not has_record:
        return Fit(None, NOT_FETCHED)
    named = dict(item_genres)
    if not named:
        return Fit(None, NO_GENRE)
    played = taste(profile, weights) if played is None else played
    if not played:
        return Fit(None, NOTHING_PLAYED)
    game = vector(named, weights)
    if not game:
        return Fit(None, NO_GENRE)  # only genres every app has: nothing to tell it apart by
    parts = {g: x * played.get(g, 0.0) for g, x in game.items()}
    score = min(1.0, sum(parts.values()))
    most = [g for g in sorted(parts, key=lambda g: (-parts[g], named[g].casefold())) if parts[g] > 0]
    shown = most[: rules.WISHLIST_FIT_GENRES_NAMED] or sorted(named, key=lambda g: named[g].casefold())
    return Fit(score, f"{like_words(score)} · {', '.join(named[g] for g in shown)}")


def share_of(game: dict[int, float], played: dict[int, float]) -> float:
    """The fit's score alone: a game's vector (`vector`) against what is played (`taste`), as `fit` works it
    out before its words. Ranking many games at once needs only this (report 9's look back, Phase 98)."""
    return min(1.0, sum(x * played.get(g, 0.0) for g, x in game.items()))
