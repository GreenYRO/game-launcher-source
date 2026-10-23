"""Turning a folder name and a PE version resource into something worth showing a human."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from shared import rules

_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_MULTISPACE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Lowercase, alphanumerics only. Used for similarity, never for display."""
    return _NON_ALNUM.sub("", text.casefold())


def similarity(left: str, right: str) -> float:
    a, b = normalize(left), normalize(right)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def clean_folder_name(folder_name: str) -> str:
    """Strip release-scene noise and version numbers from a directory name.

    Version patterns are removed first, while the dots that delimit them are still
    present -- "Arctic.Awakening.v1.0.19-P2P" only parses as a version if you look
    before separators are flattened.
    """
    text = folder_name
    for pattern in rules.NAME_STRIP_PATTERNS:
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE)

    for separator in rules.NAME_SEPARATORS:
        text = text.replace(separator, " ")
    text = _MULTISPACE.sub(" ", text).strip()

    text = _drop_tokens(text)
    text = _MULTISPACE.sub(" ", text).strip(" -")

    if not text:
        return folder_name.strip()
    return _smart_title(text)


def _drop_tokens(text: str) -> str:
    """Remove scene tags as whole words, longest phrase first."""
    for token in sorted(rules.NAME_STRIP_TOKENS, key=len, reverse=True):
        text = re.sub(rf"(?<!\w){re.escape(token)}(?!\w)", " ", text, flags=re.IGNORECASE)
    return text


def _smart_title(text: str) -> str:
    """Capitalise only if the name carries no capitalisation of its own.

    Title-casing everything would turn "BeamNG Drive" into "Beamng Drive" and
    "LEGO Batman Legacy of the Dark Knight" into a sea of capitalised prepositions.
    """
    if any(ch.isupper() for ch in text):
        return text
    return " ".join(word[:1].upper() + word[1:] for word in text.split(" "))


def sanitize_title(value: str | None) -> str | None:
    """Strip trademark symbols and tidy whitespace. Used for PE names and Steam titles."""
    if not value:
        return None
    cleaned = value
    for ch in rules.NAME_TRIM_CHARS:
        cleaned = cleaned.replace(ch, "")
    cleaned = _MULTISPACE.sub(" ", cleaned).strip(" -_")
    return cleaned or None


def accept_pe_name(pe_name: str, folder_clean: str) -> tuple[bool, str]:
    """Decide whether a PE name beats the cleaned folder name. Returns (accept, why).

    Two guards, both derived from what the games on this machine actually report:
      * a name unrelated to the folder is an internal codename (Khazan's exe says "KZ");
      * a run-together name is a build identifier, so a spaced, longer folder name that
        says more wins ("LEGOBatmanLotDK" loses to "LEGO Batman Legacy of the Dark Knight").
    """
    ratio = similarity(pe_name, folder_clean)
    if ratio < rules.PE_NAME_ACCEPT_RATIO:
        return False, f"unrelated to folder name (ratio {ratio:.2f})"

    if rules.PE_NAME_REJECT_IF_SQUASHED:
        squashed = " " not in pe_name.strip()
        folder_is_richer = " " in folder_clean and len(folder_clean) > len(pe_name)
        if squashed and folder_is_richer:
            return False, "looks like an internal build name; folder name says more"

    return True, f"matches folder name (ratio {ratio:.2f})"


def title_words(name: str) -> list[str]:
    """A name as the words that make it that game: no punctuation, edition or leading "The".

    Runs of single letters are one word, so "S.T.A.L.K.E.R. 2" and a packaged build's
    "s.t.a.l.k.e.r.2" both read as "stalker 2".
    """
    joined: list[str] = []
    run = ""
    for word in re.findall(r"[a-z0-9]+", name.casefold()):
        if len(word) == 1 and word.isalpha():
            run += word
            continue
        if run:
            joined.append(run)
            run = ""
        joined.append(word)
    if run:
        joined.append(run)
    text = f" {' '.join(joined)} "
    for phrase in sorted(rules.TITLE_EDITION_PHRASES, key=len, reverse=True):
        text = text.replace(f" {phrase} ", " ")
    words = text.split()
    if len(words) > 1 and words[0] == "the":
        words = words[1:]
    return words


def same_title(left: str, right: str) -> bool:
    """Whether two names are one game, give or take an edition or a subtitle.

    One must start with every word of the other ("The Witcher 3" and "The Witcher 3: Wild
    Hunt"), a one-word name must match whole, and a number right after the shared words
    makes a sequel, not a new version ("Far Cry 3"). It is a question put to the user,
    never a decision taken for them -- "Silent Hill" would still match "Silent Hill
    Townfall".
    """
    a, b = title_words(left), title_words(right)
    if not a or not b:
        return False
    if "".join(a) == "".join(b):
        return True  # the same letters, spaced or punctuated differently
    short, long = sorted((a, b), key=len)
    if long[: len(short)] != short or len(short) < rules.TITLE_MIN_PREFIX_WORDS:
        return False
    following = long[len(short)]
    return not (following.isdigit() or following in rules.TITLE_SEQUEL_NUMERALS)


def choose_display_name(
    product_name: str | None,
    file_description: str | None,
    folder_clean: str,
) -> tuple[str, str]:
    """Pick the display name. Returns (name, origin) where origin explains the choice."""
    for label, raw in (("ProductName", product_name), ("FileDescription", file_description)):
        candidate = sanitize_title(raw)
        if not candidate:
            continue
        ok, why = accept_pe_name(candidate, folder_clean)
        if ok:
            return candidate, f"pe:{label} ({why})"
    return folder_clean, "folder"
