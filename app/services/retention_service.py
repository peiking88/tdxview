"""
Data retention and archival service.

Manages data lifecycle: automatic archiving of old Parquet files and
cleanup of expired cache entries based on configured retention policies.
"""

import json
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.config.settings import get_settings
from app.data.database import DatabaseManager
from app.data.parquet_manager import ParquetManager


class RetentionService:
    """Enforces data retention policies: archive old data, purge expired caches."""

    def __init__(self):
        settings = get_settings()
        self._parquet_dir = Path(settings.database.parquet_dir)
        self._cache_dir = Path(settings.database.cache_dir)
        self._archive_dir = self._parquet_dir.parent / "archive"
        self._db = DatabaseManager()
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

    def scan_parquet_files(self) -> List[Dict[str, Any]]:
        """Scan Parquet directory and return file metadata list.

        Each entry contains: path, symbol, size_bytes, modified_time, age_days.
        """
        files = []
        if not self._parquet_dir.exists():
            return files

        now = time.time()
        for pq in self._parquet_dir.rglob("*.parquet"):
            stat = pq.stat()
            rel = pq.relative_to(self._parquet_dir)
            parts = rel.parts
            symbol = pq.stem
            date_str = None
            if len(parts) > 1:
                date_str = str(Path(*parts[:-1]))
            age_days = (now - stat.st_mtime) / 86400
            files.append({
                "path": str(pq),
                "relative_path": str(rel),
                "symbol": symbol,
                "date_partition": date_str,
                "size_bytes": stat.st_size,
                "modified_time": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "age_days": round(age_days, 2),
            })
        return files

    def get_archive_candidates(self) -> List[Dict[str, Any]]:
        """Return files older than archive_threshold_days."""
        all_files = self.scan_parquet_files()
        return [f for f in all_files if f["age_days"] > self._archive_threshold_days]

    def get_purge_candidates(self) -> List[Dict[str, Any]]:
        """Return files older than retention_days (should be deleted)."""
        all_files = self.scan_parquet_files()
        return [f for f in all_files if f["age_days"] > self._retention_days]

    def archive_files(
        self,
        files: Optional[List[Dict[str, Any]]] = None,
        compress: bool = True,
    ) -> Dict[str, Any]:
        """Archive Parquet files to the archive directory.

        If *files* is None, archives all files older than archive_threshold_days.
        Returns summary with archived count and total bytes.
        """
        candidates = files or self.get_archive_candidates()
        if not candidates:
            return {"archived_count": 0, "total_bytes": 0, "details": []}

        self._archive_dir.mkdir(parents=True, exist_ok=True)
        archived = []
        total_bytes = 0

        for entry in candidates:
            src = Path(entry["path"])
            if not src.exists():
                continue
            rel = Path(entry["relative_path"])
            dst = self._archive_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)

            if not dst.exists():
                shutil.copy2(src, dst)
                total_bytes += entry["size_bytes"]
                archived.append({
                    "source": str(src),
                    "destination": str(dst),
                    "size_bytes": entry["size_bytes"],
                })

        return {
            "archived_count": len(archived),
            "total_bytes": total_bytes,
            "details": archived,
        }

    def purge_expired_files(
        self,
        files: Optional[List[Dict[str, Any]]] = None,
        archive_first: bool = True,
    ) -> Dict[str, Any]:
        """Delete Parquet files older than retention_days.

        If *archive_first* is True, files are archived before deletion.
        Returns summary with purged count and total bytes freed.
        """
        candidates = files or self.get_purge_candidates()
        if not candidates:
            return {"purged_count": 0, "total_bytes_freed": 0, "details": []}

        if archive_first:
            self.archive_files(candidates)

        purged = []
        total_freed = 0

        for entry in candidates:
            src = Path(entry["path"])
            if src.exists():
                size = src.stat().st_size
                src.unlink()
                total_freed += size
                purged.append({
                    "path": str(src),
                    "size_bytes_freed": size,
                })

        return {
            "purged_count": len(purged),
            "total_bytes_freed": total_freed,
            "details": purged,
        }

    def cleanup_cache(self) -> Dict[str, Any]:
        """Remove expired disk cache entries."""
        queries_dir = self._cache_dir / "queries"
        if not queries_dir.exists():
            return {"removed_count": 0, "total_bytes_freed": 0}

        now = time.time()
        removed = 0
        total_freed = 0

        for json_file in queries_dir.rglob("*.json"):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                if data.get("expires_at") and now > data["expires_at"]:
                    size = json_file.stat().st_size
                    json_file.unlink()
                    removed += 1
                    total_freed += size
            except Exception:
                continue

        return {
            "removed_count": removed,
            "total_bytes_freed": total_freed,
        }

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
        parquet_size = sum(
            f.stat().st_size for f in self._parquet_dir.rglob("*.parquet")
            if self._parquet_dir.exists()
        )
        archive_size = sum(
            f.stat().st_size for f in self._archive_dir.rglob("*.parquet")
            if self._archive_dir.exists()
        )
        cache_size = sum(
            f.stat().st_size for f in self._cache_dir.rglob("*")
            if self._cache_dir.exists() and f.is_file()
        )
        db_path = Path(get_settings().database.duckdb_path)
        db_size = db_path.stat().st_size if db_path.exists() else 0

        return {
            "parquet_bytes": parquet_size,
            "archive_bytes": archive_size,
            "cache_bytes": cache_size,
            "database_bytes": db_size,
            "total_bytes": parquet_size + archive_size + cache_size + db_size,
        }

    def run_full_retention(self) -> Dict[str, Any]:
        """Execute the full retention pipeline: archive → purge → cache cleanup → log cleanup.

        Returns a combined summary of all operations.
        """
        archive_result = self.archive_files()
        purge_result = self.purge_expired_files(archive_first=False)
        cache_result = self.cleanup_cache()
        log_result = self.cleanup_system_logs()
        storage = self.get_storage_stats()

        return {
            "timestamp": datetime.now().isoformat(),
            "archive": archive_result,
            "purge": purge_result,
            "cache_cleanup": cache_result,
            "log_cleanup": log_result,
            "storage_after": storage,
        }
