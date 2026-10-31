"""Command line for KC Smart Search.

    python -m picasapy.kc_smart [--data-dir DIR] [--json] update
    python -m picasapy.kc_smart search "dog on the beach" [--limit N] [--min-score S]
    python -m picasapy.kc_smart similar <path> [--limit N]
    python -m picasapy.kc_smart status

Without --data-dir the app's own data folder is used.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from pathlib import Path

from .index import DEFAULT_MIN_SCORE, SmartIndex
from .model import ClipEncoder, models_present


def default_data_dir() -> Path:
    from picasapy.app.application_data import _data_dir

    return _data_dir()


def _print(args, payload, text_lines):
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for line in text_lines:
            print(line)


def _download_progress(name: str, done: int, total: int) -> None:
    pct = 100 * done // total if total else 0
    print(f"\rdownloading {name}: {done >> 20}/{total >> 20} MB ({pct}%)", end="", file=sys.stderr)
    if done >= total:
        print(file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m picasapy.kc_smart", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", type=Path, help="folder that holds index.db")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--threads", type=int, default=None, help="onnxruntime CPU threads")
    sub = ap.add_subparsers(dest="cmd", required=True)
    up = sub.add_parser("update", help="embed new and changed photos")
    up.add_argument("--batch", type=int, default=16)
    up.add_argument("--sleep", type=float, default=0.05, help="pause between batches (s)")
    se = sub.add_parser("search", help="find photos by a text description")
    se.add_argument("text")
    se.add_argument("--limit", type=int, default=60)
    se.add_argument("--min-score", type=float, default=DEFAULT_MIN_SCORE)
    si = sub.add_parser("similar", help="find photos that look like this one")
    si.add_argument("path")
    si.add_argument("--limit", type=int, default=60)
    si.add_argument("--min-score", type=float, default=0.0)
    sub.add_parser("status", help="counts and model state")
    args = ap.parse_args(argv)

    data_dir = args.data_dir or default_data_dir()
    encoder = ClipEncoder(data_dir, threads=args.threads,
                          progress_cb=None if args.json else _download_progress)
    idx = SmartIndex(data_dir, encoder,
                     batch_size=getattr(args, "batch", 16), sleep_s=getattr(args, "sleep", 0.05))

    if args.cmd == "update":
        stop = threading.Event()
        t0 = time.perf_counter()

        def prog(done: int, total: int) -> None:
            if not args.json and total:
                print(f"\rembedding {done}/{total}", end="", file=sys.stderr)

        try:
            stats = idx.update(prog, stop)
        except KeyboardInterrupt:
            stop.set()
            print("\nstopped; run update again to resume", file=sys.stderr)
            return 130
        secs = time.perf_counter() - t0
        stats["seconds"] = round(secs, 2)
        if not args.json:
            print(file=sys.stderr)
        rate = stats["added"] / secs if secs and stats["added"] else 0.0
        _print(args, stats, [
            f"added {stats['added']}, removed {stats['removed']}, failed {stats['failed']} "
            f"in {secs:.1f}s ({rate:.1f} photos/s)"
        ])
        return 0
    if args.cmd in ("search", "similar"):
        t0 = time.perf_counter()
        if args.cmd == "search":
            hits = idx.search(args.text, limit=args.limit, min_score=args.min_score)
        else:
            hits = idx.similar(args.path, limit=args.limit, min_score=args.min_score)
        ms = (time.perf_counter() - t0) * 1000
        _print(args, {"results": [{"path": p, "score": round(s, 4)} for p, s in hits],
                      "ms": round(ms, 1)},
               [f"{s:.3f}  {p}" for p, s in hits] + [f"({len(hits)} results, {ms:.0f} ms)"])
        return 0
    st = idx.status()
    st["models_downloaded"] = models_present(data_dir)
    _print(args, st, [f"{k}: {v}" for k, v in st.items()])
    return 0
