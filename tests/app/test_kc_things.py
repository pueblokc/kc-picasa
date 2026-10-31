import sqlite3

import numpy as np

from picasapy.app.kc_things import VOCABULARY, list_things, photos_with_thing, update_things
from picasapy.kc_smart.index import SmartIndex


class FakeEncoder:
    model_id = "fake"

    def encode_texts(self, prompts):
        return np.array([[1.0, 0.0] if "dog" in p else [0.0, 1.0] for p in prompts])


def test_tags_in_smart_db_only(tmp_path):
    index = SmartIndex(tmp_path, encoder=FakeEncoder())
    with sqlite3.connect(index.db_path) as conn:
        conn.execute("INSERT INTO embeddings(path, mtime_ns, size, vec) VALUES (?, 1, 1, ?)",
                     ("dog.jpg", np.array([1.0, 0.0], dtype="<f2").tobytes()))
    assert update_things(index, threshold=0.5) > 0
    tags = list_things(tmp_path)
    assert {t["tag"] for t in tags} >= {"dog"}
    assert photos_with_thing(tmp_path, "dog")[0]["path"] == "dog.jpg"
    assert photos_with_thing(tmp_path, "not-in-vocabulary") == []
    assert not (tmp_path / ".picasa.ini").exists()
    assert len(VOCABULARY) >= 80
