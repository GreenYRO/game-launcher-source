"""Reading the version resource embedded in a Windows executable.

win32api.GetFileVersionInfo is the primary path: it is a direct Win32 call and does not
read the file body, which matters when a game exe is 380 MB. pefile is a fallback for the
occasional binary whose resource the Win32 call refuses, and is size-capped because pefile
reads the whole file into memory.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import win32api

log = logging.getLogger(__name__)

# Win32 error for "the specified resource type cannot be found in the image file".
_ERROR_RESOURCE_TYPE_NOT_FOUND = 1813

FIELDS = ("ProductName", "FileDescription", "CompanyName")

# pefile loads the entire file, so only fall back for reasonably sized binaries.
PEFILE_FALLBACK_MAX_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True)
class VersionInfo:
    product_name: str | None = None
    file_description: str | None = None
    company_name: str | None = None
    origin: str = "none"

    @property
    def is_empty(self) -> bool:
        return not (self.product_name or self.file_description)


EMPTY = VersionInfo()


def read_version_info(path: str, size: int | None = None) -> VersionInfo:
    """Best-effort read. Never raises; an unreadable resource is normal, not an error."""
    info = _read_win32(path)
    if not info.is_empty:
        return info
    if size is not None and size > PEFILE_FALLBACK_MAX_BYTES:
        log.debug("no version resource via win32api and too large for pefile: %s", path)
        return info
    return _read_pefile(path) or info


def _read_win32(path: str) -> VersionInfo:
    try:
        translations = win32api.GetFileVersionInfo(path, "\\VarFileInfo\\Translation")
    except Exception as exc:  # pywintypes.error and friends
        if getattr(exc, "winerror", None) != _ERROR_RESOURCE_TYPE_NOT_FOUND:
            log.debug("GetFileVersionInfo failed on %s: %s", path, exc)
        return EMPTY
    if not translations:
        log.debug("empty translation table: %s", path)
        return EMPTY

    lang, codepage = translations[0]
    values: dict[str, str | None] = {}
    for field in FIELDS:
        key = "\\StringFileInfo\\%04X%04X\\%s" % (lang, codepage, field)
        try:
            raw = win32api.GetFileVersionInfo(path, key)
        except Exception as exc:
            log.debug("field %s unreadable in %s: %s", field, path, exc)
            raw = None
        values[field] = raw.strip() if isinstance(raw, str) and raw.strip() else None

    return VersionInfo(
        product_name=values["ProductName"],
        file_description=values["FileDescription"],
        company_name=values["CompanyName"],
        origin="win32api",
    )


def _read_pefile(path: str) -> VersionInfo | None:
    try:
        import pefile
    except ImportError as exc:
        log.debug("pefile unavailable (%s); skipping fallback for %s", exc, path)
        return None

    try:
        pe = pefile.PE(path, fast_load=True)
    except Exception as exc:
        log.debug("pefile could not open %s: %s", path, exc)
        return None

    try:
        pe.parse_data_directories(
            directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_RESOURCE"]]
        )
        found: dict[str, str] = {}
        for file_info in getattr(pe, "FileInfo", []) or []:
            for entry in file_info:
                for table in getattr(entry, "StringTable", []) or []:
                    for raw_key, raw_value in table.entries.items():
                        key = raw_key.decode("utf-8", "replace")
                        value = raw_value.decode("utf-8", "replace").strip()
                        if key in FIELDS and value:
                            found.setdefault(key, value)
        if not found:
            return None
        return VersionInfo(
            product_name=found.get("ProductName"),
            file_description=found.get("FileDescription"),
            company_name=found.get("CompanyName"),
            origin="pefile",
        )
    except Exception as exc:
        log.debug("pefile resource parse failed on %s: %s", path, exc)
        return None
    finally:
        try:
            pe.close()
        except Exception as exc:
            log.debug("pefile close failed on %s: %s", path, exc)
