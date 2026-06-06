"""Pick-up shot runs when re-running workflow for the same script number."""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

from click import confirm
from rich.console import Console

from .premiere_proxy import proxy_subfolder_name
from .project_paths import project_root, video_folder_name
from .utils import format_bytes, iter_files

console = Console()

PICKUP_RUN_FILE = ".pickup_run.json"
PICKUP_SHOTS_RE = re.compile(r"^Pick Up Shots #(\d+)$", re.IGNORECASE)


@dataclass
class PickupRun:
    """Active pick-up workflow for one script re-run."""

    number: int
    shots_folder: str
    working_proxies_folder: str
    final_proxies_folder: str


def pickup_shots_folder_name(n: int) -> str:
    return f"Pick Up Shots #{n}"


def pickup_proxies_folder_name(n: int) -> str:
    """First pick-up uses 'Pickup Proxies'; later runs add #N."""
    if n <= 1:
        return "Pickup Proxies"
    return f"Pickup Proxies #{n}"


def _folder_has_footage(path: Path, extensions: list[str]) -> bool:
    if not path.is_dir():
        return False
    ext_set = {e.lower() for e in extensions}
    for file in iter_files(path, extensions):
        if file.suffix.lower() in ext_set and file.stat().st_size > 0:
            return True
    return False


def detect_primary_run_exists(cfg: dict, folder_name: str) -> bool:
    """True if this script already has a first-run project on SSD or HDD."""
    ssd_path, hdd_path = project_root(cfg, folder_name)

    if not ssd_path.is_dir() and not hdd_path.is_dir():
        return False

    extensions = cfg.get("footage_extensions", [".mp4", ".mov", ".xml"])
    video = video_folder_name(cfg)

    if (ssd_path / f"{folder_name}.prproj").exists():
        return True
    if (hdd_path / f"{folder_name}.prproj").exists():
        return True
    if _folder_has_footage(ssd_path / video, extensions):
        return True
    if _folder_has_footage(hdd_path / video, extensions):
        return True
    if ssd_path.is_dir() and any(
        PICKUP_SHOTS_RE.match(p.name) for p in ssd_path.iterdir() if p.is_dir()
    ):
        return True
    return False


def _existing_pickup_numbers(project_path: Path) -> list[int]:
    nums: list[int] = []
    if not project_path.is_dir():
        return nums
    for child in project_path.iterdir():
        if not child.is_dir():
            continue
        m = PICKUP_SHOTS_RE.match(child.name)
        if m:
            nums.append(int(m.group(1)))
    return nums


def next_pickup_number(project_path: Path) -> int:
    existing = _existing_pickup_numbers(project_path)
    return max(existing, default=0) + 1


def _summarize_folder(path: Path, label: str, extensions: list[str]) -> None:
    if not path.exists():
        console.print(f"  {label}: [dim](not found)[/dim] {path}")
        return
    files = list(iter_files(path, extensions))
    size = sum(f.stat().st_size for f in files)
    console.print(f"  {label}: {len(files)} file(s), {format_bytes(size)}")
    console.print(f"           {path}")


def prompt_pickup_run(cfg: dict, folder_name: str) -> bool:
    """Ask user to confirm a pick-up run instead of overwriting Video/."""
    ssd_path, hdd_path = project_root(cfg, folder_name)
    extensions = cfg.get("footage_extensions", [".mp4", ".mov", ".xml"])
    video = video_folder_name(cfg)
    n = next_pickup_number(ssd_path)

    console.print("\n[bold yellow]Existing project detected[/bold yellow]")
    console.print(f"  Script folder: {folder_name}\n")
    _summarize_folder(ssd_path / video, "SSD Video", extensions)
    _summarize_folder(hdd_path / video, "HDD Video", extensions)
    for num in sorted(_existing_pickup_numbers(ssd_path)):
        name = pickup_shots_folder_name(num)
        _summarize_folder(ssd_path / name, f"SSD {name}", extensions)

    console.print(
        f"\nA new run will create [bold]{pickup_shots_folder_name(n)}[/bold] "
        f"(original Video/ is left unchanged)."
    )
    console.print(
        f"After proxies finish, [bold]{pickup_proxies_folder_name(n)}[/bold] "
        "is uploaded to HDD and Google Drive.\n"
    )
    return confirm("Start pick-up shots run?", default=True)


def prepare_pickup_run(cfg: dict, folder_name: str) -> PickupRun:
    """Create pick-up folders on SSD + HDD and write .pickup_run.json."""
    ssd_path, hdd_path = project_root(cfg, folder_name)
    n = next_pickup_number(ssd_path)
    shots = pickup_shots_folder_name(n)
    proxy_sub = proxy_subfolder_name(cfg)
    working_proxies = f"{shots}/{proxy_sub}"
    final_proxies = pickup_proxies_folder_name(n)

    run = PickupRun(
        number=n,
        shots_folder=shots,
        working_proxies_folder=working_proxies,
        final_proxies_folder=final_proxies,
    )

    for root in (ssd_path, hdd_path):
        (root / shots).mkdir(parents=True, exist_ok=True)
        (root / shots / proxy_sub).mkdir(parents=True, exist_ok=True)

    save_pickup_run(ssd_path, run)
    console.print(f"\n[green]Pick-up run #{n} ready.[/green]")
    console.print(f"  Footage → {shots}/")
    console.print(f"  Proxies (during encode) → {working_proxies}/")
    console.print(f"  After encode → {final_proxies}/")
    console.print(f"  Premiere:    re-opens same {folder_name}.prproj (does not create a new project)")
    return run


def save_pickup_run(project_path: Path, run: PickupRun) -> None:
    data = asdict(run)
    data["status"] = "active"
    (project_path / PICKUP_RUN_FILE).write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_pickup_run(project_path: Path) -> PickupRun | None:
    path = project_path / PICKUP_RUN_FILE
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if data.get("status") not in ("active", "complete", None):
        return None
    return PickupRun(
        number=int(data["number"]),
        shots_folder=data["shots_folder"],
        working_proxies_folder=data["working_proxies_folder"],
        final_proxies_folder=data["final_proxies_folder"],
    )


def mark_pickup_complete(project_path: Path) -> None:
    path = project_path / PICKUP_RUN_FILE
    if not path.is_file():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data["status"] = "complete"
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except (json.JSONDecodeError, OSError):
        path.unlink(missing_ok=True)


def pickup_working_proxies_path(project_path: Path, run: PickupRun) -> Path:
    return project_path / Path(run.working_proxies_folder)


def pickup_final_proxies_path(project_path: Path, run: PickupRun) -> Path:
    return project_path / run.final_proxies_folder


def finalize_pickup_proxies(cfg: dict, folder_name: str, run: PickupRun) -> Path | None:
    """
    Move pick-up Proxies folder to project-root Pickup Proxies [#N] on SSD.
    """
    ssd_path, hdd_path = project_root(cfg, folder_name)
    proxy_sub = proxy_subfolder_name(cfg)
    working = ssd_path / run.shots_folder / proxy_sub
    final = ssd_path / run.final_proxies_folder

    if not working.is_dir() or not any(f.is_file() for f in working.rglob("*")):
        console.print(f"[yellow]No proxy files to finalize at {working}[/yellow]")
        return None

    if final.exists():
        if any(final.rglob("*")):
            console.print(f"[yellow]Replacing existing {final.name}/ on SSD[/yellow]")
        shutil.rmtree(final)

    shutil.move(str(working), str(final))
    console.print(f"\n[green]Renamed pick-up proxies:[/green] {final}")

    (hdd_path / run.final_proxies_folder).mkdir(parents=True, exist_ok=True)
    return final


def resolve_proxy_watch_path(cfg: dict, folder_name: str) -> Path:
    """Path to poll during encode — pick-up working Proxies or primary Video/Proxies."""
    ssd_path, _ = project_root(cfg, folder_name)
    run = load_pickup_run(ssd_path)
    if run:
        return pickup_working_proxies_path(ssd_path, run)
    from .project_paths import proxies_path

    return proxies_path(cfg, folder_name, destination="ssd")
