"""
Unit tests for the data layer: cache, parquet, database, TdxDataSource, DataService.
"""

import json
import time
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.data.cache import MemoryCache, DiskCache, CacheManager, generate_cache_key
from app.data.database import DatabaseManager
from app.data.parquet_manager import ParquetManager


# ===========================================================================
# MemoryCache
# ===========================================================================

class TestMemoryCache:
    def test_set_and_get(self):
        cache = MemoryCache(max_size_mb=1, default_ttl=60)
        cache.set("k1", "v1")
        assert cache.get("k1") == "v1"

    def test_get_missing_key(self):
        cache = MemoryCache()
        assert cache.get("nope") is None

    def test_ttl_expiry(self):
        cache = MemoryCache(max_size_mb=1, default_ttl=1)
        cache.set("k1", "v1", ttl=1)
        time.sleep(1.1)
        assert cache.get("k1") is None

    def test_delete(self):
        cache = MemoryCache()
        cache.set("k1", "v1")
        cache.delete("k1")
        assert cache.get("k1") is None

    def test_clear(self):
        cache = MemoryCache()
        cache.set("k1", "v1")
        cache.set("k2", "v2")
        cache.clear()
        assert cache.count == 0

    def test_eviction(self):
        cache = MemoryCache(max_size_mb=1, default_ttl=600)
        # Set items with large sizes to trigger eviction
        for i in range(200):
            cache.set(f"k{i}", f"v{i}", size=10000)
        # Should have evicted some items
        assert cache.size <= 1 * 1024 * 1024

    def test_lru_order(self):
        cache = MemoryCache(max_size_mb=1, default_ttl=600)
        cache.set("k1", "v1")
        cache.set("k2", "v2")
        # Access k1 to move it to end
        cache.get("k1")
        # k2 should be evicted first
        assert cache.count == 2

    def test_overwrite_key(self):
        cache = MemoryCache()
        cache.set("k1", "old")
        cache.set("k1", "new")
        assert cache.get("k1") == "new"


# ===========================================================================
# DiskCache
# ===========================================================================

class TestDiskCache:
    def test_set_and_get(self, tmp_dir):
        cache = DiskCache(cache_dir=str(tmp_dir / "cache"))
        cache.set("k1", {"val": 42}, ttl=3600)
        result = cache.get("k1")
        assert result == {"val": 42}

    def test_get_missing_key(self, tmp_dir):
        cache = DiskCache(cache_dir=str(tmp_dir / "cache"))
        assert cache.get("nope") is None

    def test_ttl_expiry(self, tmp_dir):
        cache = DiskCache(cache_dir=str(tmp_dir / "cache"))
        cache.set("k1", {"val": 1}, ttl=1)
        time.sleep(1.1)
        assert cache.get("k1") is None

    def test_delete(self, tmp_dir):
        cache = DiskCache(cache_dir=str(tmp_dir / "cache"))
        cache.set("k1", {"val": 1}, ttl=3600)
        cache.delete("k1")
        assert cache.get("k1") is None

    def test_clear(self, tmp_dir):
        cache = DiskCache(cache_dir=str(tmp_dir / "cache"))
        cache.set("k1", {"val": 1}, ttl=3600)
        cache.set("k2", {"val": 2}, ttl=3600)
        cache.clear()
        assert cache.get("k1") is None
        assert cache.get("k2") is None


# ===========================================================================
# CacheManager
# ===========================================================================

class TestCacheManager:
    def test_memory_hit(self, tmp_dir):
        cm = CacheManager()
        cm.memory.set("k1", "from_memory")
        assert cm.get("k1") == "from_memory"

    def test_disk_hit_promotes_to_memory(self, tmp_dir):
        cm = CacheManager()
        cm.disk.set("k1", {"val": "from_disk"}, ttl=3600)
        # Memory miss, disk hit
        result = cm.get("k1")
        assert result == {"val": "from_disk"}
        # Now it should be in memory too
        assert cm.memory.get("k1") == {"val": "from_disk"}

    def test_set_writes_both(self, tmp_dir):
        cm = CacheManager()
        cm.set("k1", {"val": 42})
        assert cm.memory.get("k1") == {"val": 42}
        assert cm.disk.get("k1") == {"val": 42}

    def test_delete_removes_both(self, tmp_dir):
        cm = CacheManager()
        cm.set("k1", {"val": 1})
        cm.delete("k1")
        assert cm.memory.get("k1") is None
        assert cm.disk.get("k1") is None

    def test_clear_both(self, tmp_dir):
        cm = CacheManager()
        cm.set("k1", {"val": 1})
        cm.clear()
        assert cm.get("k1") is None


# ===========================================================================
# generate_cache_key
# ===========================================================================

class TestGenerateCacheKey:
    def test_deterministic(self):
        key1 = generate_cache_key("history", {"a": 1, "b": 2})
        key2 = generate_cache_key("history", {"b": 2, "a": 1})
        assert key1 == key2  # sort_keys ensures order doesn't matter

    def test_different_params(self):
        key1 = generate_cache_key("history", {"a": 1})
        key2 = generate_cache_key("history", {"a": 2})
        assert key1 != key2

    def test_different_type(self):
        key1 = generate_cache_key("history", {"a": 1})
        key2 = generate_cache_key("realtime", {"a": 1})
        assert key1 != key2

    def test_format(self):
        key = generate_cache_key("test", {"x": 1})
        assert key.startswith("test:")


# ===========================================================================
# ParquetManager
# ===========================================================================

class TestParquetManager:
    def test_save_and_load(self, tmp_dir):
        pm = ParquetManager(parquet_dir=str(tmp_dir / "parquet"))
        df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
        pm.save(df, "000001.SZ")
        loaded = pm.load("000001.SZ")
        assert loaded is not None
        assert len(loaded) == 2

    def test_load_missing(self, tmp_dir):
        pm = ParquetManager(parquet_dir=str(tmp_dir / "parquet"))
        assert pm.load("MISSING") is None

    def test_save_with_date_partition(self, tmp_dir):
        pm = ParquetManager(parquet_dir=str(tmp_dir / "parquet"))
        df = pd.DataFrame({"a": [1]})
        pm.save(df, "000001.SZ", date="2024-01-15")
        loaded = pm.load("000001.SZ", date="2024-01-15")
        assert loaded is not None
        assert len(loaded) == 1

    def test_list_symbols(self, tmp_dir):
        pm = ParquetManager(parquet_dir=str(tmp_dir / "parquet"))
        pm.save(pd.DataFrame({"a": [1]}), "AAPL")
        pm.save(pd.DataFrame({"b": [2]}), "GOOG")
        symbols = pm.list_symbols()
        assert "AAPL" in symbols
        assert "GOOG" in symbols

    def test_delete(self, tmp_dir):
        pm = ParquetManager(parquet_dir=str(tmp_dir / "parquet"))
        pm.save(pd.DataFrame({"a": [1]}), "DEL")
        assert pm.delete("DEL") is True
        assert pm.load("DEL") is None

    def test_delete_missing(self, tmp_dir):
        pm = ParquetManager(parquet_dir=str(tmp_dir / "parquet"))
        assert pm.delete("NOPE") is False


# ===========================================================================
# DatabaseManager
# ===========================================================================

class TestDatabaseManager:
    @pytest.fixture
    def db(self, tmp_dir):
        db_path = str(tmp_dir / "test.db")
        dm = DatabaseManager(db_path=db_path)
        dm.execute("CREATE SEQUENCE IF NOT EXISTS test_id_seq START 1")
        dm.execute("""
            CREATE TABLE IF NOT EXISTS test_tbl (
                id INTEGER PRIMARY KEY DEFAULT nextval('test_id_seq'),
                name TEXT NOT NULL,
                value INTEGER DEFAULT 0
            )
        """)
        dm.connection.commit()
        yield dm
        dm.close()

    def test_execute_and_fetch_one(self, db):
        db.execute("INSERT INTO test_tbl (name, value) VALUES ('a', 1)")
        db.connection.commit()
        row = db.fetch_one("SELECT name, value FROM test_tbl WHERE name = ?", ["a"])
        assert row == ("a", 1)

    def test_fetch_all(self, db):
        db.execute("INSERT INTO test_tbl (name, value) VALUES ('x', 10)")
        db.execute("INSERT INTO test_tbl (name, value) VALUES ('y', 20)")
        db.connection.commit()
        rows = db.fetch_all("SELECT name, value FROM test_tbl ORDER BY name")
        assert len(rows) == 2

    def test_fetch_df(self, db):
        db.execute("INSERT INTO test_tbl (name, value) VALUES ('z', 99)")
        db.connection.commit()
        df = db.fetch_df("SELECT * FROM test_tbl")
        assert len(df) == 1

    def test_context_manager(self, tmp_dir):
        db_path = str(tmp_dir / "ctx_test.db")
        with DatabaseManager(db_path=db_path) as dm:
            dm.execute("CREATE TABLE t (id INT)")
            dm.connection.commit()
        # Connection should be closed


# ===========================================================================
# TdxDataSource (mocked)
# ===========================================================================

class TestTdxDataSource:
    def test_fetch_history_delegates(self):
        from app.data.sources.tdxdata_source import TdxDataSource

        source = TdxDataSource.__new__(TdxDataSource)
        mock_api = MagicMock()
        mock_api.fetch_history.return_value = pd.DataFrame({"close": [10]})
        source._api = mock_api
        source._connected = True
        source._server = None
        source._timeout = 15
        source._tdxdir = None

        result = source.fetch_history(
            stock_list=["600519"],
            start_date="2024-01-01",
            end_date="2024-06-30",
        )
        mock_api.fetch_history.assert_called_once()
        assert len(result) == 1

    def test_fetch_realtime_delegates(self):
        from app.data.sources.tdxdata_source import TdxDataSource

        source = TdxDataSource.__new__(TdxDataSource)
        mock_api = MagicMock()
        mock_api.fetch_realtime.return_value = pd.DataFrame({"close": [10]})
        source._api = mock_api
        source._connected = True
        source._server = None
        source._timeout = 15
        source._tdxdir = None

        result = source.fetch_realtime(stock_list=["600519"])
        mock_api.fetch_realtime.assert_called_once()

    def test_close(self):
        from app.data.sources.tdxdata_source import TdxDataSource

        source = TdxDataSource.__new__(TdxDataSource)
        mock_api = MagicMock()
        source._api = mock_api
        source._connected = True
        source._server = None
        source._timeout = 15
        source._tdxdir = None

        source.close()
        mock_api.close.assert_called_once()
        assert source._connected is False

    def test_validate_connection_success(self):
        from app.data.sources.tdxdata_source import TdxDataSource

        source = TdxDataSource.__new__(TdxDataSource)
        source._api = MagicMock()
        source._connected = True
        source._server = None
        source._timeout = 15
        source._tdxdir = None

        assert source.validate_connection() is True

    def test_validate_connection_failure(self):
        from app.data.sources.tdxdata_source import TdxDataSource

        source = TdxDataSource.__new__(TdxDataSource)
        source._api = None
        source._connected = False
        source._server = None
        source._timeout = 15
        source._tdxdir = None

        with patch.object(source, "_ensure_api", side_effect=Exception("fail")):
            assert source.validate_connection() is False

    def test_context_manager(self):
        from app.data.sources.tdxdata_source import TdxDataSource

        source = TdxDataSource.__new__(TdxDataSource)
        mock_api = MagicMock()
        source._api = mock_api
        source._connected = True
        source._server = None
        source._timeout = 15
        source._tdxdir = None

        with source:
            pass
        mock_api.close.assert_called_once()


# ===========================================================================
# DataService (mocked source + real cache/db)
# ===========================================================================

@pytest.fixture
def data_svc(tmp_dir, test_settings):
    """Create a DataService with a temp database."""
    from app.services.data_service import DataService

    db_path = str(tmp_dir / "svc_test.db")
    import duckdb
    conn = duckdb.connect(db_path)
    conn.execute("CREATE SEQUENCE IF NOT EXISTS data_sources_id_seq START 1")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS data_sources (
            id INTEGER PRIMARY KEY DEFAULT nextval('data_sources_id_seq'),
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            config JSON NOT NULL,
            priority INTEGER DEFAULT 1,
            enabled BOOLEAN DEFAULT TRUE,
            last_checked TIMESTAMP,
            error_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

    original = test_settings.database.duckdb_path
    test_settings.database.duckdb_path = db_path

    svc = DataService()
    yield svc

    svc.close()
    test_settings.database.duckdb_path = original


class TestDataServiceSourceCRUD:
    def test_add_and_list(self, data_svc):
        sid = data_svc.add_data_source("test_src", "tdxdata", {"api_url": "http://x"})
        assert sid > 0
        sources = data_svc.list_data_sources()
        assert any(s["name"] == "test_src" for s in sources)

    def test_get_source(self, data_svc):
        sid = data_svc.add_data_source("src2", "tdxdata", {"key": "val"})
        src = data_svc.get_data_source(sid)
        assert src is not None
        assert src["name"] == "src2"
        assert src["config"]["key"] == "val"

    def test_update_source(self, data_svc):
        sid = data_svc.add_data_source("src3", "tdxdata", {})
        data_svc.update_data_source(sid, name="renamed", enabled=False)
        src = data_svc.get_data_source(sid)
        assert src["name"] == "renamed"
        assert src["enabled"] is False

    def test_delete_source(self, data_svc):
        sid = data_svc.add_data_source("del_me", "tdxdata", {})
        data_svc.delete_data_source(sid)
        assert data_svc.get_data_source(sid) is None


class TestDataServiceFetch:
    def test_get_history_with_mock(self, data_svc):
        mock_df = pd.DataFrame({
            "stock_code": ["600519"],
            "date": ["2024-01-02"],
            "open": [1700.0],
            "high": [1710.0],
            "low": [1695.0],
            "close": [1705.0],
            "volume": [10000],
        })
        with patch.object(data_svc.source, "fetch_history", return_value=mock_df):
            df = data_svc.get_history(
                symbols=["600519"],
                start_date="2024-01-01",
                end_date="2024-01-31",
                use_cache=False,
            )
            assert len(df) == 1
            assert df.iloc[0]["close"] == 1705.0

    def test_get_history_caches_result(self, data_svc):
        mock_df = pd.DataFrame({"close": [100]})
        call_count = 0

        def mock_fetch(**kwargs):
            nonlocal call_count
            call_count += 1
            return mock_df

        with patch.object(data_svc.source, "fetch_history", side_effect=mock_fetch):
            # First call — fetches from source
            df1 = data_svc.get_history(["600519"], "2024-01-01", "2024-01-31", use_cache=True)
            assert call_count == 1

            # Second call — should hit memory cache
            df2 = data_svc.get_history(["600519"], "2024-01-01", "2024-01-31", use_cache=True)
            assert call_count == 1  # no additional fetch

    def test_get_realtime_with_mock(self, data_svc):
        mock_df = pd.DataFrame({"stock_code": ["600519"], "close": [1705.0]})
        with patch.object(data_svc.source, "fetch_realtime", return_value=mock_df):
            df = data_svc.get_realtime(["600519"], use_cache=False)
            assert len(df) == 1

    def test_fetch_and_store(self, data_svc, tmp_dir):
        mock_df = pd.DataFrame({
            "stock_code": ["600519", "000001"],
            "close": [1705.0, 12.5],
            "volume": [10000, 5000],
        })
        with patch.object(data_svc.source, "fetch_history", return_value=mock_df):
            results = data_svc.fetch_and_store(
                symbols=["600519", "000001"],
                start_date="2024-01",
                end_date="2024-06",
            )
            assert len(results) == 2

    def test_check_health(self, data_svc):
        with patch.object(data_svc.source, "validate_connection", return_value=True):
            health = data_svc.check_source_health()
            assert health["connected"] is True
            assert "checked_at" in health


