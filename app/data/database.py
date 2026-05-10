"""
DuckDB database manager.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import duckdb

from app.config.settings import get_settings


class DatabaseManager:
    """Manages DuckDB connections and common query operations."""

    def __init__(self, db_path: Optional[str] = None):
        settings = get_settings()
        self._db_path = db_path or settings.database.duckdb_path
        self._conn: Optional[duckdb.DuckDBPyConnection] = None

    @property
    def connection(self) -> duckdb.DuckDBPyConnection:
        if self._conn is None:
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
            self._conn = duckdb.connect(self._db_path)
        return self._conn

    def execute(self, sql: str, params: Optional[list] = None) -> Any:
        return self.connection.execute(sql, params or [])

    def fetch_one(self, sql: str, params: Optional[list] = None) -> Optional[tuple]:
        return self.execute(sql, params).fetchone()

    def fetch_all(self, sql: str, params: Optional[list] = None) -> List[tuple]:
        return self.execute(sql, params).fetchall()

    def fetch_df(self, sql: str, params: Optional[list] = None) -> Any:
        return self.execute(sql, params).df()

    def close(self):
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
