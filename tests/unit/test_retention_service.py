"""
RetentionService 单元测试 — 覆盖 SQL-based 数据清理。

- DuckDB 使用真实临时实例
"""

import json
import time
from pathlib import Path

import pytest

from app.data.database import DatabaseManager
from app.data.duckdb_store import DuckDBStore
from app.services.retention_service import RetentionService


@pytest.fixture
def db(tmp_path, test_settings):
    db_path = str(tmp_path / "test.duckdb")
    test_settings.database.duckdb_path = db_path

    mgr = DatabaseManager(db_path=db_path)
    # 创建 system_logs / audit_logs 表
    mgr.execute("""
        CREATE TABLE IF NOT EXISTS system_logs (
            id INTEGER PRIMARY KEY, level TEXT NOT NULL, module TEXT NOT NULL,
            message TEXT NOT NULL, details JSON, user_id INTEGER,
            ip_address TEXT, user_agent TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    mgr.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY, user_id INTEGER, action TEXT NOT NULL,
            resource_type TEXT NOT NULL, resource_id TEXT, details JSON,
            ip_address TEXT, user_agent TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    mgr.connection.commit()
    yield mgr
    mgr.close()


@pytest.fixture
def store(db):
    return DuckDBStore(db)


@pytest.fixture
def svc(db, test_settings):
    service = RetentionService(db=db)
    return service


class TestSetPolicy:
    def test_set_policy(self, svc):
        svc.set_policy(retention_days=180, archive_threshold_days=14)
        assert svc._retention_days == 180
        assert svc._archive_threshold_days == 14


class TestScanStoredData:
    def test_scan_empty(self, svc, store):
        result = svc.scan_stored_data()
        assert result == []

    def test_scan_with_data(self, svc, store):
        import pandas as pd
        df = pd.DataFrame({
            "date": ["2024-01-02"], "open": [10.0], "high": [10.5],
            "low": [9.8], "close": [10.3], "volume": [100000], "amount": [1000000.0],
        })
        store.save(df, "AAPL", data_type="history")
        result = svc.scan_stored_data()
        assert any(r["symbol"] == "AAPL" and r["table"] == "kline" for r in result)


class TestGetCandidates:
    def test_no_candidates_fresh_data(self, svc, store):
        import pandas as pd
        df = pd.DataFrame({
            "date": ["2026-01-02"], "open": [10.0], "high": [10.5],
            "low": [9.8], "close": [10.3], "volume": [100000], "amount": [1000000.0],
        })
        store.save(df, "AAPL", data_type="history")
        svc.set_policy(retention_days=365)
        candidates = svc.get_purge_candidates()
        assert len(candidates) == 0

    def test_candidates_old_data(self, svc, store):
        import pandas as pd
        df = pd.DataFrame({
            "date": ["2020-01-02"], "open": [10.0], "high": [10.5],
            "low": [9.8], "close": [10.3], "volume": [100000], "amount": [1000000.0],
        })
        store.save(df, "OLD", data_type="history")
        svc.set_policy(retention_days=365)
        candidates = svc.get_purge_candidates()
        assert len(candidates) >= 1
        assert any(c["symbol"] == "OLD" for c in candidates)


class TestPurgeExpiredData:
    def test_purge_nothing(self, svc):
        result = svc.purge_expired_data()
        assert result["purged_count"] == 0

    def test_purge_old_data(self, svc, store):
        import pandas as pd
        df = pd.DataFrame({
            "date": ["2020-01-02"], "open": [10.0], "high": [10.5],
            "low": [9.8], "close": [10.3], "volume": [100000], "amount": [1000000.0],
        })
        store.save(df, "OLD", data_type="history")
        svc.set_policy(retention_days=365)
        result = svc.purge_expired_data()
        assert result["purged_count"] >= 1

        # Verify data actually deleted
        loaded = store.load("OLD", data_type="history")
        assert loaded is None


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
    def test_storage_stats(self, svc, store):
        import pandas as pd
        df = pd.DataFrame({
            "date": ["2024-01-02"], "open": [10.0], "high": [10.5],
            "low": [9.8], "close": [10.3], "volume": [100000], "amount": [1000000.0],
        })
        store.save(df, "AAPL", data_type="history")
        result = svc.get_storage_stats()
        assert "data_rows" in result
        assert "database_bytes" in result
        assert result["data_rows"] >= 1


class TestRunFullRetention:
    def test_run_full(self, svc):
        result = svc.run_full_retention()
        assert "timestamp" in result
        assert "purge" in result
        assert "log_cleanup" in result
        assert "storage_after" in result
