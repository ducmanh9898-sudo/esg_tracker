from pathlib import Path
import sqlite3

from src.database import initialize_database


def test_schema_has_required_tables(tmp_path: Path):
    db = tmp_path / "test.db"
    initialize_database(db)
    with sqlite3.connect(db) as connection:
        names = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"companies","documents","passages","claims","metrics","evidence_links","rule_results","topic_scores"} <= names

