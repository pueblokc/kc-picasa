"""Zero-shot things catalog stored alongside KC photo embeddings."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np

from picasapy.kc_smart.index import SmartIndex

VOCABULARY = """dog cat person child baby family friend car truck bus train bicycle motorcycle airplane boat food pizza cake dessert drink coffee beach snow mountains sunset sunrise sky clouds trees forest flowers garden house building room kitchen bathroom bedroom screenshot document receipt sign computer phone television game toy christmas tree halloween birthday fireworks night city road river lake waterfall bird horse cow sheep fish butterfly insect plant grass desert ocean pool bridge tower church store restaurant wedding party graduation sports ball football baseball soccer concert music instrument book art painting sculpture clothes shoes hat pet portrait selfie landscape park trail campsite tent fire rain storm rainbow moon stars sun winter summer spring autumn""".split()

SCHEMA = """
CREATE TABLE IF NOT EXISTS thing_tags (
    path TEXT NOT NULL, tag TEXT NOT NULL, score REAL NOT NULL,
    PRIMARY KEY(path, tag)
);
CREATE INDEX IF NOT EXISTS thing_tags_tag ON thing_tags(tag);
"""


def update_things(index: SmartIndex, *, threshold: float = 0.27) -> int:
    """Replace tags for indexed photos; omit weak CLIP guesses."""
    paths, matrix, _ = index._load_matrix()
    if not paths:
        return 0
    prompts = [f"a photo of {word.replace('_', ' ')}" for word in VOCABULARY]
    text_vecs = np.asarray(index.encoder.encode_texts(prompts), dtype=np.float32)
    scores = matrix @ text_vecs.T
    records = [(path, VOCABULARY[j], float(score))
               for i, path in enumerate(paths)
               for j, score in enumerate(scores[i]) if score >= threshold]
    with sqlite3.connect(index.db_path) as conn:
        conn.executescript(SCHEMA)
        conn.execute("DELETE FROM thing_tags")
        conn.executemany("INSERT INTO thing_tags(path, tag, score) VALUES (?, ?, ?)", records)
    return len(records)


def list_things(data_dir: str | Path) -> list[dict]:
    db = Path(data_dir) / "kc-smart" / "embeddings.db"
    if not db.is_file():
        return []
    with sqlite3.connect(db.as_uri() + "?mode=ro", uri=True) as conn:
        try:
            rows = conn.execute("SELECT tag, COUNT(*) FROM thing_tags GROUP BY tag ORDER BY COUNT(*) DESC, tag").fetchall()
        except sqlite3.OperationalError:
            return []
    return [{"tag": tag, "count": count} for tag, count in rows]


def photos_with_thing(data_dir: str | Path, tag: str, limit: int = 100) -> list[dict]:
    if tag not in VOCABULARY:
        return []
    db = Path(data_dir) / "kc-smart" / "embeddings.db"
    if not db.is_file():
        return []
    with sqlite3.connect(db.as_uri() + "?mode=ro", uri=True) as conn:
        try:
            rows = conn.execute("SELECT path, score FROM thing_tags WHERE tag=? ORDER BY score DESC LIMIT ?", (tag, max(1, min(limit, 500)))).fetchall()
        except sqlite3.OperationalError:
            return []
    return [{"path": path, "score": score} for path, score in rows]
