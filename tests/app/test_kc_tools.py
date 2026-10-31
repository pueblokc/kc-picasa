"""KC sharing never executes real device or link commands in tests."""

import json
import subprocess

from picasapy.app import kc_tools


def _config(tmp_path):
    path = tmp_path / "kc-share.json"
    path.write_text(json.dumps({"tailscale_exe": "tailscale", "phone_device": "phone-test",
                                "drop_python": "python", "drop_script": "drop.py",
                                "secureshare_script": "share.py"}), encoding="utf-8")
    return path


def test_phone_and_drop_argv(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(kc_tools, "run_command", lambda argv: (calls.append(argv) or
                         subprocess.CompletedProcess(argv, 0, "", "")))
    controller = kc_tools.KcToolsController(config_file=_config(tmp_path))
    controller._share_worker("phone", ["a.jpg", "b.raw"])
    controller._share_worker("drop", ["movie.mp4"])
    assert calls == [["tailscale", "file", "cp", "a.jpg", "b.raw", "phone-test:"],
                     ["python", "drop.py", "movie.mp4", "--title", "KC Picasa",
                      "--project", "KC Picasa"]]


def test_link_extraction_and_missing_link(tmp_path, monkeypatch):
    calls = []
    copied = []
    messages = []
    controller = kc_tools.KcToolsController(config_file=_config(tmp_path))
    controller._copyLinks.connect(copied.append)
    controller._finished.connect(messages.append)
    monkeypatch.setattr(kc_tools, "run_command", lambda argv: (calls.append(argv) or
                         subprocess.CompletedProcess(argv, 0, ">>> SEND THIS LINK: https://example.test/x\n", "")))
    controller._share_worker("link", ["a.jpg", "b.raw"])
    assert calls == [["python", "share.py", "file", "a.jpg"],
                     ["python", "share.py", "file", "b.raw"]]
    assert copied == ["https://example.test/x\nhttps://example.test/x"]
    assert messages[-1] == "Link copied"


def test_windows_runner_hides_window(monkeypatch):
    seen = {}
    monkeypatch.setattr(kc_tools.sys, "platform", "win32")
    monkeypatch.setattr(kc_tools.subprocess, "run", lambda argv, **kwargs: seen.update(kwargs))
    kc_tools.run_command(["example.exe"])
    assert seen["creationflags"] == kc_tools.CREATE_NO_WINDOW
    assert seen["capture_output"] is True


def test_missing_config_disables_items(tmp_path):
    controller = kc_tools.KcToolsController(config_file=tmp_path / "missing.json")
    assert all(not controller.configured(action) for action in ("phone", "drop", "link"))
