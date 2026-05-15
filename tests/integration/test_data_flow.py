"""
数据流集成测试 — DataService.get_history / get_realtime / parallel_get_history
"""

import pandas as pd
import pytest


class TestHistoryDataFlow:

    def test_get_history(self, data_service, mock_source, tdx_available):
        if not tdx_available:
            mock_source.fetch_history.reset_mock()
        df1 = data_service.get_history(["000001"], "2024-01-01", "2024-01-31")
        df2 = data_service.get_history(["000001"], "2024-01-01", "2024-01-31")
        assert not df1.empty
        assert not df2.empty

    def test_get_realtime(self, data_service, mock_source, tdx_available):
        df = data_service.get_realtime(["000001", "600000"])
        assert not df.empty
        assert "000001" in df["stock_code"].values

    def test_parallel_get_history(self, data_service, mock_source, tdx_available):
        results = data_service.parallel_get_history(
            ["000001", "600000"], "2024-01-01", "2024-01-31"
        )
        assert len(results) == 2
        for symbol, df in results.items():
            assert not df.empty


class TestDataSourceManagement:

    def test_get_stats(self, data_service):
        stats = data_service.get_stats()
        assert isinstance(stats, dict)
        assert "source_connected" in stats
