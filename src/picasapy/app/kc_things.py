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


CLIP_LOGIT_SCALE = 100.0
# Calibrated on 375 real phone photos (2026-10-31). Raw CLIP cosine scores sit in a narrow
# 0.2-0.3 band for every photo, so a fixed cosine cut-off tags almost nothing (or noise).
# A softmax over the whole vocabulary asks the right question instead: which label fits
# THIS photo best? 0.3 tagged 66/375 photos with mostly-correct labels; 0.1 tagged noise.
TAG_MIN_PROB = 0.3
TAG_MAX_PER_PHOTO = 2
# Query confidence: the query must beat the vocabulary labels on its own top hits.
QUERY_WIN_PROB = 0.3
QUERY_MIN_WINS = 2
_SYNONYM_COS = 0.9


def _vocab_vectors(index: SmartIndex) -> np.ndarray:
    prompts = [f"a photo of {word.replace('_', ' ')}" for word in VOCABULARY]
    return np.asarray(index.encoder.encode_texts(prompts), dtype=np.float32)


def _softmax_rows(logits: np.ndarray) -> np.ndarray:
    z = np.exp(logits - logits.max(axis=-1, keepdims=True))
    return z / z.sum(axis=-1, keepdims=True)


def query_wins(index: SmartIndex, query: str, top_paths: list[str], *, top_k: int = 5) -> int:
    """How many of the top hits the query describes better than every everyday label.

    "a cat" on a library with no cats still has top hits, but on those photos "dog" or
    "toy" wins, so this returns 0-1 and the UI can say "no strong matches".
    """
    paths, matrix, rows = index._load_matrix()
    if not paths or not top_paths:
        return 0
    q = np.asarray(index.encoder.encode_texts([f"a photo of {query}"])[0], dtype=np.float32)
    vocab = _vocab_vectors(index)
    vocab = vocab[(vocab @ q) < _SYNONYM_COS]  # a label that IS the query must not compete with it
    wins = 0
    for path in top_paths[:top_k]:
        i = rows.get(path)
        if i is None:
            continue
        img = matrix[i]
        logits = CLIP_LOGIT_SCALE * np.concatenate([[img @ q], vocab @ img])
        if _softmax_rows(logits)[0] >= QUERY_WIN_PROB:
            wins += 1
    return wins


def update_things(index: SmartIndex, *, min_prob: float = TAG_MIN_PROB,
                  max_per_photo: int = TAG_MAX_PER_PHOTO) -> int:
    """Replace tags for indexed photos: each photo's best-fitting labels, weak guesses omitted."""
    paths, matrix, _ = index._load_matrix()
    if not paths:
        return 0
    probs = _softmax_rows(CLIP_LOGIT_SCALE * (matrix @ _vocab_vectors(index).T))
    records = []
    for i, path in enumerate(paths):
        for j in np.argsort(probs[i])[::-1][:max_per_photo]:
            if probs[i, j] >= min_prob:
                records.append((path, VOCABULARY[j], float(probs[i, j])))
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
