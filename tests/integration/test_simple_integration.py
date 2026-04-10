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
        assert not df.empty
        assert "symbol" in df.columns

    def test_save_and_load_parquet(self, data_service, sample_stock_df):
        data_service.save_to_parquet(sample_stock_df, "AAPL", "2024-01")
        loaded = data_service.load_from_parquet("AAPL", "2024-01")
        assert loaded is not None
        assert len(loaded) == len(sample_stock_df)

    def test_load_parquet_missing_returns_none(self, data_service):
        result = data_service.load_from_parquet("NOTEXIST", "2099-01")
        assert result is None


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


class TestSimpleUserService:

    def test_module_import(self):
        from app.services import user_service
        assert hasattr(user_service, "hash_password")
        assert hasattr(user_service, "verify_password")
        assert hasattr(user_service, "register_user")
        assert hasattr(user_service, "authenticate_user")
        assert hasattr(user_service, "get_user_by_id")
        assert hasattr(user_service, "list_users")
        assert hasattr(user_service, "set_user_preferences")
        assert hasattr(user_service, "get_user_preferences")

    def test_register_and_authenticate(self, us, clean_db):
        ok, msg = us.register_user("simple_user", "Pass!1234")
        assert ok is True, f"Registration failed: {msg}"
        user = us.authenticate_user("simple_user", "Pass!1234")
        assert user is not None
        assert user["username"] == "simple_user"

    def test_hash_and_verify_password(self, us):
        hashed = us.hash_password("testpass!1")
        assert us.verify_password("testpass!1", hashed) is True
        assert us.verify_password("wrong!pwd1", hashed) is False

    def test_create_and_decode_jwt(self, us):
        token = us.create_access_token({"sub": "testuser"})
        payload = us.decode_access_token(token)
        assert payload is not None
        assert payload["sub"] == "testuser"


class TestSimpleCrossService:

    def test_data_to_indicator_pipeline(self, data_service, indicator_service, mock_source, tdx_available):
        df = data_service.get_history(["000001"], "2024-01-01", "2024-01-31")
        assert not df.empty

        result = indicator_service.calculate("sma", df, params={"period": 5})
        assert "sma" in result
        assert len(result["sma"].dropna()) > 0

    def test_parquet_to_indicator_pipeline(
        self, data_service, indicator_service, sample_stock_df
    ):
        data_service.save_to_parquet(sample_stock_df, "TEST", "2024-01")
        loaded = data_service.load_from_parquet("TEST", "2024-01")
        assert loaded is not None

        result = indicator_service.calculate("ema", loaded, params={"period": 10})
        assert "ema" in result
