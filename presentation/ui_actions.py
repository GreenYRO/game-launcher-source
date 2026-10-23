"""The right-click menu and everything it does.

Split from the window purely to keep both files readable. Each handler takes the window so
it can reach the overrides store and ask for a refresh.
"""

from __future__ import annotations

from datetime import datetime

import logging
import os

from PySide6.QtWidgets import QFileDialog, QInputDialog, QMenu, QMessageBox

from logic import launch
from logic import removal
from shared import rules
from presentation import ui_cover_actions
from presentation import ui_removal
from presentation import ui_rules
from shared.models import ROLE_BANNER, ROLE_COVER, ROLE_LABELS

log = logging.getLogger(__name__)


def build_menu(window, view) -> QMenu:
    menu = QMenu(window)
    if window.tracker.is_running(view.key):
        # Only ever offered for the game that is actually up, so the menu never carries a
        # control that would do nothing.
        menu.addAction("Stop", lambda: stop(window, view))
    else:
        menu.addAction("Play", lambda: window.play(view))
    menu.addAction(
        "Remove from favorites" if view.favorite else "Add to favorites",
        lambda: toggle_favorite(window, view),
    )
    _add_status_submenu(window, menu, view)
    menu.addAction(
        "Edit note..." if view.notes else "Add a note...", lambda: edit_notes(window, view)
    )
    # What I paid (Phase 74), for every game; offered only where the library keeps purchases --
    # a database at version 2 or newer, which it is unless an upgrade was refused.
    from presentation import ui_purchases

    menu.addAction("What I paid...", lambda: ui_purchases.purchases_flow(window, view)).setEnabled(
        bool(getattr(window.overrides, "keeps_prices", False)))
    # Rate your last session... (Phase 102): a late rating, the pad's way to it -- offered only when one waits,
    # a session of the last RATE_LATE_DAYS long enough to be asked about and not yet rated.
    if hasattr(window, "last_unrated") and window.last_unrated(view) is not None:
        menu.addAction("Rate your last session...", lambda: window.rate_last_session(view))
    menu.addSeparator()
    menu.addAction("Rename...", lambda: rename(window, view))
    # A URI entry has no exe to swap and no command line of our own -- Steam owns both.
    # Launch options for those belong in Steam's own game properties.
    if view.entry.launch_kind == "exe":
        _add_exe_submenu(window, menu, view)
        menu.addAction("Set launch arguments...", lambda: set_arguments(window, view))
    _add_art_submenu(window, menu, view, ROLE_COVER)
    _add_art_submenu(window, menu, view, ROLE_BANNER)
    menu.addSeparator()
    menu.addAction("Open folder", lambda: open_folder(window, view))
    if view.entry.launch_kind == "exe":
        # Only games the launcher times: that is how it learns where a game saves.
        found = [f for f in view.data.get(rules.SAVE_DIRS_KEY) or [] if os.path.isdir(f)]
        menu.addAction("Open saves folder", lambda: open_saves_folder(window, view)).setEnabled(
            bool(found)
        )
        menu.addAction("Back up saves now", lambda: window.back_up_now(view))
        from logic import save_backup
        from presentation import ui_save_restore

        menu.addAction(
            "Restore saves...", lambda: ui_save_restore.restore_flow(window, view)
        ).setEnabled(bool(save_backup.choices(*ui_save_restore.choice_args(window, view))))
    # A new version of a game you had (Phase 36): reachable from the pad, and the way to
    # join two installs the page's own question did not recognise as one game.
    from logic import lineage
    from presentation import ui_earlier

    menu.addAction(
        "Same game as an earlier install...", lambda: ui_earlier.pick_flow(window, view)
    ).setEnabled(bool(lineage.earlier_installs(window.overrides, window.by_key.keys())))
    menu.addAction(
        "Mark as game" if view.is_non_game else "Mark as tool",
        lambda: ui_cover_actions.set_is_tool(window, view, not view.is_non_game),
    )
    menu.addAction("Unhide" if view.hidden else "Hide", lambda: toggle_hidden(window, view))
    menu.addSeparator()
    # Last, behind a separator, and labelled with the tier rather than a flat "Uninstall":
    # a Steam game and a folder game are not the same offer and must not look like it.
    plan = removal.plan(view, window.config, window.tracker)
    menu.addAction(
        f"{plan.button}..." if plan.available else "Uninstall...",
        lambda: ui_removal.uninstall(window, view),
    )
    return menu


def _add_art_submenu(window, menu: QMenu, view, role: str) -> None:
    """One submenu per artwork slot. Each acts on its own slot and nothing else."""
    label = ROLE_LABELS[role]
    shape = "tall image on the tile" if role == ROLE_COVER else "wide image on the game's page"

    # Explicit parent, per the Phase 2 trap: PySide6 will not keep the wrapper returned by
    # menu.addMenu("...") alive and the submenu vanishes before it can be shown.
    submenu = QMenu(label.capitalize(), menu)
    submenu.setToolTip(f"The {shape}")
    menu.addMenu(submenu)

    submenu.addAction(
        f"Find {label} online...",
        lambda: ui_cover_actions.find_art_online(window, view, role),
    )
    submenu.addAction(
        f"Set {label} from file...",
        lambda: ui_cover_actions.set_art_from_file(window, view, role),
    )
    remove = submenu.addAction(
        f"Remove {label}", lambda: ui_cover_actions.remove_art(window, view, role)
    )
    remove.setEnabled(ui_cover_actions.has_custom(view, role))


def _add_status_submenu(window, menu: QMenu, view) -> None:
    """Playing / Finished / Dropped, reachable from anywhere a menu opens -- pad included.

    The same three the game's page offers as buttons, because the page's buttons cannot
    be reached from a controller and the menu can.
    """
    # Explicit parent: the Phase 2 trap, again.
    submenu = QMenu("Mark as", menu)
    menu.addMenu(submenu)
    for status in rules.STATUSES:
        action = submenu.addAction(
            ui_rules.STATUS_LABELS[status],
            lambda s=status: set_status(window, view, "" if view.status == s else s),
        )
        action.setCheckable(True)
        action.setChecked(view.status == status)
    submenu.addSeparator()
    submenu.addAction("No mark", lambda: set_status(window, view, "")).setEnabled(
        bool(view.status)
    )


def _add_exe_submenu(window, menu: QMenu, view) -> None:
    # Built with an explicit parent rather than menu.addMenu("..."): PySide6 does not keep
    # the wrapper returned by that overload alive, and the C++ QMenu is destroyed before
    # the menu is ever shown.
    submenu = QMenu("Choose a different exe", menu)
    menu.addMenu(submenu)
    current = view.launch_target.casefold()

    submenu.addAction(
        f"{os.path.basename(view.entry.launch_target)}  (detected)",
        lambda: set_exe(window, view, None),
    ).setEnabled(view.data.get("exe") is not None)

    alternatives = [a for a in view.entry.alternatives if a.path.casefold() != current]
    if alternatives:
        submenu.addSeparator()
    for alternative in alternatives:
        parent = os.path.basename(os.path.dirname(alternative.path))
        label = f"{os.path.basename(alternative.path)}   ({parent})"
        submenu.addAction(label, lambda p=alternative.path: set_exe(window, view, p))

    submenu.addSeparator()
    submenu.addAction("Browse...", lambda: browse_exe(window, view))


# -- handlers ------------------------------------------------------------------------------


def rename(window, view) -> None:
    text, ok = QInputDialog.getText(
        window, "Rename", "Name shown in the launcher:", text=view.display_name
    )
    if not ok:
        return
    text = text.strip()
    if text == view.entry.display_name or not text:
        # Clearing the box, or typing the detected name back, drops the override.
        window.overrides.update(view.key, name=None)
        log.info("cleared name override for %s", view.key)
    else:
        window.overrides.update(view.key, name=text)
        log.info("renamed %s to %r", view.key, text)
    window.reload_views()


def set_exe(window, view, path: str | None) -> None:
    if path is not None and not os.path.isfile(path):
        QMessageBox.warning(window, "Not found", f"That file no longer exists:\n{path}")
        log.warning("refused to set missing exe %s for %s", path, view.key)
        return
    window.overrides.update(view.key, exe=path)
    log.info("launch target for %s is now %s", view.key, path or "the detected exe")
    window.reload_views()


def browse_exe(window, view) -> None:
    start = view.entry.install_dir if os.path.isdir(view.entry.install_dir) else ""
    path, _ = QFileDialog.getOpenFileName(
        window, f"Choose the exe for {view.display_name}", start, "Programs (*.exe)"
    )
    if path:
        set_exe(window, view, os.path.normpath(path))


def set_arguments(window, view) -> None:
    text, ok = QInputDialog.getText(
        window,
        "Launch arguments",
        "Passed on the command line after the exe:",
        text=view.args,
    )
    if not ok:
        return
    window.overrides.update(view.key, args=text.strip() or None)
    log.info("args for %s are now %r", view.key, text.strip())
    window.reload_views()


def open_folder(window, view) -> None:
    target = view.entry.install_dir
    if not os.path.isdir(target):
        target = os.path.dirname(view.launch_target)
    if not os.path.isdir(target):
        QMessageBox.warning(window, "Not found", f"That folder no longer exists:\n{target}")
        return
    try:
        os.startfile(target)
    except OSError as exc:
        log.error("could not open %s in Explorer: %s", target, exc)
        QMessageBox.warning(window, "Could not open folder", str(exc))


def open_saves_folder(window, view) -> None:
    """Open where this game keeps its saves -- the first such place, if it has several."""
    found = [f for f in view.data.get(rules.SAVE_DIRS_KEY) or [] if os.path.isdir(f)]
    if not found:
        QMessageBox.information(
            window, "No saves found yet",
            "The launcher learns where a game saves by watching what it writes while you "
            "play it from here. Nothing save-like has turned up for this one yet.",
        )
        return
    try:
        os.startfile(found[0])
    except OSError as exc:
        log.error("could not open %s in Explorer: %s", found[0], exc)
        QMessageBox.warning(window, "Could not open folder", str(exc))


def stop(window, view) -> None:
    """End a running game, after asking.

    The confirmation is not ceremony: this kills the whole process tree outright, and
    anything the game has not written to disk is gone. The default button is No.
    """
    answer = QMessageBox.question(
        window,
        "Stop this game?",
        f"{view.display_name} will be closed immediately.\n\n"
        "Any progress it has not saved will be lost.",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    if answer != QMessageBox.StandardButton.Yes:
        return
    if not window.tracker.stop(view.key):
        QMessageBox.warning(
            window, "Could not stop it",
            f"{view.display_name} could not be closed. It may have already exited.",
        )
    # Do not wait for the next poll: bank the time, record the session and put the button
    # back to Play now, so the page matches what just happened.
    window._poll_playtime()
    window.refresh_running_state()


def toggle_favorite(window, view) -> None:
    """Star or unstar a game.

    False is not stored: an unstarred game is simply one with no favorite key, which keeps
    overrides.json free of a line per game saying nothing. That is the opposite of the
    "mark as game" case, where False genuinely means "I disagree with Steam".
    """
    now_favorite = not view.favorite
    window.overrides.update(view.key, favorite=True if now_favorite else None)
    log.info("%s is now %s", view.key, "a favorite" if now_favorite else "not a favorite")
    window.reload_views()


def set_status(window, view, status: str) -> None:
    """Record where the user is with a game. "" clears the mark rather than storing one."""
    if status and status not in rules.STATUSES:
        log.warning("ignoring unknown status %r for %s", status, view.key)
        return
    # When the mark was set or cleared (Phase 101): written from then on, so Phase 103 can date them. A
    # library left at version 7 keeps the mark and leaves the moment out (the store's has_marks).
    moment = datetime.now().astimezone().isoformat(timespec="seconds")
    window.overrides.update(view.key, **{rules.STATUS_KEY: status or None, rules.STATUS_CHANGED_KEY: moment})
    log.info("%s marked %s", view.key, status or "with no status")
    window.reload_views()
    if status:
        text = f"{view.display_name}: {ui_rules.STATUS_LABELS[status]}"
    else:
        text = f"{view.display_name}: mark cleared"
    window.statusBar().showMessage(text, 4000)


def still_playing(window, view) -> None:
    """Left behind's third answer (Phase 103): the game is still being played. Writes when it was answered -- the
    nudge's moment -- and nothing else: the mark stays Playing, and the game is left alone for LEFT_BEHIND_DAYS."""
    moment = datetime.now().astimezone().isoformat(timespec="seconds")
    window.overrides.update(view.key, **{rules.NUDGED_KEY: moment})
    log.info("%s still playing: asked again in %d days at the soonest", view.key, rules.LEFT_BEHIND_DAYS)
    window.reload_views()
    window.statusBar().showMessage(f"{view.display_name}: still playing", 4000)


def edit_notes(window, view) -> None:
    """Write or change the note on a game. Emptying the box removes the note."""
    dialog = QInputDialog(window)
    dialog.setWindowTitle(f"Note -- {view.display_name}")
    dialog.setLabelText("Where you left off, settings that worked, anything worth keeping:")
    dialog.setOption(QInputDialog.InputDialogOption.UsePlainTextEditForTextInput, True)
    dialog.setTextValue(view.notes)
    dialog.resize(560, 340)
    if not dialog.exec():
        return
    text = dialog.textValue().strip()
    if len(text) > rules.NOTES_MAX_CHARS:
        log.info("note for %s cut to %d characters", view.key, rules.NOTES_MAX_CHARS)
        text = text[: rules.NOTES_MAX_CHARS].rstrip()
        window.statusBar().showMessage(
            f"Note saved, cut to {rules.NOTES_MAX_CHARS} characters", 6000
        )
    window.overrides.update(view.key, **{rules.NOTES_KEY: text or None})
    window.reload_views()


def toggle_hidden(window, view) -> None:
    now_hidden = not view.hidden
    window.overrides.update(view.key, hidden=True if now_hidden else None)
    log.info("%s is now %s", view.key, "hidden" if now_hidden else "visible")
    window.reload_views()


# -- launching -------------------------------------------------------------------------------


def play(window, view) -> None:
    if getattr(window, "starting_key", None) is not None:
        return  # a game is starting: Play rests, never a second start (Phase 99)
    if hasattr(window, "begin_starting"):
        window.begin_starting(view)
        if view.entry.launch_kind in rules.LAUNCH_ON_A_THREAD:
            # Windows' start call is the wait (13.1 s once, step 0): off the GUI thread, the window answering.
            result = window.run_launch(lambda: launch.launch_game(view))
        else:
            result = launch.launch_game(view)
        if not result.ok:
            window.end_starting("it would not start")  # before the dialog, exactly as today's
    else:
        result = launch.launch_game(view)
    if result.ok:
        # Started without its page being opened -- from the right-click menu -- still counts.
        window.mark_seen(view.key)
        # Success and trackability are separate questions. A URI launch (Steam, Epic, Xbox)
        # hands the game to its launcher and gets no process handle back, so `running` is
        # None even though the game is starting. Treating that as a failure is what put a
        # "would not start" box in front of games that had just started perfectly well.
        if result.running is not None:
            window.tracker.add(result.running)
            window.refresh_running_state()  # Play becomes Stop now, not at the next poll
            window.statusBar().showMessage(f"Started {view.display_name}", 4000)
        else:
            window.statusBar().showMessage(
                f"Handed {view.display_name} to its launcher (playtime not tracked)", 6000
            )
        return

    if result.needs_elevation:
        answer = QMessageBox.question(
            window,
            "Administrator rights needed",
            f"{view.display_name} would not start:\n\n{result.error}\n\nTry again as administrator?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if answer == QMessageBox.Yes:
            elevated = launch.launch_elevated(view)
            if elevated.ok:
                window.mark_seen(view.key)
                # No process handle comes back from ShellExecute, so the tracker cannot time this run;
                # the process watch can, seeing it in the list as any game started elsewhere (Phase 93).
                how = "timed by watching" if window.watch_on() else "not timed"
                window.statusBar().showMessage(f"Started {view.display_name} as administrator ({how})", 6000)
            else:
                QMessageBox.critical(window, "Could not start", elevated.error)
        return

    # Never show a bare "would not start:" with nothing after it -- an empty reason is a bug
    # in the caller, and the user cannot act on it.
    reason = result.error.strip() or "Windows gave no reason. Check the log for details."
    QMessageBox.critical(
        window, "Could not start", f"{view.display_name} would not start:\n\n{reason}"
    )
