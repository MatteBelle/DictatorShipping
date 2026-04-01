"""
Settings panel — plain tk.Toplevel (same pattern as history_window.py).

Why tk.Toplevel and not CTkToplevel: CTkToplevel on Windows resets the
WM_DELETE_WINDOW protocol, breaking the close button.
"""

import ctypes
import sys
import tkinter as tk

import customtkinter as ctk

# ── Design tokens (match app_window) ─────────────────────────────────────────
BG       = "#0b0d14"
SURFACE  = "#12141f"
SURFACE2 = "#181a28"
BORDER   = "#252840"
ACCENT   = "#6366f1"
ACCENT_HOVER = "#4f46e5"
ACCENT_MUTED = "#282b5c"
TEXT1    = "#e8eaf6"
TEXT2    = "#7b82a8"
TEXT3    = "#3d4261"

_FONT_FAMILY = (
    "Segoe UI Variable" if sys.platform == "win32"
    else "SF Pro Display" if sys.platform == "darwin"
    else "Ubuntu"
)

_WIN_W = 280
_WIN_H = 330


def _f(size: int, weight: str = "normal") -> tuple:
    """Return a font tuple for plain tk widgets."""
    return (_FONT_FAMILY, size, weight)


def _apply_dark_titlebar(win: tk.Toplevel) -> None:
    if sys.platform != "win32":
        return
    try:
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 20,
            ctypes.byref(ctypes.c_int(1)),
            ctypes.sizeof(ctypes.c_int(1)),
        )
    except Exception:
        pass


def _divider(parent: tk.Frame) -> None:
    tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", pady=(4, 0))


class SettingsWindow(tk.Toplevel):
    """
    Secondary settings panel.

    Parameters
    ----------
    parent   : AppWindow instance
    settings : config.settings.Settings
    """

    def __init__(self, parent, settings):
        super().__init__(parent)
        self._parent   = parent
        self._settings = settings

        self.title("Settings")
        self.resizable(False, False)
        self.configure(bg=BG)
        self.wm_attributes("-topmost", True)

        # Must be registered before anything can reset it
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build()

        self.update_idletasks()
        px = parent.winfo_x()
        py = parent.winfo_y()
        pw = parent.winfo_width()
        self.geometry(f"{_WIN_W}x{_WIN_H}+{px + pw + 10}+{py}")

        self.focus_force()
        self.after(0, lambda: _apply_dark_titlebar(self))

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        # ── Header ────────────────────────────────────────────────────
        header = tk.Frame(self, bg=BG)
        header.pack(fill="x", padx=14, pady=(14, 8))

        tk.Label(
            header,
            text="Settings",
            font=_f(14, "bold"),
            fg=TEXT1, bg=BG,
        ).pack(side="left")

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x", padx=14, pady=(0, 4))

        # ── Rows ──────────────────────────────────────────────────────
        content = tk.Frame(self, bg=BG)
        content.pack(fill="both", expand=True, padx=14, pady=(4, 14))

        # Always on top
        self._always_on_top_switch = self._build_switch_row(
            content,
            label="Always on top",
            key="always_on_top",
            callback=self._on_always_on_top,
        )

        _divider(content)

        # Auto-punctuation
        self._auto_punct_switch = self._build_switch_row(
            content,
            label="Auto-punct",
            key="auto_punctuation",
            callback=self._on_auto_punct,
            default=True,
        )

        _divider(content)

        # Mode
        self._build_mode_row(content)

        _divider(content)

        # Whisper model
        self._build_model_row(content)

        _divider(content)

        # Injection delay
        self._build_delay_row(content)

    def _build_switch_row(
        self, parent: tk.Frame, label: str, key: str, callback, default: bool = False
    ) -> ctk.CTkSwitch:
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=(8, 4))

        tk.Label(
            row, text=label,
            font=_f(14), fg=TEXT2, bg=BG,
            anchor="w", width=11,
        ).pack(side="left")

        host = tk.Frame(row, bg=BG)
        host.pack(side="right")

        switch = ctk.CTkSwitch(
            host, text="", command=callback,
            width=30, height=16,
            progress_color=ACCENT, button_color=TEXT1,
            button_hover_color="#ffffff", fg_color=BORDER,
        )
        switch.pack()

        if self._settings.get(key, default):
            switch.select()
        else:
            switch.deselect()

        return switch

    def _build_mode_row(self, parent: tk.Frame) -> None:
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=(8, 4))

        tk.Label(
            row, text="Mode",
            font=_f(14), fg=TEXT2, bg=BG,
            anchor="w", width=11,
        ).pack(side="left")

        host = tk.Frame(row, bg=BG)
        host.pack(side="right")

        self._mode_seg = ctk.CTkSegmentedButton(
            host,
            values=["Hold", "Toggle"],
            command=self._on_mode_change,
            width=100, height=20,
            font=ctk.CTkFont(family=_FONT_FAMILY, size=10),
            fg_color=SURFACE2,
            selected_color=ACCENT, selected_hover_color=ACCENT_HOVER,
            unselected_color=SURFACE2, unselected_hover_color=SURFACE,
            text_color=TEXT1,
        )
        self._mode_seg.pack()
        saved_mode = self._settings.get("recording_mode", "hold")
        self._mode_seg.set("Hold" if saved_mode == "hold" else "Toggle")

    def _build_model_row(self, parent: tk.Frame) -> None:
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=(8, 4))

        tk.Label(
            row, text="Whisper model",
            font=_f(14), fg=TEXT2, bg=BG,
            anchor="w", width=11,
        ).pack(side="left")

        host = tk.Frame(row, bg=BG)
        host.pack(side="right")

        self._model_combo = ctk.CTkComboBox(
            host,
            values=["tiny", "base", "small", "medium", "large"],
            command=self._on_model_change,
            width=85, height=20,
            fg_color=SURFACE2, border_color=BORDER,
            button_color=BORDER, button_hover_color=ACCENT_MUTED,
            dropdown_fg_color=SURFACE,
            font=ctk.CTkFont(family=_FONT_FAMILY, size=10),
            text_color=TEXT1,
        )
        self._model_combo.pack()
        self._model_combo.set(self._settings.get("whisper_model", "small"))

        # Note: model change takes effect on next restart
        note_row = tk.Frame(parent, bg=BG)
        note_row.pack(fill="x", pady=(0, 2))
        tk.Label(
            note_row,
            text="Takes effect on restart",
            font=_f(9),
            fg=TEXT3, bg=BG,
            anchor="e",
        ).pack(side="right")

    def _build_delay_row(self, parent: tk.Frame) -> None:
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=(8, 4))

        tk.Label(
            row, text="Inject delay",
            font=_f(14), fg=TEXT2, bg=BG,
            anchor="w", width=11,
        ).pack(side="left")

        right = tk.Frame(row, bg=BG)
        right.pack(side="right")

        self._delay_val_lbl = tk.Label(
            right,
            text=f"{self._settings.get('injection_delay_ms', 175)}ms",
            font=_f(11),
            fg=TEXT2, bg=BG,
            width=5, anchor="e",
        )
        self._delay_val_lbl.pack(side="right", padx=(4, 0))

        host = tk.Frame(right, bg=BG)
        host.pack(side="right")

        self._delay_slider = ctk.CTkSlider(
            host,
            from_=0, to=500,
            number_of_steps=50,
            command=self._on_delay_change,
            width=75, height=12,
            progress_color=ACCENT,
            button_color=ACCENT,
            button_hover_color=ACCENT_HOVER,
            fg_color=SURFACE2,
        )
        self._delay_slider.pack()
        self._delay_slider.set(self._settings.get("injection_delay_ms", 175))

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def _on_always_on_top(self):
        value = self._always_on_top_switch.get() == 1
        self._settings.set("always_on_top", value)
        self._parent.wm_attributes("-topmost", value)

    def _on_auto_punct(self):
        self._settings.set("auto_punctuation", self._auto_punct_switch.get() == 1)

    def _on_mode_change(self, value: str):
        self._parent._on_mode_change(value)

    def _on_model_change(self, value: str):
        self._settings.set("whisper_model", value)

    def _on_delay_change(self, value: float):
        ms = round(value / 10) * 10   # snap to 10ms increments
        self._settings.set("injection_delay_ms", ms)
        self._delay_val_lbl.configure(text=f"{ms}ms")

    # ── Close ─────────────────────────────────────────────────────────────────

    def _on_close(self) -> None:
        self.destroy()
