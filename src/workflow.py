"""Full day workflow: script lookup -> folders -> ingest -> Premiere -> optional upload."""

from __future__ import annotations

from rich.console import Console

from .ingest import ingest_footage
from .new_project import setup_new_project
from .premiere_jsx import write_premiere_setup_script
from .premiere_launch import launch_premiere_automation
from .project_paths import project_root, video_folder_name
from .scripts import get_script_by_number, resolve_project_folder
from .sd_compare import compare_sd_cards_from_config, print_compare_report
from .watch_upload import watch_and_upload

console = Console()


def run_full_workflow(
    cfg: dict,
    number: str,
    *,
    refresh: bool = False,
    skip_ingest: bool = False,
    open_premiere: bool = True,
    watch_upload: bool = False,
    dry_run: bool = False,
) -> None:
    """
    1. Create [###] folder from [01] Scripts on Google Drive
    2. Create Video/ on SSD + HDD
    3. Copy SD card (PRIVATE/M4ROOT/CLIP...) into Video/
    4. Write automate_premiere.jsx + open Premiere
    5. Optionally wait for Proxies and upload to Drive
    """
    entry = get_script_by_number(cfg, number, refresh=refresh)
    folder_name = entry.folder_name

    console.print(f"\n[bold]Full workflow — [{entry.number}] {entry.title}[/bold]\n")

    # Step 1 — project folders on SSD
    setup_new_project(
        cfg,
        number,
        refresh=False,
        dry_run=dry_run,
        open_premiere=False,
    )
    if dry_run:
        return

    ssd_path, _ = project_root(cfg, folder_name)
    prproj_path = ssd_path / f"{folder_name}.prproj"

    # Step 2 — ingest SD -> Video/
    if not skip_ingest:
        compare = compare_sd_cards_from_config(
            cfg, cfg.get("footage_extensions", [".mp4", ".mov"])
        )
        print_compare_report(compare)
        ingest_footage(cfg, compare=compare, shoot_date=folder_name, dry_run=False)

    # Step 3 — Premiere: auto-create project on SSD, import Video/
    jsx_path = write_premiere_setup_script(
        cfg, ssd_path, folder_name, prproj_path, script_number=entry.number
    )
    console.print(f"\n[bold]Premiere automation:[/bold] {jsx_path}")

    if open_premiere:
        launch_premiere_automation(
            cfg,
            jsx_path=jsx_path,
            prproj_path=prproj_path,
            project_folder=ssd_path,
        )
        console.print(
            "\n[dim]Premiere should open, create [bold]" + folder_name + "[/bold], "
            "set scratch disks to the SSD folder, and import Video/.[/dim]"
        )
        console.print("[dim]Close Premiere first if it was already running.[/dim]")

    console.print("\n[bold]Proxy settings (save in project template once):[/bold]")
    console.print("  Quarter | ProRes QuickTime Proxy | Proxy Icon | Next to Original, Proxy folder")

    if watch_upload:
        watch_and_upload(cfg, number, dry_run=dry_run)
    else:
        console.print(f"\n[bold]When proxies finish:[/bold] python main.py upload-drive --number {number}")
        console.print(f"  Or: python main.py watch-upload --number {number}")
