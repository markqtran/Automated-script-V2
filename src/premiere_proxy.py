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


def _path_key(path: Path) -> str:
    return str(path).replace("\\", "/").lower()


def is_ingest_preset_path(path: Path) -> bool:
    """True for Premiere ingest / copy-and-proxy presets (not valid for encodeFile)."""
    key = _path_key(path)
    return "ingestpresets" in key


def _score_ingest_preset(path: Path) -> int:
    """Higher = better match for Create Proxies / ingest."""
    if not is_ingest_preset_path(path):
        return 0

    name = path.name.lower()
    parent = _path_key(path.parent)
    score = 0
    if "prores" in name and "proxy" in name:
        score += 12
    if "proxy" in name:
        score += 4
    if r"\proxy" in parent or parent.endswith("/proxy"):
        score += 10
    if "copy" in name or "copy and" in parent:
        score -= 12
    if "ndp" in name:
        score += 15
    return score


def _score_encode_preset(path: Path) -> int:
    """Higher = better match for Media Encoder encodeFile (export presets only)."""
    if is_ingest_preset_path(path):
        return -1000

    name = path.name.lower()
    parent = _path_key(path.parent)
    score = 0
    if "prores" in name and "proxy" in name:
        score += 14
    elif "prores" in name and "proxy" in parent:
        score += 8
    if "proxy" in name:
        score += 4
    if "quarter" in name or "720" in name:
        score += 3
    if "mediaio" in parent and "systempresets" in parent:
        score += 6
    if "quicktime" in parent or "apple" in parent:
        score += 4
    if "export" in parent or "presets" in parent:
        score += 3
    if "copy" in name:
        score -= 10
    if "ingest" in name:
        score -= 20
    if "ndp" in name and "encode" in name:
        score += 20
    return score


def _best_preset(candidates: list[Path], scorer) -> Path | None:
    if not candidates:
        return None
    best = max(candidates, key=scorer)
    if scorer(best) < 5:
        return None
    return best


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

    ingest_only = [p for p in _search_epr_files() if is_ingest_preset_path(p)]
    best = _best_preset(ingest_only, _score_ingest_preset)
    if best:
        return str(best.resolve()).replace("\\", "/")
    return ""


def resolve_encode_preset_path(cfg: dict) -> str:
    """Return encoding .epr for Media Encoder encodeFile (never ingest presets)."""
    premiere = cfg.get("premiere", {})
    explicit = premiere.get("proxy_encode_preset", "")
    if explicit:
        path = Path(explicit).expanduser()
        if path.is_file():
            return str(path.resolve()).replace("\\", "/")

    for name in ("NDP_Proxy_Encode.epr", "Proxy_Encode.epr"):
        candidate = Path("templates") / name
        if candidate.is_file():
            return str(candidate.resolve()).replace("\\", "/")

    export_candidates = [p for p in _search_epr_files() if not is_ingest_preset_path(p)]
    best = _best_preset(export_candidates, _score_encode_preset)
    if best:
        return str(best.resolve()).replace("\\", "/")
    return ""


def top_scored_presets(
    *,
    ingest: bool,
    limit: int = 15,
) -> list[tuple[int, Path]]:
    """Highest-scoring presets for CLI (ingest vs encode lists)."""
    rows: list[tuple[int, Path]] = []
    for path in _search_epr_files():
        score = _score_ingest_preset(path) if ingest else _score_encode_preset(path)
        if score >= 5:
            rows.append((score, path))
    rows.sort(key=lambda r: (-r[0], r[1].name.lower()))
    return rows[:limit]


def list_discovered_presets() -> list[tuple[str, Path]]:
    """Legacy: combined list (prefer top_scored_presets in CLI)."""
    rows: list[tuple[str, Path]] = []
    for score, path in top_scored_presets(ingest=True, limit=20):
        rows.append((f"{score:2d} ingest", path))
    for score, path in top_scored_presets(ingest=False, limit=20):
        rows.append((f"{score:2d} encode", path))
    return rows


def proxy_subfolder_name(cfg: dict) -> str:
    return cfg.get("proxies", {}).get("subfolder", "Proxies")


def auto_create_proxies(cfg: dict) -> bool:
    return cfg.get("premiere", {}).get("auto_create_proxies", True)
