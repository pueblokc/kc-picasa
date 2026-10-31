"""Tests for the KC Creative Projects engine (small sizes, short durations)."""

from __future__ import annotations

import colorsys
import wave
from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image, ImageDraw

from picasapy.kc_create import _common
from picasapy.kc_create.animate import make_animation
from picasapy.kc_create.beforeafter import make_beforeafter
from picasapy.kc_create.calendar import make_calendar, us_holidays
from picasapy.kc_create.frames import make_frame
from picasapy.kc_create.mosaic import make_mosaic
from picasapy.kc_create.photobook import make_photobook
from picasapy.kc_create.reel import SIZES, make_reel
from picasapy.kc_create.yearreview import hamming, make_yearreview, phash, select_best

ROTATED = {0, 3, 6}  # stored landscape 240x160 + Orientation=6 -> shown 160x240


def _make_photo(path: Path, i: int) -> None:
    hue = i / 12
    r, g, b = (int(c * 255) for c in colorsys.hsv_to_rgb(hue, 0.6, 0.8))
    stored = (240, 160) if i in ROTATED else (200, 150)
    img = Image.new("RGB", stored, (r, g, b))
    d = ImageDraw.Draw(img)
    for k in range(6):
        d.ellipse((10 + k * 25, 20 + (k % 3) * 30, 50 + k * 25, 60 + (k % 3) * 30),
                  fill=(255 - r, g, (b + 40 * k) % 255))  # fmt: skip
    d.rectangle((0, 0, 30, 30), fill=(255, 255, 255))  # white corner marks the top-left
    exif = Image.Exif()
    if i in ROTATED:
        exif[0x0112] = 6
    month = (i % 12) + 1
    stamp = f"2026:{month:02d}:{5 + i % 20:02d} 10:00:00"
    exif[306] = stamp
    exif.get_ifd(0x8769)[36867] = stamp
    img.save(path, "JPEG", quality=92, exif=exif)


@pytest.fixture(scope="module")
def photos(tmp_path_factory) -> list[Path]:
    folder = tmp_path_factory.mktemp("kc_photos")
    paths = []
    for i in range(12):
        p = folder / f"p{i:02d}.jpg"
        _make_photo(p, i)
        paths.append(p)
    return paths


@pytest.fixture(scope="module")
def music(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("kc_audio") / "tone.wav"
    t = np.arange(44100 * 2) / 44100
    data = (np.sin(2 * np.pi * 440 * t) * 12000).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(44100)
        w.writeframes(data.tobytes())
    return path


def _frame_count(path: Path) -> int:
    cap = cv2.VideoCapture(str(path))
    n = 0
    while cap.read()[0]:
        n += 1
    cap.release()
    return n


# ----------------------------------------------------------------- common


def test_orientation_honoured_on_load(photos):
    assert Image.open(photos[0]).size == (240, 160)  # stored landscape
    assert _common.load_photo(photos[0]).size == (160, 240)  # shown portrait
    assert _common.load_photo(photos[1]).size == (200, 150)


def test_photo_date(photos):
    assert _common.photo_date(photos[2]).month == 3


# ---------------------------------------------------------------- animate


def test_gif_boomerang_and_orientation(photos, tmp_path):
    out = make_animation(photos[:4], tmp_path / "a.gif", fps=10, width=80, boomerang=True)
    with Image.open(out) as im:
        assert im.format == "GIF"
        assert im.n_frames == 6  # 4 forward + 2 back
        assert im.size == (80, 120)  # first photo is rotated -> portrait
        assert im.info["duration"] == 100


def test_gif_size_target(photos, tmp_path):
    big = make_animation(photos[:6], tmp_path / "big.gif", width=240)
    small = make_animation(photos[:6], tmp_path / "small.gif", width=240,
                           max_bytes=big.stat().st_size // 2)  # fmt: skip
    assert small.stat().st_size < big.stat().st_size


def test_webp_and_mp4(photos, tmp_path):
    webp = make_animation(photos[1:4], tmp_path / "a.webp", width=64)
    with Image.open(webp) as im:
        assert im.format == "WEBP" and im.n_frames == 3
    mp4 = make_animation(photos[1:4], tmp_path / "a.mp4", fps=5, width=64, loops=2)
    info = _common.probe(mp4)
    assert (info["width"], info["height"]) == (64, 48)
    assert _frame_count(mp4) == 6


def test_stabilise_recovers_shift(tmp_path):
    rng = np.random.default_rng(0)
    base = cv2.GaussianBlur((rng.random((120, 160)) * 255).astype(np.uint8), (0, 0), 3)
    base = cv2.cvtColor(cv2.normalize(base, None, 0, 255, cv2.NORM_MINMAX), cv2.COLOR_GRAY2RGB)
    shifted = np.roll(base, (4, 6), axis=(0, 1))
    from picasapy.kc_create.animate import _stabilise

    a, b = _stabilise([Image.fromarray(base), Image.fromarray(shifted)])
    inner = (slice(15, 105), slice(15, 145))
    err_before = np.abs(base[inner].astype(int) - shifted[inner].astype(int)).mean()
    err_after = np.abs(base[inner].astype(int) - np.asarray(b)[inner].astype(int)).mean()
    assert err_after < err_before / 2


# ------------------------------------------------------------------ reel


@pytest.mark.parametrize("size", ["9:16", "4:5", "16:9"])
def test_reel_sizes(photos, tmp_path, size):
    out = make_reel(photos[:3], tmp_path / "r.mp4", size=size, scale=0.1,
                    seconds_per_photo=1.0, crossfade=0.4, fps=10)  # fmt: skip
    info = _common.probe(out)
    w, h = SIZES[size]
    assert (info["width"], info["height"]) == (round(w * 0.1 / 2) * 2, round(h * 0.1 / 2) * 2)
    assert info["codec"] == "h264" and info["pix_fmt"].startswith("yuv420p")
    assert not info["has_audio"]
    assert info["duration"] == pytest.approx(3 * 1.0 - 2 * 0.4, abs=0.15)


def test_reel_title_captions_music_all_sizes(photos, tmp_path, music):
    out = make_reel(photos[:2], tmp_path / "full.mp4", scale=0.1, seconds_per_photo=1.0,
                    crossfade=0.3, fps=10, title="Hello", captions=["one", "two"],
                    music=music, all_sizes=True)  # fmt: skip
    for tag in ("9x16", "4x5", "16x9"):
        f = tmp_path / f"full_{tag}.mp4"
        assert f.exists()
        info = _common.probe(f)
        assert info["has_audio"] and info["audio_codec"] == "aac"
        # title (2.0s) + 2 photos (1.0s) - 2 crossfades (0.3s)
        assert info["duration"] == pytest.approx(2.0 + 1.0 + 1.0 - 0.6, abs=0.2)
    assert out.name == "full_9x16.mp4"


def test_reel_never_letterboxed(photos, tmp_path):
    """A landscape photo in a 9:16 reel: frames must fill the frame edge to edge."""
    out = make_reel([photos[1]], tmp_path / "lb.mp4", scale=0.1, seconds_per_photo=1.0,
                    fps=10, kenburns=False, ground="#000000")  # fmt: skip
    cap = cv2.VideoCapture(str(out))
    ok, frame = cap.read()
    cap.release()
    assert ok
    assert frame.mean(axis=2).min(axis=None) >= 0  # decodes
    assert frame[:4].mean() > 25 and frame[-4:].mean() > 25  # no black bars
    assert frame[:, :4].mean() > 25 and frame[:, -4:].mean() > 25


# ---------------------------------------------------------------- frames


@pytest.mark.parametrize("style", ["polaroid", "card", "matte", "postcard"])
def test_frames_single(photos, tmp_path, style):
    out = make_frame([photos[1]], tmp_path / f"{style}.png", style=style,
                     caption="Summer 2026", location="Pueblo, CO", size=300)  # fmt: skip
    with Image.open(out) as im:
        assert im.format == "PNG" and im.width > 300 and im.height > 200
        assert im.getpixel((2, 2)) == _common.rgb(_common.GROUND)  # dark ground


def test_frames_orientation_and_jpeg(photos, tmp_path):
    out = make_frame([photos[0]], tmp_path / "c.jpg", style="card", size=300)
    with Image.open(out) as im:
        assert im.format == "JPEG"
        assert im.height > im.width  # rotated photo stays portrait


def test_filmstrip(photos, tmp_path):
    out = make_frame(photos[1:5], tmp_path / "strip.png", style="filmstrip", size=300)
    with Image.open(out) as im:
        assert im.width > im.height * 2
    with pytest.raises(ValueError):
        make_frame(photos[:2], tmp_path / "x.png", style="filmstrip")


def test_custom_colours(photos, tmp_path):
    out = make_frame([photos[1]], tmp_path / "c.png", style="card", size=200, ground="#203040")
    with Image.open(out) as im:
        assert im.getpixel((1, 1)) == (0x20, 0x30, 0x40)


# -------------------------------------------------------------- calendar


def test_holidays():
    h = us_holidays(2026)
    import datetime as dt

    assert dt.date(2026, 11, 26) in h  # Thanksgiving
    assert dt.date(2026, 5, 25) in h  # Memorial Day
    assert dt.date(2026, 1, 19) in h  # MLK


def test_calendar_pdf(photos, tmp_path):
    out = make_calendar(photos, tmp_path / "cal.pdf", year=2027, start_month=7, dpi=40)
    data = out.read_bytes()
    assert data.startswith(b"%PDF")
    assert len(_pdf_pages(out)) == 12
    assert _media_boxes(out) == {(612.0, 792.0)}  # Letter: 8.5x11in
    from picasapy.kc_create.calendar import _page

    page = _page(_common.load_photo(photos[0], 400), None, 2027, 2, (340, 440), us_holidays(2027),
                 6, (15, 20, 23), (207, 201, 187), (77, 143, 133))  # fmt: skip
    assert page.size == (340, 440)


def test_calendar_page_count_via_cv(photos, tmp_path):
    out = make_calendar(photos[:3], tmp_path / "cal.pdf", year=2026, dpi=30)
    assert out.exists() and out.stat().st_size > 5000
    assert len(_pdf_pages(out)) == 12


def _media_boxes(path: Path) -> set[tuple[float, float]]:
    import re

    boxes = re.findall(rb"/MediaBox\s*\[\s*0\s+0\s+([\d.]+)\s+([\d.]+)", path.read_bytes())
    return {(float(w), float(h)) for w, h in boxes}


def _pdf_pages(path: Path) -> list[bytes]:
    import re

    return re.findall(rb"/Type\s*/Page(?![s\w])", path.read_bytes())


# ------------------------------------------------------------- photobook


def test_photobook(photos, tmp_path):
    out = make_photobook(photos, tmp_path / "book.pdf", title="Test Book", dpi=40,
                         date_captions=True)  # fmt: skip
    # cover + auto layout 1,2,3,4,1,1 = 12 photos -> 6 pages + cover
    assert len(_pdf_pages(out)) == 7
    assert _media_boxes(out) == {(612.0, 792.0)}


def test_photobook_fixed_layout(photos, tmp_path):
    out = make_photobook(photos[:8], tmp_path / "b4.pdf", per_page=4, dpi=30, cover_page=False)
    assert len(_pdf_pages(out)) == 2


# ----------------------------------------------------------- beforeafter


def test_beforeafter_swipe(photos, tmp_path):
    out = make_beforeafter([photos[1], photos[2]], tmp_path / "ba.mp4", width=128,
                           seconds=1.0, fps=10)  # fmt: skip
    info = _common.probe(out)
    assert (info["width"], info["height"]) == (128, 96)
    assert _frame_count(out) == 10
    cap = cv2.VideoCapture(str(out))
    frames = [cap.read()[1] for _ in range(6)]
    cap.release()
    assert np.abs(frames[0].astype(int) - frames[5].astype(int)).mean() > 5  # the wipe moves


def test_beforeafter_side_single_photo(photos, tmp_path):
    out = make_beforeafter([photos[0]], tmp_path / "side.mp4", mode="side", width=160,
                           seconds=0.5, fps=10)  # fmt: skip
    info = _common.probe(out)
    # each of the two panels (~78 px wide) keeps the rotated photo's portrait shape
    assert info["width"] == 160 and info["height"] > 78


# ---------------------------------------------------------------- mosaic


def test_mosaic(photos, tmp_path):
    out = make_mosaic(photos, tmp_path / "m.png", cols=16, tile=8, no_repeat=1)
    with Image.open(out) as im:
        # target is photos[0] (rotated -> portrait 2:3): 16 cols x 24 rows
        assert im.size == (16 * 8, 24 * 8)
    tgt = _common.load_photo(photos[0]).resize((16, 24), Image.BOX)
    got = Image.open(out).resize((16, 24), Image.BOX)
    diff = np.abs(np.asarray(tgt).astype(int) - np.asarray(got).astype(int)).mean()
    assert diff < 40  # colour-matched


def test_mosaic_no_neighbour_repeat(photos, tmp_path, monkeypatch):
    # many tiles available (11 photos x 5 variants) so radius 1 should be satisfiable
    import picasapy.kc_create.mosaic as mod

    seen = {}
    orig = np.argmin

    def spy(a, *args, **kw):
        k = orig(a, *args, **kw)
        seen.setdefault("n", 0)
        seen["n"] += 1
        return k

    monkeypatch.setattr(mod.np, "argmin", spy)
    make_mosaic(photos, tmp_path / "m2.png", cols=10, tile=6, no_repeat=1)
    assert seen["n"] >= 10 * 15


# ------------------------------------------------------------ yearreview


def test_phash_dedup():
    a = Image.new("RGB", (64, 64), (200, 30, 30))
    ImageDraw.Draw(a).rectangle((10, 10, 40, 40), fill=(20, 20, 200))
    b = a.copy()
    c = Image.new("RGB", (64, 64), (30, 200, 30))
    ImageDraw.Draw(c).ellipse((5, 30, 60, 60), fill=(250, 250, 0))
    assert hamming(phash(a), phash(b)) == 0
    assert hamming(phash(a), phash(c)) > 6


def test_select_best_spread_and_dedup(photos, tmp_path):
    dup = tmp_path / "dup.jpg"
    dup.write_bytes(photos[1].read_bytes())  # exact duplicate of p01
    chosen = select_best(photos + [dup], year=2026, count=8)
    assert len(chosen) == 8
    assert not ({photos[1], dup} <= set(chosen))  # one of the pair dropped
    months = {_common.photo_date(p).month for p in chosen}
    assert len(months) >= 7  # spread across months


def test_yearreview(photos, tmp_path):
    out = make_yearreview(photos, tmp_path / "yr.mp4", count=4, scale=0.1,
                          seconds_per_photo=0.8, crossfade=0.2, fps=10)  # fmt: skip
    info = _common.probe(out)
    assert info["codec"] == "h264"
    assert info["duration"] > 2.5
