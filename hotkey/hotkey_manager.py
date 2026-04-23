import threading
from typing import Callable

from pynput import keyboard


def _parse_hotkey(hotkey_str: str) -> tuple[set, keyboard.Key | keyboard.KeyCode | None]:
    """Parse '<ctrl>+<space>' into (modifiers_set, trigger_key)."""
    parts = [p.strip() for p in hotkey_str.lower().split("+")]
    modifiers = set()
    trigger = None

    modifier_map = {
        "<ctrl>": {keyboard.Key.ctrl_l, keyboard.Key.ctrl_r, keyboard.Key.ctrl},
        "<shift>": {keyboard.Key.shift_l, keyboard.Key.shift_r, keyboard.Key.shift},
        "<alt>": {keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt},
        "<cmd>": {keyboard.Key.cmd_l, keyboard.Key.cmd_r, keyboard.Key.cmd},
        "<super>": {keyboard.Key.cmd_l, keyboard.Key.cmd_r, keyboard.Key.cmd},
    }

    for part in parts:
        if part in modifier_map:
            modifiers |= modifier_map[part]
        else:
            # Try special key first
            try:
                trigger = keyboard.Key[part.strip("<>")]
            except KeyError:
                # Plain character key
                trigger = keyboard.KeyCode.from_char(part)

    return modifiers, trigger


_HOTKEY = "<ctrl>+<space>"


class HotkeyManager:
    def __init__(self):
        self._listener: keyboard.Listener | None = None
        self._pressed_keys: set = set()
        self._hotkey_active = False
        self._lock = threading.Lock()
        self._on_press_cb: Callable | None = None
        self._on_release_cb: Callable | None = None
        self._modifiers, self._trigger = _parse_hotkey(_HOTKEY)
        self._cancel_trigger = None
        self._cancel_cb: Callable | None = None

    def start(self, on_press_cb: Callable, on_release_cb: Callable):
        self._on_press_cb = on_press_cb
        self._on_release_cb = on_release_cb
        self._listener = keyboard.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release,
        )
        self._listener.daemon = True
        self._listener.start()

    def set_cancel_callback(self, trigger_key, cb: Callable):
        self._cancel_trigger = trigger_key
        self._cancel_cb = cb

    def stop(self):
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    def _key_matches_trigger(self, key) -> bool:
        if self._trigger is None:
            return False
        if isinstance(self._trigger, keyboard.KeyCode) and isinstance(key, keyboard.KeyCode):
            return self._trigger.char == key.char
        return key == self._trigger

    def _modifiers_satisfied(self) -> bool:
        if not self._modifiers:
            return True
        # At least one key from each modifier group must be pressed
        # Group modifiers by base type (ctrl, shift, alt, cmd)
        groups = {}
        for mod in self._modifiers:
            name = mod.name if hasattr(mod, "name") else str(mod)
            base = name.rstrip("_lr").rstrip("_")
            groups.setdefault(base, set()).add(mod)

        for base, variants in groups.items():
            if not (variants & self._pressed_keys):
                return False
        return True

    def _on_key_press(self, key):
        with self._lock:
            self._pressed_keys.add(key)

            if self._key_matches_trigger(key) and self._modifiers_satisfied():
                if not self._hotkey_active:
                    self._hotkey_active = True
                    if self._on_press_cb:
                        self._on_press_cb()

            if self._cancel_cb and self._cancel_trigger is not None and key == self._cancel_trigger:
                self._cancel_cb()

    def _on_key_release(self, key):
        with self._lock:
            self._pressed_keys.discard(key)

            if self._hotkey_active and self._key_matches_trigger(key):
                self._hotkey_active = False
                if self._on_release_cb:
                    self._on_release_cb()
