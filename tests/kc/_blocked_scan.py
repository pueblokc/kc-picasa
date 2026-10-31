"""Run as a script: scans a folder with pillow_heif import blocked, prints names."""
import sys

sys.modules["pillow_heif"] = None  # makes `import pillow_heif` raise ImportError

from picasapy import kc_heif
from picasapy.index.database import open_index
from picasapy.index.sync import sync_tree
from picasapy.scanner.filetypes import PHOTO_EXTENSIONS, media_kind_of

folder, db = sys.argv[1], sys.argv[2]
with open_index(db) as conn:
    sync_tree(conn, folder)
    names = sorted(r["name"] for r in conn.execute("SELECT name FROM photos"))
print("AVAILABLE", kc_heif.AVAILABLE)
print("HEIC_KIND", media_kind_of("a.heic"))
print("HAS_HEIC_EXT", ".heic" in PHOTO_EXTENSIONS)
print("NAMES", ",".join(names))
