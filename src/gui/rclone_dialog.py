"""Google Drive one-time setup dialog."""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable

from ..rclone_setup import (
    download_rclone,
    is_rclone_configured,
    launch_rclone_config,
    rclone_is_installed,
)
from .theme import style_toplevel, pill_button


class GoogleDriveSetupDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc, on_done: Callable[[], None] | None = None) -> None:
        super().__init__(master)
        self.title("Setup Google Drive")
        self.resizable(False, False)
        self.on_done = on_done
        self._status_var = tk.StringVar(value="Checking…")

        style_toplevel(self)
        self._build()
        self._refresh_status()
        self.transient(master)
        self.grab_set()

    def _build(self) -> None:
        outer = ttk.Frame(self, padding=16)
        outer.grid(row=0, column=0)

        ttk.Label(
            outer,
            text="Google Drive is used to list scripts and upload proxies.",
            wraplength=420,
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))

        steps = ttk.LabelFrame(outer, text="  One-time setup  ", style="Card.TLabelframe", padding=12)
        steps.grid(row=1, column=0, sticky="ew", pady=(0, 12))

        ttk.Label(steps, text="1. Download rclone (Google Drive tool)").grid(row=0, column=0, sticky="w")
        self._download_btn = pill_button(
            steps, "Download rclone", self._download, variant="accent"
        )
        self._download_btn.grid(row=0, column=1, padx=(12, 0), sticky="e")

        ttk.Label(steps, text="2. Sign in with your Google account").grid(
            row=1, column=0, sticky="w", pady=(8, 0)
        )
        self._config_btn = pill_button(
            steps, "Sign in to Google", self._sign_in, variant="accent"
        )
        self._config_btn.grid(row=1, column=1, padx=(12, 0), pady=(8, 0), sticky="e")

        ttk.Label(
            steps,
            text="When rclone asks, name the remote: gdrive",
            style="Muted.TLabel",
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))

        ttk.Label(outer, textvariable=self._status_var, wraplength=420).grid(
            row=2, column=0, sticky="w", pady=(0, 12)
        )

        pill_button(outer, "Close", self._close, variant="ghost").grid(row=3, column=0, sticky="e")

    def _refresh_status(self) -> None:
        installed = rclone_is_installed()
        configured = is_rclone_configured("gdrive") if installed else False

        if configured:
            self._status_var.set("Ready — Google Drive is set up.")
            self._download_btn.configure(state="disabled")
            self._config_btn.configure(text="Re-configure", state="normal")
        elif installed:
            self._status_var.set("rclone installed. Click  Sign in to Google  to finish.")
            self._download_btn.configure(state="disabled")
            self._config_btn.configure(state="normal")
        else:
            self._status_var.set("Click  Download rclone  to get started.")
            self._download_btn.configure(state="normal")
            self._config_btn.configure(state="disabled")

    def _download(self) -> None:
        self._download_btn.configure(state="disabled")
        self._status_var.set("Downloading rclone…")

        def worker() -> None:
            try:
                def progress(msg: str) -> None:
                    self.after(0, self._status_var.set, msg)

                download_rclone(on_progress=progress)
                self.after(0, self._on_download_done, None)
            except Exception as exc:
                self.after(0, self._on_download_done, exc)

        threading.Thread(target=worker, daemon=True).start()

    def _on_download_done(self, error: Exception | None) -> None:
        if error:
            messagebox.showerror("Download failed", str(error), parent=self)
        else:
            messagebox.showinfo(
                "Download complete",
                "rclone is installed.\n\nNext: click  Sign in to Google  and name the remote  gdrive .",
                parent=self,
            )
        self._refresh_status()

    def _sign_in(self) -> None:
        try:
            launch_rclone_config("gdrive")
            messagebox.showinfo(
                "Sign in",
                "A terminal window opened.\n\n"
                "Follow the prompts and name your remote  gdrive .\n"
                "When finished, close this dialog and try  List scripts  again.",
                parent=self,
            )
        except Exception as exc:
            messagebox.showerror("Setup failed", str(exc), parent=self)
        self._refresh_status()

    def _close(self) -> None:
        if self.on_done:
            self.on_done()
        self.destroy()


def open_google_drive_setup(parent: tk.Misc, on_done: Callable[[], None] | None = None) -> None:
    GoogleDriveSetupDialog(parent, on_done=on_done)
