"""Create a new Premiere project folder from a script number."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from rich.console import Console

from .premiere_jsx import write_premiere_setup_script
from .premiere_launch import launch_premiere_automation
from .project_paths import project_root, video_folder_name
from .premiere_proxy import proxy_subfolder_name
from .scripts import get_script_by_number, get_scripts, print_scripts_table

console = Console()

TEMPLATE_PATH = Path("templates") / "project_template.prproj"
PROJECT_META = ".project_info.json"


def _write_premiere_jsx(
    cfg: dict,
    ssd_path: Path,
    folder_name: str,
    prproj_path: Path,
    *,
    script_number: str = "",
) -> Path:
    """Write automate_premiere.jsx for import + proxy workflow in Premiere."""
    return write_premiere_setup_script(
        cfg, ssd_path, folder_name, prproj_path, script_number=script_number
    )


def _write_project_meta(ssd_path: Path, entry) -> None:
    meta = {
        "number": entry.number,
        "title": entry.title,
        "folder_name": entry.folder_name,
        "source_file": entry.source_file,
    }
    (ssd_path / PROJECT_META).write_text(json.dumps(meta, indent=2), encoding="utf-8")


def _create_premiere_project(
    cfg: dict,
    ssd_path: Path,
    folder_name: str,
    dry_run: bool,
    *,
    script_number: str = "",
) -> Path:
    prproj_path = ssd_path / f"{folder_name}.prproj"
    if dry_run:
        return prproj_path

    if TEMPLATE_PATH.exists():
        shutil.copy2(TEMPLATE_PATH, prproj_path)
        console.print(f"  Created project from template: {prproj_path.name}")
    else:
        console.print(
            "[yellow]No templates/project_template.prproj found.[/yellow]\n"
            "  Save a blank project with your Ingest/Proxy settings as templates/project_template.prproj"
        )

    _write_premiere_jsx(cfg, ssd_path, folder_name, prproj_path, script_number=script_number)
    return prproj_path


def _open_premiere(
    cfg: dict,
    prproj_path: Path,
    ssd_path: Path,
    *,
    jsx_path: Path | None = None,
) -> None:
    """Launch Premiere and auto-run automate_premiere.jsx (creates project on SSD)."""
    jsx = jsx_path or (ssd_path / "automate_premiere.jsx")
    launched = launch_premiere_automation(
        cfg,
        jsx_path=jsx,
        prproj_path=prproj_path,
        project_folder=ssd_path,
    )
    if not launched:
        console.print(
            f"  Manual fallback: File > Scripts > Run Script File > {jsx.name}"
        )


def setup_new_project(
    cfg: dict,
    number: str,
    *,
    refresh: bool = False,
    dry_run: bool = False,
    open_premiere: bool = False,
) -> dict:
    """
    Look up script number on Google Drive, create matching folders on SSD + HDD,
    and prepare a Premiere Pro project file.
    """
    entry = get_script_by_number(cfg, number, refresh=refresh)
    ssd_path, hdd_path = project_root(cfg, entry.folder_name)
    video_name = video_folder_name(cfg)

    console.print(f"\n[bold]New project — [{entry.number}][/bold]")
    console.print(f"  Script:  {entry.source_file}")
    console.print(f"  Folder:  {entry.folder_name}\n")

    if ssd_path.exists() and not dry_run:
        from click import confirm

        if not confirm(f"SSD folder already exists at {ssd_path}. Continue?", default=False):
            raise SystemExit(0)

    if dry_run:
        console.print("[yellow]Dry run — would create:[/yellow]")
        console.print(f"  SSD: {ssd_path}")
        console.print(f"  HDD: {hdd_path}")
        console.print(f"  Project: {ssd_path / (entry.folder_name + '.prproj')}")
        console.print(f"  Video:   {ssd_path / video_name}/")
        return {"folder_name": entry.folder_name, "ssd_path": str(ssd_path), "dry_run": True}

    ssd_path.mkdir(parents=True, exist_ok=True)
    hdd_path.mkdir(parents=True, exist_ok=True)
    (ssd_path / video_name).mkdir(exist_ok=True)
    (hdd_path / video_name).mkdir(exist_ok=True)
    proxy_name = proxy_subfolder_name(cfg)
    (ssd_path / video_name / proxy_name).mkdir(exist_ok=True)
    (hdd_path / video_name / proxy_name).mkdir(exist_ok=True)
    _write_project_meta(ssd_path, entry)
    prproj_path = _create_premiere_project(
        cfg, ssd_path, entry.folder_name, dry_run=False, script_number=entry.number
    )

    console.print(f"\n[green]Project folders created.[/green]")
    console.print(f"  SSD (Soju): {ssd_path}")
    console.print(f"  Video:      {ssd_path / video_name}/")
    console.print(f"  Proxies:    {ssd_path / video_name / proxy_name}/")
    console.print(f"  HDD backup: {hdd_path}")

    jsx_path = ssd_path / "automate_premiere.jsx"
    if open_premiere:
        _open_premiere(cfg, prproj_path, ssd_path, jsx_path=jsx_path)
    else:
        console.print("\n[bold]Next steps:[/bold]")
        console.print(f"  python main.py new-project --number {entry.number} --open-premiere")
        console.print(f"  Or close Premiere and run with --open-premiere to auto-create the project on the SSD")
        console.print(f"  4. After filming: python main.py daily --number {entry.number}")
        console.print(
            f"  5. After proxies: python main.py watch-backup --number {entry.number}"
        )

    return {
        "number": entry.number,
        "folder_name": entry.folder_name,
        "ssd_path": str(ssd_path),
        "hdd_path": str(hdd_path),
        "prproj_path": str(prproj_path),
    }


def list_available_scripts(cfg: dict, refresh: bool = False) -> None:
    """Print all scripts from the [01] Scripts Google Drive folder."""
    console.print("\n[bold][01] Scripts — available projects[/bold]\n")
    if refresh:
        console.print("[dim]Refreshing from Google Drive...[/dim]\n")
    scripts = get_scripts(cfg, refresh=refresh)
    print_scripts_table(scripts)
    console.print(
        f"\n[dim]Cached at {Path('.cache/scripts.json')} — use --refresh to update.[/dim]"
    )
    console.print("\nCreate a project: [bold]python main.py new-project --number 003[/bold]")
