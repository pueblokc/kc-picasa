"""CLIP byte-level BPE tokenizer, pure Python (no torch / transformers).

Matches the Hugging Face `CLIPTokenizerFast` used by the ONNX export:
NFC normalize, collapse whitespace, lowercase, split with the CLIP pattern
`'s|'t|'re|'ve|'m|'ll|'d|\\p{L}+|\\p{N}|[^\\s\\p{L}\\p{N}]+`, map bytes to
unicode, then BPE with `</w>` on the last symbol of each word.

The pattern is implemented as a small scanner over `unicodedata`
categories because Python's `re` has no `\\p{..}` classes.
"""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

SOT = "<|startoftext|>"
EOT = "<|endoftext|>"
CONTEXT_LENGTH = 77

_CONTRACTIONS = ("'s", "'t", "'re", "'ve", "'m", "'ll", "'d")
_WS = re.compile(r"\s+")


@lru_cache(maxsize=1)
def bytes_to_unicode() -> dict[int, str]:
    """GPT-2 / CLIP reversible byte -> printable unicode char table."""
    bs = (
        list(range(ord("!"), ord("~") + 1))
        + list(range(ord("¡"), ord("¬") + 1))
        + list(range(ord("®"), ord("ÿ") + 1))
    )
    cs = bs[:]
    n = 0
    for b in range(256):
        if b not in bs:
            bs.append(b)
            cs.append(256 + n)
            n += 1
    return dict(zip(bs, (chr(c) for c in cs), strict=True))


def _is_letter(ch: str) -> bool:
    return unicodedata.category(ch).startswith("L")


def _is_number(ch: str) -> bool:
    return unicodedata.category(ch).startswith("N")


def pre_tokenize(text: str) -> list[str]:
    """Split normalized text the way the CLIP regex does."""
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        if ch == "'":
            hit = next((c for c in _CONTRACTIONS if text.startswith(c, i)), None)
            if hit:
                out.append(hit)
                i += len(hit)
                continue
        if _is_letter(ch):
            j = i + 1
            while j < n and _is_letter(text[j]):
                j += 1
        elif _is_number(ch):
            j = i + 1
        else:
            j = i + 1
            while j < n and not (
                text[j].isspace() or _is_letter(text[j]) or _is_number(text[j])
            ):
                j += 1
        out.append(text[i:j])
        i = j
    return out


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    return _WS.sub(" ", text).lower()


class ClipTokenizer:
    def __init__(self, vocab_path: str | Path, merges_path: str | Path):
        self.encoder: dict[str, int] = json.loads(Path(vocab_path).read_text("utf-8"))
        lines = Path(merges_path).read_text("utf-8").splitlines()
        merges = [tuple(ln.split()) for ln in lines if ln and not ln.startswith("#version")]
        self.bpe_ranks = {m: i for i, m in enumerate(merges) if len(m) == 2}
        self.byte_encoder = bytes_to_unicode()
        self.sot_id = self.encoder[SOT]
        self.eot_id = self.encoder[EOT]
        self._cache: dict[str, list[str]] = {}

    def _bpe(self, token: str) -> list[str]:
        cached = self._cache.get(token)
        if cached is not None:
            return cached
        word = list(token[:-1]) + [token[-1] + "</w>"]
        while len(word) > 1:
            pairs = {(word[k], word[k + 1]) for k in range(len(word) - 1)}
            best = min(pairs, key=lambda p: self.bpe_ranks.get(p, float("inf")))
            if best not in self.bpe_ranks:
                break
            first, second = best
            merged: list[str] = []
            k = 0
            while k < len(word):
                if k < len(word) - 1 and word[k] == first and word[k + 1] == second:
                    merged.append(first + second)
                    k += 2
                else:
                    merged.append(word[k])
                    k += 1
            word = merged
        if len(self._cache) < 50_000:
            self._cache[token] = word
        return word

    def encode(self, text: str, context_length: int = CONTEXT_LENGTH) -> list[int]:
        """Token ids with start/end markers, truncated to `context_length`."""
        ids: list[int] = []
        for piece in pre_tokenize(normalize(text)):
            mapped = "".join(self.byte_encoder[b] for b in piece.encode("utf-8"))
            ids.extend(self.encoder[t] for t in self._bpe(mapped))
        ids = ids[: context_length - 2]
        return [self.sot_id, *ids, self.eot_id]

    def encode_batch(self, texts: list[str], context_length: int = CONTEXT_LENGTH):
        """Return an int64 array padded with the end token (CLIP pad token)."""
        import numpy as np

        rows = [self.encode(t, context_length) for t in texts]
        width = max(len(r) for r in rows)
        arr = np.full((len(rows), width), self.eot_id, dtype=np.int64)
        for i, r in enumerate(rows):
            arr[i, : len(r)] = r
        return arr
