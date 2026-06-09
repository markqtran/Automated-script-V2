"""Locate, download, and configure rclone for Google Drive."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

from .app_paths import app_root, user_data_dir

RCLONE_DOWNLOAD_URL = "https://downloads.rclone.org/rclone-current-windows-amd64.zip"


def rclone_install_path() -> Path:
    """Where we store rclone.exe for this app (persists across exe updates)."""
    return user_data_dir() / "rclone.exe"


def find_rclone(*, download_if_missing: bool = False) -> str:
    """
    Return path to rclone executable.

    Search order: PATH → next to exe → AppData → project folder (dev).
    Optionally auto-download into AppData when missing.
    """
    path = shutil.which("rclone")
    if path:
        return path

    for candidate in _candidate_paths():
        if candidate.is_file():
            return str(candidate)

    if download_if_missing and sys.platform == "win32":
        dest = download_rclone()
        return str(dest)

    raise RuntimeError(_missing_rclone_message())


def _candidate_paths() -> list[Path]:
    paths = [
        app_root() / "rclone.exe",
        rclone_install_path(),
        Path.cwd() / "rclone.exe",
    ]
    if not getattr(sys, "frozen", False):
        paths.append(Path(__file__).resolve().parent.parent / "rclone.exe")
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        key = str(path).lower()
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def rclone_is_installed() -> bool:
    try:
        find_rclone()
        return True
    except RuntimeError:
        return False


def download_rclone(dest: Path | None = None, on_progress: Callable[[str], None] | None = None) -> Path:
    """Download rclone.exe for Windows into AppData (or dest)."""
    if sys.platform != "win32":
        raise RuntimeError("Automatic rclone download is only supported on Windows.")

    dest = dest or rclone_install_path()
    dest.parent.mkdir(parents=True, exist_ok=True)

    if on_progress:
        on_progress("Downloading rclone…")

    with tempfile.TemporaryDirectory() as tmp:
        zip_path = Path(tmp) / "rclone.zip"

        def _report(block_num: int, block_size: int, total_size: int) -> None:
            if on_progress and total_size > 0:
                pct = min(100, int(block_num * block_size * 100 / total_size))
                on_progress(f"Downloading rclone… {pct}%")

        urllib.request.urlretrieve(RCLONE_DOWNLOAD_URL, zip_path, _report)

        if on_progress:
            on_progress("Extracting rclone…")

        with zipfile.ZipFile(zip_path) as archive:
            exe_members = [n for n in archive.namelist() if n.endswith("rclone.exe")]
            if not exe_members:
                raise RuntimeError("Download failed — rclone.exe not found in zip.")
            archive.extract(exe_members[0], tmp)
            src = Path(tmp) / exe_members[0]
            shutil.copy2(src, dest)

    if on_progress:
        on_progress(f"Installed: {dest}")

    return dest


def is_rclone_configured(remote_name: str = "gdrive") -> bool:
    """True if rclone is installed and the named remote exists."""
    try:
        rclone = find_rclone()
    except RuntimeError:
        return False

    result = subprocess.run(
        [rclone, "listremotes"],
        capture_output=True,
        text=True,
        creationflags=_subprocess_flags(),
    )
    if result.returncode != 0:
        return False
    return f"{remote_name}:" in result.stdout


def launch_rclone_config(remote_name: str = "gdrive") -> None:
    """Open a guided terminal that walks through rclone Google sign-in."""
    launch_guided_google_signin(remote_name)


def launch_guided_google_signin(remote_name: str = "gdrive") -> None:
    """Launch a helper script that auto-answers rclone config prompts."""
    rclone = find_rclone(download_if_missing=True)
    script_path = user_data_dir() / "google_signin.bat"
    script_path.parent.mkdir(parents=True, exist_ok=True)

    # Piped answers: new remote → gdrive → Google Drive → defaults → browser OAuth
    script = f"""@echo off
title Footage Workflow - Google Sign-In
color 0A
echo.
echo  =============================================
echo    Footage Workflow - Google Sign-In
echo  =============================================
echo.
echo  Your browser will open. Sign in with the Google
echo  account that has access to your shared folders.
echo.
echo  Starting in 3 seconds...
timeout /t 3 /nobreak >nul
(
echo n
echo {remote_name}
echo drive
echo.
echo.
echo 1
echo.
echo n
echo n
echo y
echo n
echo y
echo q
) | "{rclone}" config
echo.
echo  =============================================
echo  Setup step finished.
echo  Return to Footage Workflow and click Verify Setup.
echo  =============================================
pause
"""
    script_path.write_text(script, encoding="utf-8")
    if sys.platform == "win32":
        subprocess.Popen(["cmd", "/c", "start", "Footage Workflow Setup", str(script_path)])
    else:
        subprocess.Popen([str(script_path)])


def verify_google_drive_access(cfg: dict) -> tuple[bool, str]:
    """Test that rclone can reach the [01] Scripts folder."""
    from .gdrive import list_drive_files

    folder_id = cfg.get("scripts", {}).get("folder_id", "")
    if not folder_id:
        return False, "Scripts folder ID is not configured."

    if not is_rclone_configured("gdrive"):
        return False, "Google sign-in not finished. Complete sign-in in the setup window."

    try:
        files = list_drive_files(cfg, folder_id)
    except Exception as exc:
        return False, str(exc)

    if not files:
        return False, "Connected, but the Scripts folder looks empty. Check folder access."
    return True, f"Connected — found {len(files)} file(s) in Scripts folder."



def _subprocess_flags() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _missing_rclone_message() -> str:
    if getattr(sys, "frozen", False):
        return (
            "Google Drive tool (rclone) is not installed yet.\n\n"
            "In the app, click  Quick Setup  →  Install Everything ."
        )
    return (
        "rclone not found.\n\n"
        "Run: powershell -ExecutionPolicy Bypass -File install-rclone.ps1\n"
        "Or click  Setup Google Drive  in the app."
    )
