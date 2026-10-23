"""The tray icon (Phase 92): where the launcher lives while its window is closed.

It exists whenever Settings' "Keep running when the window is closed" is on. A left click
brings the window back; the right-click menu holds the games played last -- Play, or Stop for
the one running -- and the launcher's own Rescan, Settings... and Quit. Nothing in it is new
behaviour: every entry calls what the window already does, so a game started here is timed
by the Job Object exactly as a click on its tile would time it.

The menu is a child of the window, so it wears the window's stylesheet, and it is filled
afresh each time it opens: the games, and which of them is running, are read at that moment.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from logic import taskbar
from presentation import ui_rules
from shared import humanize

log = logging.getLogger(__name__)

TOOLTIP = "Game Launcher"
UPDATED = "Game Launcher -- updated to {version}; open it to see what's new"  # Phase 106
FIRST_HIDE = ("Game Launcher is still running here. Right-click the icon to quit, "
              "or turn this off in Settings.")


def recent_games(views, running: set[str], count: int) -> list:
    """The games the menu offers: a game running now first, then the ones played last.

    Never a hidden game or a demo or tool, never one that has never been played. A running
    game is always there, even before its first minute is banked as its last played.
    """
    def played_at(view) -> float:
        moment = view.last_played
        return moment.timestamp() if moment is not None else 0.0

    candidates = [view for view in views if not view.hidden and not view.is_non_game
                  and (view.key in running or view.last_played is not None)]
    candidates.sort(key=lambda view: (view.key not in running, -played_at(view)))
    return candidates[:count]


def tooltip(playing: list[tuple[str, int]], updated: str = "") -> str:
    """'Game Launcher', or 'Playing Slow Roads for 1h 12m' while a game started from here is timed; after an update
    whose notes are not seen yet (Phase 106), 'Game Launcher -- updated to 1.2.10; open it to see what's new'."""
    if not playing:
        return UPDATED.format(version=updated) if updated else TOOLTIP
    return "Playing " + ", ".join(f"{name} for {humanize.playtime(seconds)}" for name, seconds in playing)


def _menu_text(text: str) -> str:
    return text.replace("&", "&&")  # a menu reads a lone & as the next letter's shortcut


class Tray(QObject):
    """The icon and its menu, owned by the window; `window` is the MainWindow."""

    def __init__(self, window) -> None:
        super().__init__(window)
        self.window = window
        self.icon = QSystemTrayIcon(QIcon(str(taskbar.ICON_PATH)), window)
        self.icon.setToolTip(TOOLTIP)
        self.menu = QMenu(window)
        self.menu.setObjectName("TrayMenu")
        self.menu.aboutToShow.connect(self.fill)
        self.icon.setContextMenu(self.menu)
        self.icon.activated.connect(self._activated)
        # A click on a balloon (Phase 101): what the balloon asked for -- the price alert's opens the Wishlist tab.
        # Every other balloon asks for nothing, so a click on it does nothing, as before.
        self._on_click = None
        self.icon.messageClicked.connect(self._message_clicked)
        self.fill()

    # -- the icon ----------------------------------------------------------------------------

    def show(self) -> None:
        self.icon.show()

    def visible(self) -> bool:
        return self.icon.isVisible()

    def remove(self) -> None:
        """Gone from the tray at once -- the icon is hidden before it is let go of."""
        self.icon.hide()
        self.icon.setContextMenu(None)
        self.menu.deleteLater()
        self.icon.deleteLater()
        self.deleteLater()

    def set_tooltip(self, text: str) -> None:
        if self.icon.toolTip() != text:
            self.icon.setToolTip(text)

    def say(self, text: str, clicked=None) -> None:
        """One balloon from the icon -- Windows shows it as a notification. `clicked` is what a click on it does
        (Phase 101); a later balloon replaces it, so a click never does what an older balloon asked."""
        self._on_click = clicked
        self.icon.showMessage(TOOLTIP, text, QSystemTrayIcon.MessageIcon.Information, ui_rules.TRAY_BALLOON_MS)

    def _message_clicked(self) -> None:
        action, self._on_click = self._on_click, None
        if action is not None:
            log.info("tray balloon clicked")
            action()

    def _activated(self, reason) -> None:
        # A double click arrives as a click and then a double click: the click alone brings the window
        # back, or it was brought back twice (seen in launcher.log on 18 October).
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            log.info("tray icon clicked: the window is brought back")
            self.window.bring_forward()

    # -- the menu ----------------------------------------------------------------------------

    def fill(self) -> None:
        window = self.window
        self.menu.clear()
        self.menu.addAction("Open Game Launcher").triggered.connect(lambda _checked=False: window.bring_forward())
        running = window.tracker.active_keys
        observed = window.observer.running()  # seen running, started outside the launcher (Phase 93)
        games = recent_games(window.views, running | observed, ui_rules.RECENT_TRAY_GAMES)
        if games:
            self.menu.addSeparator()
        for view in games:
            if view.key in running:
                action = self.menu.addAction(_menu_text(f"Stop {view.display_name}"))
                action.triggered.connect(lambda _checked=False, key=view.key: window._stop_key(key))
            elif view.key in observed:
                # Not started here: nothing to stop, and never a second copy (Phase 93).
                self.menu.addAction(_menu_text(f"{view.display_name} is running")).setEnabled(False)
            else:
                action = self.menu.addAction(_menu_text(f"Play {view.display_name}"))
                action.triggered.connect(lambda _checked=False, key=view.key: window._play_key(key))
        self.menu.addSeparator()
        rescan = self.menu.addAction("Rescan")
        rescan.setEnabled(not (window.worker is not None and window.worker.isRunning()))
        rescan.triggered.connect(lambda _checked=False: window.start_scan())
        self.menu.addAction("Settings...").triggered.connect(lambda _checked=False: window.open_settings())
        self.menu.addAction("Quit").triggered.connect(lambda _checked=False: window.quit_launcher())

    def entries(self) -> list[str]:
        """The menu's words, separators as '-' -- what a test reads."""
        return ["-" if action.isSeparator() else action.text() for action in self.menu.actions()]
