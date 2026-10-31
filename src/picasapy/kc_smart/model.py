"""CLIP image + text encoders on onnxruntime (CPU), with a one-time download.

The model files (see MODELS.md) are fetched on first use into
`<data_dir>/kc-smart/models/<model id>/`, resumably (`.part` + HTTP Range),
and each one is checked against a pinned sha256 before it is used.
After that everything runs offline.
"""

from __future__ import annotations

import hashlib
import os
import sys
import threading
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np
from PIL import Image

from .tokenizer import ClipTokenizer

# progress_cb(file_name, bytes_done, bytes_total)
DownloadProgress = Callable[[str, int, int], None]


class Encoder(Protocol):
    """What SmartIndex needs. Vectors come back L2-normalized, float32."""

    model_id: str
    dim: int

    def encode_images(self, images: Sequence[Image.Image]) -> np.ndarray: ...

    def encode_texts(self, texts: Sequence[str]) -> np.ndarray: ...


@dataclass(frozen=True)
class ModelFile:
    name: str  # path inside the repo
    sha256: str
    size: int


@dataclass(frozen=True)
class ModelSpec:
    model_id: str
    repo: str
    revision: str
    vision: ModelFile
    text: ModelFile
    vocab: ModelFile
    merges: ModelFile
    image_size: int = 224
    mean: tuple[float, float, float] = (0.48145466, 0.4578275, 0.40821073)
    std: tuple[float, float, float] = (0.26862954, 0.26130258, 0.27577711)

    @property
    def files(self) -> tuple[ModelFile, ...]:
        return (self.vision, self.text, self.vocab, self.merges)

    @property
    def total_bytes(self) -> int:
        return sum(f.size for f in self.files)


CLIP_B32_Q8 = ModelSpec(
    model_id="clip-vit-b32-q8",
    repo="Xenova/clip-vit-base-patch32",
    revision="6b7c523703ae26e39be4b03774966f8571c7f523",
    vision=ModelFile(
        "onnx/vision_model_quantized.onnx",
        "583fd1110a514667812fee7d684952aaf82a99b959760c8d7dca7e0ab9839299",
        89_117_001,
    ),
    text=ModelFile(
        "onnx/text_model_quantized.onnx",
        "73baab855d406190da9faa498cfedf65f15cf309f4cc7385b7b032e6d08e5c3a",
        64_504_507,
    ),
    vocab=ModelFile(
        "vocab.json",
        "5047b556ce86ccaf6aa22b3ffccfc52d391ea4accdab9c2f2407da5b742d4363",
        862_328,
    ),
    merges=ModelFile(
        "merges.txt",
        "9fd691f7c8039210e0fced15865466c65820d09b63988b0174bfe25de299051a",
        524_619,
    ),
)

DEFAULT_SPEC = CLIP_B32_Q8
DEFAULT_BASE_URL = "https://huggingface.co"


class ModelDownloadError(RuntimeError):
    pass


def models_dir(data_dir: str | Path, spec: ModelSpec = DEFAULT_SPEC) -> Path:
    return Path(data_dir) / "kc-smart" / "models" / spec.model_id


def _local_path(root: Path, f: ModelFile) -> Path:
    return root / Path(f.name).name


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def models_present(data_dir: str | Path, spec: ModelSpec = DEFAULT_SPEC) -> bool:
    root = models_dir(data_dir, spec)
    return all(
        _local_path(root, f).is_file() and _local_path(root, f).stat().st_size == f.size
        for f in spec.files
    )


def download_file(
    url: str,
    dest: Path,
    sha256: str,
    size: int,
    progress_cb: DownloadProgress | None = None,
    stop_event: threading.Event | None = None,
    timeout: float = 60.0,
) -> Path:
    """Download `url` to `dest` with resume and a sha256 check.

    Partial data lives in `dest.part`; a later call continues from its size.
    A hash mismatch deletes the partial file and raises.
    """
    if dest.is_file() and dest.stat().st_size == size:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    have = part.stat().st_size if part.exists() else 0
    if have > size:
        part.unlink()
        have = 0
    if have < size:
        req = urllib.request.Request(url, headers={"User-Agent": "kc-picasa-smart/1"})
        if have:
            req.add_header("Range", f"bytes={have}-")
        try:
            resp = urllib.request.urlopen(req, timeout=timeout)  # noqa: S310
        except OSError as exc:
            raise ModelDownloadError(f"download failed for {dest.name}: {exc}") from exc
        with resp:
            if have and resp.status != 206:
                have = 0  # server ignored Range: start over
            with open(part, "ab" if have else "wb") as out:
                done = have
                while True:
                    if stop_event is not None and stop_event.is_set():
                        raise ModelDownloadError("download stopped")
                    chunk = resp.read(1 << 20)
                    if not chunk:
                        break
                    out.write(chunk)
                    done += len(chunk)
                    if progress_cb:
                        progress_cb(dest.name, done, size)
    got = _sha256(part)
    if got != sha256:
        part.unlink(missing_ok=True)
        raise ModelDownloadError(f"sha256 mismatch for {dest.name}: {got}")
    os.replace(part, dest)
    return dest


def ensure_models(
    data_dir: str | Path,
    spec: ModelSpec = DEFAULT_SPEC,
    progress_cb: DownloadProgress | None = None,
    stop_event: threading.Event | None = None,
    base_url: str | None = None,
) -> Path:
    """Make sure every model file is on disk; download what is missing."""
    base = (base_url or os.environ.get("KC_SMART_MODEL_BASE_URL") or DEFAULT_BASE_URL)
    root = models_dir(data_dir, spec)
    for f in spec.files:
        url = f"{base.rstrip('/')}/{spec.repo}/resolve/{spec.revision}/{f.name}"
        download_file(url, _local_path(root, f), f.sha256, f.size, progress_cb, stop_event)
    return root


def _platform() -> str:
    return sys.platform


def _import_onnxruntime():
    """Import onnxruntime; on Windows fall back to the MSVC runtime DLLs that
    PySide6 bundles when the system has no Visual C++ redistributable."""
    try:
        import onnxruntime

        return onnxruntime
    except ImportError:
        if _platform() != "win32":
            raise
    import ctypes

    import PySide6

    qt_dir = Path(PySide6.__file__).parent
    for dll in ("vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll", "msvcp140_1.dll"):
        if (qt_dir / dll).is_file():
            ctypes.WinDLL(str(qt_dir / dll))
    for name in [m for m in sys.modules if m.startswith("onnxruntime")]:
        del sys.modules[name]
    import onnxruntime

    return onnxruntime


def preprocess(
    images: Sequence[Image.Image], spec: ModelSpec = DEFAULT_SPEC
) -> np.ndarray:
    """CLIP preprocessing: shortest edge -> 224 bicubic, centre crop, normalize.
    Returns NCHW float32."""
    s = spec.image_size
    mean = np.asarray(spec.mean, dtype=np.float32)
    std = np.asarray(spec.std, dtype=np.float32)
    out = np.empty((len(images), 3, s, s), dtype=np.float32)
    for i, im in enumerate(images):
        im = im.convert("RGB")
        w, h = im.size
        scale = s / min(w, h)
        nw, nh = max(s, round(w * scale)), max(s, round(h * scale))
        im = im.resize((nw, nh), Image.Resampling.BICUBIC)
        left, top = (nw - s) // 2, (nh - s) // 2
        im = im.crop((left, top, left + s, top + s))
        arr = np.asarray(im, dtype=np.float32) / 255.0
        out[i] = ((arr - mean) / std).transpose(2, 0, 1)
    return out


def _l2(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float32)
    n = np.linalg.norm(x, axis=1, keepdims=True)
    return x / np.maximum(n, 1e-12)


class ClipEncoder:
    """CLIP encoders. Sessions load lazily, so text-only use never loads the
    vision model and vice versa."""

    dim = 512

    def __init__(
        self,
        data_dir: str | Path,
        spec: ModelSpec = DEFAULT_SPEC,
        threads: int | None = None,
        progress_cb: DownloadProgress | None = None,
    ):
        self.spec = spec
        self.model_id = spec.model_id
        self.data_dir = Path(data_dir)
        self.threads = threads or max(1, (os.cpu_count() or 2) // 2)
        self._progress_cb = progress_cb
        self._lock = threading.Lock()
        self._vision = None
        self._text = None
        self._tokenizer: ClipTokenizer | None = None

    def _root(self) -> Path:
        return ensure_models(self.data_dir, self.spec, self._progress_cb)

    def _session(self, f: ModelFile):
        ort = _import_onnxruntime()
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = self.threads
        opts.inter_op_num_threads = 1
        return ort.InferenceSession(
            str(_local_path(self._root(), f)), opts, providers=["CPUExecutionProvider"]
        )

    def _vision_session(self):
        with self._lock:
            if self._vision is None:
                self._vision = self._session(self.spec.vision)
            return self._vision

    def _text_session(self):
        with self._lock:
            if self._text is None:
                root = self._root()
                self._tokenizer = ClipTokenizer(
                    _local_path(root, self.spec.vocab), _local_path(root, self.spec.merges)
                )
                self._text = self._session(self.spec.text)
            return self._text

    def encode_images(self, images: Sequence[Image.Image]) -> np.ndarray:
        sess = self._vision_session()
        (out,) = sess.run(["image_embeds"], {"pixel_values": preprocess(images, self.spec)})
        return _l2(out)

    def encode_texts(self, texts: Sequence[str]) -> np.ndarray:
        sess = self._text_session()
        assert self._tokenizer is not None
        ids = self._tokenizer.encode_batch(list(texts))
        (out,) = sess.run(["text_embeds"], {"input_ids": ids})
        return _l2(out)
