from datetime import date

from picasapy.app.kc_memories import on_this_day
from picasapy.index import open_index


def test_on_this_day_uses_override_and_earlier_years(tmp_path):
    index = tmp_path / "index.db"
    with open_index(index) as conn:
        conn.execute("INSERT INTO folders(path) VALUES (?)", (str(tmp_path),))
        folder_id = conn.execute("SELECT id FROM folders").fetchone()[0]
        for name, taken, override in [
            ("old.jpg", "2021-10-31", None),
            ("override.jpg", "2020-01-01", "2023-10-31"),
            ("today.jpg", "2026-10-31", None),
            ("other.jpg", "2022-10-30", None),
        ]:
            conn.execute(
                "INSERT INTO photos(folder_id,name,kind,size,mtime_ns,taken_at,taken_at_override) "
                "VALUES (?,?,?,?,?,?,?)",
                (folder_id, name, "photo", 1, 1, taken, override),
            )
        conn.commit()
    memories = on_this_day(index, date(2026, 10, 31))
    assert [p["name"] for p in memories] == ["override.jpg", "old.jpg"]
    assert [p["yearsAgo"] for p in memories] == [3, 5]
    assert all(p["folder"] == str(tmp_path) for p in memories)


def test_on_this_day_missing_index(tmp_path):
    assert on_this_day(tmp_path / "missing.db", date(2026, 10, 31)) == []
