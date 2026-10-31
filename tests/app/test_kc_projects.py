from pathlib import Path

from picasapy.app.kc_projects import KcProjectsController, project_argv, unique_path


def test_unique_path_never_overwrites(tmp_path):
    (tmp_path / "Photo Reel.mp4").write_bytes(b"old")
    (tmp_path / "Photo Reel-2.mp4").write_bytes(b"old")
    assert unique_path(tmp_path, "Photo Reel", ".mp4") == tmp_path / "Photo Reel-3.mp4"


def test_reel_argv_contains_options_and_paths(tmp_path):
    output = tmp_path / "reel.mp4"
    argv = project_argv("reel", output, ["a.jpg", "b.jpg"], {"size": "4:5", "title": "Trip"})
    assert argv[1:4] == ["-m", "picasapy.kc_create", "reel"]
    assert argv[-2:] == ["a.jpg", "b.jpg"]
    assert argv[argv.index("--out") + 1] == str(output)
    assert argv[argv.index("--size") + 1] == "4:5"


def test_cancel_terminates_process(tmp_path):
    controller = KcProjectsController(tmp_path, output_dir=tmp_path)

    class Process:
        terminated = False

        def terminate(self):
            self.terminated = True

    process = Process()
    controller._process = process
    controller.cancel()
    assert controller._cancelled
    assert process.terminated


def test_no_selection_does_not_start(tmp_path, monkeypatch):
    controller = KcProjectsController(tmp_path, output_dir=tmp_path)
    messages = []
    controller.message.connect(messages.append)
    monkeypatch.setattr("picasapy.app.kc_projects.threading.Thread", lambda **kwargs: 1 / 0)
    controller.create("reel", [], {})
    assert not controller.busy
    assert "No photos" in messages[-1]
