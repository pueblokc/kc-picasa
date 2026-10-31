"""Background renderer for KC Projects."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Property, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices

CREATE_NO_WINDOW = 0x08000000
PROJECTS = {
    "reel": ("Photo Reel", ".mp4"), "animate": ("Animated Loop", ".gif"),
    "frames": ("Frame - Card", ".jpg"), "calendar": ("Photo Calendar", ".pdf"),
    "photobook": ("Photo Book", ".pdf"), "beforeafter": ("Before - After", ".mp4"),
    "mosaic": ("Photo Mosaic", ".jpg"), "yearreview": ("Year in Review", ".mp4"),
}


def unique_path(folder: Path, stem: str, suffix: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{stem}{suffix}"
    number = 2
    while path.exists():
        path = folder / f"{stem}-{number}{suffix}"
        number += 1
    return path


def project_argv(project: str, output: Path, photos: list[str], options: dict) -> list[str]:
    if project not in PROJECTS:
        raise ValueError(f"Unknown project: {project}")
    argv = [sys.executable, "-m", "picasapy.kc_create", project, "--out", str(output)]
    permitted = {
        "reel": ("size", "title", "music"), "animate": ("fps", "width"),
        "frames": ("style", "caption"), "calendar": ("year",),
        "photobook": ("title",), "beforeafter": ("mode",),
        "mosaic": ("cols",), "yearreview": ("year", "size", "music"),
    }[project]
    for key in permitted:
        value = options.get(key)
        if value is not None and value != "":
            argv.extend((f"--{key}", str(value)))
    return [*argv, *photos]


def photos_for_year(index_db: Path, year: int) -> list[str]:
    uri = index_db.resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        rows = conn.execute(
            "SELECT f.path, p.name FROM photos p JOIN folders f ON f.id=p.folder_id "
            "WHERE p.kind != 'video' AND strftime('%Y', p.mtime_ns / 1000000000, 'unixepoch')=?",
            (str(year),),
        ).fetchall()
    return [str(Path(folder) / name) for folder, name in rows]


class KcProjectsController(QObject):
    message = Signal(str)
    changed = Signal()
    _finished = Signal(str, str)

    def __init__(self, data_dir: str | Path, parent: QObject | None = None,
                 output_dir: Path | None = None) -> None:
        super().__init__(parent)
        self._data_dir = Path(data_dir)
        self._output_dir = output_dir or Path.home() / "Pictures" / "KC Projects"
        self._busy = False
        self._output = ""
        self._process: subprocess.Popen | None = None
        self._cancelled = False
        self._finished.connect(self._on_finished)

    @Property(bool, notify=changed)
    def busy(self) -> bool:
        return self._busy

    @Property(str, notify=changed)
    def output(self) -> str:
        return self._output

    @Slot(str, "QVariantList", "QVariantMap")
    def create(self, project: str, photos: list[str], options: dict) -> None:
        if self._busy:
            self.message.emit("A KC project is already rendering")
            return
        if project not in PROJECTS:
            self.message.emit("Unknown KC project")
            return
        if project == "yearreview":
            try:
                photos = photos_for_year(self._data_dir / "index.db", int(options.get("year") or datetime.now().year))
            except (OSError, sqlite3.Error, ValueError) as exc:
                self.message.emit(f"Could not read library: {exc}")
                return
        options = dict(options)
        music = options.get("music", "")
        if isinstance(music, str) and music.startswith("file:"):
            options["music"] = QUrl(music).toLocalFile()
        photos = [str(p) for p in photos if p]
        if not photos:
            self.message.emit("No photos available for this project")
            return
        title, suffix = PROJECTS[project]
        output = unique_path(self._output_dir, title, suffix)
        argv = project_argv(project, output, photos, options)
        self._busy = True
        self._cancelled = False
        self._output = ""
        self.changed.emit()
        self.message.emit(f"Rendering {title}...")
        threading.Thread(target=self._worker, args=(argv, output), daemon=True).start()

    def _worker(self, argv: list[str], output: Path) -> None:
        try:
            self._process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                             text=True, creationflags=CREATE_NO_WINDOW if os.name == "nt" else 0)
            stdout, stderr = self._process.communicate()
            if self._cancelled:
                self._finished.emit("KC project cancelled", "")
            elif self._process.returncode:
                self._finished.emit("KC project failed: " + (stderr or stdout)[-300:], "")
            elif output.is_file():
                self._finished.emit("KC project finished", str(output))
            else:
                self._finished.emit("KC project did not create an output file", "")
        except OSError as exc:
            self._finished.emit(f"KC project failed: {exc}", "")
        finally:
            self._process = None

    @Slot()
    def cancel(self) -> None:
        self._cancelled = True
        if self._process is not None:
            self._process.terminate()

    @Slot()
    def openFolder(self) -> None:
        if self._output:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(self._output).parent)))

    @Slot(str, str)
    def _on_finished(self, message: str, output: str) -> None:
        self._busy = False
        self._output = output
        self.changed.emit()
        self.message.emit(message)
