"""Scan ingest targets for new, identical, and conflicting files."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from rich.console import Console
from rich.table import Table

from .ingest import _ingest_roots, _video_dest_relative
from .interactive import user_confirm
from .sd_compare import CompareResult
from .utils import safe_file_size, sha256_file_with_retry

console = Console()


@dataclass
class IngestPlan:
    new_files: list[tuple[str, Path]] = field(default_factory=list)
    identical: list[tuple[str, Path]] = field(default_factory=list)
    conflicts: list[tuple[str, Path, str]] = field(default_factory=list)
    skipped_outside_clip: int = 0
    overwrite_conflicts: bool = False

    @property
    def total_sources(self) -> int:
        return len(self.new_files) + len(self.identical) + len(self.conflicts)


def build_ingest_plan(
    cfg: dict,
    compare: CompareResult,
    shoot_date: str | None,
    *,
    pickup_subfolder: str | None = None,
) -> IngestPlan:
    verify = cfg.get("ingest", {}).get("verify_checksum", True)
    plan = IngestPlan()
    ssd_root, _hdd_root = _ingest_roots(cfg, shoot_date, pickup_subfolder=pickup_subfolder)

    for rel, src in compare.all_unique_files.items():
        dest_rel = _video_dest_relative(rel, cfg)
        if dest_rel is None:
            plan.skipped_outside_clip += 1
            continue

        dest_ssd = ssd_root / dest_rel.replace("/", "\\")
        dest_hdd = _ingest_roots(cfg, shoot_date, pickup_subfolder=pickup_subfolder)[1] / dest_rel.replace(
            "/", "\\"
        )
        status = _classify_dest(src, dest_ssd, dest_hdd, verify=verify)

        if status == "new":
            plan.new_files.append((dest_rel, src))
        elif status == "identical":
            plan.identical.append((dest_rel, src))
        else:
            plan.conflicts.append((dest_rel, src, status))

    return plan


def _classify_dest(src: Path, dest_ssd: Path, dest_hdd: Path, *, verify: bool) -> str:
    src_size = safe_file_size(src)
    if src_size is None:
        return "new"

    found_identical = False
    for label, dest in (("SSD", dest_ssd), ("HDD", dest_hdd)):
        if not dest.is_file():
            continue
        dest_size = safe_file_size(dest)
        if dest_size is None:
            continue
        if dest_size != src_size:
            return f"{label} size mismatch"
        if verify:
            try:
                if sha256_file_with_retry(src) != sha256_file_with_retry(dest):
                    return f"{label} checksum mismatch"
            except OSError:
                return f"{label} unreadable during compare"
        found_identical = True
    if found_identical:
        return "identical"
    return "new"


def print_ingest_plan(plan: IngestPlan) -> None:
    console.print("\n[bold]Ingest plan[/bold]")
    console.print(f"  New files:     {len(plan.new_files)}")
    console.print(f"  Already match: {len(plan.identical)} (will skip)")
    console.print(f"  Conflicts:     {len(plan.conflicts)} (different from SD card)")
    if plan.skipped_outside_clip:
        console.print(f"  Outside CLIP:  {plan.skipped_outside_clip} (skipped)")

    if plan.conflicts:
        table = Table(title="Conflicting files (already on drive, different data)")
        table.add_column("File")
        table.add_column("Issue")
        for dest_rel, _src, issue in plan.conflicts[:15]:
            table.add_row(dest_rel, issue)
        console.print(table)
        if len(plan.conflicts) > 15:
            console.print(f"  ... and {len(plan.conflicts) - 15} more")


def confirm_ingest_plan(plan: IngestPlan) -> bool:
    """Prompt user before copying. Returns True to proceed."""
    print_ingest_plan(plan)

    if plan.total_sources == 0 and plan.skipped_outside_clip:
        console.print("[yellow]No footage files found under CLIP on SD card.[/yellow]")
        return False

    if not plan.new_files and not plan.conflicts:
        if plan.identical:
            console.print("[green]All footage already on SSD/HDD — nothing new to copy.[/green]")
            return user_confirm("Continue anyway (re-import / open Premiere)?", default=False)
        return False

    if plan.conflicts:
        overwrite = user_confirm(
            f"{len(plan.conflicts)} file(s) already exist with different data.\n"
            "Overwrite them on SSD and HDD?",
            default=False,
        )
        if overwrite:
            plan.overwrite_conflicts = True
        else:
            plan.overwrite_conflicts = False
            if not plan.new_files:
                console.print("[yellow]Cancelled — no new files to copy without overwriting.[/yellow]")
                return False
            if not user_confirm(
                f"Copy only {len(plan.new_files)} new file(s) and skip conflicts?",
                default=True,
            ):
                return False
    return True


def confirm_existing_project(path: Path, *, role: str = "Project") -> bool:
    if not path.exists():
        return True
    return user_confirm(
        f"{role} folder already exists:\n{path}\n\nContinue using this folder?",
        default=False,
    )
