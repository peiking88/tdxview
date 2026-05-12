"""
Data retention and archival service.

Manages data lifecycle: purging old data from DuckDB tables
based on configured retention policies.
"""

import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config.settings import get_settings
from app.data.database import DatabaseManager
from app.data.duckdb_store import _ALL_DATA_TABLES


class RetentionService:
    """Enforces data retention policies: purge old data from DuckDB."""

    def __init__(self, db: Optional[DatabaseManager] = None):
        self._db = db or DatabaseManager()
        self._retention_days = 365
        self._archive_threshold_days = 30

    def set_policy(
        self,
        retention_days: int = 365,
        archive_threshold_days: int = 30,
    ) -> None:
        """Configure retention policy parameters."""
        self._retention_days = retention_days
        self._archive_threshold_days = archive_threshold_days

    def scan_stored_data(self) -> List[Dict[str, Any]]:
        """Scan all data tables and return per-symbol metadata.

        Each entry contains: table, symbol, row_count, oldest_date.
        """
        results = []
        cutoff = (datetime.now() - timedelta(days=self._retention_days)).strftime("%Y-%m-%d")
        for table in _ALL_DATA_TABLES:
            try:
                rows = self._db.fetch_all(
                    f"SELECT symbol, count(*) as cnt, min(trade_date) as oldest "
                    f"FROM {table} GROUP BY symbol",
                )
                for r in rows:
                    results.append({
                        "table": table,
                        "symbol": r[0],
                        "row_count": r[1],
                        "oldest_date": str(r[2]) if r[2] is not None else None,
                    })
            except Exception:
                continue
        return results

    def get_archive_candidates(self) -> List[Dict[str, Any]]:
        """Return data older than archive_threshold_days."""
        cutoff = (datetime.now() - timedelta(days=self._archive_threshold_days)).strftime("%Y-%m-%d")
        candidates = []
        for table in _ALL_DATA_TABLES:
            try:
                rows = self._db.fetch_all(
                    f"SELECT symbol, count(*) FROM {table} WHERE trade_date < ? GROUP BY symbol",
                    [cutoff],
                )
                for r in rows:
                    candidates.append({"table": table, "symbol": r[0], "old_rows": r[1]})
            except Exception:
                continue
        return candidates

    def get_purge_candidates(self) -> List[Dict[str, Any]]:
        """Return data older than retention_days."""
        cutoff = (datetime.now() - timedelta(days=self._retention_days)).strftime("%Y-%m-%d")
        candidates = []
        for table in _ALL_DATA_TABLES:
            try:
                rows = self._db.fetch_all(
                    f"SELECT symbol, count(*) FROM {table} WHERE trade_date < ? GROUP BY symbol",
                    [cutoff],
                )
                for r in rows:
                    candidates.append({"table": table, "symbol": r[0], "old_rows": r[1]})
            except Exception:
                continue
        return candidates

    def archive_files(self, files=None, compress=True) -> Dict[str, Any]:
        """Archive is now a no-op — data lives in DuckDB, archived via backup."""
        return {"archived_count": 0, "total_bytes": 0, "details": []}

    def purge_expired_data(self, archive_first: bool = True) -> Dict[str, Any]:
        """Delete data older than retention_days from DuckDB tables."""
        cutoff = (datetime.now() - timedelta(days=self._retention_days)).strftime("%Y-%m-%d")
        purged = []

        for table in _ALL_DATA_TABLES:
            try:
                row = self._db.fetch_one(
                    f"SELECT count(*) FROM {table} WHERE trade_date < ?", [cutoff],
                )
                if row and row[0] > 0:
                    count = row[0]
                    self._db.execute(
                        f"DELETE FROM {table} WHERE trade_date < ?", [cutoff],
                    )
                    purged.append({"table": table, "rows_deleted": count})
            except Exception:
                continue

        self._db.connection.commit()
        return {
            "purged_count": len(purged),
            "details": purged,
        }

    # Keep backward-compatible alias
    def purge_expired_files(self, files=None, archive_first=True):
        return self.purge_expired_data(archive_first=archive_first)

    def cleanup_system_logs(self, max_age_days: int = 30) -> Dict[str, Any]:
        """Remove system log entries older than max_age_days from DuckDB."""
        cutoff = (datetime.now() - timedelta(days=max_age_days)).isoformat()
        try:
            self._db.execute(
                "DELETE FROM system_logs WHERE created_at < ?", [cutoff]
            )
            self._db.execute(
                "DELETE FROM audit_logs WHERE created_at < ?", [cutoff]
            )
            self._db.connection.commit()
            return {"status": "ok", "cutoff": cutoff}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def get_storage_stats(self) -> Dict[str, Any]:
        """Return storage usage statistics."""
        db_path = Path(get_settings().database.duckdb_path)
        db_size = db_path.stat().st_size if db_path.exists() else 0

        # Count total rows across data tables
        data_rows = 0
        for table in _ALL_DATA_TABLES:
            try:
                row = self._db.fetch_one(f"SELECT count(*) FROM {table}")
                if row:
                    data_rows += row[0]
            except Exception:
                continue

        return {
            "data_rows": data_rows,
            "database_bytes": db_size,
        }

    # Backward-compatible alias
    def scan_parquet_files(self):
        return self.scan_stored_data()

    def run_full_retention(self) -> Dict[str, Any]:
        """Execute the full retention pipeline: purge → log cleanup."""
        purge_result = self.purge_expired_data()
        log_result = self.cleanup_system_logs()
        storage = self.get_storage_stats()

        return {
            "timestamp": datetime.now().isoformat(),
            "purge": purge_result,
            "log_cleanup": log_result,
            "storage_after": storage,
        }
