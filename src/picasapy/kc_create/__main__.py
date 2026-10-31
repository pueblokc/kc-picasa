"""CLI: python -m picasapy.kc_create <project> --out FILE photos..."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from ._common import ACCENT, GROUND, TEXT, expand_photos


def _parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="python -m picasapy.kc_create")
    sub = root.add_subparsers(dest="project", required=True)

    def add(name: str, help_: str) -> argparse.ArgumentParser:
        p = sub.add_parser(name, help=help_)
        p.add_argument("photos", nargs="+", help="photo files or folders")
        p.add_argument("--out", required=True, type=Path)
        p.add_argument("--ground", default=GROUND)
        p.add_argument("--text", default=TEXT)
        p.add_argument("--accent", default=ACCENT)
        return p

    p = add("animate", "animated GIF / WebP / MP4 loop (by --out suffix)")
    p.add_argument("--fps", type=float, default=8)
    p.add_argument("--width", type=int, default=480)
    p.add_argument("--boomerang", action="store_true")
    p.add_argument("--stabilize", action="store_true")
    p.add_argument("--max-kb", type=int, help="size target for GIF/WebP")

    p = add("reel", "Ken Burns photo video")
    p.add_argument("--size", default="9:16", choices=["9:16", "4:5", "16:9"])
    p.add_argument("--all-sizes", action="store_true")
    p.add_argument("--scale", type=float, default=1.0)
    p.add_argument("--seconds", type=float, default=3.0)
    p.add_argument("--crossfade", type=float, default=0.6)
    p.add_argument("--title")
    p.add_argument("--subtitle")
    p.add_argument("--caption", action="append", help="repeat once per photo")
    p.add_argument("--music", type=Path)

    p = add("frames", "polaroid / filmstrip / card / matte / postcard")
    p.set_defaults(ground="#1c2328")
    p.add_argument("--classic", action="store_true", help="cream paper and dark ink")
    p.add_argument("--style", default="polaroid",
                   choices=["polaroid", "filmstrip", "card", "matte", "postcard"])  # fmt: skip
    p.add_argument("--caption")
    p.add_argument("--date")
    p.add_argument("--location")
    p.add_argument("--size", type=int, default=1200)

    p = add("calendar", "12-month Letter PDF calendar")
    p.add_argument("--year", type=int)
    p.add_argument("--start-month", type=int, default=1)
    p.add_argument("--no-holidays", action="store_true")
    p.add_argument("--dpi", type=int, default=150)

    p = add("photobook", "album PDF")
    p.add_argument("--title", default="Photo Album")
    p.add_argument("--subtitle")
    p.add_argument("--per-page", type=int, choices=[1, 2, 3, 4])
    p.add_argument("--date-captions", action="store_true")
    p.add_argument("--dpi", type=int, default=150)

    p = add("beforeafter", "before/after swipe or side-by-side MP4")
    p.add_argument("--mode", default="swipe", choices=["swipe", "side"])
    p.add_argument("--seconds", type=float, default=4.0)
    p.add_argument("--width", type=int, default=1080)

    p = add("mosaic", "photo mosaic (first photo = target unless --target)")
    p.add_argument("--target", type=Path)
    p.add_argument("--cols", type=int, default=48)
    p.add_argument("--tile", type=int, default=32)
    p.add_argument("--no-repeat", type=int, default=2)

    p = add("yearreview", "best photos of a year as a reel")
    p.add_argument("--year", type=int)
    p.add_argument("--count", type=int, default=30)
    p.add_argument("--size", default="9:16", choices=["9:16", "4:5", "16:9"])
    p.add_argument("--all-sizes", action="store_true")
    p.add_argument("--scale", type=float, default=1.0)
    p.add_argument("--music", type=Path)
    return root


def main(argv: list[str] | None = None) -> int:
    a = _parser().parse_args(argv)
    photos = expand_photos(a.photos)
    colours = {"ground": a.ground, "text": a.text, "accent": a.accent}
    started = time.perf_counter()
    if a.project == "animate":
        from .animate import make_animation

        res = make_animation(photos, a.out, fps=a.fps, width=a.width, boomerang=a.boomerang,
                             stabilize=a.stabilize, max_bytes=a.max_kb * 1024 if a.max_kb else None)  # fmt: skip
    elif a.project == "reel":
        from .reel import make_reel

        res = make_reel(photos, a.out, size=a.size, all_sizes=a.all_sizes, scale=a.scale,
                        seconds_per_photo=a.seconds, crossfade=a.crossfade, title=a.title,
                        subtitle=a.subtitle, captions=a.caption, music=a.music, **colours)  # fmt: skip
    elif a.project == "frames":
        from .frames import make_frame

        res = make_frame(photos, a.out, style=a.style, caption=a.caption, date=a.date,
                         location=a.location, size=a.size, classic=a.classic, **colours)  # fmt: skip
    elif a.project == "calendar":
        from .calendar import make_calendar

        res = make_calendar(photos, a.out, year=a.year, start_month=a.start_month,
                            holidays=not a.no_holidays, dpi=a.dpi, **colours)  # fmt: skip
    elif a.project == "photobook":
        from .photobook import make_photobook

        res = make_photobook(photos, a.out, title=a.title, subtitle=a.subtitle,
                             per_page=a.per_page, date_captions=a.date_captions, dpi=a.dpi, **colours)  # fmt: skip
    elif a.project == "beforeafter":
        from .beforeafter import make_beforeafter

        res = make_beforeafter(photos, a.out, mode=a.mode, seconds=a.seconds, width=a.width, **colours)
    elif a.project == "mosaic":
        from .mosaic import make_mosaic

        res = make_mosaic(photos, a.out, target=a.target, cols=a.cols, tile=a.tile, no_repeat=a.no_repeat)
    else:
        from .yearreview import make_yearreview

        res = make_yearreview(photos, a.out, year=a.year, count=a.count, size=a.size,
                              all_sizes=a.all_sizes, scale=a.scale, music=a.music, **colours)  # fmt: skip
    print(f"wrote {res} ({time.perf_counter() - started:.1f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
