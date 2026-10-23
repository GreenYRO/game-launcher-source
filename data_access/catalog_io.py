"""Reading the generated catalog, and the user's edits that sit on top of it.

Two files, deliberately separate. catalog.json is disposable and rewritten by every scan.
overrides.json holds everything the user would be upset to lose -- renames, a hand-picked
exe, launch arguments, hidden flags, playtime -- and discovery never writes to it. They are
married at load time by identity key, and the override always wins.
"""

from __future__ import annotations

import copy
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from data_access import backups
from shared import paths
from shared import rules
from shared.models import GameEntry

log = logging.getLogger(__name__)

CATALOG_PATH = paths.data_dir() / "catalog.json"
OVERRIDES_PATH = paths.data_dir() / "overrides.json"

OVERRIDES_VERSION = 1


# -- catalog -----------------------------------------------------------------------------


def load_catalog(path: Path = CATALOG_PATH) -> list[GameEntry]:
    if not path.is_file():
        log.info("no catalog at %s yet", path)
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.error("could not read catalog %s: %s", path, exc)
        return []

    entries: list[GameEntry] = []
    for raw in payload.get("entries", []):
        try:
            entries.append(GameEntry.from_dict(raw))
        except (TypeError, KeyError, ValueError) as exc:
            log.error("skipping malformed catalog entry %r: %s", raw.get("display_name"), exc)
    # Art the scan found in the launcher's own cache, with the folder it was in then. Found
    # again here, once, if the project has moved since (Phase 37) -- the next scan writes
    # the new paths -- rather than on every repaint of a tile.
    return relocate_entries(entries)


def relocate_entries(entries: list[GameEntry]) -> list[GameEntry]:
    """The catalogue's own art paths found again after a move -- for any store's catalogue."""
    for entry in entries:
        if _is_artwork(entry.icon_hint):
            entry.icon_hint = relocated(entry.icon_hint)
        banner = entry.extra.get("banner")
        if isinstance(banner, str) and banner:
            entry.extra["banner"] = relocated(banner)
    return entries


def read_catalog_header(path: Path = CATALOG_PATH) -> dict:
    """When the catalogue was written and which folders it walked -- {} if there is none.

    For the migration (Phase 67), which keeps both on the scan it brings in.
    """
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.error("could not read catalog %s: %s", path, exc)
        return {}
    if not isinstance(payload, dict):
        return {}
    return {name: payload[name] for name in ("generated_at", "roots", "entry_count") if name in payload}


def save_catalog(entries: list[GameEntry], path: Path = CATALOG_PATH, roots=()) -> None:
    payload = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "roots": list(roots),
        "entry_count": len(entries),
        "entries": [entry.to_dict() for entry in entries],
    }
    _atomic_write(path, json.dumps(payload, indent=2, ensure_ascii=False))


def last_scan_time(path: Path = CATALOG_PATH) -> datetime | None:
    """When the last scan's findings were written -- what "sizes as of" means on Storage."""
    try:
        stamp = path.stat().st_mtime
    except OSError as exc:
        log.info("no catalogue timestamp available: %s", exc)
        return None
    return datetime.fromtimestamp(stamp).astimezone()


# -- overrides ---------------------------------------------------------------------------


class Overrides:
    """The user's edits, keyed by GameEntry.identity_key."""

    def __init__(self, path: Path = OVERRIDES_PATH) -> None:
        self.path = path
        self.games: dict[str, dict[str, Any]] = {}
        self.load()

    def load(self) -> None:
        if not self.path.is_file():
            log.info("no overrides at %s yet; starting empty", self.path)
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.error("could not read overrides %s: %s -- leaving them alone", self.path, exc)
            return
        games = payload.get("games") if isinstance(payload, dict) else None
        if not isinstance(games, dict):
            log.error("overrides %s has no 'games' object; starting empty", self.path)
            return
        self.games = {k: v for k, v in games.items() if isinstance(v, dict)}
        log.info("loaded %d override record(s)", len(self.games))

    def get(self, key: str) -> dict[str, Any]:
        return self.games.get(key, {})

    def update(self, key: str, **values: Any) -> None:
        """Set fields for one game and persist. Values of None remove the field."""
        record = self.games.setdefault(key, {})
        for name, value in values.items():
            if value is None:
                record.pop(name, None)
            else:
                record[name] = value
        if not record:
            self.games.pop(key, None)
        self.save()

    # -- named operations (Phase 64) --------------------------------------------------------
    # What the rest of the program used to do by reaching into `games` itself. Each is one
    # write at most -- in the database to come, one transaction -- and each hands out the
    # same live record dicts `get` does, which the views read.

    def values_of(self, name: str) -> dict[str, Any]:
        """Every record's value of one field, for the records that hold it."""
        return {key: record[name] for key, record in self.games.items() if name in record}

    def uncarried(self) -> list[tuple[str, dict[str, Any]]]:
        """Every record whose history was not carried over to a newer install (Phase 36)."""
        return [(key, record) for key, record in self.games.items()
                if not record.get(rules.CARRIED_TO_KEY)]

    def update_many(self, changes: dict[str, dict[str, Any]]) -> None:
        """`update` for several games, written once. Values of None remove the field."""
        for key, values in changes.items():
            record = self.games.setdefault(key, {})
            for name, value in values.items():
                if value is None:
                    record.pop(name, None)
                else:
                    record[name] = value
            if not record:
                self.games.pop(key, None)
        if changes:
            self.save()

    def carry(self, old_key: str, new_key: str, *, old_record: dict[str, Any],
              new_record: dict[str, Any]) -> None:
        """Both halves of carrying a history over, written together, never one alone.

        The new game's record becomes `new_record` in place -- its views hold that dict --
        and the old one is replaced by what stays on it.
        """
        record = self.games.setdefault(new_key, {})
        record.clear()
        record.update(new_record)
        self.games[old_key] = dict(old_record)
        self.save()

    def export_records(self) -> dict[str, dict[str, Any]]:
        """A copy of every record, for an export bundle (Phase 65): changing it changes nothing here."""
        return copy.deepcopy(self.games)

    def import_records(self, records: dict[str, dict[str, Any]]) -> bool:
        """Records from a bundle, each replacing this PC's whole record for its game, written once.

        The rules -- which side wins, how two session lists combine -- are transfer's, decided
        before this is called; this only stores. If the write fails, every record is put back
        as it was, so the store and the file never disagree. Returns whether it was written.
        """
        before = {key: copy.deepcopy(self.games[key]) for key in records if key in self.games}
        for key, values in records.items():
            record = self.games.setdefault(key, {})
            record.clear()
            record.update(values)
        if not records or self.save():
            return True
        for key in records:
            if key in before:
                self.games[key].clear()
                self.games[key].update(before[key])
            else:
                self.games.pop(key, None)
        log.error("the imported records could not be written; nothing was kept")
        return False

    # -- the catalogue, as the database store has it (Phase 69) ----------------------------
    # So the window speaks to either store the same way: the JSON one keeps the catalogue
    # in catalog.json, as it always has; a scan's trigger and start are the database's only.

    def load_catalog(self) -> list[GameEntry]:
        return load_catalog()

    def save_catalog(self, entries: list[GameEntry], roots=(), *, trigger: str = "manual",
                     started_at: str | None = None) -> bool:
        save_catalog(entries, roots=roots)
        return True

    def last_scan_time(self) -> datetime | None:
        return last_scan_time()

    def steam_fetched(self) -> None:
        """None: the JSON keeps no Steam projection, so a scan has nothing to bring up to date."""
        return None

    def close(self) -> None:
        """Nothing to let go of: the file is written whole, and closed, by every save."""

    def save(self) -> bool:
        payload = {"version": OVERRIDES_VERSION, "games": self.games}
        return _atomic_write(self.path, json.dumps(payload, indent=2, ensure_ascii=False))


def _atomic_write(path: Path, text: str) -> bool:
    """Temp file then replace, so a crash mid-save cannot truncate the real one.

    One implementation, in backups.py, shared with config.json -- the two files it
    protects are exactly the two that must never be written any other way.
    """
    return backups.atomic_write(path, text + "\n")


# -- the merged view the GUI actually shows ------------------------------------------------


@dataclass
class GameView:
    entry: GameEntry
    data: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return self.entry.identity_key

    @property
    def display_name(self) -> str:
        return self.data.get("name") or self.entry.display_name

    @property
    def is_renamed(self) -> bool:
        return bool(self.data.get("name"))

    @property
    def launch_target(self) -> str:
        return self.data.get("exe") or self.entry.launch_target

    @property
    def working_dir(self) -> str:
        """Always the chosen exe's own directory -- games resolve assets relative to it."""
        if self.entry.launch_kind == "uri":
            return self.entry.working_dir
        return os.path.dirname(self.launch_target)

    @property
    def args(self) -> str:
        return self.data.get("args", "")

    @property
    def hidden(self) -> bool:
        return bool(self.data.get("hidden"))

    @property
    def favorite(self) -> bool:
        """The user's own star.

        Stored on any game, including hidden ones and tools -- unstarring something just to
        hide it, then finding the star gone on unhiding, would be its own small annoyance.
        Nothing that *displays* favorites may use this alone: every chip and badge filters
        hidden entries and tools out first, so a starred tool never reappears through it.
        """
        return bool(self.data.get("favorite"))

    @property
    def status(self) -> str:
        """Where the user says they are with it: playing, finished, dropped -- or "".

        Anything else in the file (a hand edit, a future value) reads as unset rather than
        being shown as a mark nobody chose.
        """
        value = self.data.get(rules.STATUS_KEY)
        return value if value in rules.STATUSES else ""

    @property
    def status_since(self) -> str:
        """When the mark was set (Phase 101 dates it; version 8), as stored -- "" for no mark, or one set before."""
        value = self.data.get(rules.STATUS_CHANGED_KEY)
        return value if self.status and isinstance(value, str) else ""

    @property
    def notes(self) -> str:
        value = self.data.get(rules.NOTES_KEY)
        return value.strip() if isinstance(value, str) else ""

    @property
    def app_type(self) -> str:
        """Steam's own classification, once looked up. Empty for everything else."""
        return str(self.entry.extra.get("app_type") or "")

    @property
    def is_non_game(self) -> bool:
        """A demo, tool, soundtrack or similar.

        Three rules, in order:

        1. The user's own "mark as tool / mark as game" wins outright. They can see the
           thing running and Steam's classification cannot argue with that.
        2. A game whose appid came from a *name search* is never auto-hidden. That appid is
           a guess, however good the score, and a guess is not enough to make a game the
           user physically installed vanish from their library. The type is still recorded
           and shown on the detail page -- it just does not hide anything.
        3. Otherwise trust Steam: for an entry that came from a Steam manifest, the appid is
           certain and "demo" really means demo.
        """
        marked = self.data.get("is_tool")
        if marked is not None:
            return bool(marked)
        if self.entry.extra.get("appid_source") == rules.APPID_SOURCE_SEARCH:
            return False
        kind = self.app_type
        return bool(kind) and kind not in rules.STEAM_GAME_TYPES

    @property
    def matched_appid(self) -> str:
        """The appid this entry resolved to, whether from a manifest or by name search."""
        return str(self.data.get("appid") or self.entry.extra.get("appid") or "")

    @property
    def playtime_seconds(self) -> int:
        return int(self.data.get("playtime_seconds", 0))

    @property
    def last_played(self) -> datetime | None:
        played_here = _parse_time(self.data.get("last_played"))
        if played_here is not None:
            return played_here
        # Steam keeps its own LastPlayed in the manifest. Without this, a Steam game the
        # user plays regularly would read "never" until they happened to start it from
        # here. A launch through this launcher takes precedence once it happens.
        stamp = self.entry.extra.get("last_played_unix")
        if isinstance(stamp, int) and stamp > 0:
            try:
                return datetime.fromtimestamp(stamp).astimezone()
            except (OverflowError, OSError, ValueError) as exc:
                log.warning("bad LastPlayed %r for %s: %s", stamp, self.entry.display_name, exc)
        return None

    @property
    def first_seen(self) -> datetime | None:
        return _parse_time(self.data.get("first_seen"))

    @property
    def is_new(self) -> bool:
        """Found by a scan and not yet looked at -- the NEW tag on the tile.

        The stored flag is only half of it. It also lapses after NEW_BADGE_DAYS, and the
        moment the game has been played anywhere since it arrived: a Steam game started
        from Steam itself carries Steam's own LastPlayed, and has plainly been seen.
        """
        if not self.data.get(rules.NEW_KEY):
            return False
        arrived = self.first_seen
        if arrived is None:
            return False
        played = self.last_played
        if played is not None and played >= arrived:
            return False
        return datetime.now().astimezone() - arrived <= timedelta(days=rules.NEW_BADGE_DAYS)

    @property
    def icon_path(self) -> str:
        return self.launch_target if self.entry.launch_kind == "exe" else self.entry.icon_hint

    @property
    def cover_source(self) -> str:
        """The image to draw as this game's cover, or "" to draw a placeholder.

        A cover the user picked always wins; otherwise whatever the provider found. A
        chosen file that has since been deleted falls back rather than showing a blank.
        """
        chosen = self.data.get("cover")
        if isinstance(chosen, str) and chosen:
            if not os.path.isfile(chosen):
                chosen = relocated(chosen)  # the project folder may have moved (Phase 37)
            if os.path.isfile(chosen):
                return chosen
            log.warning("cover %s for %s is gone; falling back", chosen, self.display_name)
        hint = self.entry.icon_hint
        return hint if _is_artwork(hint) else ""

    @property
    def banner_source(self) -> str:
        """Wide art for the detail page, or "" to build one from the cover."""
        for candidate in (self.data.get("banner"), self.entry.extra.get("banner")):
            if isinstance(candidate, str) and candidate:
                if not os.path.isfile(candidate):
                    candidate = relocated(candidate)  # the project folder may have moved
                if os.path.isfile(candidate):
                    return candidate
        return ""

    @property
    def has_own_cover(self) -> bool:
        return bool(self.cover_source)

    @property
    def cover_chosen(self) -> bool:
        """A cover was set for it by hand -- found or not (Phase 105: the batch never writes over one)."""
        return bool(self.data.get("cover"))


def _is_artwork(path: str) -> bool:
    return bool(path) and os.path.splitext(path)[1].casefold() in rules.ARTWORK_EXTENSIONS


def relocated(path: str) -> str:
    """Where a file the launcher keeps itself is now, if the project folder has moved.

    Covers and banners are stored with full paths -- "C:\\Users\\andre\\Claude New\\cache\\
    sgdb_art\\4265.jpg" -- so renaming the project folder (Phase 37) would point every
    chosen picture at a folder that no longer exists. A path that is gone, and leads into
    one of the launcher's own folders (rules.OWN_DATA_FOLDERS), is looked for again under
    the current data folder. Anything else -- a picture picked from Downloads -- is left
    exactly as it is, found or not.
    """
    if not path or os.path.exists(path):
        return path
    parts = [part for part in path.replace("/", "\\").split("\\") if part]
    own = {name.casefold(): name for name in rules.OWN_DATA_FOLDERS}
    for index in range(len(parts) - 1, -1, -1):
        name = own.get(parts[index].casefold())
        if name is not None:
            # The folder by its own spelling, so the path written back reads like the rest.
            candidate = paths.data_dir().joinpath(name, *parts[index + 1:])
            if candidate.exists():
                return str(candidate)
    return path


def relocate_artwork(overrides: Overrides) -> int:
    """Point chosen artwork left behind by a moved project folder at where it is now.

    Run once as the window opens, so overrides.json says the right thing for everything
    that reads it -- an export bundles only artwork it can find. Returns how many paths
    changed; writes nothing when none did.
    """
    # Through the store's own operations (Phase 67), so either store can be handed in.
    changes: dict[str, dict[str, Any]] = {}
    for name in rules.ARTWORK_KEYS:
        for key, value in overrides.values_of(name).items():
            if isinstance(value, str) and value:
                found = relocated(value)
                if found != value:
                    changes.setdefault(key, {})[name] = found
    moved = sum(len(values) for values in changes.values())
    if moved:
        overrides.update_many(changes)
        log.info("found %d chosen picture(s) again after the project folder moved", moved)
    return moved


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        log.warning("unparseable timestamp in overrides: %r", value)
        return None


def _still_on_disk(entry: GameEntry, overrides: Overrides) -> bool:
    if entry.install_dir and not os.path.isdir(entry.install_dir):
        return False
    if entry.launch_kind == "exe":
        # A hand-picked exe is what would actually run, so it is what has to exist. Checking
        # the detected one instead would drop a game the user had pointed somewhere valid.
        # This also catches loose exes, whose install_dir is the scan root and never missing.
        target = overrides.get(entry.identity_key).get("exe") or entry.launch_target
        if target and not os.path.isfile(target):
            return False
    return True


def prune_missing(
    entries: list[GameEntry], overrides: Overrides
) -> tuple[list[GameEntry], list[GameEntry]]:
    """Split the catalog into games still on disk and games that have been deleted.

    The catalog is a snapshot of the last scan, so a game uninstalled since then is still in
    it and would show a tile that cannot launch. Dropping it happens in memory only: nothing
    is written here, the catalog keeps the stale record until the next scan rewrites it, and
    the game's overrides -- playtime, chosen art, custom name -- are deliberately left alone
    so reinstalling into the same folder brings all of it back.

    Leaving it in memory also means the check re-runs every start, so a game on a drive that
    was merely unplugged reappears by itself once the drive is back.
    """
    kept, gone = [], []
    for entry in entries:
        (kept if _still_on_disk(entry, overrides) else gone).append(entry)
    for entry in gone:
        log.info(
            "dropping %r: %s is no longer on disk",
            entry.display_name,
            entry.install_dir or entry.launch_target,
        )
    return kept, gone


def merge(entries: list[GameEntry], overrides: Overrides) -> list[GameView]:
    """Marry catalog entries to their overrides. Overrides win on every field they set."""
    views = [GameView(entry=entry, data=overrides.get(entry.identity_key)) for entry in entries]

    # first_seen powers the "recently added" sort. Discovery never writes overrides, so the
    # GUI stamps it the first time it lays eyes on a game -- and tags the game NEW, unless
    # this is the launcher's first look at anything at all. On a first run, or after
    # overrides.json was lost, every game is fresh, and a wall of NEW tags would say nothing.
    stamp = datetime.now().astimezone().isoformat(timespec="seconds")
    fresh = [view.key for view in views if not view.data.get("first_seen")]
    # A tag the game has outgrown -- by age, or by being played elsewhere -- is dropped
    # here, so it does not sit in overrides.json looking like a bug.
    lapsed = [view.key for view in views if view.data.get(rules.NEW_KEY) and not view.is_new]
    # The name each game goes by, kept beside its history (Phase 36). The catalog forgets a
    # game the moment its folder is gone; this is how the record left behind can still say
    # which game it was, when a new version of it turns up. Written only when it changes.
    unnamed = [view for view in views
               if view.entry.display_name
               and view.data.get(rules.KNOWN_AS_KEY) != view.entry.display_name]
    if fresh or lapsed or unnamed:
        # Through the store's own operations (Phase 67), one write, so either store can be
        # handed in; the records come out as they always did.
        knew_some = any(overrides.values_of("first_seen").values())
        changes: dict[str, dict[str, Any]] = {}
        for key in fresh:
            changes.setdefault(key, {})["first_seen"] = stamp
            if knew_some:
                changes[key][rules.NEW_KEY] = True
        for key in lapsed:
            changes.setdefault(key, {})[rules.NEW_KEY] = None
        for view in unnamed:
            changes.setdefault(view.key, {})[rules.KNOWN_AS_KEY] = view.entry.display_name
        overrides.update_many(changes)
        if fresh:
            log.info(
                "stamped first_seen on %d new game(s)%s",
                len(fresh),
                " and tagged them NEW" if knew_some else " (first look at this library: none tagged NEW)",
            )
        if lapsed:
            log.info("the NEW tag lapsed on %d game(s)", len(lapsed))
        views = [GameView(entry=e, data=overrides.get(e.identity_key)) for e in entries]

    return views
