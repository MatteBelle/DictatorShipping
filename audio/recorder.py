import threading
import numpy as np
import sounddevice as sd


class AudioRecorder:
    def __init__(self, settings):
        self._settings = settings
        self._frames: list[np.ndarray] = []
        self._recording = False
        self._lock = threading.Lock()
        self._stream: sd.InputStream | None = None

    def start(self):
        with self._lock:
            self._frames = []
            self._recording = True

        device = self._settings.get("input_device_index")
        sample_rate = self._settings.get("sample_rate", 16000)

        self._stream = sd.InputStream(
            samplerate=sample_rate,
            channels=1,
            dtype="float32",
            device=device,
            callback=self._callback,
        )
        self._stream.start()

    def stop(self) -> np.ndarray:
        with self._lock:
            self._recording = False

        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        with self._lock:
            if self._frames:
                audio = np.concatenate(self._frames, axis=0).flatten()
            else:
                audio = np.zeros(0, dtype="float32")
            self._frames = []

        return audio

    @property
    def level(self) -> float:
        """RMS amplitude of the most recent audio chunk (0.0 – 1.0)."""
        with self._lock:
            if not self._frames:
                return 0.0
            return float(np.sqrt(np.mean(self._frames[-1] ** 2)))

    def _callback(self, indata: np.ndarray, frames: int, time, status):
        with self._lock:
            if self._recording:
                self._frames.append(indata.copy())

    def list_devices(self) -> list[dict]:
        devices = sd.query_devices()
        result = []
        for i, d in enumerate(devices):
            if d["max_input_channels"] > 0:
                result.append({"index": i, "name": d["name"]})
        return result
