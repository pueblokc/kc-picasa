"""KC: HEIC / HEIF / AVIF support (needs the optional pillow-heif)."""

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("pillow_heif")

import cv2  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from picasapy import kc_heif  # noqa: E402
from picasapy.index.database import open_index  # noqa: E402
from picasapy.index.sync import sync_tree  # noqa: E402
from picasapy.scanner.filetypes import PHOTO_EXTENSIONS, media_kind_of  # noqa: E402
from picasapy.thumbs.cache import ThumbnailCache  # noqa: E402

TAKEN = "2021:05:06 07:08:09"
# Stored 80x40: left half blue, right half red. Orientation 6 (rotate 90 CW)
# makes it upright 40x80 with BLUE ON TOP.
STORED_SIZE = (80, 40)
UPRIGHT_SIZE = (40, 80)
FORMATS = ("heic", "avif")


def _make(path: Path) -> None:
    image = Image.new("RGB", STORED_SIZE, (200, 30, 30))
    image.paste((30, 30, 200), (0, 0, 40, 40))
    exif = Image.Exif()
    exif[0x0112] = 6
    exif.get_ifd(0x8769)[0x9003] = TAKEN
    image.save(path, exif=exif.tobytes(), quality=95)


@pytest.fixture()
def library(tmp_path):
    folder = tmp_path / "lib"
    folder.mkdir()
    for ext in FORMATS:
        _make(folder / f"phone.{ext}")
    return folder


def _index(folder, tmp_path):
    with open_index(tmp_path / "index.db") as conn:
        sync_tree(conn, folder)
        return {
            r["name"]: dict(r)
            for r in conn.execute(
                "SELECT p.*, COALESCE(p.taken_at_override, p.taken_at) AS date "
                "FROM photos p"
            )
        }


def _is_blue_over_red(bgr: np.ndarray) -> bool:
    height, width = bgr.shape[:2]
    top = bgr[height // 4, width // 2]
    bottom = bgr[3 * height // 4, width // 2]
    return top[0] > 150 and top[2] < 90 and bottom[2] > 150 and bottom[0] < 90


def test_extensions_listed_when_available():
    for ext in (".heic", ".heif", ".hif", ".avif"):
        assert ext in PHOTO_EXTENSIONS
        assert media_kind_of(f"x{ext}") == "photo"
    assert kc_heif.is_heif("a.HEIC") and not kc_heif.is_heif("a.jpg")


@pytest.mark.parametrize("ext", FORMATS)
def test_indexed_with_date_size_orientation(library, tmp_path, ext):
    row = _index(library, tmp_path)[f"phone.{ext}"]
    assert row["date"].startswith("2021-05-06T07:08:09") or row["date"].startswith(
        "2021-05-06 07:08:09"
    ), row["date"]
    # HEIC: pixels pre-rotated by pillow-heif (orientation reset to 1);
    # AVIF: stored size + EXIF orientation 6. Either way the *displayed*
    # shape is portrait.
    width, height = row["width"], row["height"]
    if ext == "heic":
        assert (width, height) == UPRIGHT_SIZE and row["orientation"] == 1
    else:
        assert (width, height) == STORED_SIZE and row["orientation"] == 6


@pytest.mark.parametrize("ext", FORMATS)
def test_thumbnail_upright(library, tmp_path, ext):
    path = library / f"phone.{ext}"
    stat = path.stat()
    cache = ThumbnailCache(tmp_path / "thumbs", size=64)
    thumb = cache.get_or_create(path, stat.st_mtime_ns, stat.st_size)
    assert thumb is not None
    bgr = cv2.imdecode(np.fromfile(thumb, np.uint8), cv2.IMREAD_COLOR)
    height, width = bgr.shape[:2]
    assert height > width, bgr.shape
    assert _is_blue_over_red(bgr)


@pytest.mark.parametrize("ext", FORMATS)
def test_decode_helpers(library, ext):
    path = library / f"phone.{ext}"
    qimage = kc_heif.decode_to_qimage(path, 40)
    assert not qimage.isNull()
    assert qimage.height() > qimage.width() and max(qimage.width(), qimage.height()) <= 40
    top = qimage.pixelColor(qimage.width() // 2, qimage.height() // 4)
    assert top.blue() > 150 and top.red() < 90
    assert kc_heif.decode_to_qimage(library / "missing.heic").isNull()


@pytest.mark.parametrize("ext", FORMATS)
def test_export_to_jpeg(library, tmp_path, ext):
    from picasapy.export.exporter import export_photos
    from picasapy.export.export_models import ExportItem
    from picasapy.export.export_settings import ExportSettings

    out = tmp_path / "out"
    report = export_photos([ExportItem(source=library / f"phone.{ext}")], out, ExportSettings())
    assert not report.failed, report.reasons
    assert len(report.exported) == 1
    exported = report.exported[0]
    assert exported.suffix.lower() in (".jpg", ".jpeg")
    with Image.open(exported) as result:
        assert result.format == "JPEG"
        assert result.size[1] > result.size[0]
    bgr = cv2.imdecode(np.fromfile(exported, np.uint8), cv2.IMREAD_COLOR)
    assert _is_blue_over_red(bgr)


def test_provider_viewer_url_and_pixels(library):
    from picasapy.app.display_photo_provider import DisplayPhotoProvider
    from urllib.parse import quote

    if not kc_heif.needs_helper(library / "phone.heic"):
        pytest.skip("this Qt build reads HEIC natively")
    image = DisplayPhotoProvider().requestImage(quote((library / "phone.heic").as_posix()), None, None)
    assert not image.isNull() and image.height() > image.width()


def test_without_pillow_heif_app_still_works(library, tmp_path):
    (library / "plain.jpg").parent.mkdir(exist_ok=True)
    Image.new("RGB", (10, 10), (1, 2, 3)).save(library / "plain.jpg")
    script = Path(__file__).with_name("_blocked_scan.py")
    result = subprocess.run(
        [sys.executable, str(script), str(library), str(tmp_path / "blocked.db")],
        capture_output=True,
        text=True,
        creationflags=0x08000000 if os.name == "nt" else 0,
    )
    assert result.returncode == 0, result.stderr
    lines = dict(line.split(" ", 1) for line in result.stdout.splitlines() if " " in line)
    assert lines["AVAILABLE"] == "False"
    assert lines["HEIC_KIND"] == "None"
    assert lines["HAS_HEIC_EXT"] == "False"
    assert lines["NAMES"] == "plain.jpg"


def test_quick_view_has_mime_types_for_new_extensions():
    # quick_view builds a mime table over PHOTO_EXTENSIONS at import; a missing
    # entry would crash app start-up.
    from picasapy.app.quick_view import IMAGE_MIME_TYPES_BY_EXTENSION

    assert IMAGE_MIME_TYPES_BY_EXTENSION[".heic"] == "image/heic"
    assert IMAGE_MIME_TYPES_BY_EXTENSION[".avif"] == "image/avif"
