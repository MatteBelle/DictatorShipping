import json
import os
from datetime import datetime
from pathlib import Path


def _history_path(config_dir: Path) -> Path:
    return config_dir / "history.json"


def load_history(config_dir: Path, max_entries: int) -> list[dict]:
    path = _history_path(config_dir)
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Keep only the most recent max_entries
        return data[-max_entries:] if len(data) > max_entries else data
    except (json.JSONDecodeError, OSError):
        return []


def save_history(config_dir: Path, history: list[dict], max_entries: int):
    path = _history_path(config_dir)
    tmp = path.with_suffix(".tmp")
    trimmed = history[-max_entries:] if len(history) > max_entries else history
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(trimmed, f, indent=2, ensure_ascii=False)
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
