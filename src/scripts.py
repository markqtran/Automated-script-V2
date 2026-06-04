"""Look up video project names from the [01] Scripts folder on Google Drive."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from rich.table import Table

from .gdrive import list_drive_files
from .utils import normalize_path, sanitize_windows_folder_name

console = Console()

SCRIPT_PATTERN = re.compile(r"^\[(\d{3})\]\s*(.+?)(?:\.pdf)?$", re.IGNORECASE)
CACHE_DIR = Path(".cache")
CACHE_FILE = CACHE_DIR / "scripts.json"


@dataclass(frozen=True)
class ScriptEntry:
    number: str
    title: str
    folder_name: str
    source_file: str


def _scripts_folder_id(cfg: dict) -> str:
    scripts_cfg = cfg.get("scripts", {})
    folder_id = scripts_cfg.get("folder_id")
    if not folder_id:
        raise ValueError(
            "Missing scripts.folder_id in config.yaml — set the [01] Scripts Google Drive folder ID."
        )
    return folder_id


def normalize_script_number(number: str) -> str:
    """Accept '3', '03', or '003' and return '003'."""
    digits = re.sub(r"\D", "", number)
    if not digits:
        raise ValueError(f"Invalid script number: {number!r}")
    if len(digits) > 3:
        raise ValueError(f"Script number must be 3 digits or less, got: {number!r}")
    return digits.zfill(3)


def build_project_folder_name(number: str, title: str) -> str:
    """e.g. '[004] POV - Your friend is highkey a serial killer' (Windows-safe)."""
    safe_title = sanitize_windows_folder_name(title)
    return f"[{number}] {safe_title}"


def parse_script_filename(filename: str) -> ScriptEntry | None:
    """Parse '[003] Teaching an Ipad Kid.pdf' into a ScriptEntry."""
    name = filename.strip()
    match = SCRIPT_PATTERN.match(name)
    if not match:
        return None
    number, title = match.group(1), match.group(2).strip()
    title = re.sub(r"\.pdf$", "", title, flags=re.IGNORECASE).strip()
    folder_name = build_project_folder_name(number, title)
    return ScriptEntry(
        number=number,
        title=title,
        folder_name=folder_name,
        source_file=name if name.lower().endswith(".pdf") else f"{name}.pdf",
    )


def fetch_scripts_from_drive(cfg: dict) -> dict[str, ScriptEntry]:
    """List script PDFs from Google Drive and return a map of number -> entry."""
    folder_id = _scripts_folder_id(cfg)
    filenames = list_drive_files(cfg, folder_id)

    scripts: dict[str, ScriptEntry] = {}
    for name in filenames:
        entry = parse_script_filename(name)
        if entry:
            scripts[entry.number] = entry

    if not scripts:
        raise RuntimeError(
            "No scripts found in the [01] Scripts folder. "
            "Check scripts.folder_id and rclone access."
        )
    return scripts


def _load_cache() -> dict[str, dict] | None:
    if not CACHE_FILE.exists():
        return None
    try:
        with CACHE_FILE.open(encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _save_cache(scripts: dict[str, ScriptEntry]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        num: {
            "number": e.number,
            "title": e.title,
            "folder_name": e.folder_name,
            "source_file": e.source_file,
        }
        for num, e in sorted(scripts.items())
    }
    with CACHE_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _cache_to_entries(data: dict[str, dict]) -> dict[str, ScriptEntry]:
    entries: dict[str, ScriptEntry] = {}
    for num, v in data.items():
        number = v["number"]
        title = v["title"]
        entries[num] = ScriptEntry(
            number=number,
            title=title,
            folder_name=build_project_folder_name(number, title),
            source_file=v["source_file"],
        )
    return entries


def get_scripts(cfg: dict, refresh: bool = False) -> dict[str, ScriptEntry]:
    """Return cached scripts or refresh from Google Drive."""
    if not refresh:
        cached = _load_cache()
        if cached:
            return _cache_to_entries(cached)

    scripts = fetch_scripts_from_drive(cfg)
    _save_cache(scripts)
    return scripts


def get_script_by_number(cfg: dict, number: str, refresh: bool = False) -> ScriptEntry:
    """Look up a script by 3-digit number."""
    normalized = normalize_script_number(number)
    scripts = get_scripts(cfg, refresh=refresh)
    if normalized not in scripts:
        available = ", ".join(sorted(scripts))
        raise KeyError(
            f"Script [{normalized}] not found in [01] Scripts folder.\n"
            f"Available: {available}\n"
            f"Run: python main.py list-scripts --refresh"
        )
    return scripts[normalized]


def resolve_project_folder(cfg: dict, number: str, refresh: bool = False) -> str:
    """Return folder name like '[003] Teaching an Ipad Kid' for ingest/daily."""
    return get_script_by_number(cfg, number, refresh=refresh).folder_name


def print_scripts_table(scripts: dict[str, ScriptEntry]) -> None:
    table = Table(show_header=True, header_style="bold")
    table.add_column("#", justify="right")
    table.add_column("Project folder name")
    table.add_column("Script file", style="dim")
    for num in sorted(scripts):
        entry = scripts[num]
        table.add_row(num, entry.folder_name, entry.source_file)
    console.print(table)
