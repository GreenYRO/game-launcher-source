"""The public repository, built from one commit of this one.

    .venv\\Scripts\\python.exe packaging\\export_public.py            builds ..\\game-launcher-source
    .venv\\Scripts\\python.exe packaging\\export_public.py --check    checks only; writes nothing
    .venv\\Scripts\\python.exe packaging\\export_public.py --verify   reads the published copy back

The development repository stays private: its history holds the author's own settings and
library (config.json and overrides.json were tracked until Phase 69). What is public is a
snapshot of one commit, made like this, in order:

1. HEAD of this repository, committed work only. Uncommitted changes stop the export
   (``--allow-dirty`` exports HEAD regardless, and says what was left behind).
2. ``git archive HEAD``: the tree as committed, minus every path marked ``export-ignore`` in
   .gitattributes (Claude Code's working files, the explanations written for the author, the
   publishers' artwork the mockups were made with).
3. Every file of the snapshot is searched for what must never leave: the SteamGridDB key in
   data/config.json, every key an old committed config.json ever held, every address this
   repository has committed under, and any Steam account id (Steam's base constant,
   76561197960265728, is part of a formula, not an account, and is allowed). One hit stops the
   export. So does a ``data`` folder, an excluded path, or a missing README.md or LICENSE.
4. The snapshot replaces the contents of the sibling folder ../game-launcher-source, a git
   repository of its own on ``main`` (a clone of the published one when it exists, else a new
   one): one commit per export, "Source as of <version> (<commit>)", authored under the GitHub
   no-reply address ``gh api user`` gives, never the address this repository commits under. A
   snapshot identical to the last one makes no commit.
5. It prints the command that publishes, and never runs it: publishing is the user's word.

``--verify`` clones the published repository into a temporary folder, runs the same search
on it, and compares its files with the local export, the way check_installer.py reads the
built installer back.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET_NAME = "game-launcher-source"
PUBLIC_REPO = "GreenYRO/game-launcher-source"
PUBLIC_URL = f"https://github.com/{PUBLIC_REPO}.git"
DESCRIPTION = ("A Windows game launcher in Python and PySide6, and the bachelor's thesis built on it "
               "(Transilvania University of Brasov, 2026-2027)")

STEAM_BASE_ID = b"76561197960265728"
STEAM_ID = re.compile(rb"7656119\d{10}")
CONFIG_PATHS = ("config.json", "data/config.json")
NEVER_PRESENT = ("data",)
MUST_BE_PRESENT = ("README.md", "LICENSE", "launcher.py", "docs/ISTORIC.md", ".gitattributes")


def run(args: list[str], cwd: Path, check: bool = True, text: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(args, cwd=str(cwd), capture_output=True, text=text)
    if check and result.returncode:
        err = result.stderr if text else result.stderr.decode("utf-8", errors="replace")
        raise SystemExit(f"{' '.join(args)} failed in {cwd}:\n{err.strip()}")
    return result


def git(*args: str, cwd: Path = ROOT, check: bool = True) -> str:
    return run(["git", *args], cwd, check).stdout


# --- what is exported -------------------------------------------------------------------------

def head() -> tuple[str, str, str]:
    """The commit being exported: its full and short hash, and APP_VERSION as committed."""
    sha = git("rev-parse", "HEAD").strip()
    short = git("rev-parse", "--short", "HEAD").strip()
    version_py = git("show", "HEAD:shared/version.py")
    found = re.search(r'^APP_VERSION\s*=\s*"([^"]+)"', version_py, re.M)
    if not found:
        raise SystemExit("shared/version.py at HEAD holds no APP_VERSION")
    return sha, short, found.group(1)


def dirty() -> list[str]:
    """Tracked files changed since HEAD, and files git does not know: none of them is exported."""
    return [line.rstrip() for line in git("status", "--porcelain").splitlines() if line.strip()]


def export_ignored() -> list[str]:
    """The paths .gitattributes marks export-ignore, as committed at HEAD: what the archive leaves out."""
    paths = []
    for line in git("show", "HEAD:.gitattributes").splitlines():
        words = line.split("#", 1)[0].split()
        if len(words) >= 2 and "export-ignore" in words[1:]:
            paths.append(words[0].strip("/"))
    return paths


def snapshot(into: Path) -> None:
    """`git archive HEAD`, unpacked into `into`."""
    tar_bytes = run(["git", "archive", "--format=tar", "HEAD"], ROOT, text=False).stdout
    with tarfile.open(fileobj=io.BytesIO(tar_bytes)) as tar:
        if hasattr(tarfile, "data_filter"):
            tar.extractall(into, filter="data")
        else:  # a Python before the filter existed
            tar.extractall(into)


# --- what must never leave --------------------------------------------------------------------

def forbidden() -> dict[bytes, str]:
    """Byte strings no exported file may hold, each with what it is. The values are never printed."""
    strings: dict[bytes, str] = {}
    config = ROOT / "data" / "config.json"
    if config.exists():
        key = json.loads(config.read_text(encoding="utf-8")).get("steamgriddb_key") or ""
        if key:
            strings[key.encode("utf-8")] = "the SteamGridDB key in data/config.json"
    for path in CONFIG_PATHS:
        for sha in git("log", "--all", "--format=%H", "--", path).split():
            shown = run(["git", "show", f"{sha}:{path}"], ROOT, check=False)
            if shown.returncode:
                continue
            try:
                old = json.loads(shown.stdout).get("steamgriddb_key") or ""
            except ValueError:
                continue
            if old:
                strings.setdefault(old.encode("utf-8"), f"a SteamGridDB key an old committed {path} held")
    for address in set(git("log", "--all", "--format=%ae%n%ce").split()):
        if address and not address.endswith("@users.noreply.github.com"):
            strings[address.encode("utf-8")] = "an e-mail address this repository has committed under"
    return strings


def files_of(tree: Path) -> list[Path]:
    return sorted(p for p in tree.rglob("*") if p.is_file() and ".git" not in p.relative_to(tree).parts)


def scan(tree: Path, strings: dict[bytes, str], excluded: list[str]) -> list[str]:
    """Everything wrong with a tree about to be published; an empty list is the pass."""
    problems = []
    for path in files_of(tree):
        rel = path.relative_to(tree).as_posix()
        data = path.read_bytes()
        for value, what in strings.items():
            if value in data or value.decode("utf-8", errors="replace") in rel:
                problems.append(f"{rel}: holds {what}")
        for found in STEAM_ID.finditer(data):
            if found.group(0) != STEAM_BASE_ID:
                problems.append(f"{rel}: holds a Steam account id")
                break
    for rel in NEVER_PRESENT + tuple(excluded):
        if (tree / rel).exists():
            problems.append(f"{rel}: must not be in the snapshot")
    for rel in MUST_BE_PRESENT:
        if not (tree / rel).exists():
            problems.append(f"{rel}: missing from the snapshot")
    return problems


def summary(tree: Path) -> tuple[int, int]:
    files = files_of(tree)
    return len(files), sum(p.stat().st_size for p in files)


# --- the public repository --------------------------------------------------------------------

def identity(author: str | None) -> tuple[str, str]:
    """The name and no-reply address the public repository commits under."""
    if author:
        found = re.fullmatch(r"\s*(.+?)\s*<([^<>]+)>\s*", author)
        if not found:
            raise SystemExit("--author wants the form \"Name <address>\"")
        return found.group(1), found.group(2)
    probe = run(["gh", "api", "user"], ROOT, check=False)
    if probe.returncode:
        raise SystemExit("gh api user failed (is GitHub CLI installed and signed in?):\n"
                         f"{probe.stderr.strip()}\n"
                         "Pass --author \"Name <id+login@users.noreply.github.com>\" instead.")
    user = json.loads(probe.stdout)
    return user.get("name") or user["login"], f"{user['id']}+{user['login']}@users.noreply.github.com"


def writable(path: Path) -> None:
    """Windows keeps files from a copy read-only; make a tree deletable (folders keep their x bit)."""
    for p in [path, *path.rglob("*")]:
        try:
            os.chmod(p, stat.S_IRWXU if p.is_dir() and not p.is_symlink() else stat.S_IREAD | stat.S_IWRITE)
        except OSError:
            pass


def emptied(target: Path) -> None:
    """The target's working tree removed, its .git kept."""
    for child in target.iterdir():
        if child.name == ".git":
            continue
        if child.is_dir() and not child.is_symlink():
            writable(child)
            shutil.rmtree(child)
        else:
            os.chmod(child, stat.S_IREAD | stat.S_IWRITE)
            child.unlink()


def prepare(target: Path, name: str, address: str) -> None:
    """An empty working tree in the target repository: the one already there, else a clone of the
    published repository (so the export is a commit on top of its history), else a new one."""
    if target.exists():
        if not (target / ".git").is_dir():
            raise SystemExit(f"{target} exists and is not a git repository: refusing to touch it")
        remotes = git("remote", "-v", cwd=target)
        if remotes.strip() and PUBLIC_REPO not in remotes:
            raise SystemExit(f"{target} is some other repository (its remote is not {PUBLIC_REPO}): refusing")
    elif run(["git", "clone", "-q", PUBLIC_URL, str(target)], ROOT, check=False).returncode == 0:
        print(f"cloned {PUBLIC_URL}")
    else:
        target.mkdir(parents=True)
        git("init", "-q", "-b", "main", cwd=target)
    emptied(target)
    git("config", "user.name", name, cwd=target)
    git("config", "user.email", address, cwd=target)


def commit(target: Path, version: str, short: str) -> str | None:
    git("add", "-A", cwd=target)
    if run(["git", "diff", "--cached", "--quiet"], target, check=False).returncode == 0:
        return None
    git("commit", "-q", "-m", f"Source as of {version} ({short})", cwd=target)
    return git("log", "-1", "--format=%h %s", cwd=target).strip()


# --- the three commands -----------------------------------------------------------------------

def report(tree: Path, excluded: list[str], strings: dict[bytes, str], problems: list[str]) -> None:
    count, size = summary(tree)
    print(f"{count} files, {size / 1048576:.1f} MB")
    print("left out by .gitattributes: " + ", ".join(excluded))
    kinds = sorted(set(strings.values()))
    print(f"searched every file for {len(strings)} strings ({'; '.join(kinds)}) and for Steam account ids")
    if problems:
        print("REFUSED:")
        for problem in problems:
            print("  " + problem)
        raise SystemExit(1)
    print("found none of them: the snapshot is clean")


def export(args: argparse.Namespace) -> None:
    changed = dirty()
    if changed and not args.allow_dirty:
        print("Uncommitted changes: the export is of HEAD, and these would not be in it. Commit first,")
        print("or pass --allow-dirty to export HEAD anyway.")
        for line in changed:
            print("  " + line)
        raise SystemExit(1)
    sha, short, version = head()
    print(f"exporting {short} (version {version})")
    if changed:
        print("left behind, uncommitted:")
        for line in changed:
            print("  " + line)
    excluded = export_ignored()
    strings = forbidden()
    with tempfile.TemporaryDirectory(prefix="export-public-") as temp:
        tree = Path(temp) / "tree"
        snapshot(tree)
        report(tree, excluded, strings, scan(tree, strings, excluded))
        if args.check:
            print("--check: nothing written")
            return
        target = Path(args.target).resolve() if args.target else ROOT.parent / TARGET_NAME
        name, address = identity(args.author)
        prepare(target, name, address)
        shutil.copytree(tree, target, dirs_exist_ok=True)
    made = commit(target, version, short)
    print(f"the public repository: {target}")
    print(f"commits as: {name} <{address}>")
    print("new commit: " + made if made else "nothing changed since the last export: no new commit")
    if git("remote", cwd=target).strip():
        print(f'to publish:  git -C "{target}" push')
    else:
        print("to publish (makes the public repository on GitHub and pushes main to it):")
        print(f'  gh repo create {PUBLIC_REPO} --public --source "{target}" --remote origin --push '
              f'--description "{DESCRIPTION}"')


def verify(args: argparse.Namespace) -> None:
    target = Path(args.target).resolve() if args.target else ROOT.parent / TARGET_NAME
    url = args.url or PUBLIC_URL
    excluded = export_ignored()
    strings = forbidden()
    with tempfile.TemporaryDirectory(prefix="verify-public-") as temp:
        clone = Path(temp) / "clone"
        print(f"cloning {url}")
        run(["git", "clone", "-q", "--depth", "1", url, str(clone)], Path(temp))
        print("published: " + git("log", "-1", "--format=%h %s (%an <%ae>)", cwd=clone).strip())
        report(clone, excluded, strings, scan(clone, strings, excluded))
        if target.exists():
            local = {p.relative_to(target).as_posix() for p in files_of(target)}
            remote = {p.relative_to(clone).as_posix() for p in files_of(clone)}
            if local == remote:
                print(f"the same {len(local)} files as {target}")
            else:
                print("DIFFERENT from the local export:")
                for rel in sorted(local - remote):
                    print("  only here:   " + rel)
                for rel in sorted(remote - local):
                    print("  only there:  " + rel)
                raise SystemExit(1)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="the public repository, from one commit of this one")
    parser.add_argument("--check", action="store_true", help="build and scan the snapshot; write nothing")
    parser.add_argument("--allow-dirty", action="store_true", help="export HEAD even with uncommitted changes")
    parser.add_argument("--target", help=f"the public repository's folder (default: ../{TARGET_NAME})")
    parser.add_argument("--author", help="\"Name <address>\" to commit as, instead of asking gh")
    parser.add_argument("--verify", action="store_true", help="clone the published repository and check it")
    parser.add_argument("--url", help=f"the repository --verify clones (default: {PUBLIC_URL})")
    args = parser.parse_args(argv)
    try:
        if args.verify:
            verify(args)
        else:
            export(args)
    except KeyboardInterrupt:
        raise SystemExit(130)


if __name__ == "__main__":
    main()
