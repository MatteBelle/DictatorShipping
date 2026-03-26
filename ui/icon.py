"""
Icon helpers for DictatorShipping.

  build_ico(app_dir)           → Path  (creates/updates .ico from JPG)
  get_pil_image(app_dir, size) → PIL Image (white background removed)
"""
from pathlib import Path


def _jpg_path(app_dir: Path) -> Path:
    return app_dir / "DictatorShipping.jpg"


def _remove_white_bg(img):
    """Flood-fill transparent from every corner to strip the white background."""
    from PIL import ImageDraw
    img = img.convert("RGBA")
    w, h = img.size
    for pt in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]:
        ImageDraw.floodfill(img, pt, (0, 0, 0, 0), thresh=28)
    return img


def build_ico(app_dir: Path) -> Path:
    """Convert DictatorShipping.jpg → .ico (regenerates whenever JPG is newer)."""
    ico_path = app_dir / "DictatorShipping.ico"
    jpg_path = _jpg_path(app_dir)

    if not jpg_path.exists():
        return ico_path

    # Skip rebuild if ico already exists and is at least as fresh as the jpg
    if ico_path.exists() and ico_path.stat().st_mtime >= jpg_path.stat().st_mtime:
        return ico_path

    from PIL import Image
    img = Image.open(jpg_path).convert("RGBA")
    img = _remove_white_bg(img)
    img.save(
        str(ico_path),
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    return ico_path


def get_pil_image(app_dir: Path, size: tuple = (64, 64)):
    """Return a PIL Image resized to *size* with white background removed."""
    from PIL import Image
    jpg_path = _jpg_path(app_dir)
    if jpg_path.exists():
        img = Image.open(jpg_path).convert("RGBA")
        img = _remove_white_bg(img)
        img = img.resize(size, Image.LANCZOS)
        return img
    return _fallback_image(size)


def _fallback_image(size: tuple = (64, 64)):
    from PIL import Image, ImageDraw
    w, h = size
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([2, 2, w - 2, h - 2], fill=(29, 78, 216, 255))
    cx = w // 2
    d.rounded_rectangle([cx - 10, int(h * 0.17), cx + 10, int(h * 0.56)], radius=9, fill="white")
    d.arc([int(w * 0.22), int(h * 0.42), int(w * 0.78), int(h * 0.78)], start=0, end=180, fill="white", width=3)
    d.line([cx, int(h * 0.78), cx, int(h * 0.875)], fill="white", width=3)
    d.line([int(w * 0.375), int(h * 0.875), int(w * 0.625), int(h * 0.875)], fill="white", width=3)
    return img
