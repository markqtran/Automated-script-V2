"""Full day workflow: script lookup -> folders -> ingest -> Premiere -> optional upload."""

from __future__ import annotations

from rich.console import Console

from .ingest import ingest_footage
from .new_project import setup_new_project
from .pickup import detect_primary_run_exists, prepare_pickup_run, prompt_pickup_run
from .premiere_jsx import write_premiere_setup_script
from .premiere_launch import launch_premiere_automation
from .premiere_proxy import proxy_subfolder_name
from .project_paths import project_root
from .scripts import get_script_by_number
from .sd_compare import compare_sd_cards_from_config, print_compare_report
from .watch_upload import watch_and_backup_hdd, watch_and_upload

console = Console()


def run_full_workflow(
    cfg: dict,
    number: str,
    *,
    refresh: bool = False,
    skip_ingest: bool = False,
    open_premiere: bool = True,
    wait_backup: bool = False,
    watch_upload: bool = False,
    dry_run: bool = False,
) -> None:
    """
    1. Create [###] folder from [01] Scripts (or pick-up subfolder on re-run)
    2. Ingest SD -> Video/ (first run) or Pick Up Shots #N/ (re-run)
    3. Premiere JSX + optional launch
    4. Optionally wait for proxies, rename pick-up Proxies, HDD backup, Drive upload
    """
    entry = get_script_by_number(cfg, number, refresh=refresh)
    folder_name = entry.folder_name
    pickup_run = None

    console.print(f"\n[bold]Full workflow — [{entry.number}] {entry.title}[/bold]\n")

    ssd_path, hdd_path = project_root(cfg, folder_name)

    if detect_primary_run_exists(cfg, folder_name):
        if not prompt_pickup_run(cfg, folder_name):
            raise SystemExit(0)
        pickup_run = prepare_pickup_run(cfg, folder_name)
        ssd_path.mkdir(parents=True, exist_ok=True)
        hdd_path.mkdir(parents=True, exist_ok=True)
    else:
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

    if not skip_ingest:
        compare = compare_sd_cards_from_config(
            cfg, cfg.get("footage_extensions", [".mp4", ".mov"])
        )
        print_compare_report(compare)
        ingest_footage(
            cfg,
            compare=compare,
            shoot_date=folder_name,
            pickup_subfolder=pickup_run.shots_folder if pickup_run else None,
            dry_run=False,
        )

    import_dir = None
    proxies_override = None
    import_label = ""
    if pickup_run:
        import_dir = ssd_path / pickup_run.shots_folder
        proxies_override = import_dir / proxy_subfolder_name(cfg)
        import_label = pickup_run.shots_folder

    jsx_path = write_premiere_setup_script(
        cfg,
        ssd_path,
        folder_name,
        prproj_path,
        script_number=entry.number,
        import_dir=import_dir,
        proxies_dir_override=proxies_override,
        import_label=import_label,
        continue_existing_project=pickup_run is not None,
    )
    console.print(f"\n[bold]Premiere automation:[/bold] {jsx_path}")

    from .prproj_ingest import disable_premiere_ingest_settings

    if pickup_run and not prproj_path.is_file():
        console.print(
            f"\n[red]Missing project file for pick-up run:[/red] {prproj_path}\n"
            "  Complete a first workflow for this script, save the .prproj on the SSD, then re-run."
        )
        raise SystemExit(1)

    if prproj_path.is_file():
        disable_premiere_ingest_settings(prproj_path)

    if open_premiere:
        launch_premiere_automation(
            cfg,
            jsx_path=jsx_path,
            prproj_path=prproj_path,
            project_folder=ssd_path,
        )
        if pickup_run:
            console.print(
                f"\n[dim]Premiere will [bold]re-open[/bold] {prproj_path.name}, "
                f"import new clips from {import_label}/, save, and queue proxies.[/dim]"
            )
        else:
            target = import_label or "Video"
            console.print(
                f"\n[dim]Premiere should open project [bold]{folder_name}[/bold], "
                f"import {target}/, and queue proxies.[/dim]"
            )
        console.print(
            "[dim]Premiere reopens automatically when already running (save open projects first).[/dim]"
        )

    console.print("\n[bold]Proxy settings (save in project template once):[/bold]")
    console.print("  Quarter | ProRes QuickTime Proxy | Proxy Icon | Next to Original, Proxy folder")

    if watch_upload:
        watch_and_upload(cfg, number, dry_run=dry_run)
    elif wait_backup:
        watch_and_backup_hdd(cfg, number, dry_run=dry_run)
    else:
        console.print(f"\n[bold]When proxies finish on SSD (Soju):[/bold]")
        console.print(f"  python main.py watch-backup --number {number}")
        if pickup_run:
            console.print(
                f"  (Pick-up #{pickup_run.number} → "
                f"{pickup_run.working_proxies_folder}/ on HDD, "
                f"Pickup Proxies #{pickup_run.number}/Proxies/ on Drive)"
            )
        console.print(f"  Or: python main.py workflow --number {number} --wait-backup")
        console.print(f"  Drive: python main.py watch-upload --number {number}")
