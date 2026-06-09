"""Compare two SD cards and report differences."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from rich.table import Table

from .drive_settings import DRIVE_NA_LABEL, is_drive_na
from .utils import format_bytes, normalize_path, scan_directory

console = Console()


@dataclass
class CompareResult:
    primary_only: list[str]
    backup_only: list[str]
    size_mismatch: list[tuple[str, int, int]]
    matching: list[str]
    primary_path: Path
    backup_path: Path
    single_card: bool = False

    @property
    def in_sync(self) -> bool:
        if self.single_card:
            return True
        return not self.primary_only and not self.backup_only and not self.size_mismatch

    @property
    def recommended_source(self) -> Path:
        """When cards differ, prefer the card with more footage files."""
        primary_count = len(self.matching) + len(self.primary_only)
        backup_count = len(self.matching) + len(self.backup_only)
        if backup_count > primary_count:
            return self.backup_path
        return self.primary_path

    @property
    def all_unique_files(self) -> dict[str, Path]:
        """Map relative path -> source path for every file across both cards."""
        result: dict[str, Path] = {}
        for rel in self.matching + self.primary_only:
            result[rel] = self.primary_path / rel.replace("/", "\\")
        for rel in self.backup_only:
            result[rel] = self.backup_path / rel.replace("/", "\\")
        return result


def _compare_primary_only(primary_path: Path, extensions: list[str]) -> CompareResult:
    """Ingest from one SD card when the backup card is not inserted."""
    primary_files = scan_directory(primary_path, extensions)
    matching = sorted(primary_files)
    return CompareResult(
        primary_only=[],
        backup_only=[],
        size_mismatch=[],
        matching=matching,
        primary_path=primary_path,
        backup_path=primary_path,
        single_card=True,
    )


def compare_sd_cards_from_config(cfg: dict, extensions: list[str]) -> CompareResult:
    """Compare SD cards, or use primary only when backup is missing or single_card is set."""
    sd = cfg.get("sd_cards", {})
    primary = sd["primary"]
    backup = sd.get("backup", "")
    single_card = sd.get("single_card", False)

    primary_path = normalize_path(primary)
    if not primary_path.exists():
        raise FileNotFoundError(f"Primary SD card not found: {primary_path}")

    if single_card or is_drive_na(backup):
        console.print("[dim]Single SD card mode — ingesting from primary card only.[/dim]")
        return _compare_primary_only(primary_path, extensions)

    backup_path = normalize_path(backup)
    if backup_path == primary_path:
        console.print("[dim]Primary and backup paths are the same — single card mode.[/dim]")
        return _compare_primary_only(primary_path, extensions)

    if not backup_path.exists():
        console.print(
            f"[yellow]Backup SD card not found at {backup_path}. "
            "Using primary card only.[/yellow]"
        )
        return _compare_primary_only(primary_path, extensions)

    return compare_sd_cards(primary, backup, extensions)


def compare_sd_cards(
    primary: str | Path,
    backup: str | Path,
    extensions: list[str],
) -> CompareResult:
    primary_path = normalize_path(primary)
    backup_path = normalize_path(backup)

    if not primary_path.exists():
        raise FileNotFoundError(f"Primary SD card not found: {primary_path}")
    if not backup_path.exists():
        raise FileNotFoundError(f"Backup SD card not found: {backup_path}")

    primary_files = scan_directory(primary_path, extensions)
    backup_files = scan_directory(backup_path, extensions)

    primary_only: list[str] = []
    backup_only: list[str] = []
    size_mismatch: list[tuple[str, int, int]] = []
    matching: list[str] = []

    all_keys = sorted(set(primary_files) | set(backup_files))
    for rel in all_keys:
        p = primary_files.get(rel)
        b = backup_files.get(rel)
        if p and not b:
            primary_only.append(rel)
        elif b and not p:
            backup_only.append(rel)
        elif p and b:
            if p.size != b.size:
                size_mismatch.append((rel, p.size, b.size))
            else:
                matching.append(rel)

    return CompareResult(
        primary_only=primary_only,
        backup_only=backup_only,
        size_mismatch=size_mismatch,
        matching=matching,
        primary_path=primary_path,
        backup_path=backup_path,
    )


def print_compare_report(result: CompareResult) -> None:
    if result.single_card:
        console.print("\n[bold]SD Card Report (single card)[/bold]\n")
        console.print(f"  Card: {result.primary_path}\n")
        console.print(f"  Footage files found: {len(result.matching)}")
        if result.matching:
            console.print("\n[green]Ready to ingest from primary card.[/green]")
        else:
            console.print("\n[yellow]No footage files found on this card.[/yellow]")
        return

    console.print("\n[bold]SD Card Comparison Report[/bold]\n")
    console.print(f"  Primary: {result.primary_path}")
    console.print(f"  Backup:  {result.backup_path}\n")

    table = Table(show_header=True, header_style="bold")
    table.add_column("Status", style="dim")
    table.add_column("Count", justify="right")
    table.add_row("Matching files", str(len(result.matching)))
    table.add_row("Only on primary", str(len(result.primary_only)), style="yellow")
    table.add_row("Only on backup", str(len(result.backup_only)), style="yellow")
    table.add_row("Size mismatches", str(len(result.size_mismatch)), style="red")
    console.print(table)

    if result.primary_only:
        console.print("\n[yellow]Files only on PRIMARY card:[/yellow]")
        for rel in result.primary_only[:20]:
            console.print(f"  + {rel}")
        if len(result.primary_only) > 20:
            console.print(f"  ... and {len(result.primary_only) - 20} more")

    if result.backup_only:
        console.print("\n[yellow]Files only on BACKUP card:[/yellow]")
        for rel in result.backup_only[:20]:
            console.print(f"  + {rel}")
        if len(result.backup_only) > 20:
            console.print(f"  ... and {len(result.backup_only) - 20} more")

    if result.size_mismatch:
        console.print("\n[red]Size mismatches (same filename, different size):[/red]")
        for rel, ps, bs in result.size_mismatch[:10]:
            console.print(f"  ! {rel}  primary={format_bytes(ps)}  backup={format_bytes(bs)}")

    if result.in_sync:
        console.print("\n[green]Cards are in sync.[/green]")
    else:
        src = result.recommended_source
        console.print(
            f"\n[yellow]Cards differ. Recommended ingest source: {src}[/yellow]"
        )
        console.print("Ingest will copy all unique files from both cards.")
