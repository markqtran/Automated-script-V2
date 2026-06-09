"""Load and validate configuration."""

from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path

import yaml

from .app_paths import default_config_path, ensure_user_config, resource_path
from .drive_settings import drive_label_for_gui, is_drive_na, normalize_drive_value
from .utils import normalize_path

DEFAULT_CONFIG = Path("config.yaml")
EXAMPLE_CONFIG = Path("config.example.yaml")

_FOLDER_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{10,}$")
_DRIVE_URL_RE = re.compile(r"/folders/([a-zA-Z0-9_-]+)")


def extract_folder_id(url_or_id: str) -> str:
    """Extract a Google Drive folder ID from a full URL or bare ID."""
    text = (url_or_id or "").strip()
    if not text:
        return ""
    if _FOLDER_ID_RE.match(text):
        return text
    match = _DRIVE_URL_RE.search(text)
    return match.group(1) if match else text


def load_config(path: Path | None = None) -> dict:
    if path is None:
        ensure_user_config()
        config_path = default_config_path()
    else:
        config_path = normalize_path(path)
        if not config_path.exists():
            example = resource_path(EXAMPLE_CONFIG.name)
            if not example.exists():
                example = normalize_path(EXAMPLE_CONFIG)
            raise FileNotFoundError(
                f"Config not found: {config_path}\n"
                f"Copy {example.name} to {config_path.name} and edit your drive paths."
            )
    with config_path.open(encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    _validate(cfg)
    return cfg


def save_config(cfg: dict, path: Path | None = None) -> Path:
    """Write config to disk (creates parent folders if needed)."""
    config_path = normalize_path(path or default_config_path())
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("w", encoding="utf-8") as f:
        yaml.dump(cfg, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
    return config_path


def default_config_template() -> dict:
    """Load config.example.yaml as a dict (for first-time GUI setup)."""
    example = resource_path(EXAMPLE_CONFIG.name)
    if not example.is_file():
        example = normalize_path(EXAMPLE_CONFIG)
    if example.is_file():
        with example.open(encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def merge_user_settings(cfg: dict, settings: dict) -> dict:
    """Apply GUI settings onto an existing config dict."""
    merged = deepcopy(cfg)
    merged.setdefault("sd_cards", {})
    merged.setdefault("destinations", {})
    merged.setdefault("scripts", {})
    merged.setdefault("google_drive", {})

    for key in ("primary", "backup"):
        if key in settings.get("sd_cards", {}):
            raw = settings["sd_cards"][key]
            if key == "backup" and is_drive_na(raw):
                merged["sd_cards"]["backup"] = ""
                merged["sd_cards"]["single_card"] = True
            else:
                merged["sd_cards"][key] = normalize_drive_value(raw)
                if key == "backup":
                    merged["sd_cards"]["single_card"] = False

    for key in ("ssd_editing", "hdd_backup", "hdd_backup_mirror"):
        if key in settings.get("destinations", {}):
            raw = settings["destinations"][key]
            if key == "hdd_backup_mirror" and is_drive_na(raw):
                merged["destinations"]["hdd_backup_mirror"] = ""
                merged.setdefault("mirror", {})["enabled"] = False
            else:
                merged["destinations"][key] = normalize_drive_value(raw)
                if key == "hdd_backup_mirror":
                    merged.setdefault("mirror", {})["enabled"] = True

    scripts_id = settings.get("scripts_folder_id", "")
    if scripts_id:
        merged["scripts"]["folder_id"] = scripts_id

    drive_id = settings.get("google_drive_folder_id", "")
    if drive_id:
        merged["google_drive"]["folder_id"] = drive_id

    merged["google_drive"].setdefault("rclone_remote", "gdrive")
    return merged


def config_to_gui_settings(cfg: dict) -> dict:
    """Extract user-editable fields for the settings dialog."""
    sd = cfg.get("sd_cards", {})
    dest = cfg.get("destinations", {})
    return {
        "sd_cards": {
            "primary": sd.get("primary", "G:\\"),
            "backup": drive_label_for_gui(sd.get("backup", "")),
        },
        "destinations": {
            "ssd_editing": dest.get("ssd_editing", "E:\\"),
            "hdd_backup": dest.get("hdd_backup", "H:\\"),
            "hdd_backup_mirror": drive_label_for_gui(dest.get("hdd_backup_mirror", "")),
        },
        "scripts_folder_id": cfg.get("scripts", {}).get("folder_id", ""),
        "google_drive_folder_id": cfg.get("google_drive", {}).get("folder_id", ""),
    }


def _validate(cfg: dict) -> None:
    required = [
        ("sd_cards", "primary"),
        ("destinations", "ssd_editing"),
        ("destinations", "hdd_backup"),
    ]
    # backup SD and mirror HDD are optional (N/A in Settings)
    sd = cfg.setdefault("sd_cards", {})
    if "backup" not in sd:
        sd["backup"] = ""
    if is_drive_na(sd.get("backup")):
        sd["backup"] = ""
        sd.setdefault("single_card", True)
    dest = cfg.setdefault("destinations", {})
    if "hdd_backup_mirror" not in dest:
        dest["hdd_backup_mirror"] = ""
    if is_drive_na(dest.get("hdd_backup_mirror")):
        dest["hdd_backup_mirror"] = ""
        cfg.setdefault("mirror", {})["enabled"] = False
    for *parents, key in required:
        node = cfg
        for p in parents:
            if p not in node:
                raise ValueError(f"Missing config section: {'.'.join(parents)}")
            node = node[p]
        if key not in node:
            raise ValueError(f"Missing config key: {'.'.join(parents + [key])}")
