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
    server.setsockopt(
        socket.SOL_SOCKET, socket.SO_REUSEADDR, 1
    )  # Allow reuse to prevent lock issues

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
                except Exception as e:
                    # Log but don't crash
                    print(f"Socket listener error: {e}", file=sys.stderr)
                    break

        threading.Thread(target=_listen, daemon=True).start()
        return server

    except OSError as e:
        # Another instance is already running — tell it to show itself, then quit
        try:
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.settimeout(2)
            client.connect(("127.0.0.1", _INSTANCE_PORT))
            client.send(b"show")
            client.close()
        except Exception:
            # If we can't connect, the port might be stale - continue anyway
            print(
                f"Warning: Port {_INSTANCE_PORT} appears in use but unreachable",
                file=sys.stderr,
            )
            # Don't exit - let this instance try to run
            return None
        sys.exit(0)


def main():
    config_dir = _config_dir()

    # Redirect errors to a log file (pythonw has no console)
    log_path = config_dir / "error.log"
    # Rotate log if it's too large (> 1MB)
    try:
        if log_path.exists() and log_path.stat().st_size > 1_000_000:
            backup_path = config_dir / "error.log.old"
            if backup_path.exists():
                backup_path.unlink()
            log_path.rename(backup_path)
    except Exception:
        pass

    sys.stderr = open(str(log_path), "a", encoding="utf-8", buffering=1)

    # Log startup
    import datetime

    print(f"\n{'=' * 60}", file=sys.stderr)
    print(f"DictatorShipping started at {datetime.datetime.now()}", file=sys.stderr)
    print(f"Python: {sys.version}", file=sys.stderr)
    print(f"PID: {os.getpid()}", file=sys.stderr)
    print(f"{'=' * 60}\n", file=sys.stderr)

    try:
        settings = Settings()
        recorder = AudioRecorder(settings)
        whisper = WhisperEngine(settings)
        injector = TextInjector(settings)
        hotkey_mgr = HotkeyManager()

        app = AppWindow(
            settings, recorder, whisper, injector, hotkey_mgr, config_dir, APP_DIR
        )

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

        # Clean shutdown
        print(
            f"\nShutting down gracefully at {datetime.datetime.now()}\n",
            file=sys.stderr,
        )

        if _lock_socket:
            try:
                _lock_socket.close()
            except Exception:
                pass
        tray.stop()

        # Clean up hotkey listener
        try:
            hotkey_mgr.stop()
        except Exception:
            pass

        # Clean up audio
        try:
            recorder.stop()
        except Exception:
            pass

    except KeyboardInterrupt:
        print("\nInterrupted by user", file=sys.stderr)
        sys.exit(0)
    except Exception as e:
        print(f"\nFATAL ERROR: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc(file=sys.stderr)
        # Try to show error dialog before crashing
        try:
            import tkinter.messagebox as mb

            mb.showerror(
                "DictatorShipping Error",
                f"Fatal error occurred:\n{str(e)[:200]}\n\nCheck error.log for details.",
            )
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
