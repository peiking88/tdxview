"""
Tests for data import, incremental import, reimport, and import status tracking.
"""

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from app.data.models.import_record import DataType, ImportStatus
from app.services.data_service import DataService


def _create_mock_source():
    src = MagicMock()
    src.validate_connection.return_value = True
    src.fetch_history.return_value = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=10, freq="D"),
        "open": np.random.uniform(10, 30, 10),
        "high": np.random.uniform(11, 33, 10),
        "low": np.random.uniform(9, 27, 10),
        "close": np.random.uniform(10, 32, 10),
        "volume": np.random.randint(100_000, 1_000_000, 10),
        "stock_code": ["600519"] * 10,
    })
    src.fetch_realtime.return_value = pd.DataFrame({
        "stock_code": ["600519"],
        "price": [1705.0],
        "volume": [10000],
    })
    src.fetch_tick.return_value = pd.DataFrame({
        "price": [15.0, 15.01],
        "volume": [100, 200],
        "date": ["2024-01-15", "2024-01-15"],
    })
    src.fetch_financial.return_value = pd.DataFrame({
        "report_date": ["2024-03-31"],
        "revenue": [1000000],
        "net_profit": [200000],
    })
    src.fetch_f10.return_value = {
        "summary": pd.DataFrame({"item": ["EPS"], "value": [5.0]}),
        "shareholder": pd.DataFrame({"name": ["A"], "pct": [10.0]}),
    }
    src.fetch_basic.return_value = pd.DataFrame({
        "ex_date": ["2024-06-15"],
        "dividend": [0.5],
    })
    src.close.return_value = None
    return src


def _init_test_db(db_path):
    import duckdb
    conn = duckdb.connect(db_path)
    conn.execute("CREATE SEQUENCE IF NOT EXISTS data_sources_id_seq START 1")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS data_sources (
            id INTEGER PRIMARY KEY DEFAULT nextval('data_sources_id_seq'),
            name TEXT NOT NULL, type TEXT NOT NULL, config TEXT NOT NULL,
            priority INTEGER DEFAULT 1, enabled BOOLEAN DEFAULT TRUE,
            last_checked TIMESTAMP, error_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS data_imports (
            symbol TEXT NOT NULL,
            data_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'success',
            record_count INTEGER DEFAULT 0,
            start_date DATE,
            end_date DATE,
            storage_key TEXT,
            file_size_bytes INTEGER,
            error_message TEXT,
            import_duration_ms INTEGER,
            imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_data_imports_symbol_type ON data_imports(symbol, data_type)")
    conn.commit()
    conn.close()


@pytest.fixture
def svc(tmp_path):
    from app.config.settings import get_settings
    settings = get_settings()

    db_path = str(tmp_path / "test.duckdb")

    orig_db = settings.database.duckdb_path

    settings.database.duckdb_path = db_path

    _init_test_db(db_path)

    mock_source = _create_mock_source()
    with patch("app.services.data_service.TdxDataSource", return_value=mock_source):
        service = DataService()
    service._source = mock_source

    yield service, mock_source

    service.close()
    settings.database.duckdb_path = orig_db


# ======================================================================
# import_data
# ======================================================================

class TestImportData:
    def test_import_history(self, svc):
        s, src = svc
        record = s.import_data("600519", "history", start_date="2024-01-01", end_date="2024-01-31")
        assert record.status == ImportStatus.SUCCESS
        assert record.record_count > 0
        assert record.storage_key is not None
        assert record.import_duration_ms is not None

    def test_import_financial(self, svc):
        s, src = svc
        record = s.import_data("600519", "financial")
        assert record.status == ImportStatus.SUCCESS
        assert record.record_count == 1
        assert record.storage_key is not None

    def test_import_f10(self, svc):
        s, src = svc
        record = s.import_data("600519", "f10")
        assert record.status == ImportStatus.SUCCESS
        assert record.record_count == 2  # summary + shareholder
        assert record.storage_key is not None

    def test_import_basic(self, svc):
        s, src = svc
        record = s.import_data("600519", "basic")
        assert record.status == ImportStatus.SUCCESS
        assert record.record_count == 1

    def test_import_tick(self, svc):
        s, src = svc
        record = s.import_data("600519", "tick", date="2024-01-15")
        assert record.status == ImportStatus.SUCCESS
        assert record.record_count == 2

    def test_import_realtime(self, svc):
        s, src = svc
        record = s.import_data("600519", "realtime")
        assert record.status == ImportStatus.SUCCESS

    def test_import_failure(self, svc):
        s, src = svc
        src.fetch_financial.side_effect = ConnectionError("server down")
        record = s.import_data("600519", "financial")
        assert record.status == ImportStatus.FAILED
        assert "server down" in record.error_message

    def test_import_unknown_type(self, svc):
        s, src = svc
        with pytest.raises(Exception):
            s.import_data("600519", "unknown_type")


# ======================================================================
# import status tracking
# ======================================================================

class TestImportStatus:
    def test_get_last_import(self, svc):
        s, src = svc
        s.import_data("600519", "financial")
        record = s.get_last_import("600519", "financial")
        assert record is not None
        assert record.symbol == "600519"
        assert record.data_type == DataType.FINANCIAL

    def test_get_last_import_not_found(self, svc):
        s, src = svc
        record = s.get_last_import("999999", "financial")
        assert record is None

    def test_get_import_status_all(self, svc):
        s, src = svc
        s.import_data("600519", "financial")
        s.import_data("600519", "basic")
        records = s.get_import_status()
        assert len(records) == 2

    def test_get_import_status_filter_symbol(self, svc):
        s, src = svc
        s.import_data("600519", "financial")
        s.import_data("000001", "financial")
        records = s.get_import_status(symbol="600519")
        assert all(r.symbol == "600519" for r in records)

    def test_get_import_status_filter_type(self, svc):
        s, src = svc
        s.import_data("600519", "financial")
        s.import_data("600519", "basic")
        records = s.get_import_status(data_type="financial")
        assert all(r.data_type == DataType.FINANCIAL for r in records)

    def test_upsert_replaces_existing(self, svc):
        s, src = svc
        r1 = s.import_data("600519", "financial")
        assert r1.record_count == 1
        src.fetch_financial.return_value = pd.DataFrame({
            "revenue": range(10),
        })
        r2 = s.import_data("600519", "financial")
        records = s.get_import_status(symbol="600519", data_type="financial")
        assert len(records) == 1  # replaced, not appended


# ======================================================================
# incremental import
# ======================================================================

class TestIncrementalImport:
    def test_no_history_full_import(self, svc):
        s, src = svc
        record = s.incremental_import("600519", "financial")
        assert record.status == ImportStatus.SUCCESS

    def test_incremental_history_new_data(self, svc):
        s, src = svc
        # First import
        s.import_data("600519", "history", start_date="2024-01-01", end_date="2024-01-10")

        # Set up mock for incremental data
        src.fetch_history.return_value = pd.DataFrame({
            "date": pd.date_range("2024-01-11", periods=5, freq="D"),
            "open": [10.0] * 5,
            "high": [11.0] * 5,
            "low": [9.0] * 5,
            "close": [10.5] * 5,
            "volume": [100000] * 5,
            "stock_code": ["600519"] * 5,
        })

        record = s.incremental_import("600519", "history")
        assert record.status == ImportStatus.SUCCESS
        # The incremental call should use start_date after last end_date
        call_args = src.fetch_history.call_args
        assert call_args is not None

    def test_incremental_history_already_uptodate(self, svc):
        s, src = svc
        # Import with future end_date
        future = datetime.now().strftime("%Y-%m-%d")
        src.fetch_history.return_value = pd.DataFrame({
            "date": pd.date_range("2099-01-01", periods=5, freq="D"),
            "open": [10.0] * 5,
            "high": [11.0] * 5,
            "low": [9.0] * 5,
            "close": [10.5] * 5,
            "volume": [100000] * 5,
            "stock_code": ["600519"] * 5,
        })
        first = s.import_data("600519", "history", start_date="2099-01-01", end_date=future)

        # Reset for incremental
        call_count_before = src.fetch_history.call_count
        record = s.incremental_import("600519", "history")
        # Should return the existing record without new fetch
        assert src.fetch_history.call_count == call_count_before

    def test_incremental_financial_overwrites(self, svc):
        s, src = svc
        s.import_data("600519", "financial")
        record = s.incremental_import("600519", "financial")
        assert record.status == ImportStatus.SUCCESS


# ======================================================================
# reimport
# ======================================================================

class TestReimportData:
    def test_reimport_financial(self, svc):
        s, src = svc
        # First import
        r1 = s.import_data("600519", "financial")
        assert r1.status == ImportStatus.SUCCESS

        # New data
        src.fetch_financial.return_value = pd.DataFrame({
            "revenue": range(5),
            "net_profit": range(5),
        })

        # Reimport
        r2 = s.reimport_data("600519", "financial")
        assert r2.status == ImportStatus.SUCCESS
        assert r2.record_count == 5

        # Should have replaced the record
        records = s.get_import_status(symbol="600519", data_type="financial")
        assert len(records) == 1

    def test_reimport_clears_store(self, svc):
        s, src = svc
        r1 = s.import_data("600519", "financial")
        assert r1.storage_key is not None

        src.fetch_financial.return_value = pd.DataFrame({"revenue": [999]})
        s.reimport_data("600519", "financial")

        # New data should exist in store
        loaded = s.load_from_parquet("600519", data_type="financial")
        assert loaded is not None
        assert loaded.iloc[0]["revenue"] == 999

    def test_reimport_history(self, svc):
        s, src = svc
        s.import_data("600519", "history", start_date="2024-01-01", end_date="2024-01-31")
        src.fetch_history.return_value = pd.DataFrame({
            "date": pd.date_range("2024-06-01", periods=3, freq="D"),
            "close": [100.0] * 3,
            "stock_code": ["600519"] * 3,
        })
        r = s.reimport_data("600519", "history", start_date="2024-06-01", end_date="2024-06-30")
        assert r.status == ImportStatus.SUCCESS


# ======================================================================
# Dividend type mapping
# ======================================================================

class TestDividendMapping:
    def test_map_dividend_type(self):
        assert DataService._map_dividend_type("front") == "qfq"
        assert DataService._map_dividend_type("back") == "hfq"
        assert DataService._map_dividend_type("none") == "none"
        assert DataService._map_dividend_type("unknown") == "none"
