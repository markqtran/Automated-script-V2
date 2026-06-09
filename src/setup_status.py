"""Check whether first-time setup is complete."""

from __future__ import annotations

from .config_loader import default_config_template, load_config
from .rclone_setup import is_rclone_configured, rclone_is_installed


def setup_status() -> dict[str, bool]:
    """Return which setup steps are done (fast local checks only)."""
    config_ok = False
    try:
        load_config()
        config_ok = True
    except (FileNotFoundError, ValueError):
        pass

    rclone_ok = rclone_is_installed()
    google_ok = is_rclone_configured("gdrive") if rclone_ok else False

    return {
        "config": config_ok,
        "rclone": rclone_ok,
        "google": google_ok,
        "complete": config_ok and rclone_ok and google_ok,
    }


def default_google_folder_ids() -> dict[str, str]:
    """Team default folder IDs from config.example.yaml."""
    template = default_config_template()
    return {
        "scripts_folder_id": template.get("scripts", {}).get("folder_id", ""),
        "google_drive_folder_id": template.get("google_drive", {}).get("folder_id", ""),
    }
