"""Resolve application root, user config, and bundled resource paths."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

APP_NAME = "FootageWorkflow"


def is_frozen() -> bool:
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def app_root() -> Path:
    """Directory containing the exe (frozen) or project root (dev)."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def bundle_root() -> Path:
    """PyInstaller extraction dir (frozen) or project root (dev)."""
    if is_frozen():
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return app_root()


def resource_path(relative: str | Path) -> Path:
    """Path to a bundled file (templates, example config, etc.)."""
    return bundle_root() / relative


def user_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if base:
        return Path(base) / APP_NAME
    return Path.home() / f".{APP_NAME}"


def default_config_path() -> Path:
    """User-editable config location (persists across exe updates)."""
    if not is_frozen():
        local = Path("config.yaml")
        if local.is_file():
            return local.resolve()
    return user_data_dir() / "config.yaml"


def ensure_user_config() -> Path:
    """
    Create config.yaml in the user data folder on first run.
    Returns the path to the config file.
    """
    config_path = default_config_path()
    if config_path.is_file():
        return config_path

    config_path.parent.mkdir(parents=True, exist_ok=True)
    example = resource_path("config.example.yaml")
    if example.is_file():
        shutil.copy2(example, config_path)
    else:
        config_path.write_text(
            "# Footage Workflow — edit drive letters and Google links in Settings.\n",
            encoding="utf-8",
        )
    return config_path


def list_windows_drives() -> list[str]:
    """Return available drive roots like ['C:\\\\', 'E:\\\\', ...]."""
    import string

    return [f"{letter}:\\" for letter in string.ascii_uppercase if Path(f"{letter}:\\").exists()]
