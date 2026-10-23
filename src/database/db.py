import sqlite3
from pathlib import Path

import pandas as pd

from src.paths import DATABASE_PATH, SCHEMA_PATH


def connect(path: Path | str = DATABASE_PATH) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database(path: Path | str = DATABASE_PATH) -> Path:
    path = Path(path)
    with connect(path) as connection:
        connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    return path


def fetch_df(query: str, params=(), path: Path | str = DATABASE_PATH) -> pd.DataFrame:
    with connect(path) as connection:
        return pd.read_sql_query(query, connection, params=params)

