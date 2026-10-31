"""KC Picasa: read-only queries over index.db, shared by the local API and the MCP server.

Standard library only (Pillow is imported lazily for thumbnails), so the MCP
server can use it without Qt. Every call opens its own read-only connection.
"""

from __future__ import annotations

import datetime as _dt
import os
import re
import sqlite3
from pathlib import Path

DB_NAME = "index.db"
MAX_LIMIT = 500
DEFAULT_LIMIT = 50

_TAKEN = "COALESCE(p.taken_at_override, p.taken_at)"
_CAPTION = "COALESCE(NULLIF(p.caption_file, ''), NULLIF(p.caption_ini, ''))"
_SELECT = (
    f"SELECT p.id, f.path AS folder, p.name, {_TAKEN} AS taken, p.star, "
    f"p.width, p.height, {_CAPTION} AS caption "
    "FROM photos p JOIN folders f ON f.id = p.folder_id "
)
_VISIBLE = "p.hidden = 0 AND f.hidden = 0"
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MD_RE = re.compile(r"^(\d{2})-(\d{2})$")
_WORD_RE = re.compile(r"\w+", re.UNICODE)


class QueryError(ValueError):
    """Bad caller input (maps to HTTP 400)."""


def db_path(data_dir: Path | str) -> Path:
    return Path(data_dir) / DB_NAME


def connect_ro(data_dir: Path | str, timeout: float = 2.0) -> sqlite3.Connection:
    """Open index.db read-only. Raises sqlite3.OperationalError if it is missing."""
    uri = db_path(data_dir).resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=timeout)
    conn.row_factory = sqlite3.Row
    return conn


def clamp_limit(value: object, default: int = DEFAULT_LIMIT) -> int:
    if value in (None, ""):
        return default
    try:
        n = int(value)  # type: ignore[call-overload]
    except (TypeError, ValueError):
        raise QueryError("limit must be an integer") from None
    return max(1, min(n, MAX_LIMIT))


def _photo(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "path": os.path.join(row["folder"], row["name"]),
        "name": row["name"],
        "taken": row["taken"],
        "star": row["star"],
        "width": row["width"],
        "height": row["height"],
        "caption": row["caption"],
    }


def _check_date(value: str, label: str = "date") -> str:
    if not _DATE_RE.match(value or ""):
        raise QueryError(f"{label} must be YYYY-MM-DD")
    try:
        _dt.date.fromisoformat(value)
    except ValueError:
        raise QueryError(f"{label} is not a real date") from None
    return value


def fts_query(q: str) -> str:
    """Turn free text into a safe FTS5 prefix query: every word quoted, ANDed."""
    words = _WORD_RE.findall(q or "")
    return " ".join('"' + w.replace('"', '""') + '"*' for w in words)


def search(conn: sqlite3.Connection, q: str, limit: object = None) -> list[dict]:
    match = fts_query(q)
    if not match:
        return []
    rows = conn.execute(
        _SELECT + "JOIN photos_fts ON photos_fts.rowid = p.id "
        f"WHERE photos_fts MATCH ? AND {_VISIBLE} "
        "ORDER BY photos_fts.rank, p.id LIMIT ?",
        (match, clamp_limit(limit)),
    ).fetchall()
    return [_photo(r) for r in rows]


def photos(
    conn: sqlite3.Connection,
    date: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    folder: str | None = None,
    starred: bool = False,
    limit: object = None,
) -> list[dict]:
    where = [_VISIBLE]
    args: list[object] = []
    day = f"substr({_TAKEN}, 1, 10)"
    if date:
        where.append(f"{day} = ?")
        args.append(_check_date(date))
    if date_from:
        where.append(f"{day} >= ?")
        args.append(_check_date(date_from, "from"))
    if date_to:
        where.append(f"{day} <= ?")
        args.append(_check_date(date_to, "to"))
    if folder:
        esc = folder.rstrip("/\\").replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        where.append("(f.path = ? OR f.path LIKE ? ESCAPE '\\' OR f.path LIKE ? ESCAPE '\\')")
        args += [folder.rstrip("/\\"), esc + "/%", esc + "\\\\%"]
    if starred:
        where.append("p.star = 1")
    rows = conn.execute(
        _SELECT + "WHERE " + " AND ".join(where) + f" ORDER BY {_TAKEN}, p.id LIMIT ?",
        (*args, clamp_limit(limit)),
    ).fetchall()
    return [_photo(r) for r in rows]


def on_this_day(conn: sqlite3.Connection, month_day: str | None = None, limit: object = None) -> dict:
    if not month_day:
        today = _dt.date.today()
        month_day = f"{today.month:02d}-{today.day:02d}"
    m = _MD_RE.match(month_day)
    if not m:
        raise QueryError("date must be MM-DD")
    try:
        _dt.date(2000, int(m.group(1)), int(m.group(2)))  # 2000 is a leap year
    except ValueError:
        raise QueryError("date is not a real month-day") from None
    rows = conn.execute(
        _SELECT + f"WHERE {_VISIBLE} AND substr({_TAKEN}, 6, 5) = ? "
        f"ORDER BY {_TAKEN} DESC, p.id LIMIT ?",
        (month_day, clamp_limit(limit, MAX_LIMIT)),
    ).fetchall()
    years: dict[str, list[dict]] = {}
    for r in rows:
        years.setdefault(r["taken"][:4], []).append(_photo(r))
    return {
        "date": month_day,
        "years": [{"year": int(y), "photos": ps} for y, ps in years.items()],
    }


def folders(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT f.id, f.path, f.date, COUNT(p.id) AS photos FROM folders f "
        "LEFT JOIN photos p ON p.folder_id = f.id AND p.hidden = 0 "
        "WHERE f.hidden = 0 GROUP BY f.id ORDER BY f.path"
    ).fetchall()
    return [dict(r) for r in rows]


def albums(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT a.token, MAX(a.name) AS name, MAX(a.date) AS date, "
        "MAX(a.description) AS description, "
        "(SELECT COUNT(*) FROM photo_albums pa WHERE pa.token = a.token) AS photos "
        "FROM albums a GROUP BY a.token ORDER BY name"
    ).fetchall()
    return [dict(r) for r in rows]


def people(conn: sqlite3.Connection) -> list[dict]:
    try:
        rows = conn.execute(
            "SELECT person_name AS name, COUNT(*) AS faces, "
            "COUNT(DISTINCT photo_id) AS photos FROM face "
            "WHERE person_name IS NOT NULL AND person_name <> '' "
            "GROUP BY person_name ORDER BY photos DESC, name"
        ).fetchall()
    except sqlite3.OperationalError:  # older index without the face table/columns
        return []
    return [dict(r) for r in rows]


def photo_detail(conn: sqlite3.Connection, photo_id: int) -> dict | None:
    row = conn.execute(
        "SELECT p.*, f.path AS folder FROM photos p JOIN folders f ON f.id = p.folder_id "
        "WHERE p.id = ?",
        (photo_id,),
    ).fetchone()
    if row is None:
        return None
    full = os.path.join(row["folder"], row["name"])
    keywords = ",".join(k for k in (row["keywords_file"], row["keywords_ini"]) if k)
    names = [
        r[0]
        for r in conn.execute(
            "SELECT COALESCE(a.name, pa.token) FROM photo_albums pa "
            "LEFT JOIN albums a ON a.token = pa.token AND a.folder_id = ? "
            "WHERE pa.photo_id = ? GROUP BY pa.token",
            (row["folder_id"], photo_id),
        )
    ]
    try:
        faces = [
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT person_name FROM face WHERE photo_id = ? "
                "AND person_name IS NOT NULL AND person_name <> ''",
                (photo_id,),
            )
        ]
    except sqlite3.OperationalError:
        faces = []
    return {
        "id": row["id"],
        "path": full,
        "folder": row["folder"],
        "name": row["name"],
        "kind": row["kind"],
        "size": row["size"],
        "taken": row["taken_at_override"] or row["taken_at"],
        "star": row["star"],
        "hidden": row["hidden"],
        "width": row["width"],
        "height": row["height"],
        "orientation": row["orientation"],
        "caption": row["caption_file"] or row["caption_ini"] or None,
        "keywords": [k.strip() for k in keywords.split(",") if k.strip()],
        "lat": row["exif_lat"],
        "lon": row["exif_lon"],
        "albums": names,
        "people": faces,
        "exists": os.path.isfile(full),
    }


def stats(conn: sqlite3.Connection) -> dict:
    def pairs(sql: str) -> dict:
        return {str(k): v for k, v in conn.execute(sql).fetchall()}

    base = f"FROM photos p JOIN folders f ON f.id = p.folder_id WHERE {_VISIBLE}"
    return {
        "photos": conn.execute(f"SELECT COUNT(*) {base}").fetchone()[0],
        "starred": conn.execute(f"SELECT COUNT(*) {base} AND p.star = 1").fetchone()[0],
        "by_year": pairs(
            f"SELECT COALESCE(substr({_TAKEN}, 1, 4), 'unknown'), COUNT(*) {base} "
            "GROUP BY 1 ORDER BY 1"
        ),
        "by_kind": pairs(f"SELECT p.kind, COUNT(*) {base} GROUP BY 1 ORDER BY 1"),
    }


def counts(conn: sqlite3.Connection) -> tuple[int, int]:
    return (
        conn.execute("SELECT COUNT(*) FROM photos").fetchone()[0],
        conn.execute("SELECT COUNT(*) FROM folders").fetchone()[0],
    )


def photo_path(conn: sqlite3.Connection, photo_id: int) -> str | None:
    row = conn.execute(
        "SELECT f.path, p.name FROM photos p JOIN folders f ON f.id = p.folder_id WHERE p.id = ?",
        (photo_id,),
    ).fetchone()
    return None if row is None else os.path.join(row[0], row[1])


def make_thumb(path: str, size: int = 256) -> bytes:
    """JPEG thumbnail, EXIF orientation honoured. Raises OSError if unreadable."""
    import io

    from PIL import Image, ImageOps

    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im)
        im.thumbnail((size, size))
        out = io.BytesIO()
        im.convert("RGB").save(out, "JPEG", quality=82)
        return out.getvalue()
