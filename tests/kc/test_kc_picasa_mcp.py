"""KC Picasa MCP server: tool functions called directly, plus the stdio protocol."""

from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest
from kc_index_fixture import PHOTOS, TODAY_MD, build_index

from picasapy.app.kc_api import start_server

MCP_FILE = Path(__file__).resolve().parents[2] / "kc" / "mcp" / "kc_picasa_mcp.py"


@pytest.fixture
def mcp(tmp_path):
    spec = importlib.util.spec_from_file_location("kc_picasa_mcp_under_test", MCP_FILE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    ids = build_index(tmp_path)
    mod.set_data_dir(tmp_path)
    return mod, tmp_path, ids


def test_search_photos(mcp):
    m, _, _ = mcp
    assert [p["name"] for p in m.search_photos("beach")] == ["beach_sunset.jpg"]
    assert [p["name"] for p in m.search_photos('"wow"')] == ["birthday cake.jpg"]
    assert m.search_photos("") == []
    assert len(m.search_photos("jpg", 2)) == 2
    assert m.search_photos("x'; DROP TABLE photos;--") == []


def test_on_this_day_and_date(mcp):
    m, _, _ = mcp
    today = m.on_this_day()
    assert today["date"] == TODAY_MD and [y["year"] for y in today["years"]] == [2025, 2024]
    assert [y["year"] for y in m.on_this_day("07-04")["years"]] == [2023]
    assert [p["name"] for p in m.photos_on_date("2024-06-01")] == ["hike_peak.jpg"]


def test_lists_stats_and_detail(mcp):
    m, _, ids = mcp
    assert len(m.list_folders()) == 1
    assert m.list_albums()[0]["name"] == "Summer"
    assert m.list_people() == [{"name": "Alex", "faces": 1, "photos": 1}]
    assert m.photo_stats()["photos"] == len(PHOTOS) - 1
    assert m.get_photo(ids["hike_peak.jpg"])["albums"] == ["Summer"]
    with pytest.raises(Exception, match="no photo"):
        m.get_photo(99999)


def test_call_tool_wraps_results_and_errors(mcp):
    m, _, _ = mcp
    res = m.call_tool("search_photos", {"q": "beach", "limit": 5})
    assert "isError" not in res
    assert json.loads(res["content"][0]["text"])[0]["name"] == "beach_sunset.jpg"
    assert m.call_tool("on_this_day", {"month_day": "99-99"})["isError"] is True
    assert m.call_tool("nope", {})["isError"] is True
    assert m.call_tool("get_photo", {"id": 99999})["isError"] is True


def test_works_without_app_and_hides_run_action(mcp):
    m, _, _ = mcp
    names = [t["name"] for t in m.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})["result"]["tools"]]
    assert "search_photos" in names and "run_action" not in names
    res = m.call_tool("run_action", {"action": "x", "paths": []})
    assert res["isError"] is True and "not running" in res["content"][0]["text"]


def test_run_action_via_running_app(mcp):
    m, tmp, _ = mcp

    class Actions:
        def run(self, action, paths):
            return {"got": [action, paths]}

    server = start_server(tmp, port=0, actions=Actions())
    try:
        names = [t["name"] for t in m.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})["result"]["tools"]]
        assert "run_action" in names
        assert m.run_action("share", ["a.jpg"]) == {"ok": True, "result": {"got": ["share", ["a.jpg"]]}}
        (tmp / "kc-api-token").write_text("tok", encoding="utf-8")
        assert m.run_action("share", [])["ok"] is True  # token is picked up from the data dir
    finally:
        server.close()


def test_run_action_501_reported(mcp):
    m, tmp, _ = mcp
    server = start_server(tmp, port=0)
    try:
        res = m.call_tool("run_action", {"action": "share", "paths": []})
        assert res["isError"] is True and "501" in res["content"][0]["text"]
    finally:
        server.close()


def test_handshake_in_process(mcp):
    m, _, _ = mcp
    init = m.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert init["result"]["serverInfo"]["name"] == "kc-picasa"
    assert m.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    assert m.handle({"jsonrpc": "2.0", "id": 2, "method": "bogus"})["error"]["code"] == -32601
    out = io.StringIO()
    m.serve(io.StringIO("not json\n" + json.dumps({"jsonrpc": "2.0", "id": 3, "method": "ping"}) + "\n"), out)
    lines = [json.loads(x) for x in out.getvalue().splitlines()]
    assert lines[0]["error"]["code"] == -32700 and lines[1] == {"jsonrpc": "2.0", "id": 3, "result": {}}


def test_stdio_subprocess_end_to_end(tmp_path):
    build_index(tmp_path)
    msgs = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
         "params": {"name": "search_photos", "arguments": {"q": "café"}}},
    ]
    proc = subprocess.run(
        [sys.executable, "-I", str(MCP_FILE), "--data-dir", str(tmp_path)],
        input="\n".join(json.dumps(m) for m in msgs) + "\n",
        capture_output=True, text=True, encoding="utf-8", timeout=60,
        creationflags=0x08000000 if sys.platform == "win32" else 0,
    )
    assert proc.returncode == 0, proc.stderr
    replies = [json.loads(x) for x in proc.stdout.splitlines()]
    assert [r["id"] for r in replies] == [1, 2]
    found = json.loads(replies[1]["result"]["content"][0]["text"])
    assert [p["name"] for p in found] == ["café_août.jpg"]


def test_default_data_dir_env_override(mcp, monkeypatch, tmp_path):
    m, _, _ = mcp
    monkeypatch.setenv("KC_PICASA_DATA", str(tmp_path / "x"))
    assert m.default_data_dir() == tmp_path / "x"
    monkeypatch.delenv("KC_PICASA_DATA")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "la"))
    assert m.default_data_dir() == tmp_path / "la" / "PicasaPy"
