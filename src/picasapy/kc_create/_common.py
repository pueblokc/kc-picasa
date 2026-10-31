"""Shared helpers for the KC Creative Projects engine.

Everything here is UI-free: image loading with EXIF orientation, colours,
fonts, face focus points and a small ffmpeg pipe writer.
"""

from __future__ import annotations

import datetime as _dt
import re
import subprocess
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

# Dark-friendly defaults (callers can override every one of them).
GROUND = "#0f1417"
TEXT = "#cfc9bb"
ACCENT = "#4d8f85"

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}

_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def rgb(colour: str | tuple[int, int, int]) -> tuple[int, int, int]:
    """'#rrggbb' / 'rgb' / tuple -> (r, g, b)."""
    if isinstance(colour, tuple):
        return (int(colour[0]), int(colour[1]), int(colour[2]))
    value = colour.strip().lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    if not re.fullmatch(r"[0-9a-fA-F]{6}", value):
        raise ValueError(f"bad colour: {colour!r}")
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))


def expand_photos(items: Iterable[str | Path]) -> list[Path]:
    """Files stay as they are; directories expand to their images (sorted)."""
    result: list[Path] = []
    for item in items:
        path = Path(item)
        if path.is_dir():
            result.extend(
                sorted(p for p in path.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
            )
        else:
            result.append(path)
    return result


def load_photo(path: str | Path, max_side: int | None = None) -> Image.Image:
    """Open an image as RGB with EXIF orientation applied."""
    with Image.open(path) as opened:
        if max_side and opened.format == "JPEG":
            opened.draft("RGB", (max_side * 2, max_side * 2))
        image = ImageOps.exif_transpose(opened)
        image = image.convert("RGB")
    if max_side and max(image.size) > max_side:
        image.thumbnail((max_side, max_side), Image.LANCZOS)
    return image


def photo_date(path: str | Path) -> _dt.datetime:
    """EXIF capture date, falling back to the file's modified time."""
    try:
        with Image.open(path) as image:
            exif = image.getexif()
            raw = None
            try:
                raw = exif.get_ifd(0x8769).get(36867)
            except Exception:
                raw = None
            raw = raw or exif.get(306)
        if raw:
            return _dt.datetime.strptime(str(raw)[:19], "%Y:%m:%d %H:%M:%S")
    except Exception:
        pass
    return _dt.datetime.fromtimestamp(Path(path).stat().st_mtime)


_FONT_FILES = {
    "sans": ["segoeui.ttf", "arial.ttf", "DejaVuSans.ttf", "Helvetica.ttc"],
    "bold": ["segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"],
    "serif": ["georgia.ttf", "times.ttf", "DejaVuSerif.ttf"],
    "hand": ["Inkfree.ttf", "segoepr.ttf", "comic.ttf", "DejaVuSans-Oblique.ttf"],
    "mono": ["consola.ttf", "cour.ttf", "DejaVuSansMono.ttf"],
}


def font(kind: str, size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    """A TrueType font of the given family, or Pillow's scalable default."""
    for name in _FONT_FILES.get(kind, _FONT_FILES["sans"]):
        try:
            return ImageFont.truetype(name, max(6, int(size)))
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=max(6, int(size)))
    except TypeError:  # very old Pillow
        return ImageFont.load_default()


def text_size(draw: ImageDraw.ImageDraw, text: str, fnt) -> tuple[int, int]:
    left, top, right, bottom = draw.textbbox((0, 0), text, font=fnt)
    return right - left, bottom - top


def wrap_text(draw: ImageDraw.ImageDraw, text: str, fnt, max_width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in str(text).split("\n"):
        current = ""
        for word in paragraph.split():
            trial = f"{current} {word}".strip()
            if text_size(draw, trial, fnt)[0] <= max_width or not current:
                current = trial
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


def fit_font(draw, text: str, kind: str, max_width: int, start: int, minimum: int = 10):
    """Largest font (<= start) whose single-line text fits in max_width."""
    size = start
    while size > minimum:
        fnt = font(kind, size)
        if text_size(draw, text, fnt)[0] <= max_width:
            return fnt
        size -= 2
    return font(kind, minimum)


def draw_centered(draw, xy_center: tuple[float, float], text: str, fnt, fill) -> None:
    draw.text(xy_center, text, font=fnt, fill=fill, anchor="mm")


def cover(image: Image.Image, width: int, height: int, focus=(0.5, 0.5)) -> Image.Image:
    """Resize + crop to exactly width x height, cropping around `focus` (0..1)."""
    sw, sh = image.size
    scale = max(width / sw, height / sh)
    nw, nh = max(width, round(sw * scale)), max(height, round(sh * scale))
    resized = image.resize((nw, nh), Image.LANCZOS)
    left = int(round(min(max(focus[0] * nw - width / 2, 0), nw - width)))
    top = int(round(min(max(focus[1] * nh - height / 2, 0), nh - height)))
    return resized.crop((left, top, left + width, top + height))


def contain(image: Image.Image, width: int, height: int) -> Image.Image:
    """Resize to fit inside width x height, keeping aspect (no padding)."""
    scale = min(width / image.width, height / image.height)
    return image.resize(
        (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
        Image.LANCZOS,
    )


def shadow_layer(size: tuple[int, int], radius: int, opacity: int = 150) -> Image.Image:
    """Blurred black rectangle (L mode) used to drop shadows."""
    pad = radius * 3
    layer = Image.new("L", (size[0] + pad * 2, size[1] + pad * 2), 0)
    ImageDraw.Draw(layer).rectangle(
        (pad, pad, pad + size[0] - 1, pad + size[1] - 1), fill=opacity
    )
    return layer.filter(ImageFilter.GaussianBlur(radius))


def paste_with_shadow(
    canvas: Image.Image,
    tile: Image.Image,
    xy: tuple[int, int],
    radius: int = 14,
    offset: tuple[int, int] = (0, 8),
    opacity: int = 150,
) -> None:
    layer = shadow_layer(tile.size, radius, opacity)
    pad = radius * 3
    black = Image.new("RGB", layer.size, (0, 0, 0))
    canvas.paste(black, (xy[0] - pad + offset[0], xy[1] - pad + offset[1]), layer)
    canvas.paste(tile, xy)


def rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    scale = 4
    mask = Image.new("L", (size[0] * scale, size[1] * scale), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, size[0] * scale - 1, size[1] * scale - 1), radius * scale, fill=255
    )
    return mask.resize(size, Image.LANCZOS)


# ---------------------------------------------------------------- faces

_detector = None
_detector_tried = False


def face_boxes(image: Image.Image) -> list[tuple[float, float, float, float]]:
    """Faces as normalised (left, top, right, bottom). [] if none/unavailable."""
    global _detector, _detector_tried
    if not _detector_tried:
        _detector_tried = True
        try:
            from picasapy.faces.detector import FaceDetector

            candidate = FaceDetector()
            _detector = candidate if candidate.available else None
        except Exception:
            _detector = None
    if _detector is None:
        return []
    small = image.copy()
    small.thumbnail((640, 640))
    try:
        import cv2

        bgr = cv2.cvtColor(np.asarray(small), cv2.COLOR_RGB2BGR)
        found = _detector.detect(bgr)
    except Exception:
        return []
    w, h = small.size
    return [(f.left / w, f.top / h, f.right / w, f.bottom / h) for f in found]


def face_focus(
    boxes: list[tuple[float, float, float, float]],
) -> tuple[float, float] | None:
    """Area-weighted centre of the faces (None when there are none)."""
    if not boxes:
        return None
    weights = [max(1e-6, (b[2] - b[0]) * (b[3] - b[1])) for b in boxes]
    total = sum(weights)
    cx = sum((b[0] + b[2]) / 2 * wt for b, wt in zip(boxes, weights)) / total
    cy = sum((b[1] + b[3]) / 2 * wt for b, wt in zip(boxes, weights)) / total
    return (cx, cy)


# --------------------------------------------------------------- ffmpeg


def ffmpeg_exe() -> str:
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def run_ffmpeg(args: list[str]) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", *args],
        capture_output=True,
        creationflags=_NO_WINDOW,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            "ffmpeg failed: " + proc.stderr.decode("utf-8", "replace")[-800:]
        )
    return proc


class VideoWriter:
    """Pipe RGB frames to ffmpeg (H.264 yuv420p, optional audio filter graph)."""

    def __init__(
        self,
        out: Path,
        size: tuple[int, int],
        fps: float,
        audio: Path | None = None,
        duration: float | None = None,
        audio_filter: str | None = None,
        crf: int = 20,
    ) -> None:
        self.size = size
        args = [
            ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
            "-f", "rawvideo", "-pix_fmt", "rgb24",
            "-s", f"{size[0]}x{size[1]}", "-r", f"{fps:g}", "-i", "-",
        ]  # fmt: skip
        if audio is not None:
            args += ["-stream_loop", "-1", "-i", str(audio)]
            args += ["-filter_complex", f"[1:a]{audio_filter}[a]"]
            args += ["-map", "0:v", "-map", "[a]", "-c:a", "aac", "-b:a", "192k"]
            if duration:
                args += ["-t", f"{duration:.3f}"]
        args += [
            "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf),
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out),
        ]  # fmt: skip
        self._proc = subprocess.Popen(
            args,
            stdin=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=_NO_WINDOW,
        )

    def write(self, frame: np.ndarray) -> None:
        assert frame.shape[1] == self.size[0] and frame.shape[0] == self.size[1]
        self._proc.stdin.write(np.ascontiguousarray(frame, dtype=np.uint8).tobytes())

    def close(self) -> None:
        self._proc.stdin.close()
        err = self._proc.stderr.read()
        code = self._proc.wait()
        if code != 0:
            raise RuntimeError("ffmpeg failed: " + err.decode("utf-8", "replace")[-800:])


def even(value: float) -> int:
    return max(2, int(round(value / 2)) * 2)


def probe(path: str | Path) -> dict:
    """Duration / size / streams from `ffmpeg -i` (no ffprobe needed)."""
    proc = subprocess.run(
        [ffmpeg_exe(), "-hide_banner", "-i", str(path)],
        capture_output=True,
        creationflags=_NO_WINDOW,
    )
    text = proc.stderr.decode("utf-8", "replace")
    info: dict = {"has_audio": "Audio:" in text, "has_video": "Video:" in text}
    m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", text)
    if m:
        info["duration"] = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])
    m = re.search(r"Video: (\w+).*?, (\d{2,5})x(\d{2,5})", text)
    if m:
        info["codec"] = m[1]
        info["width"], info["height"] = int(m[2]), int(m[3])
    m = re.search(r"Video:.*?(yuv\w+)", text)
    if m:
        info["pix_fmt"] = m[1]
    m = re.search(r"Audio: (\w+)", text)
    if m:
        info["audio_codec"] = m[1]
    return info


def chunks(seq: list, n: int) -> Iterator[list]:
    for i in range(0, len(seq), n):
        yield seq[i : i + n]
