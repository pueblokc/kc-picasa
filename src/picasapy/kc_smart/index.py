"""SmartIndex: CLIP embeddings for the photo library, in their own SQLite file.

* Embeddings live in `<data_dir>/kc-smart/embeddings.db`. The app's
  `index.db` is only ever opened read-only (`file:...?mode=ro`).
* A row is keyed by the full photo path and remembers the `mtime_ns` and
  `size` it was computed from (taken from index.db), so a changed photo is
  re-embedded and a deleted one is dropped.
* `update()` commits after every batch, so a stopped run resumes where it
  left off. Photos that fail to decode are remembered (same key) and not
  retried until the file changes.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from collections.abc import Callable
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from .model import Encoder

# progress_cb(done, total)
UpdateProgress = Callable[[int, int], None]

# module-level handles so tests can swap them without touching the globals
_connect_db = sqlite3.connect
_sleep = time.sleep

# Cosine score below which a text match is noise for CLIP ViT-B/32.
# Typical text<->image scores: unrelated ~0.15, good match ~0.25-0.35.
DEFAULT_MIN_SCORE = 0.2
DECODE_SIZE = 448  # decode at most this size (CLIP looks at 224 px)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS embeddings (
    path TEXT PRIMARY KEY,
    mtime_ns INTEGER NOT NULL,
    size INTEGER NOT NULL,
    vec BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS failures (
    path TEXT PRIMARY KEY,
    mtime_ns INTEGER NOT NULL,
    size INTEGER NOT NULL,
    error TEXT NOT NULL
);
"""

_PHOTOS_SQL = """
SELECT f.path AS folder, p.name AS name, p.mtime_ns AS mtime_ns, p.size AS size,
       f.offline AS offline
FROM photos p JOIN folders f ON f.id = p.folder_id
WHERE p.kind != 'video'
"""


def load_image(path: str | Path, max_side: int = DECODE_SIZE) -> Image.Image:
    """Decode a photo at thumbnail size, EXIF orientation applied, RGB."""
    with Image.open(path) as im:
        im.draft("RGB", (max_side, max_side))  # JPEG: decode at 1/2..1/8 scale
        im = ImageOps.exif_transpose(im)
        im = im.convert("RGB")
        im.thumbnail((max_side, max_side), Image.Resampling.BILINEAR)
        return im


class SmartIndex:
    def __init__(
        self,
        data_dir: str | Path,
        encoder: Encoder | None = None,
        *,
        batch_size: int = 16,
        sleep_s: float = 0.05,
        min_score: float = DEFAULT_MIN_SCORE,
        image_loader: Callable[[str], Image.Image] = load_image,
    ):
        self.data_dir = Path(data_dir)
        self.index_db = self.data_dir / "index.db"
        self.db_path = self.data_dir / "kc-smart" / "embeddings.db"
        self._encoder = encoder
        self.batch_size = batch_size
        self.sleep_s = sleep_s
        self.min_score = min_score
        self.image_loader = image_loader
        self._cache_lock = threading.Lock()
        self._paths: list[str] | None = None
        self._matrix: np.ndarray | None = None
        self._row: dict[str, int] = {}
        self._init_db()

    # -- plumbing -------------------------------------------------------

    @property
    def encoder(self) -> Encoder:
        if self._encoder is None:
            from .model import ClipEncoder

            self._encoder = ClipEncoder(self.data_dir)
        return self._encoder

    def _connect(self) -> sqlite3.Connection:
        conn = _connect_db(self.db_path, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
        conn.close()

    def _check_model(self, conn: sqlite3.Connection) -> None:
        """Vectors from another model are useless: drop them on a switch."""
        row = conn.execute("SELECT value FROM meta WHERE key='model_id'").fetchone()
        model_id = self.encoder.model_id
        if row and row[0] == model_id:
            return
        conn.execute("DELETE FROM embeddings")
        conn.execute("DELETE FROM failures")
        conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES ('model_id', ?)", (model_id,)
        )
        conn.commit()
        self._invalidate()

    def library(self) -> dict[str, tuple[int, int, bool]]:
        """{path: (mtime_ns, size, offline)} for every still photo in index.db,
        read through a read-only connection."""
        if not self.index_db.is_file():
            return {}
        uri = self.index_db.resolve().as_uri() + "?mode=ro"
        conn = _connect_db(uri, uri=True, timeout=10)
        try:
            rows = conn.execute(_PHOTOS_SQL).fetchall()
        finally:
            conn.close()
        return {
            str(Path(folder) / name): (int(mtime), int(size), bool(offline))
            for folder, name, mtime, size, offline in rows
        }

    def _invalidate(self) -> None:
        with self._cache_lock:
            self._paths = None
            self._matrix = None
            self._row = {}

    def _load_matrix(self) -> tuple[list[str], np.ndarray, dict[str, int]]:
        with self._cache_lock:
            if self._matrix is None:
                conn = self._connect()
                try:
                    rows = conn.execute("SELECT path, vec FROM embeddings ORDER BY path").fetchall()
                finally:
                    conn.close()
                paths = [r[0] for r in rows]
                if rows:
                    mat = np.frombuffer(b"".join(r[1] for r in rows), dtype="<f2")
                    mat = mat.reshape(len(rows), -1).astype(np.float32)
                else:
                    mat = np.zeros((0, 0), dtype=np.float32)
                self._paths, self._matrix = paths, mat
                self._row = {p: i for i, p in enumerate(paths)}
            assert self._paths is not None
            return self._paths, self._matrix, self._row

    # -- update ---------------------------------------------------------

    def update(
        self,
        progress_cb: UpdateProgress | None = None,
        stop_event: threading.Event | None = None,
    ) -> dict[str, int]:
        """Embed new and changed photos, drop deleted ones.

        Returns counts: added, removed, failed, todo, stopped (0/1)."""
        stats = {"added": 0, "removed": 0, "failed": 0, "todo": 0, "stopped": 0}
        conn = self._connect()
        try:
            self._check_model(conn)
            wanted = self.library()
            have = {
                p: (m, s)
                for p, m, s in conn.execute("SELECT path, mtime_ns, size FROM embeddings")
            }
            failed = {
                p: (m, s) for p, m, s in conn.execute("SELECT path, mtime_ns, size FROM failures")
            }
            gone = [p for p in have.keys() | failed.keys() if p not in wanted]
            if gone:
                conn.executemany("DELETE FROM embeddings WHERE path=?", [(p,) for p in gone])
                conn.executemany("DELETE FROM failures WHERE path=?", [(p,) for p in gone])
                conn.commit()
                stats["removed"] = sum(1 for p in gone if p in have)
                self._invalidate()
            todo = sorted(
                p
                for p, (m, s, offline) in wanted.items()
                if not offline and have.get(p) != (m, s) and failed.get(p) != (m, s)
            )
            stats["todo"] = len(todo)
            if progress_cb:
                progress_cb(0, len(todo))
            done = 0
            for start in range(0, len(todo), self.batch_size):
                if stop_event is not None and stop_event.is_set():
                    stats["stopped"] = 1
                    break
                batch = todo[start : start + self.batch_size]
                images, ok, bad = [], [], []
                for p in batch:
                    try:
                        images.append(self.image_loader(p))
                        ok.append(p)
                    except Exception as exc:  # noqa: BLE001 - any bad file is skipped
                        bad.append((p, f"{type(exc).__name__}: {exc}"[:300]))
                vecs = self.encoder.encode_images(images) if images else []
                conn.executemany(
                    "INSERT OR REPLACE INTO embeddings(path, mtime_ns, size, vec) "
                    "VALUES (?, ?, ?, ?)",
                    [
                        (p, *wanted[p][:2], np.asarray(v, dtype="<f2").tobytes())
                        for p, v in zip(ok, vecs, strict=True)
                    ],
                )
                conn.executemany("DELETE FROM failures WHERE path=?", [(p,) for p in ok])
                conn.executemany(
                    "INSERT OR REPLACE INTO failures(path, mtime_ns, size, error) "
                    "VALUES (?, ?, ?, ?)",
                    [(p, *wanted[p][:2], err) for p, err in bad],
                )
                conn.commit()
                stats["added"] += len(ok)
                stats["failed"] += len(bad)
                done += len(batch)
                self._invalidate()
                if progress_cb:
                    progress_cb(done, len(todo))
                if self.sleep_s > 0 and done < len(todo):
                    if stop_event is not None:
                        stop_event.wait(self.sleep_s)
                    else:
                        _sleep(self.sleep_s)
        finally:
            conn.close()
        return stats

    # -- queries --------------------------------------------------------

    def _rank(
        self, query: np.ndarray, limit: int, min_score: float | None, exclude: str | None = None
    ) -> list[tuple[str, float]]:
        paths, mat, row = self._load_matrix()
        if not paths:
            return []
        scores = mat @ np.asarray(query, dtype=np.float32).reshape(-1)
        if exclude is not None and exclude in row:
            scores[row[exclude]] = -np.inf
        threshold = self.min_score if min_score is None else min_score
        k = min(limit, len(paths))
        top = np.argpartition(-scores, k - 1)[:k]
        top = top[np.argsort(-scores[top], kind="stable")]
        return [(paths[i], float(scores[i])) for i in top if scores[i] >= threshold]

    def search(
        self, text: str, limit: int = 60, min_score: float | None = None
    ) -> list[tuple[str, float]]:
        """Photos matching a text query, best first: [(path, cosine score)]."""
        text = text.strip()
        if not text or limit <= 0:
            return []
        if not self._load_matrix()[0]:
            return []
        q = self.encoder.encode_texts([text])[0]
        return self._rank(q, limit, min_score)

    def vector(self, path: str | Path) -> np.ndarray | None:
        _paths, mat, row = self._load_matrix()
        i = row.get(str(path))
        return None if i is None else mat[i]

    def similar(
        self, path: str | Path, limit: int = 60, min_score: float | None = 0.0
    ) -> list[tuple[str, float]]:
        """Photos that look like `path` (itself excluded). Uses the stored
        vector, or embeds the file on the fly if it is not indexed."""
        path = str(path)
        vec = self.vector(path)
        if vec is None:
            vec = self.encoder.encode_images([self.image_loader(path)])[0]
        return self._rank(vec, limit, min_score, exclude=path)

    def status(self) -> dict[str, object]:
        conn = self._connect()
        try:
            n = conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
            nf = conn.execute("SELECT COUNT(*) FROM failures").fetchone()[0]
            row = conn.execute("SELECT value FROM meta WHERE key='model_id'").fetchone()
        finally:
            conn.close()
        lib = self.library()
        return {
            "embedded": n,
            "failed": nf,
            "library_photos": len(lib),
            "model_id": row[0] if row else None,
            "db_path": str(self.db_path),
        }
