"""Shared utilities for the footage workflow automation."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

# Characters invalid in Windows file/folder names (colon, etc.)
_INVALID_WIN_NAME = re.compile(r'[<>:"/\\|?*]')

# Windows I/O errors that often clear after a short wait (SD cards, USB HDDs).
_TRANSIENT_WINERRORS = frozenset({21, 32, 53, 121, 1117, 1392})


@dataclass(frozen=True)
class FileInfo:
    relative_path: str
    size: int
    mtime: float

    @property
    def name(self) -> str:
        return Path(self.relative_path).name


def normalize_path(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def win_long_path(path: Path) -> Path:
    """
    Windows extended-length path (\\\\?\\...) — required for reliable I/O when
    project folders contain brackets, e.g. [004] Title.
    """
    if sys.platform != "win32":
        return path
    text = str(path)
    if text.startswith("\\\\?\\"):
        return path
    try:
        resolved = path.expanduser().resolve()
    except OSError:
        resolved = path.expanduser().absolute()
    text = str(resolved)
    if text.startswith("\\\\?\\"):
        return Path(text)
    if text.startswith("\\\\"):
        return Path("\\\\?\\UNC\\" + text[2:])
    return Path("\\\\?\\" + text)


def path_has_brackets(path: Path) -> bool:
    text = str(path)
    return "[" in text or "]" in text


def sanitize_windows_folder_name(text: str) -> str:
    """
    Make a script title safe for SSD/HDD project folders and .prproj names.

    Drive PDFs may use ':' (e.g. 'POV: Your friend...') which Windows rejects.
    """
    cleaned = text.strip()
    cleaned = cleaned.replace(":", " -")
    cleaned = _INVALID_WIN_NAME.sub("-", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = cleaned.rstrip(". ")
    return cleaned or "Untitled"


def iter_files(root: Path, extensions: Iterable[str] | None = None) -> Iterable[Path]:
    """Yield all files under root, optionally filtered by extension."""
    ext_set = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in extensions} if extensions else None
    if not root.exists():
        return
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            path = Path(dirpath) / name
            if ext_set and path.suffix.lower() not in ext_set:
                continue
            yield path


def relative_to(path: Path, root: Path) -> str:
    return str(path.relative_to(root)).replace("\\", "/")


def sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    open_path = win_long_path(path) if sys.platform == "win32" else path
    with open_path.open("rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class CopyResult:
    ok: bool
    src_hash: str | None = None
    error: str = ""


def safe_file_size(path: Path) -> int | None:
    for candidate in (path, win_long_path(path) if sys.platform == "win32" else path):
        try:
            return candidate.stat().st_size
        except OSError:
            continue
    return None


def safe_unlink(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def sha256_file_with_retry(
    path: Path,
    *,
    max_retries: int = 5,
    retry_delay: float = 2.0,
    chunk_size: int = 8 * 1024 * 1024,
) -> str:
    last_error: OSError | None = None
    for attempt in range(max_retries):
        try:
            return sha256_file(path, chunk_size=chunk_size)
        except OSError as exc:
            last_error = exc
            if attempt + 1 < max_retries and _is_transient_copy_error(exc):
                time.sleep(retry_delay * (attempt + 1))
                continue
            raise
    if last_error is not None:
        raise last_error
    raise OSError(f"Cannot hash {path}")


def _subprocess_flags() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _is_transient_copy_error(exc: OSError) -> bool:
    winerror = getattr(exc, "winerror", None)
    if winerror in _TRANSIENT_WINERRORS:
        return True
    text = str(exc).lower()
    return "timeout" in text or "device is not ready" in text or "i/o device error" in text


def _read_with_retry(
    fin,
    size: int,
    *,
    max_retries: int,
    retry_delay: float,
) -> bytes:
    last_error: OSError | None = None
    for attempt in range(max_retries):
        try:
            return fin.read(size)
        except OSError as exc:
            last_error = exc
            if attempt + 1 < max_retries and _is_transient_copy_error(exc):
                time.sleep(retry_delay * (attempt + 1))
                continue
            raise
    if last_error is not None:
        raise last_error
    return b""


def _chunked_copy(
    src: Path,
    dest: Path,
    *,
    chunk_size: int = 8 * 1024 * 1024,
    compute_hash: bool = False,
    max_retries: int = 5,
    retry_delay: float = 2.0,
) -> str | None:
    src_open = win_long_path(src) if sys.platform == "win32" else src
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest_open = win_long_path(dest) if sys.platform == "win32" else dest
    hasher = hashlib.sha256() if compute_hash else None
    with src_open.open("rb") as fin, dest_open.open("wb") as fout:
        while True:
            chunk = _read_with_retry(
                fin,
                chunk_size,
                max_retries=max_retries,
                retry_delay=retry_delay,
            )
            if not chunk:
                break
            fout.write(chunk)
            if hasher:
                hasher.update(chunk)
    return hasher.hexdigest() if hasher else None


def _finalize_partial(partial: Path, dest: Path) -> None:
    safe_unlink(dest)
    if sys.platform == "win32":
        win_long_path(partial).replace(win_long_path(dest))
    else:
        partial.replace(dest)


def _robocopy_single_file(
    src: Path,
    dest: Path,
    *,
    robocopy_retries: int = 10,
    robocopy_wait: int = 5,
) -> bool:
    """Windows robocopy — skip bracket paths like [004] (robocopy treats [] specially)."""
    robocopy = shutil.which("robocopy")
    if not robocopy or sys.platform != "win32":
        return False
    if path_has_brackets(src) or path_has_brackets(dest):
        return False

    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        robocopy,
        str(src.parent),
        str(dest.parent),
        src.name,
        "/COPY:DAT",
        "/DCOPY:DAT",
        f"/R:{robocopy_retries}",
        f"/W:{robocopy_wait}",
        "/NFL",
        "/NDL",
        "/NJH",
        "/NJS",
        "/NC",
        "/NS",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, creationflags=_subprocess_flags())
    except OSError:
        return False
    if result.returncode >= 8:
        return False

    src_size = safe_file_size(src)
    dest_size = safe_file_size(dest)
    return dest.is_file() and src_size is not None and dest_size == src_size


def copy_file_robust(
    src: Path,
    dest: Path,
    *,
    max_retries: int = 8,
    retry_delay: float = 3.0,
    compute_hash: bool = False,
) -> CopyResult:
    """
    Copy a file with retries for flaky SD/USB drives.

    Never raises — returns CopyResult with ok=False and error set on failure.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_name(dest.name + ".partial")
    last_error = ""

    for attempt in range(max_retries):
        safe_unlink(partial)
        try:
            if _robocopy_single_file(
                src,
                dest,
                robocopy_retries=min(10, max_retries),
                robocopy_wait=max(3, int(retry_delay)),
            ):
                if compute_hash:
                    try:
                        src_hash = sha256_file_with_retry(
                            src,
                            max_retries=max_retries,
                            retry_delay=retry_delay,
                        )
                        return CopyResult(ok=True, src_hash=src_hash)
                    except OSError as exc:
                        last_error = str(exc)
                        safe_unlink(dest)
                        if attempt + 1 < max_retries and _is_transient_copy_error(exc):
                            time.sleep(retry_delay * (attempt + 1))
                            continue
                        break
                return CopyResult(ok=True)

            src_hash = _chunked_copy(
                src,
                partial,
                compute_hash=compute_hash,
                max_retries=max_retries,
                retry_delay=retry_delay,
            )
            try:
                shutil.copystat(src, partial)
            except OSError:
                pass
            _finalize_partial(partial, dest)
            return CopyResult(ok=True, src_hash=src_hash)
        except OSError as exc:
            last_error = str(exc)
            safe_unlink(partial)
            if attempt + 1 < max_retries and _is_transient_copy_error(exc):
                time.sleep(retry_delay * (attempt + 1))
                continue

    safe_unlink(partial)
    safe_unlink(dest)
    return CopyResult(ok=False, error=last_error or "copy failed after retries")


def mirror_folder(src: Path, dest: Path, *, max_retries: int = 3) -> CopyResult:
    """Mirror a folder tree (used for SSD Video/ → HDD Video/ after SD ingest)."""
    if not src.is_dir():
        return CopyResult(ok=False, error=f"source folder missing: {src}")

    dest.mkdir(parents=True, exist_ok=True)
    use_robocopy = (
        sys.platform == "win32"
        and shutil.which("robocopy")
        and not path_has_brackets(src)
        and not path_has_brackets(dest)
    )
    if use_robocopy:
        robocopy = shutil.which("robocopy")
        cmd = [
            robocopy,
            str(src),
            str(dest),
            "/E",
            "/R:3",
            "/W:2",
            "/MT:8",
            "/NFL",
            "/NDL",
            "/NJH",
            "/NJS",
        ]
        for attempt in range(max_retries):
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, creationflags=_subprocess_flags())
            except OSError as exc:
                if attempt + 1 >= max_retries:
                    return CopyResult(ok=False, error=str(exc))
                time.sleep(2 * (attempt + 1))
                continue
            if result.returncode < 8:
                return CopyResult(ok=True)
            if attempt + 1 >= max_retries:
                break
            time.sleep(2 * (attempt + 1))

    copied = 0
    last_error = ""
    for file in sorted(src.rglob("*")):
        if not file.is_file():
            continue
        rel = file.relative_to(src)
        target = dest / rel
        result = copy_file_robust(file, target, max_retries=max_retries)
        if result.ok:
            copied += 1
        else:
            last_error = result.error
    if copied == 0 and last_error:
        return CopyResult(ok=False, error=last_error)
    return CopyResult(ok=True)


def scan_directory(root: Path, extensions: Iterable[str] | None = None) -> dict[str, FileInfo]:
    """Build a map of relative_path -> FileInfo for all matching files."""
    root = normalize_path(root)
    files: dict[str, FileInfo] = {}
    for path in iter_files(root, extensions):
        rel = relative_to(path, root)
        stat = path.stat()
        files[rel] = FileInfo(relative_path=rel, size=stat.st_size, mtime=stat.st_mtime)
    return files


def format_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} {unit}"
        n /= 1024
    return f"{n:.1f} PB"
