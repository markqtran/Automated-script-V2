"""Resolve Premiere proxy / ingest preset paths for JSX automation."""

from __future__ import annotations

import os
from pathlib import Path


def _search_epr_files() -> list[Path]:
    """Find .epr presets under Adobe install and user Documents."""
    found: list[Path] = []
    roots: list[Path] = []

    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    roots.append(Path(program_files) / "Adobe")
    roots.append(Path.home() / "Documents" / "Adobe")

    for root in roots:
        if not root.exists():
            continue
        try:
            for path in root.rglob("*.epr"):
                if path.is_file():
                    found.append(path)
        except OSError:
            continue
    return found


def _score_preset(path: Path, *, ingest: bool) -> int:
    """Higher = better match for proxy workflow."""
    name = path.name.lower()
    parent = str(path.parent).lower()
    score = 0
    if "prores" in name and "proxy" in name:
        score += 10
    if "proxy" in name:
        score += 5
    if "quarter" in name or "720" in name or "25" in name:
        score += 3
    if ingest and "ingest" in name:
        score += 8
    if ingest and "ingest" in parent:
        score += 4
    if "ndp" in name:
        score += 15
    return score


def resolve_proxy_preset_path(cfg: dict) -> str:
    """Return ingest .epr path (Create Proxies dialog), or best guess from disk."""
    premiere = cfg.get("premiere", {})
    explicit = premiere.get("proxy_ingest_preset", "")
    if explicit:
        path = Path(explicit).expanduser()
        if path.is_file():
            return str(path.resolve()).replace("\\", "/")

    for name in ("NDP_Proxy_Ingest.epr", "Proxy_Ingest.epr", "ProRes_Proxy_Ingest.epr"):
        candidate = Path("templates") / name
        if candidate.is_file():
            return str(candidate.resolve()).replace("\\", "/")

    candidates = _search_epr_files()
    if not candidates:
        return ""

    best = max(candidates, key=lambda p: _score_preset(p, ingest=True))
    if _score_preset(best, ingest=True) >= 5:
        return str(best.resolve()).replace("\\", "/")
    return ""


def resolve_encode_preset_path(cfg: dict) -> str:
    """Return encoding .epr for Media Encoder queue (encodeFile fallback)."""
    premiere = cfg.get("premiere", {})
    explicit = premiere.get("proxy_encode_preset", "") or premiere.get("proxy_ingest_preset", "")
    if explicit:
        path = Path(explicit).expanduser()
        if path.is_file():
            return str(path.resolve()).replace("\\", "/")

    for name in ("NDP_Proxy_Encode.epr", "NDP_Proxy_Ingest.epr", "Proxy_Encode.epr"):
        candidate = Path("templates") / name
        if candidate.is_file():
            return str(candidate.resolve()).replace("\\", "/")

    candidates = _search_epr_files()
    if not candidates:
        return ""

    best = max(candidates, key=lambda p: _score_preset(p, ingest=False))
    if _score_preset(best, ingest=False) >= 5:
        return str(best.resolve()).replace("\\", "/")
    return ""


def list_discovered_presets() -> list[tuple[str, Path]]:
    """All .epr files with scores for CLI listing."""
    rows: list[tuple[str, Path]] = []
    for path in sorted(_search_epr_files(), key=lambda p: p.name.lower()):
        score = _score_preset(path, ingest=True)
        rows.append((f"{score:2d} ingest", path))
    return rows


def proxy_subfolder_name(cfg: dict) -> str:
    return cfg.get("proxies", {}).get("subfolder", "Proxies")


def auto_create_proxies(cfg: dict) -> bool:
    return cfg.get("premiere", {}).get("auto_create_proxies", True)
