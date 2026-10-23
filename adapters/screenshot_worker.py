"""Fetching screenshots off the GUI thread.

Opening a game's page must never block on the network, so thumbnails arrive one at a time
and the strip fills in as they land. Anything already cached is used without a request, and
every download is size-checked like the rest of the project's art.
"""

from __future__ import annotations

import logging
import os

from PySide6.QtCore import QThread, Signal

from shared import rules
from web import steam_web

log = logging.getLogger(__name__)


def cache_path(cache_dir: str, appid: str, index: int, full: bool) -> str:
    kind = "full" if full else "thumb"
    return os.path.join(cache_dir, "screenshots", appid, f"{index:02d}_{kind}.jpg")


class ScreenshotWorker(QThread):
    """Downloads a list of images, emitting each as it lands."""

    ready = Signal(int, str)  # index, local path
    done = Signal()

    def __init__(self, jobs: list[tuple[int, str, str]], parent=None) -> None:
        super().__init__(parent)
        self.jobs = jobs  # (index, url, target path)

    def run(self) -> None:
        for index, url, target in self.jobs:
            if self.isInterruptionRequested():
                log.debug("screenshot fetch interrupted")
                break
            path = _ensure(url, target)
            if path:
                self.ready.emit(index, path)
        self.done.emit()


def _ensure(url: str, target: str) -> str:
    """Return a local path for this image, downloading it only if it is not already here."""
    if os.path.isfile(target) and os.path.getsize(target) >= rules.SCREENSHOT_MIN_BYTES:
        return target
    blob = steam_web.fetch_image(url)
    if blob is None:
        return ""
    if len(blob) < rules.SCREENSHOT_MIN_BYTES:
        log.info("screenshot %s is only %d bytes; ignoring", url, len(blob))
        return ""
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as handle:
            handle.write(blob)
    except OSError as exc:
        log.error("could not write %s: %s", target, exc)
        return ""
    return target


class HeroWorker(QThread):
    """Fetches SteamGridDB heroes for a game that has no Steam screenshots to cycle.

    The name lookup, the hero list and the downloads all happen here, so opening a page
    never waits on any of it.
    """

    ready = Signal(str)  # local path
    done = Signal()

    def __init__(self, name: str, key: str, cache_dir: str, limit: int, parent=None) -> None:
        super().__init__(parent)
        self.name = name
        self.key = key
        self.cache_dir = cache_dir
        self.limit = limit

    def run(self) -> None:
        from web import steamgriddb

        try:
            for path in steamgriddb.iter_hero_paths(
                self.name, self.key, self.cache_dir, self.limit
            ):
                if self.isInterruptionRequested():
                    log.debug("hero fetch interrupted")
                    break
                self.ready.emit(path)
        except Exception as exc:
            log.exception("hero fetch failed for %r: %s", self.name, exc)
        self.done.emit()


def plan(cache_dir: str, appid: str, pairs: list[tuple[str, str]], full: bool = False):
    """Build the job list for a game's screenshots, plus the paths already cached."""
    jobs, existing = [], {}
    for index, (thumb, full_url) in enumerate(pairs):
        url = full_url if full else thumb
        target = cache_path(cache_dir, appid, index, full)
        if os.path.isfile(target) and os.path.getsize(target) >= rules.SCREENSHOT_MIN_BYTES:
            existing[index] = target
        else:
            jobs.append((index, url, target))
    return jobs, existing


class NewsWorker(QThread):
    """Fetches a game's recent update posts off the GUI thread.

    Opening a page must never wait on the network, so the block simply appears once the
    posts land -- or never, which is the normal case for two thirds of this library.

    Like the others here, this must be stopped from the window's closeEvent: Qt aborts the
    process if a QThread is still running when its owner is destroyed.
    """

    ready = Signal(str, list)  # appid, list[steam_news.NewsItem]

    def __init__(self, appid: str, cache_dir: str, allow_network: bool, parent=None) -> None:
        super().__init__(parent)
        self.appid = appid
        self.cache_dir = cache_dir
        self.allow_network = allow_network

    def run(self) -> None:
        if self.isInterruptionRequested():
            return
        from web import steam_news

        items = steam_news.fetch_for(self.appid, self.cache_dir, self.allow_network)
        if self.isInterruptionRequested():
            log.debug("news fetch for %s interrupted; dropping the result", self.appid)
            return
        self.ready.emit(self.appid, items)


class CapsuleWorker(QThread):
    """The covers of the wished games without one, off the GUI thread (Phase 87).

    The Wishlist page shows what is cached at once and asks this for the rest, at most
    rules.WISHLIST_ART_PER_VISIT a visit, a second apart, each emitted as it lands. Stopped from
    the window's closeEvent, as every worker here must be.
    """

    ready = Signal(int, str)  # appid, local path

    def __init__(self, appids: list[int], cache_dir: str, parent=None) -> None:
        super().__init__(parent)
        self.appids = list(appids)[: rules.WISHLIST_ART_PER_VISIT]
        self.cache_dir = cache_dir

    def run(self) -> None:
        import time

        for index, appid in enumerate(self.appids):
            if self.isInterruptionRequested():
                log.debug("wishlist covers interrupted")
                return
            if index:
                time.sleep(rules.STEAM_WEB_RATE_LIMIT_SECONDS)
            path = steam_web.fetch_capsule(appid, self.cache_dir)
            if path:
                self.ready.emit(appid, path)
