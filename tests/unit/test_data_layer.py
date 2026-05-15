"""
Unit tests for the data layer: TdxDataSource, DataService.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


# ===========================================================================
# TdxDataSource (mocked)
# ===========================================================================

class TestTdxDataSource:
    def test_fetch_history_delegates(self):
        from app.data.sources.tdxdata_source import TdxDataSource

        source = TdxDataSource.__new__(TdxDataSource)
        mock_api = MagicMock()
        mock_api.fetch_hybrid.return_value = pd.DataFrame({"close": [10]})
        source._api = mock_api
        source._connected = True
        source._server = None
        source._timeout = 15
        source._tdxdir = None

        result = source.fetch_history(
            stock_list=["600519"],
            start_date="2024-01-01",
            end_date="2024-06-30",
        )
        mock_api.fetch_hybrid.assert_called_once()
        assert len(result) == 1

    def test_fetch_realtime_delegates(self):
        from app.data.sources.tdxdata_source import TdxDataSource

        source = TdxDataSource.__new__(TdxDataSource)
        mock_api = MagicMock()
        mock_api.fetch_realtime.return_value = pd.DataFrame({"close": [10]})
        source._api = mock_api
        source._connected = True
        source._server = None
        source._timeout = 15
        source._tdxdir = None

        result = source.fetch_realtime(stock_list=["600519"])
        mock_api.fetch_realtime.assert_called_once()

    def test_close(self):
        from app.data.sources.tdxdata_source import TdxDataSource

        source = TdxDataSource.__new__(TdxDataSource)
        mock_api = MagicMock()
        source._api = mock_api
        source._connected = True
        source._server = None
        source._timeout = 15
        source._tdxdir = None

        source.close()
        mock_api.close.assert_called_once()
        assert source._connected is False

    def test_validate_connection_success(self):
        from app.data.sources.tdxdata_source import TdxDataSource

        source = TdxDataSource.__new__(TdxDataSource)
        source._api = MagicMock()
        source._connected = True
        source._server = None
        source._timeout = 15
        source._tdxdir = None

        assert source.validate_connection() is True

    def test_validate_connection_failure(self):
        from app.data.sources.tdxdata_source import TdxDataSource

        source = TdxDataSource.__new__(TdxDataSource)
        source._api = None
        source._connected = False
        source._server = None
        source._timeout = 15
        source._tdxdir = None

        with patch.object(source, "_ensure_api", side_effect=Exception("fail")):
            assert source.validate_connection() is False

    def test_context_manager(self):
        from app.data.sources.tdxdata_source import TdxDataSource

        source = TdxDataSource.__new__(TdxDataSource)
        mock_api = MagicMock()
        source._api = mock_api
        source._connected = True
        source._server = None
        source._timeout = 15
        source._tdxdir = None

        with source:
            pass
        mock_api.close.assert_called_once()


# ===========================================================================
# DataService (mocked source)
# ===========================================================================

@pytest.fixture
def data_svc():
    """Create a DataService with mocked source."""
    from app.services.data_service import DataService

    svc = DataService()
    # Replace source with mock
    mock_source = MagicMock()
    svc._source = mock_source
    yield svc
    svc.close()


class TestDataServiceFetch:
    def test_get_history_with_mock(self, data_svc):
        mock_df = pd.DataFrame({
            "stock_code": ["600519"],
            "date": ["2024-01-02"],
            "open": [1700.0],
            "high": [1710.0],
            "low": [1695.0],
            "close": [1705.0],
            "volume": [10000],
        })
        with patch.object(data_svc.source, "fetch_history", return_value=mock_df):
            df = data_svc.get_history(
                symbols=["600519"],
                start_date="2024-01-01",
                end_date="2024-01-31",
                use_cache=False,
            )
            assert len(df) == 1
            assert df.iloc[0]["close"] == 1705.0

    def test_get_realtime_with_mock(self, data_svc):
        mock_df = pd.DataFrame({"stock_code": ["600519"], "close": [1705.0]})
        with patch.object(data_svc.source, "fetch_realtime", return_value=mock_df):
            df = data_svc.get_realtime(["600519"], use_cache=False)
            assert len(df) == 1

    def test_get_factor_with_mock(self, data_svc, tmp_path):
        mock_df = pd.DataFrame({
            "date": ["2024-01-15", "2024-01-16"],
            "factor": [1.05, 1.0],
        })
        from app.services.data_service import DataService
        DataService._FACTOR_CACHE_PATH = tmp_path / "factors.json"

        with patch.object(data_svc.source, "fetch_factor", return_value=mock_df):
            df = data_svc.get_factor("600519", adjust="qfq", use_cache=False)
            assert len(df) == 2

    def test_get_stats(self, data_svc):
        stats = data_svc.get_stats()
        assert stats["source_connected"] is True

    def test_close_and_context_manager(self):
        from app.services.data_service import DataService

        svc = DataService()
        mock_source = MagicMock()
        svc._source = mock_source

        with svc as s:
            assert s is svc
        mock_source.close.assert_called_once()
