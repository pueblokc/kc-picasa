"""Build a small throwaway index.db (with the project's own schema code) for KC tests."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from PIL import Image

from picasapy.index.database import open_index

TODAY_MD = dt.date.today().strftime("%m-%d")
# (name, taken, star, caption, keywords, hidden)
PHOTOS = [
    ("beach_sunset.jpg", "2023-07-04T18:30:00", 1, "Sunset at the beach", "summer,sea", 0),
    ("birthday cake.jpg", "2023-12-25T12:00:00", 0, 'Grandma said "wow"', "family", 0),
    ("hike_peak.jpg", "2024-06-01T09:15:00", 1, "Peak hike", "mountain,summer", 0),
    ("old_town.jpg", f"2024-{TODAY_MD}T10:00:00", 0, None, "city", 0),
    ("today_then.jpg", f"2025-{TODAY_MD}T11:00:00", 0, "Same day, a year on", None, 0),
    ("café_août.jpg", "2025-08-15T15:00:00", 0, "Crème brûlée", "food", 0),
    ("secret.jpg", "2025-08-16T15:00:00", 0, "hidden beach", None, 1),
]


def build_index(data_dir: Path) -> dict[str, int]:
    """Create index.db + real JPEGs under data_dir/photos. Returns name -> photo id."""
    photos_dir = data_dir / "photos"
    photos_dir.mkdir(parents=True, exist_ok=True)
    ids: dict[str, int] = {}
    with open_index(data_dir / "index.db") as conn:
        conn.execute("INSERT INTO folders(path, date) VALUES (?, ?)", (str(photos_dir), "2024-01-01"))
        folder_id = conn.execute("SELECT id FROM folders").fetchone()[0]
        for name, taken, star, caption, keywords, hidden in PHOTOS:
            size = (200, 100)
            img = Image.new("RGB", size, (200, 120, 40))
            exif = Image.Exif()
            if name == "hike_peak.jpg":
                exif[0x0112] = 6  # stored 200x100, displayed 100x200
            img.save(photos_dir / name, "JPEG", exif=exif)
            cur = conn.execute(
                "INSERT INTO photos(folder_id, name, kind, size, mtime_ns, star, hidden,"
                " caption_ini, keywords_ini, taken_at, width, height)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (folder_id, name, "image", 1000, 1, star, hidden, caption, keywords, taken, *size),
            )
            ids[name] = cur.lastrowid
        conn.execute("INSERT INTO albums(folder_id, token, name, date) VALUES (?,?,?,?)",
                     (folder_id, "tok1", "Summer", "2024-06-01"))
        conn.execute("INSERT INTO photo_albums(photo_id, token) VALUES (?,?)",
                     (ids["hike_peak.jpg"], "tok1"))
        conn.execute(
            "INSERT INTO face(photo_id, rect_left, rect_top, rect_right, rect_bottom, det_conf,"
            " right_eye_x, right_eye_y, left_eye_x, left_eye_y, nose_x, nose_y,"
            " mouth_right_x, mouth_right_y, mouth_left_x, mouth_left_y, state, person_name)"
            " VALUES (?,0,0,1,1,1,0,0,0,0,0,0,0,0,0,0,'named','Alex')",
            (ids["birthday cake.jpg"],),
        )
        conn.commit()
    return ids
