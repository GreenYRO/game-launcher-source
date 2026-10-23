"""Phase 99: one question for the friends, and three things for the eye.

  1. the one question: due exactly when the switch is off, it was never asked and this start did not ask
     the first-run ones -- never otherwise, never on a copy of the user's own config; shown a second after
     the window first appears; "Not now" by default and Escape; worked by the pad; the day it was asked
     written on both answers, the switch only on yes and nothing else; another dialog up, it waits;
  2. version_seen written at start, by its own key; never by a first run's start before its question;
  3. the accent: five families, Violet's table as it was, AA on the dark surfaces for all five; a pick shows
     at once (Settings included) and OK keeps it by its own key, Cancel puts it back; what carries it; a
     game's own colour untouched; the pills painted round, their edge growing with the interface;
  4. Starting...: an exe started off the GUI thread with the window answering; every surface says so and
     Play rests; each way it ends (the screen taken, closed at once, seen running, the backstop, Escape, a
     click, B); a failure ends it before its dialog; a game already running never shows it; reduced motion;
  5. the genre pill: the library's genres with counts and "No genre known", AND with the chips and the
     search, the count line, its own key, an unknown value as all, the wave on a pick only, the pad;
  6. the documents: CLAUDE.md's row and layout, ARHITECTURA 5.5-5.7 and its maps, CITESTE-MA on its page,
     the two explanation pages and their index, the build log's notes; the version not raised.

On a throwaway copy of the data; the network is blocked; the user's config and library are photographed
at the start and compared at the end.
"""
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import sources  # the build log's notes (Phase 91)
import test_sandbox

# The question unanswered in this copy: the sandbox writes it as asked for every other suite.
box = test_sandbox.start({"allow_network": False, "startup_scan": False, "tv_mode": False,
                          "tray_offer_shown": None, "version_seen": None})
box.copy_cache("steam_details", "steam_web.json", "steam_search.json")
attempts: list[str] = []


def no_network(request, *args, **kwargs):
    attempts.append(getattr(request, "full_url", str(request)))
    raise OSError("the network is blocked in this suite")


urllib.request.urlopen = no_network

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

app = QApplication([])

from adapters import controller
from presentation import ui_offer, ui_rules, ui_tv, ui_window
from shared import rules, version

passed = failed = 0


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"   PASS  {name}")
    else:
        failed += 1
        print(f"   FAIL  {name}   {detail}")


def unreached(section, exc):
    import traceback
    traceback.print_exc()
    check(f"section {section} ran to its end", False, repr(exc))


def settle(seconds):
    loop = QEventLoop()
    QTimer.singleShot(int(seconds * 1000), loop.quit)
    loop.exec()


def press(window, name: str) -> None:
    """A button as the hub sends it: emitted from inside a timer, queued to the window."""
    QTimer.singleShot(0, lambda: window.pads.action.emit(name))


def saved() -> dict:
    return box.read_json("config.json")


print("=== 1. the one question ===")
try:
    check("the sandbox writes the question as asked under the launcher's own name for it",
          rules.TRAY_OFFER_KEY in test_sandbox.ALWAYS_WRITTEN)
    before = saved()
    check("this copy: the switch off, never asked", not before.get(rules.KEEP_RUNNING_KEY)
          and not before.get(rules.TRAY_OFFER_KEY), {k: before.get(k) for k in (rules.KEEP_RUNNING_KEY, rules.TRAY_OFFER_KEY)})
    window = ui_window.MainWindow()
    window.detail.allow_network = False
    window.resize(1280, 820)
    shown_at = []
    seen: dict = {}
    real_exec = ui_offer.TrayOfferDialog.exec

    def watched_exec(dialog):
        shown_at.append(time.monotonic())
        seen["dialog"] = dialog
        seen["focus"] = None
        QTimer.singleShot(300, lambda: seen.update(focus=QApplication.focusWidget(),
                                                   default=dialog.not_now_button.isDefault()))
        # The pad: right to "Keep it running"? No -- B, as someone who does not want it, says Not now.
        QTimer.singleShot(500, lambda: press(window, controller.BACK))
        return real_exec(dialog)

    ui_offer.TrayOfferDialog.exec = watched_exec
    # The clock before show(): the first paint happens inside it (the first row's covers read from disk, about
    # 0.2 s on 22 October), and the question's second is counted from the show (Phase 104).
    first_paint = time.monotonic()
    window.show()
    window.raise_()
    window.activateWindow()
    settle(0.6)
    check("not before the window has settled: nothing yet at 0.6 s", not shown_at)
    settle(2.4)
    after = saved()
    check(f"asked a second after the first paint ({(shown_at[0] - first_paint) if shown_at else 0:.1f} s)",
          bool(shown_at) and 0.9 <= shown_at[0] - first_paint < 2.5, shown_at)
    dialog = seen.get("dialog")
    check("in the first-run questions' style, its words the brief's", dialog is not None
          and dialog.objectName() == "FirstRun" and ui_offer.TEXT.startswith("Game Launcher can stay in the tray")
          and "Start with Windows" not in ui_offer.TEXT and "start it with Windows" in ui_offer.LATER)
    check("Not now is the default, and the ring starts on it", seen.get("default") is True
          and seen.get("focus") is getattr(dialog, "not_now_button", None), seen)
    check("B on the pad says Not now: the day it was asked written, the switch still off",
          after.get(rules.TRAY_OFFER_KEY) and not after.get(rules.KEEP_RUNNING_KEY) and window.tray is None
          and not window.keep_running, {k: after.get(k) for k in (rules.TRAY_OFFER_KEY, rules.KEEP_RUNNING_KEY)})
    changed = {k for k in set(before) | set(after) if before.get(k) != after.get(k)}
    check("and nothing else in config.json changed but version_seen", changed <= {rules.TRAY_OFFER_KEY,
                                                                                rules.VERSION_SEEN_KEY}, changed)
    window.offer_tray()
    settle(0.3)
    check("never twice: asked again, nothing shows", len(shown_at) == 1)

    # Yes, by the pad: right to Keep it running, A.
    window.config.pop(rules.TRAY_OFFER_KEY, None)
    shown_at.clear()

    def yes_exec(dialog):
        shown_at.append(time.monotonic())
        QTimer.singleShot(300, lambda: press(window, controller.RIGHT))
        QTimer.singleShot(600, lambda: seen.update(on=QApplication.focusWidget()))
        QTimer.singleShot(800, lambda: press(window, controller.ACTIVATE))
        return real_exec(dialog)

    ui_offer.TrayOfferDialog.exec = yes_exec
    before = saved()
    window.offer_tray()
    settle(0.3)
    after = saved()
    check("right moves the ring to Keep it running", seen.get("on") is not None
          and getattr(seen.get("on"), "text", lambda: "")() == ui_offer.KEEP, seen.get("on"))
    check("A on it: the switch on, the day written, the tray icon up -- nothing else",
          after.get(rules.KEEP_RUNNING_KEY) is True and after.get(rules.TRAY_OFFER_KEY) and window.keep_running
          and {k for k in set(before) | set(after) if before.get(k) != after.get(k)}
          <= {rules.TRAY_OFFER_KEY, rules.KEEP_RUNNING_KEY}, {k: after.get(k) for k in (rules.KEEP_RUNNING_KEY,)})

    # Escape, at the desk.
    window.config.pop(rules.TRAY_OFFER_KEY, None)
    window._set_keep_running(False)
    window.config[rules.KEEP_RUNNING_KEY] = False

    def escape_exec(dialog):
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QKeyEvent
        from PySide6.QtCore import QEvent

        def escape():
            QApplication.sendEvent(dialog, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
        QTimer.singleShot(300, escape)
        return real_exec(dialog)

    ui_offer.TrayOfferDialog.exec = escape_exec
    window.offer_tray()
    settle(0.3)
    check("Escape is Not now", saved().get(rules.TRAY_OFFER_KEY) and not window.keep_running)

    ui_offer.TrayOfferDialog.exec = lambda dialog: shown_at.append("shown") or QDialog.DialogCode.Rejected
    shown_at.clear()
    cases = []
    for label, setup, due in (
            ("the switch on", lambda: (window.config.pop(rules.TRAY_OFFER_KEY, None),
                                       setattr(window, "keep_running", True)), False),
            ("already asked", lambda: (setattr(window, "keep_running", False),
                                       window.config.__setitem__(rules.TRAY_OFFER_KEY, "2026-10-19")), False),
            ("a first run's start", lambda: (window.config.pop(rules.TRAY_OFFER_KEY, None),
                                             setattr(window, "_first_run_start", True)), False),
            ("the switch off and never asked, on a later start", lambda: setattr(window, "_first_run_start", False), True)):
        setup()
        cases.append((label, window.tray_offer_due(), due))
    check("due exactly when all three hold: " + "; ".join(f"{l} -> {d}" for l, d, _w in cases),
          all(d == w for _l, d, w in cases), cases)
    real = json.loads(test_sandbox.read_real("config.json"))
    window.keep_running = bool(real.get(rules.KEEP_RUNNING_KEY, rules.KEEP_RUNNING_DEFAULT))
    window.config[rules.TRAY_OFFER_KEY] = real.get(rules.TRAY_OFFER_KEY)
    check(f"on the user's own config (Keep running {'on' if window.keep_running else 'off'}) it is never due",
          window.keep_running and not window.tray_offer_due() or bool(real.get(rules.TRAY_OFFER_KEY)),
          (window.keep_running, real.get(rules.TRAY_OFFER_KEY)))
    # Another dialog up: it waits, and asks once that one is gone.
    window.keep_running = False
    window.config.pop(rules.TRAY_OFFER_KEY, None)
    shown_at.clear()
    blocker = QMessageBox(QMessageBox.Icon.Information, "Another", "Another question", parent=window)
    QTimer.singleShot(200, window.offer_tray)
    QTimer.singleShot(900, blocker.accept)
    blocker.exec()
    held = list(shown_at)
    settle(rules.TRAY_OFFER_RETRY_MS / 1000 + 0.6)
    check("with another dialog up it waits, and asks once that one has gone", held == [] and shown_at == ["shown"],
          (held, shown_at))
    ui_offer.TrayOfferDialog.exec = real_exec
except Exception as exc:
    unreached("1", exc)

print("\n=== 2. version_seen ===")
try:
    check(f"written at start, by its own key: {saved().get(rules.VERSION_SEEN_KEY)}",
          saved().get(rules.VERSION_SEEN_KEY) == version.APP_VERSION and window.config.get(rules.VERSION_SEEN_KEY)
          == version.APP_VERSION)
    window.first_run = True
    window.config[rules.VERSION_SEEN_KEY] = "0.0.1"
    window._note_version()
    check("a first run's start writes nothing before its question", window.config.get(rules.VERSION_SEEN_KEY) == "0.0.1"
          and saved().get(rules.VERSION_SEEN_KEY) == version.APP_VERSION)
    window.first_run = False
    window._note_version()
    check("an older one is brought up to this version", saved().get(rules.VERSION_SEEN_KEY) == version.APP_VERSION)
    source = (PROJECT / "presentation" / "ui_window.py").read_text(encoding="utf-8")
    check("and the first-run answer carries it", '"enable_xbox": xbox, rules.VERSION_SEEN_KEY: version.APP_VERSION'
          in source)
except Exception as exc:
    unreached("2", exc)

print("\n=== 3. the accent ===")
try:
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QColor
    from presentation import ui_settings, ui_theme

    def lum(hex_colour):
        c = QColor(hex_colour)
        parts = []
        for v in (c.redF(), c.greenF(), c.blueF()):
            parts.append(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4)
        return 0.2126 * parts[0] + 0.7152 * parts[1] + 0.0722 * parts[2]

    def ratio(a, b):
        hi, lo = sorted((lum(a), lum(b)), reverse=True)
        return (hi + 0.05) / (lo + 0.05)

    def near(a: QColor, b: QColor, within=26):
        return abs(a.red() - b.red()) + abs(a.green() - b.green()) + abs(a.blue() - b.blue()) <= within

    names = list(ui_rules.ACCENTS)
    check("five families, Violet first and the default", names == ["Violet", "Teal", "Amber", "Rose", "Slate"]
          and ui_rules.ACCENT_DEFAULT == "Violet" and all(sorted(f) == [100, 200, 300, 400, 500, 600, 700, 800, 900]
                                                          for f in ui_rules.ACCENTS.values()))
    check("test copies never carry an accent: the suites measure Violet", "accent" in test_sandbox.NEVER_COPIED
          and ui_rules.ACCENT_KEY == "accent")
    violet = ui_rules.ACCENTS["Violet"]
    drift = [n for n, step in ui_rules.ACCENT_STEPS.items() if getattr(ui_rules, n) != violet[step]]
    check("at Violet every named colour is exactly the table's step -- today's palette, unchanged", not drift, drift)
    ui_theme.use_accent("Violet")
    forms = {n: getattr(ui_rules, n) for n in ui_rules.ACCENT_FORMS}
    check("and so are the colours written in another form (rgba, #AARRGGBB)",
          forms["COLOR_PRIMARY_HOVER"] == "rgba(145, 132, 217, 31)" and forms["COLOR_STORAGE_BAR"] == "#299184d9"
          and forms["COLOR_REPORT_LORENZ_FILL"] == "#2e9184d9", forms)
    grounds = {"the ground": ui_rules.COLOR_BACKGROUND, "a card": ui_rules.COLOR_SURFACE}
    low = []
    for name, f in ui_rules.ACCENTS.items():
        pairs = [(f[500], g, 4.5) for g in grounds.values()] + [(f[400], g, 4.5) for g in grounds.values()]
        pairs += [(f[300], ui_rules.COLOR_BACKGROUND, 3.0), (f[200], f[900], 4.5), (f[100], f[900], 4.5),
                  (f[100], f[800], 4.5), (f[500], ui_rules.COLOR_SURFACE_RAISED, 3.0), (f[600], ui_rules.COLOR_BACKGROUND, 3.0)]
        low += [(name, a, b, round(ratio(a, b), 2)) for a, b, floor in pairs if ratio(a, b) < floor]
    check("all five keep AA contrast for text and marks on the dark surfaces", not low, low)
    check("an unknown name is the default's", ui_theme.use_accent("Chartreuse") == "Violet")
    game_colour = ui_theme.accent_for("Some Game").name()

    window.config["library_layout"] = "rail"
    window._apply_layout()
    window.show_library()
    settle(0.6)
    place = window.rail.places["library"]
    spot = place.mapTo(window, QPoint(place.width() - 20, 4))
    before = window.grab().toImage().pixelColor(spot)
    settings_exec = ui_settings.SettingsDialog.exec
    notes: dict = {}

    def drive_settings(dialog, answer):
        def steps():
            dialog.accent_swatches["Violet"].setFocus()
            window.pads.action.emit(controller.RIGHT)  # along the row: Teal
            QTimer.singleShot(400, lambda: notes.update(after_right=dialog.accent(), live=window.accent,
                                                        pixel=window.grab().toImage().pixelColor(spot)))
            QTimer.singleShot(600, lambda: window.pads.action.emit(controller.RIGHT))  # Amber
            QTimer.singleShot(800, lambda: window.pads.action.emit(controller.LEFT))  # back to Teal
            QTimer.singleShot(1000, lambda: window.pads.action.emit(controller.ACTIVATE))  # A picks the one it is on
            QTimer.singleShot(1300, lambda: notes.update(picked=dialog.accent()))
            QTimer.singleShot(1500, dialog.accept if answer == "ok" else dialog.reject)
        QTimer.singleShot(300, steps)
        return settings_exec(dialog)

    ui_settings.SettingsDialog.exec = lambda dialog: drive_settings(dialog, "cancel")
    window.open_settings()
    settle(0.4)
    check("in Settings the pad moves along the swatches and the window follows at once",
          notes.get("after_right") == "Teal" and notes.get("live") == "Teal"
          and near(notes.get("pixel", QColor()), QColor(ui_rules.ACCENTS["Teal"][900]), 30)
          and not near(before, notes.get("pixel", QColor()), 6), (notes, before.name()))
    check("A picks the one the ring is on", notes.get("picked") == "Teal", notes)
    check("Cancel puts the accent back as it was, and writes nothing", window.accent == "Violet"
          and ui_rules.COLOR_ACCENT == violet[500] and saved().get(ui_rules.ACCENT_KEY) is None
          and near(window.grab().toImage().pixelColor(spot), before, 6))
    ui_settings.SettingsDialog.exec = lambda dialog: drive_settings(dialog, "ok")
    window.open_settings()
    settle(0.6)
    teal = ui_rules.ACCENTS["Teal"]
    shot = window.grab().toImage()
    check("OK keeps it, by its own key", window.accent == "Teal" and saved().get(ui_rules.ACCENT_KEY) == "Teal")
    check("the rail's chosen place, its section labels and a chosen chip's fill in Teal",
          near(shot.pixelColor(spot), QColor(teal[900]), 30) and ui_rules.COLOR_SECTION_LABEL == teal[500]
          and ui_rules.COLOR_CHIP_CHOSEN == teal[900] and ui_rules.COLOR_RAIL_TOP == "#99" + teal[900][1:])
    check("the stylesheet rebuilt in it", teal[500] in window.styleSheet() and violet[500] not in window.styleSheet())
    glow = ui_theme.soft_edge(40, 40, 8, 12, ui_rules.COLOR_ACCENT, 255).toImage().pixelColor(14, 26)
    check("a glow asked for now is Teal's (the halo cache is keyed by its colour)", glow.hue() in range(150, 200), glow.hue())
    brand = window.rail.brand.pixmap().toImage()
    hue = max((brand.pixelColor(x, brand.height() // 2) for x in range(brand.width())), key=lambda c: c.alpha()).hue()
    check(f"an icon painted once -- the rail's brand -- painted again in it (hue {hue})", hue in range(150, 200), hue)
    check("a game's own colour is the game's: untouched", ui_theme.accent_for("Some Game").name() == game_colour)
    # The pills (Phase 99, reported from use): their boxes are painted, not the stylesheet's.
    chip = window.library.chips["all"]
    check("the chips' and switches' boxes are painted round, the stylesheet's border transparent",
          "QPushButton#Chip, QPushButton#ToggleChip {{" not in window.styleSheet()
          and "border: 1px solid transparent" in ui_theme.stylesheet(1.0)
          and type(window.library.hidden_box).__name__ == "PillToggle", type(window.library.hidden_box))
    check("their edge a little wider with the interface's size, never under a pixel",
          ui_theme.pill_edge(1.0) == 1.0 and ui_theme.pill_edge(1.25) == 1.25 and ui_theme.pill_edge(0.85) == 1.0)

    probe = ui_settings.SettingsDialog(window.config, window, known_keys=set())
    probe.show()
    settle(0.5)
    ok = next(b for b in probe.findChildren(ui_settings.QPushButton) if b.text() == "OK")
    check("Settings opens on the swatch chosen -- not handed to OK, as Qt does a dialog whose first control is a button",
          probe.focusWidget() is probe.accent_swatches["Teal"], type(probe.focusWidget()).__name__)
    check("and OK stays the default, its outline in the accent: a swatch is never the default",
          ok.isDefault() and not any(s.isDefault() or s.autoDefault() for s in probe.accent_swatches.values()))
    probe.reject()
    settle(0.2)

    # A restart: the same accent, the same pixels.
    shot_before = window.grab().toImage().pixelColor(spot)
    window._stop_watch()
    window._shut_down = True
    window.close()
    settle(0.3)
    window.overrides.close()
    ui_theme.use_accent("Violet")  # as a new process begins: Violet, until the window reads config.json
    window = ui_window.MainWindow()
    window.config["library_layout"] = "rail"
    window.resize(1280, 820)
    window.show()
    settle(1.6)
    window._apply_layout()
    window.show_library()
    settle(0.6)
    check("after a restart the same accent, the same pixel on the rail", window.accent == "Teal"
          and near(window.grab().toImage().pixelColor(spot), shot_before, 4), (window.accent,))
except Exception as exc:
    unreached("3", exc)
finally:
    if "settings_exec" in dir():
        ui_settings.SettingsDialog.exec = settings_exec

print("\n=== 4. Starting... ===")
try:
    import threading
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtCore import QEvent
    from logic import launch
    from presentation import ui_actions, ui_continue, ui_library

    real_launch = launch.launch_game
    real_critical = ui_actions.QMessageBox.critical
    window.config["library_layout"] = "top"
    window._apply_layout()
    window.show_library()
    window.raise_()
    window.activateWindow()
    settle(0.6)
    exe = next(v for v in window.views if v.entry.launch_kind == "exe" and not v.hidden)
    uri = next((v for v in window.views if v.entry.launch_kind == "uri" and not v.hidden), None)
    during: dict = {}

    def slow_start(view):
        during["thread"] = threading.current_thread() is not threading.main_thread()
        time.sleep(0.7)
        return launch.LaunchResult(True, running=None)

    launch.launch_game = slow_start
    window._set_keep_running(True)
    window.config[rules.KEEP_RUNNING_KEY] = True
    QTimer.singleShot(250, lambda: during.update(
        answered=True, splash=window.splash.showing, key=window.starting_key,
        tile=ui_library.tile_subtitle(exe, None, False, window.is_starting(exe.key)),
        tray=window.tray.icon.toolTip() if window.tray is not None else None,
        detail=window.detail.starting, again=(ui_actions.play(window, exe) is None and window.starting_key == exe.key)))
    ui_actions.play(window, exe)
    check("an exe's start runs off the window's thread", during.get("thread") is True, during)
    check("and the window answers meanwhile: the splash up, Starting... on the tile and the tray",
          during.get("answered") and during.get("splash") and during.get("key") == exe.key
          and during.get("tile") == ui_rules.STARTING_TEXT and (during.get("tray") or "").startswith("Starting "),
          during)
    check("Play rests while it starts: a second press starts nothing", during.get("again") is True)
    check("the game's page says Starting... too, and its Play rests",
          (window.show_detail(exe.key) or True) and settle(0.6) is None and window.detail.starting
          and window.detail.play_button.text() == ui_rules.STARTING_TEXT and not window.detail.play_button.isEnabled())
    window.show_library()
    settle(0.5)
    # 1. the game took the screen
    app.applicationStateChanged.emit(Qt.ApplicationState.ApplicationInactive)
    settle(0.2)
    check("it ends when the launcher loses the foreground (the game took the screen)",
          window.starting_key is None and not window.splash.showing)
    check("and every surface says what is true again", not window.detail.starting
          and ui_library.tile_subtitle(exe, None, False, window.is_starting(exe.key)) != ui_rules.STARTING_TEXT)
    launch.launch_game = lambda view: launch.LaunchResult(True, running=None)
    # 2. the tracker saw it close at once
    ui_actions.play(window, exe)
    # Only the hook: what a session's end does besides (the saves, a scan, the front) is stood in for.
    held = {name: getattr(window, name) for name in ("_queue_after_session", "_come_back_to_front",
                                                     "_run_wanted_scan", "_run_saves")}
    real_poll = window.tracker.poll
    window.tracker.poll = lambda: [launch.Tick(exe.key, exe.display_name, 0, True, None, 0)]
    for name in held:
        setattr(window, name, lambda *a, **k: None)
    try:
        window._poll_playtime()
    finally:
        window.tracker.poll = real_poll
        for name, fn in held.items():
            setattr(window, name, fn)
    check("it ends when the tracker sees the game close straight away", window.starting_key is None)
    # 3. the watcher saw a store's game running
    target = uri or exe
    ui_actions.play(window, target)
    real_feed, real_worker = window.observer.feed, window.process_worker
    from datetime import datetime as _dt
    from logic import observe

    def seen_as(view):
        return observe.Seen(view.key, view.display_name, False, view.entry.launch_kind,
                            _dt.now().astimezone(), time.monotonic())


    def fed(keys, watched, active, now, local):
        window.observer.live[target.key] = seen_as(target)
        return []

    window.observer.feed, window.process_worker = fed, object()
    window._on_seen([], time.monotonic())
    window.observer.feed, window.process_worker = real_feed, real_worker
    window.observer.live.pop(target.key, None)
    check("it ends when the watcher sees the game running (a store's game)", window.starting_key is None)
    # 4. the time it may take
    saved_max = rules.LAUNCH_SPLASH_MAX_S
    rules.LAUNCH_SPLASH_MAX_S = 1
    ui_actions.play(window, exe)
    settle(1.3)
    rules.LAUNCH_SPLASH_MAX_S = saved_max
    check(f"it ends after LAUNCH_SPLASH_MAX_S at most ({saved_max} s; 1 s here)", window.starting_key is None)
    # 5. Escape, a click, B
    for how in ("escape", "click", "pad"):
        ui_actions.play(window, exe)
        settle(0.2)
        if how == "escape":
            QApplication.sendEvent(window.splash, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape,
                                                            Qt.KeyboardModifier.NoModifier))
        elif how == "click":
            from PySide6.QtTest import QTest
            QTest.mouseClick(window.splash, Qt.MouseButton.LeftButton)
        else:
            press(window, controller.BACK)
        settle(0.3)
        check(f"it ends on {'Escape' if how == 'escape' else 'a click' if how == 'click' else 'B on the pad'}",
              window.starting_key is None and not window.splash.showing)
    # A start that fails: the splash goes, the dialog is today's.
    said: list = []
    ui_actions.QMessageBox.critical = lambda parent, title, text: said.append((title, text, window.splash.showing))
    launch.launch_game = lambda view: launch.LaunchResult(False, error="The file is gone")
    ui_actions.play(window, exe)
    check("a start that fails ends it first, and the dialog is exactly today's",
          window.starting_key is None and said and said[0][0] == "Could not start" and "would not start" in said[0][1]
          and said[0][2] is False, said)
    ui_actions.QMessageBox.critical = real_critical
    # A game already running never shows it.
    launch.launch_game = lambda view: launch.LaunchResult(True, running=None)
    window.observer.live[exe.key] = seen_as(exe)
    window.play(exe)
    check("a game already running never shows it", window.starting_key is None and not window.splash.showing)
    window.observer.live.pop(exe.key, None)
    # Reduce animations: plain.
    window.reduce_animations = True
    ui_actions.play(window, exe)
    settle(0.3)
    check("with Reduce animations it is shown plain: no fade, no moving dots",
          window.splash.showing and window.splash._opacity == 1.0 and not window.splash._dots.isActive())
    window.end_starting("test")
    window.reduce_animations = False
    window._set_keep_running(False)
    launch.launch_game = real_launch
except Exception as exc:
    unreached("4", exc)
finally:
    if "real_launch" in dir():
        launch.launch_game = real_launch

print("\n=== 5. the genre pill ===")
try:
    lib = window.library
    pill = lib.genre_pill
    window.show_library()
    settle(0.5)
    genres = window.overrides.genres()
    shown = [v for v in window.views if not v.hidden and not v.is_non_game]
    want: dict = {}
    for view in shown:
        for name in genres.get(view.key, ()):
            want[name] = want.get(name, 0) + 1
    unknown = sum(1 for v in shown if not genres.get(v.key))
    entries = [(pill.itemText(i), pill.itemData(i, ui_library.COUNT_ROLE)) for i in range(pill.count())]
    check(f"the genres present, with their counts, and No genre known ({unknown})",
          entries[0] == (ui_rules.GENRE_ALL, len(shown)) and dict(entries[1:-1] if unknown else entries[1:]) == want
          and (entries[-1] == (ui_rules.GENRE_NONE, unknown) if unknown else True), entries)
    check("never a content warning among them", not any(n in ("Nudity", "Violent") for n, _c in entries))
    waves: list = []
    real_wave = lib.play_entrance
    lib.play_entrance = lambda: waves.append(1)
    top = entries[1][0]
    lib._genre_picked(next(i for i in range(pill.count()) if pill.itemText(i) == top))
    settle(0.4)
    check(f"picking {top} shows its games only", all(top in genres.get(k, ()) for k in lib.visible_keys)
          and len(lib.visible_keys) == want[top], (len(lib.visible_keys), want[top]))
    check("the count line says what is showing", f"· {top}" in lib.count_label.text(), lib.count_label.text())
    check("remembered by its own key", saved().get(ui_rules.LIBRARY_GENRE_KEY) == top)
    check("the wave on a pick", len(waves) == 1)
    lib.refresh()
    check("and never on a refresh", len(waves) == 1)
    lib.chips["favorites"].click()
    settle(0.3)
    both = [k for k in lib.visible_keys]
    check("with a chip, an AND: favourites of that genre only", all(window.by_key[k].favorite and top in genres.get(k, ())
                                                                    for k in both))
    lib.chips["all"].click()
    lib.filter_box.setText("zzz-nothing")
    settle(0.3)
    check("and with the search, an AND too", lib.visible_keys == [])
    lib.filter_box.setText("")
    settle(0.2)
    if unknown:
        lib._genre_picked(pill.count() - 1)
        settle(0.3)
        check("No genre known shows the games with no genre -- never hidden by a filter they cannot match",
              len(lib.visible_keys) == unknown and all(not genres.get(k) for k in lib.visible_keys))
    waves_before, written_before = len(waves), saved().get(ui_rules.LIBRARY_GENRE_KEY)
    lib.set_genre("Not a genre at all")
    check("an unknown value is all of them", pill.chosen() == ui_rules.GENRE_ALL and len(lib.visible_keys) == len(shown))
    lib.set_genre(top)
    check("set_genre puts one back quietly: no wave, no write", len(waves) == waves_before and pill.chosen() == top
          and saved().get(ui_rules.LIBRARY_GENRE_KEY) == written_before, (len(waves), waves_before, pill.chosen()))
    lib.set_genre(ui_rules.GENRE_ALL)
    lib.play_entrance = real_wave
    # The pad: up from the card to the row above the grid, along it, A opens the genre list, down and A picks.
    window.library.list.setFocus()
    window.library.list.setCurrentRow(0)
    settle(0.2)
    press(window, controller.UP)  # onto the Continue card
    settle(0.3)
    press(window, controller.UP)  # and on up to the row of controls
    settle(0.3)
    on_row = lib.on_controls
    controls = lib._controls()
    steps = controls.index(pill) - lib._control_at
    for _ in range(max(0, steps)):
        press(window, controller.RIGHT)
        settle(0.15)
    at_pill = QApplication.focusWidget() is pill
    ringed = lib.controls_ring.target is pill
    press(window, controller.ACTIVATE)
    settle(0.5)
    opened = QApplication.activePopupWidget() is not None
    press(window, controller.DOWN)
    settle(0.2)
    press(window, controller.ACTIVATE)
    settle(0.6)
    check("the pad: up past the card reaches the row above the grid, along it to the genre pill, ringed",
          on_row and at_pill and ringed, (on_row, at_pill, ringed, steps))
    check("A opens its list, down and A pick the next genre: the grid follows", opened
          and pill.chosen() == entries[1][0] and QApplication.activePopupWidget() is None, (opened, pill.chosen()))
    press(window, controller.DOWN)
    settle(0.3)
    check("and down comes back off the row", not lib.on_controls)
    # Suite 32 found it: the pad left on the row by "up" with no card, a tile chosen another way, then up did nothing.
    lib._enter_controls()
    lib.select_key(lib.visible_keys[0])
    check("a tile the window chooses takes the pad off the row, its ring with it",
          not lib.on_controls and lib.controls_ring.target is None, (lib.on_controls, lib.controls_ring.target))
    lib._enter_controls()
    lib.list.pressed.emit(lib.list.model().index(0, 0))
    check("and so does a click on a tile", not lib.on_controls)
    lib.set_genre(ui_rules.GENRE_ALL)
    window.config.pop(ui_rules.LIBRARY_GENRE_KEY, None)
except Exception as exc:
    unreached("5", exc)

print("\n=== 6. the documents ===")
try:
    def doc(name):
        return (PROJECT / name).read_text(encoding="utf-8").replace("\r\n", "\n")

    claude = doc("CLAUDE.md")
    row = next(line for line in claude.splitlines() if line.startswith("| 99 |"))
    check("CLAUDE.md: row 99 has all three steps done", all(f"**{n} of 3 done**" in row for n in (1, 2, 3)))
    check("CLAUDE.md's layout names the splash, the start's thread and the offer",
          all(f"  {name}" in claude for name in ("ui_splash.py", "launch_worker.py", "ui_offer.py")))
    arch = doc("docs/ARHITECTURA.md")
    heads = [arch.index(h) for h in ("### 5.5 For you", "### 5.6 Culoarea de accent", "### 5.7 „Starting…”")]
    check("ARHITECTURA: 5.5, 5.6 and 5.7 in order, the splash and the thread in its maps",
          heads == sorted(heads) and "`ui_splash.py` *(Faza 99)*" in arch and "`launch_worker.py` *(Faza 99)*" in arch)
    readme = doc("docs/CITESTE-MA.md")
    check("CITESTE-MA: Starting and the genre filter, still on its one page, naming the current version",
          "**Starting…**" in readme and "după gen" in readme and len(readme.splitlines()) <= 110
          and f"Versiunea {version.APP_VERSION}." in readme, len(readme.splitlines()))
    at_phase_99 = subprocess.run(["git", "show", "b665ee2:shared/version.py"], cwd=PROJECT, capture_output=True,
                                 text=True, encoding="utf-8").stdout
    check("no version raised in this phase: 1.2.7 at its last commit, the raise was Phase 100's",
          'APP_VERSION = "1.2.7"' in at_phase_99, at_phase_99[-200:])
    sections = ("## Ce s-a construit", "## De ce contează pentru lucrare", "## Cum funcționează",
                "## Cinci cuvinte", "## Trei întrebări ale comisiei", "## Ce nu poate face")
    for page in ("faza-97.md", "faza-99.md"):
        text = doc(f"docs/explicatii/{page}")
        check(f"docs/explicatii/{page}: the six parts, no file names or code",
              all(h in text for h in sections) and ".py" not in text and "`" not in text)
    index = doc("docs/explicatii/CITESTE-MA.md")
    check("the explanations' index names faza 97 and faza 99", "faza 97" in index and "faza 99" in index)
    log = sources.build_log()
    check("the build log has Phase 99's notes above Phase 98's",
          "## Phase 99 notes" in log and log.index("## Phase 99 notes") < log.index("## Phase 98 notes"))
except Exception as exc:
    unreached("6", exc)

if "window" in globals():
    window._stop_watch()  # the process watch's thread, before Python lets go of the window (an abort otherwise)
    if window.tray is not None:
        window._set_keep_running(False)
    window._shut_down = True
    window.overrides.close()
    settle(0.3)
changed = box.finish()
check("config.json, the library database and the Run key's value are unchanged", not changed, changed)
check("nothing in this suite reached the network", attempts == [], attempts)
print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
