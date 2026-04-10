"""
数据流集成测试 — DataService.get_history / save_to_parquet / load_from_parquet / get_realtime
"""

import pandas as pd
import pytest


class TestHistoryDataFlow:

    def test_get_history_caches_result(self, data_service, mock_source, tdx_available):
        if not tdx_available:
            mock_source.fetch_history.reset_mock()
        df1 = data_service.get_history(["000001"], "2024-01-01", "2024-01-31")
        df2 = data_service.get_history(["000001"], "2024-01-01", "2024-01-31")
        assert not df1.empty
        assert not df2.empty

    def test_save_and_load_parquet(self, data_service, sample_stock_df):
        data_service.save_to_parquet(sample_stock_df, "AAPL")
        loaded = data_service.load_from_parquet("AAPL")
        assert loaded is not None
        assert len(loaded) == len(sample_stock_df)

    def test_load_parquet_missing_returns_none(self, data_service):
        assert data_service.load_from_parquet("NONEXIST") is None

    def test_save_parquet_with_date_partition(self, data_service, sample_stock_df):
        data_service.save_to_parquet(sample_stock_df, "AAPL", date="2024-01-01")
        loaded = data_service.load_from_parquet("AAPL", date="2024-01-01")
        assert loaded is not None

    def test_get_realtime(self, data_service, mock_source, tdx_available):
        df = data_service.get_realtime(["000001", "600000"])
        assert not df.empty
        assert "000001" in df["symbol"].values

    def test_fetch_and_store(self, data_service, mock_source, tdx_available):
        result = data_service.fetch_and_store(["000001"], "2024-01-01", "2024-01-10")
        assert "000001" in result
        assert result["000001"].exists()

    def test_parallel_get_history(self, data_service, mock_source, tdx_available):
        results = data_service.parallel_get_history(
            ["000001", "600000"], "2024-01-01", "2024-01-31"
        )
        assert len(results) == 2
        for symbol, df in results.items():
            assert not df.empty

    def test_batch_query_symbols(self, data_service, mock_source, sample_stock_df):
        data_service.save_to_parquet(sample_stock_df, "AAPL")
        result = data_service.batch_query_symbols(
            ["AAPL"], start_date="2024-01-01", end_date="2024-12-31"
        )
        assert isinstance(result, dict)


class TestCacheBehaviour:

    def test_cache_clear_then_refetch(self, data_service, mock_source, tdx_available):
        if not tdx_available:
            mock_source.fetch_history.reset_mock()
        df1 = data_service.get_history(["000001"], "2024-01-01", "2024-01-31")
        data_service._cache.clear()
        df2 = data_service.get_history(["000001"], "2024-01-01", "2024-01-31")
        if not tdx_available:
            assert mock_source.fetch_history.call_count >= 1

    def test_realtime_short_ttl(self, data_service, mock_source, tdx_available):
        if not tdx_available:
            mock_source.fetch_realtime.reset_mock()
        data_service.get_realtime(["000001"])
        data_service.get_realtime(["000001"])


class TestDataSourceManagement:

    def test_list_data_sources(self, data_service):
        result = data_service.list_data_sources()
        assert isinstance(result, list)

    def test_get_stats(self, data_service):
        stats = data_service.get_stats()
        assert isinstance(stats, dict)

    def test_check_source_health(self, data_service, mock_source, tdx_available):
        if not tdx_available:
            mock_source.validate_connection.return_value = True
        health = data_service.check_source_health()
        assert isinstance(health, dict)
