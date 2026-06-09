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
    with path.open("rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


def safe_file_size(path: Path) -> int | None:
    try:
        return path.stat().st_size
    except OSError:
        return None


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
    hasher = hashlib.sha256() if compute_hash else None
    with src.open("rb") as fin, dest.open("wb") as fout:
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


def _robocopy_single_file(src: Path, dest: Path) -> bool:
    """Windows robocopy — often more reliable than Python copy on SD/USB drives."""
    robocopy = shutil.which("robocopy")
    if not robocopy or sys.platform != "win32":
        return False

    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        robocopy,
        str(src.parent),
        str(dest.parent),
        src.name,
        "/COPY:DAT",
        "/DCOPY:DAT",
        "/R:3",
        "/W:3",
        "/NFL",
        "/NDL",
        "/NJH",
        "/NJS",
        "/NC",
        "/NS",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, creationflags=_subprocess_flags())
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
) -> str | None:
    """
    Copy a file with retries for flaky SD/USB drives.

    Uses robocopy on Windows when available, otherwise chunked I/O.
    Returns source sha256 when compute_hash=True (single pass over source).
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_name(dest.name + ".partial")
    last_error: OSError | None = None

    for attempt in range(max_retries):
        partial.unlink(missing_ok=True)
        try:
            if _robocopy_single_file(src, dest):
                if compute_hash:
                    return sha256_file_with_retry(
                        src,
                        max_retries=max_retries,
                        retry_delay=retry_delay,
                    )
                return None

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
            partial.replace(dest)
            return src_hash
        except OSError as exc:
            last_error = exc
            partial.unlink(missing_ok=True)
            if attempt + 1 < max_retries and _is_transient_copy_error(exc):
                time.sleep(retry_delay * (attempt + 1))
                continue
            raise

    if last_error is not None:
        raise last_error
    return None


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
