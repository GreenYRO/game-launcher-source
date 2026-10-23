"""Uninstalling a game, tiered by who actually owns the install.

**This is the only module in the project that destroys anything**, and it does so in
exactly one place: `send_to_recycle_bin`. Everything else here decides whether that is
even allowed to be offered.

The tier is not a presentation detail -- it is the honest answer to "what can this
launcher actually do about this game", and the button says only that:

  * **folders** -- ours to remove. If the game shipped an uninstaller at the root of its
    folder, that runs; otherwise the folder goes to the **Recycle Bin** through the Windows
    shell, with the shell's own progress dialog. Never `rmtree`, never a permanent delete.
  * **gog** -- GOG records a real `uninstallCommand` per game in the registry. Read and
    verified to exist before it is offered; if it is missing, the button says so.
  * **steam** -- `steam://uninstall/<appid>`, which opens Steam's own confirmation. This
    was verified against this machine rather than taken from documentation: every installed
    Steam game's UninstallString in the Windows uninstall registry is literally that URI.
  * **epic, ubisoft, xbox** -- no verified programmatic uninstall exists. The button says
    exactly that and opens the owner instead. No protocol URI here was invented; all three
    schemes were read out of HKCR first.

Four safety rules are enforced here rather than in the UI, so no future caller can skip
them, and each has a test:

  1. The deleting tier is offered for folder-source entries and nothing else.
  2. The folder must resolve **under a configured scan root**, or the operation refuses.
  3. The folder must not *be* a scan root -- a loose exe dropped in `C:\\games` produces an
     entry whose install_dir is the root itself, and deleting that would take the lot.
  4. A game with a live session refuses, because its files are open and half of it would
     survive anyway.
  5. (Phase 82) A folder is never removed if it is a whole drive, one of Windows' own folders
     (rules.SYSTEM_FOLDERS, by where it sits), or sits directly on a drive's root. With C:\\
     chosen as a game folder, rules 2 and 3 alone put "Remove from disk..." on Program Files.
     A drive is refused as a game folder now, so no such game should exist; the rule holds
     anyway -- for a config.json edited by hand -- and `send_to_recycle_bin` asks it again
     itself, being the one place anything is destroyed.
"""

from __future__ import annotations

import fnmatch
import logging
import os
import subprocess

from shared import drives
from shared import registry
from shared import rules

log = logging.getLogger(__name__)

# Populated lazily so a machine without pywin32's shell module still imports the launcher.
try:
    from win32com.shell import shell, shellcon

    SHELL_AVAILABLE = True
except Exception as exc:  # pragma: no cover - pywin32 is a hard dependency in practice
    logging.getLogger(__name__).warning("shell file operations unavailable: %s", exc)
    shell = shellcon = None
    SHELL_AVAILABLE = False

FOLDER_SOURCE = "folders"


class Plan:
    """What can be done about one game, and what the button should therefore say."""

    def __init__(self, tier, button, explanation, target="", owner="", blocked=""):
        self.tier = tier
        self.button = button
        self.explanation = explanation
        self.target = target
        self.owner = owner
        self.blocked = blocked

    @property
    def deletes(self) -> bool:
        """True only for the one tier that removes files."""
        return self.tier == rules.TIER_DELETE and not self.blocked

    @property
    def available(self) -> bool:
        return not self.blocked

    def __repr__(self) -> str:
        return f"<Plan {self.tier} {self.button!r}{' BLOCKED' if self.blocked else ''}>"


# -- the safety rules ----------------------------------------------------------------------


def scan_roots(config: dict) -> list[str]:
    return [
        os.path.normcase(os.path.abspath(root))
        for root in config.get("roots", rules.DEFAULT_ROOTS)
        if root
    ]


def under_scan_root(path: str, config: dict) -> bool:
    """True when `path` sits *inside* one of the configured roots.

    Inside, not equal to: an entry whose install_dir is the root itself must never be
    deletable, or one loose exe in C:\\games would put "remove the whole games folder"
    behind a button.
    """
    if not path:
        return False
    target = os.path.normcase(os.path.abspath(path))
    return any(
        target.startswith(root + os.sep) and target != root for root in scan_roots(config)
    )


def protected(folder: str) -> str:
    """The fifth rule: why this folder is never removed, whoever asks -- or "" if it may be."""
    if not folder:
        return ""
    folder = os.path.abspath(folder)
    if drives.is_drive_root(folder):
        return f"It is a whole drive, so it will not be touched:\n{folder}"
    if drives.is_system_folder(folder):
        return f"It is one of Windows' own folders, so it will not be touched:\n{folder}"
    if drives.on_drive_root(folder):
        return (f"It sits directly on {drives.drive_name(os.path.splitdrive(folder)[0])}, where a "
                f"game folder never is, so it will not be touched:\n{folder}")
    return ""


def refuse_reason(view, config: dict, tracker=None) -> str:
    """Why the deleting tier must not run for this game, or "" if it may."""
    if view.entry.source != FOLDER_SOURCE:
        return (
            f"{view.display_name} was installed by {view.entry.source}, so this launcher "
            "does not own its files."
        )
    if tracker is not None and tracker.is_running(view.key):
        return (
            f"{view.display_name} is running. Stop it first -- its files are open, and "
            "removing it now would leave part of it behind."
        )
    folder = view.entry.install_dir
    if not folder or not os.path.isdir(folder):
        return f"Its folder is already gone:\n{folder or '(no folder recorded)'}"
    kept = protected(folder)
    if kept:
        return kept
    if not under_scan_root(folder, config):
        return (
            f"Its folder is not inside a folder you told the launcher to scan, so it will "
            f"not be touched:\n{folder}"
        )
    return ""


# -- working out the tier -------------------------------------------------------------------


def uninstaller_at_root(folder: str) -> str | None:
    """A recognised uninstaller sitting at the top of a game folder, if there is one."""
    if not folder or not os.path.isdir(folder):
        return None
    try:
        names = os.listdir(folder)
    except OSError as exc:
        log.warning("could not list %s: %s", folder, exc)
        return None
    for name in sorted(names):
        lowered = name.casefold()
        if not lowered.endswith(".exe"):
            continue
        if any(fnmatch.fnmatch(lowered, glob) for glob in rules.UNINSTALLER_ROOT_GLOBS):
            return os.path.join(folder, name)
    return None


def gog_uninstall_command(source_id: str) -> str | None:
    """GOG's own recorded uninstaller for one game, if it is recorded and really there."""
    if not source_id:
        return None
    for hive, subkey in rules.GOG_REGISTRY_LOCATIONS:
        command = registry.read_value(
            hive, f"{subkey}\\{source_id}", rules.GOG_UNINSTALL_VALUE
        )
        if not command:
            continue
        path = str(command).strip('"')
        if os.path.isfile(path):
            log.info("GOG records an uninstaller for %s: %s", source_id, path)
            return path
        log.warning("GOG names an uninstaller for %s that is not there: %s", source_id, path)
    return None


def plan(view, config: dict, tracker=None) -> Plan:
    """The one thing this launcher can honestly offer for this game."""
    source = view.entry.source

    if source == FOLDER_SOURCE:
        blocked = refuse_reason(view, config, tracker)
        if blocked:
            return Plan(rules.TIER_BLOCKED, "Uninstall", blocked, blocked=blocked)
        found = uninstaller_at_root(view.entry.install_dir)
        if found:
            return Plan(
                rules.TIER_UNINSTALLER,
                "Run its uninstaller",
                f"{view.display_name} came with its own uninstaller, which knows what it "
                "installed. It runs next and takes over from here.",
                target=found,
            )
        return Plan(
            rules.TIER_DELETE,
            "Remove from disk",
            f"The whole folder goes to the Recycle Bin, so you can put it back if this "
            "was a mistake.",
            target=view.entry.install_dir,
        )

    if source == "gog":
        found = gog_uninstall_command(view.entry.source_id)
        if found:
            return Plan(
                rules.TIER_UNINSTALLER,
                "Run its uninstaller",
                f"GOG recorded an uninstaller for {view.display_name}. It runs next and "
                "takes over from here.",
                target=found,
                owner="GOG",
            )
        return Plan(
            rules.TIER_OWNER,
            "Open GOG Galaxy",
            "GOG has not recorded an uninstaller for this game on this machine, so it has "
            "to be removed from GOG Galaxy.",
            target="",
            owner="GOG Galaxy",
        )

    if source == "steam":
        appid = view.entry.source_id
        return Plan(
            rules.TIER_STORE,
            "Uninstall through Steam",
            f"Steam owns this install. Its own uninstall window opens next and asks you "
            "there -- nothing is removed until you confirm it in Steam.",
            target=rules.STEAM_UNINSTALL_URI.format(appid=appid),
            owner="Steam",
        )

    owners = {
        "epic": ("Epic Games Launcher", rules.EPIC_LIBRARY_URI),
        "ubisoft": ("Ubisoft Connect", rules.UBISOFT_CLIENT_URI),
        "xbox": ("Windows installed apps", rules.XBOX_APPS_URI),
    }
    if source in owners:
        name, uri = owners[source]
        return Plan(
            rules.TIER_OWNER,
            f"Open {name}",
            f"There is no reliable way for this launcher to uninstall a {source} game, so "
            f"it will not pretend otherwise. {name} opens next and you can remove "
            f"{view.display_name} there.",
            target=uri,
            owner=name,
        )

    return Plan(
        rules.TIER_BLOCKED,
        "Uninstall",
        f"This launcher does not know how {view.display_name} was installed.",
        blocked=f"unknown source {source!r}",
    )


# -- doing it ---------------------------------------------------------------------------------


def send_to_recycle_bin(path: str, hwnd: int = 0, interactive: bool = True,
                        already_asked: bool = False):
    """Move a folder to the Recycle Bin through the Windows shell. Returns (ok, message).

    `FOF_ALLOWUNDO` is what makes this recoverable, and it is never omitted. The shell's
    own progress dialog and its "this is too big for the Recycle Bin" prompt are wanted
    here, so no confirmation flags are set -- if Windows decides the folder is too large to
    recycle, that is its dialog and the user's decision, not ours to answer for them.

    `already_asked` adds FOF_NOCONFIRMATION alone, for a caller that has just asked the
    same question itself -- restoring saves (Phase 30). Progress and error dialogs stay.

    `interactive=False` adds the silencing flags and exists **only so tests never block on
    a dialog nobody is there to click**. The application always calls this with True.
    """
    if not SHELL_AVAILABLE:
        return False, "The Windows shell file operations are not available."
    if not path or not os.path.isdir(path):
        return False, f"That folder is not there any more:\n{path}"
    kept = protected(path)
    if kept:  # the fifth rule, asked again where the deleting happens
        log.error("refused to send %s to the Recycle Bin: %s", path, kept.splitlines()[0])
        return False, kept

    flags = shellcon.FOF_ALLOWUNDO
    if already_asked:
        flags |= shellcon.FOF_NOCONFIRMATION
    if not interactive:
        flags |= (
            shellcon.FOF_NOCONFIRMATION | shellcon.FOF_SILENT | shellcon.FOF_NOERRORUI
        )

    log.info("sending %s to the Recycle Bin (flags=0x%x)", path, flags)
    try:
        result, aborted = shell.SHFileOperation(
            (hwnd, shellcon.FO_DELETE, path, None, flags, None, None)
        )
    except Exception as exc:  # pywintypes.error and friends
        log.error("the shell refused to remove %s: %s", path, exc)
        return False, f"Windows would not remove it:\n{exc}"

    if aborted:
        log.info("the user cancelled the removal of %s", path)
        return False, "Cancelled - nothing was removed."
    if result != 0:
        log.error("shell delete of %s returned %s", path, result)
        return False, f"Windows reported error {result} and did not remove it."
    if os.path.isdir(path):
        log.error("shell delete of %s reported success but the folder is still there", path)
        return False, "Windows reported success but the folder is still there."
    return True, "Moved to the Recycle Bin."


def run_uninstaller(command: str):
    """Start a game's own uninstaller and let it take over. Returns (ok, message)."""
    if not command or not os.path.isfile(command):
        return False, f"That uninstaller is not there any more:\n{command}"
    log.info("starting the uninstaller %s", command)
    try:
        subprocess.Popen([command], cwd=os.path.dirname(command), close_fds=True)
    except OSError as exc:
        log.error("could not start %s: %s", command, exc)
        return False, f"Windows would not start it:\n{exc}"
    return True, "Its uninstaller is running. Follow the prompts it shows."


def open_uri(uri: str):
    """Hand a URI to the shell -- a store's uninstall flow, or its window. (ok, message)."""
    if not uri:
        return False, "There is nothing to open."
    log.info("opening %s", uri)
    try:
        os.startfile(uri)
    except OSError as exc:
        log.error("the shell refused %s: %s", uri, exc)
        return False, f"Windows could not open it:\n{uri}\n\n{exc}"
    return True, ""


def perform(plan_: Plan, hwnd: int = 0, interactive: bool = True):
    """Carry out a plan. The single entry point the UI uses. Returns (ok, message)."""
    if plan_.blocked:
        return False, plan_.blocked
    if plan_.tier == rules.TIER_DELETE:
        return send_to_recycle_bin(plan_.target, hwnd, interactive)
    if plan_.tier == rules.TIER_UNINSTALLER:
        return run_uninstaller(plan_.target)
    if plan_.tier in (rules.TIER_STORE, rules.TIER_OWNER):
        if not plan_.target:
            return False, plan_.explanation
        ok, message = open_uri(plan_.target)
        if ok:
            message = (
                f"{plan_.owner} is opening. Finish removing it there."
                if plan_.owner
                else "Opened."
            )
        return ok, message
    return False, f"Nothing to do for tier {plan_.tier!r}."
