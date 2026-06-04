#!/usr/bin/env python3
"""
Footage workflow automation — daily ingest through final backup.

Usage:
  python main.py new-project --number 003  # Create folders from [01] Scripts
  python main.py list-scripts             # Show all script numbers/titles
  python main.py daily --number 003       # Ingest into the matching project folder
  python main.py ingest             # Ingest without compare report
  python main.py proxies --folder   # Create FFmpeg proxies
  python main.py upload-drive       # Upload proxies + project to Google Drive
  python main.py audit-assets       # Find files not backed up on HDD
  python main.py mirror             # Mirror HDD1 to HDD2
  python main.py finalize           # Audit + copy missing + mirror
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import click
from rich.console import Console

from src.asset_audit import audit_assets
from src.config_loader import load_config
from src.gdrive import upload_to_drive
from src.ingest import ingest_footage
from src.mirror import mirror_backup
from src.new_project import list_available_scripts, setup_new_project
from src.proxies import create_proxies
from src.project_paths import project_root
from src.scripts import resolve_project_folder
from src.sd_compare import compare_sd_cards_from_config, print_compare_report

console = Console()


def _cfg_path(config: str) -> Path:
    return Path(config)


@click.group()
@click.option("--config", "-c", default="config.yaml", help="Path to config file")
@click.pass_context
def cli(ctx: click.Context, config: str) -> None:
    """Automate your filming to edit to backup workflow."""
    ctx.ensure_object(dict)
    try:
        ctx.obj["cfg"] = load_config(_cfg_path(config))
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1)


@cli.command("list-scripts")
@click.option("--refresh", is_flag=True, help="Refresh script list from Google Drive")
@click.pass_context
def cmd_list_scripts(ctx: click.Context, refresh: bool) -> None:
    """List all scripts from Google Drive [01] Scripts folder."""
    list_available_scripts(ctx.obj["cfg"], refresh=refresh)


@cli.command("new-project")
@click.option("--number", "-n", required=True, help="3-digit script number (e.g. 003)")
@click.option("--refresh", is_flag=True, help="Refresh script list from Google Drive")
@click.option("--open-premiere", is_flag=True, help="Launch Adobe Premiere Pro after creating folders")
@click.option("--dry-run", is_flag=True)
@click.pass_context
def cmd_new_project(
    ctx: click.Context,
    number: str,
    refresh: bool,
    open_premiere: bool,
    dry_run: bool,
) -> None:
    """Create project folders named after a script (e.g. 003 -> [003] Teaching an Ipad Kid)."""
    setup_new_project(
        ctx.obj["cfg"],
        number,
        refresh=refresh,
        dry_run=dry_run,
        open_premiere=open_premiere,
    )


@cli.command("compare-sd")
@click.pass_context
def cmd_compare_sd(ctx: click.Context) -> None:
    """Compare primary and backup SD cards."""
    cfg = ctx.obj["cfg"]
    result = compare_sd_cards_from_config(
        cfg,
        cfg.get("footage_extensions", [".mp4", ".mov"]),
    )
    print_compare_report(result)


@cli.command()
@click.option("--date", "shoot_date", default=None, help="Project folder name or YYYY-MM-DD")
@click.option("--number", "-n", default=None, help="3-digit script number (looks up folder name from Drive)")
@click.option("--dry-run", is_flag=True, help="Show what would happen without copying")
@click.pass_context
def ingest(
    ctx: click.Context,
    shoot_date: str | None,
    number: str | None,
    dry_run: bool,
) -> None:
    """Copy footage from SD cards to SSD and HDD."""
    cfg = ctx.obj["cfg"]
    if number:
        shoot_date = resolve_project_folder(cfg, number)
        console.print(f"[bold]Project folder:[/bold] {shoot_date}")
    compare = compare_sd_cards_from_config(
        cfg,
        cfg.get("footage_extensions", [".mp4", ".mov"]),
    )
    print_compare_report(compare)

    if not compare.single_card and not compare.in_sync:
        if not click.confirm("Cards differ. Continue ingest from both cards?", default=True):
            raise SystemExit(0)

    ingest_footage(cfg, compare=compare, shoot_date=shoot_date, dry_run=dry_run)


@cli.command()
@click.option("--date", "shoot_date", default=None, help="Project folder name or YYYY-MM-DD")
@click.option("--number", "-n", default=None, help="3-digit script number (looks up folder name from Drive)")
@click.option("--dry-run", is_flag=True)
@click.option("--skip-ingest", is_flag=True, help="Compare only, skip copy")
@click.pass_context
def daily(
    ctx: click.Context,
    shoot_date: str | None,
    number: str | None,
    dry_run: bool,
    skip_ingest: bool,
) -> None:
    """End-of-day workflow: compare SD cards and ingest to SSD + HDD."""
    cfg = ctx.obj["cfg"]
    if number:
        shoot_date = resolve_project_folder(cfg, number)
    else:
        date_fmt = cfg["ingest"].get("date_folder_format", "%Y-%m-%d")
        shoot_date = shoot_date or datetime.now().strftime(date_fmt)

    console.print(f"[bold]Daily workflow — {shoot_date}[/bold]")

    compare = compare_sd_cards_from_config(
        cfg,
        cfg.get("footage_extensions", [".mp4", ".mov"]),
    )
    print_compare_report(compare)

    if skip_ingest:
        return

    if not compare.single_card and not compare.in_sync:
        console.print(
            "\n[yellow]Tip: One card has extra footage (backup card inserted late?). "
            "Ingest will merge files from both cards.[/yellow]"
        )

    stats = ingest_footage(cfg, compare=compare, shoot_date=shoot_date, dry_run=dry_run)

    console.print("\n[bold]Next steps in Adobe Premiere Pro:[/bold]")
    console.print(f"  1. Open your .prproj on the SSD (scratch disks = SSD)")
    console.print(f"  2. Import this folder into Media: {stats['video_path']}")
    console.print("  3. Right-click clips > Proxy > Create Proxies (ProRes / Quarter / your preset)")
    console.print("  4. Wait for Media Encoder to finish")
    if number:
        console.print(f"  5. Upload: python main.py upload-drive --number {number}")
    else:
        console.print(f"  5. Upload: python main.py upload-drive -f \"{stats['ssd_path']}\"")


@cli.command()
@click.option("--folder", "-f", required=True, help="Footage folder on SSD (date folder)")
@click.option("--dry-run", is_flag=True)
@click.pass_context
def proxies(ctx: click.Context, folder: str, dry_run: bool) -> None:
    """Generate FFmpeg proxy files for assistant editor."""
    create_proxies(folder, ctx.obj["cfg"], dry_run=dry_run)


@cli.command("upload-drive")
@click.option("--folder", "-f", default=None, help="Project folder on SSD, e.g. F:\\[003] Title")
@click.option("--number", "-n", default=None, help="3-digit script number (finds project folder)")
@click.option("--project", "-p", default=None, help="Path to .prproj file")
@click.option("--dry-run", is_flag=True)
@click.pass_context
def cmd_upload_drive(
    ctx: click.Context,
    folder: str | None,
    number: str | None,
    project: str | None,
    dry_run: bool,
) -> None:
    """Upload Video/Proxies folder and .prproj to Google Drive (not original footage)."""
    cfg = ctx.obj["cfg"]
    if number:
        name = resolve_project_folder(cfg, number)
        folder = str(project_root(cfg, name)[0])
        console.print(f"[bold]Project folder:[/bold] {folder}")
    if not folder:
        raise click.UsageError("Provide --folder or --number")
    upload_to_drive(folder, cfg, project_file=project, dry_run=dry_run)


@cli.command("audit-assets")
@click.option("--project-folder", "-p", required=True, help="Project folder on SSD")
@click.option("--hdd-folder", "-h", default=None, help="Matching folder on HDD (auto if omitted)")
@click.option("--copy", "copy_missing", is_flag=True, help="Copy missing files to HDD")
@click.option("--dry-run", is_flag=True)
@click.pass_context
def cmd_audit_assets(
    ctx: click.Context,
    project_folder: str,
    hdd_folder: str | None,
    copy_missing: bool,
    dry_run: bool,
) -> None:
    """Audit project assets against HDD backup."""
    cfg = ctx.obj["cfg"]
    if hdd_folder is None:
        proj = Path(project_folder)
        hdd_folder = str(Path(cfg["destinations"]["hdd_backup"]) / proj.name)
    audit_assets(project_folder, hdd_folder, cfg, copy_missing=copy_missing, dry_run=dry_run)


@cli.command()
@click.option("--dry-run", is_flag=True)
@click.pass_context
def mirror(ctx: click.Context, dry_run: bool) -> None:
    """Mirror primary HDD backup to secondary HDD."""
    mirror_backup(ctx.obj["cfg"], dry_run=dry_run)


@cli.command()
@click.option("--project-folder", "-p", required=True, help="Completed project folder on SSD")
@click.option("--hdd-folder", "-h", default=None, help="Matching folder on primary HDD")
@click.option("--dry-run", is_flag=True)
@click.option("--skip-mirror", is_flag=True, help="Skip mirroring to second HDD")
@click.pass_context
def finalize(ctx: click.Context, project_folder: str, hdd_folder: str | None, dry_run: bool, skip_mirror: bool) -> None:
    """End-of-project: audit assets, copy missing to HDD, mirror to second HDD."""
    cfg = ctx.obj["cfg"]
    if hdd_folder is None:
        proj = Path(project_folder)
        hdd_folder = str(Path(cfg["destinations"]["hdd_backup"]) / proj.name)

    console.print("[bold]Finalize project — asset audit[/bold]")
    result = audit_assets(
        project_folder,
        hdd_folder,
        cfg,
        copy_missing=True,
        dry_run=dry_run,
    )

    if not result["in_sync"] and not dry_run:
        console.print("\n[green]Missing files copied to primary HDD.[/green]")

    if not skip_mirror:
        console.print("\n[bold]Mirroring primary HDD to secondary HDD[/bold]")
        mirror_backup(cfg, dry_run=dry_run)
    else:
        console.print("\n[dim]Mirror skipped (--skip-mirror).[/dim]")


if __name__ == "__main__":
    cli()
