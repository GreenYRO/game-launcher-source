"""Finding saves and backing them up, off the GUI thread.

One walk of the save locations serves every game in the job -- it takes about two seconds
for this machine's ~127,000 files -- and zipping a large save folder takes a few more.
Neither belongs on the thread that draws the window. The worker never writes
overrides.json: it reports what it found, and the window, which owns that file, records it.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

from PySide6.QtCore import QThread, Signal

from logic import save_backup
from logic import saves

log = logging.getLogger(__name__)


@dataclass
class Job:
    key: str
    name: str
    appid: str
    install_dir: str
    windows: list[tuple[float, float]]
    known: list[str] = field(default_factory=list)  # folders found on earlier runs
    ignored: tuple[str, ...] = ()
    back_up: bool = True
    reason: str = "after playing"


@dataclass
class Outcome:
    key: str
    folders: list[str]
    newly_found: list[str]
    backup: save_backup.Result | None


class SaveWorker(QThread):
    finishedJobs = Signal(object)  # list[Outcome]

    def __init__(self, jobs: list[Job], other_names: tuple[str, ...], parent=None) -> None:
        super().__init__(parent)
        self.jobs = jobs
        self.other_names = other_names

    def run(self) -> None:
        outcomes: list[Outcome] = []
        try:
            outcomes = run_jobs(self.jobs, self.other_names, stop=self.isInterruptionRequested)
        except Exception:  # logged with its traceback; the window carries on without it
            log.exception("looking for saves failed")
        self.finishedJobs.emit(outcomes)


def run_jobs(jobs: list[Job], other_names: tuple[str, ...], stop=lambda: False) -> list[Outcome]:
    """The work itself, callable without a thread -- the uninstall flow and the tests do."""
    if not jobs:
        return []
    bases = saves.known_folders()
    game_bases = [("game", job.install_dir) for job in jobs
                  if job.install_dir and os.path.isdir(job.install_dir)]
    starts = [w[0] for job in jobs for w in job.windows]
    index = saves.build_index(bases + game_bases, since=min(starts) if starts else 0.0)
    outcomes = []
    for job in jobs:
        if stop():
            break
        found = saves.find(
            index, bases + game_bases, name=job.name, appid=job.appid,
            install_dir=job.install_dir, windows=job.windows, ignored=job.ignored,
            other_names=tuple(n for n in other_names if n != job.name),
        )
        found_paths = [f.path for f in found]
        # Folders found before are kept while they exist: a game does not write every
        # save folder in every session, and one quiet session must not forget one.
        # ...unless it was never a save folder at all: a crash report or telemetry folder
        # recorded before Phase 36 learned to tell, which is dropped here for good.
        known = [p for p in saves.only_save_folders(job.known)
                 if os.path.isdir(p) and p not in job.ignored]
        folders = known + [p for p in found_paths
                           if os.path.normcase(p) not in {os.path.normcase(k) for k in known}]
        newly = [p for p in folders if p not in job.known]
        for item in found:
            if item.path in newly:
                log.info("saves of %s are in %s (%s)", job.name, item.path, item.reason)
        result = None
        if job.back_up and folders:
            result = save_backup.back_up(job.key, job.name, folders, job.reason)
        outcomes.append(Outcome(job.key, folders, newly, result))
    return outcomes
