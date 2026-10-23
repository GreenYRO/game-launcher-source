"""Game controllers, turned into a handful of named actions.

Read through SDL's game-controller layer, so a DualSense and an Xbox pad produce identical
button numbers and neither needs its own mapping table.

Three things here are less obvious than they look:

* **SDL is given a dummy video driver.** It refuses to deliver an event queue without a
  video subsystem, and letting it initialise a real one inside a Qt process means two
  toolkits owning windows. The dummy driver gives SDL its queue and creates nothing.
* **Input is ignored unless the launcher window is active.** SDL keeps reporting buttons
  while a game runs fullscreen on top, so without this gate every press in-game would also
  be steering the launcher behind it -- and you would come back to a different selection.
* **Only one pad is ever read.** DS4Windows can present a virtual pad beside the real
  DualSense, and reading both would double every press. Whichever pad is actually being
  touched becomes the active one and the others are ignored.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Callable

from shared import rules

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ.setdefault("SDL_VIDEODRIVER", rules.CONTROLLER_SDL_VIDEODRIVER)

from PySide6.QtCore import QObject, QTimer, Signal  # noqa: E402

log = logging.getLogger(__name__)

UP, DOWN, LEFT, RIGHT = "up", "down", "left", "right"
ACTIVATE, BACK, MENU, SETTINGS = "activate", "back", "menu", "settings"
# Y on an Xbox pad, Triangle on a DualSense. Was the only face button unused.
SURPRISE = "surprise"
# View on an Xbox pad, Create on a DualSense -- SDL calls it BACK, which it has not been
# on a controller for two console generations. Checked against the real pad before it was
# used: pygame reports it as button 4, distinct from START, and reads cleanly.
STATS = "stats"
PAGE_UP, PAGE_DOWN = "page_up", "page_down"

try:
    import pygame
    from pygame._sdl2 import controller as sdl_controller

    PYGAME_AVAILABLE = True
except Exception as exc:  # pygame missing or unloadable; the launcher still works
    logging.getLogger(__name__).warning("pygame unavailable, controllers disabled: %s", exc)
    pygame = None
    sdl_controller = None
    PYGAME_AVAILABLE = False


def _joystick_power(index: int) -> str:
    """SDL's battery level for one device, or "unknown" if it will not say.

    Probed against the real hardware: `pygame._sdl2.controller.Controller` has no
    power-level accessor at all, while the plain `pygame.joystick.Joystick` on the same
    device index does. A wired pad answers "wired", which is a real answer meaning there is
    nothing to show rather than a failure.
    """
    if not PYGAME_AVAILABLE:
        return rules.POWER_UNKNOWN
    try:
        stick = pygame.joystick.Joystick(index)
        if not hasattr(stick, "get_power_level"):
            log.info("this pygame build cannot report a battery level")
            return rules.POWER_UNKNOWN
        return str(stick.get_power_level() or rules.POWER_UNKNOWN)
    except Exception as exc:
        log.warning("could not read the battery for device %d: %s", index, exc)
        return rules.POWER_UNKNOWN


def _button_map() -> dict[int, str]:
    return {
        pygame.CONTROLLER_BUTTON_A: ACTIVATE,
        pygame.CONTROLLER_BUTTON_B: BACK,
        pygame.CONTROLLER_BUTTON_X: MENU,
        pygame.CONTROLLER_BUTTON_Y: SURPRISE,
        pygame.CONTROLLER_BUTTON_START: SETTINGS,
        pygame.CONTROLLER_BUTTON_BACK: STATS,
        pygame.CONTROLLER_BUTTON_LEFTSHOULDER: PAGE_UP,
        pygame.CONTROLLER_BUTTON_RIGHTSHOULDER: PAGE_DOWN,
    }


def _dpad_map() -> dict[int, str]:
    return {
        pygame.CONTROLLER_BUTTON_DPAD_UP: UP,
        pygame.CONTROLLER_BUTTON_DPAD_DOWN: DOWN,
        pygame.CONTROLLER_BUTTON_DPAD_LEFT: LEFT,
        pygame.CONTROLLER_BUTTON_DPAD_RIGHT: RIGHT,
    }


def family_of(name: str) -> str:
    """Which family's buttons a pad of this name has printed on it (Phase 50).

    SDL gives every pad the same Xbox-shaped layout, so this only decides the pictures in
    the TV hint bar. Recognisably PlayStation by name, or else Xbox.
    """
    lowered = name.casefold()
    if any(word in lowered for word in rules.CONTROLLER_PLAYSTATION_WORDS):
        return rules.PAD_PLAYSTATION
    return rules.PAD_XBOX


class ControllerHub(QObject):
    """Polls the active pad and emits named actions."""

    action = Signal(str)
    padsChanged = Signal(str)
    powerChanged = Signal(str)
    # Whose buttons the pad in use has printed on it (Phase 50): rules.PAD_XBOX or
    # rules.PAD_PLAYSTATION, or "" with no pad at all. Emitted only when it changes.
    familyChanged = Signal(str)

    def __init__(self, window_is_active: Callable[[], bool], parent=None) -> None:
        super().__init__(parent)
        self.window_is_active = window_is_active
        self.available = False
        self._pads: dict[int, object] = {}
        self._active_id: int | None = None
        # instance id -> device index, for reaching the joystick behind a pad
        self._device_index: dict[int, int] = {}
        self._power = rules.POWER_UNKNOWN
        self._family = ""
        self._direction = ""
        self._next_repeat = 0.0
        self._pressed: set[int] = set()

        self._timer = QTimer(self)
        self._timer.setInterval(rules.CONTROLLER_POLL_MS)
        self._timer.timeout.connect(self._poll)

    # -- lifecycle -------------------------------------------------------------------------

    def start(self) -> bool:
        if not PYGAME_AVAILABLE:
            return False
        try:
            pygame.display.init()
            pygame.joystick.init()
            sdl_controller.init()
        except Exception as exc:
            log.error("could not start SDL for controllers: %s", exc)
            return False

        self.available = True
        self._sync_pads()
        self._power_timer = QTimer(self)
        self._power_timer.setInterval(rules.CONTROLLER_POWER_POLL_MS)
        self._power_timer.timeout.connect(self.refresh_power)
        self._power_timer.start()
        self.refresh_power()
        self._timer.start()
        log.info("controller support started (%d pad(s))", len(self._pads))
        return True

    def stop(self) -> None:
        self._timer.stop()
        for pad in self._pads.values():
            try:
                pad.quit()
            except Exception as exc:
                log.debug("closing pad failed: %s", exc)
        self._pads.clear()
        if self.available and PYGAME_AVAILABLE:
            try:
                pygame.quit()
            except Exception as exc:
                log.debug("pygame shutdown failed: %s", exc)
        self.available = False

    def describe(self) -> str:
        if not self.available:
            return "no controller support"
        if not self._pads:
            return "no controller connected"
        names = [self._name(pad) for pad in self._pads.values()]
        return ", ".join(names)

    # -- device bookkeeping ------------------------------------------------------------------

    def family(self) -> str:
        """Whose buttons the pad in use has on it: the active pad, else the first one."""
        pad = self._pads.get(self._active_id) if self._active_id is not None else None
        pad = pad if pad is not None else next(iter(self._pads.values()), None)
        return family_of(self._name(pad)) if pad is not None else ""

    def _note_family(self) -> None:
        family = self.family()
        if family != self._family:
            self._family = family
            log.info("controller buttons drawn as: %s", family or "(no pad)")
            self.familyChanged.emit(family)

    def _name(self, pad) -> str:
        try:
            return str(pad.name)
        except Exception:
            return "controller"

    def _sync_pads(self) -> None:
        """Rebuild the pad list from what SDL currently reports."""
        found: dict[int, object] = {}
        try:
            count = pygame.joystick.get_count()
        except Exception as exc:
            log.warning("cannot count joysticks: %s", exc)
            return

        for index in range(count):
            try:
                if not sdl_controller.is_controller(index):
                    log.info("device %d is not a game controller; ignoring", index)
                    continue
                pad = sdl_controller.Controller(index)
                found[pad.id] = pad
                self._device_index[pad.id] = index
            except Exception as exc:
                log.warning("cannot open controller %d: %s", index, exc)

        if set(found) != set(self._pads):
            for iid, pad in self._pads.items():
                if iid not in found:
                    try:
                        pad.quit()
                    except Exception as exc:
                        log.debug("closing removed pad failed: %s", exc)
            self._pads = found
            if self._active_id not in self._pads:
                self._active_id = None
            log.info("controllers now: %s", self.describe())
            self.padsChanged.emit(self.describe())
            self.refresh_power()
            self._note_family()
        else:
            self._pads = found

    # -- polling -----------------------------------------------------------------------------

    def _poll(self) -> None:
        if not self.available:
            return
        try:
            events = pygame.event.get()
        except Exception as exc:
            log.error("controller polling failed, stopping: %s", exc)
            self.stop()
            return

        if any(
            event.type in (pygame.CONTROLLERDEVICEADDED, pygame.CONTROLLERDEVICEREMOVED,
                           pygame.JOYDEVICEADDED, pygame.JOYDEVICEREMOVED)
            for event in events
        ):
            self._sync_pads()

        if not self._pads:
            return

        # Everything below this line is discarded while a game has the foreground.
        if not self.window_is_active():
            self._reset_held()
            return

        pad = self._active_pad()
        if pad is None:
            return

        self._emit_buttons(pad)
        self._emit_direction(pad)

    # -- battery ------------------------------------------------------------------------------

    def power_level(self) -> str:
        """The active pad's battery, as SDL last reported it."""
        return self._power

    def refresh_power(self) -> None:
        """Re-read the active pad's battery. Called on a slow timer, never while polling.

        The level is read from the plain joystick on the same device index: pygame's
        game-controller wrapper does not expose it at all, which was checked against the
        real hardware rather than assumed.
        """
        level = rules.POWER_UNKNOWN
        pad = self._pads.get(self._active_id) if self._active_id is not None else None
        if pad is None:
            pad = next(iter(self._pads.values()), None)
        if pad is not None:
            index = self._device_index.get(getattr(pad, "id", -1))
            if index is not None:
                level = _joystick_power(index)
        if level != self._power:
            log.info("controller battery: %s", level)
            self._power = level
            self.powerChanged.emit(level)

    def _reset_held(self) -> None:
        self._direction = ""
        self._pressed.clear()

    def _active_pad(self):
        """The pad being touched. Sticky: it stays active until another one moves."""
        current = self._pads.get(self._active_id) if self._active_id is not None else None
        if current is not None and self._has_input(current):
            return current
        for iid, pad in self._pads.items():
            if iid != self._active_id and self._has_input(pad):
                log.info("active controller is now %s", self._name(pad))
                self._active_id = iid
                self.refresh_power()
                self._note_family()
                self._reset_held()
                return pad
        return current if current is not None else next(iter(self._pads.values()), None)

    def _has_input(self, pad) -> bool:
        try:
            if any(pad.get_button(b) for b in _button_map()):
                return True
            if any(pad.get_button(b) for b in _dpad_map()):
                return True
            return bool(self._stick_direction(pad))
        except Exception as exc:
            log.debug("reading pad state failed: %s", exc)
            return False

    def _stick_direction(self, pad) -> str:
        try:
            x = pad.get_axis(pygame.CONTROLLER_AXIS_LEFTX) / 32768.0
            y = pad.get_axis(pygame.CONTROLLER_AXIS_LEFTY) / 32768.0
        except Exception as exc:
            log.debug("reading axes failed: %s", exc)
            return ""
        dead = rules.CONTROLLER_AXIS_DEADZONE
        if abs(x) < dead and abs(y) < dead:
            return ""
        if abs(x) >= abs(y):
            return RIGHT if x > 0 else LEFT
        return DOWN if y > 0 else UP

    def _emit_buttons(self, pad) -> None:
        for button, name in _button_map().items():
            try:
                down = bool(pad.get_button(button))
            except Exception as exc:
                log.debug("reading button %s failed: %s", button, exc)
                continue
            if down and button not in self._pressed:
                self._pressed.add(button)
                log.debug("controller action %s", name)
                self.action.emit(name)
            elif not down:
                self._pressed.discard(button)

    def _emit_direction(self, pad) -> None:
        direction = ""
        for button, name in _dpad_map().items():
            try:
                if pad.get_button(button):
                    direction = name
                    break
            except Exception as exc:
                log.debug("reading dpad failed: %s", exc)
        if not direction:
            direction = self._stick_direction(pad)

        now = time.monotonic()
        if direction != self._direction:
            self._direction = direction
            if direction:
                self._next_repeat = now + rules.CONTROLLER_REPEAT_DELAY_MS / 1000.0
                self.action.emit(direction)
            return
        if direction and now >= self._next_repeat:
            self._next_repeat = now + rules.CONTROLLER_REPEAT_RATE_MS / 1000.0
            self.action.emit(direction)
