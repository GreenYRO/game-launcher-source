"""What's new (Phase 106): a version's release notes, read from the files the build carries, and when a start shows
them.

Every release writes docs/release-notes/<version>.md before it is built -- the Romanian under "## Română", the
English under "## English" -- and its GitHub page is made from that file, so the two never differ. The build refuses
a version without one (`ready`). The launcher shows the English (`section`), as every word of it is English: once,
on the first start after an update (`due`: the version last seen is another one -- never on a first run, whose
questions come first, and never when no version was ever written), and in Settings, About, at any time.

The notes published for 1.2.6 to 1.2.9 marked their two languages with bold labels and a rule between them; those
are read too, so a release page cached from before the files is shown by the same code.
"""

from __future__ import annotations

import logging
from pathlib import Path

from shared import paths, rules, version

log = logging.getLogger(__name__)

ROMANIAN, ENGLISH = rules.RELEASE_NOTES_HEADINGS
LABELS = {ROMANIAN: "**Română**", ENGLISH: "**English**"}  # how 1.2.6-1.2.9 were published


def notes_dir() -> Path:
    """Where the notes are: the project's docs/release-notes from source, the same place under the bundle's
    resources in an installed copy."""
    return paths.resource_dir().joinpath(*rules.RELEASE_NOTES_DIR)


def notes_file(number: str, folder: Path | None = None) -> Path:
    return (folder or notes_dir()) / f"{number}.md"


def read(number: str, folder: Path | None = None) -> str:
    """A version's notes file as it is, or "" when this copy has none."""
    path = notes_file(number, folder)
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    except (OSError, UnicodeDecodeError) as exc:
        log.warning("what's new: %s could not be read (%s)", path, exc)
        return ""


def _starts(line: str) -> str | None:
    """The language a line opens, as a heading or as the published labels -- or None."""
    stripped = line.strip()
    for heading, label in LABELS.items():
        if stripped in (heading, label):
            return heading
    return None


def section(text: str, heading: str = ENGLISH) -> str:
    """The text under one language's heading, up to the next one (or a rule before it). A text with neither
    heading -- the releases before 1.2.6, in one language -- is shown whole."""
    lines = (text or "").replace("\r\n", "\n").split("\n")
    opened = [_starts(line) for line in lines]
    if not any(opened):
        return (text or "").strip()
    if heading not in opened:
        return ""
    start = opened.index(heading) + 1
    end = next((i for i in range(start, len(lines)) if opened[i]), len(lines))
    body = lines[start:end]
    while body and body[-1].strip() in ("", "---"):
        body.pop()
    return "\n".join(body).strip()


def ready(number: str, folder: Path | None = None) -> tuple[bool, str]:
    """May this version be built? (True, "") when its notes file is there with both headings and text under each;
    else (False, why) -- the build says it and stops."""
    path = notes_file(number, folder)
    if not path.is_file():
        return False, f"no release notes for {number}: write {path} first, both languages"
    text = read(number, folder)
    for heading in rules.RELEASE_NOTES_HEADINGS:
        if heading not in (line.strip() for line in text.splitlines()):
            return False, f"{path.name} has no '{heading}' heading"
        if not section(text, heading):
            return False, f"{path.name} has nothing under '{heading}'"
    return True, ""


def due(config: dict, first_run: bool) -> bool:
    """The first start after an update: a version was seen, and it is another one. Never a first run's."""
    seen = config.get(rules.VERSION_SEEN_KEY)
    return not first_run and isinstance(seen, str) and bool(seen.strip()) and seen != version.APP_VERSION


def english(number: str | None = None, folder: Path | None = None) -> str:
    """The English notes of a version this copy carries (this one's by default) -- "" when it carries none."""
    return section(read(number or version.APP_VERSION, folder))
