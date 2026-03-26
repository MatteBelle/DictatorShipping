import gc
import re
import threading
from typing import Callable

import numpy as np


def _resolve_device_and_compute(settings) -> tuple[str, str]:
    device = settings.get("whisper_device", "auto")
    compute = settings.get("whisper_compute_type", "auto")

    if device == "auto":
        try:
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            device = "cpu"

    if compute == "auto":
        compute = "float16" if device == "cuda" else "int8"

    return device, compute


class WhisperEngine:
    def __init__(self, settings):
        self._settings = settings
        self._model = None
        self._lock = threading.Lock()

    def load_model(self, progress_cb: Callable[[str], None] | None = None):
        with self._lock:
            if self._model is not None:
                return

            from faster_whisper import WhisperModel

            model_size = self._settings.get("whisper_model", "small")
            device, compute_type = _resolve_device_and_compute(self._settings)

            if progress_cb:
                progress_cb(f"Loading Whisper model '{model_size}'…")

            self._model = WhisperModel(
                model_size,
                device=device,
                compute_type=compute_type,
            )

            if progress_cb:
                progress_cb("ready")

    def transcribe(self, audio: np.ndarray) -> str:
        with self._lock:
            if self._model is None:
                self.load_model()

            language = self._settings.get("language", "auto")
            lang_arg = None if language == "auto" else language
            auto_punct = self._settings.get("auto_punctuation", True)

            segments, _ = self._model.transcribe(
                audio,
                language=lang_arg,
                beam_size=5,
                vad_filter=True,
            )

            text = " ".join(seg.text.strip() for seg in segments).strip()

            if not auto_punct:
                text = re.sub(r"[^\w\s]", "", text)

            return text

    def unload(self):
        with self._lock:
            self._model = None
            gc.collect()

    def is_loaded(self) -> bool:
        with self._lock:
            return self._model is not None

    def active_device(self) -> str:
        device, _ = _resolve_device_and_compute(self._settings)
        return device.upper()
