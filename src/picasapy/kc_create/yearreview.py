"""Year in review: pick the best photos of a year, then render a reel."""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np

from ._common import face_boxes, load_photo, photo_date
from .reel import make_reel


def sharpness(img) -> float:
    gray = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def phash(img) -> int:
    """64-bit perceptual hash (DCT of a 32x32 grey thumbnail)."""
    gray = cv2.cvtColor(np.asarray(img.resize((32, 32))), cv2.COLOR_RGB2GRAY)
    low = cv2.dct(np.float32(gray))[:8, :8]
    bits = (low > np.median(low[1:].ravel() if low.size > 1 else low)).ravel()
    return int("".join("1" if b else "0" for b in bits), 2)


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def select_best(
    photos: list[Path],
    *,
    year: int | None = None,
    count: int = 30,
    dup_distance: int = 6,
    faces: bool = True,
) -> list[Path]:
    """Best `count` photos of `year` (default: the most common year), in date
    order. Score = sharpness (log) + a bonus for faces; near-duplicates (pHash
    distance <= dup_distance) keep only the best; picks are spread over months
    by taking the best of each month in turn."""
    dated = [(p, photo_date(p)) for p in photos]
    if year is None:
        year = Counter(d.year for _p, d in dated).most_common(1)[0][0]
    pool = [(p, d) for p, d in dated if d.year == year]
    scored = []
    for p, d in pool:
        img = load_photo(p, max_side=512)
        score = float(np.log1p(sharpness(img)))
        if faces and face_boxes(img):
            score += 2.0
        scored.append((score, p, d, phash(img)))
    scored.sort(key=lambda s: -s[0])
    kept: list[tuple[float, Path, object, int]] = []
    for item in scored:
        if all(hamming(item[3], k[3]) > dup_distance for k in kept):
            kept.append(item)
    by_month: dict[int, list] = defaultdict(list)
    for item in kept:
        by_month[item[2].month].append(item)  # already best-first
    chosen: list = []
    while len(chosen) < count and any(by_month.values()):
        for month in sorted(by_month):
            if by_month[month] and len(chosen) < count:
                chosen.append(by_month[month].pop(0))
    chosen.sort(key=lambda s: s[2])
    return [s[1] for s in chosen]


def make_yearreview(
    photos: list[Path],
    out: Path,
    *,
    year: int | None = None,
    count: int = 30,
    title: str | None = None,
    **reel_opts,
) -> Path:
    """Select the best photos of a year and render them with reel.make_reel.
    Captions default to each photo's date; extra options go to make_reel."""
    chosen = select_best(photos, year=year, count=count)
    if not chosen:
        raise ValueError("no photos found for that year")
    yr = photo_date(chosen[0]).year
    if "captions" not in reel_opts:
        reel_opts["captions"] = [
            photo_date(p).strftime("%B %d").replace(" 0", " ") for p in chosen
        ]
    return make_reel(
        chosen, out, title=title or f"{yr} in Review", **reel_opts
    )
