"""
RetentionService additional unit tests covering uncovered lines.

原则：真实环境优先于 mock
- DuckDB 使用真实临时实例
- 文件系统操作使用真实临时目录
- get_settings 已由 conftest autouse patch 指向临时目录
"""

import json
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.services.retention_service import RetentionService


@pytest.fixture
def data_dirs(tmp_path, test_settings):
    parquet_dir = tmp_path / "parquet"
    parquet_dir.mkdir()
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    queries_dir = cache_dir / "queries"
    queries_dir.mkdir()
    db_path = str(tmp_path / "test.duckdb")

    originals = {
        "parquet_dir": test_settings.database.parquet_dir,
        "cache_dir": test_settings.database.cache_dir,
        "duckdb_path": test_settings.database.duckdb_path,
    }
    test_settings.database.parquet_dir = str(parquet_dir)
    test_settings.database.cache_dir = str(cache_dir)
    test_settings.database.duckdb_path = db_path

    yield {
        "parquet_dir": parquet_dir,
        "cache_dir": cache_dir,
        "queries_dir": queries_dir,
        "db_path": db_path,
    }

    test_settings.database.parquet_dir = originals["parquet_dir"]
    test_settings.database.cache_dir = originals["cache_dir"]
    test_settings.database.duckdb_path = originals["duckdb_path"]


@pytest.fixture
def svc(data_dirs):
    service = RetentionService()

    from app.data.database import DatabaseManager
    db = DatabaseManager(db_path=data_dirs["db_path"])
    db.execute("""
        CREATE TABLE IF NOT EXISTS system_logs (
            id INTEGER PRIMARY KEY,
            level TEXT NOT NULL,
            module TEXT NOT NULL,
            message TEXT NOT NULL,
            details JSON,
            user_id INTEGER,
            ip_address TEXT,
            user_agent TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            action TEXT NOT NULL,
            resource_type TEXT NOT NULL,
            resource_id TEXT,
            details JSON,
            ip_address TEXT,
            user_agent TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    db.connection.commit()
    service._db = db
    return service


class TestSetPolicy:
    def test_set_policy(self, svc):
        svc.set_policy(retention_days=180, archive_threshold_days=14)
        assert svc._retention_days == 180
        assert svc._archive_threshold_days == 14


class TestScanParquetFiles:
    def test_scan_empty_dir(self, svc, data_dirs):
        result = svc.scan_parquet_files()
        assert result == []

    def test_scan_nonexistent_dir(self, svc):
        svc._parquet_dir = Path("/nonexistent_xyz")
        result = svc.scan_parquet_files()
        assert result == []

    def test_scan_with_files(self, svc, data_dirs):
        pq_file = data_dirs["parquet_dir"] / "AAPL.parquet"
        pq_file.write_text("test_data_content_here")
        old_mtime = time.time() - 40 * 86400
        import os
        os.utime(str(pq_file), (old_mtime, old_mtime))

        result = svc.scan_parquet_files()
        assert len(result) == 1
        assert result[0]["symbol"] == "AAPL"
        assert result[0]["age_days"] > 30

    def test_scan_with_partition(self, svc, data_dirs):
        partition_dir = data_dirs["parquet_dir"] / "2024-01"
        partition_dir.mkdir()
        pq_file = partition_dir / "GOOGL.parquet"
        pq_file.write_text("test_data")
        old_mtime = time.time() - 40 * 86400
        import os
        os.utime(str(pq_file), (old_mtime, old_mtime))

        result = svc.scan_parquet_files()
        assert len(result) == 1
        assert result[0]["date_partition"] == "2024-01"


class TestGetCandidates:
    def test_get_archive_candidates(self, svc, data_dirs):
        pq_file = data_dirs["parquet_dir"] / "OLD.parquet"
        pq_file.write_text("old_data_content_here")
        old_mtime = time.time() - 60 * 86400
        import os
        os.utime(str(pq_file), (old_mtime, old_mtime))

        svc.set_policy(archive_threshold_days=30)
        candidates = svc.get_archive_candidates()
        assert len(candidates) == 1

    def test_get_purge_candidates(self, svc, data_dirs):
        pq_file = data_dirs["parquet_dir"] / "VERYOLD.parquet"
        pq_file.write_text("very_old_data_content_here")
        old_mtime = time.time() - 400 * 86400
        import os
        os.utime(str(pq_file), (old_mtime, old_mtime))

        svc.set_policy(retention_days=365)
        candidates = svc.get_purge_candidates()
        assert len(candidates) == 1


class TestArchiveFiles:
    def test_archive_no_candidates(self, svc):
        result = svc.archive_files(files=[])
        assert result["archived_count"] == 0

    def test_archive_files_success(self, svc, data_dirs):
        pq_file = data_dirs["parquet_dir"] / "TEST.parquet"
        pq_file.write_text("test_content_data")
        old_mtime = time.time() - 60 * 86400
        import os
        os.utime(str(pq_file), (old_mtime, old_mtime))

        files = svc.scan_parquet_files()
        result = svc.archive_files(files=files)
        assert result["archived_count"] == 1
        assert result["total_bytes"] > 0


class TestPurgeExpiredFiles:
    def test_purge_no_candidates(self, svc):
        result = svc.purge_expired_files(files=[])
        assert result["purged_count"] == 0

    def test_purge_files(self, svc, data_dirs):
        pq_file = data_dirs["parquet_dir"] / "DEL.parquet"
        pq_file.write_text("delete_this_data_content")
        assert pq_file.exists()

        files = [{"path": str(pq_file), "size_bytes": 100}]
        result = svc.purge_expired_files(files=files, archive_first=False)
        assert result["purged_count"] == 1
        assert not pq_file.exists()


class TestCleanupCache:
    def test_cleanup_no_dir(self, svc, data_dirs):
        data_dirs["queries_dir"].rmdir()
        result = svc.cleanup_cache()
        assert result["removed_count"] == 0

    def test_cleanup_expired_entries(self, svc, data_dirs):
        queries_dir = data_dirs["queries_dir"]
        expired = queries_dir / "expired.json"
        expired.write_text(json.dumps({"expires_at": time.time() - 100}))
        valid = queries_dir / "valid.json"
        valid.write_text(json.dumps({"expires_at": time.time() + 10000}))

        result = svc.cleanup_cache()
        assert result["removed_count"] == 1
        assert not expired.exists()
        assert valid.exists()


class TestCleanupSystemLogs:
    def test_cleanup_success(self, svc):
        from datetime import datetime, timedelta
        cutoff_time = (datetime.now() - timedelta(days=10)).isoformat()
        svc._db.execute(
            "INSERT INTO system_logs (id, level, module, message, created_at) VALUES (?, ?, ?, ?, ?)",
            [1, "INFO", "test", "old_log", cutoff_time],
        )
        svc._db.execute(
            "INSERT INTO system_logs (id, level, module, message) VALUES (?, ?, ?, ?)",
            [2, "INFO", "test", "new_log"],
        )
        svc._db.connection.commit()

        result = svc.cleanup_system_logs(max_age_days=30)
        assert result["status"] == "ok"
        assert "cutoff" in result

        remaining = svc._db.fetch_all("SELECT * FROM system_logs")
        assert len(remaining) >= 1

    def test_cleanup_error_no_table(self, svc):
        svc._db = type("FakeDB", (), {
            "execute": lambda self, *a, **kw: (_ for _ in ()).throw(Exception("no table")),
            "connection": type("FakeConn", (), {"commit": lambda self: None})(),
        })()
        result = svc.cleanup_system_logs()
        assert result["status"] == "error"


class TestGetStorageStats:
    def test_storage_stats(self, svc, data_dirs):
        pq = data_dirs["parquet_dir"] / "test.parquet"
        pq.write_text("data")
        result = svc.get_storage_stats()
        assert "parquet_bytes" in result
        assert "total_bytes" in result
        assert result["parquet_bytes"] > 0


class TestRunFullRetention:
    def test_run_full(self, svc, data_dirs):
        result = svc.run_full_retention()
        assert "timestamp" in result
        assert "archive" in result
        assert "purge" in result
        assert "cache_cleanup" in result
        assert "log_cleanup" in result
        assert "storage_after" in result
