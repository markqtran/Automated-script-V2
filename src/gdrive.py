"""Upload project files and proxies to Google Drive via rclone."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rich.console import Console

from .project_paths import find_prproj, proxies_dir, proxies_folder_name
from .rclone_setup import find_rclone
from .utils import normalize_path

console = Console()


def list_drive_files(cfg: dict, folder_id: str) -> list[str]:
    """List filenames in a Google Drive folder via rclone."""
    gdrive = cfg.get("google_drive", {})
    remote = gdrive.get("rclone_remote", "gdrive")
    rclone = find_rclone()

    cmd = [
        rclone,
        "lsf",
        f"{remote}:",
        "--drive-root-folder-id",
        folder_id,
        "--files-only",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"Failed to list Drive folder {folder_id}:\n{result.stderr.strip()}"
        )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _drive_dest(cfg: dict, subpath: str) -> tuple[str, list[str]]:
    """Build rclone destination path and optional flags for a shared folder ID."""
    gdrive = cfg.get("google_drive", {})
    remote = gdrive.get("rclone_remote", "gdrive")
    folder_id = gdrive.get("folder_id")
    upload_folder = gdrive.get("upload_folder", "")

    if folder_id:
        # Upload into a specific shared folder (e.g. [04] Proxies/Project file)
        dest = f"{remote}:{subpath}" if subpath else f"{remote}:"
        extra = ["--drive-root-folder-id", folder_id]
    else:
        base = upload_folder or "Assistant Editor Projects"
        dest = f"{remote}:{base}/{subpath}" if subpath else f"{remote}:{base}"
        extra = []

    return dest, extra


def upload_to_drive(
    local_folder: str | Path,
    cfg: dict,
    project_file: str | Path | None = None,
    dry_run: bool = False,
    *,
    proxies_path: Path | None = None,
    proxies_upload_name: str | None = None,
    proxies_drive_subpath: str | None = None,
) -> dict:
    """
    Upload Proxies folder + .prproj to Google Drive (assistant editor handoff).

    Primary run: Video/Proxies/ → Drive .../Proxies/
    Pick-up run: Pick Up Shots #N/Proxies/ → Drive .../Pickup Proxies #N/Proxies/
    """
    gdrive = cfg.get("google_drive", {})
    folder_id = gdrive.get("folder_id")

    local = normalize_path(local_folder)
    if not local.exists():
        raise FileNotFoundError(f"Local folder not found: {local}")

    rclone = find_rclone()
    project_name = local.name
    dest, drive_flags = _drive_dest(cfg, project_name)

    stats = {"uploads": 0, "errors": 0}

    def _run_rclone(src: Path, target: str) -> bool:
        cmd = [
            rclone,
            "copy",
            str(src),
            target,
            "--progress",
            "--checksum",
            "-v",
            *drive_flags,
        ]
        if dry_run:
            cmd.insert(1, "--dry-run")

        label = f"{target} (folder_id={folder_id})" if folder_id else target
        console.print(f"\n[bold]Uploading[/bold] {src} -> {label}")
        result = subprocess.run(cmd)
        return result.returncode == 0

    # Upload Proxies (primary: Proxies/ | pick-up: Pickup Proxies/Proxies/)
    proxy_path = proxies_path if proxies_path else proxies_dir(cfg, local)
    if proxies_drive_subpath:
        proxy_target = f"{dest}/{proxies_drive_subpath}"
    else:
        proxy_name = proxies_upload_name or proxies_folder_name(cfg)
        proxy_target = f"{dest}/{proxy_name}"
    if proxy_path and proxy_path.is_dir():
        ok = _run_rclone(proxy_path, proxy_target)
        stats["uploads" if ok else "errors"] += 1
    elif proxies_path:
        console.print(
            f"[yellow]No Proxies folder found.[/yellow]\n"
            f"  Expected: {proxies_path}\n"
            f"  Create proxies in Premiere first (right-click clips > Proxy > Create Proxies)."
        )
    else:
        video = cfg.get("project", {}).get("video_folder", "Video")
        proxy_name = proxies_folder_name(cfg)
        console.print(
            f"[yellow]No Proxies folder found.[/yellow]\n"
            f"  Expected: {local / video / proxy_name} or {local / proxy_name}\n"
            f"  Create proxies in Premiere first (right-click clips > Proxy > Create Proxies)."
        )

    # Upload .prproj at project root only
    if project_file:
        prproj = normalize_path(project_file)
    else:
        found = find_prproj(cfg, local)
        prproj = found if found else None

    if prproj and prproj.exists():
        ok = _run_rclone(prproj, dest)
        stats["uploads" if ok else "errors"] += 1
    elif project_file:
        console.print(f"[yellow]Project file not found: {prproj}[/yellow]")
    else:
        console.print(
            "[yellow]No .prproj found in project folder.[/yellow] "
            "Save your Premiere project in the project folder, then re-run."
        )

    if stats["errors"]:
        console.print(f"\n[red]Upload finished with {stats['errors']} error(s).[/red]")
    else:
        if folder_id:
            link = f"https://drive.google.com/drive/folders/{folder_id}"
            console.print(
                f"\n[green]Upload complete.[/green] Project: [001] style folder "
                f"'{project_name}' in [04] Proxies/Project file"
            )
            console.print(f"  Drive parent: {link}")
        else:
            console.print(f"\n[green]Upload complete.[/green] Assistant editor folder: {dest}")

    stats["remote_path"] = dest
    stats["project_name"] = project_name
    return stats
