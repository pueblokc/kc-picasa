from datetime import datetime, timedelta
import sqlite3
from contextlib import closing

import pytest

from picasapy.app.kc_backup import (
    apply_pending_restore, automatic_backup, backup_files, backup_index,
    stage_restore, verify_index,
)
from picasapy.index import open_index


def _index(path, value):
    with open_index(path) as conn:
        conn.execute("INSERT INTO folders(path) VALUES (?)", (value,))
        conn.commit()


def _folder(path):
    with closing(sqlite3.connect(path)) as conn:
        return conn.execute("SELECT path FROM folders").fetchone()[0]


def test_online_backup_valid_and_automatic_interval(tmp_path):
    _index(tmp_path / "index.db", "first")
    backup = backup_index(tmp_path)
    verify_index(backup)
    assert _folder(backup) == "first"
    assert automatic_backup(tmp_path) is None


def test_pruning_keeps_newest_fourteen(tmp_path):
    _index(tmp_path / "index.db", "first")
    start = datetime(2026, 10, 1)
    for day in range(16):
        backup_index(tmp_path, start + timedelta(days=day))
    assert len(backup_files(tmp_path)) == 14
    assert backup_files(tmp_path)[0].name == "index-20261016-000000.db"


def test_restore_stages_then_swaps_and_retains_previous(tmp_path):
    index = tmp_path / "index.db"
    _index(index, "before")
    backup = backup_index(tmp_path)
    with open_index(index) as conn:
        conn.execute("UPDATE folders SET path='after'")
        conn.commit()
    stage_restore(tmp_path, backup)
    assert _folder(index) == "after"
    previous = apply_pending_restore(tmp_path, datetime(2026, 10, 31))
    assert _folder(index) == "before"
    assert _folder(previous) == "after"


def test_corrupt_backup_is_refused(tmp_path):
    _index(tmp_path / "index.db", "first")
    backup = backup_index(tmp_path)
    backup.write_bytes(b"not sqlite")
    with pytest.raises((sqlite3.DatabaseError, ValueError)):
        stage_restore(tmp_path, backup)
    assert not (tmp_path / "index.db.restore-pending").exists()
