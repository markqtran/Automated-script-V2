"""Wait for Premiere/Media Encoder proxies, back up to HDD, optional Drive upload."""

from __future__ import annotations

import time
from pathlib import Path

from rich.console import Console

from .gdrive import upload_to_drive
from .project_paths import find_prproj, proxies_dir, project_root
from .proxy_backup import backup_proxies_to_hdd
from .scripts import resolve_project_folder

console = Console()


def _proxy_files_ready(proxy_path: Path) -> bool:
    return proxy_path.is_dir() and any(f.is_file() for f in proxy_path.rglob("*"))


def _folder_stable(path: Path, wait_seconds: int = 30) -> bool:
    """True if no file in tree changed size/mtime for wait_seconds."""
    if not path.exists():
        return False

    def snapshot() -> dict[str, tuple[int, float]]:
        snap: dict[str, tuple[int, float]] = {}
        for f in path.rglob("*"):
            if f.is_file():
                st = f.stat()
                snap[str(f)] = (st.st_size, st.st_mtime)
        return snap

    last = snapshot()
    if not last:
        return False

    stable_for = 0
    poll = 5

    while stable_for < wait_seconds:
        time.sleep(poll)
        current = snapshot()
        if current == last and current:
            stable_for += poll
        else:
            stable_for = 0
            last = current

    return True


def wait_for_proxies(
    cfg: dict,
    number: str,
    *,
    timeout_minutes: int = 180,
    stable_seconds: int = 30,
) -> tuple[str, Path] | None:
    """Block until SSD Video/Proxies has stable proxy files. Returns folder_name, ssd_path."""
    folder_name = resolve_project_folder(cfg, number)
    ssd_path, _ = project_root(cfg, folder_name)
    proxy_path = proxies_dir(cfg, ssd_path)

    console.print(f"\n[bold]Waiting for proxies on SSD[/bold] — {folder_name}")
    console.print(f"  Project: {ssd_path}")
    console.print(f"  Watching: {proxy_path or (ssd_path / 'Video' / 'Proxies')}\n")

    deadline = time.time() + timeout_minutes * 60
    while time.time() < deadline:
        proxy_path = proxies_dir(cfg, ssd_path)
        if proxy_path and _proxy_files_ready(proxy_path):
            console.print(f"[green]Proxies found:[/green] {proxy_path}")
            if _folder_stable(proxy_path, stable_seconds):
                console.print("[green]Proxies complete (files stable).[/green]")
                return folder_name, ssd_path
            console.print("[dim]Proxies still encoding, waiting...[/dim]")
        else:
            console.print("[dim]No proxy files yet — Media Encoder still working...[/dim]")
        time.sleep(10)

    console.print("[red]Timed out waiting for proxies on SSD.[/red]")
    return None


def watch_and_backup_hdd(
    cfg: dict,
    number: str,
    *,
    timeout_minutes: int = 180,
    stable_seconds: int = 30,
    dry_run: bool = False,
) -> dict:
    """Wait for SSD proxies, then copy Video/Proxies → HDD backup."""
    waited = wait_for_proxies(
        cfg, number, timeout_minutes=timeout_minutes, stable_seconds=stable_seconds
    )
    if not waited:
        return {"success": False, "reason": "timeout"}

    folder_name, _ = waited
    backup_stats = backup_proxies_to_hdd(cfg, folder_name, dry_run=dry_run)
    ok = backup_stats.get("copied", 0) > 0 or backup_stats.get("skipped", 0) > 0
    return {"success": ok, "backup": backup_stats}


def watch_and_upload(
    cfg: dict,
    number: str,
    *,
    timeout_minutes: int = 180,
    stable_seconds: int = 30,
    dry_run: bool = False,
) -> dict:
    """Wait for proxies, copy SSD → HDD, then upload Proxies + .prproj to Drive."""
    waited = wait_for_proxies(
        cfg, number, timeout_minutes=timeout_minutes, stable_seconds=stable_seconds
    )
    if not waited:
        return {"success": False, "reason": "timeout"}

    folder_name, ssd_path = waited
    backup_stats = backup_proxies_to_hdd(cfg, folder_name, dry_run=dry_run)

    if dry_run:
        console.print("[yellow]Dry run — would upload to Drive next.[/yellow]")
        return {"success": True, "dry_run": True, "backup": backup_stats}

    upload_stats = upload_to_drive(
        ssd_path, cfg, project_file=find_prproj(cfg, ssd_path), dry_run=False
    )
    return {"success": True, "backup": backup_stats, "upload": upload_stats}
