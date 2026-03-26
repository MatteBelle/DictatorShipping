import sys
import time

import pyperclip
from pynput.keyboard import Controller, Key


class TextInjector:
    def __init__(self, settings):
        self._settings = settings
        self._keyboard = Controller()

    def inject(self, text: str):
        if not text:
            return

        delay_ms = self._settings.get("injection_delay_ms", 175)
        time.sleep(delay_ms / 1000.0)

        use_clipboard = self._settings.get("use_clipboard_fallback", False)

        if use_clipboard:
            self._inject_via_clipboard(text)
        else:
            try:
                self._inject_via_pynput(text)
            except Exception as e:
                print(f"[TextInjector] pynput failed ({e}), falling back to clipboard")
                self._inject_via_clipboard(text)

    def _inject_via_pynput(self, text: str):
        self._keyboard.type(text)

    def _inject_via_clipboard(self, text: str):
        previous = ""
        try:
            previous = pyperclip.paste()
        except Exception:
            pass

        pyperclip.copy(text)
        time.sleep(0.05)

        paste_key = Key.cmd if sys.platform == "darwin" else Key.ctrl
        with self._keyboard.pressed(paste_key):
            self._keyboard.press("v")
            self._keyboard.release("v")

        time.sleep(0.1)
        try:
            pyperclip.copy(previous)
        except Exception:
            pass
