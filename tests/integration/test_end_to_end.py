"""
端到端功能测试
测试完整的用户场景和工作流程
"""

import numpy as np
import pandas as pd
import pytest


class TestRealtimeDataWorkflow:

    def test_realtime_quotes(self, data_service, mock_source, tdx_available):
        df = data_service.get_realtime(["000001", "600000"])
        assert not df.empty
        assert "stock_code" in df.columns
        assert len(df) == 2


class TestFullIndicatorAnalysis:

    def test_multi_indicator_analysis_report(self, indicator_service, sample_stock_df):
        results = indicator_service.calculate_multiple(
            ["sma", "ema", "rsi", "macd", "bollinger_bands"],
            sample_stock_df,
            params_map={
                "sma": {"period": 10},
                "ema": {"period": 12},
                "rsi": {"period": 14},
            },
        )

        assert "sma" in results
        assert "ema" in results
        assert "rsi" in results
        assert "macd" in results
        assert "bollinger_bands" in results

        close = sample_stock_df["close"]
        sma_val = results["sma"]["sma"]
        rsi_val = results["rsi"]["rsi"]
        bb_upper = results["bollinger_bands"]["bb_upper"]
        bb_lower = results["bollinger_bands"]["bb_lower"]

        assert len(sma_val) == len(close)
        assert len(rsi_val) == len(close)
        assert len(bb_upper) == len(close)
        assert len(bb_lower) == len(close)

        valid_sma = sma_val.dropna()
        assert len(valid_sma) > 0

    def test_data_to_indicator_pipeline(
        self, data_service, indicator_service, mock_source, tdx_available
    ):
        df = data_service.get_history(["000001"], "2024-01-01", "2024-01-31")
        assert not df.empty

        result = indicator_service.calculate("sma", df, params={"period": 5})
        assert "sma" in result
        assert len(result["sma"].dropna()) > 0
