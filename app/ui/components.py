import tkinter as tk


def _contrast_text_for(bg_color, fallback="white"):
    if not isinstance(bg_color, str) or not bg_color.startswith("#") or len(bg_color) != 7:
        return fallback
    try:
        r = int(bg_color[1:3], 16)
        g = int(bg_color[3:5], 16)
        b = int(bg_color[5:7], 16)
    except ValueError:
        return fallback

    # Relative luminance estimate: brighter backgrounds should use dark text.
    luminance = (0.299 * r) + (0.587 * g) + (0.114 * b)
    return "#111111" if luminance >= 170 else "white"


def create_modern_button(
    parent,
    text,
    command,
    bg,
    hover,
    fg="white",
    active_bg=None,
    state="normal",
    hover_fg=None,
    active_fg=None,
):
    resolved_hover_fg = hover_fg if hover_fg is not None else _contrast_text_for(hover, fallback=fg)
    resolved_active_bg = hover if not active_bg else active_bg
    resolved_active_fg = (
        active_fg if active_fg is not None else _contrast_text_for(resolved_active_bg, fallback=fg)
    )

    btn = tk.Button(
        parent,
        text=text,
        command=command,
        font=("Segoe UI", 10, "bold"),
        bg=bg,
        fg=fg,
        activebackground=resolved_active_bg,
        activeforeground=resolved_active_fg,
        cursor="hand2",
        padx=15,
        pady=6,
        relief="flat",
        borderwidth=0,
        state=state,
    )

    btn._normal_bg = bg
    btn._hover_bg = hover
    btn._active_bg = resolved_active_bg
    btn._fg = fg
    btn._hover_fg = resolved_hover_fg
    btn._active_fg = resolved_active_fg
    btn._force_hover_fg = hover_fg is not None
    btn._force_active_fg = active_fg is not None

    def on_enter(_event):
        if btn["state"] == tk.NORMAL:
            btn.config(bg=btn._hover_bg, fg=btn._hover_fg)

    def on_leave(_event):
        if btn["state"] == tk.NORMAL:
            btn.config(bg=btn._normal_bg, fg=btn._fg)

    btn.bind("<Enter>", on_enter)
    btn.bind("<Leave>", on_leave)
    return btn


def update_button_theme(btn, bg=None, hover=None, active_bg=None, fg=None, hover_fg=None, active_fg=None):
    if bg is not None:
        btn._normal_bg = bg
    if hover is not None:
        btn._hover_bg = hover
    if active_bg is not None:
        btn._active_bg = active_bg
    if fg is not None:
        btn._fg = fg
    if hover_fg is not None:
        btn._hover_fg = hover_fg
        btn._force_hover_fg = True
    if active_fg is not None:
        btn._active_fg = active_fg
        btn._force_active_fg = True

    if not getattr(btn, "_force_hover_fg", False):
        btn._hover_fg = _contrast_text_for(btn._hover_bg, fallback=btn._fg)
    if not getattr(btn, "_force_active_fg", False):
        btn._active_fg = _contrast_text_for(btn._active_bg, fallback=btn._fg)

    btn.config(
        bg=btn._normal_bg,
        fg=btn._fg,
        activebackground=btn._active_bg,
        activeforeground=btn._active_fg,
    )
