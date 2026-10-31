"""KC Picasa local API: real HTTP against a temp index on an ephemeral port."""

from __future__ import annotations

import json
import socket
import sqlite3
import urllib.error
import urllib.request
from io import BytesIO
from urllib.parse import quote

import pytest
from kc_index_fixture import PHOTOS, TODAY_MD, build_index
from PIL import Image

from picasapy.app import kc_queries
from picasapy.app.kc_api import start_server
from picasapy.index.database import open_index

VISIBLE = len(PHOTOS) - 1  # one photo is hidden


@pytest.fixture
def api(tmp_path):
    ids = build_index(tmp_path)
    server = start_server(tmp_path, port=0)
    assert server is not None
    yield tmp_path, server, ids
    server.close()


def call(server, path, method="GET", body=None, token=None, raw=False):
    url = f"http://127.0.0.1:{server.kc_port}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            payload = r.read()
            return r.status, (payload if raw else json.loads(payload)), r.headers
    except urllib.error.HTTPError as e:
        payload = e.read()
        return e.code, (payload if raw else json.loads(payload)), e.headers


def names(server, path):
    return [p["name"] for p in call(server, path)[1]]


def test_health_and_info_file(api):
    tmp, server, _ = api
    status, body, _ = call(server, "/health")
    assert status == 200
    assert body["ok"] and body["app"] == "KC Picasa" and body["version"]
    assert body["photos"] == len(PHOTOS) and body["folders"] == 1
    assert body["db_path"].endswith("index.db")
    info = json.loads((tmp / "kc-api.json").read_text())
    assert info["port"] == server.kc_port and info["pid"] and info["version"]


def test_binds_loopback_only(api):
    _, server, _ = api
    assert server.server_address[0] == "127.0.0.1"


def test_search(api):
    _, server, _ = api
    status, body, _ = call(server, "/v1/search?q=beach")
    assert status == 200
    assert [p["name"] for p in body] == ["beach_sunset.jpg"]  # hidden photo excluded
    p = body[0]
    assert set(p) == {"id", "path", "name", "taken", "star", "width", "height", "caption"}
    assert p["path"].endswith("beach_sunset.jpg") and p["star"] == 1 and p["width"] == 200
    assert names(server, "/v1/search?q=sun") == ["beach_sunset.jpg"]  # prefix
    assert names(server, "/v1/search?q=mountain") == ["hike_peak.jpg"]  # keywords
    assert names(server, "/v1/search?q=cr%C3%A8me") == ["café_août.jpg"]  # non-ASCII


ODD = ['"', '"wow"', 'wow"', "a OR b", "NEAR(", "*", "beach AND", "-sea",
       "x'; DROP TABLE photos;--", "(", ":", "name:beach", "^"]


@pytest.mark.parametrize("q", ODD)
def test_search_odd_input_never_errors(api, q):
    _, server, _ = api
    status, body, _ = call(server, "/v1/search?q=" + quote(q))
    assert status == 200 and isinstance(body, list)
    assert call(server, "/health")[1]["photos"] == len(PHOTOS)  # nothing was dropped


def test_search_quotes_still_match(api):
    _, server, _ = api
    assert names(server, "/v1/search?q=%22wow%22") == ["birthday cake.jpg"]


def test_search_empty_and_limit(api):
    _, server, _ = api
    assert call(server, "/v1/search")[1] == []
    assert call(server, "/v1/search?q=%20")[1] == []
    status, body, _ = call(server, "/v1/search?q=jpg&limit=2")
    assert status == 200 and len(body) == 2
    assert call(server, "/v1/search?q=a&limit=zzz")[0] == 400


def test_photos_filters(api):
    _, server, _ = api
    assert names(server, "/v1/photos?date=2024-06-01") == ["hike_peak.jpg"]
    assert names(server, "/v1/photos?from=2023-01-01&to=2023-12-31") == [
        "beach_sunset.jpg", "birthday cake.jpg"]
    assert names(server, "/v1/photos?starred=1") == ["beach_sunset.jpg", "hike_peak.jpg"]
    assert len(names(server, "/v1/photos")) == VISIBLE
    assert len(names(server, "/v1/photos?limit=3")) == 3
    folder = call(server, "/v1/folders")[1][0]["path"]
    assert len(names(server, "/v1/photos?folder=" + quote(folder))) == VISIBLE
    assert names(server, "/v1/photos?folder=" + quote(folder + "_nope")) == []
    assert call(server, "/v1/photos?date=2024-13-40")[0] == 400
    assert call(server, "/v1/photos?date=yesterday")[0] == 400


def test_photos_taken_override_wins(api):
    tmp, server, ids = api
    with open_index(tmp / "index.db") as conn:
        conn.execute("UPDATE photos SET taken_at_override='2020-02-02T00:00:00' WHERE id=?",
                     (ids["hike_peak.jpg"],))
        conn.commit()
    assert names(server, "/v1/photos?date=2020-02-02") == ["hike_peak.jpg"]
    assert names(server, "/v1/photos?date=2024-06-01") == []


def test_onthisday(api):
    _, server, _ = api
    status, body, _ = call(server, "/v1/onthisday")  # default: today
    assert status == 200 and body["date"] == TODAY_MD
    assert [y["year"] for y in body["years"]] == [2025, 2024]
    assert body["years"][0]["photos"][0]["name"] == "today_then.jpg"
    body = call(server, "/v1/onthisday?date=07-04")[1]
    assert [y["year"] for y in body["years"]] == [2023]
    assert call(server, "/v1/onthisday?date=01-01")[1]["years"] == []
    assert call(server, "/v1/onthisday?date=13-45")[0] == 400
    assert call(server, "/v1/onthisday?date=garbage")[0] == 400


def test_folders_albums_people(api):
    _, server, _ = api
    folders = call(server, "/v1/folders")[1]
    assert len(folders) == 1 and folders[0]["photos"] == VISIBLE
    assert call(server, "/v1/albums")[1] == [
        {"token": "tok1", "name": "Summer", "date": "2024-06-01", "description": None, "photos": 1}]
    assert call(server, "/v1/people")[1] == [{"name": "Alex", "faces": 1, "photos": 1}]


def test_people_empty_without_face_table(tmp_path):
    build_index(tmp_path)
    conn = sqlite3.connect(tmp_path / "index.db")
    conn.execute("DROP TABLE face")
    conn.commit()
    conn.close()
    ro = kc_queries.connect_ro(tmp_path)
    try:
        assert kc_queries.people(ro) == []
    finally:
        ro.close()


def test_photo_detail(api):
    _, server, ids = api
    status, body, _ = call(server, f"/v1/photo/{ids['hike_peak.jpg']}")
    assert status == 200
    assert body["name"] == "hike_peak.jpg" and body["exists"] is True
    assert body["keywords"] == ["mountain", "summer"] and body["albums"] == ["Summer"]
    assert call(server, f"/v1/photo/{ids['birthday cake.jpg']}")[1]["people"] == ["Alex"]
    assert call(server, "/v1/photo/99999")[0] == 404
    assert call(server, "/v1/photo/abc")[0] == 404


def test_stats(api):
    _, server, _ = api
    body = call(server, "/v1/stats")[1]
    assert body["photos"] == VISIBLE and body["starred"] == 2
    assert body["by_year"] == {"2023": 2, "2024": 2, "2025": 2}
    assert body["by_kind"] == {"image": 6}


def test_thumb_is_valid_jpeg_and_honours_orientation(api):
    _, server, ids = api
    status, data, headers = call(server, f"/v1/thumb/{ids['beach_sunset.jpg']}?size=64", raw=True)
    assert status == 200 and headers["Content-Type"] == "image/jpeg"
    im = Image.open(BytesIO(data))
    assert im.format == "JPEG" and im.size == (64, 32)
    im.load()
    # EXIF orientation 6: stored 200x100, displayed portrait
    data = call(server, f"/v1/thumb/{ids['hike_peak.jpg']}?size=100", raw=True)[1]
    assert Image.open(BytesIO(data)).size == (50, 100)
    # second call (LRU) returns identical bytes
    assert call(server, f"/v1/thumb/{ids['hike_peak.jpg']}?size=100", raw=True)[1] == data
    assert call(server, "/v1/thumb/99999")[0] == 404
    assert call(server, f"/v1/thumb/{ids['beach_sunset.jpg']}?size=big")[0] == 400


def test_thumb_missing_file_is_404(api):
    tmp, server, ids = api
    (tmp / "photos" / "hike_peak.jpg").unlink()
    assert call(server, f"/v1/thumb/{ids['hike_peak.jpg']}")[0] == 404


def test_unknown_route_and_method(api):
    _, server, _ = api
    assert call(server, "/nope")[0] == 404
    assert call(server, "/v1/search", method="POST", body={})[0] == 404


def test_token_auth(api):
    tmp, server, _ = api
    assert call(server, "/v1/stats")[0] == 200  # no token file: open
    (tmp / "kc-api-token").write_text("s3cret\n", encoding="utf-8")
    assert call(server, "/health")[0] == 200  # health is always open
    assert call(server, "/v1/stats")[0] == 401
    assert call(server, "/v1/stats", token="wrong")[0] == 401
    assert call(server, "/v1/stats", token="s3cret")[0] == 200
    assert call(server, "/v1/action", method="POST", body={"action": "x", "paths": []})[0] == 401
    (tmp / "kc-api-token").unlink()
    assert call(server, "/v1/stats")[0] == 200


def test_action_501_without_handler(api):
    _, server, _ = api
    status, body, _ = call(server, "/v1/action", method="POST",
                           body={"action": "share", "paths": ["a"]})
    assert status == 501 and body["ok"] is False


def test_action_forwarded(tmp_path):
    build_index(tmp_path)
    seen = []

    class Actions:
        def run(self, action, paths):
            seen.append((action, paths))
            if action == "boom":
                raise RuntimeError("nope")
            return {"done": len(paths)}

    server = start_server(tmp_path, port=0, actions=Actions())
    try:
        status, body, _ = call(server, "/v1/action", method="POST",
                               body={"action": "share", "paths": ["a.jpg", "b.jpg"]})
        assert status == 200 and body == {"ok": True, "result": {"done": 2}}
        assert seen == [("share", ["a.jpg", "b.jpg"])]
        assert call(server, "/v1/action", method="POST", body={"action": "boom", "paths": []})[0] == 500
        assert call(server, "/v1/action", method="POST", body={"paths": []})[0] == 400
        assert call(server, "/v1/action", method="POST", body={"action": "x", "paths": "a"})[0] == 400
        req = urllib.request.Request(f"http://127.0.0.1:{server.kc_port}/v1/action",
                                     data=b"{not json", method="POST")
        with pytest.raises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(req, timeout=5)
        assert err.value.code == 400
    finally:
        server.close()


def test_busy_port_falls_back_to_next(tmp_path):
    build_index(tmp_path)
    first = start_server(tmp_path, port=0)
    try:
        base = first.kc_port
        second = start_server(tmp_path, port=base)
        try:
            assert second is not None and second.kc_port == base + 1
            assert call(second, "/health")[0] == 200
            assert json.loads((tmp_path / "kc-api.json").read_text())["port"] == base + 1
        finally:
            second.close()
    finally:
        first.close()


def test_all_ports_busy_returns_none(tmp_path):
    build_index(tmp_path)
    socks = []
    try:
        s0 = socket.socket()
        s0.bind(("127.0.0.1", 0))
        s0.listen()
        base = s0.getsockname()[1]
        socks.append(s0)
        for i in range(1, 5):
            s = socket.socket()
            try:
                s.bind(("127.0.0.1", base + i))
            except OSError:
                s.close()
                pytest.skip("neighbour port not free on this machine")
            s.listen()
            socks.append(s)
        assert start_server(tmp_path, port=base) is None
    finally:
        for s in socks:
            s.close()


def test_missing_index_does_not_crash(tmp_path):
    server = start_server(tmp_path, port=0)
    try:
        status, body, _ = call(server, "/health")
        assert status == 200 and body["photos"] is None
        assert call(server, "/v1/stats")[0] == 503
    finally:
        server.close()


def test_readonly_connection_refuses_writes(api):
    tmp, _, _ = api
    conn = kc_queries.connect_ro(tmp)
    try:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("DELETE FROM photos")
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("INSERT INTO folders(path) VALUES ('x')")
    finally:
        conn.close()
    check = sqlite3.connect(tmp / "index.db")
    try:
        assert check.execute("SELECT COUNT(*) FROM photos").fetchone()[0] == len(PHOTOS)
    finally:
        check.close()


def test_close_removes_info_file(tmp_path):
    build_index(tmp_path)
    server = start_server(tmp_path, port=0)
    assert (tmp_path / "kc-api.json").exists()
    server.close()
    assert not (tmp_path / "kc-api.json").exists()
