"""KC Smart Search engine tests.

Fast tests use a fake colour encoder; the one `slow` test downloads the real
CLIP model (~155 MB, cached in the pytest cache dir) and checks the ranking.
"""

from __future__ import annotations

import hashlib
import http.server
import json
import os
import sqlite3
import threading
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from picasapy.index.database import open_index
from picasapy.kc_smart import index as kc_index
from picasapy.kc_smart import model as kc_model
from picasapy.kc_smart.index import SmartIndex
from picasapy.kc_smart.tokenizer import ClipTokenizer, pre_tokenize

# ---------------------------------------------------------------- helpers

COLOURS = {"red": (220, 20, 20), "green": (20, 200, 20), "blue": (20, 20, 220)}


class FakeEncoder:
    """Image -> its mean RGB; text -> the named colour. Counts work done."""

    model_id = "fake-rgb"
    dim = 3

    def __init__(self):
        self.images_seen = 0

    def encode_images(self, images):
        self.images_seen += len(images)
        vecs = np.array([np.asarray(im, dtype=np.float32).mean(axis=(0, 1)) for im in images])
        return vecs / np.linalg.norm(vecs, axis=1, keepdims=True)

    def encode_texts(self, texts):
        vecs = np.array([COLOURS[t.split()[-1]] for t in texts], dtype=np.float32)
        return vecs / np.linalg.norm(vecs, axis=1, keepdims=True)


class Library:
    """A real index.db (upstream schema) plus photo files on disk."""

    def __init__(self, root: Path):
        self.root = root
        self.photos = root / "photos"
        self.photos.mkdir(parents=True)
        self.db = root / "index.db"
        with open_index(self.db) as conn:
            conn.execute("INSERT INTO folders(path) VALUES (?)", (str(self.photos),))
            conn.commit()

    def add(
        self, name: str, colour, kind: str = "photo", raw: bytes | None = None,
        mtime_ns: int | None = None,
    ) -> str:
        path = self.photos / name
        if raw is not None:
            path.write_bytes(raw)
        elif colour is not None:
            Image.new("RGB", (64, 48), colour).save(path)
        if mtime_ns is not None:
            os.utime(path, ns=(mtime_ns, mtime_ns))
        st = path.stat()
        with open_index(self.db) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO photos(folder_id, name, kind, size, mtime_ns) "
                "VALUES (1, ?, ?, ?, ?)",
                (name, kind, st.st_size, st.st_mtime_ns),
            )
            conn.commit()
        return str(path)

    def remove(self, name: str) -> None:
        with open_index(self.db) as conn:
            conn.execute("DELETE FROM photos WHERE name=?", (name,))
            conn.commit()


@pytest.fixture
def lib(tmp_path):
    return Library(tmp_path)


def _names(hits):
    return [Path(p).name for p, _ in hits]


# ---------------------------------------------------------------- tokenizer


def test_pre_tokenize_follows_clip_pattern():
    assert pre_tokenize("don't stop, it's x_y 2024") == [
        "don", "'t", "stop", ",", "it", "'s", "x", "_", "y", "2", "0", "2", "4"
    ]
    assert pre_tokenize("?'s café") == ["?'", "s", "café"]


def test_bpe_with_tiny_vocab(tmp_path):
    vocab = {"<|startoftext|>": 0, "<|endoftext|>": 1, "c": 2, "a": 3, "t</w>": 4,
             "ca": 5, "cat</w>": 6, "s</w>": 7, "!</w>": 8}
    (tmp_path / "v.json").write_text(json.dumps(vocab), "utf-8")
    (tmp_path / "m.txt").write_text("#version: 0.2\nc a\nca t</w>\n", "utf-8")
    tok = ClipTokenizer(tmp_path / "v.json", tmp_path / "m.txt")
    assert tok.encode("CAT") == [0, 6, 1]
    assert tok.encode("cat !") == [0, 6, 8, 1]
    batch = tok.encode_batch(["cat", "cat !"])
    assert batch.tolist() == [[0, 6, 1, 1], [0, 6, 8, 1]]
    assert len(tok.encode("cat " * 200)) == 77


# Reference ids from the Hugging Face `tokenizers` library loading
# Xenova/clip-vit-base-patch32 tokenizer.json at the pinned revision.
CLIP_REFERENCE = {
    "a photo of a cat": [49406, 320, 1125, 539, 320, 2368, 49407],
    "dog on the beach": [49406, 1929, 525, 518, 2117, 49407],
    "Birthday CAKE!!": [49406, 1166, 2972, 748, 49407],
    "snow in the backyard": [49406, 2583, 530, 518, 12608, 49407],
    "don't stop, it's 2024 x_y": [
        49406, 847, 713, 1691, 267, 585, 568, 273, 271, 273, 275, 343, 318, 344, 49407
    ],
    "café naïve ½ ²": [49406, 15304, 1097, 35689, 563, 33613, 41175, 49407],
    "  hello   world  ": [49406, 3306, 1002, 49407],
    "?'s <b>&amp;": [49406, 13610, 338, 283, 321, 29, 261, 6259, 282, 49407],
}


def _cache_dir(pytestconfig, tmp_path_factory, name: str) -> Path:
    cache = getattr(pytestconfig, "cache", None)
    return Path(cache.mkdir(name)) if cache else tmp_path_factory.mktemp(name)


@pytest.fixture(scope="session")
def clip_vocab_dir(pytestconfig, tmp_path_factory):
    """vocab.json + merges.txt (1.4 MB) fetched once into the pytest cache."""
    root = _cache_dir(pytestconfig, tmp_path_factory, "kc_smart_tok")
    spec = kc_model.DEFAULT_SPEC
    try:
        for f in (spec.vocab, spec.merges):
            url = f"{kc_model.DEFAULT_BASE_URL}/{spec.repo}/resolve/{spec.revision}/{f.name}"
            kc_model.download_file(url, root / Path(f.name).name, f.sha256, f.size)
    except kc_model.ModelDownloadError as exc:
        pytest.skip(f"no network for the CLIP vocab: {exc}")
    return root


@pytest.mark.parametrize("text", list(CLIP_REFERENCE))
def test_tokenizer_matches_clip_reference(clip_vocab_dir, text):
    tok = ClipTokenizer(clip_vocab_dir / "vocab.json", clip_vocab_dir / "merges.txt")
    assert tok.encode(text) == CLIP_REFERENCE[text]


# ---------------------------------------------------------------- download


class _RangeHandler(http.server.BaseHTTPRequestHandler):
    payload = b""
    requests: list[str | None] = []

    def do_GET(self):  # noqa: N802
        rng = self.headers.get("Range")
        type(self).requests.append(rng)
        start = int(rng.split("=")[1].split("-")[0]) if rng else 0
        body = self.payload[start:]
        self.send_response(206 if rng else 200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def range_server():
    payload = os.urandom(300_000)
    _RangeHandler.payload = payload
    _RangeHandler.requests = []
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _RangeHandler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_port}/f.bin", payload
    srv.shutdown()


def test_download_resumes_and_checks_sha(tmp_path, range_server):
    url, payload = range_server
    sha = hashlib.sha256(payload).hexdigest()
    dest = tmp_path / "m" / "f.bin"
    dest.parent.mkdir()
    (dest.parent / "f.bin.part").write_bytes(payload[:100_000])  # interrupted earlier
    seen = []
    kc_model.download_file(url, dest, sha, len(payload), lambda n, d, t: seen.append((d, t)))
    assert dest.read_bytes() == payload
    assert _RangeHandler.requests == ["bytes=100000-"]
    assert seen[-1] == (len(payload), len(payload))
    assert not (dest.parent / "f.bin.part").exists()


def test_download_rejects_bad_sha(tmp_path, range_server):
    url, payload = range_server
    dest = tmp_path / "f.bin"
    with pytest.raises(kc_model.ModelDownloadError, match="sha256"):
        kc_model.download_file(url, dest, "0" * 64, len(payload))
    assert not dest.exists() and not (tmp_path / "f.bin.part").exists()


def test_preprocess_shape_and_centre_crop():
    im = Image.new("RGB", (400, 200), (255, 255, 255))
    ImageDraw.Draw(im).rectangle((0, 0, 99, 199), fill=(0, 0, 0))  # left quarter black
    arr = kc_model.preprocess([im])
    assert arr.shape == (1, 3, 224, 224) and arr.dtype == np.float32
    # the black strip falls outside the centre crop
    assert arr[0, 0].min() > 1.5


# ---------------------------------------------------------------- index


def test_update_and_search(lib, tmp_path):
    for name, col in [("r.png", "red"), ("g.png", "green"), ("b.png", "blue")]:
        lib.add(name, COLOURS[col])
    enc = FakeEncoder()
    idx = SmartIndex(tmp_path, enc, sleep_s=0)
    progress = []
    stats = idx.update(lambda d, t: progress.append((d, t)))
    assert stats["added"] == 3 and stats["failed"] == 0
    assert progress[0] == (0, 3) and progress[-1] == (3, 3)
    assert (tmp_path / "kc-smart" / "embeddings.db").is_file()
    hits = idx.search("something blue", min_score=-1)
    assert _names(hits)[0] == "b.png" and hits[0][1] == pytest.approx(1.0, abs=1e-3)
    assert _names(idx.search("red", limit=1, min_score=-1)) == ["r.png"]
    assert len(idx.search("red", min_score=0.9)) == 1
    assert idx.search("   ") == []
    # nothing new: nothing re-embedded
    assert idx.update()["added"] == 0 and enc.images_seen == 3


def test_vectors_stored_as_float16(lib, tmp_path):
    lib.add("r.png", COLOURS["red"])
    SmartIndex(tmp_path, FakeEncoder(), sleep_s=0).update()
    conn = sqlite3.connect(tmp_path / "kc-smart" / "embeddings.db")
    (blob,) = conn.execute("SELECT vec FROM embeddings").fetchone()
    conn.close()
    assert len(blob) == 3 * 2


def test_changed_photo_is_reembedded(lib, tmp_path):
    lib.add("x.png", COLOURS["red"], mtime_ns=1_000_000_000_000_000_000)
    idx = SmartIndex(tmp_path, FakeEncoder(), sleep_s=0)
    idx.update()
    assert _names(idx.search("red", limit=1, min_score=0.9)) == ["x.png"]
    lib.add("x.png", COLOURS["blue"], mtime_ns=1_000_000_001_000_000_000)
    stats = idx.update()
    assert stats["added"] == 1
    assert idx.search("red", min_score=0.9) == []
    assert _names(idx.search("blue", min_score=0.9)) == ["x.png"]


def test_deleted_photo_is_dropped(lib, tmp_path):
    lib.add("a.png", COLOURS["red"])
    lib.add("b.png", COLOURS["red"])
    idx = SmartIndex(tmp_path, FakeEncoder(), sleep_s=0)
    idx.update()
    lib.remove("a.png")
    stats = idx.update()
    assert stats["removed"] == 1 and stats["added"] == 0
    assert _names(idx.search("red", min_score=-1)) == ["b.png"]
    assert idx.status()["embedded"] == 1


def test_videos_skipped_and_bad_files_not_retried(lib, tmp_path):
    lib.add("ok.png", COLOURS["green"])
    lib.add("clip.mp4", None, kind="video", raw=b"not a video")
    lib.add("broken.jpg", None, raw=b"not an image")
    enc = FakeEncoder()
    idx = SmartIndex(tmp_path, enc, sleep_s=0)
    stats = idx.update()
    assert stats == {"added": 1, "removed": 0, "failed": 1, "todo": 2, "stopped": 0}
    assert idx.update()["todo"] == 0  # the broken file is remembered
    st = idx.status()
    assert st["embedded"] == 1 and st["failed"] == 1 and st["library_photos"] == 2


def test_resume_after_stop(lib, tmp_path):
    for i in range(10):
        lib.add(f"p{i}.png", COLOURS["red"] if i % 2 else COLOURS["blue"])
    enc = FakeEncoder()
    idx = SmartIndex(tmp_path, enc, batch_size=3, sleep_s=0)
    stop = threading.Event()

    def stop_after_first_batch(done, total):
        if done >= 3:
            stop.set()

    first = idx.update(stop_after_first_batch, stop)
    assert first["stopped"] == 1 and first["added"] == 3
    assert idx.status()["embedded"] == 3
    second = SmartIndex(tmp_path, enc, batch_size=3, sleep_s=0).update()
    assert second["added"] == 7 and second["todo"] == 7
    assert enc.images_seen == 10  # nothing embedded twice


def test_throttle_sleeps_between_batches(lib, tmp_path, monkeypatch):
    for i in range(5):
        lib.add(f"p{i}.png", COLOURS["red"])
    sleeps = []
    monkeypatch.setattr(kc_index, "_sleep", sleeps.append)
    SmartIndex(tmp_path, FakeEncoder(), batch_size=2, sleep_s=0.25).update()
    assert sleeps == [0.25, 0.25]  # 3 batches, no sleep after the last


def test_index_db_opened_read_only(lib, tmp_path, monkeypatch):
    lib.add("r.png", COLOURS["red"])
    before = lib.db.read_bytes()
    real_connect = kc_index._connect_db
    opened = []

    def spy(target, *a, **kw):
        opened.append((str(target), kw.get("uri", False)))
        conn = real_connect(target, *a, **kw)
        if "index.db" in str(target):
            # a read-only connection must refuse writes
            with pytest.raises(sqlite3.OperationalError, match="readonly"):
                conn.execute("CREATE TABLE kc_probe(x)")
        return conn

    monkeypatch.setattr(kc_index, "_connect_db", spy)
    idx = SmartIndex(tmp_path, FakeEncoder(), sleep_s=0)
    assert idx.update()["added"] == 1
    idx.status()
    to_index = [(t, uri) for t, uri in opened if "index.db" in t]
    assert to_index and all(uri and t.endswith("?mode=ro") for t, uri in to_index)
    assert lib.db.read_bytes() == before
    # SQLite may leave an empty -wal sidecar for a WAL database; nothing in it
    wal = Path(str(lib.db) + "-wal")
    assert not wal.exists() or wal.stat().st_size == 0


def test_similar_excludes_itself(lib, tmp_path):
    lib.add("r1.png", (220, 20, 20))
    lib.add("r2.png", (200, 40, 30))
    lib.add("b.png", COLOURS["blue"])
    idx = SmartIndex(tmp_path, FakeEncoder(), sleep_s=0)
    idx.update()
    hits = idx.similar(lib.photos / "r1.png")
    assert _names(hits) == ["r2.png", "b.png"]
    assert _names(idx.similar(lib.photos / "r1.png", min_score=0.9)) == ["r2.png"]
    # a file outside the index is embedded on the fly
    outside = tmp_path / "outside.png"
    Image.new("RGB", (10, 10), COLOURS["blue"]).save(outside)
    assert _names(idx.similar(outside, limit=1)) == ["b.png"]


def test_model_switch_drops_old_vectors(lib, tmp_path):
    lib.add("r.png", COLOURS["red"])
    SmartIndex(tmp_path, FakeEncoder(), sleep_s=0).update()

    class Other(FakeEncoder):
        model_id = "other"

    stats = SmartIndex(tmp_path, Other(), sleep_s=0).update()
    assert stats["added"] == 1


def test_missing_index_db_is_empty(tmp_path):
    idx = SmartIndex(tmp_path, FakeEncoder(), sleep_s=0)
    assert idx.update()["todo"] == 0
    assert idx.search("red") == []
    assert not (tmp_path / "index.db").exists()


def test_cli_status_and_search(lib, tmp_path, monkeypatch, capsys):
    from picasapy.kc_smart import cli

    lib.add("r.png", COLOURS["red"])
    monkeypatch.setattr(cli, "ClipEncoder", lambda *a, **k: FakeEncoder())
    assert cli.main(["--data-dir", str(tmp_path), "--json", "update", "--sleep", "0"]) == 0
    assert json.loads(capsys.readouterr().out)["added"] == 1
    assert cli.main(["--data-dir", str(tmp_path), "--json", "search", "red"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert [Path(r["path"]).name for r in out["results"]] == ["r.png"]
    assert cli.main(["--data-dir", str(tmp_path), "--json", "status"]) == 0
    st = json.loads(capsys.readouterr().out)
    assert st["embedded"] == 1 and st["models_downloaded"] is False


# ---------------------------------------------------------------- real model


@pytest.mark.slow
def test_real_clip_ranks_red_square_above_blue_circle(
    lib, tmp_path, pytestconfig, tmp_path_factory
):
    model_home = _cache_dir(pytestconfig, tmp_path_factory, "kc_smart_models")
    kc_model.ensure_models(model_home)
    sq = Image.new("RGB", (320, 240), (255, 255, 255))
    ImageDraw.Draw(sq).rectangle((80, 40, 240, 200), fill=(220, 20, 20))
    circ = Image.new("RGB", (320, 240), (255, 255, 255))
    ImageDraw.Draw(circ).ellipse((80, 40, 240, 200), fill=(20, 40, 220))
    sq.save(lib.photos / "red_square.jpg")
    circ.save(lib.photos / "blue_circle.jpg")
    for name in ("red_square.jpg", "blue_circle.jpg"):
        lib.add(name, None)  # file already on disk: just index it

    idx = SmartIndex(tmp_path, kc_model.ClipEncoder(model_home), sleep_s=0)
    assert idx.update()["added"] == 2
    hits = idx.search("a red square", min_score=-1)
    assert _names(hits) == ["red_square.jpg", "blue_circle.jpg"]
    assert hits[0][1] > hits[1][1] + 0.02
    hits = idx.search("a blue circle", min_score=-1)
    assert _names(hits)[0] == "blue_circle.jpg"
    assert _names(idx.similar(lib.photos / "red_square.jpg")) == ["blue_circle.jpg"]
