"""
简单的集成测试 - 验证基本功能
"""

import numpy as np
import pandas as pd
import pytest


class TestSimpleDataService:

    def test_get_history(self, data_service, mock_source, tdx_available):
        df = data_service.get_history(["000001"], "2024-01-01", "2024-01-31")
        assert df is not None
        assert not df.empty
        assert "close" in df.columns

    def test_get_realtime(self, data_service, mock_source, tdx_available):
        df = data_service.get_realtime(["000001", "600000"])
        assert df is not None
        if df.empty:
            pytest.skip("实时数据不可用（非交易时段或服务器无响应）")
        assert "stock_code" in df.columns


class TestSimpleIndicatorService:

    def test_calculate_sma(self, indicator_service, sample_stock_df):
        result = indicator_service.calculate("sma", sample_stock_df, params={"period": 5})
        assert result is not None
        assert "sma" in result
        assert len(result["sma"]) == len(sample_stock_df)

    def test_calculate_rsi(self, indicator_service, sample_stock_df):
        result = indicator_service.calculate("rsi", sample_stock_df, params={"period": 14})
        assert "rsi" in result
        assert len(result["rsi"]) == len(sample_stock_df)

    def test_calculate_macd(self, indicator_service, sample_stock_df):
        result = indicator_service.calculate("macd", sample_stock_df)
        assert "macd_line" in result
        assert "signal_line" in result
        assert "histogram" in result

    def test_list_indicators(self, indicator_service):
        indicators = indicator_service.list_indicators()
        assert len(indicators) >= 8
        names = [i["name"] for i in indicators]
        assert "sma" in names
        assert "rsi" in names


class TestSimpleCrossService:

    def test_data_to_indicator_pipeline(self, data_service, indicator_service, mock_source, tdx_available):
        df = data_service.get_history(["000001"], "2024-01-01", "2024-01-31")
        assert not df.empty

        result = indicator_service.calculate("sma", df, params={"period": 5})
        assert "sma" in result
        assert len(result["sma"].dropna()) > 0
