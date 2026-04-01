"""
History panel — built entirely with plain tkinter (no CustomTkinter).

Why no CTk: CTkToplevel on Windows calls self.after(200, iconbitmap) which
resets the WM_DELETE_WINDOW protocol, making the close button a no-op.
CTkTextbox inside a plain Toplevel also fails to display text correctly
because CTk widgets expect a CTkToplevel parent for bg_color resolution.
"""

import ctypes
import sys
import tkinter as tk
import tkinter.messagebox as mb
from pathlib import Path

import pyperclip

# ── Design tokens (match app_window) ─────────────────────────────────────────
BG           = "#0b0d14"
SURFACE      = "#12141f"
SURFACE2     = "#181a28"
BORDER       = "#252840"
ACCENT       = "#6366f1"
ACCENT_HOVER = "#4f46e5"
C_DANGER     = "#ef4444"
C_DANGER_H   = "#dc2626"
TEXT1        = "#e8eaf6"
TEXT2        = "#7b82a8"
TEXT3        = "#3d4261"

_WIN_W  = 720    # window width in px
_CARD_H = 105    # approximate per-card height for initial sizing

_FONT_FAMILY = (
    "Segoe UI Variable" if sys.platform == "win32"
    else "SF Pro Display" if sys.platform == "darwin"
    else "Ubuntu"
)


def _f(size: int, bold: bool = False) -> tuple:
    return (_FONT_FAMILY, size, "bold" if bold else "normal")


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


class HistoryWindow(tk.Toplevel):
    """
    Floating panel showing recent dictation entries.

    Constructor args
    ----------------
    parent      : the AppWindow (tk.Tk subclass)
    history     : list of entry dicts [{text, elapsed, words, timestamp}, ...]
    config_dir  : Path — where history.json lives; shown in the clear dialog
    on_clear    : callable() — wipe all entries and close this window
    on_delete   : callable(entry: dict) — remove one entry from storage
    """

    def __init__(
        self,
        parent,
        history: list[dict],
        config_dir: Path,
        on_clear=None,
        on_delete=None,
    ):
        super().__init__(parent)
        self.title("History")
        self.resizable(True, True)
        self.configure(bg=BG)
        self.wm_attributes("-topmost", True)

        # Register close handler immediately — nothing in this class resets it.
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        self._config_dir  = config_dir
        self._on_clear_cb = on_clear
        self._on_delete_cb = on_delete
        self._history_ref = history          # live reference for Copy All
        self._entry_count = len(history)
        self._canvas: tk.Canvas | None = None

        self._build(history)

        self.update_idletasks()
        px = parent.winfo_x()
        py = parent.winfo_y()
        pw = parent.winfo_width()
        self.geometry(f"+{px + pw + 10}+{py}")
        self.focus_force()
        self.after(0, lambda: _apply_dark_titlebar(self))

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self, history: list[dict]) -> None:
        # ── Header ────────────────────────────────────────────────────
        header = tk.Frame(self, bg=BG)
        header.pack(fill="x", padx=14, pady=(14, 8))

        tk.Label(
            header, text="Recent Dictations",
            font=_f(15, bold=True), fg=TEXT1, bg=BG,
        ).pack(side="left")

        if history:
            # Clear All (destructive — red)
            clear_btn = tk.Button(
                header, text="Clear All",
                font=_f(10), fg=TEXT1, bg=C_DANGER,
                activeforeground=TEXT1, activebackground=C_DANGER_H,
                relief="flat", bd=0, padx=10, pady=4,
                cursor="hand2",
            )
            clear_btn.configure(command=self._on_clear)
            clear_btn.pack(side="right", padx=(6, 0))

            # Copy All (secondary)
            self._copy_all_btn = tk.Button(
                header, text="Copy All",
                font=_f(10), fg=TEXT2, bg=SURFACE2,
                activeforeground=TEXT1, activebackground=ACCENT_HOVER,
                relief="flat", bd=0, padx=10, pady=4,
                cursor="hand2",
            )
            self._copy_all_btn.configure(command=self._copy_all)
            self._copy_all_btn.pack(side="right")

        # ── Divider ───────────────────────────────────────────────────
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x", padx=14, pady=(0, 4))

        # ── Empty state ───────────────────────────────────────────────
        if not history:
            pad = tk.Frame(self, bg=BG)
            pad.pack(expand=True, fill="both", pady=24)
            tk.Label(pad, text="No dictations yet",
                     font=_f(13), fg=TEXT3, bg=BG).pack()
            tk.Label(pad, text="Use the hotkey to start dictating",
                     font=_f(11), fg=TEXT3, bg=BG).pack(pady=(4, 0))
            self.geometry(f"{_WIN_W}x140")
            self._build_path_label()
            return

        # ── Scrollable card list ───────────────────────────────────────
        total_h = min(len(history), 7) * _CARD_H + 100
        self.geometry(f"{_WIN_W}x{total_h}")

        outer = tk.Frame(self, bg=BG)
        outer.pack(fill="both", expand=True, padx=6, pady=(0, 4))

        self._canvas = tk.Canvas(outer, bg=BG, highlightthickness=0)
        vsb = tk.Scrollbar(outer, orient="vertical", command=self._canvas.yview)
        self._inner = tk.Frame(self._canvas, bg=BG)

        self._inner.bind(
            "<Configure>",
            lambda _e: self._canvas.configure(
                scrollregion=self._canvas.bbox("all"),
            ),
        )
        win_id = self._canvas.create_window((0, 0), window=self._inner, anchor="nw")
        self._canvas.configure(yscrollcommand=vsb.set)
        self._canvas.bind(
            "<Configure>",
            lambda e: self._canvas.itemconfigure(win_id, width=e.width),
        )

        vsb.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        # Mousewheel: bind globally only while mouse is inside the panel.
        self._canvas.bind("<Enter>", self._mw_bind)
        self._canvas.bind("<Leave>", self._mw_unbind)

        for i, entry in enumerate(reversed(history)):
            self._build_card(self._inner, entry, is_latest=(i == 0))

        self._build_path_label()

    def _build_path_label(self) -> None:
        """Storage path hint at the bottom of the window."""
        history_path = self._config_dir / "history.json"
        tk.Label(
            self,
            text=f"Storage: {history_path}",
            font=_f(8),
            fg=TEXT3, bg=BG,
            anchor="w",
        ).pack(fill="x", padx=14, pady=(2, 8))

    def _mw_bind(self, _e=None) -> None:
        self.bind_all("<MouseWheel>", self._on_mousewheel)

    def _mw_unbind(self, _e=None) -> None:
        self.unbind_all("<MouseWheel>")

    def _on_mousewheel(self, event) -> None:
        if self._canvas:
            self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _build_card(self, parent: tk.Frame, entry: dict, is_latest: bool) -> None:
        text      = entry["text"]
        elapsed   = entry["elapsed"]
        words     = entry["words"]
        timestamp = entry.get("timestamp", "")

        # 1-px coloured border via outer frame background
        outer = tk.Frame(parent, bg=ACCENT if is_latest else BORDER, padx=1, pady=1)
        outer.pack(fill="x", padx=4, pady=(0, 6))

        card = tk.Frame(outer, bg=SURFACE)
        card.pack(fill="both")

        # ── Badge / meta row ──────────────────────────────────────────
        top = tk.Frame(card, bg=SURFACE)
        top.pack(fill="x", padx=10, pady=(8, 4))

        elapsed_str = f"{elapsed:.2f}s" if elapsed < 10 else f"{elapsed:.1f}s"

        _badge(top, f"{words}w").pack(side="left")
        _badge(top, elapsed_str).pack(side="left", padx=(4, 0))
        if is_latest:
            _badge(top, "latest", fg="#818cf8", bg="#1e2d5a").pack(
                side="left", padx=(4, 0),
            )
        if len(timestamp) >= 16:
            tk.Label(top, text=timestamp[11:16],
                     font=_f(9), fg=TEXT3, bg=SURFACE).pack(
                side="left", padx=(6, 0),
            )

        # Delete (×) button — right-most (pack right first so center fills gap)
        del_btn = tk.Button(
            top, text="×",
            font=_f(12, bold=True), fg=TEXT3, bg=SURFACE,
            activeforeground=C_DANGER, activebackground=SURFACE,
            relief="flat", bd=0, padx=6, pady=0,
            cursor="hand2",
        )
        del_btn.configure(
            command=lambda e=entry, f=outer: self._delete_entry(e, f),
        )
        del_btn.pack(side="right", padx=(4, 0))

        # Copy button — centered between badges and delete button
        _center = tk.Frame(top, bg=SURFACE)
        _center.pack(side="left", expand=True, fill="x")
        copy_btn = tk.Button(
            _center, text="Copy",
            font=_f(10), fg=TEXT2, bg=SURFACE2,
            activeforeground=TEXT1, activebackground=ACCENT_HOVER,
            relief="flat", bd=0, padx=8, pady=2,
            cursor="hand2",
        )
        copy_btn.configure(command=lambda t=text, b=copy_btn: self._copy_one(t, b))
        copy_btn.pack()

        # ── Text display ──────────────────────────────────────────────
        # state=disabled: mouse selection + Ctrl+C work; typing is blocked.
        # "body" tag preserves foreground colour even in disabled state
        # (Tk on Windows otherwise uses the system grey for disabled text).
        txt = tk.Text(
            card,
            height=1,
            font=_f(13),
            wrap="word",
            bg=SURFACE,
            relief="flat", bd=0,
            padx=6, pady=4,
            highlightthickness=0,
            selectbackground=ACCENT_HOVER,
            selectforeground=TEXT1,
            cursor="arrow",
        )
        txt.tag_configure("body", foreground=TEXT1, background=SURFACE)
        txt.insert("1.0", text, "body")
        txt.configure(state="disabled")
        txt.pack(fill="x", padx=10, pady=(0, 8))
        txt.bind("<MouseWheel>", self._on_mousewheel)

        def _update_height(event, w=txt):
            lines = w.count("1.0", "end", "displaylines")
            if lines:
                w.configure(height=lines)

        txt.bind("<Configure>", _update_height)

    # ── Actions ───────────────────────────────────────────────────────────────

    def _copy_one(self, text: str, btn: tk.Button) -> None:
        try:
            pyperclip.copy(text)
        except Exception:
            pass
        btn.configure(text="✓ Copied", fg=TEXT1, bg=ACCENT)
        self.after(1400, lambda: btn.configure(text="Copy", fg=TEXT2, bg=SURFACE2))

    def _copy_all(self) -> None:
        """Copy every entry to clipboard, newest first, separated by blank lines."""
        texts = [e["text"] for e in reversed(self._history_ref)]
        try:
            pyperclip.copy("\n\n".join(texts))
        except Exception:
            return
        self._copy_all_btn.configure(text="✓ Copied!", fg=TEXT1, bg=ACCENT)
        self.after(1600, lambda: self._copy_all_btn.configure(
            text="Copy All", fg=TEXT2, bg=SURFACE2,
        ))

    def _delete_entry(self, entry: dict, card_frame: tk.Frame) -> None:
        """Remove a single card from the UI and notify the caller."""
        card_frame.destroy()
        self._entry_count -= 1
        if self._on_delete_cb:
            self._on_delete_cb(entry)

    def _on_clear(self) -> None:
        n = self._entry_count
        noun = "entry" if n == 1 else "entries"
        history_path = self._config_dir / "history.json"
        confirmed = mb.askyesno(
            "Clear History",
            f"Permanently delete all {n} {noun}?\n\n"
            f"File: {history_path}\n\n"
            "This cannot be undone.",
            icon="warning",
            parent=self,
        )
        if confirmed and self._on_clear_cb:
            self._on_clear_cb()
        # AppWindow._on_history_clear destroys this window.

    def destroy(self) -> None:
        try:
            self.unbind_all("<MouseWheel>")
        except Exception:
            pass
        super().destroy()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _badge(parent: tk.Frame, text: str,
           fg: str = TEXT2, bg: str = SURFACE2) -> tk.Frame:
    f = tk.Frame(parent, bg=bg, padx=6, pady=2)
    tk.Label(f, text=text, font=_f(9), fg=fg, bg=bg).pack()
    return f
