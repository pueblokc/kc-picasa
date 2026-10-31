"""Photo mosaic: rebuild a target photo out of tiles of other photos."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from ._common import cover, load_photo


def _variants(img: Image.Image, tile: int) -> list[Image.Image]:
    """Whole photo plus four corner zooms: more distinct tiles from few photos."""
    w, h = img.size
    s = min(w, h)
    boxes = [
        ((w - s) // 2, (h - s) // 2, (w + s) // 2, (h + s) // 2),
    ]
    half = int(s * 0.6)
    for fx, fy in ((0.25, 0.25), (0.75, 0.25), (0.25, 0.75), (0.75, 0.75)):
        cx, cy = int(w * fx), int(h * fy)
        x0 = min(max(cx - half // 2, 0), w - half)
        y0 = min(max(cy - half // 2, 0), h - half)
        boxes.append((x0, y0, x0 + half, y0 + half))
    return [img.crop(b).resize((tile, tile), Image.LANCZOS) for b in boxes]


def make_mosaic(
    photos: list[Path],
    out: Path,
    *,
    target: Path | None = None,
    cols: int = 48,
    tile: int = 32,
    no_repeat: int = 2,
    tint: float = 0.35,
) -> Path:
    """Build a mosaic of `target` (default: the first photo) from the other
    photos. A tile is not reused within `no_repeat` cells (Chebyshev distance)
    of itself when an alternative exists. `tint` (0..1) pulls each tile's colour
    toward the target cell for a sharper likeness."""
    out = Path(out)
    photos = list(photos)
    if target is None:
        if len(photos) < 2:
            raise ValueError("mosaic needs a target and at least one tile photo")
        target, photos = photos[0], photos[1:]
    if not photos:
        raise ValueError("mosaic needs at least one tile photo")
    tgt = load_photo(target, max_side=cols * tile)
    rows = max(1, round(cols * tgt.height / tgt.width))
    small = np.asarray(tgt.resize((cols, rows), Image.BOX), np.uint8)

    tiles: list[np.ndarray] = []
    for p in photos:
        tiles.extend(np.asarray(v) for v in _variants(load_photo(p, max_side=tile * 8), tile))
    tiles_arr = np.stack(tiles).astype(np.float32)  # N,t,t,3
    means = tiles_arr.mean(axis=(1, 2))  # N,3

    def lab(a: np.ndarray) -> np.ndarray:
        return cv2.cvtColor(a.reshape(-1, 1, 3).astype(np.uint8), cv2.COLOR_RGB2LAB).reshape(-1, 3).astype(np.float32)

    tile_lab = lab(means)
    cell_lab = lab(small.reshape(-1, 3)).reshape(rows, cols, 3)
    placed = -np.ones((rows, cols), np.int32)
    canvas = np.zeros((rows * tile, cols * tile, 3), np.uint8)
    rng = np.random.default_rng(1)
    for r in range(rows):
        for c in range(cols):
            dist = np.linalg.norm(tile_lab - cell_lab[r, c], axis=1)
            dist = dist + rng.random(len(dist)) * 0.5  # break ties
            r0, c0 = max(0, r - no_repeat), max(0, c - no_repeat)
            used = placed[r0 : r + 1, c0 : min(cols, c + no_repeat + 1)]
            blocked = np.unique(used[used >= 0])
            # same photo (all 5 variants) counts as reuse of its source image
            if len(blocked) and len(blocked) < len(tile_lab):
                dist[blocked] += 1e6
            k = int(np.argmin(dist))
            placed[r, c] = k
            t = tiles_arr[k]
            if tint > 0:
                shift = (small[r, c].astype(np.float32) - means[k]) * tint
                t = np.clip(t + shift, 0, 255)
            canvas[r * tile : (r + 1) * tile, c * tile : (c + 1) * tile] = t.astype(np.uint8)
    out.parent.mkdir(parents=True, exist_ok=True)
    img = Image.fromarray(canvas)
    if out.suffix.lower() in (".jpg", ".jpeg"):
        img.save(out, quality=92)
    else:
        img.save(out)
    return out
