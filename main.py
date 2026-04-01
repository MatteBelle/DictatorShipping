import os
import socket
import sys
import threading
import traceback
from pathlib import Path

APP_DIR = Path(__file__).parent

from config.settings import Settings, _config_dir
from audio.recorder import AudioRecorder
from transcription.whisper_engine import WhisperEngine
from output.text_injector import TextInjector
from hotkey.hotkey_manager import HotkeyManager
from ui.app_window import AppWindow
from ui.tray import TrayManager

# Port used as single-instance lock (localhost only)
_INSTANCE_PORT = 19847


def _setup_single_instance(app: AppWindow) -> socket.socket | None:
    """
    Try to bind the lock port.
    - Success  → first instance; start a listener thread and return the socket.
    - Failure  → another instance is running; send it 'show' and exit this process.
    """
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)

    try:
        server.bind(("127.0.0.1", _INSTANCE_PORT))
        server.listen(5)
        server.settimeout(1.0)

        def _listen():
            while True:
                try:
                    conn, _ = server.accept()
                    msg = conn.recv(16).strip()
                    conn.close()
                    if msg == b"show":
                        app.show()
                except socket.timeout:
                    continue
                except OSError:
                    break

        threading.Thread(target=_listen, daemon=True).start()
        return server

    except OSError:
        # Another instance is already running — tell it to show itself, then quit
        try:
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.settimeout(2)
            client.connect(("127.0.0.1", _INSTANCE_PORT))
            client.send(b"show")
            client.close()
        except Exception:
            pass
        sys.exit(0)


def main():
    config_dir = _config_dir()

    # Redirect errors to a log file (pythonw has no console)
    log_path = config_dir / "error.log"
    sys.stderr = open(str(log_path), "a", encoding="utf-8", buffering=1)

    settings = Settings()
    recorder = AudioRecorder(settings)
    whisper = WhisperEngine(settings)
    injector = TextInjector(settings)
    hotkey_mgr = HotkeyManager()

    app = AppWindow(settings, recorder, whisper, injector, hotkey_mgr, config_dir, APP_DIR)

    # Single-instance guard — must happen after app is created so the listener
    # can call app.show(). Exits immediately if another instance is running.
    _lock_socket = _setup_single_instance(app)

    tray = TrayManager(
        on_show_hide=app.toggle_visibility,
        on_quit=lambda: app.after(0, app._quit),
        app_dir=APP_DIR,
    )
    tray_ok = tray.start()
    app._tray = tray

    if tray_ok:
        # Start hidden; the tray icon is the entry point.
        # If this is a fresh re-launch (no prior instance found), show the
        # window briefly so the user knows the app started.
        app.withdraw()
        # Show after 500 ms so the tray icon has time to appear first
        app.after(500, app._do_show)
    # If tray unavailable, window stays visible

    app.mainloop()

    if _lock_socket:
        try:
            _lock_socket.close()
        except Exception:
            pass
    tray.stop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        config_dir = _config_dir()
        with open(str(config_dir / "error.log"), "a", encoding="utf-8") as f:
            traceback.print_exc(file=f)
        raise
