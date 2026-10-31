"""KC Picasa MCP server (stdio).

Reads the photo index (index.db) read-only, so it works with the app closed.
If the app's local API is running, it also offers ``run_action``.

Data dir: ``--data-dir`` > env ``KC_PICASA_DATA`` > ``%LOCALAPPDATA%\\PicasaPy``.
Speaks newline-delimited JSON-RPC 2.0 (MCP stdio transport) with the standard
library only, so it needs no extra packages beyond the repo's own ``src`` tree.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from picasapy.app import kc_queries as q  # noqa: E402

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "kc-picasa", "version": "0.1.0"}

_data_dir: Path = Path()


def default_data_dir() -> Path:
    env = os.environ.get("KC_PICASA_DATA")
    if env:
        return Path(env)
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "PicasaPy"


def set_data_dir(path: Path | str) -> None:
    global _data_dir
    _data_dir = Path(path)


def _with_conn(fn, *args, **kwargs):
    conn = q.connect_ro(_data_dir)
    try:
        return fn(conn, *args, **kwargs)
    finally:
        conn.close()


# -- tools (plain functions; call them directly in tests)
def search_photos(q_text: str, limit: int = 50) -> list[dict]:
    return _with_conn(q.search, q_text, limit)


def photos_on_date(date: str) -> list[dict]:
    return _with_conn(q.photos, date=date, limit=q.MAX_LIMIT)


def on_this_day(month_day: str = "") -> dict:
    return _with_conn(q.on_this_day, month_day or None)


def list_folders() -> list[dict]:
    return _with_conn(q.folders)


def list_albums() -> list[dict]:
    return _with_conn(q.albums)


def list_people() -> list[dict]:
    return _with_conn(q.people)


def photo_stats() -> dict:
    return _with_conn(q.stats)


def get_photo(id: int) -> dict:
    detail = _with_conn(q.photo_detail, int(id))
    if detail is None:
        raise q.QueryError(f"no photo with id {id}")
    return detail


def _api_base() -> tuple[str, str] | None:
    """(base url, token) when the app's API answers /health, else None."""
    try:
        info = json.loads((_data_dir / "kc-api.json").read_text("utf-8"))
        base = f"http://127.0.0.1:{int(info['port'])}"
        with urllib.request.urlopen(base + "/health", timeout=1.5) as r:
            if not json.load(r).get("ok"):
                return None
    except (OSError, ValueError, KeyError, urllib.error.URLError):
        return None
    try:
        token = (_data_dir / "kc-api-token").read_text("utf-8").strip()
    except OSError:
        token = ""
    return base, token


def run_action(action: str, paths: list[str]) -> dict:
    found = _api_base()
    if found is None:
        raise RuntimeError("KC Picasa is not running (its local API did not answer)")
    base, token = found
    req = urllib.request.Request(
        base + "/v1/action",
        data=json.dumps({"action": action, "paths": paths}).encode("utf-8"),
        headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as exc:
        try:
            detail = json.load(exc).get("error", "")
        except ValueError:
            detail = ""
        raise RuntimeError(f"app answered {exc.code}: {detail}") from None


def _schema(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or []}


_STR = {"type": "string"}
_INT = {"type": "integer"}
TOOLS: dict[str, tuple[object, str, dict]] = {
    "search_photos": (search_photos, "Full-text search over photo names, captions and keywords (prefix match).",
                      _schema({"q": _STR, "limit": {**_INT, "default": 50}}, ["q"])),
    "photos_on_date": (photos_on_date, "Photos taken on one day (YYYY-MM-DD).", _schema({"date": _STR}, ["date"])),
    "on_this_day": (on_this_day, "Photos taken on a month-day (MM-DD, default today), grouped by year.",
                    _schema({"month_day": _STR})),
    "list_folders": (list_folders, "All indexed folders with photo counts.", _schema({})),
    "list_albums": (list_albums, "All albums with photo counts.", _schema({})),
    "list_people": (list_people, "Named people from face tags, with photo counts.", _schema({})),
    "photo_stats": (photo_stats, "Counts by year, by kind, and starred.", _schema({})),
    "get_photo": (get_photo, "Full details of one photo by id.", _schema({"id": _INT}, ["id"])),
    "run_action": (run_action, "Ask the running app to perform an action on files (needs the app open).",
                   _schema({"action": _STR, "paths": {"type": "array", "items": _STR}}, ["action", "paths"])),
}

# MCP argument name -> function parameter name
_ARG_ALIAS = {"search_photos": {"q": "q_text"}}


def call_tool(name: str, arguments: dict) -> dict:
    """Run a tool and return an MCP tool result."""
    if name not in TOOLS:
        return {"isError": True, "content": [{"type": "text", "text": f"unknown tool: {name}"}]}
    fn = TOOLS[name][0]
    kwargs = {_ARG_ALIAS.get(name, {}).get(k, k): v for k, v in (arguments or {}).items()}
    try:
        result = fn(**kwargs)  # type: ignore[operator]
    except Exception as exc:  # tool errors are reported to the model, not raised
        return {"isError": True, "content": [{"type": "text", "text": f"{type(exc).__name__}: {exc}"}]}
    return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=1)}]}


def handle(msg: dict) -> dict | None:
    """One JSON-RPC message in, response (or None for notifications) out."""
    method, mid = msg.get("method"), msg.get("id")
    if mid is None:  # notification (e.g. notifications/initialized)
        return None

    def ok(result: object) -> dict:
        return {"jsonrpc": "2.0", "id": mid, "result": result}

    if method == "initialize":
        return ok({"protocolVersion": PROTOCOL_VERSION, "capabilities": {"tools": {}}, "serverInfo": SERVER_INFO})
    if method == "ping":
        return ok({})
    if method == "tools/list":
        return ok({"tools": [
            {"name": n, "description": d, "inputSchema": s}
            for n, (_f, d, s) in TOOLS.items()
            if n != "run_action" or _api_base() is not None
        ]})
    if method == "tools/call":
        params = msg.get("params") or {}
        return ok(call_tool(params.get("name", ""), params.get("arguments") or {}))
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}}


def serve(stdin=None, stdout=None) -> None:
    stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
            reply = handle(msg) if isinstance(msg, dict) else None
        except ValueError:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
        if reply is not None:
            stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
            stdout.flush()


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="KC Picasa MCP server (stdio)")
    ap.add_argument("--data-dir", help="folder holding index.db (default: env KC_PICASA_DATA or %%LOCALAPPDATA%%\\PicasaPy)")
    args = ap.parse_args(argv)
    set_data_dir(args.data_dir or default_data_dir())
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    serve()


if __name__ == "__main__":
    main()
