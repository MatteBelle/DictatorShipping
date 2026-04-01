import json
import os
from datetime import datetime
from pathlib import Path


def _history_path(config_dir: Path) -> Path:
    return config_dir / "history.json"


def load_history(config_dir: Path) -> list[dict]:
    path = _history_path(config_dir)
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def save_history(config_dir: Path, history: list[dict]):
    path = _history_path(config_dir)
    tmp = path.with_suffix(".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    except OSError:
        pass


def clear_history(config_dir: Path) -> None:
    """Overwrite the history file with an empty list."""
    path = _history_path(config_dir)
    tmp = path.with_suffix(".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump([], f)
        os.replace(tmp, path)
    except OSError:
        pass


def make_entry(text: str, elapsed: float) -> dict:
    return {
        "text": text,
        "elapsed": round(elapsed, 3),
        "words": len(text.split()),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }
