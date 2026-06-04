"""Create a new Premiere project folder from a script number."""

from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
from pathlib import Path

from rich.console import Console

from .project_paths import project_root, video_dir, video_folder_name
from .scripts import get_script_by_number, get_scripts, print_scripts_table

console = Console()


def _find_premiere_exe(cfg: dict) -> Path | None:
    premiere_cfg = cfg.get("premiere", {})
    if premiere_cfg.get("exe_path"):
        path = Path(premiere_cfg["exe_path"])
        if path.exists():
            return path

    patterns = [
        r"C:\Program Files\Adobe\Adobe Premiere Pro *\Adobe Premiere Pro.exe",
        r"C:\Program Files\Adobe\Adobe Premiere Pro *\Adobe Premiere Pro.exe",
    ]
    matches: list[str] = []
    for pattern in patterns:
        matches.extend(glob.glob(pattern))
    if not matches:
        return None
    return Path(sorted(matches)[-1])


def _write_premiere_jsx(ssd_path: Path, prproj_path: Path) -> Path:
    """Write an ExtendScript file to create/open the project in Premiere."""
    jsx_path = ssd_path / "create_premiere_project.jsx"
    # ExtendScript prefers forward slashes
    prproj_js = str(prproj_path).replace("\\", "/")
    jsx_content = f"""// Auto-generated — run from Premiere: File > Scripts > Run Script File
(function () {{
    var projectPath = "{prproj_js}";
    var file = new File(projectPath);
    if (file.exists) {{
        app.openDocument(projectPath);
    }} else {{
        app.newProject(projectPath);
    }}
}})();
"""
    jsx_path.write_text(jsx_content, encoding="utf-8")
    return jsx_path


def _write_project_meta(ssd_path: Path, entry) -> None:
    meta = {
        "number": entry.number,
        "title": entry.title,
        "folder_name": entry.folder_name,
        "source_file": entry.source_file,
    }
    (ssd_path / PROJECT_META).write_text(json.dumps(meta, indent=2), encoding="utf-8")


def _create_premiere_project(ssd_path: Path, folder_name: str, dry_run: bool) -> Path:
    prproj_path = ssd_path / f"{folder_name}.prproj"
    if dry_run:
        return prproj_path

    if TEMPLATE_PATH.exists():
        shutil.copy2(TEMPLATE_PATH, prproj_path)
        console.print(f"  Created project from template: {prproj_path.name}")
    else:
        console.print(
            "[yellow]No templates/project_template.prproj found.[/yellow]\n"
            "  Premiere project will be created via ExtendScript on first open."
        )

    _write_premiere_jsx(ssd_path, prproj_path)
    return prproj_path


def _open_premiere(cfg: dict, prproj_path: Path | None, ssd_path: Path) -> None:
    premiere = _find_premiere_exe(cfg)
    if not premiere:
        console.print(
            "[yellow]Adobe Premiere Pro not found.[/yellow] "
            "Set premiere.exe_path in config.yaml or open Premiere manually."
        )
        os.startfile(ssd_path)  # noqa: S606 — opens folder in Explorer on Windows
        return

    if prproj_path and prproj_path.exists():
        console.print(f"Opening Premiere with {prproj_path.name}...")
        subprocess.Popen([str(premiere), str(prproj_path)], shell=False)
    else:
        console.print("Opening Premiere — run the ExtendScript to create the project:")
        console.print(f"  File > Scripts > Run Script File > {ssd_path / 'create_premiere_project.jsx'}")
        subprocess.Popen([str(premiere)], shell=False)
        os.startfile(ssd_path)  # noqa: S606


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
    _write_project_meta(ssd_path, entry)
    prproj_path = _create_premiere_project(ssd_path, entry.folder_name, dry_run=False)

    console.print(f"\n[green]Project folders created.[/green]")
    console.print(f"  SSD (Soju): {ssd_path}")
    console.print(f"  Video:      {ssd_path / video_name}/")
    console.print(f"  HDD backup: {hdd_path}")

    if open_premiere:
        _open_premiere(cfg, prproj_path if prproj_path.exists() else None, ssd_path)
    else:
        console.print("\n[bold]Next steps:[/bold]")
        if prproj_path.exists():
            console.print(f"  Open in Premiere: {prproj_path}")
        else:
            console.print("  1. Open Adobe Premiere Pro")
            console.print(f"  2. File > Scripts > Run Script File > {ssd_path / 'create_premiere_project.jsx'}")
        console.print(f"  3. Import the Video folder in Premiere, create proxies (your preset)")
        console.print(f"  4. After filming: python main.py daily --number {entry.number}")
        console.print(f"  5. After proxies finish: python main.py upload-drive --number {entry.number}")

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
