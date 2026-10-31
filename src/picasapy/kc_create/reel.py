"""Photo video / reel: Ken Burns, crossfades, title card, captions, music."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

from ._common import (
    ACCENT,
    GROUND,
    TEXT,
    VideoWriter,
    face_boxes,
    face_focus,
    fit_font,
    font,
    load_photo,
    rgb,
    text_size,
    wrap_text,
)

SIZES = {"9:16": (1080, 1920), "4:5": (1080, 1350), "16:9": (1920, 1080)}


def output_size(size: str, scale: float = 1.0) -> tuple[int, int]:
    if size not in SIZES:
        raise ValueError(f"size must be one of {sorted(SIZES)}")
    w, h = SIZES[size]
    return (max(2, round(w * scale / 2) * 2), max(2, round(h * scale / 2) * 2))


class _Clip:
    """One photo animated as a Ken Burns move at the target size."""

    def __init__(self, image: Image.Image, focus, size, index, strength, kenburns):
        self.W, self.H = size
        iw, ih = image.size
        # largest target-aspect window inside the photo
        aspect = self.W / self.H
        bw = min(iw, ih * aspect)
        bh = bw / aspect
        # pre-scale so the base window is ~1.4x the output (quality when zooming)
        k = min(1.0, 1.4 * self.W / bw)
        if k < 1.0:
            image = image.resize((max(1, round(iw * k)), max(1, round(ih * k))), Image.LANCZOS)
        self.src = np.asarray(image)
        self.bw, self.bh = bw * k, bh * k
        ih2, iw2 = self.src.shape[:2]
        fx, fy = (focus[0] * iw2, focus[1] * ih2) if focus else (iw2 / 2, ih2 / 2)
        self.has_focus = focus is not None
        z_end = 1.0 + strength
        zoom_in = index % 2 == 0
        self.z0, self.z1 = (1.0, z_end) if zoom_in else (z_end, 1.0)
        c_mid = (fx, fy)
        if not kenburns:
            self.z0 = self.z1 = 1.0
        if self.has_focus:
            # zoom toward the faces: the close end sits on them, the wide end is centred
            ctr = (iw2 / 2, ih2 / 2)
            c_wide = (
                (fx + ctr[0]) / 2,
                (fy + ctr[1]) / 2,
            )
            self.c0, self.c1 = (c_wide, c_mid) if zoom_in else (c_mid, c_wide)
        else:
            # gentle pan across the picture
            span_x = max(0.0, iw2 - self.bw) / 2 * 0.6
            span_y = max(0.0, ih2 - self.bh) / 2 * 0.6
            sx = 1 if (index // 2) % 2 == 0 else -1
            self.c0 = (iw2 / 2 - span_x * sx, ih2 / 2 - span_y * sx)
            self.c1 = (iw2 / 2 + span_x * sx, ih2 / 2 + span_y * sx)
            if not kenburns:
                self.c0 = self.c1 = (iw2 / 2, ih2 / 2)
        self.overlay: tuple[np.ndarray, np.ndarray] | None = None  # rgb, alpha(0..1)

    def frame(self, p: float) -> np.ndarray:
        p = min(1.0, max(0.0, p))
        e = p * p * (3 - 2 * p)  # smoothstep
        zoom = self.z0 + (self.z1 - self.z0) * e
        cx = self.c0[0] + (self.c1[0] - self.c0[0]) * e
        cy = self.c0[1] + (self.c1[1] - self.c0[1]) * e
        ww, wh = self.bw / zoom, self.bh / zoom
        ih, iw = self.src.shape[:2]
        cx = min(max(cx, ww / 2), iw - ww / 2)
        cy = min(max(cy, wh / 2), ih - wh / 2)
        s = self.W / ww
        mat = np.array(
            [[s, 0, -(cx - ww / 2) * s], [0, s, -(cy - wh / 2) * s]], dtype=np.float32
        )
        out = cv2.warpAffine(
            self.src, mat, (self.W, self.H), flags=cv2.INTER_AREA if s < 0.7 else cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REPLICATE,
        )
        if self.overlay is not None:
            colour, alpha = self.overlay
            a = alpha * min(1.0, p / 0.12, (1 - p) / 0.12 if p > 0.88 else 1.0)
            out = (out * (1 - a[..., None]) + colour * a[..., None]).astype(np.uint8)
        return out


def _caption_overlay(text: str, size, text_col, ground) -> tuple[np.ndarray, np.ndarray]:
    W, H = size
    layer = Image.new("L", (W, H), 0)
    probe = ImageDraw.Draw(layer)
    fnt = font("sans", max(14, round(W * 0.045)))
    lines = wrap_text(probe, text, fnt, int(W * 0.84))[:3]
    lh = text_size(probe, "Ag", fnt)[1] * 1.4
    block = lh * len(lines)
    band_top = int(H * 0.93 - block - W * 0.04)
    band_top = max(0, band_top)
    alpha = np.zeros((H, W), np.float32)
    ramp = np.linspace(0, 0.78, H - band_top, dtype=np.float32)
    alpha[band_top:, :] = ramp[:, None]
    colour = np.empty((H, W, 3), np.uint8)
    colour[:] = ground
    img = Image.fromarray(colour)
    d = ImageDraw.Draw(img)
    y = H * 0.93 - block
    for line in lines:
        d.text((W / 2, y), line, font=fnt, fill=text_col, anchor="ma")
        y += lh
    tmask = Image.new("L", (W, H), 0)
    td = ImageDraw.Draw(tmask)
    y = H * 0.93 - block
    for line in lines:
        td.text((W / 2, y), line, font=fnt, fill=255, anchor="ma")
        y += lh
    alpha = np.maximum(alpha, np.asarray(tmask, np.float32) / 255.0)
    return np.asarray(img), alpha


def _title_card(title: str, subtitle: str | None, size, ground, text_col, accent) -> np.ndarray:
    W, H = size
    img = Image.new("RGB", (W, H), ground)
    d = ImageDraw.Draw(img)
    fnt = fit_font(d, title, "serif", int(W * 0.8), int(W * 0.11), 14)
    lines = wrap_text(d, title, fnt, int(W * 0.8))
    lh = text_size(d, "Ag", fnt)[1] * 1.35
    y = H / 2 - lh * len(lines) / 2
    for line in lines:
        d.text((W / 2, y), line, font=fnt, fill=text_col, anchor="ma")
        y += lh
    d.rectangle((W * 0.4, y + lh * 0.3, W * 0.6, y + lh * 0.3 + max(2, H * 0.004)), fill=accent)
    if subtitle:
        sf = font("sans", max(12, round(W * 0.04)))
        d.text((W / 2, y + lh * 0.8), subtitle, font=sf, fill=accent, anchor="ma")
    return np.asarray(img)


class _StaticClip:
    def __init__(self, frame: np.ndarray):
        self._frame = frame

    def frame(self, p: float) -> np.ndarray:
        return self._frame


def _audio_filter(total: float, fade_in: float, fade_out: float) -> str:
    fo = max(0.0, total - fade_out)
    return (
        f"atrim=0:{total:.3f},asetpts=PTS-STARTPTS,"
        f"afade=t=in:st=0:d={fade_in:.2f},afade=t=out:st={fo:.3f}:d={fade_out:.2f},"
        "loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000"
    )


def make_reel(
    photos: list[Path],
    out: Path,
    *,
    size: str = "9:16",
    scale: float = 1.0,
    seconds_per_photo: float = 3.0,
    crossfade: float = 0.6,
    fps: int = 30,
    title: str | None = None,
    subtitle: str | None = None,
    title_seconds: float = 2.0,
    captions: list[str] | None = None,
    music: Path | None = None,
    kenburns: bool = True,
    zoom: float = 0.18,
    faces: bool = True,
    all_sizes: bool = False,
    ground: str = GROUND,
    text: str = TEXT,
    accent: str = ACCENT,
) -> Path:
    """Render a Ken Burns reel. With `all_sizes` it writes three files named
    `<stem>_9x16.mp4`, `<stem>_4x5.mp4`, `<stem>_16x9.mp4` and returns the 9:16 one."""
    out = Path(out)
    if not photos:
        raise ValueError("reel needs at least one photo")
    out.parent.mkdir(parents=True, exist_ok=True)
    # decode + face-detect once, reuse for every size
    images, foci = [], []
    for path in photos:
        img = load_photo(path, max_side=2400)
        images.append(img)
        foci.append(face_focus(face_boxes(img)) if faces else None)
    if all_sizes:
        first = None
        for name in SIZES:
            target = out.with_name(f"{out.stem}_{name.replace(':', 'x')}{out.suffix or '.mp4'}")
            res = _render(
                images, foci, target, name, scale, seconds_per_photo, crossfade, fps,
                title, subtitle, title_seconds, captions, music, kenburns, zoom,
                ground, text, accent,
            )  # fmt: skip
            first = first or res
        return first
    return _render(
        images, foci, out, size, scale, seconds_per_photo, crossfade, fps,
        title, subtitle, title_seconds, captions, music, kenburns, zoom,
        ground, text, accent,
    )  # fmt: skip


def _render(
    images, foci, out, size_name, scale, spp, xfade, fps, title, subtitle, title_s,
    captions, music, kenburns, zoom, ground, text, accent,
) -> Path:  # fmt: skip
    size = output_size(size_name, scale)
    g, t, a = rgb(ground), rgb(text), rgb(accent)
    xfade = min(max(0.0, xfade), spp * 0.45)
    clips: list = []
    durations: list[float] = []
    if title:
        clips.append(_StaticClip(_title_card(title, subtitle, size, g, t, a)))
        durations.append(max(title_s, xfade * 2 + 0.5))
    for i, (img, focus) in enumerate(zip(images, foci)):
        clip = _Clip(img, focus, size, i, zoom, kenburns)
        if captions and i < len(captions) and captions[i]:
            clip.overlay = _caption_overlay(captions[i], size, t, g)
        clips.append(clip)
        durations.append(spp)
    starts, cursor = [], 0.0
    for d in durations:
        starts.append(cursor)
        cursor += d - xfade
    total = starts[-1] + durations[-1]
    n_frames = int(round(total * fps))

    audio_filter = _audio_filter(total, 1.5, min(2.5, total / 3)) if music else None
    writer = VideoWriter(
        out, size, fps, audio=Path(music) if music else None, duration=total,
        audio_filter=audio_filter,
    )  # fmt: skip
    try:
        for f in range(n_frames):
            now = f / fps
            active = [
                i for i, s in enumerate(starts) if s <= now < s + durations[i]
            ] or [len(clips) - 1]
            frames = []
            for i in active[-2:]:
                frames.append((i, clips[i].frame((now - starts[i]) / durations[i])))
            if len(frames) == 2:
                (i0, f0), (i1, f1) = frames
                mix = min(1.0, max(0.0, (now - starts[i1]) / xfade)) if xfade else 1.0
                frame = (f0 * (1 - mix) + f1 * mix).astype(np.uint8)
            else:
                frame = frames[0][1]
            writer.write(frame)
    finally:
        writer.close()
    return out
