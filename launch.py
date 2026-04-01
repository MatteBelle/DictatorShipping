#!/usr/bin/env python3
"""
DictatorShipping Launcher — stdlib only (runs before any packages are installed).
Handles: venv creation, pip install, then launches main.py.
"""

import os
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk

# Hide the console window immediately on Windows (before anything else shows)
if sys.platform == "win32":
    import ctypes
    _hwnd = ctypes.windll.kernel32.GetConsoleWindow()
    if _hwnd:
        ctypes.windll.user32.ShowWindow(_hwnd, 0)  # SW_HIDE

APP_DIR = Path(__file__).parent
VENV_DIR = APP_DIR / ".venv"
REQUIREMENTS = APP_DIR / "requirements.txt"

if sys.platform == "win32":
    VENV_PYTHON  = VENV_DIR / "Scripts" / "python.exe"
    VENV_PYTHONW = VENV_DIR / "Scripts" / "pythonw.exe"  # no-console variant
else:
    VENV_PYTHON  = VENV_DIR / "bin" / "python"
    VENV_PYTHONW = VENV_PYTHON  # same on Unix

# Suppress console windows for all child processes on Windows
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def _run_silent(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, creationflags=_NO_WINDOW)


def _pip_healthy() -> bool:
    return _run_silent([str(VENV_PYTHON), "-m", "pip", "--version"]).returncode == 0


def _venv_ready() -> bool:
    return VENV_PYTHON.exists() and _pip_healthy()


def _packages_installed() -> bool:
    return _run_silent([
        str(VENV_PYTHON), "-c",
        "import customtkinter, faster_whisper, sounddevice, pynput, "
        "pyperclip, pystray, PIL",
    ]).returncode == 0


# ---------------------------------------------------------------------------
# Setup UI
# ---------------------------------------------------------------------------

BG       = "#0b0d14"
SURFACE  = "#12141f"
SURFACE2 = "#181a28"
BORDER   = "#1e2133"
ACCENT   = "#6366f1"
TEXT1    = "#e8eaf6"
TEXT2    = "#7b82a8"
TEXT3    = "#3d4261"


class SetupWindow:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("DictatorShipping")
        self.root.configure(bg=BG)
        self.root.resizable(False, False)
        self._build_ui()
        self._center()
        self._done = False

    def _center(self):
        self.root.update_idletasks()
        w, h = 460, 330
        sx = (self.root.winfo_screenwidth() - w) // 2
        sy = (self.root.winfo_screenheight() - h) // 2
        self.root.geometry(f"{w}x{h}+{sx}+{sy}")

    def _build_ui(self):
        # App name
        tk.Label(
            self.root, text="DictatorShipping",
            font=("Helvetica", 22, "bold"),
            bg=BG, fg=TEXT1,
        ).pack(pady=(32, 2))

        tk.Label(
            self.root, text="Getting everything ready…",
            font=("Helvetica", 11),
            bg=BG, fg=TEXT2,
        ).pack(pady=(0, 22))

        # Progress bar container (gives it a rounded look via frame)
        bar_frame = tk.Frame(self.root, bg=SURFACE2, bd=0)
        bar_frame.pack(fill="x", padx=36, pady=(0, 6))

        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Setup.Horizontal.TProgressbar",
            troughcolor=SURFACE2,
            background=ACCENT,
            bordercolor=SURFACE2,
            lightcolor=ACCENT,
            darkcolor=ACCENT,
            thickness=6,
        )
        self._progress = ttk.Progressbar(
            bar_frame,
            style="Setup.Horizontal.TProgressbar",
            mode="determinate",
            length=388,
            maximum=100,
        )
        self._progress.pack()

        # Step label
        self._step_var = tk.StringVar(value="")
        tk.Label(
            self.root, textvariable=self._step_var,
            font=("Helvetica", 11, "bold"),
            bg=BG, fg=TEXT1,
        ).pack(pady=(10, 0))

        # Sub-label
        self._sub_var = tk.StringVar(value="")
        tk.Label(
            self.root, textvariable=self._sub_var,
            font=("Helvetica", 9),
            bg=BG, fg=TEXT2, wraplength=400,
        ).pack(pady=(2, 8))

        # Log area
        log_outer = tk.Frame(self.root, bg=SURFACE, bd=0)
        log_outer.pack(fill="x", padx=30, pady=(0, 8))
        self._log = tk.Text(
            log_outer,
            height=4, width=54,
            bg=SURFACE, fg=TEXT3,
            font=("Courier", 8),
            relief="flat", state="disabled", wrap="word",
            insertbackground=SURFACE,
        )
        self._log.pack(padx=10, pady=8)

    def set_step(self, text: str, sub: str = ""):
        def _do():
            self._step_var.set(text)
            self._sub_var.set(sub)
        self.root.after(0, _do)

    def set_progress(self, pct: float):
        self.root.after(0, lambda: self._progress.configure(value=pct))

    def log(self, line: str):
        line = line.strip()
        if not line:
            return
        def _do():
            self._log.configure(state="normal")
            self._log.insert("end", line + "\n")
            self._log.see("end")
            self._log.configure(state="disabled")
        self.root.after(0, _do)

    def close(self):
        self._done = True
        self.root.after(0, self.root.destroy)

    def start(self, worker_fn):
        threading.Thread(target=worker_fn, daemon=True).start()
        self.root.mainloop()


# ---------------------------------------------------------------------------
# Setup steps
# ---------------------------------------------------------------------------

def _run_step(ui: SetupWindow, cmd: list[str], log_prefix: str = "") -> int:
    """Run a subprocess, streaming output to the log. Returns exit code."""
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(APP_DIR),
        creationflags=_NO_WINDOW,
    )
    for line in proc.stdout:
        clean = line.strip()
        if clean:
            ui.log(f"{log_prefix}{clean}")
    proc.wait()
    return proc.returncode


def _create_venv(ui: SetupWindow):
    ui.set_step("Creating virtual environment…", "This only happens once.")
    ui.set_progress(5)

    if VENV_DIR.exists() and not _pip_healthy():
        ui.log("Broken venv detected — removing and recreating…")
        import shutil
        shutil.rmtree(str(VENV_DIR), ignore_errors=True)

    import venv as _venv
    _venv.create(str(VENV_DIR), with_pip=False, clear=False)

    ui.set_step("Bootstrapping pip…")
    ui.set_progress(8)
    _run_silent([str(VENV_PYTHON), "-m", "ensurepip", "--upgrade"])


def _upgrade_pip(ui: SetupWindow):
    ui.set_step("Upgrading pip…")
    ui.set_progress(12)
    _run_step(ui, [str(VENV_PYTHON), "-m", "pip", "install", "--upgrade", "pip", "-q"])


def _install_packages(ui: SetupWindow):
    ui.set_step(
        "Installing dependencies…",
        "faster-whisper, customtkinter, sounddevice, pynput… (~2 min first time)",
    )
    ui.set_progress(18)

    proc = subprocess.Popen(
        [str(VENV_PYTHON), "-m", "pip", "install",
         "-r", str(REQUIREMENTS), "--progress-bar", "off"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, cwd=str(APP_DIR), creationflags=_NO_WINDOW,
    )
    installed = 0
    for line in proc.stdout:
        clean = line.strip()
        if clean:
            ui.log(clean)
            if clean.lower().startswith(("collecting", "downloading", "installing")):
                installed += 1
                ui.set_progress(min(18 + installed * 3, 72))
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError("pip install failed — check the log above.")


def _ensure_ico():
    """Convert DictatorShipping.jpg → .ico via venv Pillow (regenerates if JPG is newer)."""
    ico = APP_DIR / "DictatorShipping.ico"
    jpg = APP_DIR / "DictatorShipping.jpg"
    if not jpg.exists():
        return
    if ico.exists() and ico.stat().st_mtime >= jpg.stat().st_mtime:
        return  # already up to date
    _run_silent([
        str(VENV_PYTHON), "-c",
        (
            f"import sys; sys.path.insert(0,{str(APP_DIR)!r}); "
            f"from ui.icon import build_ico; from pathlib import Path; "
            f"build_ico(Path({str(APP_DIR)!r}))"
        ),
    ])


def _ensure_shortcut():
    """Create (or refresh) the desktop .lnk shortcut on Windows."""
    if sys.platform != "win32":
        return
    marker = APP_DIR / ".shortcut_created"
    ico = APP_DIR / "DictatorShipping.ico"
    # Recreate if: no marker exists, or the ico was just regenerated (newer than marker)
    needs = (
        not marker.exists() or
        (ico.exists() and ico.stat().st_mtime > marker.stat().st_mtime)
    )
    if not needs:
        return

    vbs = APP_DIR / "launch.vbs"
    desktop = Path.home() / "Desktop"
    lnk = desktop / "DictatorShipping.lnk"

    ico_part = f'$s.IconLocation="{ico}";' if ico.exists() else ""
    ps = (
        f'$s=(New-Object -ComObject WScript.Shell).CreateShortcut("{lnk}");'
        f'$s.TargetPath="{vbs}";'
        f'$s.WorkingDirectory="{APP_DIR}";'
        f'{ico_part}'
        f'$s.Save()'
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
        capture_output=True,
        creationflags=_NO_WINDOW,
    )
    if result.returncode == 0:
        marker.touch()


def _launch_app(ui: SetupWindow):
    ui.set_step("Setting up icon & shortcut…", "")
    ui.set_progress(96)
    _ensure_ico()
    _ensure_shortcut()

    ui.set_step("Launching DictatorShipping…", "")
    ui.set_progress(100)
    import time
    time.sleep(0.6)
    ui.close()


# ---------------------------------------------------------------------------
# Main bootstrap
# ---------------------------------------------------------------------------

def _already_setup() -> bool:
    return _venv_ready() and _packages_installed()


def _spawn_main():
    """Launch main.py using pythonw (no console) and exit this process."""
    exe = str(VENV_PYTHONW) if VENV_PYTHONW.exists() else str(VENV_PYTHON)
    main_py = str(APP_DIR / "main.py")
    if sys.platform == "win32":
        subprocess.Popen(
            [exe, main_py],
            creationflags=subprocess.DETACHED_PROCESS | _NO_WINDOW,
        )
        sys.exit(0)
    else:
        os.execv(exe, [exe, main_py])


def _worker(ui: SetupWindow):
    try:
        if not _venv_ready():
            _create_venv(ui)
            _upgrade_pip(ui)

        if not _packages_installed():
            _install_packages(ui)
        else:
            ui.set_progress(72)
            ui.log("Dependencies already installed. ✓")

        _launch_app(ui)

    except Exception as exc:
        ui.set_step(f"Setup failed: {exc}", "Check the log above for details.")
        ui.log(f"ERROR: {exc}")


def _kill_stale_instances():
    """
    Kill any leftover pythonw/python processes running main.py from this folder.
    This runs before spawning a new instance so the slate is clean.
    Only active on Windows; uses tasklist (stdlib, no extra deps).
    """
    if sys.platform != "win32":
        return
    main_py = str(APP_DIR / "main.py").lower()
    try:
        result = subprocess.run(
            ["wmic", "process", "where",
             "name='pythonw.exe' or name='python.exe'",
             "get", "ProcessId,CommandLine", "/format:csv"],
            capture_output=True, text=True, creationflags=_NO_WINDOW,
        )
        current_pid = os.getpid()
        for line in result.stdout.splitlines():
            if main_py in line.lower():
                parts = line.strip().split(",")
                try:
                    pid = int(parts[-1])
                    if pid != current_pid:
                        subprocess.run(
                            ["taskkill", "/F", "/PID", str(pid)],
                            capture_output=True, creationflags=_NO_WINDOW,
                        )
                except (ValueError, IndexError):
                    pass
    except Exception:
        pass


def main():
    os.chdir(APP_DIR)

    # Kill any stale instances of main.py before launching a fresh one
    _kill_stale_instances()

    # Fast path: already set up — launch immediately, no UI
    if _already_setup():
        _ensure_ico()
        _ensure_shortcut()
        _spawn_main()
        return  # only reached on Unix if execv fails

    # First run: show setup window
    ui = SetupWindow()
    ui.start(lambda: _worker(ui))

    if not _already_setup():
        sys.exit(1)  # setup failed

    _spawn_main()


if __name__ == "__main__":
    main()
