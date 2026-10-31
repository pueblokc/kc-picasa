"""KC commands shared by the menu bar and photo context menu."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtGui import QGuiApplication

CREATE_NO_WINDOW = 0x08000000
CONFIG_FIELDS = ("tailscale_exe", "phone_device", "drop_python", "drop_script", "secureshare_script")


def config_path() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local" / "share"))) / "PicasaPy" / "kc-share.json"


def read_config(path: Path | None = None) -> dict[str, str]:
    try:
        data = json.loads((path or config_path()).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {key: value for key, value in data.items() if key in CONFIG_FIELDS and isinstance(value, str) and value}


def run_command(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, capture_output=True, text=True, check=False,
                          creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0)


def _run_checked(argv: list[str]) -> subprocess.CompletedProcess[str]:
    result = run_command(argv)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout or "Command failed").strip()[-300:])
    return result


def _field(text: str, label: str) -> str:
    """Value after ``label`` on the first line that contains it (``  Slug:   abc`` -> ``abc``)."""
    for line in text.splitlines():
        if label in line:
            return line.split(label, 1)[1].strip()
    return ""


class KcToolsController(QObject):
    """The worker emits only a Qt signal; it never updates QML from its thread."""

    message = Signal(str)
    busyChanged = Signal()

    def __init__(self, parent: QObject | None = None, config_file: Path | None = None) -> None:
        super().__init__(parent)
        self._config_file = config_file
        self._busy = False

    @Slot(str, result=bool)
    def configured(self, action: str) -> bool:
        cfg = read_config(self._config_file)
        needed = {"phone": ("tailscale_exe", "phone_device"),
                  "drop": ("drop_python", "drop_script"),
                  "link": ("secureshare_script",)}.get(action, ())
        return bool(needed) and all(cfg.get(key) for key in needed)

    @Slot(str, "QVariantList")
    def share(self, action: str, paths: list[str]) -> None:
        paths = [str(path) for path in paths if path]
        if not paths:
            self.message.emit("Select a photo first")
            return
        if self._busy:
            self.message.emit("KC share is already running")
            return
        if not self.configured(action):
            self.message.emit("Set up in kc-share.json")
            return
        self._busy = True
        self.busyChanged.emit()
        label = {"phone": "phone", "drop": "Drop", "link": "Share Link"}[action]
        self.message.emit(f"Sending {len(paths)} photos to {label}...")
        threading.Thread(target=self._share_worker, args=(action, paths), daemon=True).start()

    def _share_worker(self, action: str, paths: list[str]) -> None:
        cfg = read_config(self._config_file)
        try:
            if action == "phone":
                commands = [[cfg["tailscale_exe"], "file", "cp", *paths, cfg["phone_device"] + ":"]]
            elif action == "drop":
                commands = [[cfg["drop_python"], cfg["drop_script"], *paths,
                             "--title", "KC Picasa", "--project", "KC Picasa"]]
            else:
                commands = []
            links = []
            for command in commands:
                _run_checked(command)
            if action == "link":
                links.append(self._secureshare_link(cfg, paths))
            if links:
                self._copyLinks.emit("\n".join(links))
            self._finished.emit("Link copied" if links else "Sent")
        except (OSError, KeyError, RuntimeError) as error:
            self._finished.emit(f"KC share failed: {error}")

    @staticmethod
    def _secureshare_link(cfg: dict, paths: list[str]) -> str:
        """One share for the whole selection: create it, upload each file, return the one-tap link."""
        script = [cfg.get("drop_python", sys.executable), cfg["secureshare_script"]]
        title = f"KC Picasa - {len(paths)} photo{'s' if len(paths) != 1 else ''}"
        created = _run_checked([*script, "file", title]).stdout
        slug = _field(created, "Slug:")
        if not slug:
            raise RuntimeError("Share Link: no slug came back")
        for path in paths:
            _run_checked([*script, "upload", slug, path])
        info = _run_checked([*script, "get", slug]).stdout
        link = next((m.group(0) for line in info.splitlines() if "SEND THIS LINK" in line
                     for m in [re.search(r"https://\S+", line)] if m), "")
        return link or _field(info, "URL:") or _field(created, "URL:")

    _finished = Signal(str)
    _copyLinks = Signal(str)

    @Slot(str)
    def _finish_on_ui(self, message: str) -> None:
        self._busy = False
        self.busyChanged.emit()
        self.message.emit(message)

    @Slot(str)
    def _copy_on_ui(self, links: str) -> None:
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(links)

    def connect_worker_signals(self) -> None:
        self._finished.connect(self._finish_on_ui)
        self._copyLinks.connect(self._copy_on_ui)
