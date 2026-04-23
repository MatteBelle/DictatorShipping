import gc
import os
import re
import sys
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
        self._loaded_event = threading.Event()

    def load_model(self, progress_cb: Callable[[str], None] | None = None):
        with self._lock:
            if self._model is not None:
                return

            from faster_whisper import WhisperModel

            model_size = self._settings.get("whisper_model", "small")
            device, compute_type = _resolve_device_and_compute(self._settings)

            if progress_cb:
                progress_cb(f"Loading Whisper model '{model_size}'…")

            try:
                # Use threading-based timeout that works on Windows
                result = {"model": None, "error": None}

                def _load_with_timeout():
                    try:
                        result["model"] = WhisperModel(
                            model_size,
                            device=device,
                            compute_type=compute_type,
                            # Limit CPU threads to prevent resource exhaustion
                            cpu_threads=min(4, (os.cpu_count() or 4)),
                            # Set reasonable number of workers
                            num_workers=1,
                        )
                    except Exception as e:
                        result["error"] = e

                loader_thread = threading.Thread(target=_load_with_timeout, daemon=True)
                loader_thread.start()
                loader_thread.join(timeout=30.0)  # 30 second timeout

                if loader_thread.is_alive():
                    raise TimeoutError("Model loading timed out after 30 seconds")

                if result["error"]:
                    raise result["error"]

                self._model = result["model"]
                self._loaded_event.set()

                if progress_cb:
                    progress_cb("ready")

            except Exception as e:
                # Log error but don't crash the app
                import traceback

                print(f"Error loading Whisper model: {e}", file=sys.stderr)
                traceback.print_exc(file=sys.stderr)

                # Try fallback to CPU with smaller model if CUDA failed
                if device == "cuda":
                    try:
                        if progress_cb:
                            progress_cb("GPU failed, trying CPU…")
                        self._model = WhisperModel(
                            "tiny",  # Use smallest model as fallback
                            device="cpu",
                            compute_type="int8",
                            cpu_threads=2,
                            num_workers=1,
                        )
                        self._loaded_event.set()
                        if progress_cb:
                            progress_cb("ready")
                    except Exception as e2:
                        if progress_cb:
                            progress_cb(f"Model load failed: {str(e2)[:30]}")
                        raise
                else:
                    if progress_cb:
                        progress_cb(f"Model load failed: {str(e)[:30]}")
                    raise

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
        return self._loaded_event.is_set()

    def active_device(self) -> str:
        device, _ = _resolve_device_and_compute(self._settings)
        return device.upper()
