"""GUI confirmation dialogs (thread-safe for background workers)."""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox


def gui_confirm_hook(root: tk.Misc):
    """Return a confirm function safe to call from worker threads."""

    def confirm(message: str, default: bool = False) -> bool:
        result: list[bool] = [default]
        done = threading.Event()

        def ask() -> None:
            result[0] = messagebox.askyesno(
                "Footage Workflow",
                message,
                default=messagebox.YES if default else messagebox.NO,
                parent=root,  # type: ignore[arg-type]
            )
            done.set()

        root.after(0, ask)
        done.wait(timeout=600)
        return result[0]

    return confirm
