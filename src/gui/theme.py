"""Premiere Pro / Apple-inspired dark theme for tkinter."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Literal

ButtonVariant = Literal["primary", "accent", "secondary", "ghost"]

COLORS = {
    "bg": "#1c1c1e",
    "bg_header": "#141416",
    "bg_panel": "#2c2c2e",
    "bg_input": "#3a3a3c",
    "bg_hover": "#48484a",
    "bg_soft": "#323234",
    "border": "#48484a",
    "text": "#f5f5f7",
    "text_muted": "#98989d",
    "accent": "#0a84ff",
    "accent_hover": "#409cff",
    "accent_pressed": "#0060df",
    "primary": "#1473e6",
    "primary_hover": "#2680eb",
    "primary_pressed": "#0d66d0",
    "log_bg": "#161618",
    "log_fg": "#d1d1d6",
    "select": "#0a84ff",
}

FONT_UI = ("Segoe UI", 10)
FONT_UI_BOLD = ("Segoe UI", 10, "bold")
FONT_TITLE = ("Segoe UI", 15, "bold")
FONT_SUBTITLE = ("Segoe UI", 11)
FONT_SMALL = ("Segoe UI", 9)
FONT_MONO = ("Cascadia Mono", 10)
FONT_MONO_FALLBACK = ("Consolas", 10)

_VARIANTS: dict[ButtonVariant, dict[str, str]] = {
    "primary": {
        "fill": COLORS["primary"],
        "hover": COLORS["primary_hover"],
        "pressed": COLORS["primary_pressed"],
        "text": "#ffffff",
    },
    "accent": {
        "fill": COLORS["accent"],
        "hover": COLORS["accent_hover"],
        "pressed": COLORS["accent_pressed"],
        "text": "#ffffff",
    },
    "secondary": {
        "fill": COLORS["bg_input"],
        "hover": COLORS["bg_hover"],
        "pressed": COLORS["bg_soft"],
        "text": COLORS["text"],
    },
    "ghost": {
        "fill": COLORS["bg_soft"],
        "hover": COLORS["bg_input"],
        "pressed": COLORS["bg_hover"],
        "text": COLORS["text"],
    },
}


class PillButton(tk.Frame):
    """Rounded pill button — flat, borderless, Apple-style."""

    def __init__(
        self,
        parent: tk.Misc,
        text: str = "",
        command: Callable[[], None] | None = None,
        *,
        variant: ButtonVariant = "secondary",
        width: int | None = None,
    ) -> None:
        bg = _widget_bg(parent)
        super().__init__(parent, bg=bg, highlightthickness=0, bd=0)
        self._text = text
        self._command = command
        self._variant = variant
        self._state = tk.NORMAL
        self._hover = False
        self._pressed = False
        self._min_width = width

        self._canvas = tk.Canvas(
            self,
            height=self._height,
            highlightthickness=0,
            bd=0,
            bg=bg,
            cursor="hand2",
        )
        self._canvas.pack(fill="both", expand=True)
        self._canvas.bind("<Configure>", self._draw)
        self._canvas.bind("<Enter>", self._on_enter)
        self._canvas.bind("<Leave>", self._on_leave)
        self._canvas.bind("<Button-1>", self._on_press)
        self._canvas.bind("<ButtonRelease-1>", self._on_release)
        self.after_idle(self._draw)

    @property
    def _height(self) -> int:
        return 40 if self._variant == "primary" else 36

    def _on_enter(self, _event: tk.Event) -> None:
        if str(self._state) != str(tk.DISABLED):
            self._hover = True
            self._draw()

    def _on_leave(self, _event: tk.Event) -> None:
        self._hover = False
        self._pressed = False
        self._draw()

    def _on_press(self, _event: tk.Event) -> None:
        if str(self._state) != str(tk.DISABLED):
            self._pressed = True
            self._draw()

    def _on_release(self, _event: tk.Event) -> None:
        if self._pressed and self._hover and self._command and str(self._state) != str(tk.DISABLED):
            self._command()
        self._pressed = False
        self._draw()

    def _fill_color(self) -> str:
        if str(self._state) == str(tk.DISABLED):
            return COLORS["bg_soft"]
        colors = _VARIANTS[self._variant]
        if self._pressed:
            return colors["pressed"]
        if self._hover:
            return colors["hover"]
        return colors["fill"]

    def _text_color(self) -> str:
        if str(self._state) == str(tk.DISABLED):
            return COLORS["text_muted"]
        return _VARIANTS[self._variant]["text"]

    def _draw(self, _event: tk.Event | None = None) -> None:
        self._canvas.delete("all")
        w = max(self._canvas.winfo_width(), self._min_width or 0, 72)
        h = self._height
        r = h // 2
        fill = self._fill_color()

        self._canvas.create_arc(0, 0, h, h, start=90, extent=180, fill=fill, outline=fill)
        self._canvas.create_arc(w - h, 0, w, h, start=270, extent=180, fill=fill, outline=fill)
        self._canvas.create_rectangle(r, 0, w - r, h, fill=fill, outline=fill)
        self._canvas.create_text(
            w // 2,
            h // 2,
            text=self._text,
            fill=self._text_color(),
            font=FONT_UI,
        )

    def configure(self, cnf: dict | None = None, **kwargs) -> None:  # type: ignore[override]
        if cnf:
            kwargs.update(cnf)
        if "text" in kwargs:
            self._text = kwargs.pop("text")
        if "command" in kwargs:
            self._command = kwargs.pop("command")
        if "state" in kwargs:
            self._state = kwargs.pop("state")
            self._canvas.configure(cursor="" if str(self._state) == str(tk.DISABLED) else "hand2")
        if kwargs:
            super().configure(**kwargs)
        self._draw()

    config = configure


def pill_button(
    parent: tk.Misc,
    text: str,
    command: Callable[[], None] | None = None,
    *,
    variant: ButtonVariant = "secondary",
    width: int | None = None,
) -> PillButton:
    return PillButton(parent, text=text, command=command, variant=variant, width=width)


def _widget_bg(widget: tk.Misc) -> str:
    if isinstance(widget, (ttk.Frame, ttk.LabelFrame)):
        try:
            style_name = widget.cget("style") or "TFrame"
            if "Header" in style_name:
                return COLORS["bg_header"]
            if style_name in ("TFrame", ""):
                return COLORS["bg"]
            return COLORS["bg_panel"]
        except tk.TclError:
            return COLORS["bg_panel"]
    try:
        return str(widget.cget("background"))
    except tk.TclError:
        return COLORS["bg_panel"]


def apply_theme(root: tk.Misc) -> ttk.Style:
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    c = COLORS
    root.configure(bg=c["bg"])

    style.configure(".", background=c["bg"], foreground=c["text"], font=FONT_UI)
    style.configure("TFrame", background=c["bg"])
    style.configure("Panel.TFrame", background=c["bg_panel"])
    style.configure("Header.TFrame", background=c["bg_header"])

    style.configure("TLabel", background=c["bg_panel"], foreground=c["text"], font=FONT_UI)
    style.configure("Toolbar.TLabel", background=c["bg"], foreground=c["text"], font=FONT_UI)
    style.configure("Header.TLabel", background=c["bg_header"], foreground=c["text"])
    style.configure("Title.TLabel", background=c["bg_header"], foreground=c["text"], font=FONT_TITLE)
    style.configure("Subtitle.TLabel", background=c["bg_header"], foreground=c["text_muted"], font=FONT_SMALL)
    style.configure("Muted.TLabel", background=c["bg_panel"], foreground=c["text_muted"], font=FONT_SMALL)
    style.configure("SectionTitle.TLabel", background=c["bg"], foreground=c["text"], font=FONT_UI_BOLD)
    style.configure("HeaderMuted.TLabel", background=c["bg_header"], foreground=c["text_muted"], font=FONT_SMALL)

    style.configure(
        "TLabelframe",
        background=c["bg_panel"],
        foreground=c["text_muted"],
        bordercolor=c["border"],
        relief="flat",
        borderwidth=1,
    )
    style.configure("TLabelframe.Label", background=c["bg_panel"], foreground=c["text_muted"], font=FONT_SMALL)
    style.configure("Card.TLabelframe", background=c["bg_panel"], foreground=c["text"], bordercolor=c["border"])
    style.configure("Card.TLabelframe.Label", background=c["bg_panel"], foreground=c["text"], font=FONT_UI_BOLD)

    style.configure(
        "TEntry",
        fieldbackground=c["bg_input"],
        foreground=c["text"],
        insertcolor=c["text"],
        bordercolor=c["border"],
        lightcolor=c["border"],
        darkcolor=c["border"],
        padding=6,
    )
    style.configure(
        "TCombobox",
        fieldbackground=c["bg_input"],
        background=c["bg_input"],
        foreground=c["text"],
        arrowcolor=c["text_muted"],
        bordercolor=c["border"],
        padding=4,
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", c["bg_input"])],
        selectbackground=[("readonly", c["select"])],
        selectforeground=[("readonly", "#ffffff")],
    )

    return style


def style_toplevel(window: tk.Toplevel) -> None:
    window.configure(bg=COLORS["bg"])


def configure_log_text(widget: tk.Text) -> None:
    c = COLORS
    font = FONT_MONO
    try:
        import tkinter.font as tkfont

        if "Cascadia Mono" not in tkfont.families():
            font = FONT_MONO_FALLBACK
    except Exception:
        font = FONT_MONO_FALLBACK

    widget.configure(
        bg=c["log_bg"],
        fg=c["log_fg"],
        insertbackground=c["text"],
        selectbackground=c["select"],
        selectforeground="#ffffff",
        relief="flat",
        borderwidth=0,
        highlightthickness=1,
        highlightbackground=c["border"],
        highlightcolor=c["accent"],
        font=font,
        padx=10,
        pady=8,
    )


def make_header(parent: tk.Misc, title: str, subtitle: str = "") -> ttk.Frame:
    bar = ttk.Frame(parent, style="Header.TFrame", padding=(20, 14))
    ttk.Label(bar, text=title, style="Title.TLabel").pack(anchor="w")
    if subtitle:
        ttk.Label(bar, text=subtitle, style="Subtitle.TLabel").pack(anchor="w", pady=(2, 0))
    return bar
