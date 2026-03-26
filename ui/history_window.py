import pyperclip
import customtkinter as ctk

MAX_HISTORY_HARD_LIMIT = 100

# ── Design tokens (matches app_window) ───────────────────────────────────────
BG       = "#0b0d14"
SURFACE  = "#12141f"
SURFACE2 = "#181a28"
BORDER   = "#1e2133"
ACCENT   = "#6366f1"
ACCENT_HOVER = "#4f46e5"
TEXT1    = "#e8eaf6"
TEXT2    = "#7b82a8"
TEXT3    = "#3d4261"
C_READY  = "#10b981"


class HistoryWindow(ctk.CTkToplevel):
    """Floating panel showing recent dictation entries."""

    def __init__(self, parent, history: list[dict], settings, on_max_change=None):
        super().__init__(parent)
        self.title("History")
        self.resizable(False, True)
        self.configure(fg_color=BG)
        self.wm_attributes("-topmost", True)

        self._settings = settings
        self._on_max_change = on_max_change

        self._build(history)

        self.update_idletasks()
        px = parent.winfo_x()
        py = parent.winfo_y()
        pw = parent.winfo_width()
        self.geometry(f"+{px + pw + 10}+{py}")
        self.focus_force()

    def _build(self, history: list[dict]):
        # ── Header ────────────────────────────────────────────────────
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=14, pady=(14, 8))

        ctk.CTkLabel(
            header,
            text="Recent Dictations",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=TEXT1,
        ).pack(side="left")

        # Keep-N control
        keep_frame = ctk.CTkFrame(header, fg_color=SURFACE, corner_radius=8,
                                   border_width=1, border_color=BORDER)
        keep_frame.pack(side="right")

        ctk.CTkLabel(
            keep_frame,
            text="Keep",
            font=ctk.CTkFont(size=10),
            text_color=TEXT3,
        ).pack(side="left", padx=(8, 2), pady=4)

        self._max_var = ctk.StringVar(value=str(self._settings.get("max_history", 15)))
        entry = ctk.CTkEntry(
            keep_frame,
            textvariable=self._max_var,
            width=34,
            height=22,
            font=ctk.CTkFont(size=10),
            justify="center",
            fg_color=SURFACE2,
            border_color=BORDER,
            text_color=TEXT1,
        )
        entry.pack(side="left", pady=4)
        entry.bind("<Return>",   self._on_max_commit)
        entry.bind("<FocusOut>", self._on_max_commit)

        ctk.CTkLabel(
            keep_frame,
            text="entries",
            font=ctk.CTkFont(size=10),
            text_color=TEXT3,
        ).pack(side="left", padx=(2, 8), pady=4)

        # ── Divider ───────────────────────────────────────────────────
        ctk.CTkFrame(self, height=1, fg_color=BORDER).pack(fill="x", padx=14)

        # ── Empty state ───────────────────────────────────────────────
        if not history:
            empty = ctk.CTkFrame(self, fg_color="transparent")
            empty.pack(expand=True, pady=28)
            ctk.CTkLabel(
                empty,
                text="No dictations yet",
                font=ctk.CTkFont(size=12),
                text_color=TEXT3,
            ).pack()
            ctk.CTkLabel(
                empty,
                text="Use the hotkey to start dictating",
                font=ctk.CTkFont(size=10),
                text_color=TEXT3,
            ).pack(pady=(2, 0))
            self.geometry("340x130")
            return

        # ── Entry cards ───────────────────────────────────────────────
        card_h = 100
        total_h = min(len(history), 7) * card_h + 70
        self.geometry(f"340x{total_h}")

        scroll = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            scrollbar_button_color=BORDER,
            scrollbar_button_hover_color=SURFACE2,
        )
        scroll.pack(fill="both", expand=True, padx=6, pady=(6, 8))

        for i, entry in enumerate(reversed(history)):
            self._build_card(scroll, entry, is_latest=(i == 0))

    def _build_card(self, parent, entry: dict, is_latest: bool = False):
        text      = entry["text"]
        elapsed   = entry["elapsed"]
        words     = entry["words"]
        timestamp = entry.get("timestamp", "")

        # Card container
        card = ctk.CTkFrame(
            parent,
            fg_color=SURFACE,
            corner_radius=10,
            border_width=1,
            border_color=BORDER if not is_latest else ACCENT,
        )
        card.pack(fill="x", padx=4, pady=(0, 6))

        # ── Top row: badges + copy button ─────────────────────────────
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=10, pady=(8, 4))

        elapsed_str = f"{elapsed:.2f}s" if elapsed < 10 else f"{elapsed:.1f}s"

        # Word-count badge
        _badge(top, f"{words}w", SURFACE2).pack(side="left")
        # Time badge
        _badge(top, elapsed_str, SURFACE2).pack(side="left", padx=(4, 0))

        if is_latest:
            _badge(top, "latest", "#1e2d5a", text_color="#818cf8").pack(
                side="left", padx=(4, 0)
            )

        # Time of day (if available)
        if len(timestamp) >= 16:
            ctk.CTkLabel(
                top,
                text=timestamp[11:16],
                font=ctk.CTkFont(size=9),
                text_color=TEXT3,
            ).pack(side="left", padx=(6, 0))

        # Copy button
        copy_btn = ctk.CTkButton(
            top,
            text="Copy",
            width=48,
            height=22,
            corner_radius=6,
            font=ctk.CTkFont(size=10),
            fg_color=SURFACE2,
            hover_color=ACCENT_HOVER,
            border_width=1,
            border_color=BORDER,
            text_color=TEXT2,
        )
        copy_btn.configure(command=lambda t=text, b=copy_btn: self._copy(t, b))
        copy_btn.pack(side="right")

        # ── Text content ──────────────────────────────────────────────
        text_box = ctk.CTkTextbox(
            card,
            height=40,
            font=ctk.CTkFont(size=12),
            wrap="word",
            activate_scrollbars=False,
            border_width=0,
            fg_color="transparent",
            text_color=TEXT1,
            scrollbar_button_color="transparent",
        )
        text_box.insert("1.0", text)
        text_box.configure(state="disabled")
        text_box.pack(fill="x", padx=10, pady=(0, 8))

    def _copy(self, text: str, btn: ctk.CTkButton):
        try:
            pyperclip.copy(text)
        except Exception:
            pass
        btn.configure(text="✓  Copied", fg_color=ACCENT, text_color=TEXT1)
        self.after(1400, lambda: btn.configure(
            text="Copy", fg_color=SURFACE2, text_color=TEXT2
        ))

    def _on_max_commit(self, _event=None):
        try:
            val = max(1, min(int(self._max_var.get()), MAX_HISTORY_HARD_LIMIT))
            self._max_var.set(str(val))
            self._settings.set("max_history", val)
            if self._on_max_change:
                self._on_max_change(val)
        except ValueError:
            self._max_var.set(str(self._settings.get("max_history", 15)))


def _badge(parent, text: str, bg: str, text_color: str = None) -> ctk.CTkFrame:
    """Small pill-shaped badge."""
    if text_color is None:
        text_color = TEXT2
    frame = ctk.CTkFrame(parent, fg_color=bg, corner_radius=6)
    ctk.CTkLabel(
        frame,
        text=text,
        font=ctk.CTkFont(size=9),
        text_color=text_color,
    ).pack(padx=6, pady=2)
    return frame
