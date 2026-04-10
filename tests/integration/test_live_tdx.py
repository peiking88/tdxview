"""
Live network tests — only run when TDX server is reachable.

These tests use the real TdxDataSource and validate actual data
shapes, types, and content from the live server.

Run with:  TDX_LIVE=1 pytest -m live
Skip with: pytest -m "not live"
"""

import pytest

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def live_source(tdx_available, tdx_source):
    if not tdx_available:
        pytest.skip("TDX server not available")
    return tdx_source


class TestLiveConnection:
    def test_validate_connection(self, live_source):
        assert live_source.validate_connection() is True


class TestLiveHistory:
    def test_fetch_history_daily(self, live_source):
        df = live_source.fetch_history(
            stock_list=["000001"],
            start_date="2024-01-02",
            end_date="2024-01-31",
            period="1d",
        )
        assert not df.empty
        assert "close" in df.columns
        assert len(df) >= 10

    def test_fetch_history_multi_symbol(self, live_source):
        df = live_source.fetch_history(
            stock_list=["000001", "600000"],
            start_date="2024-01-02",
            end_date="2024-01-10",
            period="1d",
        )
        assert not df.empty

    def test_fetch_history_returns_dataframe(self, live_source):
        df = live_source.fetch_history(
            stock_list=["000001"],
            start_date="2024-01-02",
            end_date="2024-01-05",
        )
        assert hasattr(df, "columns")
        assert hasattr(df, "empty")


class TestLiveRealtime:
    def test_fetch_realtime(self, live_source):
        df = live_source.fetch_realtime(stock_list=["000001"])
        assert not df.empty
        assert "symbol" in df.columns or "stock_code" in df.columns


class TestLiveTick:
    def test_fetch_tick(self, live_source):
        df = live_source.fetch_tick(stock_code="000001")
        assert df is not None


class TestLiveFinancial:
    def test_fetch_financial(self, live_source):
        df = live_source.fetch_financial(stock_code="000001")
        assert df is not None

    def test_fetch_basic(self, live_source):
        df = live_source.fetch_basic(stock_code="000001")
        assert df is not None


class TestLiveF10:
    def test_fetch_f10(self, live_source):
        result = live_source.fetch_f10(stock_code="000001")
        assert result is not None
        assert isinstance(result, dict)
