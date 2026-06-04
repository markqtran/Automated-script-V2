"""Launch Adobe Premiere Pro and run automate_premiere.jsx without manual steps."""

from __future__ import annotations

import glob
import os
import subprocess
import tempfile
from pathlib import Path

from rich.console import Console

console = Console()

EXTENDSCRIPT_FLAG = "extendscriptprqe.txt"


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


def is_premiere_running() -> bool:
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq Adobe Premiere Pro.exe"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return "Adobe Premiere Pro.exe" in (result.stdout or "")
    except (OSError, subprocess.SubprocessError):
        return False


def ensure_extendscript_flag(premiere_exe: Path) -> tuple[bool, Path]:
    """
    Adobe requires an empty extendscriptprqe.txt beside Premiere.exe
    for: Premiere.exe /C es.processFile script.jsx
    """
    flag = premiere_exe.parent / EXTENDSCRIPT_FLAG
    if flag.exists():
        return True, flag
    try:
        flag.touch()
        console.print(f"[green]Created[/green] {flag}")
        return True, flag
    except OSError:
        return False, flag


def install_premiere_cli_scripting(cfg: dict) -> bool:
    """One-time setup so Premiere runs JSX on launch (may need Administrator)."""
    premiere = find_premiere_exe(cfg)
    if not premiere:
        console.print(
            "[red]Premiere not found.[/red] Set premiere.exe_path in config.yaml "
            "to your Adobe Premiere Pro.exe path."
        )
        return False

    console.print(f"Premiere: {premiere}")
    ok, flag = ensure_extendscript_flag(premiere)
    if ok:
        console.print(
            "\n[green]Premiere CLI scripting is enabled.[/green]\n"
            "  Close Premiere completely, then run:\n"
            "  python main.py workflow --number 003"
        )
        return True

    console.print(
        f"\n[red]Could not create[/red] {flag}\n\n"
        "  Run PowerShell [bold]as Administrator[/bold], then:\n"
        f'  New-Item -Path "{flag}" -ItemType File -Force\n\n'
        "  Or right-click PowerShell → Run as administrator:\n"
        "  cd C:\\Users\\Ethan\\Automated-script\n"
        "  .\\.venv\\Scripts\\Activate.ps1\n"
        "  python main.py install-premiere\n"
    )
    return False


def _jsx_path_for_extendscript(path: Path) -> str:
    """ExtendScript File() paths work best with forward slashes."""
    return path.resolve().as_posix()


def _write_temp_wrapper(jsx_path: Path) -> Path:
    """Wrapper in %TEMP% avoids cmd-line issues with [brackets] and spaces."""
    target = _jsx_path_for_extendscript(jsx_path).replace("\\", "/")
    content = f"""(function () {{
    var f = new File("{target}");
    if (!f.exists) {{
        alert("Automation script not found:\\n" + f.fsName);
        return;
    }}
    $.evalFile(f);
}})();
"""
    wrapper = Path(tempfile.gettempdir()) / "automated_script_premiere_run.jsx"
    wrapper.write_text(content, encoding="utf-8")
    return wrapper


def write_launch_batch(
    project_folder: Path,
    premiere_exe: Path,
    jsx_path: Path,
) -> Path:
    """Batch file Ethan can double-click if Python launch does not run the script."""
    bat = project_folder / "OPEN_PREMIERE_AUTOMATION.bat"
    prem = str(premiere_exe.resolve())
    jsx = str(jsx_path.resolve())
    bat.write_text(
        "@echo off\n"
        "echo Closing Premiere if running...\n"
        'taskkill /IM "Adobe Premiere Pro.exe" /F >nul 2>&1\n'
        "timeout /t 2 /nobreak >nul\n"
        "echo Starting Premiere with automation...\n"
        f'start "" "{prem}" /C es.processFile "{jsx}"\n'
        "echo.\n"
        "echo If nothing happens, run once as Administrator:\n"
        "echo   python main.py install-premiere\n"
        "pause\n",
        encoding="utf-8",
    )
    return bat


def _try_launch(premiere: Path, script_path: Path, cwd: Path) -> bool:
    script = str(script_path.resolve())
    for args in (
        [str(premiere), "/C", "es.processFile", script],
        [str(premiere), "/C", "es.process", f'$.evalFile(new File("{_jsx_path_for_extendscript(script_path)}"));'],
    ):
        try:
            subprocess.Popen(args, shell=False, cwd=str(cwd))
            return True
        except OSError:
            continue
    return False


def launch_premiere_automation(
    cfg: dict,
    *,
    jsx_path: Path,
    prproj_path: Path,
    project_folder: Path,
) -> bool:
    """
    Launch Premiere and run automate_premiere.jsx (creates project, imports Video).

    Requires extendscriptprqe.txt beside Premiere.exe — run: python main.py install-premiere
    Premiere must be fully closed first.
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

    if is_premiere_running():
        console.print(
            "[bold red]Premiere is already running.[/bold red] "
            "Quit Premiere completely (File → Exit), then run workflow again.\n"
            "  CLI scripts only run when Premiere starts from the command line."
        )
        return False

    flag_ok, flag_path = ensure_extendscript_flag(premiere)
    if not flag_ok:
        console.print(
            f"\n[yellow]Missing {EXTENDSCRIPT_FLAG}[/yellow] next to Premiere.exe.\n"
            "  Run [bold]python main.py install-premiere[/bold] "
            "(PowerShell as Administrator if it fails).\n"
        )

    wrapper = _write_temp_wrapper(jsx_path)
    bat_path = write_launch_batch(project_folder, premiere, jsx_path)

    console.print("\n[bold]Launching Premiere with automation...[/bold]")
    console.print(f"  Project folder: {project_folder}")
    console.print(f"  Script:         {jsx_path.name}")
    if flag_ok:
        console.print(f"  CLI scripting:  enabled ({flag_path.name})")
    console.print(f"  Backup launcher: {bat_path.name}  (double-click if Premiere opens empty)\n")

    launched = _try_launch(premiere, wrapper, project_folder)
    if not launched:
        _try_launch(premiere, jsx_path, project_folder)

    if not flag_ok:
        console.print(
            "[yellow]If Premiere opens but does not create the project:[/yellow]\n"
            "  1. python main.py install-premiere   (as Administrator)\n"
            f"  2. Double-click: {bat_path}\n"
            "  3. Or in Premiere: File → Scripts → Run Script File → automate_premiere.jsx\n"
        )

    return launched


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
