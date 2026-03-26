"""
System tray icon for DictatorShipping.

Windows: pystray runs in a background thread; tkinter on the main thread.
macOS:   pystray.run_detached() integrates with AppKit non-blockingly,
         then tkinter runs on the main thread as normal.
         Falls back to no-tray if AppKit integration fails.
"""

import sys
import threading


def _build_icon_image():
    from PIL import Image, ImageDraw

    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Blue circle background
    d.ellipse([2, 2, size - 2, size - 2], fill=(29, 78, 216, 255))

    # Microphone body (rounded rect)
    d.rounded_rectangle([22, 11, 42, 36], radius=9, fill="white")

    # Mic stand arc
    d.arc([14, 27, 50, 50], start=0, end=180, fill="white", width=3)

    # Vertical stem + base
    d.line([32, 50, 32, 56], fill="white", width=3)
    d.line([24, 56, 40, 56], fill="white", width=3)

    return img


class TrayManager:
    def __init__(self, on_show_hide, on_quit, app_dir=None):
        self._on_show_hide = on_show_hide
        self._on_quit = on_quit
        self._icon = None
        self._available = False
        self._app_dir = app_dir

    def start(self):
        """
        Start the tray icon.
        Returns True if tray started successfully, False otherwise.
        On Windows, runs in a daemon thread.
        On macOS, uses run_detached() (non-blocking on main thread).
        """
        try:
            import pystray

            if self._app_dir:
                try:
                    from ui.icon import get_pil_image
                    img = get_pil_image(self._app_dir, size=(64, 64))
                except Exception:
                    img = _build_icon_image()
            else:
                img = _build_icon_image()

            menu = pystray.Menu(
                pystray.MenuItem("Show / Hide", lambda icon, item: self._on_show_hide()),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Quit", lambda icon, item: self._on_quit()),
            )
            self._icon = pystray.Icon("DictatorShipping", img, "DictatorShipping", menu)

            if sys.platform == "darwin":
                # run_detached integrates with AppKit without blocking
                self._icon.run_detached()
            else:
                t = threading.Thread(target=self._icon.run, daemon=True)
                t.start()

            self._available = True
            return True

        except Exception as e:
            print(f"[Tray] Could not start system tray: {e}")
            self._available = False
            return False

    def stop(self):
        if self._icon and self._available:
            try:
                self._icon.stop()
            except Exception:
                pass

    @property
    def available(self) -> bool:
        return self._available
