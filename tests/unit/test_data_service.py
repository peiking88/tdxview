"""
DataService unit tests covering remaining active methods.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest


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
    src.fetch_local.return_value = pd.DataFrame({"close": [15.0]})
    src.fetch_hybrid.return_value = pd.DataFrame({"close": [15.0, 15.1]})
    src.close.return_value = None
    return src


@pytest.fixture
def svc():
    from app.services.data_service import DataService

    unit_mock = _create_unit_mock_source()
    with patch("app.services.data_service.TdxDataSource", return_value=unit_mock):
        service = DataService()
    service._source = unit_mock
    return service, unit_mock


class TestLocalHybrid:
    def test_get_local(self, svc):
        s, source = svc
        df = s.get_local("000001")
        assert isinstance(df, pd.DataFrame)
        source.fetch_local.assert_called_once()

    def test_get_local_with_params(self, svc):
        s, source = svc
        df = s.get_local("600519", period="1w", tdxdir="/tmp", dividend_type="qfq")
        assert isinstance(df, pd.DataFrame)
        source.fetch_local.assert_called_once_with(
            stock_code="600519", period="1w", tdxdir="/tmp", dividend_type="qfq",
        )

    def test_get_hybrid(self, svc):
        s, source = svc
        df = s.get_hybrid("000001")
        assert isinstance(df, pd.DataFrame)
        source.fetch_hybrid.assert_called_once()

    def test_get_hybrid_with_params(self, svc):
        s, source = svc
        df = s.get_hybrid(
            "600519", start_date="2024-01", end_date="2024-06",
            period="1w", tdxdir="/tmp", dividend_type="qfq",
        )
        assert isinstance(df, pd.DataFrame)
        source.fetch_hybrid.assert_called_once_with(
            stock_code="600519", start_date="2024-01", end_date="2024-06",
            period="1w", tdxdir="/tmp", dividend_type="qfq",
        )


class TestParallel:
    def test_parallel_get_history_error_handling(self, svc):
        s, source = svc

        def fail_then_ok(symbols, **kwargs):
            if "FAIL" in symbols:
                raise RuntimeError("fail")
            return pd.DataFrame({
                "date": ["2024-01-02"], "close": [10.0],
                "stock_code": [symbols[0]],
            })

        source.fetch_history.side_effect = fail_then_ok
        results = s.parallel_get_history(
            symbols=["000001", "FAIL", "600519"],
            start_date="2024-01", end_date="2024-06", max_workers=2,
        )
        assert len(results) == 3
        assert results["FAIL"].empty  # empty DataFrame on error


class TestContextManager:
    def test_close_with_source(self, svc):
        s, source = svc
        s.close()
        source.close.assert_called_once()


class TestGetStats:
    def test_get_stats_no_source(self):
        from app.services.data_service import DataService
        svc = DataService()
        stats = svc.get_stats()
        assert stats["source_connected"] is False

    def test_get_stats_with_source(self, svc):
        s, source = svc
        stats = s.get_stats()
        assert stats["source_connected"] is True


class TestDataCleaning:
    def test_clean_removes_extreme_volume_among_normal(self):
        from app.services.data_service import DataService
        # Median of [1000, 1000, 1e15] is 1000, so 1e15 is removed
        df = pd.DataFrame({
            "volume": [1000, 1000, 1e15],
            "open": [10.0] * 3, "high": [11.0] * 3,
            "low": [9.0] * 3, "close": [10.5] * 3,
        })
        result = DataService._clean_kline_data(df)
        assert len(result) == 2

    def test_clean_keeps_valid_rows(self):
        from app.services.data_service import DataService
        df = pd.DataFrame({
            "volume": [1000] * 10,
            "open": [10.0] * 10, "high": [11.0] * 10,
            "low": [9.0] * 10, "close": [10.5] * 10,
        })
        result = DataService._clean_kline_data(df)
        assert len(result) == 10

    def test_clean_empty_df(self):
        from app.services.data_service import DataService
        df = pd.DataFrame()
        result = DataService._clean_kline_data(df)
        assert result.empty

    def test_clean_removes_high_lt_low(self):
        from app.services.data_service import DataService
        df = pd.DataFrame({
            "volume": [1000], "open": [10.0], "high": [9.0],
            "low": [11.0], "close": [10.0],
        })
        result = DataService._clean_kline_data(df)
        assert len(result) == 0

    def test_multi_symbol_cleaning(self):
        from app.services.data_service import DataService
        df = pd.DataFrame({
            "stock_code": ["000001", "000001", "600519"],
            "volume": [1000, 0, 1000],
            "open": [10.0, 10.0, 10.0], "high": [11.0, 11.0, 11.0],
            "low": [9.0, 9.0, 9.0], "close": [10.5, 10.5, 10.5],
        })
        result = DataService._clean_kline_data(df)
        assert len(result) == 2


class TestDataContinuity:
    def test_consecutive_dates_no_gap(self):
        from app.services.data_service import DataService
        df = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=5, freq="D"),
            "open": [10] * 5, "high": [11] * 5, "low": [9] * 5,
            "close": [10] * 5, "volume": [1000] * 5,
        })
        report = DataService.check_continuity(df)
        assert report["total"] == 5
        assert report["valid"] == 5
        assert report["date_gaps"] == []

    def test_date_gap_detected(self):
        from app.services.data_service import DataService
        df = pd.DataFrame({
            "date": ["2024-01-01", "2024-01-10"],
            "open": [10, 10], "high": [11, 11], "low": [9, 9],
            "close": [10, 10], "volume": [1000, 1000],
        })
        report = DataService.check_continuity(df)
        assert len(report["date_gaps"]) > 0

    def test_duplicate_dates_detected(self):
        from app.services.data_service import DataService
        df = pd.DataFrame({
            "date": ["2024-01-01", "2024-01-01"],
            "open": [10, 10], "high": [11, 11], "low": [9, 9],
            "close": [10, 10], "volume": [1000, 1000],
        })
        report = DataService.check_continuity(df)
        assert any("重复" in i for i in report["issues"])

    def test_negative_volume_detected(self):
        from app.services.data_service import DataService
        df = pd.DataFrame({
            "date": ["2024-01-01"],
            "open": [10], "high": [11], "low": [9],
            "close": [10], "volume": [-100],
        })
        report = DataService.check_continuity(df)
        assert any("负" in i for i in report["issues"])

    def test_empty_df_report(self):
        from app.services.data_service import DataService
        report = DataService.check_continuity(pd.DataFrame())
        assert report["total"] == 0

    def test_no_date_column(self):
        from app.services.data_service import DataService
        df = pd.DataFrame({"close": [10.0]})
        report = DataService.check_continuity(df)
        assert report["total"] == 1
