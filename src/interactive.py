"""User confirmation — works in CLI (click) and GUI (tkinter hook)."""

from __future__ import annotations

from typing import Callable

_confirm_hook: Callable[[str, bool], bool] | None = None


def set_confirm_hook(hook: Callable[[str, bool], bool] | None) -> None:
    global _confirm_hook
    _confirm_hook = hook


def user_confirm(message: str, *, default: bool = False) -> bool:
    if _confirm_hook is not None:
        return _confirm_hook(message, default)
    import click

    return click.confirm(message, default=default)
