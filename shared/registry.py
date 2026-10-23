"""Thin, non-raising wrappers over winreg.

Every launcher provider reads the registry, and every one of them must treat "key absent"
as an ordinary outcome rather than an error. The distinction that matters is logged: a
missing key means the launcher is not installed, an OSError means it is installed and we
could not read it, and those two look identical in the catalog.
"""

from __future__ import annotations

import logging
import winreg

log = logging.getLogger(__name__)

HIVES = {
    "HKCU": winreg.HKEY_CURRENT_USER,
    "HKLM": winreg.HKEY_LOCAL_MACHINE,
    "HKCR": winreg.HKEY_CLASSES_ROOT,
}


def read_value(hive: str, subkey: str, name: str) -> str | None:
    """A single string value, or None if the key or value is not there."""
    try:
        with winreg.OpenKey(HIVES[hive], subkey) as key:
            value, _ = winreg.QueryValueEx(key, name)
    except FileNotFoundError:
        log.debug("absent: %s\\%s\\%s", hive, subkey, name)
        return None
    except OSError as exc:
        log.warning("could not read %s\\%s\\%s: %s", hive, subkey, name, exc)
        return None
    if not isinstance(value, str):
        log.warning("%s\\%s\\%s is %s, not a string", hive, subkey, name, type(value).__name__)
        return None
    return value


def read_all_values(hive: str, subkey: str) -> dict[str, object]:
    """Every value under one key, as a plain dict. Empty if the key has none."""
    values: dict[str, object] = {}
    try:
        with winreg.OpenKey(HIVES[hive], subkey) as key:
            count = winreg.QueryInfoKey(key)[1]
            for index in range(count):
                try:
                    name, value, _ = winreg.EnumValue(key, index)
                except OSError as exc:
                    log.warning("could not enumerate value %d of %s: %s", index, subkey, exc)
                    continue
                values[name] = value
    except FileNotFoundError:
        log.debug("absent: %s\\%s", hive, subkey)
    except OSError as exc:
        log.warning("could not open %s\\%s: %s", hive, subkey, exc)
    return values


def subkey_names(hive: str, subkey: str) -> list[str]:
    """Names of the immediate child keys. Empty if the key is absent."""
    names: list[str] = []
    try:
        with winreg.OpenKey(HIVES[hive], subkey) as key:
            count = winreg.QueryInfoKey(key)[0]
            for index in range(count):
                try:
                    names.append(winreg.EnumKey(key, index))
                except OSError as exc:
                    log.warning("could not enumerate subkey %d of %s: %s", index, subkey, exc)
    except FileNotFoundError:
        log.debug("absent: %s\\%s", hive, subkey)
    except OSError as exc:
        log.warning("could not open %s\\%s: %s", hive, subkey, exc)
    return names


def key_exists(hive: str, subkey: str) -> bool:
    try:
        with winreg.OpenKey(HIVES[hive], subkey):
            return True
    except FileNotFoundError:
        return False
    except OSError as exc:
        log.warning("could not test %s\\%s: %s", hive, subkey, exc)
        return False


def read_binary(hive: str, subkey: str, name: str) -> bytes | None:
    """A binary value, or None if the key or value is not there (Phase 92: Windows' StartupApproved)."""
    try:
        with winreg.OpenKey(HIVES[hive], subkey) as key:
            value, kind = winreg.QueryValueEx(key, name)
    except FileNotFoundError:
        log.debug("absent: %s\\%s\\%s", hive, subkey, name)
        return None
    except OSError as exc:
        log.warning("could not read %s\\%s\\%s: %s", hive, subkey, name, exc)
        return None
    if kind != winreg.REG_BINARY or not isinstance(value, bytes):
        log.warning("%s\\%s\\%s is not binary (type %s)", hive, subkey, name, kind)
        return None
    return value


def write_string(hive: str, subkey: str, name: str, value: str) -> bool:
    """Write a string value, making the key if it is missing. False -- logged -- if it cannot be."""
    try:
        with winreg.CreateKeyEx(HIVES[hive], subkey, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
    except OSError as exc:
        log.warning("could not write %s\\%s\\%s: %s", hive, subkey, name, exc)
        return False
    return True


def delete_value(hive: str, subkey: str, name: str) -> bool:
    """Delete one value. True when it is gone -- including when it was never there."""
    try:
        with winreg.OpenKey(HIVES[hive], subkey, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, name)
    except FileNotFoundError:
        return True
    except OSError as exc:
        log.warning("could not delete %s\\%s\\%s: %s", hive, subkey, name, exc)
        return False
    return True
