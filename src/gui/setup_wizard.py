"""One-click Quick Setup wizard."""

from __future__ import annotations

import threading
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk
from typing import Callable

from ..app_paths import ensure_user_config
from ..drive_settings import drive_combo_options, normalize_drive_value
from ..config_loader import (
    config_to_gui_settings,
    default_config_template,
    extract_folder_id,
    load_config,
    merge_user_settings,
    save_config,
)
from ..drive_detect import auto_assign_drives
from ..rclone_setup import (
    download_rclone,
    is_rclone_configured,
    launch_guided_google_signin,
    rclone_is_installed,
)
from ..setup_status import setup_status
from ..setup_verify import verify_full_setup
from .theme import style_toplevel, pill_button
from .verify_dialog import show_verify_results

SCRIPTS_HELP_URL = "https://drive.google.com/drive/folders/1RUebu5qPaac66hkgrJq5O0fz4guteIHP"
PROXIES_HELP_URL = "https://drive.google.com/drive/folders/1RWdJVs4LJKNMoDrRUTendfhD0uYy6VVl"

DRIVE_FIELDS = [
    ("sd_primary", "SD card (main slot)", "sd_cards", "primary"),
    ("sd_backup", "SD card (backup — N/A if none)", "sd_cards", "backup"),
    ("ssd_editing", "Editing SSD (Premiere)", "destinations", "ssd_editing"),
    ("hdd_backup", "Backup hard drive", "destinations", "hdd_backup"),
    ("hdd_mirror", "Second HDD mirror (N/A if none)", "destinations", "hdd_backup_mirror"),
]

OPTIONAL_DRIVE_KEYS = {"sd_backup", "hdd_mirror"}


class QuickSetupWizard(tk.Toplevel):
    """Single wizard: drives + Google links + one-click install."""

    def __init__(self, master: tk.Misc, on_done: Callable[[], None] | None = None) -> None:
        super().__init__(master)
        self.title("Quick Setup")
        self.resizable(False, False)
        self.on_done = on_done
        self._drive_vars: dict[str, tk.StringVar] = {}
        self._combos: dict[str, ttk.Combobox] = {}
        self._scripts_var = tk.StringVar()
        self._proxies_var = tk.StringVar()
        self._scripts_id_var = tk.StringVar(value="")
        self._proxies_id_var = tk.StringVar(value="")
        self._status_var = tk.StringVar(value="Plug in your drives, then click Install Everything.")
        self._installing = False

        style_toplevel(self)
        self._build()
        self._load_values()
        if not setup_status()["complete"]:
            self._auto_detect_drives()
        self.transient(master)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build(self) -> None:
        outer = ttk.Frame(self, padding=16)
        outer.grid(row=0, column=0)

        ttk.Label(
            outer,
            text="One-time setup — installs Google Drive tools and saves your drive letters.",
            wraplength=480,
            style="SectionTitle.TLabel",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))

        drives = ttk.LabelFrame(
            outer, text="  Your drives  ", style="Card.TLabelframe", padding=12
        )
        drives.grid(row=1, column=0, sticky="ew", pady=(0, 10))

        for row, (key, label, _section, _field) in enumerate(DRIVE_FIELDS, start=0):
            ttk.Label(drives, text=label).grid(row=row, column=0, sticky="w", pady=2)
            var = tk.StringVar()
            self._drive_vars[key] = var
            combo = ttk.Combobox(drives, textvariable=var, width=8, state="readonly")
            combo.grid(row=row, column=1, sticky="w", padx=(10, 0), pady=2)
            self._combos[key] = combo

        pill_button(
            drives, "Auto-detect drives", self._auto_detect_drives, variant="accent"
        ).grid(row=len(DRIVE_FIELDS), column=0, columnspan=2, sticky="w", pady=(10, 0))

        google = ttk.LabelFrame(outer, text="  Google Drive folders  ", style="Card.TLabelframe", padding=12)
        google.grid(row=2, column=0, sticky="ew", pady=(0, 10))

        ttk.Label(
            google,
            text="Paste the full folder link from your browser (or just the folder ID).",
            wraplength=480,
            style="Muted.TLabel",
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))

        ttk.Label(google, text="[01] Scripts folder").grid(row=1, column=0, sticky="w")
        scripts_entry = ttk.Entry(google, textvariable=self._scripts_var, width=52)
        scripts_entry.grid(row=1, column=1, sticky="ew", padx=(8, 4))
        scripts_entry.bind("<KeyRelease>", lambda _e: self._update_id_preview("scripts"))
        pill_button(
            google, "Open", lambda: webbrowser.open(SCRIPTS_HELP_URL), variant="ghost", width=64
        ).grid(row=1, column=2)
        ttk.Label(google, textvariable=self._scripts_id_var, style="Muted.TLabel").grid(
            row=2, column=1, sticky="w", padx=(8, 0)
        )

        ttk.Label(google, text="[04] Proxies / Project").grid(row=3, column=0, sticky="w", pady=(8, 0))
        proxies_entry = ttk.Entry(google, textvariable=self._proxies_var, width=52)
        proxies_entry.grid(row=3, column=1, sticky="ew", padx=(8, 4), pady=(8, 0))
        proxies_entry.bind("<KeyRelease>", lambda _e: self._update_id_preview("proxies"))
        pill_button(
            google, "Open", lambda: webbrowser.open(PROXIES_HELP_URL), variant="ghost", width=64
        ).grid(row=3, column=2, pady=(8, 0))
        ttk.Label(google, textvariable=self._proxies_id_var, style="Muted.TLabel").grid(
            row=4, column=1, sticky="w", padx=(8, 0)
        )

        google.columnconfigure(1, weight=1)

        progress = ttk.LabelFrame(outer, text="  Status  ", style="Card.TLabelframe", padding=12)
        progress.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        ttk.Label(progress, textvariable=self._status_var, wraplength=480).grid(row=0, column=0, sticky="w")

        btn_row = ttk.Frame(outer)
        btn_row.grid(row=4, column=0, sticky="e")

        self._verify_btn = pill_button(btn_row, "Verify Setup", self._verify, variant="secondary")
        self._verify_btn.grid(row=0, column=0, padx=4)

        self._install_btn = pill_button(
            btn_row,
            "Install Everything",
            self._install_everything,
            variant="primary",
            width=160,
        )
        self._install_btn.grid(row=0, column=1, padx=4)

        pill_button(btn_row, "Close", self._on_close, variant="ghost").grid(row=0, column=2, padx=4)

        self._refresh_drive_list()

        if setup_status()["complete"]:
            self._status_var.set("Setup already complete. Click Verify Setup to re-check anytime.")

    def _load_values(self) -> None:
        ensure_user_config()
        try:
            cfg = load_config()
        except (FileNotFoundError, ValueError):
            cfg = default_config_template()

        gui = config_to_gui_settings(cfg)
        for key, _label, section, field in DRIVE_FIELDS:
            self._drive_vars[key].set(gui[section][field])

        scripts_id = gui["scripts_folder_id"]
        proxies_id = gui["google_drive_folder_id"]
        self._scripts_var.set(
            f"https://drive.google.com/drive/folders/{scripts_id}" if scripts_id else SCRIPTS_HELP_URL
        )
        self._proxies_var.set(
            f"https://drive.google.com/drive/folders/{proxies_id}" if proxies_id else PROXIES_HELP_URL
        )
        self._update_id_preview("scripts")
        self._update_id_preview("proxies")
        self._refresh_drive_list()

    def _update_id_preview(self, which: str) -> None:
        if which == "scripts":
            folder_id = extract_folder_id(self._scripts_var.get())
            self._scripts_id_var.set(f"Folder ID: {folder_id}" if folder_id else "")
        else:
            folder_id = extract_folder_id(self._proxies_var.get())
            self._proxies_id_var.set(f"Folder ID: {folder_id}" if folder_id else "")

    def _refresh_drive_list(self) -> None:
        for key, combo in self._combos.items():
            combo["values"] = drive_combo_options(include_na=key in OPTIONAL_DRIVE_KEYS)

    def _auto_detect_drives(self) -> None:
        self._refresh_drive_list()
        guessed = auto_assign_drives()
        for key, _label, section, field in DRIVE_FIELDS:
            self._drive_vars[key].set(guessed[section][field])
        self._status_var.set("Drive letters auto-detected. Check them, then click Install Everything.")

    def _collect_settings(self) -> dict:
        sd_cards: dict[str, str] = {}
        destinations: dict[str, str] = {}
        for key, _label, section, field in DRIVE_FIELDS:
            value = normalize_drive_value(self._drive_vars[key].get())
            if section == "sd_cards":
                sd_cards[field] = value if value else "N/A"
            else:
                destinations[field] = value if value else "N/A"
        return {
            "sd_cards": sd_cards,
            "destinations": destinations,
            "scripts_folder_id": extract_folder_id(self._scripts_var.get()),
            "google_drive_folder_id": extract_folder_id(self._proxies_var.get()),
        }

    def _validate_google_links(self) -> bool:
        settings = self._collect_settings()
        if not settings["scripts_folder_id"]:
            messagebox.showerror(
                "Missing link",
                "Paste the [01] Scripts Google Drive folder link.",
                parent=self,
            )
            return False
        if not settings["google_drive_folder_id"]:
            messagebox.showerror(
                "Missing link",
                "Paste the [04] Proxies/Project Google Drive folder link.",
                parent=self,
            )
            return False
        return True

    def _install_everything(self) -> None:
        if self._installing:
            return

        if not self._validate_google_links():
            return

        settings = self._collect_settings()
        self._installing = True
        self._install_btn.configure(state="disabled")
        self._status_var.set("Installing…")

        def worker() -> None:
            try:
                self._step("Creating configuration…")
                ensure_user_config()
                try:
                    cfg = load_config()
                except (FileNotFoundError, ValueError):
                    cfg = default_config_template()
                merged = merge_user_settings(cfg, settings)
                save_config(merged)

                if not rclone_is_installed():
                    self._step("Downloading Google Drive tools…")
                    download_rclone(on_progress=lambda msg: self._step(msg))
                else:
                    self._step("Google Drive tools already installed.")

                if not is_rclone_configured("gdrive"):
                    self._step("Opening Google sign-in…")
                    launch_guided_google_signin("gdrive")
                    self._step(
                        "Sign in in the browser window that opened.\n"
                        "When finished, click Verify Setup."
                    )
                else:
                    self._step("Google Drive already signed in.")
                    self.after(0, self._verify)

            except Exception as exc:
                self.after(0, lambda: messagebox.showerror("Install failed", str(exc), parent=self))
                self.after(0, lambda: self._status_var.set(f"Install failed: {exc}"))
            finally:
                self.after(0, self._finish_install)

        threading.Thread(target=worker, daemon=True).start()

    def _step(self, message: str) -> None:
        self.after(0, lambda: self._status_var.set(message))

    def _finish_install(self) -> None:
        self._installing = False
        self._install_btn.configure(state="normal")

    def _verify(self) -> None:
        if self._installing:
            messagebox.showinfo("Busy", "Wait for Install Everything to finish.", parent=self)
            return

        self._verify_btn.configure(state="disabled")
        self._status_var.set("Checking setup…")

        settings = self._collect_settings()

        def worker() -> None:
            try:
                ensure_user_config()
                try:
                    cfg = load_config()
                except (FileNotFoundError, ValueError):
                    cfg = default_config_template()

                result = verify_full_setup(cfg, settings_override=settings)
                self.after(0, lambda: self._show_verify_result(result))
            except Exception as exc:
                self.after(
                    0,
                    lambda: messagebox.showerror("Verify failed", str(exc), parent=self),
                )
                self.after(0, lambda: self._status_var.set(f"Verify failed: {exc}"))
            finally:
                self.after(0, lambda: self._verify_btn.configure(state="normal"))

        threading.Thread(target=worker, daemon=True).start()

    def _show_verify_result(self, result) -> None:
        self._status_var.set(result.summary())
        show_verify_results(self, result)
        if result.ready and self.on_done:
            self.on_done()

    def _on_close(self) -> None:
        if self.on_done:
            self.on_done()
        self.destroy()


def open_quick_setup(parent: tk.Misc, on_done: Callable[[], None] | None = None) -> None:
    QuickSetupWizard(parent, on_done=on_done)
