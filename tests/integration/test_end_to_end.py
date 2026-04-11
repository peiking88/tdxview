"""
端到端功能测试
测试完整的用户场景和工作流程
"""

import numpy as np
import pandas as pd
import pytest


class TestUserOnboardingWorkflow:

    def test_register_login_set_preferences(self, us, clean_db):
        ok, _ = us.register_user("trader1", "Pass!1234", "trader1@example.com")
        assert ok is True
        user = us.authenticate_user("trader1", "Pass!1234")
        assert user is not None
        user_id = user["id"]

        us.set_user_preferences(user_id, {
            "theme": "dark",
            "default_symbols": ["AAPL", "GOOGL"],
            "chart_type": "candlestick",
        })

        prefs = us.get_user_preferences(user_id)
        assert prefs["theme"] == "dark"
        assert "AAPL" in prefs["default_symbols"]
        assert prefs["chart_type"] == "candlestick"

    def test_register_update_role_deactivate(self, us, clean_db):
        ok, _ = us.register_user("admin1", "Pass!1234", "admin1@example.com")
        assert ok is True
        user = us.authenticate_user("admin1", "Pass!1234")
        assert user is not None

        us.update_user_role(user["id"], "admin")
        updated = us.get_user_by_id(user["id"])
        assert updated["role"] == "admin"

        us.deactivate_user(user["id"])
        assert us.authenticate_user("admin1", "Pass!1234") is None


class TestDataFetchAndAnalyseWorkflow:

    def test_fetch_store_load_analyse(
        self, data_service, indicator_service, mock_source, sample_stock_df, tdx_available
    ):
        df = data_service.get_history(["000001"], "2024-01-01", "2024-01-31")
        assert not df.empty

        data_service.save_to_parquet(df, "000001", "2024-01")
        loaded = data_service.load_from_parquet("000001", "2024-01")
        assert loaded is not None
        assert len(loaded) > 0

        sma_result = indicator_service.calculate("sma", loaded, params={"period": 5})
        assert "sma" in sma_result
        assert len(sma_result["sma"]) == len(loaded)

        rsi_result = indicator_service.calculate("rsi", loaded, params={"period": 14})
        assert "rsi" in rsi_result

    def test_parallel_fetch_store_analyse(
        self, data_service, indicator_service, mock_source, tdx_available
    ):
        results = data_service.parallel_get_history(
            ["000001", "600000"], "2024-01-01", "2024-01-31"
        )
        assert len(results) == 2

        for symbol, df in results.items():
            assert not df.empty

            data_service.save_to_parquet(df, symbol, "2024-01")
            loaded = data_service.load_from_parquet(symbol, "2024-01")
            assert loaded is not None

            multi = indicator_service.calculate_multiple(
                ["sma", "ema", "rsi"], loaded,
                params_map={"sma": {"period": 5}, "ema": {"period": 12}},
            )
            assert "sma" in multi
            assert "ema" in multi
            assert "rsi" in multi

    def test_fetch_and_store_workflow(self, data_service, mock_source, tdx_available):
        result = data_service.fetch_and_store(
            ["000001"], "2024-01-01", "2024-01-31"
        )
        assert isinstance(result, dict)
        assert len(result) > 0

        for symbol in result:
            loaded = data_service.load_from_parquet(symbol, "2024-01")
            assert loaded is not None


class TestRealtimeDataWorkflow:

    def test_realtime_quotes(self, data_service, mock_source, tdx_available):
        df = data_service.get_realtime(["000001", "600000"])
        assert not df.empty
        assert "stock_code" in df.columns
        assert len(df) == 2

    def test_realtime_cache_short_ttl(self, data_service, mock_source, tdx_available):
        if not tdx_available:
            mock_source.fetch_realtime.reset_mock()
        data_service.get_realtime(["000001"])
        data_service.get_realtime(["000001"])


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

    def test_indicator_with_parquet_roundtrip(
        self, data_service, indicator_service, sample_stock_df
    ):
        data_service.save_to_parquet(sample_stock_df, "TEST", "2024-01")
        loaded = data_service.load_from_parquet("TEST", "2024-01")
        assert loaded is not None

        result = indicator_service.calculate("sma", loaded, params={"period": 5})
        assert "sma" in result

        data_service.save_to_parquet(
            loaded.assign(sma_5=result["sma"].values), "TEST", "2024-01-sma"
        )
        reloaded = data_service.load_from_parquet("TEST", "2024-01-sma")
        assert reloaded is not None
        assert "sma_5" in reloaded.columns


class TestUserWithDataWorkflow:

    def test_user_registers_fetches_analyses(
        self, us, data_service, indicator_service, mock_source, clean_db, tdx_available
    ):
        ok, _ = us.register_user("analyst1", "Pass!1234", "analyst1@example.com")
        assert ok is True
        user = us.authenticate_user("analyst1", "Pass!1234")
        assert user is not None
        user_id = user["id"]

        us.set_user_preferences(user_id, {
            "default_symbols": ["000001"],
            "default_indicators": ["sma", "rsi"],
        })

        df = data_service.get_history(["000001"], "2024-01-01", "2024-01-31")
        assert not df.empty

        indicators = us.get_user_preferences(user_id).get("default_indicators", [])
        for ind_name in indicators:
            result = indicator_service.calculate(ind_name, df)
            assert result is not None

        data_service.save_to_parquet(df, "000001", "2024-01")
        loaded = data_service.load_from_parquet("000001", "2024-01")
        assert loaded is not None

    def test_multiple_users_isolated_preferences(self, us, clean_db):
        ok1, _ = us.register_user("userA", "Pass!1234")
        assert ok1 is True
        ua = us.authenticate_user("userA", "Pass!1234")

        ok2, _ = us.register_user("userB", "Pass!5678")
        assert ok2 is True
        ub = us.authenticate_user("userB", "Pass!5678")

        us.set_user_preferences(ua["id"], {"theme": "dark", "symbol": "AAPL"})
        us.set_user_preferences(ub["id"], {"theme": "light", "symbol": "GOOGL"})

        prefs_a = us.get_user_preferences(ua["id"])
        prefs_b = us.get_user_preferences(ub["id"])

        assert prefs_a["theme"] == "dark"
        assert prefs_a["symbol"] == "AAPL"
        assert prefs_b["theme"] == "light"
        assert prefs_b["symbol"] == "GOOGL"
