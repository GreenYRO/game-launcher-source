# Moving this launcher to Linux (Omarchy)

Written 30 August 2026, on the Windows machine, before any Linux code exists.

## The short answer

**About three quarters of it moves across untouched. The quarter that does not is exactly
the part that finds your games.**

Measured, not guessed — 60 modules, 14,968 lines:

| | modules | lines | share |
|---|---|---|---|
| Ports as-is | 47 | 11,369 | **76%** |
| Needs small changes | 5 | 1,373 | 9% |
| Needs rewriting | 8 | 2,226 | **15%** |

Everything you actually look at and click — the cover grid, the detail page, the shelves,
the stats page, the storage page, TV mode, the settings dialog, the artwork handling, the
backups, export and import — is PySide6 and plain Python. It runs on Hyprland as it stands.
So does your data: `overrides.json` is just JSON, and your playtime, sessions, favourites
and chosen artwork carry over intact.

## What actually has to be rebuilt, and why

| Part | Why it cannot come across | What replaces it on Linux |
|---|---|---|
| `registry.py` | Linux has no registry | Nothing — the providers below read files instead |
| `providers/steam.py` | Only the *path* is Windows-specific | **Easiest win.** Same `.acf` manifests, same `vdf` library, at `~/.local/share/Steam` |
| `providers/epic.py` | Epic has no Linux client | Read **Heroic** or **legendary** config instead |
| `providers/gog.py` | Reads the Windows registry | Read **Heroic** or **Lutris** instead |
| `providers/xbox.py` | Xbox/Game Pass does not exist on Linux | Delete it |
| `providers/ubisoft.py` | Reads the Windows registry | Ubisoft games run under Lutris/Proton |
| `peinfo.py` | Reads titles out of `.exe` version resources | No equivalent — fall back to folder names |
| `launch.py` | Job Objects track the whole process tree | Process groups (`setsid` + `killpg`). Arguably simpler |
| `removal.py` | Recycle Bin via the Windows shell | The freedesktop trash spec, or `gio trash` |
| `taskbar.py` | AppUserModelID and `.lnk` shortcuts | `.desktop` files — much simpler |
| `storage.py` | Groups by drive letter | Group by mount point (`/`, `/home`, …) |
| `icons.py` | Pulls icons out of `.exe` files | Icon themes and `.desktop` icons |

New providers worth having on Omarchy that have no Windows equivalent: **Heroic**
(Epic + GOG + Amazon in one place), **Lutris**, **Bottles**, **Flatpak**, and games
launched from `.desktop` entries.

## Why it was not just built anyway

This project has one rule above the others, and it is in CLAUDE.md:

> **Never invent a registry path, protocol URI, or file format.** A provider pointed at a
> wrong path returns an empty list, which is indistinguishable from "nothing installed" —
> the worst failure mode in this project.

Every provider in the Windows version was written *after* reading the real thing off this
machine: the Steam manifests were opened, the GOG registry values were dumped, the Xbox
AUMID was assembled from a real `MicrosoftGame.config`, the Ubisoft keys were inspected and
found empty — which is why there is deliberately no EA provider at all.

A Linux version written from memory would guess where Heroic keeps its library, guess
Lutris's database shape, guess the Steam path. Some guesses would be right. The wrong ones
would silently show an empty grid and there would be no way to tell which was which. That
is the exact failure this project has refused to ship for twenty-five phases, and it should
not start now.

## What to do instead — one command

`probe_linux.py` ships beside this file. Copy it to the Omarchy machine and run:

```bash
python3 probe_linux.py --json probe.json
```

It installs nothing, changes nothing, launches nothing and deletes nothing. It reads the
places games live and prints what is really there: which Steam root exists and how many
manifests are in it, whether Heroic is installed and what shape its library file is, what
Lutris and Flatpak know about, which controllers are attached, how the disks are mounted,
and whether PySide6, vdf and pygame import.

Send the output back. Then the providers get written against facts, the same way every
Windows provider was — and the phase gates carry on as before.

## The rough shape of the work, if it goes ahead

Gated the same way, each one stopping for you to check it:

- **Phase A — the platform seam.** Move every Windows call behind one interface, with a
  Windows implementation and a Linux one. Nothing changes on Windows; that is the point,
  because it can be proven here before you leave.
- **Phase B — Steam on Linux.** The easiest provider and probably most of your library.
- **Phase C — Heroic, Lutris, Flatpak.** Written against the probe output.
- **Phase D — launching and playtime.** Process groups instead of Job Objects.
- **Phase E — trash, `.desktop` files, mount points.** Uninstall and the storage page.
- **Phase F — package it.** A `.desktop` entry and either a PKGBUILD for the AUR or an
  AppImage. Omarchy is Arch, so a PKGBUILD is the natural fit.

Phase A is worth doing on Windows before the machine is gone, because it is the only part
that can be verified on both sides.

## Carrying your library across

Independent of any of that, your data already travels. The launcher's own
**Settings → Export library** writes one zip with `config.json`, `overrides.json` and only
the artwork your overrides point at — about 11 MB. Import it on the other side. Phase 15
built it for exactly this, and the identity rule matters here: Steam, Epic and Xbox games
reattach anywhere because they are keyed by store id, while folder games are keyed by their
install path and only reattach if the game sits at the same path. On a new Linux machine
the paths will differ, so those records are kept in reserve rather than lost.
