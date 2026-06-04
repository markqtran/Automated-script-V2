"""Resolve Premiere proxy / ingest preset paths for JSX automation."""

from __future__ import annotations

from pathlib import Path


def resolve_proxy_preset_path(cfg: dict) -> str:
    """Return .epr path for proxy encoding, or empty string to search in JSX."""
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
    return ""


def proxy_subfolder_name(cfg: dict) -> str:
    return cfg.get("proxies", {}).get("subfolder", "Proxies")


def auto_create_proxies(cfg: dict) -> bool:
    return cfg.get("premiere", {}).get("auto_create_proxies", True)
