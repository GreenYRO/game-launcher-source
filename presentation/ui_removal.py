"""The uninstall confirmation, and the handlers the three surfaces share.

The dialog is a `QMessageBox` rather than a custom window for one reason that matters: the
window already knows how to drive a modal from the pad (`MainWindow._drive_dialog`, Phase
21), so this is answerable from the couch the moment it appears, with no new input code.

**Cancel is the default button, always.** For the tier that deletes, Cancel is also the
escape key and the button the focus starts on, so a stray Return or a stray A does nothing.
"""

from __future__ import annotations

import logging
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from shared import humanize
from logic import removal
from shared import rules
from adapters import save_worker

log = logging.getLogger(__name__)


def _details(view, plan) -> str:
    """The three facts a person needs before agreeing: what, where, how big."""
    lines = [f"<b>{view.display_name}</b>", ""]
    if plan.tier in (rules.TIER_DELETE, rules.TIER_UNINSTALLER) and view.entry.install_dir:
        lines.append(f"<code>{view.entry.install_dir}</code>")
    if view.entry.size_on_disk:
        lines.append(f"{humanize.size(view.entry.size_on_disk)} on disk")
    return "<br>".join(lines)


def confirm(window, view, plan, saves_line: str = "") -> bool:
    """Ask. Returns True only if the user actively chose to go ahead."""
    box = QMessageBox(window)
    box.setIcon(
        QMessageBox.Icon.Warning if plan.deletes else QMessageBox.Icon.Question
    )
    box.setWindowTitle("Uninstall this game?")
    box.setTextFormat(rules_text_format())
    box.setText(_details(view, plan))

    informative = [plan.explanation]
    if saves_line:
        informative.append(saves_line)
    if plan.deletes:
        informative.append(
            "Your playtime, session history and any artwork you chose are kept, and come "
            "back on their own if you ever reinstall it to the same folder."
        )
    box.setInformativeText("\n\n".join(informative))

    go = box.addButton(plan.button, QMessageBox.ButtonRole.DestructiveRole)
    cancel = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
    # Both of these, not one: setDefaultButton decides what Return does, setEscapeButton
    # what Escape does, and the focus decides what a pad's A does the instant it opens.
    box.setDefaultButton(cancel)
    box.setEscapeButton(cancel)
    cancel.setFocus()

    box.exec()
    chosen = box.clickedButton() is go
    log.info(
        "uninstall %s for %s: user chose %s",
        plan.tier,
        view.key,
        "go ahead" if chosen else "cancel",
    )
    return chosen


def protect_saves(window, view) -> tuple[bool, str]:
    """Copy this game's saves before anything is uninstalled. (go on?, a line to show)

    Looked for right here if they were never found before, since this may be the last
    chance. A copy that fails stops the uninstall: the point is that removing a game
    never takes its saves with it unnoticed. A game with no sessions has nothing to go on,
    and is let through with nothing to say.
    """
    job = window.save_job(view, reason="before uninstalling", back_up=True)
    if job is None:
        return True, ""
    QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
    try:
        outcomes = save_worker.run_jobs([job], window.other_game_names())
    finally:
        QApplication.restoreOverrideCursor()
    window.record_saves(outcomes)
    outcome = outcomes[0] if outcomes else None
    if outcome is None or not outcome.folders:
        return True, ""
    result = outcome.backup
    if result is None or result.error:
        return False, result.error if result is not None else "the copy never started"
    install_dir = os.path.normcase(os.path.normpath(view.entry.install_dir or ""))
    inside = bool(view.entry.install_dir) and any(
        os.path.normcase(os.path.normpath(folder)).startswith(install_dir + os.sep)
        for folder in outcome.folders
    )
    where = ("inside this folder -- they would have gone with it" if inside
             else "outside this folder, where uninstalling does not touch them")
    line = f"This game keeps its saves {where}. A copy of them is in the save backups."
    if result.too_big:
        line += f" ({len(result.too_big)} folder(s) too large to be saves were left out.)"
    log.info("saves of %s protected before uninstalling: %s", view.key, outcome.folders)
    return True, line


def rules_text_format():
    from PySide6.QtCore import Qt

    return Qt.TextFormat.RichText


def uninstall(window, view) -> None:
    """The one handler behind every surface: the menu, the detail page, the storage page."""
    plan = removal.plan(view, window.config, window.tracker)

    if plan.blocked:
        # A refusal is not a failure to explain away -- it is the safety rule working, and
        # it says which one fired.
        QMessageBox.information(window, "Cannot uninstall this one", plan.blocked)
        log.info("refused to uninstall %s: %s", view.key, plan.blocked)
        return

    go_on, saves_line = protect_saves(window, view)
    if not go_on:
        QMessageBox.warning(
            window,
            "Nothing was removed",
            f"The saves of {view.display_name} could not be copied first, so nothing was "
            f"removed.\n\n{saves_line}",
        )
        return

    if not confirm(window, view, plan, saves_line):
        return

    ok, message = removal.perform(plan, hwnd=int(window.winId()))
    if not ok:
        QMessageBox.warning(window, "Nothing was removed", message)
        return

    if plan.deletes:
        window.statusBar().showMessage(
            f"{view.display_name} moved to the Recycle Bin. Playtime and artwork kept.",
            rules.UNINSTALL_STATUS_MS,
        )
    else:
        window.queue_status(f"{message}", rules.UNINSTALL_STATUS_MS)

    # The quiet startup pass, reused: the catalogue is now wrong, and prune_missing drops
    # the tile. A store route has handed off to someone else and may not have finished, so
    # the rescan is worth running either way -- it costs about a second and a half.
    window.start_scan(quiet=True, trigger="uninstall")
