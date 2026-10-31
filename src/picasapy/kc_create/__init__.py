"""KC Creative Projects engine: fun photo projects as pure functions.

Each module exposes `make_<project>(photos, out, **opts) -> Path`.
CLI: `python -m picasapy.kc_create <project> --out FILE photos...`
"""

PROJECTS = (
    "animate",
    "reel",
    "frames",
    "calendar",
    "photobook",
    "beforeafter",
    "mosaic",
    "yearreview",
)
