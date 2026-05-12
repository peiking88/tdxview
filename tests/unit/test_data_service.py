"""
DataService additional unit tests covering uncovered lines.

原则：真实环境优先于 mock
- DuckDB 使用真实临时实例
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
        "date": ["2024-01-15", "2024-01-15", "2024-01-15"],
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

    from app.config.settings import get_settings
    settings = get_settings()
    original_db = settings.database.duckdb_path

    settings.database.duckdb_path = db_path

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
            last_checked TIMESTAMP,
            error_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(name, type)
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


class TestGetTick:
    def test_get_tick_basic(self, svc):
        s, source, is_live = svc
        df = s.get_tick("000001")
        assert isinstance(df, pd.DataFrame)
        if not is_live:
            source.fetch_tick.assert_called_once()

    def test_get_tick_with_date(self, svc):
        s, source, is_live = svc
        df = s.get_tick("000001", date="2024-01-15")
        assert isinstance(df, pd.DataFrame)
        if not is_live:
            source.fetch_tick.assert_called_once_with(
                stock_code="000001", date="2024-01-15"
            )

    def test_get_tick_no_cache(self, svc):
        s, source, is_live = svc
        df = s.get_tick("000001", use_cache=False)
        assert isinstance(df, pd.DataFrame)

    def test_get_tick_cached(self, svc):
        s, source, is_live = svc
        # Call twice — mock mode verifies no extra fetch, live mode verifies functional
        df1 = s.get_tick("000001", use_cache=True)
        call_count_after_first = source.fetch_tick.call_count if not is_live else 0
        df2 = s.get_tick("000001", use_cache=True)
        assert isinstance(df1, pd.DataFrame)
        assert isinstance(df2, pd.DataFrame)
        if not is_live:
            assert source.fetch_tick.call_count == call_count_after_first


class TestFinancialData:
    def test_get_financial(self, svc):
        s, source, is_live = svc
        df = s.get_financial("000001")
        assert df is not None
        if not is_live:
            source.fetch_financial.assert_called_once_with(stock_code="000001")

    def test_get_financial_cached(self, svc):
        s, source, is_live = svc
        df1 = s.get_financial("000001", use_cache=True)
        call_count_after_first = source.fetch_financial.call_count if not is_live else 0
        df2 = s.get_financial("000001", use_cache=True)
        assert df1 is not None
        assert df2 is not None
        if not is_live:
            assert source.fetch_financial.call_count == call_count_after_first  # cached, no extra call

    def test_get_financial_no_cache(self, svc):
        s, source, is_live = svc
        s.get_financial("000001", use_cache=False)
        # use_cache is now a no-op; second call loads from DuckDB
        s.get_financial("000001", use_cache=False)
        if not is_live:
            assert source.fetch_financial.call_count == 1

    def test_get_f10(self, svc):
        s, source, is_live = svc
        result = s.get_f10("000001")
        assert result is not None
        if not is_live:
            source.fetch_f10.assert_called_once()

    def test_get_f10_cached(self, svc):
        s, source, is_live = svc
        r1 = s.get_f10("000001", use_cache=True)
        call_count_after_first = source.fetch_f10.call_count if not is_live else 0
        r2 = s.get_f10("000001", use_cache=True)
        assert r1 is not None
        assert r2 is not None
        if not is_live:
            assert source.fetch_f10.call_count == call_count_after_first  # cached

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

    def test_get_basic_cached(self, svc):
        s, source, is_live = svc
        df1 = s.get_basic("000001", use_cache=True)
        call_count_after_first = source.fetch_basic.call_count if not is_live else 0
        df2 = s.get_basic("000001", use_cache=True)
        assert df1 is not None
        assert df2 is not None
        if not is_live:
            assert source.fetch_basic.call_count == call_count_after_first  # cached

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
        sid1 = s.add_data_source("dup_name", "tdxdata", {"timeout": 10})
        sid2 = s.add_data_source("dup_name", "tdxdata", {"timeout": 20})
        sources = s.list_data_sources()
        dup_count = sum(1 for src in sources if src["name"] == "dup_name")
        assert dup_count == 1
        assert sid1 == sid2

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
        # fetch_and_store calls source.fetch_history directly
        if not is_live:
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
            assert isinstance(result["000001"], str)


class TestParallel:
    def test_parallel_get_history_error_handling(self, svc):
        s, source, is_live = svc

        def mock_get_history(symbols, start_date, end_date, **kwargs):
            if "999999" in symbols:
                raise ConnectionError("timeout")
            return pd.DataFrame({"close": [15.0]})

        # Method replacement works in both live and mock modes
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

        def mock_get_history(**kwargs):
            raise Exception("fail")

        # Method replacement works in both live and mock modes
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
        assert "tables" in stats

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


# ===========================================================================
# Data cleaning & continuity tests
# ===========================================================================

class TestDataCleaning:
    """Test DataService._clean_kline_data anomaly removal."""

    @staticmethod
    def _make_dirty_df():
        """Create a DataFrame mimicking the 999999 anomaly.

        20 clean rows (price ~15, volume ~500000) + 5 dirty rows.
        Median price = 15.25, valid price range = [1.525, 152.5]
        Median volume = 500000, valid volume range = [50000, 5000000]
        """
        n_clean = 20
        n_dirty = 5
        dates = pd.date_range("2024-01-01", periods=n_clean + n_dirty, freq="D")
        df = pd.DataFrame({
            "date": dates,
            "open": [15.0] * n_clean + [0.0, -1.0, 15.0, 15.0, 15.0],
            "high": [16.0] * n_clean + [0.0, 15.0, 15.0, 1e20, 16.0],
            "low":  [14.0] * n_clean + [0.0, 15.0, 14.0, 14.0, 1e-5],
            "close": [15.5] * n_clean + [0.0, 15.0, 15.0, 15.0, 15.0],
            "volume": [500000] * n_clean + [0, -100, 1e24, 500000, 500000],
        })
        return df, n_clean, n_dirty

    def test_clean_removes_zero_volume(self):
        """Row with volume=0 should be removed (below median*0.1)."""
        df, _, _ = self._make_dirty_df()
        cleaned = DataService._clean_kline_data(df)
        assert (cleaned["volume"] > 0).all()

    def test_clean_removes_negative_volume(self):
        """Row with negative volume should be removed (below median*0.1)."""
        df, _, _ = self._make_dirty_df()
        cleaned = DataService._clean_kline_data(df)
        assert (cleaned["volume"] > 0).all()

    def test_clean_removes_extreme_volume(self):
        """Row with volume >> median*10 should be removed (999999 anomaly)."""
        df, _, _ = self._make_dirty_df()
        cleaned = DataService._clean_kline_data(df)
        median_vol = 500000
        assert (cleaned["volume"] <= median_vol * 10).all()

    def test_clean_removes_zero_price(self):
        """Row with OHLC = 0 should be removed (below median*0.1)."""
        df, n_clean, n_dirty = self._make_dirty_df()
        cleaned = DataService._clean_kline_data(df)
        for col in ("open", "high", "low", "close"):
            assert (cleaned[col] > 0).all()

    def test_clean_removes_negative_price(self):
        """Row with negative OHLC should be removed."""
        df, _, _ = self._make_dirty_df()
        cleaned = DataService._clean_kline_data(df)
        assert (cleaned["open"] > 0).all()

    def test_clean_removes_extreme_price(self):
        """Row with price >> median*10 should be removed."""
        df, _, _ = self._make_dirty_df()
        cleaned = DataService._clean_kline_data(df)
        median_price = 15.25
        for col in ("open", "high", "low", "close"):
            assert (cleaned[col] <= median_price * 10).all()

    def test_clean_removes_high_lt_low(self):
        """Row where high < low should be removed."""
        df, _, _ = self._make_dirty_df()
        cleaned = DataService._clean_kline_data(df)
        assert (cleaned["high"] >= cleaned["low"]).all()

    def test_clean_keeps_valid_rows(self):
        """Clean rows should be preserved."""
        df, n_clean, _ = self._make_dirty_df()
        cleaned = DataService._clean_kline_data(df)
        assert len(cleaned) >= n_clean - 2

    def test_clean_empty_df(self):
        """Empty DataFrame should pass through unchanged."""
        result = DataService._clean_kline_data(pd.DataFrame())
        assert result.empty

    def test_clean_preserves_non_numeric_columns(self):
        """Non-numeric columns like stock_code should survive cleaning."""
        df = pd.DataFrame({
            "date": ["2024-01-01", "2024-01-02"],
            "open": [15.0, 0.0],
            "high": [16.0, 0.0],
            "low": [14.0, 0.0],
            "close": [15.5, 0.0],
            "volume": [500000, 0],
            "stock_code": ["000001", "000001"],
        })
        cleaned = DataService._clean_kline_data(df)
        assert len(cleaned) == 1
        assert "stock_code" in cleaned.columns
        assert cleaned.iloc[0]["stock_code"] == "000001"

    def test_clean_999999_scenario(self):
        """Reproduce the actual 999999 anomaly: extreme volume + price outliers."""
        df = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=100, freq="D"),
            "open": [15.0] * 94 + [1e-10, 1e20, 15.0, 0.0, -5.0, 15.0],
            "high": [16.0] * 94 + [15.0, 1e20, 16.0, 0.0, 15.0, 1e-5],
            "low":  [14.0] * 94 + [15.0, 14.0, 1e-10, 0.0, 14.0, 14.0],
            "close": [15.5] * 94 + [15.0, 15.5, 15.0, 0.0, 15.0, 15.0],
            "volume": [500000] * 94 + [1e24, 1e-10, 500000, -999, 0, 500000],
        })
        cleaned = DataService._clean_kline_data(df)
        assert len(cleaned) >= 94
        assert (cleaned["volume"] > 0).all()
        assert (cleaned["high"] >= cleaned["low"]).all()
        median_price = 15.25
        for col in ("open", "high", "low", "close"):
            assert (cleaned[col] >= median_price * 0.1).all()
            assert (cleaned[col] <= median_price * 10).all()

    def test_dynamic_range_adapts_to_stock(self):
        """Cleaning should adapt to different price levels."""
        # 茅台 style: price ~1800, volume ~30000
        df = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=20, freq="D"),
            "open": [1800.0] * 18 + [0.01, 1e8],
            "high": [1810.0] * 18 + [1810.0, 1e8],
            "low": [1790.0] * 18 + [1790.0, 1790.0],
            "close": [1805.0] * 18 + [1805.0, 1805.0],
            "volume": [30000] * 18 + [30000, 1e20],
        })
        cleaned = DataService._clean_kline_data(df)
        assert len(cleaned) == 18
        assert cleaned["close"].max() < 2000

    def test_multi_symbol_cleaning(self):
        """Cleaning should work per-symbol, preserving different price levels."""
        df = pd.DataFrame({
            "stock_code": ["600519"] * 10 + ["000001"] * 10,
            "date": pd.date_range("2024-01-01", periods=20, freq="D"),
            "open": [1800.0] * 9 + [1e10] + [15.0] * 10,
            "high": [1810.0] * 9 + [1e10] + [16.0] * 10,
            "low": [1790.0] * 9 + [1790.0] + [14.0] * 10,
            "close": [1805.0] * 9 + [1e10] + [15.5] * 10,
            "volume": [30000] * 9 + [1e20] + [500000] * 10,
        })
        cleaned = DataService._clean_kline_data(df)
        # 600519: 1 dirty row removed → 9; 000001: all clean → 10
        assert len(cleaned) == 19
        assert set(cleaned["stock_code"]) == {"600519", "000001"}
        # 600519 dirty row (1e10) gone
        mtf = cleaned[cleaned["stock_code"] == "600519"]
        assert mtf["close"].max() < 10000


class TestDataContinuity:
    """Test DataService.check_continuity report."""

    def test_consecutive_dates_no_gap(self):
        """Consecutive daily dates should have no gaps."""
        df = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=20, freq="D"),
            "close": [15.0] * 20,
        })
        report = DataService.check_continuity(df)
        assert report["total"] == 20
        assert len(report["date_gaps"]) == 0

    def test_date_gap_detected(self):
        """Gaps > 1 day should be reported."""
        dates = [
            pd.Timestamp("2024-01-01"),
            pd.Timestamp("2024-01-02"),
            pd.Timestamp("2024-01-05"),  # 3-day gap
        ]
        df = pd.DataFrame({
            "date": dates,
            "close": [15.0] * 3,
        })
        report = DataService.check_continuity(df)
        assert len(report["date_gaps"]) >= 1
        assert any(g[2] > 1 for g in report["date_gaps"])

    def test_business_day_gaps_detected(self):
        """Business day frequency produces weekend gaps > 1 day."""
        df = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=20, freq="B"),
            "close": [15.0] * 20,
        })
        report = DataService.check_continuity(df)
        # Weekend gaps (Sat-Sun) = 2 days each
        assert len(report["date_gaps"]) >= 1

    def test_duplicate_dates_detected(self):
        """Duplicate dates should be reported."""
        dates = list(pd.date_range("2024-01-02", periods=5, freq="D"))
        dates.append(dates[-1])
        df = pd.DataFrame({
            "date": dates,
            "close": [15.0] * 6,
        })
        report = DataService.check_continuity(df)
        assert any("重复日期" in issue for issue in report["issues"])

    def test_negative_volume_detected(self):
        """Negative volume should be reported."""
        df = pd.DataFrame({
            "date": pd.date_range("2024-01-02", periods=5, freq="D"),
            "close": [15.0] * 5,
            "volume": [100, 200, -50, 300, 400],
        })
        report = DataService.check_continuity(df)
        assert any("负" in issue for issue in report["issues"])

    def test_high_lt_low_detected(self):
        """high < low should be reported."""
        df = pd.DataFrame({
            "date": pd.date_range("2024-01-02", periods=5, freq="D"),
            "high": [16, 16, 10, 16, 16],
            "low": [14, 14, 14, 14, 14],
            "close": [15.0] * 5,
        })
        report = DataService.check_continuity(df)
        assert any("high < low" in issue for issue in report["issues"])

    def test_empty_df_report(self):
        """Empty DataFrame should return safe report."""
        report = DataService.check_continuity(pd.DataFrame())
        assert report["total"] == 0
        assert report["issues"] == []

    def test_no_date_column(self):
        """DataFrame without date column should return safe report."""
        df = pd.DataFrame({"close": [15.0, 16.0]})
        report = DataService.check_continuity(df)
        assert report["total"] == 2
