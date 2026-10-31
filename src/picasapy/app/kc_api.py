"""KC Picasa local JSON API: query and drive the app without touching the screen.

Stdlib ``ThreadingHTTPServer`` bound to 127.0.0.1 only, served from a daemon
thread. The chosen port is written to ``<data_dir>/kc-api.json``. index.db is
opened read-only for every request. If ``<data_dir>/kc-api-token`` exists, every
endpoint except ``/health`` needs ``Authorization: Bearer <token>``.
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import sqlite3
import threading
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from . import kc_queries as q

try:
    from picasapy.app.kc_ui import KC_VERSION
except Exception:  # Qt missing (headless tools) or import failure
    KC_VERSION = "dev"

log = logging.getLogger(__name__)

DEFAULT_PORT = 8781
PORT_TRIES = 5
MAX_BODY = 1 << 20
THUMB_CACHE_SIZE = 200
INFO_FILE = "kc-api.json"
TOKEN_FILE = "kc-api-token"


class _LRU:
    def __init__(self, size: int) -> None:
        self._size = size
        self._items: OrderedDict[tuple, bytes] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: tuple) -> bytes | None:
        with self._lock:
            value = self._items.get(key)
            if value is not None:
                self._items.move_to_end(key)
            return value

    def put(self, key: tuple, value: bytes) -> None:
        with self._lock:
            self._items[key] = value
            self._items.move_to_end(key)
            while len(self._items) > self._size:
                self._items.popitem(last=False)


class KcApiServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False  # on Windows, reuse would let two instances share a port

    data_dir: Path
    actions: object | None
    kc_port: int
    thumbs: _LRU

    def close(self) -> None:
        """Stop serving and remove kc-api.json if it is still ours."""
        self.shutdown()
        self.server_close()
        info = self.data_dir / INFO_FILE
        try:
            if json.loads(info.read_text("utf-8")).get("pid") == os.getpid() and (
                json.loads(info.read_text("utf-8")).get("port") == self.kc_port
            ):
                info.unlink()
        except (OSError, ValueError):
            pass


class _Handler(BaseHTTPRequestHandler):
    server: KcApiServer
    protocol_version = "HTTP/1.0"  # one request per connection; unread bodies can't confuse it
    server_version = "KCPicasaAPI"

    def log_message(self, fmt: str, *args: object) -> None:  # keep stderr quiet
        log.debug("kc-api %s", fmt % args)

    # -- helpers
    def _send(self, status: int, body: bytes, ctype: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: object) -> None:
        self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _error(self, status: int, message: str) -> None:
        self._json(status, {"ok": False, "error": message})

    def _authorized(self) -> bool:
        try:
            token = (self.server.data_dir / TOKEN_FILE).read_text("utf-8").strip()
        except OSError:
            return True
        if not token:
            return True
        sent = self.headers.get("Authorization", "")
        return sent.startswith("Bearer ") and hmac.compare_digest(
            sent[7:].strip().encode(), token.encode()
        )

    def _dispatch(self, method: str) -> None:
        url = urlsplit(self.path)
        path = url.path.rstrip("/") or "/"
        args = {k: v[-1] for k, v in parse_qs(url.query, keep_blank_values=True).items()}
        if path != "/health" and not self._authorized():
            self.send_response(401)
            self.send_header("WWW-Authenticate", "Bearer")
            body = b'{"ok": false, "error": "unauthorized"}'
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        try:
            if method == "POST":
                if path == "/v1/action":
                    return self._action()
                return self._error(404, "not found")
            self._get(path, args)
        except q.QueryError as exc:
            self._error(400, str(exc))
        except sqlite3.OperationalError as exc:
            self._error(503, f"index unavailable: {exc}")
        except Exception:  # never let a request kill the thread silently
            log.exception("kc-api request failed")
            self._error(500, "internal error")

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        self._dispatch("POST")

    # -- routes
    def _get(self, path: str, a: dict[str, str]) -> None:
        data_dir = self.server.data_dir
        if path == "/health":
            try:
                conn = q.connect_ro(data_dir)
                try:
                    n_photos, n_folders = q.counts(conn)
                finally:
                    conn.close()
            except sqlite3.OperationalError:
                n_photos = n_folders = None
            return self._json(200, {
                "ok": True, "app": "KC Picasa", "version": KC_VERSION,
                "photos": n_photos, "folders": n_folders,
                "db_path": str(q.db_path(data_dir)),
            })
        conn = q.connect_ro(data_dir)
        try:
            if path == "/v1/search":
                return self._json(200, q.search(conn, a.get("q", ""), a.get("limit")))
            if path == "/v1/photos":
                return self._json(200, q.photos(
                    conn, a.get("date"), a.get("from"), a.get("to"), a.get("folder"),
                    a.get("starred") in ("1", "true", "yes"), a.get("limit")))
            if path == "/v1/onthisday":
                return self._json(200, q.on_this_day(conn, a.get("date"), a.get("limit")))
            if path == "/v1/folders":
                return self._json(200, q.folders(conn))
            if path == "/v1/albums":
                return self._json(200, q.albums(conn))
            if path == "/v1/people":
                return self._json(200, q.people(conn))
            if path == "/v1/stats":
                return self._json(200, q.stats(conn))
            if path.startswith("/v1/photo/"):
                pid = self._id(path[len("/v1/photo/"):])
                detail = q.photo_detail(conn, pid) if pid is not None else None
                if detail is None:
                    return self._error(404, "no such photo")
                return self._json(200, detail)
            if path.startswith("/v1/thumb/"):
                pid = self._id(path[len("/v1/thumb/"):])
                full = q.photo_path(conn, pid) if pid is not None else None
                if full is None:
                    return self._error(404, "no such photo")
                return self._thumb(full, pid, a.get("size"))
        finally:
            conn.close()
        self._error(404, "not found")

    @staticmethod
    def _id(raw: str) -> int | None:
        raw = unquote(raw)
        return int(raw) if raw.isdigit() else None

    def _thumb(self, full: str, pid: int, size_arg: str | None) -> None:
        try:
            size = max(32, min(int(size_arg or 256), 1024))
        except ValueError:
            return self._error(400, "size must be an integer")
        try:
            key = (pid, size, os.stat(full).st_mtime_ns)
        except OSError:
            return self._error(404, "file is missing")
        data = self.server.thumbs.get(key)
        if data is None:
            try:
                data = q.make_thumb(full, size)
            except Exception:
                return self._error(415, "cannot make a thumbnail for this file")
            self.server.thumbs.put(key, data)
        self._send(200, data, "image/jpeg")

    def _action(self) -> None:
        actions = self.server.actions
        if actions is None:
            return self._error(501, "no action handler is registered")
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._error(400, "bad Content-Length")
        if length > MAX_BODY:
            return self._error(413, "body too large")
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
            action = body["action"]
            paths = body.get("paths", [])
            if not isinstance(action, str) or not isinstance(paths, list) or not all(
                isinstance(p, str) for p in paths
            ):
                raise TypeError
        except (ValueError, KeyError, TypeError):
            return self._error(400, 'expected {"action": str, "paths": [str]}')
        try:
            result = actions.run(action, paths)  # type: ignore[attr-defined]
        except Exception as exc:
            log.exception("kc-api action failed")
            return self._error(500, f"action failed: {exc}")
        try:
            json.dumps(result)
        except TypeError:
            result = str(result)
        self._json(200, {"ok": True, "result": result})


def start_server(
    data_dir: Path, port: int = DEFAULT_PORT, actions: object | None = None
) -> KcApiServer | None:
    """Start the API on 127.0.0.1 (port, then port+1..port+4). Returns None on failure.

    port=0 asks the OS for a free port (used by tests).
    """
    data_dir = Path(data_dir)
    try:
        candidates = [0] if port == 0 else [port + i for i in range(PORT_TRIES)]
        server = None
        for candidate in candidates:
            try:
                server = KcApiServer(("127.0.0.1", candidate), _Handler)
                break
            except OSError:
                continue
        if server is None:
            log.warning("KC API: ports %s-%s are busy, API not started", port, port + PORT_TRIES - 1)
            return None
        server.data_dir = data_dir
        server.actions = actions
        server.thumbs = _LRU(THUMB_CACHE_SIZE)
        server.kc_port = server.server_address[1]
        threading.Thread(target=server.serve_forever, name="kc-api", daemon=True).start()
        try:
            (data_dir / INFO_FILE).write_text(
                json.dumps({"port": server.kc_port, "pid": os.getpid(), "version": KC_VERSION}),
                encoding="utf-8",
            )
        except OSError:
            log.warning("KC API: could not write %s", INFO_FILE)
        log.info("KC API listening on 127.0.0.1:%s", server.kc_port)
        return server
    except Exception:
        log.exception("KC API failed to start")
        return None
