"""Show setup verification results."""

from __future__ import annotations

import tkinter as tk
from tkinter import scrolledtext, ttk

from ..setup_verify import SetupVerification, format_verification_report
from .theme import style_toplevel, pill_button


class VerifySetupDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc, result: SetupVerification) -> None:
        super().__init__(master)
        self.title("Setup verification")
        self.resizable(True, True)
        style_toplevel(self)

        outer = ttk.Frame(self, padding=16)
        outer.pack(fill="both", expand=True)

        title = "Setup complete" if result.ready else "Setup incomplete"
        style = "SectionTitle.TLabel"
        ttk.Label(outer, text=title, style=style).pack(anchor="w")

        summary = result.summary()
        summary_style = "Muted.TLabel" if result.ready else "SectionTitle.TLabel"
        ttk.Label(outer, text=summary, wraplength=520, style=summary_style).pack(
            anchor="w", pady=(4, 10)
        )

        text = scrolledtext.ScrolledText(outer, width=64, height=18, wrap="word", font=("Consolas", 9))
        text.pack(fill="both", expand=True)
        text.insert("1.0", format_verification_report(result))
        text.configure(state="disabled")

        pill_button(outer, "Close", self.destroy, variant="primary", width=100).pack(anchor="e", pady=(12, 0))

        self.transient(master)
        self.grab_set()


def show_verify_results(parent: tk.Misc, result: SetupVerification) -> None:
    VerifySetupDialog(parent, result)
