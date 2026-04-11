"""
DataService additional unit tests covering uncovered lines.

原则：真实环境优先于 mock
- DuckDB / Parquet / Cache 使用真实临时实例
- 通达信服务器可用时使用真实连接，不可用时自动降级为 mock
- mock-only 断言（如 assert_called_once）仅在 mock 模式下执行
- 每个测试用独立的 mock 实例，避免 session scope mock 的调用计数累积
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from app.services.data_service import DataService


def _create_unit_mock_source():
    src = MagicMock()
    src.validate_connection.return_value = True
    src.fetch_history.return_value = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=10, freq="D"),
        "open": np.random.uniform(10, 30, 10),
        "high": np.random.uniform(11, 33, 10),
        "low":  np.random.uniform(9, 27, 10),
        "close": np.random.uniform(10, 32, 10),
        "volume": np.random.randint(100_000, 1_000_000, 10),
        "stock_code": ["000001"] * 10,
    })
    src.fetch_realtime.return_value = pd.DataFrame({
        "stock_code":  ["000001", "600000"],
        "price":   [15.25, 8.50],
        "change":  [0.25, -0.15],
        "change_percent": [1.67, -1.73],
        "volume":  [1_500_000, 750_000],
    })
    src.fetch_tick.return_value = pd.DataFrame({
        "price": [15.0, 15.01, 15.02],
        "volume": [100, 200, 150],
    })
    src.fetch_financial.return_value = pd.DataFrame({"revenue": [100]})
    src.fetch_f10.return_value = {"summary": pd.DataFrame({"item": ["EPS"], "value": [5.0]})}
    src.fetch_basic.return_value = pd.DataFrame({"name": ["Ping An Bank"]})
    src.fetch_local.return_value = pd.DataFrame({"close": [15.0]})
    src.fetch_hybrid.return_value = pd.DataFrame({"close": [15.0, 15.1]})
    src.close.return_value = None
    return src


@pytest.fixture
def svc(tdx_source, tdx_available, tmp_path):
    db_path = str(tmp_path / "test.duckdb")
    parquet_dir = str(tmp_path / "parquet")
    cache_dir = str(tmp_path / "cache")

    from app.config.settings import get_settings
    settings = get_settings()
    original_db = settings.database.duckdb_path
    original_parquet = settings.database.parquet_dir
    original_cache = settings.database.cache_dir

    settings.database.duckdb_path = db_path
    settings.database.parquet_dir = parquet_dir
    settings.database.cache_dir = cache_dir

    import duckdb
    conn = duckdb.connect(db_path)
    conn.execute("CREATE SEQUENCE IF NOT EXISTS data_sources_id_seq START 1")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS data_sources (
            id        INTEGER PRIMARY KEY DEFAULT nextval('data_sources_id_seq'),
            name      TEXT NOT NULL,
            type      TEXT NOT NULL,
            config    TEXT NOT NULL,
            enabled   BOOLEAN DEFAULT TRUE,
            priority  INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

    if tdx_available:
        service = DataService()
        service._source = tdx_source
        yield service, tdx_source, True
    else:
        unit_mock = _create_unit_mock_source()
        with patch("app.services.data_service.TdxDataSource", return_value=unit_mock):
            service = DataService()
        service._source = unit_mock
        yield service, unit_mock, False

    settings.database.duckdb_path = original_db
    settings.database.parquet_dir = original_parquet
    settings.database.cache_dir = original_cache


class TestGetTick:
    def test_get_tick_basic(self, svc):
        s, source, is_live = svc
        df = s.get_tick("000001")
        if is_live and df.empty:
            pytest.skip("Tick data unavailable (outside trading hours)")
        assert not df.empty
        if not is_live:
            source.fetch_tick.assert_called_once()

    def test_get_tick_with_date(self, svc):
        s, source, is_live = svc
        df = s.get_tick("000001", date="2024-01-15")
        if is_live and df.empty:
            pytest.skip("Tick data unavailable (outside trading hours)")
        assert not df.empty
        if not is_live:
            source.fetch_tick.assert_called_once_with(
                stock_code="000001", date="2024-01-15"
            )

    def test_get_tick_no_cache(self, svc):
        s, source, is_live = svc
        df = s.get_tick("000001", use_cache=False)
        if is_live and df.empty:
            pytest.skip("Tick data unavailable (outside trading hours)")
        assert not df.empty

    def test_get_tick_cached(self, svc):
        s, source, is_live = svc
        if is_live:
            pytest.skip("Tick data unavailable (outside trading hours)")
        s._cache.set(
            "tick_test",
            json.loads(
                pd.DataFrame({"price": [100.0], "volume": [50]})
                .to_json(orient="columns", date_format="iso")
            ),
        )
        df = s.get_tick("000001")
        assert not df.empty


class TestFinancialData:
    def test_get_financial(self, svc):
        s, source, is_live = svc
        df = s.get_financial("000001")
        assert df is not None
        if not is_live:
            source.fetch_financial.assert_called_once_with(stock_code="000001")

    def test_get_f10(self, svc):
        s, source, is_live = svc
        result = s.get_f10("000001")
        assert result is not None
        if not is_live:
            source.fetch_f10.assert_called_once()

    def test_get_f10_with_sections(self, svc):
        s, source, is_live = svc
        result = s.get_f10("000001", sections=["summary"])
        assert result is not None

    def test_get_basic(self, svc):
        s, source, is_live = svc
        df = s.get_basic("000001")
        assert df is not None
        if not is_live:
            source.fetch_basic.assert_called_once()

    def test_get_basic_with_date(self, svc):
        s, source, is_live = svc
        df = s.get_basic("000001", date="2024-01-01")
        assert df is not None


class TestLocalHybrid:
    def test_get_local(self, svc):
        s, source, is_live = svc
        df = s.get_local("000001")
        assert df is not None
        if not is_live:
            source.fetch_local.assert_called_once()

    def test_get_local_with_params(self, svc):
        s, source, is_live = svc
        df = s.get_local("000001", period="5m", dividend_type="front")
        if not is_live:
            source.fetch_local.assert_called_once_with(
                stock_code="000001", period="5m", tdxdir=None, dividend_type="front"
            )

    def test_get_hybrid(self, svc):
        s, source, is_live = svc
        df = s.get_hybrid("000001")
        assert df is not None
        if not is_live:
            source.fetch_hybrid.assert_called_once()

    def test_get_hybrid_with_params(self, svc):
        s, source, is_live = svc
        df = s.get_hybrid(
            "000001", start_date="2024-01-01", end_date="2024-01-31",
            period="1d", dividend_type="front",
        )
        if not is_live:
            source.fetch_hybrid.assert_called_once()


class TestDataSourceCRUD:
    def test_add_data_source(self, svc):
        s, source, is_live = svc
        result = s.add_data_source("test_source", "tdxdata", {"timeout": 10})
        assert result > 0
        ds = s.get_data_source(result)
        assert ds is not None
        assert ds["name"] == "test_source"

    def test_add_data_source_duplicate_name(self, svc):
        s, source, is_live = svc
        s.add_data_source("dup_name", "tdxdata", {"timeout": 10})
        s.add_data_source("dup_name", "tdxdata", {"timeout": 20})
        sources = s.list_data_sources()
        dup_count = sum(1 for src in sources if src["name"] == "dup_name")
        assert dup_count == 2

    def test_update_data_source(self, svc):
        s, source, is_live = svc
        sid = s.add_data_source("to_update", "tdxdata", {"timeout": 10})
        result = s.update_data_source(sid, name="updated", enabled=False)
        assert result is True
        ds = s.get_data_source(sid)
        assert ds["name"] == "updated"
        assert ds["enabled"] is False

    def test_update_data_source_no_updates(self, svc):
        s, source, is_live = svc
        result = s.update_data_source(1)
        assert result is False

    def test_delete_data_source(self, svc):
        s, source, is_live = svc
        sid = s.add_data_source("to_delete", "tdxdata", {"timeout": 10})
        result = s.delete_data_source(sid)
        assert result is True
        assert s.get_data_source(sid) is None

    def test_get_data_source_not_found(self, svc):
        s, source, is_live = svc
        result = s.get_data_source(99999)
        assert result is None

    def test_list_data_sources(self, svc):
        s, source, is_live = svc
        s.add_data_source("src1", "tdxdata", {"timeout": 10})
        s.add_data_source("src2", "tdxdata", {"timeout": 20})
        result = s.list_data_sources()
        assert len(result) >= 2

    def test_list_data_sources_empty(self, svc):
        s, source, is_live = svc
        for row in s._db.fetch_all("SELECT id FROM data_sources"):
            s._db.execute("DELETE FROM data_sources WHERE id = ?", [row[0]])
        s._db.connection.commit()
        result = s.list_data_sources()
        assert result == []


class TestFetchAndStore:
    def test_fetch_and_store_empty(self, svc):
        s, source, is_live = svc
        if is_live:
            pytest.skip("live server always returns data")
        source.fetch_history.return_value = pd.DataFrame()
        result = s.fetch_and_store(["000001"], "2099-01-01", "2099-01-02")
        assert result == {}

    def test_fetch_and_store_single_symbol(self, svc):
        s, source, is_live = svc
        if not is_live:
            source.fetch_history.return_value = pd.DataFrame({"close": [15.0]})
        result = s.fetch_and_store(["000001"], "2024-01-01", "2024-01-31")
        if not is_live:
            assert "000001" in result
            assert result["000001"].exists()


class TestParallel:
    def test_parallel_get_history_error_handling(self, svc):
        s, source, is_live = svc
        if is_live:
            pytest.skip("error injection not applicable for live server")

        def mock_get_history(symbols, start_date, end_date, **kwargs):
            if "999999" in symbols:
                raise ConnectionError("timeout")
            return pd.DataFrame({"close": [15.0]})

        s.get_history = mock_get_history
        result = s.parallel_get_history(["000001", "999999"], "2024-01-01", "2024-01-31")
        assert "000001" in result
        assert "999999" in result
        assert result["999999"].empty

    def test_parallel_fetch_and_store(self, svc):
        s, source, is_live = svc
        if not is_live:
            source.fetch_history.return_value = pd.DataFrame({
                "close": [15.0], "stock_code": ["000001"],
            })
        result = s.parallel_fetch_and_store(
            ["000001"], "2024-01-01", "2024-01-31"
        )
        assert isinstance(result, dict)


class TestBatchQuery:
    def test_batch_query_unknown_method(self, svc):
        s, source, is_live = svc
        with pytest.raises(ValueError, match="Unknown method"):
            s.batch_query_symbols(["000001"], "nonexistent_method")

    def test_batch_query_with_exception(self, svc):
        s, source, is_live = svc
        if is_live:
            pytest.skip("error injection not applicable for live server")

        def mock_get_history(**kwargs):
            raise Exception("fail")

        s.get_history = mock_get_history
        result = s.batch_query_symbols(
            ["000001"], "get_history",
            start_date="2024-01-01", end_date="2024-01-31",
        )
        assert result["000001"] is None

    def test_batch_query_tick(self, svc):
        s, source, is_live = svc
        result = s.batch_query_symbols(
            ["000001"], "get_tick", date="2024-01-01",
        )
        assert "000001" in result


class TestContextManager:
    def test_context_manager(self, svc):
        s, source, is_live = svc
        s._source = None
        with s:
            pass
        s._source = source
        with s:
            pass
        if not is_live:
            source.close.assert_called()

    def test_close_with_source(self, svc):
        s, source, is_live = svc
        s._source = source
        s.close()
        if not is_live:
            source.close.assert_called_once()


class TestGetStats:
    def test_get_stats_no_source(self, svc):
        s, source, is_live = svc
        s._source = None
        stats = s.get_stats()
        assert stats["source_connected"] is False
        assert "cache" in stats

    def test_get_stats_with_source(self, svc):
        s, source, is_live = svc
        s._source = source
        stats = s.get_stats()
        assert stats["source_connected"] is True


class TestSaveLoadParquet:
    def test_save_and_load_roundtrip(self, svc, sample_stock_df):
        s, source, is_live = svc
        s.save_to_parquet(sample_stock_df, "000001", "2024-01")
        loaded = s.load_from_parquet("000001", "2024-01")
        assert loaded is not None
        assert len(loaded) == len(sample_stock_df)

    def test_load_missing_returns_none(self, svc):
        s, source, is_live = svc
        result = s.load_from_parquet("NOTEXIST", "2099-01")
        assert result is None


@pytest.fixture
def sample_stock_df():
    dates = pd.date_range("2024-01-01", periods=31, freq="D")
    return pd.DataFrame({
        "date": dates,
        "open": np.random.uniform(10, 30, 31),
        "high": np.random.uniform(11, 33, 31),
        "low":  np.random.uniform(9, 27, 31),
        "close": np.random.uniform(10, 32, 31),
        "volume": np.random.randint(100_000, 1_000_000, 31).astype(int),
        "stock_code": ["000001"] * 31,
    })
