"""KC: HEIC / HEIF / AVIF support through the optional `pillow-heif` package.

Install with `pip install -e .[kc]`. Without pillow-heif this module is inert:
`AVAILABLE` is False, `EXTENSIONS` is empty, so the scanner never lists these
files and no other code path changes.

Orientation notes (checked with pillow-heif 1.8 / Pillow 13):
* HEIC: pillow-heif applies the rotation to the pixels and rewrites EXIF
  Orientation to 1, so the indexed size/orientation are already "upright".
* AVIF (Pillow native): pixels are stored unrotated, EXIF Orientation stays.
  `decode_to_pil` applies `exif_transpose`, which is a no-op for orientation 1,
  so both cases come out upright.
"""

from __future__ import annotations

import logging
from pathlib import Path

_log = logging.getLogger(__name__)

HEIF_EXTENSIONS = frozenset({".heic", ".heif", ".hif", ".avif"})

try:
    import pillow_heif
except ImportError:  # optional dependency
    pillow_heif = None
    AVAILABLE = False
else:
    try:
        pillow_heif.register_heif_opener()
        # Pillow >= 11.3 ships an AVIF plugin; older ones need pillow-heif's.
        from PIL import features

        if not features.check("avif") and hasattr(pillow_heif, "register_avif_opener"):
            pillow_heif.register_avif_opener()
        AVAILABLE = True
    except Exception:  # noqa: BLE001 - a broken install must not break the app
        _log.warning("pillow-heif could not be registered; HEIC support off")
        AVAILABLE = False

#: Extensions the scanner should list; empty when the decoder is missing.
EXTENSIONS = HEIF_EXTENSIONS if AVAILABLE else frozenset()


def is_heif(path: str | Path) -> bool:
    """True for a HEIC/HEIF/AVIF file name that we can decode (by extension)."""
    return AVAILABLE and Path(path).suffix.lower() in EXTENSIONS


def qt_reads_natively(path: str | Path) -> bool:
    """True when this Qt build has an image reader for the file's extension."""
    from PySide6.QtGui import QImageReader

    suffix = Path(path).suffix.lower().lstrip(".").encode()
    return suffix in {bytes(f).lower() for f in QImageReader.supportedImageFormats()}


def needs_helper(path: str | Path) -> bool:
    """HEIF family file that Qt cannot read, so it must go through us."""
    return is_heif(path) and not qt_reads_natively(path)


def decode_to_pil(path: str | Path, max_size: int | None = None):
    """Upright RGB(A->RGB) PIL image, longest side capped to `max_size`.

    Returns None when the file cannot be decoded."""
    if not AVAILABLE:
        return None
    from PIL import Image, ImageOps

    try:
        with Image.open(path) as image:
            if max_size:
                image.draft("RGB", (max_size, max_size))
            image.load()
            upright = ImageOps.exif_transpose(image)
            rgb = upright.convert("RGB")
    except (OSError, ValueError, Image.DecompressionBombError) as error:
        _log.warning("HEIF decode failed (%s): %s", error, path)
        return None
    if max_size and max(rgb.size) > max_size:
        rgb.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
    return rgb


def decode_to_qimage(path: str | Path, max_size: int | None = None):
    """Upright `QImage` (RGB888) of the file; a null `QImage` on failure."""
    from PySide6.QtGui import QImage

    rgb = decode_to_pil(path, max_size)
    if rgb is None:
        return QImage()
    width, height = rgb.size
    return QImage(rgb.tobytes(), width, height, width * 3, QImage.Format.Format_RGB888).copy()


def decode_to_bgr(path: str | Path, max_size: int | None = None):
    """Upright BGR uint8 array (cv2 layout) or None; used by the cv2 paths."""
    rgb = decode_to_pil(path, max_size)
    if rgb is None:
        return None
    import numpy as np

    return np.ascontiguousarray(np.asarray(rgb)[:, :, ::-1])
