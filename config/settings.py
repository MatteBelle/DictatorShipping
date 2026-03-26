import json
import os
import sys
import threading
from pathlib import Path


DEFAULTS = {
    "hotkey": "<ctrl>+<space>",
    "language": "auto",
    "formality": "Neutral",
    "auto_punctuation": True,
    "whisper_model": "small",
    "whisper_device": "auto",
    "whisper_compute_type": "auto",
    "ollama_url": "http://localhost:11434",
    "ollama_model": "llama3.2",
    "injection_delay_ms": 175,
    "use_clipboard_fallback": False,
    "always_on_top": True,
    "appearance_mode": "dark",
    "window_position": None,
    "input_device_index": None,
    "sample_rate": 16000,
    "recording_mode": "hold",
    "max_history": 15,
}


def _config_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA", Path.home())
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path.home() / ".config"
    path = Path(base) / "DictatorShipping"
    path.mkdir(parents=True, exist_ok=True)
    return path


class Settings:
    def __init__(self):
        self._lock = threading.RLock()
        self._path = _config_dir() / "settings.json"
        self._data: dict = {}
        self.load()

    def load(self):
        with self._lock:
            if self._path.exists():
                try:
                    with open(self._path, "r", encoding="utf-8") as f:
                        saved = json.load(f)
                    self._data = {**DEFAULTS, **saved}
                except (json.JSONDecodeError, OSError):
                    self._data = dict(DEFAULTS)
            else:
                self._data = dict(DEFAULTS)
            self.save()

    def save(self):
        with self._lock:
            tmp = self._path.with_suffix(".tmp")
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(self._data, f, indent=2)
                os.replace(tmp, self._path)
            except OSError:
                pass

    def get(self, key, default=None):
        with self._lock:
            return self._data.get(key, default)

    def set(self, key, value):
        with self._lock:
            self._data[key] = value
            self.save()
