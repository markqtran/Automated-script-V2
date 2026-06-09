"""Full setup verification — config, drives, rclone, Google Drive, Premiere."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from .app_paths import default_config_path, resource_path
from .config_loader import merge_user_settings
from .drive_settings import is_drive_na
from .premiere_launch import find_premiere_exe
from .rclone_setup import is_rclone_configured, rclone_is_installed

CheckStatus = Literal["pass", "fail", "warn", "skip"]


@dataclass
class SetupCheck:
    label: str
    status: CheckStatus
    detail: str
    required: bool = True


@dataclass
class SetupVerification:
    checks: list[SetupCheck] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return all(c.status != "fail" for c in self.checks if c.required)

    @property
    def pass_count(self) -> int:
        return sum(1 for c in self.checks if c.status == "pass")

    @property
    def fail_count(self) -> int:
        return sum(1 for c in self.checks if c.status == "fail")

    @property
    def warn_count(self) -> int:
        return sum(1 for c in self.checks if c.status == "warn")

    def summary(self) -> str:
        if self.ready and self.warn_count == 0:
            return "All checks passed — you're ready to use Footage Workflow."
        if self.ready:
            return (
                f"Ready with {self.warn_count} warning(s). "
                "You can run workflows; fix warnings when convenient."
            )
        return f"{self.fail_count} required check(s) failed — see details below."


def _add(checks: list[SetupCheck], label: str, status: CheckStatus, detail: str, *, required: bool = True) -> None:
    checks.append(SetupCheck(label=label, status=status, detail=detail, required=required))


def _check_drive(
    checks: list[SetupCheck],
    label: str,
    path: str,
    *,
    required: bool,
) -> None:
    if is_drive_na(path) or not str(path).strip():
        if required:
            _add(checks, label, "fail", "Not configured — set a drive letter in Quick Setup.")
        else:
            _add(checks, label, "skip", "Not used (N/A).", required=False)
        return

    root = Path(str(path).strip())
    if not root.exists():
        _add(
            checks,
            label,
            "warn" if required else "skip",
            f"{root} is not connected right now. Plug it in before filming.",
            required=False,
        )
        return

    _add(checks, label, "pass", f"Connected at {root}")


def verify_full_setup(cfg: dict, *, settings_override: dict | None = None) -> SetupVerification:
    """Run all setup checks. Optional settings_override applies unsaved wizard values."""
    if settings_override:
        cfg = merge_user_settings(deepcopy(cfg), settings_override)

    checks: list[SetupCheck] = []
    config_path = default_config_path()

    if config_path.is_file():
        _add(checks, "Configuration file", "pass", f"Saved at {config_path}")
    else:
        _add(checks, "Configuration file", "fail", "Missing — click Install Everything in Quick Setup.")

    scripts_id = (cfg.get("scripts") or {}).get("folder_id", "")
    if scripts_id:
        _add(checks, "[01] Scripts folder ID", "pass", scripts_id)
    else:
        _add(checks, "[01] Scripts folder ID", "fail", "Paste the Scripts Google Drive folder link.")

    proxies_id = (cfg.get("google_drive") or {}).get("folder_id", "")
    if proxies_id:
        _add(checks, "[04] Proxies folder ID", "pass", proxies_id)
    else:
        _add(checks, "[04] Proxies folder ID", "fail", "Paste the Proxies/Project Google Drive folder link.")

    sd = cfg.get("sd_cards") or {}
    dest = cfg.get("destinations") or {}

    _check_drive(checks, "SD card (primary)", sd.get("primary", ""), required=True)
    _check_drive(checks, "SD card (backup)", sd.get("backup", ""), required=False)
    _check_drive(checks, "Editing SSD", dest.get("ssd_editing", ""), required=True)
    _check_drive(checks, "Backup HDD", dest.get("hdd_backup", ""), required=True)
    _check_drive(checks, "Mirror HDD", dest.get("hdd_backup_mirror", ""), required=False)

    if rclone_is_installed():
        _add(checks, "Google Drive tools (rclone)", "pass", "Installed")
    else:
        _add(
            checks,
            "Google Drive tools (rclone)",
            "fail",
            "Not installed — click Install Everything in Quick Setup.",
        )

    if is_rclone_configured("gdrive"):
        _add(checks, "Google sign-in", "pass", "Signed in to Google Drive")
    else:
        _add(
            checks,
            "Google sign-in",
            "fail",
            "Not finished — complete sign-in, then verify again.",
        )

    if scripts_id and is_rclone_configured("gdrive") and rclone_is_installed():
        try:
            from .gdrive import list_drive_files

            files = list_drive_files(cfg, scripts_id)
            if files:
                _add(
                    checks,
                    "Scripts folder access",
                    "pass",
                    f"Can read folder — {len(files)} file(s) found",
                )
            else:
                _add(
                    checks,
                    "Scripts folder access",
                    "warn",
                    "Connected but folder looks empty. Check sharing/access.",
                    required=False,
                )
        except Exception as exc:
            _add(checks, "Scripts folder access", "fail", str(exc))

    if proxies_id and is_rclone_configured("gdrive") and rclone_is_installed():
        try:
            from .gdrive import list_drive_files

            list_drive_files(cfg, proxies_id)
            _add(checks, "Proxies folder access", "pass", "Can read upload folder")
        except Exception as exc:
            _add(checks, "Proxies folder access", "fail", str(exc))

    premiere = find_premiere_exe(cfg)
    if premiere:
        _add(checks, "Adobe Premiere Pro", "pass", str(premiere))
    else:
        _add(
            checks,
            "Adobe Premiere Pro",
            "warn",
            "Not found — install Premiere or set premiere.exe_path in config.",
            required=False,
        )

    template = resource_path("templates") / "project_template.prproj"
    if template.is_file():
        _add(checks, "Project template", "pass", str(template))
    else:
        _add(
            checks,
            "Project template",
            "warn",
            "templates/project_template.prproj missing — Premiere projects won't use your preset layout.",
            required=False,
        )

    return SetupVerification(checks=checks)


def format_verification_report(result: SetupVerification) -> str:
    icons = {"pass": "[OK]", "fail": "[FAIL]", "warn": "[WARN]", "skip": "[--]"}
    lines = [result.summary(), ""]
    for check in result.checks:
        icon = icons[check.status]
        lines.append(f"{icon} {check.label}")
        if check.detail:
            lines.append(f"     {check.detail}")
    return "\n".join(lines)
