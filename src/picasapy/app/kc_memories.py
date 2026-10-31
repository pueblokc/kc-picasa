"""Date memories from the local photo index."""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Slot


def on_this_day(index_path: str | Path, today: date) -> list[dict]:
    """Earlier years with today's month/day, newest first; read-only."""
    if not Path(index_path).exists():
        return []
    uri = Path(index_path).resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        rows = conn.execute(
            "SELECT p.id, f.path, p.name, COALESCE(p.taken_at_override, p.taken_at) "
            "FROM photos p JOIN folders f ON f.id=p.folder_id "
            "WHERE substr(COALESCE(p.taken_at_override, p.taken_at),6,5)=? "
            "AND substr(COALESCE(p.taken_at_override, p.taken_at),1,4) < ? "
            "ORDER BY COALESCE(p.taken_at_override, p.taken_at) DESC, p.id DESC",
            (today.strftime("%m-%d"), f"{today.year:04d}"),
        ).fetchall()
    return [{"id": photo_id, "year": int(taken[:4]), "yearsAgo": today.year - int(taken[:4]),
             "folder": folder, "path": str(Path(folder) / name), "url": QUrl.fromLocalFile(str(Path(folder) / name)).toString(),
             "name": name} for photo_id, folder, name, taken in rows]


class KcMemoriesController(QObject):
    def __init__(self, index_path: Path, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._index_path = index_path

    @Slot(result="QVariantList")
    def today(self) -> list[dict]:
        return on_this_day(self._index_path, date.today())
