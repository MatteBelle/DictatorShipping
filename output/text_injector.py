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
        previous = None
        clipboard_changed = False

        try:
            # Only save clipboard if we're using fallback mode
            # Minimizes exposure window
            try:
                previous = pyperclip.paste()
                clipboard_changed = True
            except Exception:
                pass

            pyperclip.copy(text)
            time.sleep(0.05)

            paste_key = Key.cmd if sys.platform == "darwin" else Key.ctrl
            with self._keyboard.pressed(paste_key):
                self._keyboard.press("v")
                self._keyboard.release("v")

            time.sleep(0.1)

        finally:
            # Always restore clipboard in finally block
            if clipboard_changed and previous is not None:
                try:
                    pyperclip.copy(previous)
                except Exception:
                    # If restore fails, at least clear the transcribed text
                    try:
                        pyperclip.copy("")
                    except Exception:
                        pass
