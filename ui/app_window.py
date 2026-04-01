import sys
import threading
import time
import tkinter as tk

import customtkinter as ctk
import pyperclip

# ── Platform-aware modern font ────────────────────────────────────────────────
_FONT_FAMILY = (
    "Segoe UI Variable" if sys.platform == "win32"
    else "SF Pro Display" if sys.platform == "darwin"
    else "Ubuntu"
)


def _f(size: int, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(family=_FONT_FAMILY, size=size, weight=weight)

from config import history_store
from config.history_store import make_entry
from ui.history_window import HistoryWindow
from ui.settings_window import SettingsWindow

# ── Design tokens ────────────────────────────────────────────────────────────
BG           = "#0b0d14"   # app background
SURFACE      = "#12141f"   # card / panel surface
SURFACE2     = "#181a28"   # slightly lighter surface
BORDER       = "#252840"   # subtle border

ACCENT       = "#6366f1"   # indigo primary
ACCENT_HOVER = "#4f46e5"
ACCENT_MUTED = "#282b5c"   # dim indigo for backgrounds

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

# ── Waveform constants ────────────────────────────────────────────────────────
_WAVE_N_BARS  = 48   # number of amplitude bars shown
_WAVE_POLL_MS = 50   # polling interval (ms)

# ── Window dimensions ─────────────────────────────────────────────────────────
_W        = 256
_H_NORMAL = 210   # idle (target ~60 % of previous 340)
_H_RECORD = 268   # recording (waveform expanded ~58 px taller)


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
    def __init__(self, settings, recorder, whisper, injector, hotkey_mgr, config_dir, app_dir=None):
        super().__init__()

        self._settings   = settings
        self._recorder   = recorder
        self._whisper    = whisper
        self._injector   = injector
        self._hotkey_mgr = hotkey_mgr
        self._config_dir = config_dir
        self._app_dir    = app_dir

        self._processing      = False
        self._is_recording    = False
        self._t_process_start = 0.0
        self._tray            = None
        self._history_win: HistoryWindow | None = None
        self._settings_win: SettingsWindow | None = None
        self._last_full_text: str = ""
        self._base_height: int = _H_NORMAL  # measured after _build_ui()

        # Waveform state
        self._wave_history: list[float] = []
        self._wave_poll_id = None

        self._history: list[dict] = history_store.load_history(config_dir)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title("DictatorShipping")
        self.resizable(False, False)
        self.configure(fg_color=BG)
        self.geometry(f"{_W}x{_H_NORMAL}")

        if settings.get("always_on_top", False):
            self.wm_attributes("-topmost", True)

        pos = settings.get("window_position")
        if pos:
            self.geometry(f"+{pos[0]}+{pos[1]}")

        self._build_ui()
        self._set_window_icon()
        self._setup_hotkey()
        self._check_macos_permissions()

        # Measure natural content height and snap window to fit.
        # CTk doubles geometry values internally (window_scaling=2.0), so we
        # must divide winfo_reqheight() by window_scaling to get the correct value.
        self.update_idletasks()
        _ws = ctk.ScalingTracker.get_window_scaling(self)
        self._base_height = max(_H_NORMAL, int(self.winfo_reqheight() / _ws))
        self.geometry(f"{_W}x{self._base_height}")

        self.after(50,  self._load_header_icon)
        self.after(200, self._load_whisper_async)

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
        header.pack(fill="x", padx=14, pady=(4, 0))

        # Gear button — top-right (packed first so it anchors right)
        self._gear_btn = ctk.CTkButton(
            header,
            text="⚙",
            width=22, height=22,
            corner_radius=6,
            font=_f(12),
            fg_color="transparent",
            hover_color=SURFACE2,
            border_width=1, border_color=BORDER,
            text_color=TEXT2,
            command=self._open_settings,
        )
        self._gear_btn.pack(side="right")

        # Icon — top-left square (image loaded via after() once event loop starts)
        self._header_icon_lbl = ctk.CTkLabel(header, text="", image=None)
        self._header_icon_lbl.pack(side="left", padx=(0, 6))

        ctk.CTkLabel(
            header,
            text="DictatorShipping",
            font=_f(13, "bold"),
            text_color=TEXT1,
        ).pack(side="left")

        # ── Status pill ───────────────────────────────────────────────
        status_row = ctk.CTkFrame(self, fg_color="transparent")
        status_row.pack(pady=(3, 0))

        self._status_pill = ctk.CTkFrame(
            status_row, fg_color=SURFACE, corner_radius=16,
            border_width=1, border_color=BORDER,
        )
        self._status_pill.pack()
        self._status_label = ctk.CTkLabel(
            self._status_pill,
            text="○  Loading model…",
            font=_f(11),
            text_color=C_LOADING,
        )
        self._status_label.pack(padx=12, pady=3)

        # ── Settings card ─────────────────────────────────────────────
        card = ctk.CTkFrame(
            self, fg_color=SURFACE, corner_radius=10,
            border_width=1, border_color=BORDER,
        )
        card.pack(fill="x", padx=14, pady=(5, 0))

        lang_row = self._add_row(card, "Language", first=True)
        ctk.CTkComboBox(
            lang_row,
            values=[lbl for lbl, _ in LANGUAGES],
            variable=ctk.StringVar(
                value=_lang_code_to_label(self._settings.get("language", "auto"))
            ),
            command=self._on_language_change,
            width=110, height=22,
            fg_color=SURFACE2, border_color=BORDER,
            button_color=BORDER, button_hover_color=ACCENT_MUTED,
            dropdown_fg_color=SURFACE,
            font=_f(11), text_color=TEXT1,
        ).pack(side="right")

        clipboard_row = self._add_row(card, "Clipboard paste", last=True)
        self._clipboard_switch = ctk.CTkSwitch(
            clipboard_row, text="", command=self._on_clipboard_toggle,
            width=36, height=18,
            progress_color=ACCENT, button_color=TEXT1,
            button_hover_color="#ffffff", fg_color=BORDER,
        )
        self._clipboard_switch.pack(side="right")
        if self._settings.get("use_clipboard_fallback", False):
            self._clipboard_switch.select()
        else:
            self._clipboard_switch.deselect()

        # Subtitle below clipboard row
        ctk.CTkLabel(
            card,
            text="Best for terminals",
            font=_f(9),
            text_color=TEXT3,
            anchor="w",
        ).pack(fill="x", padx=12, pady=(0, 3))

        # ── Last transcription field ──────────────────────────────────
        trans_frame = ctk.CTkFrame(
            self, fg_color=SURFACE, corner_radius=8,
            border_width=1, border_color=BORDER,
            height=36,
        )
        trans_frame.pack(fill="x", padx=14, pady=(3, 0))
        trans_frame.pack_propagate(False)

        trans_inner = ctk.CTkFrame(trans_frame, fg_color="transparent")
        trans_inner.pack(fill="both", expand=True, padx=6, pady=2)

        self._last_text_label = ctk.CTkLabel(
            trans_inner,
            text="No transcription yet",
            font=_f(10),
            text_color=TEXT3,
            anchor="w",
            wraplength=165,
            justify="left",
        )
        self._last_text_label.pack(side="left", fill="both", expand=True)

        self._copy_trans_btn = ctk.CTkButton(
            trans_inner,
            text="📋",
            width=24, height=24,
            corner_radius=6,
            font=_f(10),
            fg_color="transparent",
            hover_color=SURFACE2,
            border_width=1, border_color=BORDER,
            text_color=TEXT2,
            command=self._copy_last_text,
        )
        self._copy_trans_btn.pack(side="right", padx=(3, 0))

        # ── Record button ─────────────────────────────────────────────
        self._record_btn = ctk.CTkButton(
            self,
            text=self._btn_label(),
            height=36, corner_radius=10,
            font=_f(12, "bold"),
            fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=TEXT1,
        )
        self._record_btn.pack(fill="x", padx=14, pady=(4, 0))
        self._record_btn.bind("<ButtonPress-1>",   lambda e: self._on_btn_press())
        self._record_btn.bind("<ButtonRelease-1>", lambda e: self._on_btn_release())

        # ── Waveform (hidden until recording starts) ──────────────────
        self._wave_frame = ctk.CTkFrame(
            self, fg_color=SURFACE, corner_radius=8,
            border_width=1, border_color=BORDER,
        )
        # Not packed yet — shown dynamically in _start_recording
        self._wave_canvas = tk.Canvas(
            self._wave_frame,
            bg=SURFACE, bd=0, highlightthickness=0, height=36,
        )
        self._wave_canvas.pack(fill="both", expand=True, padx=6, pady=2)

        # ── Footer ────────────────────────────────────────────────────
        self._footer_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._footer_frame.pack(fill="x", padx=14, pady=(3, 3))

        self._last_time_label = ctk.CTkLabel(
            self._footer_frame,
            text="Last: —",
            font=_f(10),
            text_color=TEXT3, anchor="w",
        )
        self._last_time_label.pack(side="left")

        self._history_btn = ctk.CTkButton(
            self._footer_frame,
            text="History  ›",
            width=68, height=20, corner_radius=6,
            font=_f(10),
            fg_color=SURFACE, hover_color=SURFACE2,
            border_width=1, border_color=BORDER,
            text_color=TEXT2,
            command=self._open_history,
        )
        self._history_btn.pack(side="right")


    # ── Icon loading ──────────────────────────────────────────────────────────

    def _load_header_icon(self):
        if not self._app_dir:
            return
        try:
            from ui.icon import get_pil_image
            pil = get_pil_image(self._app_dir, size=(20, 20))
            self._header_ctk_img = ctk.CTkImage(light_image=pil, dark_image=pil, size=(20, 20))
            self._header_icon_lbl.configure(image=self._header_ctk_img)
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
        self._footer_frame.pack_forget()

        self._wave_frame.pack(fill="x", padx=14, pady=(3, 0))
        self._footer_frame.pack(fill="x", padx=14, pady=(3, 3))

        self.update_idletasks()
        _ws = ctk.ScalingTracker.get_window_scaling(self)
        self.geometry(f"{_W}x{int(self.winfo_reqheight() / _ws)}")

    def _waveform_hide(self):
        if self._wave_poll_id:
            self.after_cancel(self._wave_poll_id)
            self._wave_poll_id = None
        self._wave_frame.pack_forget()
        self._wave_canvas.delete("all")
        self.geometry(f"{_W}x{self._base_height}")

    def _waveform_poll(self):
        """Called every _WAVE_POLL_MS ms while recording."""
        if not self._is_recording:
            return

        level = self._recorder.level
        self._wave_history.append(level)
        if len(self._wave_history) > _WAVE_N_BARS:
            self._wave_history.pop(0)

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

        bar_color = ACCENT

        avail = w - 8  # 4 px padding each side
        step = avail / _WAVE_N_BARS
        bar_w = max(2.0, step * 0.55)
        max_hh = (h - 10) / 2  # half-height ceiling

        # Pad history so bars always fill from the right
        padded = [0.0] * (_WAVE_N_BARS - len(hist)) + list(hist)

        for i, amp in enumerate(padded):
            scaled = min(1.0, (amp / 0.08) ** 0.5)
            hh = max(1.0, scaled * max_hh)
            x = 4 + step * i + step / 2
            c.create_rectangle(
                x - bar_w / 2, cy - hh,
                x + bar_w / 2, cy + hh,
                fill=bar_color, outline="",
            )

    def _add_row(self, parent, label_text: str, first=False, last=False) -> ctk.CTkFrame:
        """Add a label row inside a settings card; returns the row frame for the caller to add the widget."""
        top_pad = 4 if first else 2
        bot_pad = 4 if last else 2

        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(top_pad, bot_pad))

        ctk.CTkLabel(
            row,
            text=label_text,
            font=_f(12),
            text_color=TEXT2,
            anchor="w",
            width=70,
        ).pack(side="left")

        # Subtle divider (except after last row)
        if not last:
            ctk.CTkFrame(
                parent,
                height=1,
                fg_color=BORDER,
            ).pack(fill="x", padx=12)

        return row

    # ── Settings callbacks ────────────────────────────────────────────────────

    def _on_language_change(self, label: str):
        self._settings.set("language", _lang_label_to_code(label))

    def _on_clipboard_toggle(self):
        self._settings.set("use_clipboard_fallback", self._clipboard_switch.get() == 1)

    def _on_mode_change(self, value: str):
        mode = "hold" if value == "Hold" else "toggle"
        self._settings.set("recording_mode", mode)
        self._record_btn.configure(text=self._btn_label())

    # ── Mode helpers ──────────────────────────────────────────────────────────

    def _mode(self) -> str:
        return self._settings.get("recording_mode", "hold")

    def _btn_label(self) -> str:
        return "CTRL+SPACE to Dictate" if self._mode() == "hold" else "CTRL+SPACE to Start/Stop"

    # ── Transcription field ───────────────────────────────────────────────────

    def _update_last_text(self, full_text: str):
        self._last_full_text = full_text
        words = full_text.split()
        display = " ".join(words[:30]) + "…" if len(words) > 30 else full_text
        self._last_text_label.configure(
            text=display if display else "No transcription yet",
            text_color=TEXT2 if display else TEXT3,
        )

    def _copy_last_text(self):
        if self._last_full_text:
            pyperclip.copy(self._last_full_text)
            self._copy_trans_btn.configure(text="✓", text_color=C_READY)
            self.after(1400, lambda: self._copy_trans_btn.configure(text="📋", text_color=TEXT2))

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

            elapsed = time.perf_counter() - self._t_process_start
            elapsed_str = f"{elapsed:.2f}s" if elapsed < 10 else f"{elapsed:.1f}s"

            if text:
                self._injector.inject(text)
                self._save_history_entry(text, elapsed)

            self.after(0, lambda s=elapsed_str, t=(text or ""): self._on_done(s, t))
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
        history_store.save_history(self._config_dir, self._history)

    def _on_done(self, elapsed_str: str, text: str = ""):
        self._set_status(f"Done  ·  {elapsed_str}", "ready")
        self._last_time_label.configure(
            text=f"Last: {elapsed_str}",
            text_color=TEXT2,
        )
        if text:
            self._update_last_text(text)
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
            self._config_dir,
            on_clear=self._on_history_clear,
            on_delete=self._on_history_delete,
        )

    def _on_history_clear(self):
        self._history = []
        history_store.clear_history(self._config_dir)
        if self._history_win and self._history_win.winfo_exists():
            self._history_win.destroy()
            self._history_win = None

    def _on_history_delete(self, entry: dict):
        """Remove one entry by identity, save, no window refresh needed."""
        for i, e in enumerate(self._history):
            if e is entry:
                del self._history[i]
                break
        history_store.save_history(self._config_dir, self._history)

    # ── Settings window ───────────────────────────────────────────────────────

    def _open_settings(self):
        if self._settings_win and self._settings_win.winfo_exists():
            self._settings_win.destroy()
            self._settings_win = None
            return
        self._settings_win = SettingsWindow(self, self._settings)

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
            font=_f(13),
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
        dot   = STATUS_DOTS.get(state, "○")
        color = STATUS_COLORS.get(state, C_IDLE)
        self._status_label.configure(
            text=f"{dot}  {text}",
            text_color=color,
        )

    def _on_configure(self, event):
        if event.widget is self:
            self._settings.set("window_position", [self.winfo_x(), self.winfo_y()])

    def _on_close(self):
        self._quit()

    def _quit(self):
        if self._wave_poll_id:
            self.after_cancel(self._wave_poll_id)
            self._wave_poll_id = None
        self._hotkey_mgr.stop()
        if self._tray:
            self._tray.stop()
        if self._history_win is not None:
            try:
                self._history_win.destroy()
            except Exception:
                pass
        if self._settings_win is not None:
            try:
                self._settings_win.destroy()
            except Exception:
                pass
        self.quit()
        self.destroy()
