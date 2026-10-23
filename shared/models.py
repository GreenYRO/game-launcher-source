"""The one data shape every provider produces and the GUI consumes."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict, fields
from typing import Any, Literal

LaunchKind = Literal["exe", "uri"]


@dataclass
class Alternative:
    """A launch target that was considered and rejected.

    Kept so a mis-detected game can be retargeted later from the GUI without rescanning.
    """

    path: str
    score: float
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "score": round(self.score, 2), "reason": self.reason}


# The two artwork slots a game has. They are filled, changed and cleared independently:
# the tall cover on the grid tile, and the wide banner across the detail page.
ROLE_COVER = "cover"
ROLE_BANNER = "banner"
ROLE_LABELS = {ROLE_COVER: "cover", ROLE_BANNER: "banner"}


@dataclass(frozen=True)
class ArtCandidate:
    """One possible match for a game's artwork, from any art source.

    `ident` means whatever the source needs to fetch the art afterwards: a Steam appid, or
    a SteamGridDB game id. `source` decides which one it is. `role` records which slot the
    candidate was gathered for, so a banner search can never write the cover slot.
    """

    source: str
    ident: str
    name: str
    thumbnail: str = ""
    ratio: float = 0.0
    role: str = ROLE_COVER

    @property
    def label(self) -> str:
        return self.name if self.source == "steam" else f"{self.name}   ·  SteamGridDB"


@dataclass
class GameEntry:
    source: str
    source_id: str
    display_name: str
    install_dir: str
    launch_kind: LaunchKind
    launch_target: str
    working_dir: str
    icon_hint: str
    size_on_disk: int
    detection: str
    alternatives: list[Alternative] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def identity_key(self) -> str:
        """Stable key used to marry a catalog entry to its user overrides.

        Normalized install_dir, except for URI-launched entries (a launcher can install
        several titles under one tree, and its own id is the authoritative one there).
        """
        if self.launch_kind == "uri":
            return f"{self.source}:{self.source_id}".casefold()
        return normalize_path(self.install_dir)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["alternatives"] = [a.to_dict() for a in self.alternatives]
        data["identity_key"] = self.identity_key
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GameEntry":
        """Rebuild from catalog.json. Unknown keys (identity_key) are dropped."""
        known = {f.name for f in fields(cls)}
        payload = {k: v for k, v in data.items() if k in known}
        payload["alternatives"] = [
            Alternative(
                path=alt["path"], score=float(alt.get("score", 0.0)), reason=alt.get("reason", "")
            )
            for alt in data.get("alternatives", [])
            if isinstance(alt, dict) and "path" in alt
        ]
        return cls(**payload)


def normalize_path(path: str) -> str:
    """Casefolded, separator-normalized, trailing-slash-free form used for identity.

    Windows paths are case-insensitive, so two spellings of the same directory must
    collapse to one key or overrides silently stop applying after a rescan.
    """
    import os

    return os.path.normcase(os.path.normpath(path)).rstrip("\\/")


def is_inside(path: str, parent: str) -> bool:
    """True if `path` is `parent` or sits underneath it, comparing normalized forms."""
    child, root = normalize_path(path), normalize_path(parent)
    return child == root or child.startswith(root + "\\")
