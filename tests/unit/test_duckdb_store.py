"""
DuckDBStore 单元测试 — 覆盖所有数据类型的 save/load/delete/list/info。
"""

import pytest
import pandas as pd
import numpy as np

from app.data.database import DatabaseManager
from app.data.duckdb_store import DuckDBStore


@pytest.fixture
def db(tmp_path):
    """创建临时 DuckDB 数据库。"""
    db_path = str(tmp_path / "test.duckdb")
    mgr = DatabaseManager(db_path=db_path)
    yield mgr
    mgr.close()


@pytest.fixture
def store(db):
    return DuckDBStore(db)


# ---------------------------------------------------------------------------
# K线数据
# ---------------------------------------------------------------------------


class TestKline:
    @pytest.fixture
    def kline_df(self):
        return pd.DataFrame({
            "date": ["2024-01-02", "2024-01-03", "2024-01-04"],
            "open": [10.0, 10.5, 11.0],
            "high": [10.5, 11.0, 11.5],
            "low": [9.8, 10.2, 10.8],
            "close": [10.3, 10.8, 11.2],
            "volume": [100000, 120000, 90000],
            "amount": [1030000.0, 1296000.0, 1008000.0],
        })

    def test_save_and_load(self, store, kline_df):
        key = store.save(kline_df, "000001", data_type="history")
        assert key == "kline/000001"

        loaded = store.load("000001", data_type="history")
        assert loaded is not None
        assert len(loaded) == 3
        assert "close" in loaded.columns

    def test_load_missing(self, store):
        assert store.load("NOTEXIST", data_type="history") is None

    def test_save_with_period_dividend(self, store, kline_df):
        store.save(kline_df, "000001", data_type="history", period="5m", dividend="qfq")
        loaded = store.load("000001", data_type="history", period="5m", dividend="qfq")
        assert loaded is not None
        assert len(loaded) == 3

        # 不同 period/dividend 不应加载到
        assert store.load("000001", data_type="history", period="1d", dividend="none") is None

    def test_load_with_date_range(self, store, kline_df):
        store.save(kline_df, "000001", data_type="history")
        loaded = store.load("000001", data_type="history", start_date="2024-01-03", end_date="2024-01-03")
        assert loaded is not None
        assert len(loaded) == 1

    def test_upsert_on_save(self, store, kline_df):
        """INSERT OR REPLACE: partial save preserves existing rows."""
        store.save(kline_df, "000001", data_type="history")
        # Save only the first row — should upsert, not delete others
        shorter = kline_df.iloc[:1]
        store.save(shorter, "000001", data_type="history")
        loaded = store.load("000001", data_type="history")
        assert loaded is not None
        assert len(loaded) == 3  # all rows preserved, first row updated

    def test_empty_df(self, store):
        key = store.save(pd.DataFrame(), "000001", data_type="history")
        assert key == ""

    def test_save_with_stock_code_column(self, store):
        df = pd.DataFrame({
            "date": ["2024-01-02"],
            "open": [10.0], "high": [10.5], "low": [9.8], "close": [10.3],
            "volume": [100000], "amount": [1030000.0],
            "stock_code": ["000001"],
        })
        store.save(df, "000001", data_type="history")
        loaded = store.load("000001", data_type="history")
        assert loaded is not None
        assert len(loaded) == 1


# ---------------------------------------------------------------------------
# Tick 数据
# ---------------------------------------------------------------------------


class TestTick:
    @pytest.fixture
    def tick_df(self):
        return pd.DataFrame({
            "date": ["2024-01-02", "2024-01-02", "2024-01-02"],
            "time": ["2024-01-02 09:30:00", "2024-01-02 09:30:05", "2024-01-02 09:30:10"],
            "price": [10.0, 10.01, 10.02],
            "volume": [100, 200, 150],
            "amount": [1000.0, 2002.0, 1503.0],
        })

    def test_save_and_load(self, store, tick_df):
        key = store.save(tick_df, "000001", data_type="tick")
        assert key == "tick/000001"
        loaded = store.load("000001", data_type="tick")
        assert loaded is not None
        assert len(loaded) == 3

    def test_load_with_date_filter(self, store, tick_df):
        store.save(tick_df, "000001", data_type="tick")
        loaded = store.load("000001", date="2024-01-02", data_type="tick")
        assert loaded is not None
        assert len(loaded) == 3

        loaded_empty = store.load("000001", date="2099-01-01", data_type="tick")
        assert loaded_empty is None


# ---------------------------------------------------------------------------
# Financial 数据
# ---------------------------------------------------------------------------


class TestFinancial:
    @pytest.fixture
    def fin_df(self):
        return pd.DataFrame({
            "report_date": ["2024-03-31", "2023-12-31"],
            "revenue": [100.0, 90.0],
            "net_profit": [10.0, 8.0],
        })

    def test_save_and_load(self, store, fin_df):
        key = store.save(fin_df, "600519", data_type="financial")
        assert key == "financial/600519"
        loaded = store.load("600519", data_type="financial")
        assert loaded is not None
        assert len(loaded) == 2
        assert "revenue" in loaded.columns

    def test_dynamic_columns_in_json(self, store):
        df = pd.DataFrame({
            "report_date": ["2024-03-31"],
            "custom_field": ["test_value"],
            "numeric_field": [42.0],
        })
        store.save(df, "000001", data_type="financial")
        loaded = store.load("000001", data_type="financial")
        assert loaded is not None
        assert "custom_field" in loaded.columns


# ---------------------------------------------------------------------------
# F10 数据
# ---------------------------------------------------------------------------


class TestF10:
    @pytest.fixture
    def f10_df(self):
        return pd.DataFrame({
            "section": ["摘要", "摘要", "股东"],
            "item": ["总股本", "流通股", "大股东A"],
            "value": ["100亿", "80亿", "5%"],
        })

    def test_save_and_load(self, store, f10_df):
        key = store.save(f10_df, "000001", data_type="f10")
        assert key == "f10/000001"
        loaded = store.load("000001", data_type="f10")
        assert loaded is not None
        assert len(loaded) == 3
        assert "section" in loaded.columns


# ---------------------------------------------------------------------------
# Factor 数据
# ---------------------------------------------------------------------------


class TestFactor:
    @pytest.fixture
    def factor_df(self):
        return pd.DataFrame({
            "date": ["2024-01-02", "2024-01-03", "2024-01-04"],
            "factor": [1.02, 1.01, 1.0],
        })

    def test_save_and_load(self, store, factor_df):
        key = store.save(factor_df, "000001", data_type="factor")
        assert key == "factor/000001"
        loaded = store.load("000001", data_type="factor")
        assert loaded is not None
        assert len(loaded) == 3

    def test_different_adjust(self, store, factor_df):
        store.save(factor_df, "000001", data_type="factor", dividend="qfq")
        store.save(factor_df, "000001", data_type="factor", dividend="hfq")

        qfq = store.load("000001", data_type="factor", dividend="qfq")
        hfq = store.load("000001", data_type="factor", dividend="hfq")
        assert qfq is not None
        assert hfq is not None
        assert len(qfq) == 3
        assert len(hfq) == 3


# ---------------------------------------------------------------------------
# Basic 数据
# ---------------------------------------------------------------------------


class TestBasic:
    @pytest.fixture
    def basic_df(self):
        return pd.DataFrame({
            "ex_date": ["2024-06-15", "2023-06-15"],
            "dividend": [0.5, 0.3],
        })

    def test_save_and_load(self, store, basic_df):
        key = store.save(basic_df, "000001", data_type="basic")
        assert key == "basic/000001"
        loaded = store.load("000001", data_type="basic")
        assert loaded is not None
        assert len(loaded) == 2


# ---------------------------------------------------------------------------
# Realtime 数据
# ---------------------------------------------------------------------------


class TestRealtime:
    @pytest.fixture
    def rt_df(self):
        return pd.DataFrame({
            "stock_code": ["000001"],
            "price": [10.5],
            "change": [0.3],
            "change_percent": [2.94],
            "open": [10.2],
            "high": [10.6],
            "low": [10.1],
            "volume": [500000],
            "amount": [5300000.0],
        })

    def test_save_and_load(self, store, rt_df):
        key = store.save(rt_df, "000001", data_type="realtime")
        assert key == "realtime/000001"
        loaded = store.load("000001", data_type="realtime")
        assert loaded is not None
        assert len(loaded) == 1
        assert loaded.iloc[0]["price"] == 10.5

    def test_upsert_overwrite(self, store, rt_df):
        store.save(rt_df, "000001", data_type="realtime")
        updated = rt_df.copy()
        updated["price"] = 11.0
        store.save(updated, "000001", data_type="realtime")
        loaded = store.load("000001", data_type="realtime")
        assert loaded is not None
        assert len(loaded) == 1
        assert loaded.iloc[0]["price"] == 11.0


# ---------------------------------------------------------------------------
# 通用操作: delete / list_symbols / list_data_types / get_info
# ---------------------------------------------------------------------------


class TestCommonOperations:
    def test_delete(self, store):
        df = pd.DataFrame({
            "date": ["2024-01-02"], "open": [10.0], "high": [10.5],
            "low": [9.8], "close": [10.3], "volume": [100000], "amount": [1000000.0],
        })
        store.save(df, "DEL", data_type="history")
        assert store.load("DEL", data_type="history") is not None
        assert store.delete("DEL", data_type="history") is True
        assert store.load("DEL", data_type="history") is None

    def test_delete_missing(self, store):
        assert store.delete("NOTEXIST", data_type="history") is False

    def test_list_symbols(self, store):
        df = pd.DataFrame({
            "date": ["2024-01-02"], "open": [10.0], "high": [10.5],
            "low": [9.8], "close": [10.3], "volume": [100000], "amount": [1000000.0],
        })
        store.save(df, "AAPL", data_type="history")
        store.save(df, "GOOG", data_type="history")
        symbols = store.list_symbols(data_type="history")
        assert "AAPL" in symbols
        assert "GOOG" in symbols

    def test_list_data_types(self, store):
        df = pd.DataFrame({
            "date": ["2024-01-02"], "open": [10.0], "high": [10.5],
            "low": [9.8], "close": [10.3], "volume": [100000], "amount": [1000000.0],
        })
        store.save(df, "AAPL", data_type="history")

        fin_df = pd.DataFrame({"report_date": ["2024-01-01"], "revenue": [100.0]})
        store.save(fin_df, "AAPL", data_type="financial")

        types = store.list_data_types(symbol="AAPL")
        assert "history" in types
        assert "financial" in types

    def test_list_data_types_no_symbol(self, store):
        df = pd.DataFrame({
            "date": ["2024-01-02"], "open": [10.0], "high": [10.5],
            "low": [9.8], "close": [10.3], "volume": [100000], "amount": [1000000.0],
        })
        store.save(df, "AAPL", data_type="history")
        types = store.list_data_types()
        assert "history" in types

    def test_list_symbols_empty(self, store):
        assert store.list_symbols(data_type="history") == []

    def test_get_info(self, store):
        df = pd.DataFrame({
            "date": ["2024-01-02"], "open": [10.0], "high": [10.5],
            "low": [9.8], "close": [10.3], "volume": [100000], "amount": [1000000.0],
        })
        store.save(df, "INFO", data_type="history")
        info = store.get_info("INFO", data_type="history")
        assert info is not None
        assert info["row_count"] == 1
        assert info["storage_key"] == "kline/INFO"

    def test_get_info_missing(self, store):
        assert store.get_info("NOTEXIST", data_type="history") is None

    def test_unknown_data_type_raises(self, store):
        df = pd.DataFrame({"a": [1]})
        with pytest.raises(ValueError, match="未知数据类型"):
            store.save(df, "X", data_type="unknown_type")
