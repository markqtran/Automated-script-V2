"""Wait for Premiere/Media Encoder to finish proxies, then upload to Google Drive."""

from __future__ import annotations

import time
from pathlib import Path

from rich.console import Console

from .gdrive import upload_to_drive
from .project_paths import find_prproj, proxies_dir, project_root
from .scripts import resolve_project_folder

console = Console()


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

    return bool(last)


def watch_and_upload(
    cfg: dict,
    number: str,
    *,
    timeout_minutes: int = 180,
    stable_seconds: int = 30,
    dry_run: bool = False,
) -> dict:
    """
    Poll Video/Proxies until files stop changing, then upload Proxies + .prproj.
    """
    folder_name = resolve_project_folder(cfg, number)
    ssd_path, _ = project_root(cfg, folder_name)
    proxy_path = proxies_dir(cfg, ssd_path)

    console.print(f"\n[bold]Watching for proxies[/bold] — {folder_name}")
    console.print(f"  Project: {ssd_path}")
    console.print(f"  Waiting for: {proxy_path or '(Video/Proxies)'}\n")

    deadline = time.time() + timeout_minutes * 60
    while time.time() < deadline:
        proxy_path = proxies_dir(cfg, ssd_path)
        if proxy_path and any(proxy_path.rglob("*")):
            console.print(f"[green]Proxies folder found:[/green] {proxy_path}")
            if _folder_stable(proxy_path, stable_seconds):
                console.print("[green]Proxies look complete (files stable).[/green]")
                break
            console.print("[dim]Proxies still changing, waiting...[/dim]")
        else:
            console.print("[dim]No proxies yet — finish Create Proxies in Premiere/Media Encoder...[/dim]")
        time.sleep(10)
    else:
        console.print("[red]Timed out waiting for proxies.[/red]")
        return {"success": False, "reason": "timeout"}

    if dry_run:
        console.print("[yellow]Dry run — would upload now.[/yellow]")
        return {"success": True, "dry_run": True}

    return upload_to_drive(ssd_path, cfg, project_file=find_prproj(cfg, ssd_path), dry_run=False)
