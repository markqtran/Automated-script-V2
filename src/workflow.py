"""Full day workflow: script lookup -> folders -> ingest -> Premiere -> optional upload."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rich.console import Console

from .ingest import ingest_footage
from .ingest_plan import build_ingest_plan, confirm_ingest_plan
from .interactive import user_confirm
from .new_project import setup_new_project
from .pickup import detect_primary_run_exists, prepare_pickup_run, prompt_pickup_run
from .premiere_jsx import write_premiere_setup_script
from .premiere_launch import launch_premiere_automation
from .premiere_proxy import proxy_subfolder_name
from .project_paths import project_root
from .scripts import ScriptEntry, get_script_by_number
from .sd_compare import compare_sd_cards_from_config, print_compare_report
from .watch_upload import watch_and_upload

console = Console()


@dataclass
class WorkflowContext:
    entry: ScriptEntry
    folder_name: str
    pickup_run: object | None
    ssd_path: Path
    prproj_path: Path


def _setup_project_for_number(
    cfg: dict,
    number: str,
    *,
    refresh: bool = False,
    dry_run: bool = False,
) -> WorkflowContext:
    entry = get_script_by_number(cfg, number, refresh=refresh)
    folder_name = entry.folder_name
    pickup_run = None

    if detect_primary_run_exists(cfg, folder_name):
        if not prompt_pickup_run(cfg, folder_name):
            raise SystemExit(0)
        pickup_run = prepare_pickup_run(cfg, folder_name)
        ssd_path, hdd_path = project_root(cfg, folder_name)
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
            ssd_path, _ = project_root(cfg, folder_name)
            return WorkflowContext(entry, folder_name, None, ssd_path, ssd_path / f"{folder_name}.prproj")

    ssd_path, _ = project_root(cfg, folder_name)
    prproj_path = ssd_path / f"{folder_name}.prproj"
    return WorkflowContext(entry, folder_name, pickup_run, ssd_path, prproj_path)


def _ingest_with_plan(
    cfg: dict,
    ctx: WorkflowContext,
    *,
    dry_run: bool = False,
) -> None:
    compare = compare_sd_cards_from_config(
        cfg, cfg.get("footage_extensions", [".mp4", ".mov"])
    )
    print_compare_report(compare)

    if not compare.single_card and not compare.in_sync:
        if not user_confirm(
            "Primary and backup SD cards differ.\nContinue ingest from both cards?",
            default=True,
        ):
            raise SystemExit(0)

    pickup_sub = ctx.pickup_run.shots_folder if ctx.pickup_run else None
    plan = build_ingest_plan(
        cfg,
        compare,
        ctx.folder_name,
        pickup_subfolder=pickup_sub,
    )
    if not confirm_ingest_plan(plan):
        raise SystemExit(0)

    ingest_footage(
        cfg,
        compare=compare,
        shoot_date=ctx.folder_name,
        pickup_subfolder=pickup_sub,
        dry_run=dry_run,
        plan=plan,
    )


def _premiere_setup(
    cfg: dict,
    ctx: WorkflowContext,
    *,
    open_premiere: bool,
    queue_proxies: bool | None,
) -> None:
    import_dir = None
    proxies_override = None
    import_label = ""
    if ctx.pickup_run:
        import_dir = ctx.ssd_path / ctx.pickup_run.shots_folder
        proxies_override = import_dir / proxy_subfolder_name(cfg)
        import_label = ctx.pickup_run.shots_folder

    jsx_path = write_premiere_setup_script(
        cfg,
        ctx.ssd_path,
        ctx.folder_name,
        ctx.prproj_path,
        script_number=ctx.entry.number,
        import_dir=import_dir,
        proxies_dir_override=proxies_override,
        import_label=import_label,
        continue_existing_project=ctx.pickup_run is not None,
        queue_proxies=queue_proxies,
    )
    console.print(f"\n[bold]Premiere automation:[/bold] {jsx_path}")

    from .prproj_ingest import disable_premiere_ingest_settings

    if ctx.pickup_run and not ctx.prproj_path.is_file():
        console.print(
            f"\n[red]Missing project file for pick-up run:[/red] {ctx.prproj_path}\n"
            "  Complete Phase 1 for this script first, save the .prproj on the SSD, then re-run."
        )
        raise SystemExit(1)

    if ctx.prproj_path.is_file():
        disable_premiere_ingest_settings(ctx.prproj_path)

    if open_premiere:
        launch_premiere_automation(
            cfg,
            jsx_path=jsx_path,
            prproj_path=ctx.prproj_path,
            project_folder=ctx.ssd_path,
        )
        if ctx.pickup_run:
            console.print(
                f"\n[dim]Premiere will re-open {ctx.prproj_path.name}, "
                f"import new clips from {import_label}/, and save.[/dim]"
            )
        else:
            target = import_label or "Video"
            console.print(
                f"\n[dim]Premiere should open [bold]{ctx.folder_name}[/bold], "
                f"import {target}/, and save the project.[/dim]"
            )
        console.print(
            "[dim]Premiere reopens automatically when already running (save open projects first).[/dim]"
        )


def run_phase_one(
    cfg: dict,
    number: str,
    *,
    refresh: bool = False,
    skip_ingest: bool = False,
    open_premiere: bool = True,
    dry_run: bool = False,
) -> None:
    """
    Phase 1 — project setup, SD ingest (SSD + HDD backup), Premiere import.
    Does not queue proxies; run Phase 2 after editing proxies in Premiere.
    """
    console.print(f"\n[bold]Phase 1 — Ingest & Premiere[/bold] (script {number})\n")
    ctx = _setup_project_for_number(cfg, number, refresh=refresh, dry_run=dry_run)
    console.print(f"[bold]Project:[/bold] [{ctx.entry.number}] {ctx.entry.title}\n")

    if dry_run:
        console.print("[yellow]Dry run — folders only, no copy or Premiere launch.[/yellow]")
        return

    if not skip_ingest:
        _ingest_with_plan(cfg, ctx, dry_run=False)

    _premiere_setup(cfg, ctx, open_premiere=open_premiere, queue_proxies=False)

    console.print("\n[bold]Phase 1 complete.[/bold] Footage is on SSD and HDD.")
    console.print("[dim]In Premiere: create proxies when ready, then run Phase 2.[/dim]")
    console.print(f"  GUI: Phase 2 button  |  CLI: python main.py workflow-phase2 --number {number}")


def run_phase_two(
    cfg: dict,
    number: str,
    *,
    timeout_minutes: int = 180,
    dry_run: bool = False,
) -> None:
    """
    Phase 2 — wait for proxies on SSD, back up to HDD, upload to Google Drive.
    """
    console.print(f"\n[bold]Phase 2 — Proxies & Upload[/bold] (script {number})\n")
    folder_name = get_script_by_number(cfg, number).folder_name
    ssd_path, _ = project_root(cfg, folder_name)

    if not ssd_path.exists():
        console.print(
            f"[red]Project folder not found on SSD:[/red] {ssd_path}\n"
            "  Run Phase 1 first."
        )
        raise SystemExit(1)

    if not user_confirm(
        f"Wait for proxies on SSD, back up to HDD, and upload to Google Drive?\n\n"
        f"Project: {folder_name}",
        default=True,
    ):
        raise SystemExit(0)

    result = watch_and_upload(
        cfg,
        number,
        timeout_minutes=timeout_minutes,
        dry_run=dry_run,
    )
    if not result.get("success"):
        reason = result.get("reason", "unknown")
        console.print(f"\n[red]Phase 2 did not complete ({reason}).[/red]")
        raise SystemExit(1)

    console.print("\n[bold green]Phase 2 complete.[/bold green]")


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
    console.print(f"\n[bold]Full workflow — script {number}[/bold]\n")
    ctx = _setup_project_for_number(cfg, number, refresh=refresh, dry_run=dry_run)
    console.print(f"[bold]Project:[/bold] [{ctx.entry.number}] {ctx.entry.title}\n")

    if dry_run:
        return

    if not skip_ingest:
        _ingest_with_plan(cfg, ctx, dry_run=False)

    _premiere_setup(
        cfg,
        ctx,
        open_premiere=open_premiere,
        queue_proxies=None,
    )

    console.print("\n[bold]Proxy settings (save in project template once):[/bold]")
    console.print("  Quarter | ProRes QuickTime Proxy | Proxy Icon | Next to Original, Proxy folder")

    if watch_upload:
        watch_and_upload(cfg, number, dry_run=dry_run)
    elif wait_backup:
        from .watch_upload import watch_and_backup_hdd

        watch_and_backup_hdd(cfg, number, dry_run=dry_run)
    else:
        console.print(f"\n[bold]When proxies finish on SSD (Soju):[/bold]")
        console.print(f"  python main.py workflow-phase2 --number {number}")
        if ctx.pickup_run:
            console.print(
                f"  (Pick-up #{ctx.pickup_run.number} → "
                f"{ctx.pickup_run.working_proxies_folder}/ on HDD, "
                f"Pickup Proxies #{ctx.pickup_run.number}/Proxies/ on Drive)"
            )
        console.print(f"  Or: python main.py workflow --number {number} --watch-upload")
