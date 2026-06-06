"""Copy finished proxies from SSD (Soju) to matching HDD backup folder."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from .ingest import _copy_file
from .project_paths import find_prproj, project_root, proxies_dir, proxies_path, video_dir
from .utils import format_bytes

console = Console()


def _hdd_proxies_path(cfg: dict, hdd_project: Path) -> Path:
    """Mirror SSD layout: project/Video/Proxies/."""
    from .premiere_proxy import proxy_subfolder_name
    from .project_paths import proxies_dir, video_folder_name

    video = video_folder_name(cfg)
    proxy_name = proxy_subfolder_name(cfg)
    found = proxies_dir(cfg, hdd_project)
    return found if found else hdd_project / video / proxy_name


def _proxy_files_under(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    return sorted(
        (p for p in folder.rglob("*") if p.is_file()),
        key=lambda p: str(p).lower(),
    )


def _collect_ssd_proxy_files(
    cfg: dict,
    folder_name: str,
    *,
    pickup_proxies_folder: str | None = None,
) -> tuple[Path, list[Path]]:
    """
    Prefer Video/Proxies/ or pick-up Pickup Proxies [#N]/ on SSD.
    """
    ssd_root, _ = project_root(cfg, folder_name)

    if pickup_proxies_folder:
        final = ssd_root / pickup_proxies_folder
        files = _proxy_files_under(final)
        if files:
            return final, files
        from .pickup import load_pickup_run, pickup_working_proxies_path

        run = load_pickup_run(ssd_root)
        if run:
            working = pickup_working_proxies_path(ssd_root, run)
            files = _proxy_files_under(working)
            if files:
                return working, files

    canonical = proxies_path(cfg, folder_name, destination="ssd")
    discovered = proxies_dir(cfg, ssd_root)
    source_root = discovered if discovered else canonical

    files = _proxy_files_under(source_root)
    if files:
        return source_root, files

    video_root = video_dir(cfg, folder_name, destination="ssd")
    fallback: list[Path] = []
    for path in video_root.rglob("*"):
        if not path.is_file():
            continue
        if "_proxy" in path.stem.lower():
            fallback.append(path)

    if fallback:
        console.print(
            f"[dim]Using {len(fallback)} proxy file(s) under Video/ "
            f"(not only {canonical.name}/).[/dim]"
        )
        return video_root, sorted(fallback, key=lambda p: str(p).lower())

    return canonical, []


def _robocopy_proxies(src: Path, dest: Path) -> bool:
    """Mirror proxy folder on Windows (fast, preserves timestamps)."""
    robocopy = shutil.which("robocopy")
    if not robocopy:
        return False
    dest.mkdir(parents=True, exist_ok=True)
    cmd = [
        robocopy,
        str(src),
        str(dest),
        "/E",
        "/R:2",
        "/W:2",
        "/MT:8",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    # robocopy: exit code < 8 means success (0-7 are OK)
    return result.returncode < 8


def _backup_prproj_to_hdd(
    cfg: dict,
    ssd_root: Path,
    hdd_root: Path,
    *,
    verify: bool,
    dry_run: bool,
    stats: dict,
) -> None:
    """Copy .prproj from SSD project root to matching HDD project folder."""
    prproj = find_prproj(cfg, ssd_root)
    if not prproj or not prproj.exists():
        console.print("[yellow]No .prproj on SSD to back up.[/yellow]")
        console.print("  Save the Premiere project in the project folder on Soju, then re-run.")
        return

    dest = hdd_root / prproj.name
    stats["prproj_src"] = str(prproj)
    stats["prproj_dest"] = str(dest)

    if dry_run:
        console.print(f"[yellow]Dry run — would copy[/yellow] {prproj.name} → HDD")
        return

    ok, msg = _copy_file(prproj, dest, verify, dry_run=False)
    if ok:
        stats["prproj_copied"] = True
        stats["bytes"] += prproj.stat().st_size
        console.print(f"[green]Project file backed up:[/green] {dest}")
    elif msg.startswith("skipped"):
        stats["prproj_skipped"] = True
        console.print(f"[dim]Project file already on HDD:[/dim] {dest}")
    else:
        stats["failed"] += 1
        console.print(f"[red]Project file backup failed:[/red] {msg}")


def backup_proxies_to_hdd(
    cfg: dict,
    folder_name: str,
    *,
    dry_run: bool = False,
    pickup_proxies_folder: str | None = None,
) -> dict:
    """
    Copy SSD proxies and .prproj to hdd_backup.

    Primary run: Video/Proxies/
    Pick-up run: Pickup Proxies/ or Pickup Proxies #N/ at project root.
    """
    verify = cfg.get("ingest", {}).get("verify_checksum", True)
    ssd_root, hdd_root = project_root(cfg, folder_name)

    from .pickup import load_pickup_run

    pickup = load_pickup_run(ssd_root)
    if pickup and not pickup_proxies_folder:
        pickup_proxies_folder = pickup.final_proxies_folder

    ssd_proxy_root, sources = _collect_ssd_proxy_files(
        cfg, folder_name, pickup_proxies_folder=pickup_proxies_folder
    )

    if pickup_proxies_folder:
        hdd_proxy = hdd_root / pickup_proxies_folder
        hdd_proxy.mkdir(parents=True, exist_ok=True)
    else:
        hdd_proxy = _hdd_proxies_path(cfg, hdd_root)

    stats = {
        "copied": 0,
        "skipped": 0,
        "failed": 0,
        "bytes": 0,
        "ssd_proxies": str(ssd_proxy_root),
        "hdd_proxies": str(hdd_proxy),
    }

    if not sources:
        console.print("[yellow]No proxy files on SSD to back up.[/yellow]")
        console.print(f"  Looked at: {ssd_proxy_root}")
        console.print(
            "  Wait for Media Encoder to finish, then run:\n"
            f"    python main.py backup-proxies --number ..."
        )
        stats["skipped_reason"] = "no_files"
        _backup_prproj_to_hdd(cfg, ssd_root, hdd_root, verify=verify, dry_run=dry_run, stats=stats)
        return stats

    console.print("\n[bold]Backing up proxies + project SSD → HDD[/bold]")
    console.print(f"  SSD ({ssd_root.drive or 'project'}): {ssd_root}")
    console.print(f"  From: {ssd_proxy_root} ({len(sources)} file(s))")
    console.print(f"  HDD ({hdd_root.drive or 'project'}): {hdd_root}")
    console.print(f"  To:   {hdd_proxy}\n")

    if dry_run:
        console.print(f"[yellow]Dry run — would copy {len(sources)} proxy file(s).[/yellow]")
        stats["would_copy"] = len(sources)
        _backup_prproj_to_hdd(cfg, ssd_root, hdd_root, verify=verify, dry_run=dry_run, stats=stats)
        return stats

    # Fast path: canonical Video/Proxies layout only
    use_robocopy = (
        not pickup_proxies_folder
        and ssd_proxy_root.resolve() == proxies_path(cfg, folder_name, destination="ssd").resolve()
        and len(sources) == len(_proxy_files_under(ssd_proxy_root))
        and _robocopy_proxies(ssd_proxy_root, hdd_proxy)
    )
    if use_robocopy:
        for path in _proxy_files_under(hdd_proxy):
            stats["bytes"] += path.stat().st_size
        stats["copied"] = len(_proxy_files_under(hdd_proxy))
        console.print(f"[green]Robocopy mirror complete.[/green] {stats['copied']} proxy file(s) on HDD")
        _backup_prproj_to_hdd(cfg, ssd_root, hdd_root, verify=verify, dry_run=dry_run, stats=stats)
        console.print(f"  Proxy data: {format_bytes(stats['bytes'])}")
        return stats

    hdd_proxy.mkdir(parents=True, exist_ok=True)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Proxies → HDD...", total=len(sources))
        for src in sources:
            rel = src.relative_to(ssd_proxy_root)
            dest = hdd_proxy / rel
            progress.update(task, description=str(rel)[:50])
            ok, msg = _copy_file(src, dest, verify, dry_run=False)
            if ok:
                stats["copied"] += 1
                stats["bytes"] += src.stat().st_size
            elif msg.startswith("skipped"):
                stats["skipped"] += 1
            else:
                stats["failed"] += 1
                console.print(f"[red]{rel}: {msg}[/red]")
            progress.advance(task)

    _backup_prproj_to_hdd(cfg, ssd_root, hdd_root, verify=verify, dry_run=dry_run, stats=stats)

    console.print(f"\n[green]SSD → HDD backup complete.[/green]")
    console.print(f"  Proxies copied:  {stats['copied']}")
    console.print(f"  Proxies skipped: {stats['skipped']} (already on HDD)")
    if stats.get("prproj_copied"):
        console.print("  Project file:  copied")
    elif stats.get("prproj_skipped"):
        console.print("  Project file:  already on HDD")
    if stats["failed"]:
        console.print(f"  [red]Failed:  {stats['failed']}[/red]")
    if stats["copied"] == 0 and stats["skipped"] == 0 and not stats.get("prproj_copied"):
        console.print(
            "[red]Nothing copied. Check hdd_backup drive letter in config.yaml "
            "and that the HDD is plugged in.[/red]"
        )
    console.print(f"  Data:    {format_bytes(stats['bytes'])}")

    return stats
