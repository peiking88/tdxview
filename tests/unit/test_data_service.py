"""
DataService additional unit tests covering uncovered lines.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.services.data_service import DataService


@pytest.fixture
def mock_source():
    src = MagicMock()
    src.validate_connection.return_value = True
    src.fetch_history.return_value = pd.DataFrame({
        "stock_code": ["AAPL"] * 3,
        "date": ["2024-01-02", "2024-01-03", "2024-01-04"],
        "open": [180.0, 182.0, 183.0],
        "high": [185.0, 186.0, 187.0],
        "low": [178.0, 180.0, 181.0],
        "close": [183.0, 184.0, 185.0],
        "volume": [10000, 11000, 12000],
    })
    src.fetch_realtime.return_value = pd.DataFrame({
        "stock_code": ["AAPL"],
        "price": [185.0],
        "volume": [5000],
    })
    src.fetch_tick.return_value = pd.DataFrame({
        "price": [185.0, 185.1, 185.2],
        "volume": [100, 200, 150],
    })
    src.fetch_financial.return_value = pd.DataFrame({"revenue": [100]})
    src.fetch_f10.return_value = {"summary": pd.DataFrame({"item": ["EPS"], "value": [5.0]})}
    src.fetch_basic.return_value = pd.DataFrame({"name": ["Apple Inc."]})
    src.fetch_local.return_value = pd.DataFrame({"close": [185.0]})
    src.fetch_hybrid.return_value = pd.DataFrame({"close": [185.0, 186.0]})
    src.close.return_value = None
    return src


@pytest.fixture
def svc(mock_source, tmp_path):
    with patch("app.services.data_service.TdxDataSource", return_value=mock_source):
        with patch("app.services.data_service.get_settings") as mock_settings:
            s = MagicMock()
            s.tdxdata.timeout = 10
            s.tdxdata.retry_count = 3
            mock_settings.return_value = s
            service = DataService()
    service._db = MagicMock()
    service._parquet = MagicMock()
    cache_mock = MagicMock()
    cache_mock.get.return_value = None
    service._cache = cache_mock
    service._source = mock_source
    return service


class TestGetTick:
    def test_get_tick_basic(self, svc, mock_source):
        df = svc.get_tick("AAPL")
        assert not df.empty
        mock_source.fetch_tick.assert_called_once()

    def test_get_tick_with_date(self, svc, mock_source):
        df = svc.get_tick("AAPL", date="2024-01-15")
        assert not df.empty
        mock_source.fetch_tick.assert_called_once_with(stock_code="AAPL", date="2024-01-15")

    def test_get_tick_no_cache(self, svc, mock_source):
        df = svc.get_tick("AAPL", use_cache=False)
        assert not df.empty

    def test_get_tick_cached(self, svc, mock_source):
        svc._cache.get.return_value = {"price": [100.0], "volume": [50]}
        df = svc.get_tick("AAPL")
        assert not df.empty
        mock_source.fetch_tick.assert_not_called()


class TestFinancialData:
    def test_get_financial(self, svc, mock_source):
        df = svc.get_financial("AAPL")
        assert not df.empty
        mock_source.fetch_financial.assert_called_once_with(stock_code="AAPL")

    def test_get_f10(self, svc, mock_source):
        result = svc.get_f10("AAPL")
        assert "summary" in result
        mock_source.fetch_f10.assert_called_once()

    def test_get_f10_with_sections(self, svc, mock_source):
        result = svc.get_f10("AAPL", sections=["summary"])
        assert "summary" in result

    def test_get_basic(self, svc, mock_source):
        df = svc.get_basic("AAPL")
        assert not df.empty
        mock_source.fetch_basic.assert_called_once()

    def test_get_basic_with_date(self, svc, mock_source):
        df = svc.get_basic("AAPL", date="2024-01-01")
        assert not df.empty


class TestLocalHybrid:
    def test_get_local(self, svc, mock_source):
        df = svc.get_local("AAPL")
        assert not df.empty
        mock_source.fetch_local.assert_called_once()

    def test_get_local_with_params(self, svc, mock_source):
        df = svc.get_local("AAPL", period="5m", dividend_type="front")
        mock_source.fetch_local.assert_called_once_with(
            stock_code="AAPL", period="5m", tdxdir=None, dividend_type="front"
        )

    def test_get_hybrid(self, svc, mock_source):
        df = svc.get_hybrid("AAPL")
        assert not df.empty
        mock_source.fetch_hybrid.assert_called_once()

    def test_get_hybrid_with_params(self, svc, mock_source):
        df = svc.get_hybrid(
            "AAPL", start_date="2024-01-01", end_date="2024-01-31",
            period="1d", dividend_type="front"
        )
        mock_source.fetch_hybrid.assert_called_once()


class TestDataSourceCRUD:
    def test_add_data_source(self, svc):
        svc._db.fetch_one.return_value = (1,)
        result = svc.add_data_source("test", "tdxdata", {"timeout": 10})
        assert result == 1

    def test_add_data_source_no_row(self, svc):
        svc._db.fetch_one.return_value = None
        result = svc.add_data_source("test", "tdxdata", {"timeout": 10})
        assert result == -1

    def test_update_data_source(self, svc):
        result = svc.update_data_source(1, name="updated", enabled=False)
        assert result is True

    def test_update_data_source_no_updates(self, svc):
        result = svc.update_data_source(1)
        assert result is False

    def test_delete_data_source(self, svc):
        result = svc.delete_data_source(1)
        assert result is True

    def test_get_data_source(self, svc):
        svc._db.fetch_one.return_value = (1, "test", "tdxdata", '{"timeout": 10}', True, 1)
        result = svc.get_data_source(1)
        assert result is not None
        assert result["name"] == "test"

    def test_get_data_source_not_found(self, svc):
        svc._db.fetch_one.return_value = None
        result = svc.get_data_source(999)
        assert result is None

    def test_list_data_sources(self, svc):
        svc._db.fetch_all.return_value = [
            (1, "test", "tdxdata", '{"timeout": 10}', True, 1)
        ]
        result = svc.list_data_sources()
        assert len(result) == 1

    def test_list_data_sources_empty(self, svc):
        svc._db.fetch_all.return_value = []
        result = svc.list_data_sources()
        assert result == []


class TestFetchAndStore:
    def test_fetch_and_store_empty(self, svc, mock_source):
        mock_source.fetch_history.return_value = pd.DataFrame()
        result = svc.fetch_and_store(["AAPL"], "2024-01-01", "2024-01-31")
        assert result == {}

    def test_fetch_and_store_single_symbol_no_stock_code(self, svc, mock_source):
        df = pd.DataFrame({"close": [185.0]})
        mock_source.fetch_history.return_value = df
        svc._parquet.save.return_value = Path("/tmp/test.parquet")
        result = svc.fetch_and_store(["AAPL"], "2024-01-01", "2024-01-31")
        assert "AAPL" in result


class TestParallel:
    def test_parallel_get_history_error_handling(self, svc, mock_source):
        call_count = [0]

        def mock_get_history(symbols, start_date, end_date, **kwargs):
            call_count[0] += 1
            if "GOOGL" in symbols:
                raise ConnectionError("timeout")
            return pd.DataFrame({"close": [185.0]})

        svc.get_history = mock_get_history
        result = svc.parallel_get_history(["AAPL", "GOOGL"], "2024-01-01", "2024-01-31")
        assert "AAPL" in result
        assert "GOOGL" in result
        assert result["GOOGL"].empty

    def test_parallel_fetch_and_store(self, svc, mock_source):
        svc._parquet.save.return_value = Path("/tmp/test.parquet")
        result = svc.parallel_fetch_and_store(
            ["AAPL"], "2024-01-01", "2024-01-31"
        )
        assert isinstance(result, dict)


class TestBatchQuery:
    def test_batch_query_unknown_method(self, svc):
        with pytest.raises(ValueError, match="Unknown method"):
            svc.batch_query_symbols(["AAPL"], "nonexistent_method")

    def test_batch_query_with_exception(self, svc, mock_source):
        def mock_get_history(**kwargs):
            raise Exception("fail")
        svc.get_history = mock_get_history
        result = svc.batch_query_symbols(
            ["AAPL"], "get_history",
            start_date="2024-01-01", end_date="2024-01-31"
        )
        assert result["AAPL"] is None

    def test_batch_query_tick(self, svc, mock_source):
        result = svc.batch_query_symbols(
            ["AAPL"], "get_tick",
            date="2024-01-01"
        )
        assert "AAPL" in result


class TestContextManager:
    def test_context_manager(self, svc, mock_source):
        svc._source = None
        with svc:
            pass
        svc._source = mock_source
        with svc:
            pass
        mock_source.close.assert_called()

    def test_close_with_source(self, svc, mock_source):
        svc._source = mock_source
        svc.close()
        mock_source.close.assert_called_once()


class TestGetStats:
    def test_get_stats_no_source(self, svc):
        svc._source = None
        stats = svc.get_stats()
        assert stats["source_connected"] is False
        assert "cache" in stats

    def test_get_stats_with_source(self, svc, mock_source):
        svc._source = mock_source
        stats = svc.get_stats()
        assert stats["source_connected"] is True
