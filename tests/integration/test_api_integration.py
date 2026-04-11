"""
API集成测试
测试服务层API的集成功能
"""

import json

import numpy as np
import pandas as pd
import pytest


class TestUserServiceAPI:

    def test_register_and_authenticate(self, us, clean_db):
        ok, msg = us.register_user("alice", "Pass!1234", "alice@example.com")
        assert ok is True, f"Registration failed: {msg}"
        user = us.authenticate_user("alice", "Pass!1234")
        assert user is not None
        assert user["username"] == "alice"
        assert user["email"] == "alice@example.com"
        assert user["role"] == "user"

    def test_authenticate_wrong_password(self, us, clean_db):
        us.register_user("bob", "Secret!90", "bob@example.com")
        assert us.authenticate_user("bob", "wrong!pwd") is None

    def test_authenticate_inactive_user(self, us, clean_db):
        ok, _ = us.register_user("inactive", "Pass!1234")
        assert ok is True
        user = us.get_user_by_username("inactive")
        us.deactivate_user(user["id"])
        user = us.authenticate_user("inactive", "Pass!1234")
        assert user is None

    def test_register_duplicate_username(self, us, clean_db):
        ok1, _ = us.register_user("bob", "Pass!1234")
        assert ok1 is True
        ok2, msg = us.register_user("bob", "Pass!5678")
        assert ok2 is False
        assert "already exists" in msg

    def test_register_short_password(self, us, clean_db):
        ok, msg = us.register_user("eve", "ab")
        assert ok is False
        assert "Password" in msg

    def test_get_user_by_id(self, us, clean_db):
        ok, _ = us.register_user("frank", "Pass!1234", "frank@example.com")
        assert ok is True
        user = us.authenticate_user("frank", "Pass!1234")
        fetched = us.get_user_by_id(user["id"])
        assert fetched is not None
        assert fetched["username"] == "frank"

    def test_get_user_by_username(self, us, clean_db):
        ok, _ = us.register_user("grace", "Pass!1234")
        assert ok is True
        fetched = us.get_user_by_username("grace")
        assert fetched is not None
        assert fetched["username"] == "grace"

    def test_list_users(self, us, clean_db):
        ok1, _ = us.register_user("user1", "Pass!1234")
        assert ok1 is True
        ok2, _ = us.register_user("user2", "Pass!5678")
        assert ok2 is True
        users = us.list_users()
        assert len(users) == 2

    def test_update_user_role(self, us, clean_db):
        ok, _ = us.register_user("heidi", "Pass!1234")
        assert ok is True
        user = us.authenticate_user("heidi", "Pass!1234")
        us.update_user_role(user["id"], "admin")
        updated = us.get_user_by_id(user["id"])
        assert updated["role"] == "admin"

    def test_deactivate_user(self, us, clean_db):
        ok, _ = us.register_user("ivan", "Pass!1234")
        assert ok is True
        user = us.authenticate_user("ivan", "Pass!1234")
        result = us.deactivate_user(user["id"])
        assert result is True
        updated = us.get_user_by_id(user["id"])
        assert updated["is_active"] is False

    def test_password_hash_verify(self, us):
        hashed = us.hash_password("mypass!99")
        assert us.verify_password("mypass!99", hashed) is True
        assert us.verify_password("wrong!pwd", hashed) is False


class TestUserServicePreferences:

    def test_set_and_get_preferences(self, us, clean_db):
        ok, _ = us.register_user("judy", "Pass!1234")
        assert ok is True
        user = us.authenticate_user("judy", "Pass!1234")

        prefs = {"theme": "dark", "language": "zh-CN", "symbols": ["AAPL", "GOOGL"]}
        us.set_user_preferences(user["id"], prefs)

        got = us.get_user_preferences(user["id"])
        assert got["theme"] == "dark"
        assert got["language"] == "zh-CN"
        assert "AAPL" in got["symbols"]

    def test_update_preferences_merges(self, us, clean_db):
        ok, _ = us.register_user("karl", "Pass!1234")
        assert ok is True
        user = us.authenticate_user("karl", "Pass!1234")

        us.set_user_preferences(user["id"], {"theme": "dark", "lang": "en"})
        us.update_user_preferences(user["id"], {"theme": "light", "chart": "candle"})

        got = us.get_user_preferences(user["id"])
        assert got["theme"] == "light"
        assert got["lang"] == "en"
        assert got["chart"] == "candle"


class TestUserServiceJWT:

    def test_create_and_decode_token(self, us):
        token = us.create_access_token({"sub": "alice", "role": "user"})
        assert isinstance(token, str)

        payload = us.decode_access_token(token)
        assert payload is not None
        assert payload["sub"] == "alice"
        assert payload["role"] == "user"

    def test_decode_invalid_token(self, us):
        assert us.decode_access_token("invalid.token.here") is None


class TestDataServiceAPI:

    def test_get_history(self, data_service, mock_source, tdx_available):
        df = data_service.get_history(["000001"], "2024-01-01", "2024-01-31")
        assert not df.empty
        assert "close" in df.columns

    def test_get_history_uses_cache(self, data_service, mock_source, tdx_available):
        if not tdx_available:
            mock_source.fetch_history.reset_mock()
        data_service.get_history(["000001"], "2024-01-01", "2024-01-31")
        data_service.get_history(["000001"], "2024-01-01", "2024-01-31")

    def test_get_realtime(self, data_service, mock_source, tdx_available):
        df = data_service.get_realtime(["000001", "600000"])
        assert not df.empty
        assert "stock_code" in df.columns

    def test_save_and_load_parquet(self, data_service, sample_stock_df):
        data_service.save_to_parquet(sample_stock_df, "AAPL", "2024-01")
        loaded = data_service.load_from_parquet("AAPL", "2024-01")
        assert loaded is not None
        assert len(loaded) == len(sample_stock_df)

    def test_load_parquet_missing(self, data_service):
        result = data_service.load_from_parquet("NOTEXIST", "2099-01")
        assert result is None

    def test_fetch_and_store(self, data_service, mock_source, tdx_available):
        result = data_service.fetch_and_store(["000001"], "2024-01-01", "2024-01-31")
        assert isinstance(result, dict)
        if not tdx_available:
            mock_source.fetch_history.assert_called()

    def test_parallel_get_history(self, data_service, mock_source, tdx_available):
        result = data_service.parallel_get_history(
            ["000001", "600000"], "2024-01-01", "2024-01-31"
        )
        assert isinstance(result, dict)
        assert "000001" in result
        assert "600000" in result

    def test_check_source_health(self, data_service, mock_source, tdx_available):
        if not tdx_available:
            mock_source.validate_connection.return_value = True
        health = data_service.check_source_health()
        assert health["connected"] is True


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

    def test_calculate_uses_cache(self, indicator_service, sample_stock_df):
        r1 = indicator_service.calculate("sma", sample_stock_df, params={"period": 5})
        r2 = indicator_service.calculate("sma", sample_stock_df, params={"period": 5})
        pd.testing.assert_series_equal(r1["sma"].reset_index(drop=True), r2["sma"].reset_index(drop=True))

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
