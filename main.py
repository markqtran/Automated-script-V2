#!/usr/bin/env python3
"""
Footage workflow automation — daily ingest through final backup.

Usage:
  python main.py new-project --number 003  # Create folders from [01] Scripts
  python main.py list-scripts             # Show all script numbers/titles
  python main.py workflow --number 003       # Full pipeline: folders + ingest + Premiere script
  python main.py watch-backup --number 003   # Wait for proxies → copy SSD → HDD
  python main.py watch-upload --number 003   # Wait → HDD backup → Drive upload
  python main.py backup-proxies --number 003 # Copy Video/Proxies now (if already done)
  python main.py ingest             # Ingest without compare report
  python main.py proxies --folder   # Create FFmpeg proxies
  python main.py upload-drive       # Upload proxies + project to Google Drive
  python main.py audit-assets       # Find files not backed up on HDD
  python main.py mirror             # Mirror HDD1 to HDD2
  python main.py finalize           # Audit + copy missing + mirror
"""

from __future__ import annotations

import sys
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
from src.proxy_backup import backup_proxies_to_hdd
from src.watch_upload import watch_and_backup_hdd, watch_and_upload
from src.workflow import run_full_workflow, run_phase_one, run_phase_two

console = Console()


def _cfg_path(config: str) -> Path:
    return Path(config)


@click.group()
@click.option(
    "--config",
    "-c",
    default=None,
    help="Path to config file (default: config.yaml or AppData)",
)
@click.pass_context
def cli(ctx: click.Context, config: str | None) -> None:
    """Automate your filming to edit to backup workflow."""
    ctx.ensure_object(dict)
    try:
        ctx.obj["cfg"] = load_config(_cfg_path(config) if config else None)
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1)


@cli.command("list-scripts")
@click.option("--refresh", is_flag=True, help="Refresh script list from Google Drive")
@click.pass_context
def cmd_list_scripts(ctx: click.Context, refresh: bool) -> None:
    """List all scripts from Google Drive [01] Scripts folder."""
    list_available_scripts(ctx.obj["cfg"], refresh=refresh)


@cli.command("list-proxy-presets")
@click.pass_context
def cmd_list_proxy_presets(ctx: click.Context) -> None:
    """List .epr presets on this PC (for proxy automation setup)."""
    from src.premiere_proxy import (
        resolve_encode_preset_path,
        resolve_proxy_preset_path,
        top_scored_presets,
    )

    cfg = ctx.obj["cfg"]
    ingest_path = resolve_proxy_preset_path(cfg)
    encode_path = resolve_encode_preset_path(cfg)

    console.print("\n[bold]Configured proxy presets[/bold]")
    console.print(f"  Ingest: {ingest_path or '(not set)'}")
    console.print(f"  Encode: {encode_path or '(not set)'}")

    if ingest_path and encode_path and ingest_path == encode_path:
        console.print(
            "\n[yellow]Encode must NOT be an IngestPresets file.[/yellow] "
            "Automation uses encodeFile → Video/Proxies/ on the SSD."
        )

    ingest_rows = top_scored_presets(ingest=True)
    encode_rows = top_scored_presets(ingest=False)

    if ingest_rows:
        console.print("\n[bold]Top ingest presets[/bold] (Create Proxies / manual)\n")
        for score, path in ingest_rows:
            console.print(f"  [{score:2d}] {path}")

    if encode_rows:
        console.print("\n[bold]Top encode presets[/bold] (auto proxy queue — NOT IngestPresets)\n")
        for score, path in encode_rows:
            console.print(f"  [{score:2d}] {path}")
    else:
        console.print("\n[yellow]No export preset auto-detected on this PC.[/yellow]")

    console.print("\n[bold]Required for empty Video/Proxies fix[/bold]")
    console.print("  1. Media Encoder → + → [bold]Create Preset[/bold] (not Ingest)")
    console.print("     QuickTime · ProRes QuickTime Proxy · Quarter")
    console.print("  2. Reveal Preset File → copy to:")
    console.print("     templates/NDP_Proxy_Encode.epr")
    console.print("  3. Re-run: python main.py list-proxy-presets")
    console.print("     Encode should show templates/NDP_Proxy_Encode.epr")
    console.print("\n[dim]Optional: premiere.proxy_encode_preset in config.yaml[/dim]\n")


@cli.command("install-premiere")
@click.pass_context
def cmd_install_premiere(ctx: click.Context) -> None:
    """
    One-time: enable Premiere to run automate_premiere.jsx on launch.
    Creates extendscriptprqe.txt next to Adobe Premiere Pro.exe (may need Administrator).
    """
    from src.premiere_launch import install_premiere_cli_scripting

    ok = install_premiere_cli_scripting(ctx.obj["cfg"])
    raise SystemExit(0 if ok else 1)


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


@cli.command()
@click.option("--number", "-n", required=True, help="3-digit script number (e.g. 003)")
@click.option("--refresh", is_flag=True, help="Refresh script list from Google Drive")
@click.option("--skip-ingest", is_flag=True, help="Skip SD card copy (folders + Premiere only)")
@click.option("--no-premiere", is_flag=True, help="Do not launch Premiere")
@click.option(
    "--wait-backup",
    is_flag=True,
    help="After proxies finish, copy Video/Proxies from SSD to hdd_backup",
)
@click.option("--watch-upload", is_flag=True, help="Wait for proxies, HDD backup, then upload to Drive")
@click.option("--dry-run", is_flag=True)
@click.pass_context
def workflow(
    ctx: click.Context,
    number: str,
    refresh: bool,
    skip_ingest: bool,
    no_premiere: bool,
    wait_backup: bool,
    watch_upload: bool,
    dry_run: bool,
) -> None:
    """
    Full workflow matching your Premiere process:
    [01] Scripts name -> SSD folder + Video/ -> SD ingest -> Premiere JSX -> optional Drive upload.
    """
    run_full_workflow(
        ctx.obj["cfg"],
        number,
        refresh=refresh,
        skip_ingest=skip_ingest,
        open_premiere=not no_premiere,
        wait_backup=wait_backup,
        watch_upload=watch_upload,
        dry_run=dry_run,
    )


@cli.command("workflow-phase1")
@click.option("--number", "-n", required=True, help="3-digit script number (e.g. 003)")
@click.option("--refresh", is_flag=True, help="Refresh script list from Google Drive")
@click.option("--skip-ingest", is_flag=True, help="Skip SD card copy (folders + Premiere only)")
@click.option("--no-premiere", is_flag=True, help="Do not launch Premiere")
@click.option("--dry-run", is_flag=True)
@click.pass_context
def cmd_workflow_phase1(
    ctx: click.Context,
    number: str,
    refresh: bool,
    skip_ingest: bool,
    no_premiere: bool,
    dry_run: bool,
) -> None:
    """
    Phase 1: create project, ingest SD to SSD/HDD, import in Premiere.
    Checks for duplicate/conflicting files before copying.
    """
    run_phase_one(
        ctx.obj["cfg"],
        number,
        refresh=refresh,
        skip_ingest=skip_ingest,
        open_premiere=not no_premiere,
        dry_run=dry_run,
    )


@cli.command("workflow-phase2")
@click.option("--number", "-n", required=True, help="3-digit script number (e.g. 003)")
@click.option("--timeout", default=180, help="Max minutes to wait for proxies on SSD")
@click.option("--dry-run", is_flag=True)
@click.pass_context
def cmd_workflow_phase2(
    ctx: click.Context,
    number: str,
    timeout: int,
    dry_run: bool,
) -> None:
    """
    Phase 2: wait for proxies, back up to HDD, upload to Google Drive.
    """
    run_phase_two(
        ctx.obj["cfg"],
        number,
        timeout_minutes=timeout,
        dry_run=dry_run,
    )


@cli.command("watch-backup")
@click.option("--number", "-n", required=True, help="3-digit script number")
@click.option("--timeout", default=180, help="Max minutes to wait for proxies on SSD")
@click.option("--dry-run", is_flag=True)
@click.pass_context
def cmd_watch_backup(
    ctx: click.Context,
    number: str,
    timeout: int,
    dry_run: bool,
) -> None:
    """Wait for Media Encoder on SSD, then copy Video/Proxies and .prproj to HDD."""
    watch_and_backup_hdd(
        ctx.obj["cfg"],
        number,
        timeout_minutes=timeout,
        dry_run=dry_run,
    )


@cli.command("watch-upload")
@click.option("--number", "-n", required=True, help="3-digit script number")
@click.option("--timeout", default=180, help="Max minutes to wait for proxies")
@click.option("--dry-run", is_flag=True)
@click.pass_context
def cmd_watch_upload(
    ctx: click.Context,
    number: str,
    timeout: int,
    dry_run: bool,
) -> None:
    """Wait for proxies, back up SSD→HDD, then upload Proxies + .prproj to Drive."""
    watch_and_upload(
        ctx.obj["cfg"],
        number,
        timeout_minutes=timeout,
        dry_run=dry_run,
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
        console.print(f"  5. HDD backup: python main.py watch-backup --number {number}")
        console.print(f"  6. Drive:      python main.py upload-drive --number {number}")
    else:
        console.print(f"  5. HDD backup: python main.py backup-proxies -f \"{stats['ssd_path']}\"")


@cli.command()
@click.option("--folder", "-f", required=True, help="Footage folder on SSD (date folder)")
@click.option("--dry-run", is_flag=True)
@click.pass_context
def proxies(ctx: click.Context, folder: str, dry_run: bool) -> None:
    """Generate FFmpeg proxy files for assistant editor."""
    create_proxies(folder, ctx.obj["cfg"], dry_run=dry_run)


@cli.command("backup-proxies")
@click.option("--number", "-n", default=None, help="3-digit script number")
@click.option("--folder", "-f", default=None, help="SSD project folder (e.g. F:\\[003] Title)")
@click.option("--dry-run", is_flag=True)
@click.pass_context
def cmd_backup_proxies(
    ctx: click.Context,
    number: str | None,
    folder: str | None,
    dry_run: bool,
) -> None:
    """Copy Video/Proxies and .prproj from SSD (Soju) to matching folder on hdd_backup."""
    cfg = ctx.obj["cfg"]
    if number:
        folder_name = resolve_project_folder(cfg, number)
    elif folder:
        folder_name = Path(folder).name
    else:
        raise click.UsageError("Provide --number or --folder")
    backup_proxies_to_hdd(cfg, folder_name, dry_run=dry_run)


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
    """Back up proxies to HDD, then upload Proxies + .prproj to Google Drive."""
    cfg = ctx.obj["cfg"]
    folder_name: str | None = None
    if number:
        folder_name = resolve_project_folder(cfg, number)
        folder = str(project_root(cfg, folder_name)[0])
        console.print(f"[bold]Project folder:[/bold] {folder}")
    if not folder:
        raise click.UsageError("Provide --folder or --number")
    if folder_name is None:
        folder_name = Path(folder).name
    from src.pickup import load_pickup_run, pickup_drive_upload_subpath, pickup_proxies_path

    ssd_path = project_root(cfg, folder_name)[0]
    pickup = load_pickup_run(ssd_path)
    backup_proxies_to_hdd(cfg, folder_name, dry_run=dry_run)
    upload_kwargs: dict = {}
    if pickup:
        upload_kwargs["proxies_path"] = pickup_proxies_path(ssd_path, pickup)
        upload_kwargs["proxies_drive_subpath"] = pickup_drive_upload_subpath(cfg, pickup.number)
    upload_to_drive(
        folder,
        cfg,
        project_file=project,
        dry_run=dry_run,
        **upload_kwargs,
    )


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
    if len(sys.argv) == 1:
        from src.gui.app import run_gui

        run_gui()
    else:
        cli()
