"""Auto-detect Windows drive letters for first-time setup."""

from __future__ import annotations

import ctypes
import string
import sys
from pathlib import Path

from .drive_settings import DRIVE_NA_LABEL

DRIVE_REMOVABLE = 2
DRIVE_FIXED = 3


def _drive_type(root: str) -> int:
    return int(ctypes.windll.kernel32.GetDriveTypeW(root))  # type: ignore[attr-defined]


def _drive_size(root: str) -> int:
    try:
        import shutil

        return shutil.disk_usage(root).total
    except OSError:
        return 0


def is_removable_drive(path: str | Path) -> bool:
    """True when path is on a removable drive (typical SD card reader)."""
    if sys.platform != "win32":
        return False
    text = str(path).strip()
    if len(text) >= 2 and text[1] == ":":
        root = text[:2] + "\\"
    else:
        return False
    if not Path(root).exists():
        return False
    return _drive_type(root) == DRIVE_REMOVABLE


def list_removable_drives() -> list[str]:
    drives: list[str] = []
    for letter in string.ascii_uppercase:
        root = f"{letter}:\\"
        if Path(root).exists() and _drive_type(root) == DRIVE_REMOVABLE:
            drives.append(root)
    return drives


def list_fixed_drives(*, exclude_system: bool = True) -> list[str]:
    drives: list[str] = []
    for letter in string.ascii_uppercase:
        if exclude_system and letter == "C":
            continue
        root = f"{letter}:\\"
        if Path(root).exists() and _drive_type(root) == DRIVE_FIXED:
            drives.append(root)
    return drives


def auto_assign_drives() -> dict:
    """
    Guess drive roles from plugged-in hardware.

    Removable → SD cards. Fixed (non-C) → SSD/HDD by size (smallest = editing SSD).
    """
    removable = list_removable_drives()
    fixed = sorted(list_fixed_drives(), key=_drive_size)

    sd_primary = removable[0] if removable else "G:\\"
    sd_backup = removable[1] if len(removable) > 1 else DRIVE_NA_LABEL

    ssd_editing = fixed[0] if fixed else "E:\\"
    hdd_backup = fixed[-1] if fixed else "H:\\"
    hdd_mirror = fixed[-2] if len(fixed) > 1 else DRIVE_NA_LABEL

    return {
        "sd_cards": {"primary": sd_primary, "backup": sd_backup},
        "destinations": {
            "ssd_editing": ssd_editing,
            "hdd_backup": hdd_backup,
            "hdd_backup_mirror": hdd_mirror,
        },
    }
