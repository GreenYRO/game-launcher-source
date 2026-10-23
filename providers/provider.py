"""The contract every discovery source implements.

A provider is asked two things: whether its source exists on this machine at all, and what
it found. It never raises -- a launcher that is not installed yields an empty list, and so
does one that is installed but unreadable. The difference goes in the log, because those two
outcomes look identical in the catalog and only one of them is normal.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from shared.models import GameEntry


@runtime_checkable
class Provider(Protocol):
    name: str

    def is_available(self) -> bool:
        """Cheap check: does this source exist here? No scanning, no heavy I/O."""
        ...

    def discover(self) -> list[GameEntry]:
        """Return everything found. Must not raise, for any reason."""
        ...
