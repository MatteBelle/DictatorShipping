import sys
import threading
import time
import tkinter as tk

import customtkinter as ctk

from config import history_store
from config.history_store import make_entry
from ui.history_window import HistoryWindow

# ── Design tokens ────────────────────────────────────────────────────────────
BG           = "#0b0d14"   # app background
SURFACE      = "#12141f"   # card / panel surface
SURFACE2     = "#181a28"   # slightly lighter surface
BORDER       = "#1e2133"   # subtle border

ACCENT       = "#6366f1"   # indigo primary
ACCENT_HOVER = "#4f46e5"
ACCENT_MUTED = "#2e3063"   # dim indigo for backgrounds

C_IDLE       = "#4b5675"
C_RECORDING  = "#ef4444"
C_TRANSCRIBE = "#f59e0b"
C_PROCESS    = "#6366f1"
C_READY      = "#10b981"
C_ERROR      = "#ef4444"
C_LOADING    = "#8b5cf6"

TEXT1        = "#e8eaf6"   # primary text
TEXT2        = "#7b82a8"   # secondary text
TEXT3        = "#3d4261"   # muted text

STATUS_COLORS = {
    "idle":         C_IDLE,
    "recording":    C_RECORDING,
    "transcribing": C_TRANSCRIBE,
    "processing":   C_PROCESS,
    "ready":        C_READY,
    "error":        C_ERROR,
    "loading":      C_LOADING,
}

STATUS_DOTS = {
    "idle":         "○",
    "recording":    "⏺",
    "transcribing": "◌",
    "processing":   "◌",
    "ready":        "●",
    "error":        "⚠",
    "loading":      "◌",
}

# ── Waveform / silence-detection constants ────────────────────────────────────
_WAVE_N_BARS       = 48     # number of amplitude bars shown
_WAVE_POLL_MS      = 50     # polling interval (ms)
_SILENCE_THRESHOLD = 0.008  # RMS below this counts as silence
_AUTO_STOP_FRAMES  = 50     # 50 × 50 ms = 2.5 s silence → auto-stop
_MIN_REC_FRAMES    = 16     # 16 × 50 ms = 0.8 s min before auto-stop triggers

# ── Window heights ────────────────────────────────────────────────────────────
_H_NORMAL  = 500   # idle (bottom icon visible)
_H_RECORD  = 558   # recording (waveform expanded ~58 px taller)

def _lerp_hex(c1: str, c2: str, t: float) -> str:
    """Linearly interpolate between two #rrggbb colours."""
    t = max(0.0, min(1.0, t))
    r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
    r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
    return (
        f"#{int(r1 + (r2 - r1) * t):02x}"
        f"{int(g1 + (g2 - g1) * t):02x}"
        f"{int(b1 + (b2 - b1) * t):02x}"
    )


LANGUAGES = [
    ("Auto-detect", "auto"),
    ("English", "en"),
    ("Italian", "it"),
    ("French", "fr"),
    ("German", "de"),
    ("Spanish", "es"),
    ("Portuguese", "pt"),
    ("Dutch", "nl"),
    ("Russian", "ru"),
    ("Chinese", "zh"),
    ("Japanese", "ja"),
]

FORMALITY_LEVELS = ["Neutral", "Formal", "Casual"]


def _lang_label_to_code(label: str) -> str:
    for lbl, code in LANGUAGES:
        if lbl == label:
            return code
    return "auto"


def _lang_code_to_label(code: str) -> str:
    for lbl, c in LANGUAGES:
        if c == code:
            return lbl
    return "Auto-detect"


class AppWindow(ctk.CTk):
    def __init__(self, settings, recorder, whisper, ollama, injector, hotkey_mgr, config_dir, app_dir=None):
        super().__init__()

        self._settings  = settings
        self._recorder  = recorder
        self._whisper   = whisper
        self._ollama    = ollama
        self._injector  = injector
        self._hotkey_mgr = hotkey_mgr
        self._config_dir = config_dir
        self._app_dir    = app_dir

        self._processing      = False
        self._is_recording    = False
        self._t_process_start = 0.0
        self._tray            = None
        self._history_win: HistoryWindow | None = None

        # Waveform / silence-detection state
        self._wave_history: list[float] = []
        self._wave_silence_frames = 0
        self._wave_total_frames   = 0
        self._wave_poll_id        = None

        max_h = settings.get("max_history", 15)
        self._history: list[dict] = history_store.load_history(config_dir, max_h)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title("DictatorShipping")
        self.resizable(False, False)
        self.configure(fg_color=BG)
        self.geometry(f"320x{_H_NORMAL}")

        if settings.get("always_on_top", True):
            self.wm_attributes("-topmost", True)

        pos = settings.get("window_position")
        if pos:
            self.geometry(f"+{pos[0]}+{pos[1]}")

        self._build_ui()
        self._set_window_icon()
        self._setup_hotkey()
        self._check_macos_permissions()

        # Delay icon image loading until after the event loop starts so the
        # Tk window is fully mapped and configure() calls are guaranteed to apply.
        self.after(50,  self._load_header_icon)
        self.after(50,  self._load_bottom_icon)
        self.after(200, self._load_whisper_async)
        self.after(300, self._check_ollama_async)

        self.bind("<Configure>", self._on_configure)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── Show / hide ───────────────────────────────────────────────────────────

    def show(self):
        self.after(0, self._do_show)

    def hide(self):
        self.after(0, self.withdraw)

    def toggle_visibility(self):
        self.after(0, self._do_toggle)

    def _do_show(self):
        self.deiconify()
        self.lift()
        self.focus_force()

    def _do_toggle(self):
        if self.winfo_viewable():
            self.withdraw()
        else:
            self._do_show()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Header ────────────────────────────────────────────────────
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(14, 0))

        # Icon — top-left square (image loaded via after() once event loop starts)
        self._header_icon_lbl = ctk.CTkLabel(header, text="", image=None)
        self._header_icon_lbl.pack(side="left", padx=(0, 8))

        ctk.CTkLabel(
            header,
            text="DictatorShipping",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=TEXT1,
        ).pack(side="left")

        # Ollama status dot (right)
        self._ollama_dot = ctk.CTkLabel(
            header, text="●", font=ctk.CTkFont(size=10), text_color=TEXT3,
        )
        self._ollama_dot.pack(side="right", pady=(2, 0))
        ctk.CTkLabel(
            header, text="LLM", font=ctk.CTkFont(size=9), text_color=TEXT3,
        ).pack(side="right", padx=(0, 3), pady=(2, 0))

        # ── Status pill ───────────────────────────────────────────────
        status_row = ctk.CTkFrame(self, fg_color="transparent")
        status_row.pack(pady=(8, 0))

        self._status_pill = ctk.CTkFrame(
            status_row, fg_color=SURFACE, corner_radius=20,
            border_width=1, border_color=BORDER,
        )
        self._status_pill.pack()
        self._status_label = ctk.CTkLabel(
            self._status_pill,
            text="○  Loading model…",
            font=ctk.CTkFont(size=12),
            text_color=C_LOADING,
        )
        self._status_label.pack(padx=16, pady=6)

        # ── Settings card ─────────────────────────────────────────────
        card = ctk.CTkFrame(
            self, fg_color=SURFACE, corner_radius=14,
            border_width=1, border_color=BORDER,
        )
        card.pack(fill="x", padx=16, pady=(10, 0))

        self._add_row(card, "Language",
            ctk.CTkComboBox(
                card,
                values=[lbl for lbl, _ in LANGUAGES],
                variable=ctk.StringVar(
                    value=_lang_code_to_label(self._settings.get("language", "auto"))
                ),
                command=self._on_language_change,
                width=150, height=30,
                fg_color=SURFACE2, border_color=BORDER,
                button_color=BORDER, button_hover_color=ACCENT_MUTED,
                dropdown_fg_color=SURFACE,
                font=ctk.CTkFont(size=12), text_color=TEXT1,
            ), first=True)

        self._add_row(card, "Formality",
            ctk.CTkComboBox(
                card,
                values=FORMALITY_LEVELS,
                variable=ctk.StringVar(value=self._settings.get("formality", "Neutral")),
                command=self._on_formality_change,
                width=150, height=30,
                fg_color=SURFACE2, border_color=BORDER,
                button_color=BORDER, button_hover_color=ACCENT_MUTED,
                dropdown_fg_color=SURFACE,
                font=ctk.CTkFont(size=12), text_color=TEXT1,
            ))

        self._punct_switch = ctk.CTkSwitch(
            card, text="", command=self._on_punctuation_toggle,
            width=44, height=22,
            progress_color=ACCENT, button_color=TEXT1,
            button_hover_color="#ffffff", fg_color=BORDER,
        )
        if self._settings.get("auto_punctuation", True):
            self._punct_switch.select()
        else:
            self._punct_switch.deselect()
        self._add_row(card, "Auto-punct", self._punct_switch)

        self._mode_seg = ctk.CTkSegmentedButton(
            card, values=["Hold", "Toggle"],
            command=self._on_mode_change,
            width=150, height=30,
            font=ctk.CTkFont(size=12),
            fg_color=SURFACE2,
            selected_color=ACCENT, selected_hover_color=ACCENT_HOVER,
            unselected_color=SURFACE2, unselected_hover_color=SURFACE,
            text_color=TEXT1, text_color_disabled=TEXT3,
        )
        saved_mode = self._settings.get("recording_mode", "hold")
        self._mode_seg.set("Hold" if saved_mode == "hold" else "Toggle")
        self._add_row(card, "Mode", self._mode_seg, last=True)

        # ── Hotkey hint chip ──────────────────────────────────────────
        hint_row = ctk.CTkFrame(self, fg_color="transparent")
        hint_row.pack(pady=(8, 0))
        self._hint_chip = ctk.CTkFrame(
            hint_row, fg_color=SURFACE, corner_radius=8,
            border_width=1, border_color=BORDER,
        )
        self._hint_chip.pack()
        self._hotkey_label = ctk.CTkLabel(
            self._hint_chip,
            text=self._hotkey_hint(),
            font=ctk.CTkFont(size=10),
            text_color=TEXT2,
        )
        self._hotkey_label.pack(padx=12, pady=5)

        # ── Record button ─────────────────────────────────────────────
        self._record_btn = ctk.CTkButton(
            self,
            text=self._btn_label(),
            height=52, corner_radius=14,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=TEXT1,
        )
        self._record_btn.pack(fill="x", padx=16, pady=(8, 0))
        self._record_btn.bind("<ButtonPress-1>",   lambda e: self._on_btn_press())
        self._record_btn.bind("<ButtonRelease-1>", lambda e: self._on_btn_release())

        # ── Waveform (hidden until recording starts) ──────────────────
        self._wave_frame = ctk.CTkFrame(
            self, fg_color=SURFACE, corner_radius=12,
            border_width=1, border_color=BORDER,
        )
        # Not packed yet — shown dynamically in _start_recording
        self._wave_canvas = tk.Canvas(
            self._wave_frame,
            bg=SURFACE, bd=0, highlightthickness=0, height=46,
        )
        self._wave_canvas.pack(fill="both", expand=True, padx=8, pady=4)

        # ── Footer ────────────────────────────────────────────────────
        self._footer_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._footer_frame.pack(fill="x", padx=18, pady=(8, 8))

        self._last_time_label = ctk.CTkLabel(
            self._footer_frame,
            text="Last: —",
            font=ctk.CTkFont(size=11),
            text_color=TEXT3, anchor="w",
        )
        self._last_time_label.pack(side="left")

        self._history_btn = ctk.CTkButton(
            self._footer_frame,
            text="History  ›",
            width=80, height=26, corner_radius=8,
            font=ctk.CTkFont(size=11),
            fg_color=SURFACE, hover_color=SURFACE2,
            border_width=1, border_color=BORDER,
            text_color=TEXT2,
            command=self._open_history,
        )
        self._history_btn.pack(side="right")

        # ── Bottom-center icon ────────────────────────────────────────
        self._bottom_icon_frame = ctk.CTkFrame(
            self, fg_color=SURFACE, corner_radius=16,
            border_width=1, border_color=BORDER,
        )
        self._bottom_icon_frame.pack(pady=(0, 12))
        self._bottom_icon_lbl = ctk.CTkLabel(self._bottom_icon_frame, text="", image=None)
        self._bottom_icon_lbl.pack(padx=10, pady=10)

    # ── Icon loading ──────────────────────────────────────────────────────────

    def _load_header_icon(self):
        if not self._app_dir:
            return
        try:
            from ui.icon import get_pil_image
            pil = get_pil_image(self._app_dir, size=(32, 32))
            # Store on self — CTkImage must outlive the function call
            self._header_ctk_img = ctk.CTkImage(light_image=pil, dark_image=pil, size=(32, 32))
            self._header_icon_lbl.configure(image=self._header_ctk_img)
        except Exception:
            import traceback; traceback.print_exc()

    def _load_bottom_icon(self):
        if not self._app_dir:
            return
        try:
            from ui.icon import get_pil_image
            pil = get_pil_image(self._app_dir, size=(64, 64))
            # Store on self — CTkImage must outlive the function call
            self._bottom_ctk_img = ctk.CTkImage(light_image=pil, dark_image=pil, size=(64, 64))
            self._bottom_icon_lbl.configure(image=self._bottom_ctk_img)
        except Exception:
            import traceback; traceback.print_exc()

    def _set_window_icon(self):
        if not self._app_dir:
            return
        try:
            ico = self._app_dir / "DictatorShipping.ico"
            if sys.platform == "win32" and ico.exists():
                self.iconbitmap(str(ico))
            else:
                from ui.icon import get_pil_image
                from PIL import ImageTk
                pil_img = get_pil_image(self._app_dir, size=(32, 32))
                photo = ImageTk.PhotoImage(pil_img)
                self.iconphoto(True, photo)
                self._icon_photo = photo  # prevent GC
        except Exception:
            pass

    # ── Waveform ──────────────────────────────────────────────────────────────

    def _waveform_show(self):
        """Insert waveform between record button and footer, expand window."""
        # Re-pack trailing widgets to insert waveform in the right position
        self._footer_frame.pack_forget()
        self._bottom_icon_frame.pack_forget()

        self._wave_frame.pack(fill="x", padx=16, pady=(6, 0))
        self._footer_frame.pack(fill="x", padx=18, pady=(8, 8))
        self._bottom_icon_frame.pack(pady=(0, 12))

        self.update_idletasks()  # force layout so canvas gets real dimensions
        self.geometry(f"320x{_H_RECORD}")

    def _waveform_hide(self):
        if self._wave_poll_id:
            self.after_cancel(self._wave_poll_id)
            self._wave_poll_id = None
        self._wave_frame.pack_forget()
        self._wave_canvas.delete("all")
        self.geometry(f"320x{_H_NORMAL}")

    def _waveform_poll(self):
        """Called every _WAVE_POLL_MS ms while recording."""
        if not self._is_recording:
            return

        level = self._recorder.level
        self._wave_history.append(level)
        if len(self._wave_history) > _WAVE_N_BARS:
            self._wave_history.pop(0)

        if level < _SILENCE_THRESHOLD:
            self._wave_silence_frames += 1
        else:
            self._wave_silence_frames = 0
        self._wave_total_frames += 1

        # Auto-stop after sustained silence (only past min recording time)
        if (self._wave_total_frames >= _MIN_REC_FRAMES and
                self._wave_silence_frames >= _AUTO_STOP_FRAMES):
            self.after(0, self._stop_and_process)
            return

        self._draw_waveform()
        self._wave_poll_id = self.after(_WAVE_POLL_MS, self._waveform_poll)

    def _draw_waveform(self):
        c = self._wave_canvas
        c.delete("all")
        w = c.winfo_width()
        h = c.winfo_height()
        if w <= 1 or h <= 1:
            return

        cy = h // 2

        # Center baseline
        c.create_line(4, cy, w - 4, cy, fill=BORDER, width=1)

        hist = self._wave_history
        if not hist:
            return

        # How far into the auto-stop countdown (0 → 1)
        silence_frac = min(1.0, self._wave_silence_frames / _AUTO_STOP_FRAMES)

        # Color: accent indigo → amber as silence builds
        bar_color = _lerp_hex(ACCENT, "#f59e0b", silence_frac)

        avail = w - 8  # 4 px padding each side
        step = avail / _WAVE_N_BARS
        bar_w = max(2.0, step * 0.55)
        max_hh = (h - 10) / 2  # half-height ceiling

        # Pad history so bars always fill from the right
        padded = [0.0] * (_WAVE_N_BARS - len(hist)) + list(hist)

        for i, amp in enumerate(padded):
            # Sqrt scaling for perceptual loudness
            scaled = min(1.0, (amp / 0.08) ** 0.5)
            hh = max(1.0, scaled * max_hh)
            x = 4 + step * i + step / 2
            c.create_rectangle(
                x - bar_w / 2, cy - hh,
                x + bar_w / 2, cy + hh,
                fill=bar_color, outline="",
            )

    def _add_row(self, parent, label_text: str, widget, first=False, last=False):
        """Add a label + widget row inside a settings card."""
        top_pad = 10 if first else 4
        bot_pad = 10 if last else 4

        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(top_pad, bot_pad))

        ctk.CTkLabel(
            row,
            text=label_text,
            font=ctk.CTkFont(size=12),
            text_color=TEXT2,
            anchor="w",
            width=80,
        ).pack(side="left")

        widget.pack(side="right")

        # Subtle divider (except after last row)
        if not last:
            ctk.CTkFrame(
                parent,
                height=1,
                fg_color=BORDER,
            ).pack(fill="x", padx=12)

    # ── Settings callbacks ────────────────────────────────────────────────────

    def _on_language_change(self, label: str):
        self._settings.set("language", _lang_label_to_code(label))

    def _on_formality_change(self, value: str):
        self._settings.set("formality", value)

    def _on_punctuation_toggle(self):
        self._settings.set("auto_punctuation", self._punct_switch.get() == 1)

    def _on_mode_change(self, value: str):
        mode = "hold" if value == "Hold" else "toggle"
        self._settings.set("recording_mode", mode)
        self._hotkey_label.configure(text=self._hotkey_hint())
        self._record_btn.configure(text=self._btn_label())

    # ── Mode helpers ──────────────────────────────────────────────────────────

    def _mode(self) -> str:
        return self._settings.get("recording_mode", "hold")

    def _hotkey_hint(self) -> str:
        key = self._settings.get("hotkey", "<ctrl>+<space>")
        action = "hold to dictate" if self._mode() == "hold" else "press to start / stop"
        return f"{key}  ·  {action}"

    def _btn_label(self) -> str:
        return "⏺   HOLD TO DICTATE" if self._mode() == "hold" else "⏺   CLICK TO DICTATE"

    # ── Hotkey wiring ─────────────────────────────────────────────────────────

    def _setup_hotkey(self):
        self._hotkey_mgr.start(
            on_press_cb=self._on_hotkey_press,
            on_release_cb=self._on_hotkey_release,
        )

    def _on_hotkey_press(self):
        if self._mode() == "hold":
            self.after(0, self._start_recording)
        else:
            if self._is_recording:
                self.after(0, self._stop_and_process)
            else:
                self.after(0, self._start_recording)

    def _on_hotkey_release(self):
        if self._mode() == "hold":
            self.after(0, self._stop_and_process)

    def _on_btn_press(self):
        if self._mode() == "hold":
            self._start_recording()
        else:
            if self._is_recording:
                self._stop_and_process()
            else:
                self._start_recording()

    def _on_btn_release(self):
        if self._mode() == "hold":
            self._stop_and_process()

    # ── State machine ─────────────────────────────────────────────────────────

    def _start_recording(self):
        if self._processing:
            self._set_status("Busy — please wait", "error")
            return
        if not self._whisper.is_loaded():
            self._set_status("Model not ready yet", "error")
            return
        self._is_recording = True
        self._recorder.start()
        self._set_status("Recording…", "recording")
        self._record_btn.configure(
            fg_color=C_RECORDING,
            hover_color="#dc2626",
            text="⏹   RECORDING…",
        )
        # Show waveform
        self._wave_history = []
        self._wave_silence_frames = 0
        self._wave_total_frames   = 0
        self._waveform_show()
        self._wave_poll_id = self.after(_WAVE_POLL_MS, self._waveform_poll)

    def _stop_and_process(self):
        if self._processing:
            return
        self._is_recording = False
        audio = self._recorder.stop()
        self._waveform_hide()
        self._record_btn.configure(
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            text=self._btn_label(),
        )

        if len(audio) < 1600:
            self._set_status("Too short — try again", "error")
            self.after(2000, lambda: self._restore_idle_status())
            return

        self._processing = True
        self._t_process_start = time.perf_counter()
        self._set_status("Transcribing…", "transcribing")
        threading.Thread(target=self._worker, args=(audio,), daemon=True).start()

    def _worker(self, audio):
        try:
            text = self._whisper.transcribe(audio)

            formality = self._settings.get("formality", "Neutral")
            if formality != "Neutral" and text:
                self.after(0, lambda: self._set_status("Rewriting…", "processing"))
                text = self._ollama.rewrite(text, formality)

            elapsed = time.perf_counter() - self._t_process_start
            elapsed_str = f"{elapsed:.2f}s" if elapsed < 10 else f"{elapsed:.1f}s"

            if text:
                self._injector.inject(text)
                self._save_history_entry(text, elapsed)

            self.after(0, lambda s=elapsed_str: self._on_done(s))
            self.after(3500, self._restore_idle_status)
        except Exception as e:
            print(f"[Worker] Error: {e}")
            self.after(0, lambda: self._set_status(f"Error: {e}", "error"))
            self.after(3000, self._restore_idle_status)
        finally:
            self._processing = False

    def _save_history_entry(self, text: str, elapsed: float):
        entry = make_entry(text, elapsed)
        self._history.append(entry)
        max_h = self._settings.get("max_history", 15)
        if len(self._history) > max_h:
            self._history = self._history[-max_h:]
        history_store.save_history(self._config_dir, self._history, max_h)

    def _on_done(self, elapsed_str: str):
        self._set_status(f"Done  ·  {elapsed_str}", "ready")
        self._last_time_label.configure(
            text=f"Last: {elapsed_str}",
            text_color=TEXT2,
        )
        if self._history_win and self._history_win.winfo_exists():
            self._history_win.destroy()
            self._open_history()

    def _restore_idle_status(self):
        device = self._whisper.active_device() if self._whisper.is_loaded() else ""
        suffix = f"  ·  {device}" if device else ""
        self._set_status(f"Idle{suffix}", "idle")

    # ── History window ────────────────────────────────────────────────────────

    def _open_history(self):
        if self._history_win and self._history_win.winfo_exists():
            self._history_win.destroy()
            self._history_win = None
            return
        self._history_win = HistoryWindow(
            self,
            self._history,
            self._settings,
            on_max_change=self._on_max_history_change,
        )

    def _on_max_history_change(self, new_max: int):
        if len(self._history) > new_max:
            self._history = self._history[-new_max:]
        history_store.save_history(self._config_dir, self._history, new_max)

    # ── Async startup ─────────────────────────────────────────────────────────

    def _load_whisper_async(self):
        def _load():
            self._whisper.load_model(
                progress_cb=lambda msg: self.after(
                    0, lambda m=msg: self._set_status(m, "loading")
                )
            )
            device = self._whisper.active_device()
            self.after(0, lambda: self._set_status(f"Idle  ·  {device}", "idle"))

        threading.Thread(target=_load, daemon=True).start()

    def _check_ollama_async(self):
        def _check():
            available = self._ollama.is_available()
            color = C_READY if available else TEXT3
            self.after(0, lambda: self._ollama_dot.configure(text_color=color))

        threading.Thread(target=_check, daemon=True).start()
        self.after(30_000, self._check_ollama_async)

    def _check_macos_permissions(self):
        if sys.platform != "darwin":
            return
        try:
            import subprocess
            result = subprocess.run(
                ["osascript", "-e",
                 'tell application "System Events" to return UI elements enabled'],
                capture_output=True, text=True, timeout=3,
            )
            if "false" in result.stdout.lower():
                self._show_macos_accessibility_warning()
        except Exception:
            pass

    def _show_macos_accessibility_warning(self):
        import subprocess
        dialog = ctk.CTkToplevel(self)
        dialog.title("Accessibility Required")
        dialog.geometry("340x180")
        dialog.configure(fg_color=BG)
        dialog.wm_attributes("-topmost", True)
        ctk.CTkLabel(
            dialog,
            text="DictatorShipping needs Accessibility\naccess to use the hotkey and inject text.\n\n"
                 "System Settings → Privacy & Security\n→ Accessibility → add this app.",
            justify="left",
            text_color=TEXT2,
            font=ctk.CTkFont(size=12),
        ).pack(padx=20, pady=16)
        ctk.CTkButton(
            dialog,
            text="Open Privacy Settings",
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            command=lambda: subprocess.Popen([
                "open",
                "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
            ]),
        ).pack(pady=(0, 16))

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _set_status(self, text: str, state: str = "idle"):
        dot  = STATUS_DOTS.get(state, "○")
        color = STATUS_COLORS.get(state, C_IDLE)
        self._status_label.configure(
            text=f"{dot}  {text}",
            text_color=color,
        )

    def _on_configure(self, event):
        if event.widget is self:
            self._settings.set("window_position", [self.winfo_x(), self.winfo_y()])

    def _on_close(self):
        if self._tray and self._tray.available:
            self.withdraw()
        else:
            self._quit()

    def _quit(self):
        if self._wave_poll_id:
            self.after_cancel(self._wave_poll_id)
            self._wave_poll_id = None
        self._hotkey_mgr.stop()
        if self._tray:
            self._tray.stop()
        self.destroy()
