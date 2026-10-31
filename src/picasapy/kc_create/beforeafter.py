"""Before/after side-by-side or swipe-wipe MP4."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageOps

from ._common import ACCENT, GROUND, TEXT, VideoWriter, cover, even, font, load_photo, rgb


def auto_enhance(img: Image.Image) -> Image.Image:
    """A simple 'edited' look used when only one photo is supplied."""
    out = ImageOps.autocontrast(img, cutoff=1)
    out = ImageEnhance.Color(out).enhance(1.25)
    return ImageEnhance.Sharpness(out).enhance(1.6)


def _label(img: Image.Image, text: str, left: bool, fg, bg) -> None:
    d = ImageDraw.Draw(img)
    f = font("bold", max(12, img.width // 22))
    l, t, r, b = d.textbbox((0, 0), text, font=f)
    pad = max(4, img.width // 90)
    x = pad * 2 if left else img.width - (r - l) - pad * 4
    y = pad * 2
    d.rounded_rectangle((x - pad, y - pad, x + (r - l) + pad, y + (b - t) + pad * 1.6), radius=pad, fill=bg)
    d.text((x, y - t), text, font=f, fill=fg)


def make_beforeafter(
    photos: list[Path],
    out: Path,
    *,
    mode: str = "swipe",
    seconds: float = 4.0,
    width: int = 1080,
    fps: int = 30,
    labels: tuple[str, str] = ("BEFORE", "AFTER"),
    ground: str = GROUND,
    text: str = TEXT,
    accent: str = ACCENT,
) -> Path:
    """Two photos (before, after) or one photo plus an auto-enhanced version.

    mode 'swipe': a divider wipes left to right, holds, and wipes back.
    mode 'side': before and after side by side."""
    out = Path(out)
    if mode not in ("swipe", "side"):
        raise ValueError("mode must be 'swipe' or 'side'")
    if not 1 <= len(photos) <= 2:
        raise ValueError("beforeafter needs one or two photos")
    g, t, a = rgb(ground), rgb(text), rgb(accent)
    before = load_photo(photos[0], max_side=width * 2)
    after = load_photo(photos[1], max_side=width * 2) if len(photos) == 2 else auto_enhance(before)
    out.parent.mkdir(parents=True, exist_ok=True)
    if mode == "side":
        gap = max(4, width // 100)
        pw = (width - gap) // 2
        ph = round(pw * before.height / before.width)
        W, H = even(width), even(ph)
        canvas = Image.new("RGB", (W, H), g)
        b, af = cover(before, pw, H), cover(after, pw, H)
        _label(b, labels[0], True, g, a)
        _label(af, labels[1], True, g, a)
        canvas.paste(b, (0, 0))
        canvas.paste(af, (W - pw, 0))
        frame = np.asarray(canvas)
        writer = VideoWriter(out, (W, H), fps)
        try:
            for _ in range(max(1, round(seconds * fps))):
                writer.write(frame)
        finally:
            writer.close()
        return out
    W = even(width)
    H = even(round(W * before.height / before.width))
    b_arr = np.asarray(cover(before, W, H))
    a_img = cover(after, W, H)
    a_arr = np.asarray(a_img)
    n = max(4, round(seconds * fps))
    lab_b = Image.fromarray(b_arr.copy())
    lab_a = Image.fromarray(a_arr.copy())
    _label(lab_b, labels[0], True, g, a)
    _label(lab_a, labels[1], False, g, a)
    b_arr, a_arr = np.asarray(lab_b), np.asarray(lab_a)
    line_w = max(2, W // 300)
    writer = VideoWriter(out, (W, H), fps)
    try:
        for i in range(n):
            u = i / (n - 1)
            # 0->1 wipe in the first 40%, hold, 1->0 in the last 40%
            if u < 0.4:
                p = u / 0.4
            elif u < 0.6:
                p = 1.0
            else:
                p = 1 - (u - 0.6) / 0.4
            p = p * p * (3 - 2 * p)
            x = int(round(p * W))
            frame = b_arr.copy()
            frame[:, :x] = a_arr[:, :x]
            frame[:, max(0, x - line_w // 2) : x + line_w // 2 + 1] = a
            writer.write(frame)
    finally:
        writer.close()
    return out
