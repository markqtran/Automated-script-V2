"""Standard project folder layout on SSD / HDD."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from .utils import normalize_path


def _drive_root(path: Path) -> str | None:
    """Return Windows drive root like E:\\ or None for UNC/non-drive paths."""
    if path.drive:
        return path.drive + "\\"
    anchor = path.anchor
    return anchor if anchor else None


def require_destination_ready(path: Path, role: str, config_key: str) -> None:
    """
    Fail fast with a clear message when a configured drive is unplugged or wrong.

    WinError 21 "device is not ready" often means the letter in config.yaml
    does not match the plugged-in SSD/HDD (e.g. Soju is F: but config says E:).
    """
    root = _drive_root(path)
    if not root:
        return

    if not os.path.exists(root):
        print(
            f"\n[ERROR] {role} drive not found: {root}\n"
            f"  Config key: destinations.{config_key}\n"
            f"  Target path: {path}\n\n"
            f"  Fix: Plug in the drive, open File Explorer, note the correct letter,\n"
            f"  then edit config.yaml → destinations.{config_key}\n"
            f"  Example for Soju SSD: ssd_editing: \"F:\\\\\"\n",
            file=sys.stderr,
        )
        raise SystemExit(1)

    try:
        os.listdir(root)
    except OSError as exc:
        print(
            f"\n[ERROR] Cannot access {role} drive {root}: {exc}\n"
            f"  Config: destinations.{config_key} = {path.anchor or path}\n"
            f"  Unplug/replug the drive or fix the drive letter in config.yaml.\n",
            file=sys.stderr,
        )
        raise SystemExit(1)


def video_folder_name(cfg: dict) -> str:
    return cfg.get("project", {}).get("video_folder", "Video")


def proxies_folder_name(cfg: dict) -> str:
    return cfg.get("proxies", {}).get("subfolder", "Proxies")


def project_root(cfg: dict, folder_name: str) -> tuple[Path, Path]:
    """SSD and HDD roots for a project, e.g. F:\\[003] Title\\."""
    dest = cfg["destinations"]
    ssd = normalize_path(dest["ssd_editing"]) / folder_name
    hdd = normalize_path(dest["hdd_backup"]) / folder_name
    require_destination_ready(ssd, "Editing SSD (Soju)", "ssd_editing")
    require_destination_ready(hdd, "Backup HDD", "hdd_backup")
    return ssd, hdd


def video_dir(cfg: dict, folder_name: str, *, destination: str = "ssd") -> Path:
    """Footage + Premiere proxies live under Video\\ on the SSD (and mirror on HDD)."""
    ssd, hdd = project_root(cfg, folder_name)
    root = ssd if destination == "ssd" else hdd
    return root / video_folder_name(cfg)


def proxies_dir(cfg: dict, project_folder: str | Path) -> Path | None:
    """
    Find Proxies folder for Google Drive upload.
    Premiere (next to original media) creates: Project/Video/Proxies/
    """
    root = normalize_path(project_folder)
    video = video_folder_name(cfg)
    proxy_name = proxies_folder_name(cfg)
    for candidate in (root / video / proxy_name, root / proxy_name):
        if candidate.is_dir():
            return candidate
    return None


def find_prproj(cfg: dict, project_folder: str | Path) -> Path | None:
    root = normalize_path(project_folder)
    exts = cfg.get("project_extensions", [".prproj"])
    candidates = sorted(root.glob(f"*{exts[0]}"))
    if candidates:
        return candidates[0]
    # Match folder name, e.g. [003] Title.prproj
    named = root / f"{root.name}.prproj"
    if named.exists():
        return named
    return None
