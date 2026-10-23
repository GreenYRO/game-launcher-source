"""Everything the user can do to a game's artwork, plus marking it a tool or a game.

A game has two independent artwork slots: the tall **cover** on its grid tile, and the wide
**banner** across its detail page. Every function here takes a role and touches that slot
only -- setting a banner can never disturb a cover you were happy with, and removing one
leaves the other exactly where it was.

All of it is stored in overrides.json, so a scan never undoes a choice made here, and every
one of these is reversible from the same menu.
"""

from __future__ import annotations

import dataclasses
import logging
import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QMessageBox

from shared import paths
from shared import rules
from shared.models import ROLE_BANNER, ROLE_COVER, ROLE_LABELS
from web import steam_search, steam_web, steamgriddb
from presentation.ui_cover_dialog import CoverPickerDialog

log = logging.getLogger(__name__)

CACHE_DIR = str(paths.cache_dir())
IMAGE_FILTER = "Images (*.jpg *.jpeg *.png *.bmp *.webp)"

# Which override key each slot writes. Nothing else in this module knows the key names.
SLOT_KEY = {ROLE_COVER: "cover", ROLE_BANNER: "banner"}


def network_allowed(window) -> bool:
    if window.config.get("allow_network", rules.ALLOW_NETWORK_DEFAULT):
        return True
    QMessageBox.information(
        window,
        "Network lookups are off",
        "Looking artwork up needs network access, which is switched off.\n\n"
        "Turn on 'Allow network lookups' in Settings, or set an image from a file.",
    )
    return False


def find_art_online(window, view, role: str = ROLE_COVER) -> None:
    """Search for artwork for one slot and let the user pick from the results."""
    if not network_allowed(window):
        return

    label = ROLE_LABELS[role]
    key = str(window.config.get("steamgriddb_key", "") or "")

    QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
    try:
        window.statusBar().showMessage(f"Searching for a {label} for {view.display_name}...")
        QApplication.processEvents()
        # Steam's search returns games, not images, so the role is stamped on afterwards --
        # it decides which of that game's images gets downloaded once one is chosen.
        candidates = [
            dataclasses.replace(candidate, role=role)
            for candidate in steam_search.candidates_for(view.display_name)
        ]
        # SteamGridDB is only consulted when the user has supplied their own key. Its grids
        # feed the cover slot and its heroes feed the banner slot.
        if steamgriddb.configured(key):
            candidates.extend(steamgriddb.search(view.display_name, key, role))
        thumbnails = {
            (c.source, c.ident): steam_web.fetch_image(c.thumbnail) for c in candidates
        }
    finally:
        QGuiApplication.restoreOverrideCursor()
        window.statusBar().clearMessage()

    if not candidates:
        extra = (
            ""
            if steamgriddb.configured(key)
            else "\n\nAdding a SteamGridDB key in Settings would also search there, which "
            "covers games Steam does not sell."
        )
        QMessageBox.information(
            window,
            "Nothing found",
            f"No match for “{view.display_name}”.{extra}\n\nYou can still set a {label} "
            "from a file.",
        )
        return

    dialog = CoverPickerDialog(view.display_name, candidates, thumbnails, window, role=role)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return
    candidate = dialog.chosen()
    if candidate is None:
        return

    QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
    try:
        if candidate.source == steamgriddb.SOURCE:
            path = steamgriddb.fetch_for(candidate.ident, key, CACHE_DIR, role)
        else:
            path = steam_web.fetch_for(candidate.ident, CACHE_DIR, role)
    finally:
        QGuiApplication.restoreOverrideCursor()

    if not path:
        QMessageBox.warning(
            window,
            "No artwork",
            f"That entry has no {label} image published. Try another result, or set one "
            "from a file.",
        )
        return

    _write_slot(window, view, role, path)
    _refresh(window, f"{view.display_name}: {label} updated")


def set_art_from_file(window, view, role: str = ROLE_COVER) -> None:
    label = ROLE_LABELS[role]
    start = view.entry.install_dir if os.path.isdir(view.entry.install_dir) else ""
    path, _ = QFileDialog.getOpenFileName(
        window, f"{label.capitalize()} image for {view.display_name}", start, IMAGE_FILTER
    )
    if not path:
        return
    _write_slot(window, view, role, os.path.normpath(path))
    _refresh(window, f"{view.display_name}: {label} set")


def remove_art(window, view, role: str = ROLE_COVER) -> None:
    """Clear one slot, back to whatever was detected automatically. The other is untouched."""
    label = ROLE_LABELS[role]
    window.overrides.update(view.key, **{SLOT_KEY[role]: None})
    log.info("%s: cleared the %s override", view.key, label)
    _refresh(window, f"{view.display_name}: back to the detected {label}")


def has_custom(view, role: str = ROLE_COVER) -> bool:
    return bool(view.data.get(SLOT_KEY[role]))


def set_is_tool(window, view, is_tool: bool) -> None:
    # Store the answer, not the absence of one. Writing None here would delete the override
    # and let Steam's own label win again, so "Mark as game" on something Steam calls a demo
    # would appear to do nothing at all.
    window.overrides.update(view.key, is_tool=bool(is_tool))
    label = "a tool" if is_tool else "a game"
    log.info("%s marked as %s", view.key, label)
    _refresh(window, f"{view.display_name} is now marked as {label}")


def fill_cover(window, view, path: str) -> bool:
    """A cover the batch found (Phase 105), written as Find online writes one: the cover slot only, the banner
    untouched -- and never over a cover set by hand, one chosen while the batch ran included."""
    if has_custom(view, ROLE_COVER):
        log.info("%s: a cover was set by hand meanwhile; the one found is not written", view.key)
        return False
    _write_slot(window, view, ROLE_COVER, path)
    return True


def covers_filled(window, count: int) -> None:
    """The grid redrawn with the covers just written (Phase 105), and a word on the status line."""
    _refresh(window, f"{count} cover{'s' if count != 1 else ''} filled from SteamGridDB")


def _write_slot(window, view, role: str, path: str) -> None:
    """Write exactly one slot. Nothing else in the record is read or altered."""
    window.overrides.update(view.key, **{SLOT_KEY[role]: path})
    log.info("%s: %s is now %s", view.key, ROLE_LABELS[role], path)


def _refresh(window, message: str) -> None:
    window.covers.clear()
    window.reload_views()
    window.statusBar().showMessage(message, 5000)
