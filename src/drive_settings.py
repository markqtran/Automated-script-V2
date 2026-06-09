"""Drive letter helpers — including optional N/A for unused slots."""

from __future__ import annotations

DRIVE_NA_LABEL = "N/A"


def is_drive_na(value: str | None) -> bool:
    """True when the user has no drive for this slot."""
    if value is None:
        return True
    text = str(value).strip()
    if not text:
        return True
    return text.upper() in ("N/A", "NA", "NONE", "-", "NONE.")


def drive_label_for_gui(value: str | None) -> str:
    """Show N/A in dropdowns when the slot is unused."""
    return DRIVE_NA_LABEL if is_drive_na(value) else str(value).strip()


def normalize_drive_value(value: str) -> str:
    """Convert GUI value to a Windows drive root, or empty string for N/A."""
    if is_drive_na(value):
        return ""
    text = value.strip()
    if not text.endswith("\\"):
        text = text.rstrip(":") + ":\\"
    return text


def drive_combo_options(*, include_na: bool = False) -> list[str]:
    """Drive letters for comboboxes, optionally with N/A first."""
    from .app_paths import list_windows_drives

    drives = list_windows_drives() or ["C:\\"]
    if include_na:
        return [DRIVE_NA_LABEL, *drives]
    return drives
