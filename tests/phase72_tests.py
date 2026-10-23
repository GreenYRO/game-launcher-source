"""Phase 72: two annoyances reported from use.

1. "When I set a custom cover for a game it automatically makes it a banner too sometimes
   (check Rehaunted)." A game with no wide art of its own -- Steam has no hero for Rehaunted --
   got its cover blurred across the top of its page as frame 0 of the picture, in front of its
   screenshots. That frame is now only a stand-in: the first real image takes its place, at
   once if it is already on disk, by a fade if the stand-in was already on screen. A game with
   wide art of its own, or a banner chosen by hand, is as it was.
2. "When I open the settings, then click OK, the launcher unmaximizes itself." OK re-applied
   the TV/desk mode, and the desk side called showNormal() every time. And the same call
   brought a minimised launcher back after a game as a window, not maximised.

On a throwaway copy of the data, with the cached Steam records and screenshots copied in, read
only; nothing is fetched.
"""
import os
import sys
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import test_sandbox

# The window here is built directly, at the desk, as launcher.py builds it only when the settings
# say so; a copy of settings left in TV mode (the user's, 16 October) would make Settings' OK
# rightly go fullscreen. This suite is about the desk window, so it asks for it (Phase 91).
box = test_sandbox.start({"tv_mode": False})
REAL_SHOTS = PROJECT / "data" / "cache" / "screenshots"
box.copy_cache("steam_details", "steam_web.json",
               *[f"screenshots/{name}" for name in (os.listdir(REAL_SHOTS) if REAL_SHOTS.is_dir() else [])])

import logging

logging.basicConfig(level=logging.ERROR)

from PySide6.QtCore import QEventLoop, Qt, QTimer
from PySide6.QtWidgets import QApplication, QDialog

app = QApplication([])

from adapters.screenshot_worker import plan
from logic import focus, gamedetails
from presentation import ui_rules, ui_settings, ui_window
from shared import paths

passed = failed = 0


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"   PASS  {name}")
    else:
        failed += 1
        print(f"   FAIL  {name}   {detail}")


def unreached(section: str, exc: Exception):
    """A section that could not run to its end on this code counts as one failure."""
    check(f"section {section} runs to its end on this code", False, repr(exc))


def settle(seconds: float) -> None:
    loop = QEventLoop()
    QTimer.singleShot(int(seconds * 1000), loop.quit)
    loop.exec()


def cached_frames(view) -> list[str]:
    """The full-size screenshots of a game already on disk -- what its picture can cycle at once."""
    record = gamedetails.record_for(view)
    shots = gamedetails.screenshots(record, ui_rules.SCREENSHOT_MAX_PER_GAME) if record else []
    appid = str(view.entry.extra.get("appid") or "")
    _jobs, existing = plan(str(paths.cache_dir()), appid, shots[: ui_rules.BANNER_CYCLE_MAX_FRAMES], full=True)
    return [existing[i] for i in sorted(existing)]


window = ui_window.MainWindow()
window.detail.allow_network = False  # nothing fetched: only what is on disk
window.resize(1280, 820)
window.show()
settle(1.0)
banner = window.detail.banner

print("=== 1. a cover chosen by hand stays the cover; the picture cycles the game's images ===")
try:
    views = [v for v in window.views if not v.hidden]
    with_shots = {v.key: cached_frames(v) for v in views}
    chosen_no_wide = [v for v in views if v.data.get("cover") and not v.banner_source and with_shots[v.key]]
    print(f"   (games with a chosen cover, no wide art and screenshots on disk: "
          f"{', '.join(v.display_name for v in chosen_no_wide) or 'none'})")
    subject = next((v for v in chosen_no_wide if "rehaunted" in v.key), chosen_no_wide[0] if chosen_no_wide else None)
    check("there is such a game to look at (Rehaunted on this machine)", subject is not None)
    window.show_detail(subject.key)
    settle(1.5)
    check(f"{subject.display_name}: the picture starts on a screenshot, not the cover",
          banner.frames and banner.frames[0] == with_shots[subject.key][0], banner.frames[:2])
    check("and the cover is nowhere in the cycle", "" not in banner.frames, banner.frames)
    check("every screenshot on disk is in it, in order",
          banner.frames == with_shots[subject.key][: len(banner.frames)] and len(banner.frames) == len(with_shots[subject.key]),
          (len(banner.frames), len(with_shots[subject.key])))
    check("and it cycles: there are dots for them", len(banner._dot_rects()) == len(banner.frames) > 1)
    check("the cover beside the title is still the chosen cover",
          window.detail.cover_art.view.cover_source == subject.data.get("cover")
          or os.path.basename(window.detail.cover_art.view.cover_source) == os.path.basename(subject.data["cover"]))

    hero = next((v for v in views if v.banner_source and not v.data.get("banner") and with_shots[v.key]), None)
    if hero is not None:
        window.show_detail(hero.key)
        settle(1.0)
        check(f"a game with wide art of its own ({hero.display_name}): its hero still comes first",
              banner.frames and banner.frames[0] == "" and len(banner.frames) == 1 + len(with_shots[hero.key]),
              banner.frames[:2])
    picked = next((v for v in views if v.data.get("banner")), None)
    if picked is not None:
        window.show_detail(picked.key)
        settle(1.0)
        check(f"a banner chosen by hand ({picked.display_name}): shown alone, never cycled",
              banner.frames == [""] and not banner.cycling_allowed)
    bare = next((v for v in views if not v.banner_source and not with_shots[v.key]), None)
    if bare is not None:
        window.show_detail(bare.key)
        settle(1.0)
        check(f"a game with no images at all ({bare.display_name}): the stand-in stays, there is nothing else",
              banner.frames == [""])
except Exception as exc:
    unreached("1", exc)

print("\n=== 2. an image arriving after the stand-in was seen takes its place by a fade ===")
try:
    late = next(v for v in views if not v.banner_source and with_shots[v.key])
    shots = with_shots[late.key]
    banner.set_view(late)  # as the page does, before any image is on disk
    window.detail.grab()  # the stand-in is painted: it has been on screen
    check("the stand-in alone at first", banner.frames == [""])
    banner.add_frame(shots[0])
    check("a fade begins from it to the image", banner._replacing and banner._next_index == 1
          and banner._animation.state() == banner._animation.State.Running)
    check("no dots while the stand-in leaves", banner._dot_rects() == [])
    if len(shots) > 1:
        banner.add_frame(shots[1])  # another arrives during the fade
    settle(ui_rules.BANNER_CYCLE_FADE_MS / 1000 + 0.4)
    check("then the stand-in is gone and the image is the one showing",
          not banner._replacing and banner.frames[0] == shots[0] and "" not in banner.frames and banner.index == 0,
          (banner.frames, banner.index))
    check("an image that came during the fade is kept", len(shots) < 2 or banner.frames == shots[:2], banner.frames)
    banner.set_view(late)
    window.detail.grab()
    banner.add_frame(shots[0])
    banner.set_view(subject)  # another game opened mid-fade
    settle(ui_rules.BANNER_CYCLE_FADE_MS / 1000 + 0.3)
    check("a game opened in the middle of the fade keeps its own first frame",
          banner.frames == [""] and banner.index == 0, banner.frames)
except Exception as exc:
    unreached("2", exc)

window.show_library()
settle(0.5)

print("\n=== 3. Settings' OK leaves a maximised window maximised ===")
try:
    window.showMaximized()
    settle(0.8)
    check("the window is maximised to begin with", window.isMaximized())
    real_exec = ui_settings.SettingsDialog.exec
    ui_settings.SettingsDialog.exec = lambda self: QDialog.DialogCode.Accepted  # OK, nothing changed
    try:
        window.open_settings()
    finally:
        ui_settings.SettingsDialog.exec = real_exec
    settle(0.8)
    check("after OK it is still maximised", window.isMaximized() and not window.isFullScreen(),
          (window.isMaximized(), window.isFullScreen()))
    window.set_tv_mode(True)
    settle(0.8)
    check("TV mode is fullscreen", window.isFullScreen())
    window.set_tv_mode(False)
    settle(0.8)
    check("leaving TV mode goes back to maximised, as it was", window.isMaximized() and not window.isFullScreen(),
          (window.isMaximized(), window.isFullScreen()))
except Exception as exc:
    unreached("3", exc)

print("\n=== 4. coming back after a game restores a minimised window maximised ===")
try:
    window.showMaximized()
    settle(0.5)
    window.showMinimized()
    settle(0.8)
    check("minimised from maximised", window.isMinimized())
    real_empty, real_front = focus.foreground_is_empty, focus.bring_to_front
    focus.foreground_is_empty = lambda: True  # the game closed onto the bare desktop
    focus.bring_to_front = lambda hwnd: True
    try:
        window._come_back_to_front()
    finally:
        focus.foreground_is_empty, focus.bring_to_front = real_empty, real_front
    settle(0.8)
    check("back, and maximised again -- not a window", not window.isMinimized() and window.isMaximized(),
          (window.isMinimized(), window.isMaximized()))
    window.set_tv_mode(True)
    settle(0.5)
    window.showMinimized()
    settle(0.8)
    focus.foreground_is_empty = lambda: True
    focus.bring_to_front = lambda hwnd: True
    try:
        window._come_back_to_front()
    finally:
        focus.foreground_is_empty, focus.bring_to_front = real_empty, real_front
    settle(0.8)
    check("in TV mode it comes back fullscreen", window.isFullScreen(), window.windowState())
    window.set_tv_mode(False)
    settle(0.5)
except Exception as exc:
    unreached("4", exc)

window.close()
settle(0.3)

print("\n=== 5. the real library is exactly as it was found ===")
changed = box.finish()
check("config.json and the library database are unchanged", not changed, changed)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
