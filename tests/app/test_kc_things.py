import sqlite3

import numpy as np

from picasapy.app.kc_things import (QUERY_MIN_WINS, VOCABULARY, list_things, photos_with_thing, query_wins,
                                    update_things)
from picasapy.kc_smart.index import SmartIndex

# 3-d fake CLIP space: axis 0 = dog, axis 1 = car, axis 2 = everything else.
_AXES = {"dog": 0, "car": 1}


def _unit(axis: int, mix: float = 0.0) -> np.ndarray:
    v = np.full(3, mix)
    v[axis] = 1.0
    return v / np.linalg.norm(v)


class FakeEncoder:
    model_id = "fake"

    def encode_texts(self, prompts):
        out = []
        for p in prompts:
            axis = next((a for word, a in _AXES.items() if word in p), 2)
            out.append(_unit(axis))
        return np.array(out)


def _index(tmp_path, photos):
    index = SmartIndex(tmp_path, encoder=FakeEncoder())
    with sqlite3.connect(index.db_path) as conn:
        for path, vec in photos.items():
            conn.execute("INSERT INTO embeddings(path, mtime_ns, size, vec) VALUES (?, 1, 1, ?)",
                         (path, np.asarray(vec, dtype="<f2").tobytes()))
    return index


def test_tags_in_smart_db_only(tmp_path):
    index = _index(tmp_path, {"dog.jpg": _unit(0), "car.jpg": _unit(1)})
    assert update_things(index) > 0
    assert {t["tag"] for t in list_things(tmp_path)} >= {"dog", "car"}
    assert photos_with_thing(tmp_path, "dog")[0]["path"] == "dog.jpg"
    assert photos_with_thing(tmp_path, "not-in-vocabulary") == []
    assert not (tmp_path / ".picasa.ini").exists()
    assert len(VOCABULARY) >= 80


def test_ambiguous_photo_gets_no_tag(tmp_path):
    """A photo equally close to everything must not be tagged with a guess."""
    index = _index(tmp_path, {"blur.jpg": np.ones(3) / np.sqrt(3)})
    update_things(index)
    assert photos_with_thing(tmp_path, "dog") == []


def test_query_wins_only_where_the_query_beats_the_labels(tmp_path):
    index = _index(tmp_path, {f"dog{i}.jpg": _unit(0, 0.05) for i in range(5)})
    paths = [f"dog{i}.jpg" for i in range(5)]
    assert query_wins(index, "a dog", paths) >= QUERY_MIN_WINS  # "dog" label is a synonym, removed
    assert query_wins(index, "a cat", paths) < QUERY_MIN_WINS  # "dog" label beats "cat" on dog photos
    assert query_wins(index, "a dog", []) == 0
    assert query_wins(index, "a dog", ["missing.jpg"]) == 0
