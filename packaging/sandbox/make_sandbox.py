"""Write GameLauncher.wsb: a clean Windows to try the installer in (Phase 78).

    .venv\\Scripts\\python.exe packaging\\sandbox\\make_sandbox.py ["C:\\games\\Slow Roads"]

Windows Sandbox (a Windows 11 Pro feature) starts a throwaway Windows with nothing installed
-- no Python, no Steam, no game folders -- which is what a friend's PC looks like to the
launcher, and everything in it is gone when its window closes. A .wsb file tells it what to
bring in. This one maps two folders, both read only, so nothing in the sandbox can change them:

  dist\\                 the installer, onto the sandbox's Desktop as "Installer"
  one game folder        onto the Desktop too, then copied to C:\\Games\\<name> when the sandbox
                         starts, so the first-run question finds C:\\Games by itself and the
                         scan finds the game in an ordinary folder (a copy, not the mapping:
                         whether a mapped folder looks like a link from inside is not known
                         here, and the scan skips links)

Explorer opens on the installer once the copy is done. A .wsb must name absolute paths on this
PC, and no tracked file names the project folder (Phase 37), so the file is written by this
script from wherever the project is, and git ignores it.
"""

from __future__ import annotations

import sys
from pathlib import Path
from xml.sax.saxutils import escape

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
DIST = PROJECT / "dist"
WSB = HERE / "GameLauncher.wsb"
DEFAULT_GAME = Path(r"C:\games\Slow Roads")  # a folder game with nothing chosen for it (Phase 47's plain game)

SANDBOX_DESKTOP = r"C:\Users\WDAGUtilityAccount\Desktop"  # the sandbox's one user, always this name
SANDBOX_GAMES = r"C:\Games"


def wsb_text(dist: Path, game: Path) -> str:
    installer = rf"{SANDBOX_DESKTOP}\Installer"
    mapped_game = rf"{SANDBOX_DESKTOP}\{game.name}"
    copied_game = rf"{SANDBOX_GAMES}\{game.name}"
    # robocopy answers 1 for "files copied"; the sandbox does not care, and explorer opens after.
    command = (f'cmd /c robocopy "{mapped_game}" "{copied_game}" /E /NFL /NDL /NJH /NJS '
               f'& start "" explorer "{installer}"')
    return f"""<Configuration>
  <!-- Written by packaging/sandbox/make_sandbox.py (Phase 78); see docs/DISTRIBUTIE.md. -->
  <MappedFolders>
    <MappedFolder>
      <HostFolder>{escape(str(dist))}</HostFolder>
      <SandboxFolder>{escape(installer)}</SandboxFolder>
      <ReadOnly>true</ReadOnly>
    </MappedFolder>
    <MappedFolder>
      <HostFolder>{escape(str(game))}</HostFolder>
      <SandboxFolder>{escape(mapped_game)}</SandboxFolder>
      <ReadOnly>true</ReadOnly>
    </MappedFolder>
  </MappedFolders>
  <LogonCommand>
    <Command>{escape(command)}</Command>
  </LogonCommand>
</Configuration>
"""


def write(target: Path = WSB, dist: Path = DIST, game: Path = DEFAULT_GAME) -> Path:
    for folder, what in ((dist, "the installer's folder (build it first: packaging\\build.py)"),
                         (game, "the game folder")):
        if not folder.is_dir():
            raise SystemExit(f"{what} is not there: {folder}")
    target.write_text(wsb_text(dist, game), encoding="utf-8")
    return target


def main() -> int:
    game = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_GAME
    written = write(game=game)
    print(f"wrote {written}\n  installer: {DIST}\n  game:      {game} -> {SANDBOX_GAMES}\\{game.name} in the sandbox")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
