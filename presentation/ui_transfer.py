"""Export and import, from the Settings dialog.

Two flows, both deliberately talkative. Export says plainly what is going into the file,
including whether the SteamGridDB key is in there, because a bundle with a key in it is
not safe to hand to anyone. Import says what it did afterwards, including which of the
imported games can take effect on this PC and which are waiting for their game to appear.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QLabel,
    QMessageBox,
    QVBoxLayout,
)

from shared import humanize
from shared import rules
from logic import transfer

log = logging.getLogger(__name__)

BUNDLE_FILTER = f"Game Launcher library (*{rules.TRANSFER_SUFFIX});;Zip files (*.zip)"


class ExportDialog(QDialog):
    """What is about to go in the file, and the one decision worth making about it."""

    def __init__(self, has_key: bool, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export my library")
        self.setMinimumWidth(460)
        self.has_key = has_key

        intro = QLabel(
            "This saves one file holding everything the installer deliberately leaves out:\n\n"
            "    •  your settings and scan folders\n"
            "    •  playtime, renamed games and hidden games\n"
            "    •  the cover and banner artwork you picked\n\n"
            "Your game files are not included — this is only what the launcher remembers "
            "about them."
        )
        intro.setWordWrap(True)

        self.include_key = QCheckBox("Include my SteamGridDB key")
        self.include_key.setChecked(has_key)
        self.include_key.setEnabled(has_key)

        warning = QLabel(
            "Your SteamGridDB key is part of your settings. Leave it in to save typing it "
            "again on your own PCs; take it out if this file might reach anyone else."
            if has_key
            else "You have no SteamGridDB key saved, so there is nothing private in the file."
        )
        warning.setObjectName("Meta")
        warning.setWordWrap(True)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Choose file...")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(self.include_key)
        layout.addWidget(warning)
        layout.addSpacing(6)
        layout.addWidget(buttons)


def export_flow(parent, config: dict, store=None) -> bool:
    """Ask, save, report. Returns True only if a file was written.

    `store` is the window's (Phase 65), handed down by Settings; without one the library is
    read as it is saved.
    """
    has_key = bool(str(config.get("steamgriddb_key", "") or ""))
    options = ExportDialog(has_key, parent)
    if options.exec() != QDialog.DialogCode.Accepted:
        return False

    suggested = str(Path(os.path.expanduser("~")) / "Desktop" / transfer.default_name())
    chosen, _ = QFileDialog.getSaveFileName(parent, "Save my library", suggested, BUNDLE_FILTER)
    if not chosen:
        return False

    report = transfer.export_bundle(Path(chosen), include_key=options.include_key.isChecked(),
                                    store=store)
    if not report.ok:
        QMessageBox.warning(parent, "Could not export", report.message)
        return False

    size = humanize.size(report.path.stat().st_size) if report.path else ""
    key_line = (
        "\n\nThis file contains your SteamGridDB key, so keep it to yourself."
        if report.includes_key
        else "\n\nNo SteamGridDB key is in this file."
    )
    QMessageBox.information(
        parent,
        "Exported",
        f"{report.message}\n\nSaved to:\n{report.path}  ({size}){key_line}",
    )
    return True


def import_flow(parent, known_keys: set[str], store=None) -> transfer.ImportReport | None:
    """Pick a bundle, confirm what it is, merge it, and report. None if nothing happened."""
    start = str(Path(os.path.expanduser("~")) / "Desktop")
    chosen, _ = QFileDialog.getOpenFileName(parent, "Import a library", start, BUNDLE_FILTER)
    if not chosen:
        return None

    manifest, problem = transfer.read_manifest(Path(chosen))
    if manifest is None:
        QMessageBox.warning(parent, "Could not import", problem)
        return None

    created = str(manifest.get("created", "an unknown date"))[:16].replace("T", " at ")
    key_line = (
        "\nIt also carries a SteamGridDB key, which will replace the one saved here."
        if manifest.get("includes_steamgriddb_key")
        else ""
    )
    confirm = QMessageBox.question(
        parent,
        "Import this library?",
        f"Made on {created}.\n\n"
        f"It holds {manifest.get('games', '?')} saved games and "
        f"{manifest.get('art_files', 0)} artwork files.{key_line}\n\n"
        "Anything this PC already knows about those games is replaced. Games only this PC "
        "knows about are left alone, and a backup is taken first.",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    if confirm != QMessageBox.StandardButton.Yes:
        return None

    report = transfer.import_bundle(Path(chosen), known_keys, store=store)
    if not report.ok:
        QMessageBox.warning(parent, "Could not import", report.message)
        return None
    QMessageBox.information(parent, "Imported", report.message)
    return report
