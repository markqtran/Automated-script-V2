"""Settings dialog — drive letters and Google Drive folder links."""

from __future__ import annotations

import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk
from typing import Callable

from ..drive_settings import drive_combo_options, normalize_drive_value
from ..config_loader import (
    config_to_gui_settings,
    default_config_template,
    extract_folder_id,
    load_config,
    merge_user_settings,
    save_config,
)
from .theme import style_toplevel, pill_button

DRIVE_FIELDS = [
    ("sd_primary", "SD card (main slot)", "sd_cards", "primary"),
    ("sd_backup", "SD card (backup — N/A if none)", "sd_cards", "backup"),
    ("ssd_editing", "Editing SSD (Premiere)", "destinations", "ssd_editing"),
    ("hdd_backup", "Backup hard drive", "destinations", "hdd_backup"),
    ("hdd_mirror", "Second HDD mirror (N/A if none)", "destinations", "hdd_backup_mirror"),
]

OPTIONAL_DRIVE_KEYS = {"sd_backup", "hdd_mirror"}

SCRIPTS_HELP_URL = "https://drive.google.com/drive/folders/1RUebu5qPaac66hkgrJq5O0fz4guteIHP"
PROXIES_HELP_URL = "https://drive.google.com/drive/folders/1RWdJVs4LJKNMoDrRUTendfhD0uYy6VVl"


class SettingsDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc, on_saved: Callable[[], None] | None = None) -> None:
        super().__init__(master)
        self.title("Settings")
        self.resizable(False, False)
        self.on_saved = on_saved
        self._drive_vars: dict[str, tk.StringVar] = {}
        self._combos: dict[str, ttk.Combobox] = {}
        self._scripts_var = tk.StringVar()
        self._proxies_var = tk.StringVar()
        self._scripts_id_var = tk.StringVar(value="")
        self._proxies_id_var = tk.StringVar(value="")

        style_toplevel(self)
        self._build()
        self._load_values()
        self.transient(master)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

    def _build(self) -> None:
        pad = {"padx": 12, "pady": 4}
        outer = ttk.Frame(self, padding=12)
        outer.grid(row=0, column=0, sticky="nsew")

        drives_frame = ttk.LabelFrame(outer, text="  Drive letters  ", style="Card.TLabelframe", padding=10)
        drives_frame.grid(row=0, column=0, sticky="ew", **pad)

        ttk.Label(
            drives_frame,
            text="Plug in your drives, then pick the matching letter for each role.",
            wraplength=420,
            style="Muted.TLabel",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

        for row, (key, label, _section, _field) in enumerate(DRIVE_FIELDS, start=1):
            ttk.Label(drives_frame, text=label).grid(row=row, column=0, sticky="w", pady=2)
            var = tk.StringVar()
            self._drive_vars[key] = var
            combo = ttk.Combobox(drives_frame, textvariable=var, width=8, state="readonly")
            combo.grid(row=row, column=1, sticky="w", padx=(8, 0), pady=2)
            self._combos[key] = combo

        pill_button(
            drives_frame, "Refresh drives", self._refresh_drives, variant="accent"
        ).grid(row=len(DRIVE_FIELDS) + 1, column=0, columnspan=2, pady=(10, 0), sticky="w")

        google_frame = ttk.LabelFrame(outer, text="  Google Drive folders  ", style="Card.TLabelframe", padding=10)
        google_frame.grid(row=1, column=0, sticky="ew", **pad)

        ttk.Label(
            google_frame,
            text="Paste the full folder link from your browser (or just the folder ID).",
            wraplength=420,
            style="Muted.TLabel",
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))

        ttk.Label(google_frame, text="[01] Scripts folder").grid(row=1, column=0, sticky="w")
        scripts_entry = ttk.Entry(google_frame, textvariable=self._scripts_var, width=48)
        scripts_entry.grid(row=1, column=1, sticky="ew", padx=(8, 4))
        scripts_entry.bind("<KeyRelease>", lambda _e: self._update_id_preview("scripts"))
        pill_button(
            google_frame, "Open", lambda: webbrowser.open(SCRIPTS_HELP_URL), variant="ghost", width=64
        ).grid(row=1, column=2)
        ttk.Label(google_frame, textvariable=self._scripts_id_var, style="Muted.TLabel").grid(
            row=2, column=1, sticky="w", padx=(8, 0)
        )

        ttk.Label(google_frame, text="[04] Proxies / Project").grid(row=3, column=0, sticky="w", pady=(8, 0))
        proxies_entry = ttk.Entry(google_frame, textvariable=self._proxies_var, width=48)
        proxies_entry.grid(row=3, column=1, sticky="ew", padx=(8, 4), pady=(8, 0))
        proxies_entry.bind("<KeyRelease>", lambda _e: self._update_id_preview("proxies"))
        pill_button(
            google_frame, "Open", lambda: webbrowser.open(PROXIES_HELP_URL), variant="ghost", width=64
        ).grid(row=3, column=2, pady=(8, 0))
        ttk.Label(google_frame, textvariable=self._proxies_id_var, style="Muted.TLabel").grid(
            row=4, column=1, sticky="w", padx=(8, 0)
        )

        google_frame.columnconfigure(1, weight=1)

        ttk.Label(
            outer,
            text="Change drive letters here. For full install use  Quick Setup  on the main window.",
            wraplength=420,
            style="Muted.TLabel",
        ).grid(row=2, column=0, sticky="w", **pad)

        btn_frame = ttk.Frame(outer)
        btn_frame.grid(row=3, column=0, sticky="e", pady=(8, 0))
        pill_button(btn_frame, "Cancel", self._on_cancel, variant="ghost").grid(row=0, column=0, padx=4)
        pill_button(btn_frame, "Save", self._on_save, variant="primary", width=100).grid(row=0, column=1)

        self._refresh_drives()

    def _refresh_drives(self) -> None:
        for key, combo in self._combos.items():
            combo["values"] = drive_combo_options(include_na=key in OPTIONAL_DRIVE_KEYS)
            current = combo.get()
            if current and current not in combo["values"]:
                combo.set(combo["values"][0])

    def _load_values(self) -> None:
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
            f"https://drive.google.com/drive/folders/{scripts_id}" if scripts_id else ""
        )
        self._proxies_var.set(
            f"https://drive.google.com/drive/folders/{proxies_id}" if proxies_id else ""
        )
        self._update_id_preview("scripts")
        self._update_id_preview("proxies")
        self._refresh_drives()

    def _update_id_preview(self, which: str) -> None:
        if which == "scripts":
            folder_id = extract_folder_id(self._scripts_var.get())
            self._scripts_id_var.set(f"Folder ID: {folder_id}" if folder_id else "")
        else:
            folder_id = extract_folder_id(self._proxies_var.get())
            self._proxies_id_var.set(f"Folder ID: {folder_id}" if folder_id else "")

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

    def _on_save(self) -> None:
        settings = self._collect_settings()
        if not settings["scripts_folder_id"]:
            messagebox.showerror("Missing link", "Paste the [01] Scripts Google Drive folder link.")
            return
        if not settings["google_drive_folder_id"]:
            messagebox.showerror(
                "Missing link",
                "Paste the [04] Proxies/Project Google Drive folder link.",
            )
            return

        try:
            try:
                cfg = load_config()
            except (FileNotFoundError, ValueError):
                cfg = default_config_template()
            merged = merge_user_settings(cfg, settings)
            path = save_config(merged)
        except OSError as exc:
            messagebox.showerror("Save failed", str(exc))
            return

        messagebox.showinfo("Saved", f"Settings saved to:\n{path}")
        if self.on_saved:
            self.on_saved()
        self.destroy()

    def _on_cancel(self) -> None:
        self.destroy()


def open_settings(parent: tk.Misc, on_saved: Callable[[], None] | None = None) -> None:
    SettingsDialog(parent, on_saved=on_saved)
