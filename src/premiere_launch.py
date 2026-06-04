"""Launch Adobe Premiere Pro and run automate_premiere.jsx without manual steps."""

from __future__ import annotations

import glob
import os
import subprocess
from pathlib import Path

from rich.console import Console

console = Console()


def find_premiere_exe(cfg: dict) -> Path | None:
    premiere_cfg = cfg.get("premiere", {})
    if premiere_cfg.get("exe_path"):
        path = Path(premiere_cfg["exe_path"])
        if path.exists():
            return path

    patterns = [
        r"C:\Program Files\Adobe\Adobe Premiere Pro *\Adobe Premiere Pro.exe",
    ]
    matches: list[str] = []
    for pattern in patterns:
        matches.extend(glob.glob(pattern))
    if not matches:
        return None
    return Path(sorted(matches)[-1])


def _scripting_enabled_hint(premiere_exe: Path) -> str | None:
    """Adobe requires extendscriptprqe.txt beside Premiere.exe for CLI script execution."""
    flag = premiere_exe.parent / "extendscriptprqe.txt"
    if flag.exists():
        return None
    return (
        f"[yellow]Tip:[/yellow] For fully automatic scripting, create an empty file:\n"
        f"  {flag}\n"
        f"  (Then close Premiere and run this command again.)"
    )


def launch_premiere_automation(
    cfg: dict,
    *,
    jsx_path: Path,
    prproj_path: Path,
    project_folder: Path,
) -> bool:
    """
    Launch Premiere and run automate_premiere.jsx.

    Uses: Premiere.exe /C es.processFile "path\\automate_premiere.jsx"
    Works when Premiere is not already running (Adobe limitation).
    """
    premiere_cfg = cfg.get("premiere", {})
    if premiere_cfg.get("auto_run_script") is False:
        return _launch_premiere_project_only(cfg, prproj_path, project_folder)

    premiere = find_premiere_exe(cfg)
    if not premiere:
        console.print(
            "[yellow]Adobe Premiere Pro not found.[/yellow] "
            "Set premiere.exe_path in config.yaml."
        )
        os.startfile(project_folder)  # noqa: S606
        return False

    if not jsx_path.is_file():
        console.print(f"[red]Automation script missing:[/red] {jsx_path}")
        return False

    hint = _scripting_enabled_hint(premiere)
    if hint:
        console.print(hint)

    jsx = str(jsx_path.resolve())
    console.print("\n[bold]Launching Premiere with automation...[/bold]")
    console.print(f"  Project folder: {project_folder}")
    console.print(f"  Script:         {jsx_path.name}")
    console.print(
        "[dim]Close Premiere completely first — CLI scripts only run on a fresh launch.[/dim]\n"
    )

    subprocess.Popen(
        [str(premiere), "/C", "es.processFile", jsx],
        shell=False,
        cwd=str(project_folder),
    )
    return True


def _launch_premiere_project_only(
    cfg: dict,
    prproj_path: Path,
    project_folder: Path,
) -> bool:
    """Open an existing .prproj (no automatic JSX)."""
    premiere = find_premiere_exe(cfg)
    if not premiere:
        os.startfile(project_folder)  # noqa: S606
        return False

    if prproj_path.is_file():
        console.print(f"Opening Premiere: {prproj_path.name}")
        subprocess.Popen([str(premiere), str(prproj_path.resolve())], shell=False)
    else:
        console.print("Opening Premiere — run automate_premiere.jsx from File > Scripts")
        subprocess.Popen([str(premiere)], shell=False)
        os.startfile(project_folder)  # noqa: S606
    return True
