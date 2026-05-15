"""
API集成测试
测试服务层API的集成功能
"""

import pandas as pd
import pytest


class TestDataServiceAPI:

    def test_get_history(self, data_service, mock_source, tdx_available):
        df = data_service.get_history(["000001"], "2024-01-01", "2024-01-31")
        assert not df.empty
        assert "close" in df.columns

    def test_get_history_uses_mock(self, data_service, mock_source, tdx_available):
        if not tdx_available:
            mock_source.fetch_history.reset_mock()
        data_service.get_history(["000001"], "2024-01-01", "2024-01-31")
        data_service.get_history(["000001"], "2024-01-01", "2024-01-31")

    def test_get_realtime(self, data_service, mock_source, tdx_available):
        df = data_service.get_realtime(["000001", "600000"])
        assert not df.empty
        assert "stock_code" in df.columns

    def test_parallel_get_history(self, data_service, mock_source, tdx_available):
        result = data_service.parallel_get_history(
            ["000001", "600000"], "2024-01-01", "2024-01-31"
        )
        assert isinstance(result, dict)
        assert "000001" in result
        assert "600000" in result


class TestIndicatorServiceAPI:

    def test_calculate_sma(self, indicator_service, sample_stock_df):
        result = indicator_service.calculate("sma", sample_stock_df, params={"period": 5})
        assert "sma" in result
        assert len(result["sma"]) == len(sample_stock_df)

    def test_calculate_ema(self, indicator_service, sample_stock_df):
        result = indicator_service.calculate("ema", sample_stock_df, params={"period": 12})
        assert "ema" in result
        assert len(result["ema"]) == len(sample_stock_df)

    def test_calculate_rsi(self, indicator_service, sample_stock_df):
        result = indicator_service.calculate("rsi", sample_stock_df, params={"period": 14})
        assert "rsi" in result
        assert len(result["rsi"]) == len(sample_stock_df)

    def test_calculate_macd(self, indicator_service, sample_stock_df):
        result = indicator_service.calculate("macd", sample_stock_df)
        assert "macd_line" in result
        assert "signal_line" in result
        assert "histogram" in result

    def test_calculate_bollinger_bands(self, indicator_service, sample_stock_df):
        result = indicator_service.calculate("bollinger_bands", sample_stock_df)
        assert "bb_upper" in result
        assert "bb_middle" in result
        assert "bb_lower" in result

    def test_calculate_obv(self, indicator_service, sample_stock_df):
        result = indicator_service.calculate("obv", sample_stock_df)
        assert "obv" in result

    def test_calculate_vwap(self, indicator_service, sample_stock_df):
        result = indicator_service.calculate("vwap", sample_stock_df)
        assert "vwap" in result

    def test_calculate_unknown_raises(self, indicator_service, sample_stock_df):
        with pytest.raises(ValueError, match="Unknown indicator"):
            indicator_service.calculate("nonexistent", sample_stock_df)

    def test_calculate_multiple(self, indicator_service, sample_stock_df):
        result = indicator_service.calculate_multiple(
            ["sma", "ema"], sample_stock_df,
            params_map={"sma": {"period": 10}, "ema": {"period": 12}},
        )
        assert "sma" in result
        assert "ema" in result
        assert "sma" in result["sma"]
        assert "ema" in result["ema"]

    def test_list_indicators(self, indicator_service):
        indicators = indicator_service.list_indicators()
        assert len(indicators) >= 8
        names = [i["name"] for i in indicators]
        assert "sma" in names
        assert "ema" in names
        assert "rsi" in names
        assert "macd" in names

    def test_get_indicator_info(self, indicator_service):
        info = indicator_service.get_indicator_info("sma")
        assert info is not None
        assert info["name"] == "sma"
        assert info["category"] == "trend"
        assert info["is_builtin"] is True

    def test_get_indicator_info_unknown(self, indicator_service):
        assert indicator_service.get_indicator_info("nonexistent") is None
