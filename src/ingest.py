"""Copy footage from SD cards to SSD (editing) and HDD (backup)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from .premiere_proxy import proxy_subfolder_name
from .project_paths import project_root, video_dir, video_folder_name
from .sd_compare import CompareResult, compare_sd_cards_from_config
from .utils import (
    copy_file_robust,
    format_bytes,
    normalize_path,
    safe_file_size,
    sha256_file_with_retry,
)

console = Console()


def _ingest_roots(
    cfg: dict,
    folder_name: str | None,
    *,
    pickup_subfolder: str | None = None,
) -> tuple[Path, Path]:
    """SSD/HDD ingest targets for primary Video/ or pick-up subfolder."""
    if folder_name and pickup_subfolder:
        ssd_proj, hdd_proj = project_root(cfg, folder_name)
        return ssd_proj / pickup_subfolder, hdd_proj / pickup_subfolder

    date_fmt = cfg["ingest"].get("date_folder_format", "%Y-%m-%d")
    folder = folder_name or datetime.now().strftime(date_fmt)
    return video_dir(cfg, folder, destination="ssd"), video_dir(cfg, folder, destination="hdd")


def _dest_paths(cfg: dict, shoot_date: str | None = None) -> tuple[Path, Path]:
    """SSD/HDD ingest targets: project folder / Video / (camera paths)."""
    return _ingest_roots(cfg, shoot_date)


def _video_dest_relative(rel: str, cfg: dict) -> str | None:
    """
    Map SD card path to Video/ path.
    Strips camera folders (PRIVATE/M4ROOT/CLIP) — only contents inside CLIP go to Video/.
    Returns None to skip files not under CLIP when clip_contents_only is enabled.
    """
    ingest = cfg.get("ingest", {})
    if not ingest.get("clip_contents_only", True):
        return rel.replace("\\", "/")

    normalized = rel.replace("\\", "/").lstrip("/")
    parts = [p for p in normalized.split("/") if p]
    clip_name = ingest.get("clip_folder_name", "CLIP").upper()

    clip_index = None
    for i, part in enumerate(parts):
        if part.upper() == clip_name:
            clip_index = i
            break

    if clip_index is None:
        return None

    rest = parts[clip_index + 1 :]
    if not rest:
        return None

    if ingest.get("flatten_clip", False):
        return rest[-1]

    return "/".join(rest)


def _copy_file(
    src: Path,
    dest: Path,
    verify: bool,
    dry_run: bool,
    *,
    force: bool = False,
    max_retries: int = 8,
    retry_delay: float = 3.0,
) -> tuple[bool, str]:
    """Copy one file. Returns (copied, message). Skips if dest exists and matches."""
    try:
        src_size = safe_file_size(src)
        if src_size is None:
            return False, "FAILED cannot read source file on SD/drive"

        if dest.exists() and not force:
            dest_size = safe_file_size(dest)
            if dest_size is not None and dest_size == src_size:
                if not verify:
                    return False, "skipped (exists)"
                try:
                    if sha256_file_with_retry(
                        dest,
                        max_retries=max_retries,
                        retry_delay=retry_delay,
                    ) == sha256_file_with_retry(
                        src,
                        max_retries=max_retries,
                        retry_delay=retry_delay,
                    ):
                        return False, "skipped (verified)"
                except OSError as exc:
                    return False, f"FAILED verify {exc}"
                return False, "skipped (conflict)"
            if dest_size is not None and dest_size > src_size:
                return False, "skipped (dest larger)"
            if dest_size is not None:
                return False, "skipped (conflict)"

        if dry_run:
            return True, "would copy"

        src_hash = copy_file_robust(
            src,
            dest,
            max_retries=max_retries,
            retry_delay=retry_delay,
            compute_hash=verify,
        )

        if verify:
            dest_size = safe_file_size(dest)
            if dest_size != src_size:
                dest.unlink(missing_ok=True)
                return False, "FAILED size mismatch after copy"
            dest_hash = sha256_file_with_retry(
                dest,
                max_retries=max_retries,
                retry_delay=retry_delay,
            )
            if src_hash is None:
                src_hash = sha256_file_with_retry(
                    src,
                    max_retries=max_retries,
                    retry_delay=retry_delay,
                )
            if src_hash != dest_hash:
                dest.unlink(missing_ok=True)
                return False, "FAILED checksum"
        return True, "copied"
    except OSError as exc:
        dest.unlink(missing_ok=True)
        partial = dest.with_name(dest.name + ".partial")
        partial.unlink(missing_ok=True)
        return False, f"FAILED {exc}"


def ingest_footage(
    cfg: dict,
    compare: CompareResult | None = None,
    shoot_date: str | None = None,
    *,
    pickup_subfolder: str | None = None,
    dry_run: bool = False,
    plan=None,
) -> dict:
    """
    Copy all footage from SD card(s) into project/Video/ on SSD and HDD.
    When pickup_subfolder is set (e.g. 'Pick Up Shots #1'), ingest there instead.
    """
    extensions = cfg.get("footage_extensions", [".mp4", ".mov"])
    ingest_cfg = cfg.get("ingest", {})
    verify = ingest_cfg.get("verify_checksum", True)
    max_retries = int(ingest_cfg.get("copy_retries", 8))
    retry_delay = float(ingest_cfg.get("copy_retry_delay_seconds", 3.0))

    if compare is None:
        compare = compare_sd_cards_from_config(cfg, extensions)

    files = compare.all_unique_files
    ssd_root, hdd_root = _ingest_roots(
        cfg,
        shoot_date,
        pickup_subfolder=pickup_subfolder,
    )
    video_name = video_folder_name(cfg)
    proxy_name = proxy_subfolder_name(cfg)
    ingest_label = pickup_subfolder or video_name
    ssd_root.mkdir(parents=True, exist_ok=True)
    hdd_root.mkdir(parents=True, exist_ok=True)
    (ssd_root / proxy_name).mkdir(exist_ok=True)
    (hdd_root / proxy_name).mkdir(exist_ok=True)

    to_copy: list[tuple[str, Path, str, bool]] = []
    skipped_outside_clip = 0

    if plan is not None:
        from .ingest_plan import IngestPlan

        assert isinstance(plan, IngestPlan)
        skipped_outside_clip = plan.skipped_outside_clip
        for dest_rel, src in plan.new_files:
            to_copy.append((dest_rel, src, dest_rel, False))
        if plan.overwrite_conflicts:
            for dest_rel, src, _issue in plan.conflicts:
                to_copy.append((dest_rel, src, dest_rel, True))
    else:
        for rel, src in files.items():
            dest_rel = _video_dest_relative(rel, cfg)
            if dest_rel is None:
                skipped_outside_clip += 1
                continue
            to_copy.append((dest_rel, src, rel, False))

    stats = {"copied_ssd": 0, "copied_hdd": 0, "skipped": 0, "failed": 0, "bytes": 0}

    console.print(f"\n[bold]Ingesting {len(to_copy)} file(s) into {ingest_label}/[/bold]")
    console.print("  (CLIP contents only — no PRIVATE/M4ROOT/CLIP folders on SSD)")
    console.print(f"  SSD: {ssd_root}")
    console.print(f"  HDD: {hdd_root}\n")
    if skipped_outside_clip:
        console.print(f"  [dim]Skipped {skipped_outside_clip} file(s) outside CLIP on SD card[/dim]\n")

    copy_opts = {"max_retries": max_retries, "retry_delay": retry_delay}

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Copying...", total=len(to_copy))

        for dest_rel, src, rel, force in sorted(to_copy, key=lambda x: x[0]):
            try:
                progress.update(task, description=dest_rel[:60])

                ssd_dest = ssd_root / dest_rel.replace("/", "\\")
                hdd_dest = hdd_root / dest_rel.replace("/", "\\")

                ok_ssd, msg_ssd = _copy_file(
                    src,
                    ssd_dest,
                    verify,
                    dry_run,
                    force=force,
                    **copy_opts,
                )
                if ok_ssd:
                    stats["copied_ssd"] += 1
                    stats["bytes"] += safe_file_size(ssd_dest) or safe_file_size(src) or 0
                elif msg_ssd.startswith("skipped"):
                    stats["skipped"] += 1
                elif msg_ssd.startswith("FAILED"):
                    stats["failed"] += 1
                    console.print(f"[red]SSD {dest_rel}: {msg_ssd}[/red]")

                hdd_src = ssd_dest if ssd_dest.is_file() else src
                hdd_verify = verify and hdd_src == src
                ok_hdd, msg_hdd = _copy_file(
                    hdd_src,
                    hdd_dest,
                    hdd_verify,
                    dry_run,
                    force=force,
                    **copy_opts,
                )
                if ok_hdd:
                    stats["copied_hdd"] += 1
                elif msg_hdd.startswith("skipped"):
                    stats["skipped"] += 1
                elif msg_hdd.startswith("FAILED"):
                    stats["failed"] += 1
                    console.print(f"[red]HDD {dest_rel}: {msg_hdd}[/red]")
            except OSError as exc:
                stats["failed"] += 1
                console.print(f"[red]{dest_rel}: {exc}[/red]")

            progress.advance(task)

    console.print(f"\n[green]Ingest complete.[/green]" if stats["failed"] == 0 else "\n[yellow]Ingest finished with errors.[/yellow]")
    console.print(f"  SSD copies: {stats['copied_ssd']}")
    console.print(f"  HDD copies: {stats['copied_hdd']}")
    console.print(f"  Skipped:    {stats['skipped']}")
    if skipped_outside_clip:
        console.print(f"  Not under CLIP: {skipped_outside_clip}")
    if stats["failed"]:
        console.print(f"  [red]Failed:     {stats['failed']}[/red]")
        console.print(
            "\n[dim]Tip: Re-plug the SD card and SSD/HDD, wait a few seconds, then re-run. "
            "You can set ingest.verify_checksum: false in config for faster copies on flaky cards. "
            f"Retries: up to {max_retries} per file.[/dim]"
        )
        raise SystemExit(1)
    console.print(f"  Data moved: {format_bytes(stats['bytes'])}")

    stats["ssd_path"] = str(ssd_root.parent)
    stats["video_path"] = str(ssd_root)
    stats["hdd_path"] = str(hdd_root.parent)
    return stats
