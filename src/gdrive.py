"""Upload project files and proxies to Google Drive via rclone."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from rich.console import Console

from .project_paths import find_prproj, video_folder_name
from .utils import normalize_path

console = Console()


def _find_rclone() -> str:
    path = shutil.which("rclone")
    if path:
        return path

    # Also check project folder (install-rclone.ps1 puts it here)
    candidates = [
        Path.cwd() / "rclone.exe",
        Path(__file__).resolve().parent.parent / "rclone.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    raise RuntimeError(
        "rclone not found. Run: powershell -ExecutionPolicy Bypass -File install-rclone.ps1\n"
        "Or download from https://rclone.org/downloads/"
    )


def list_drive_files(cfg: dict, folder_id: str) -> list[str]:
    """List filenames in a Google Drive folder via rclone."""
    gdrive = cfg.get("google_drive", {})
    remote = gdrive.get("rclone_remote", "gdrive")
    rclone = _find_rclone()

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
) -> dict:
    """
    Upload Video/ (footage + Proxies) and .prproj to Google Drive [04].

    Creates a Drive subfolder named like the SSD project folder, e.g.
    [003] POV You're teaching an ipad kid/Video/... and [003] ....prproj
    under google_drive.folder_id ([04] Proxies/Project file).
    """
    gdrive = cfg.get("google_drive", {})
    folder_id = gdrive.get("folder_id")

    local = normalize_path(local_folder)
    if not local.exists():
        raise FileNotFoundError(f"Local folder not found: {local}")

    _find_rclone()
    rclone = shutil.which("rclone") or "rclone"
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

    # Upload entire Video/ tree (clips, .xml sidecars, Video/Proxies/, etc.)
    video_name = video_folder_name(cfg)
    video_path = local / video_name
    if video_path.is_dir() and any(video_path.rglob("*")):
        ok = _run_rclone(video_path, f"{dest}/{video_name}")
        stats["uploads" if ok else "errors"] += 1
    else:
        console.print(
            f"[yellow]No Video folder to upload.[/yellow]\n"
            f"  Expected: {video_path}\n"
            f"  Run ingest first: python main.py daily --number ..."
        )
        stats["errors"] += 1

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
                f"\n[green]Upload complete.[/green] Drive folder: '{project_name}'"
            )
            console.print(f"  Contents: {video_name}/ + .prproj")
            console.print(f"  Open [04] and find: {link}")
        else:
            console.print(f"\n[green]Upload complete.[/green] Assistant editor folder: {dest}")

    stats["remote_path"] = dest
    stats["project_name"] = project_name
    return stats
