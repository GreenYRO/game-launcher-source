#!/usr/bin/env python3
"""What game sources exist on THIS Linux machine? Run it on Omarchy and send back the output.

This is the same first step every phase of this project took on Windows: look at the real
machine before writing a line of code that depends on it. Nothing here is installed,
changed, launched or deleted -- it only reads, and it only reads places that belong to
games and game launchers.

    python3 probe_linux.py                   # readable report
    python3 probe_linux.py --json probe.json # the same thing as data

Pure standard library, Python 3.9+. No pip install and no virtualenv needed.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

HOME = Path.home()
XDG_DATA = Path(os.environ.get("XDG_DATA_HOME", HOME / ".local" / "share"))
XDG_CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", HOME / ".config"))

report: dict = {}
INDENT = "     "
QUOTE = '"'


def head(title: str) -> None:
    print("\n" + "=" * 74)
    print(title)
    print("=" * 74)


def note(text: str) -> None:
    print(INDENT + text)


def look(label: str, path: Path, deep: int = 0) -> dict:
    """Report whether a path exists, and optionally what is directly inside it."""
    info = {"path": str(path), "exists": path.exists()}
    mark = "FOUND  " if info["exists"] else "absent "
    print(f"  {mark} {label:34} {path}")
    if info["exists"] and path.is_dir() and deep:
        try:
            names = sorted(p.name for p in path.iterdir())
        except OSError as exc:
            note(f"(cannot list: {exc})")
            return info
        info["children"] = names[:80]
        info["child_count"] = len(names)
        if names:
            note(f"{len(names)} entries: " + ", ".join(names[:deep])
                 + (" ..." if len(names) > deep else ""))
    return info


def run(cmd, timeout: int = 20):
    """Run a read-only command if it is installed. Returns (ok, output)."""
    if not shutil.which(cmd[0]):
        return False, f"{cmd[0]} is not installed"
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except Exception as exc:
        return False, str(exc)
    return out.returncode == 0, (out.stdout or out.stderr).strip()


# ------------------------------------------------------------------------------ machine
head("1. THE MACHINE")
osrelease = {}
try:
    for line in Path("/etc/os-release").read_text().splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            osrelease[key] = value.strip(QUOTE)
except OSError:
    pass
report["system"] = {
    "distro": osrelease.get("PRETTY_NAME", "unknown"),
    "kernel": platform.release(),
    "python": sys.version.split()[0],
    "session_type": os.environ.get("XDG_SESSION_TYPE", "?"),
    "desktop": os.environ.get("XDG_CURRENT_DESKTOP", "?"),
    "hyprland": bool(os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")),
}
for key, value in report["system"].items():
    note(f"{key:16} {value}")

head("2. CAN THE LAUNCHER RUN AT ALL?")
mods = {}
for module in ("PySide6", "vdf", "pygame"):
    try:
        __import__(module)
        mods[module] = "importable"
    except Exception as exc:
        mods[module] = f"missing ({type(exc).__name__})"
    note(f"{module:12} {mods[module]}")
report["modules"] = mods
note("")
note("PySide6 is the interface, vdf reads Steam manifests, pygame reads controllers.")
note("All three have Linux wheels. None of them is the problem; the providers are.")

# -------------------------------------------------------------------------------- steam
head("3. STEAM  (the one provider that should port almost unchanged)")
report["steam"] = {"roots": {}, "libraries": [], "manifests": [], "proton_prefixes": 0}
steam_roots = (
    ("Steam, native", XDG_DATA / "Steam"),
    ("Steam, old path", HOME / ".steam" / "steam"),
    ("Steam, flatpak", HOME / ".var" / "app" / "com.valvesoftware.Steam"
     / ".local" / "share" / "Steam"),
)
for label, path in steam_roots:
    info = look(label, path)
    report["steam"]["roots"][label] = info
    if not info["exists"]:
        continue
    libfile = path / "steamapps" / "libraryfolders.vdf"
    if libfile.is_file():
        text = libfile.read_text(errors="replace")
        note(f"libraryfolders.vdf: {libfile.stat().st_size} bytes")
        report["steam"]["libraryfolders_sample"] = text[:1500]
        for line in text.splitlines():
            if f"{QUOTE}path{QUOTE}" in line and line.count(QUOTE) >= 4:
                found = line.split(QUOTE)[3]
                report["steam"]["libraries"].append(found)
                note(f"  library: {found}")
    apps = path / "steamapps"
    if apps.is_dir():
        acf = sorted(apps.glob("appmanifest_*.acf"))
        note(f"{len(acf)} appmanifest_*.acf files in {apps}")
        report["steam"]["manifests"] += [f.name for f in acf]
        if acf:
            note("first one verbatim -- this is the format the provider parses:")
            for line in acf[0].read_text(errors="replace").splitlines()[:14]:
                print(INDENT + "  | " + line)
    compat = apps / "compatdata"
    if compat.is_dir():
        try:
            count = len(list(compat.iterdir()))
        except OSError:
            count = 0
        report["steam"]["proton_prefixes"] = count
        note(f"{count} Proton prefixes in compatdata (Windows games run through Proton)")

# ------------------------------------------------------------------------------- heroic
head("4. HEROIC AND LEGENDARY  (where Epic and GOG games live on Linux)")
report["heroic"] = {}
heroic_paths = (
    ("Heroic config", XDG_CONFIG / "heroic"),
    ("Heroic flatpak", HOME / ".var" / "app" / "com.heroicgameslauncher.hgl"
     / "config" / "heroic"),
    ("legendary (Epic CLI)", XDG_CONFIG / "legendary"),
)
for label, path in heroic_paths:
    info = look(label, path, deep=12)
    report["heroic"][label] = info
    if not info["exists"]:
        continue
    for name in ("gog_store/installed.json", "store_cache/gog_library.json",
                 "lib-cache/library.json", "installed.json", "config.json"):
        target = path / name
        if target.is_file():
            note(f"  {name}: {target.stat().st_size} bytes")
            try:
                data = json.loads(target.read_text(errors="replace"))
                shape = list(data)[:8] if isinstance(data, dict) else f"list of {len(data)}"
                note(f"     top level: {shape}")
                report["heroic"].setdefault("samples", {})[name] = str(shape)
            except Exception as exc:
                note(f"     (not readable as JSON: {exc})")

# ------------------------------------------------------------------- lutris and friends
head("5. LUTRIS, BOTTLES, FLATPAK")
report["others"] = {}
for label, path in (
    ("Lutris config", XDG_CONFIG / "lutris"),
    ("Lutris data", XDG_DATA / "lutris"),
    ("Lutris game db", XDG_DATA / "lutris" / "pga.db"),
    ("Bottles", XDG_DATA / "bottles"),
    ("Flatpak data", XDG_DATA / "flatpak"),
):
    report["others"][label] = look(label, path, deep=10)
ok, out = run(["flatpak", "list", "--app", "--columns=application,name"])
if ok:
    lines = [line for line in out.splitlines() if line.strip()]
    note(f"flatpak apps installed: {len(lines)}")
    for line in lines[:15]:
        note("  " + line)
    report["others"]["flatpak_apps"] = lines
else:
    note(f"flatpak: {out}")

# -------------------------------------------------------------------------- folder games
head("6. GAMES SITTING IN FOLDERS  (what the folder scanner would walk)")
report["folders"] = {}
for label in ("Games", "games", "Downloads"):
    report["folders"][label] = look(f"~/{label}", HOME / label, deep=15)
note("")
note("On Windows the scanner finds a game by its .exe and reads the title out of the")
note("file's version resource. Linux has no equivalent -- a native game is an ELF binary")
note("with no title inside it -- so naming would fall back to the folder name.")

# ----------------------------------------------------------------------- desktop entries
head("7. DESKTOP ENTRIES  (how Linux itself lists installed applications)")
entries = []
for base in (XDG_DATA / "applications", Path("/usr/share/applications"),
             XDG_DATA / "flatpak" / "exports" / "share" / "applications"):
    if base.is_dir():
        found = sorted(base.glob("*.desktop"))
        entries += found
        note(f"{len(found):4} .desktop files in {base}")
games = []
for path in entries:
    try:
        text = path.read_text(errors="replace")
    except OSError:
        continue
    for line in text.splitlines():
        if line.startswith("Categories=") and "Game" in line:
            name = next((l.split("=", 1)[1] for l in text.splitlines()
                         if l.startswith("Name=")), path.stem)
            games.append((name, path))
            break
report["desktop_games"] = [{"name": n, "file": str(p)} for n, p in games]
note("")
note(f"{len(games)} of them are categorised as games:")
for name, path in games[:20]:
    note(f"  {name}   <- {path.name}")
if len(games) > 20:
    note(f"  ... and {len(games) - 20} more")

# -------------------------------------------------------------------------- the plumbing
head("8. THE PLUMBING A PORT WOULD NEED")
report["plumbing"] = {}
report["plumbing"]["trash"] = look("XDG trash (for uninstall)", XDG_DATA / "Trash", deep=6)
note("  Windows uses the shell's Recycle Bin; Linux has the freedesktop trash spec here.")
ok, out = run(["gio", "--version"])
note(f"  gio (can move files to trash): {out.splitlines()[0] if ok else out}")

pads = sorted(Path("/dev/input").glob("js*"))
report["plumbing"]["joysticks"] = [str(p) for p in pads]
note(f"  {len(pads)} joystick nodes under /dev/input")
byid = Path("/dev/input/by-id")
if byid.is_dir():
    for entry in sorted(byid.iterdir()):
        lowered = entry.name.lower()
        if "joystick" in lowered or "gamepad" in lowered or "event-joystick" in lowered:
            note(f"    {entry.name}")

mounts = []
try:
    for line in Path("/proc/mounts").read_text().splitlines():
        parts = line.split()
        if len(parts) > 2 and parts[0].startswith("/dev/"):
            mounts.append((parts[0], parts[1], parts[2]))
except OSError:
    pass
report["plumbing"]["mounts"] = mounts
note(f"  {len(mounts)} real disks mounted "
     "(the storage page would group by these, not by C: and D:)")
for device, point, fstype in mounts[:10]:
    try:
        st = os.statvfs(point)
        free = st.f_bavail * st.f_frsize / 1e9
        total = st.f_blocks * st.f_frsize / 1e9
        note(f"    {point:22} {fstype:8} {free:7.1f} GB free of {total:.1f} GB")
    except OSError:
        note(f"    {point:22} {fstype:8} (could not measure)")

# ----------------------------------------------------------------------------- summary
head("SUMMARY")
present = []
if any(info.get("exists") for info in report["steam"]["roots"].values()):
    present.append(f"Steam ({len(report['steam']['manifests'])} installed games)")
if any(isinstance(v, dict) and v.get("exists") for v in report["heroic"].values()):
    present.append("Heroic or legendary")
if report["others"].get("Lutris data", {}).get("exists"):
    present.append("Lutris")
if report["others"].get("Bottles", {}).get("exists"):
    present.append("Bottles")
if report["others"].get("flatpak_apps"):
    present.append(f"{len(report['others']['flatpak_apps'])} flatpak apps")
if report["desktop_games"]:
    present.append(f"{len(report['desktop_games'])} desktop entries marked as games")

print("")
note("Game sources present on this machine:")
for item in present or ["(none detected)"]:
    note("  - " + item)
print("")
note("Send this whole output back, and the providers can be written against what is")
note("really here rather than guessed at. That is the rule the Windows version was")
note("built on, and it is the reason it finds all 21 of your games instead of some.")

if "--json" in sys.argv:
    index = sys.argv.index("--json")
    target = Path(sys.argv[index + 1] if len(sys.argv) > index + 1 else "probe.json")
    target.write_text(json.dumps(report, indent=2, default=str))
    print("")
    note(f"Also written as data to {target}")
