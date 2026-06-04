"""Shared utilities for the footage workflow automation."""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

# Characters invalid in Windows file/folder names (colon, etc.)
_INVALID_WIN_NAME = re.compile(r'[<>:"/\\|?*]')


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
