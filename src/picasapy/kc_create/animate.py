"""Animated GIF / WebP / MP4 loop from a burst or a selection of photos."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from ._common import VideoWriter, cover, even, load_photo


def _stabilise(frames: list[Image.Image]) -> list[Image.Image]:
    """Align every frame to the first with OpenCV ECC (Euclidean motion)."""
    ref = np.asarray(frames[0])
    scale = min(1.0, 320 / max(ref.shape[:2]))
    gray_ref = cv2.cvtColor(cv2.resize(ref, None, fx=scale, fy=scale), cv2.COLOR_RGB2GRAY)
    criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 60, 1e-5)
    out = [frames[0]]
    for frame in frames[1:]:
        arr = np.asarray(frame)
        gray = cv2.cvtColor(cv2.resize(arr, None, fx=scale, fy=scale), cv2.COLOR_RGB2GRAY)
        warp = np.eye(2, 3, dtype=np.float32)
        try:
            _cc, warp = cv2.findTransformECC(
                gray_ref, gray, warp, cv2.MOTION_EUCLIDEAN, criteria, None, 5
            )
        except cv2.error:
            out.append(frame)
            continue
        warp[:, 2] /= scale  # translation back to full-size pixels
        aligned = cv2.warpAffine(
            arr,
            warp,
            (arr.shape[1], arr.shape[0]),
            flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
            borderMode=cv2.BORDER_REPLICATE,
        )
        out.append(Image.fromarray(aligned))
    return out


def _gif_palette(frames: list[Image.Image], colors: int) -> Image.Image:
    """One shared palette built from a montage of all frames."""
    thumbs = [f.resize((64, 64)) for f in frames]
    montage = Image.new("RGB", (64 * len(thumbs), 64))
    for i, thumb in enumerate(thumbs):
        montage.paste(thumb, (i * 64, 0))
    return montage.quantize(colors=colors, method=Image.MEDIANCUT, dither=Image.NONE)


def _write_gif(frames, out: Path, fps: float, loop: int, colors: int) -> None:
    palette = _gif_palette(frames, colors)
    quant = [f.quantize(palette=palette, dither=Image.FLOYDSTEINBERG) for f in frames]
    quant[0].save(
        out,
        save_all=True,
        append_images=quant[1:],
        duration=max(20, round(1000 / fps)),
        loop=loop,
        optimize=False,
        disposal=1,
    )


def _write_webp(frames, out: Path, fps: float, loop: int, quality: int) -> None:
    frames[0].save(
        out,
        save_all=True,
        append_images=frames[1:],
        duration=max(20, round(1000 / fps)),
        loop=loop,
        quality=quality,
        method=4,
    )


def _write_mp4(frames, out: Path, fps: float, loops: int) -> None:
    size = (even(frames[0].width), even(frames[0].height))
    writer = VideoWriter(out, size, fps)
    try:
        for _ in range(max(1, loops)):
            for frame in frames:
                writer.write(np.asarray(frame.resize(size) if frame.size != size else frame))
    finally:
        writer.close()


def make_animation(
    photos: list[Path],
    out: Path,
    *,
    fps: float = 8.0,
    width: int = 480,
    boomerang: bool = False,
    stabilize: bool = False,
    loop: int = 0,
    loops: int = 3,
    colors: int = 128,
    quality: int = 80,
    max_bytes: int | None = None,
) -> Path:
    """Animate `photos` into a GIF / WebP / MP4 (chosen by the `out` suffix).

    boomerang plays forward then backward; stabilize aligns frames with ECC;
    `max_bytes` shrinks width/palette/quality until the file fits (GIF/WebP).
    `loop` is the GIF/WebP loop count (0 = forever); `loops` repeats an MP4.
    """
    out = Path(out)
    if not photos:
        raise ValueError("animate needs at least one photo")
    suffix = out.suffix.lower()
    if suffix not in {".gif", ".webp", ".mp4"}:
        raise ValueError("output must end in .gif, .webp or .mp4")

    loaded = [load_photo(p, max_side=max(width, 480) * 2) for p in photos]
    base = loaded[0]
    ratio = base.height / base.width
    full_w = max(16, width)
    full_h = max(16, round(full_w * ratio))
    # crop every frame to the first frame's shape (never stretch)
    frames = [cover(img, full_w, full_h) for img in loaded]
    if stabilize and len(frames) > 1:
        frames = _stabilise(frames)
    if boomerang and len(frames) > 2:
        frames = frames + frames[-2:0:-1]
    elif boomerang and len(frames) == 2:
        frames = frames + frames[:1]

    out.parent.mkdir(parents=True, exist_ok=True)

    def render(scale: float, ncolors: int, q: int) -> None:
        w = even(full_w * scale)
        h = even(full_h * scale)
        sized = frames if scale == 1.0 and (w, h) == frames[0].size else [
            f.resize((w, h), Image.LANCZOS) for f in frames
        ]
        if suffix == ".gif":
            _write_gif(sized, out, fps, loop, ncolors)
        elif suffix == ".webp":
            _write_webp(sized, out, fps, loop, q)
        else:
            _write_mp4(sized, out, fps, loops)

    render(1.0, colors, quality)
    if max_bytes and suffix in {".gif", ".webp"}:
        scale, ncolors, q = 1.0, colors, quality
        while out.stat().st_size > max_bytes and scale > 0.15:
            scale *= 0.85
            ncolors = max(32, int(ncolors * 0.8))
            q = max(25, q - 8)
            render(scale, ncolors, q)
    return out
