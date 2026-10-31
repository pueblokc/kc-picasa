"""Verified SQLite index backups and a restart-safe restore stage."""

from __future__ import annotations

import os
import shutil
import sqlite3
import threading
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot


def _stamp(now: datetime | None = None) -> str:
    return (now or datetime.now()).strftime("%Y%m%d-%H%M%S")


def backup_files(data_dir: Path) -> list[Path]:
    return sorted((data_dir / "kc-backups").glob("index-*.db"), reverse=True)


def verify_index(path: Path) -> None:
    with closing(sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)) as conn:
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Index integrity check failed")


def backup_index(data_dir: Path, now: datetime | None = None, keep: int = 14) -> Path:
    source = data_dir / "index.db"
    if not source.exists():
        raise FileNotFoundError(source)
    directory = data_dir / "kc-backups"
    directory.mkdir(parents=True, exist_ok=True)
    dest = directory / f"index-{_stamp(now)}.db"
    temp = dest.with_suffix(".db.tmp")
    try:
        with closing(sqlite3.connect(f"{source.resolve().as_uri()}?mode=ro", uri=True)) as src:
            with closing(sqlite3.connect(temp)) as target:
                src.backup(target)
        verify_index(temp)
        os.replace(temp, dest)
    finally:
        temp.unlink(missing_ok=True)
    for old in backup_files(data_dir)[keep:]:
        old.unlink()
    return dest


def automatic_backup(data_dir: Path, now: datetime | None = None) -> Path | None:
    now = now or datetime.now()
    newest = backup_files(data_dir)
    if newest and now - datetime.fromtimestamp(newest[0].stat().st_mtime) < timedelta(hours=24):
        return None
    return backup_index(data_dir, now)


def stage_restore(data_dir: Path, backup: Path) -> Path:
    backup = backup.resolve()
    if backup not in [p.resolve() for p in backup_files(data_dir)]:
        raise ValueError("Choose a KC index backup")
    verify_index(backup)
    pending = data_dir / "index.db.restore-pending"
    temp = pending.with_suffix(".tmp")
    try:
        shutil.copy2(backup, temp)
        verify_index(temp)
        os.replace(temp, pending)
    finally:
        temp.unlink(missing_ok=True)
    return pending


def apply_pending_restore(data_dir: Path, now: datetime | None = None) -> Path | None:
    pending = data_dir / "index.db.restore-pending"
    if not pending.exists():
        return None
    verify_index(pending)
    current = data_dir / "index.db"
    previous = data_dir / f"index.db.before-restore-{_stamp(now)}"
    if current.exists():
        os.replace(current, previous)
    try:
        os.replace(pending, current)
    except OSError:
        if previous.exists():
            os.replace(previous, current)
        raise
    for extension in ("-wal", "-shm"):
        sidecar = data_dir / f"index.db{extension}"
        if sidecar.exists():
            os.replace(sidecar, data_dir / f"{previous.name}{extension}")
    return previous if previous.exists() else None


class KcBackupController(QObject):
    message = Signal(str)
    _result = Signal(str)

    def __init__(self, data_dir: Path, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._data_dir = data_dir
        self._result.connect(self.message.emit)

    def _work(self, action, label: str) -> None:
        self.message.emit(label)

        def runner():
            try:
                action()
                self._result.emit("Index backup ready" if label.startswith("Backing") else "Restore ready. Restart now.")
            except Exception as exc:
                self._result.emit(f"KC backup failed: {exc}")

        threading.Thread(target=runner, daemon=True).start()

    @Slot()
    def automatic(self) -> None:
        def runner():
            try:
                automatic_backup(self._data_dir)
            except Exception as exc:
                self._result.emit(f"Automatic index backup failed: {exc}")

        threading.Thread(target=runner, daemon=True).start()

    @Slot()
    def backupNow(self) -> None:  # noqa: N802
        self._work(lambda: backup_index(self._data_dir), "Backing up index...")

    @Slot(result="QVariantList")
    def backups(self) -> list[dict]:
        return [{"path": str(p), "name": p.name, "size": p.stat().st_size,
                 "modified": datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")}
                for p in backup_files(self._data_dir)]

    @Slot(str)
    def restore(self, path: str) -> None:
        self._work(lambda: stage_restore(self._data_dir, Path(path)), "Preparing restore...")
