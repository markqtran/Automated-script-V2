"""Main GUI launcher for Footage Workflow."""

from __future__ import annotations

import sys
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

from click.testing import CliRunner

from ..app_paths import default_config_path, ensure_user_config
from ..config_loader import load_config
from ..setup_status import setup_status
from ..setup_verify import verify_full_setup
from ..interactive import set_confirm_hook
from .prompts import gui_confirm_hook
from .setup_wizard import open_quick_setup
from .settings_dialog import open_settings
from .theme import apply_theme, configure_log_text, make_header, pill_button
from .verify_dialog import show_verify_results


class FootageWorkflowApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Footage Workflow")
        self.minsize(720, 560)
        self.geometry("780x620")

        apply_theme(self)

        set_confirm_hook(gui_confirm_hook(self))

        self._script_var = tk.StringVar()
        self._busy = False
        self._runner = CliRunner()

        self._build()
        self._check_first_run()

    def _build(self) -> None:
        make_header(self, "Footage Workflow", "Filming → edit → backup").pack(fill="x")

        toolbar = ttk.Frame(self, padding=(20, 12, 20, 8))
        toolbar.pack(fill="x")

        script_box = ttk.Frame(toolbar)
        script_box.pack(side="left")
        ttk.Label(script_box, text="Script #", style="Toolbar.TLabel", font=("Segoe UI", 10, "bold")).pack(
            side="left"
        )
        script_entry = ttk.Entry(script_box, textvariable=self._script_var, width=10, font=("Segoe UI", 11))
        script_entry.pack(side="left", padx=(10, 0))

        pill_button(toolbar, "Settings", self._open_settings, variant="ghost").pack(side="right")
        pill_button(toolbar, "Verify Setup", self._verify_setup, variant="secondary").pack(
            side="right", padx=(0, 10)
        )
        pill_button(
            toolbar, "Quick Setup", self._open_quick_setup, variant="accent"
        ).pack(side="right", padx=(0, 10))

        body = ttk.Frame(self, padding=(20, 0, 20, 12))
        body.pack(fill="both", expand=True)

        full = ttk.LabelFrame(body, text="  One-click full day  ", style="Card.TLabelframe", padding=16)
        full.pack(fill="x", pady=(0, 12))

        pill_button(
            full,
            "Run Full Workflow",
            self._cmd_full_workflow,
            variant="primary",
            width=200,
        ).pack(anchor="w")

        split = ttk.LabelFrame(body, text="  Split workflow  ", style="Card.TLabelframe", padding=16)
        split.pack(fill="x", pady=(0, 12))

        split_row = ttk.Frame(split)
        split_row.pack(fill="x")

        pill_button(
            split_row,
            "Phase 1 — Ingest & Premiere",
            self._cmd_phase_one,
            variant="primary",
            width=220,
        ).pack(side="left", padx=(0, 10))

        pill_button(
            split_row,
            "Phase 2 — Proxies & Upload",
            self._cmd_phase_two,
            variant="primary",
            width=220,
        ).pack(side="left")

        ttk.Label(
            split,
            text="Phase 1 copies SD → SSD/HDD and opens Premiere (no proxies).\n"
            "Phase 2 waits for proxies, backs up to HDD, and uploads to Drive.",
            style="Muted.TLabel",
            wraplength=680,
        ).pack(anchor="w", pady=(10, 0))

        actions = ttk.LabelFrame(body, text="  Individual steps  ", style="Card.TLabelframe", padding=14)
        actions.pack(fill="x", pady=(0, 12))

        buttons = [
            ("List scripts", self._cmd_list_scripts),
            ("New project", self._cmd_new_project),
            ("Daily ingest", self._cmd_daily),
            ("Compare SD cards", self._cmd_compare_sd),
            ("Upload to Drive", self._cmd_upload),
            ("Watch & upload", self._cmd_watch_upload),
        ]

        for col, (label, handler) in enumerate(buttons):
            pill_button(actions, label, handler, variant="secondary", width=130).grid(
                row=0, column=col, padx=5, pady=6
            )
        for col in range(len(buttons)):
            actions.columnconfigure(col, weight=1)

        log_frame = ttk.LabelFrame(body, text="  Output  ", style="Card.TLabelframe", padding=10)
        log_frame.pack(fill="both", expand=True)

        self._log = scrolledtext.ScrolledText(log_frame, height=14, wrap="word", state="disabled")
        configure_log_text(self._log)
        self._log.pack(fill="both", expand=True)

        status_bar = ttk.Frame(self, style="Header.TFrame", padding=(20, 8))
        status_bar.pack(fill="x", side="bottom")
        self._status_var = tk.StringVar(value="Ready")
        ttk.Label(status_bar, textvariable=self._status_var, style="HeaderMuted.TLabel").pack(side="left")

    def _check_first_run(self) -> None:
        ensure_user_config()
        status = setup_status()

        if status["complete"]:
            self._append_log(f"Config: {default_config_path()}\n")
            self._append_log("Ready — enter a script number and choose an action.\n\n")
            return

        self._append_log("First-time setup required.\n")
        self._append_log("Click  Quick Setup  →  Install Everything  (one-time, ~2 minutes).\n\n")
        self.after(400, self._open_quick_setup)

    def _open_quick_setup(self) -> None:
        open_quick_setup(self, on_done=self._on_setup_done)

    def _verify_setup(self) -> None:
        if self._busy:
            messagebox.showinfo("Busy", "Wait for the current task to finish.")
            return

        self._append_log("\nChecking setup…\n")
        self._set_busy(True)

        def worker() -> None:
            try:
                ensure_user_config()
                cfg = load_config()
                result = verify_full_setup(cfg)
                self.after(0, lambda: show_verify_results(self, result))
                self.after(0, self._append_log, f"{result.summary()}\n\n")
                if result.ready:
                    self.after(0, lambda: self._status_var.set("Ready"))
            except (FileNotFoundError, ValueError) as exc:
                self.after(
                    0,
                    lambda: messagebox.showwarning(
                        "Setup required",
                        f"{exc}\n\nOpen Quick Setup to install everything.",
                    ),
                )
                self.after(0, self._append_log, f"Setup check failed: {exc}\n\n")
            except Exception as exc:
                self.after(0, self._append_log, f"Setup check failed: {exc}\n\n")
            finally:
                self.after(0, self._set_busy, False)

        threading.Thread(target=worker, daemon=True).start()

    def _on_setup_done(self) -> None:
        if setup_status()["complete"]:
            self._append_log("Setup complete — you're ready to go.\n\n")
        else:
            self._append_log("Setup not finished — open Quick Setup to continue.\n\n")

    def _open_settings(self) -> None:
        open_settings(self, on_saved=self._on_settings_saved)

    def _on_settings_saved(self) -> None:
        self._append_log(f"Settings updated → {default_config_path()}\n")

    def _require_script_number(self) -> str | None:
        number = self._script_var.get().strip()
        if not number:
            messagebox.showwarning("Script number", "Enter a 3-digit script number (e.g. 003).")
            return None
        if not number.isdigit():
            messagebox.showwarning("Script number", "Script number should be digits only (e.g. 003).")
            return None
        return number.zfill(3) if len(number) < 3 else number

    def _cmd_list_scripts(self) -> None:
        self._run_command(["list-scripts"])

    def _cmd_full_workflow(self) -> None:
        number = self._require_script_number()
        if number:
            self._run_command(["workflow", "--number", number, "--watch-upload"])

    def _cmd_phase_one(self) -> None:
        number = self._require_script_number()
        if number:
            self._run_command(["workflow-phase1", "--number", number])

    def _cmd_phase_two(self) -> None:
        number = self._require_script_number()
        if number:
            self._run_command(["workflow-phase2", "--number", number])

    def _cmd_new_project(self) -> None:
        number = self._require_script_number()
        if number:
            self._run_command(["new-project", "--number", number, "--open-premiere"])

    def _cmd_daily(self) -> None:
        number = self._require_script_number()
        if number:
            self._run_command(["daily", "--number", number])

    def _cmd_compare_sd(self) -> None:
        self._run_command(["compare-sd"])

    def _cmd_upload(self) -> None:
        number = self._require_script_number()
        if number:
            self._run_command(["upload-drive", "--number", number])

    def _cmd_watch_upload(self) -> None:
        number = self._require_script_number()
        if number:
            self._run_command(["watch-upload", "--number", number])

    def _append_log(self, text: str) -> None:
        self._log.configure(state="normal")
        self._log.insert("end", text)
        self._log.see("end")
        self._log.configure(state="disabled")

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._status_var.set("Running…" if busy else "Ready")

    def _run_command(self, args: list[str]) -> None:
        if self._busy:
            messagebox.showinfo("Busy", "Wait for the current task to finish.")
            return

        if self._needs_drive(args) and not self._ensure_setup_ready():
            return

        config = str(default_config_path())
        full_args = ["--config", config, *args]

        self._append_log(f"\n{'─' * 50}\n> {' '.join(args)}\n{'─' * 50}\n")
        self._set_busy(True)

        def worker() -> None:
            from main import cli

            try:
                result = self._runner.invoke(cli, full_args, catch_exceptions=True)
                output = result.output or ""
                if result.exception:
                    output += f"\n[Error: {result.exception}]\n"
                self.after(0, self._append_log, output)
                self.after(0, self._append_log, f"\n[Exit code: {result.exit_code}]\n")
                if result.exception and "rclone" in str(result.exception).lower():
                    self.after(0, self._open_quick_setup)
            except Exception as exc:
                self.after(0, self._append_log, f"\n[Error: {exc}]\n")
            finally:
                self.after(0, self._set_busy, False)

        threading.Thread(target=worker, daemon=True).start()

    @staticmethod
    def _needs_drive(args: list[str]) -> bool:
        drive_commands = {
            "list-scripts",
            "new-project",
            "upload-drive",
            "watch-upload",
            "workflow",
            "workflow-phase1",
            "workflow-phase2",
        }
        return bool(args) and args[0] in drive_commands

    def _ensure_setup_ready(self) -> bool:
        if setup_status()["complete"]:
            return True
        if messagebox.askyesno(
            "Setup required",
            "Quick Setup is not complete yet.\n\nOpen setup now?",
        ):
            self._open_quick_setup()
        return False


def run_gui() -> None:
    if sys.platform == "win32":
        try:
            from ctypes import windll

            windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

    app = FootageWorkflowApp()
    app.mainloop()


if __name__ == "__main__":
    run_gui()
