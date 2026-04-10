"""
IndicatorService additional unit tests covering uncovered lines.
"""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.services.indicator_service import IndicatorService, INDICATOR_REGISTRY


@pytest.fixture
def sample_df():
    return pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=50, freq="1min" if False else "D"),
        "open": [100 + i for i in range(50)],
        "high": [101 + i for i in range(50)],
        "low": [99 + i for i in range(50)],
        "close": [100.5 + i * 0.5 for i in range(50)],
        "volume": [1000 + i * 10 for i in range(50)],
    })


@pytest.fixture
def svc():
    return IndicatorService()


class TestCalculateUnsupportedInput:
    def test_calculate_unknown_indicator(self, svc, sample_df):
        with pytest.raises(ValueError, match="Unknown indicator"):
            svc.calculate("nonexistent_indicator_xyz", sample_df, use_cache=False)


class TestCalculateWithCache:
    def test_calculate_caches_result(self, svc, sample_df):
        with patch("app.services.indicator_service.get_settings") as mock_settings:
            s = MagicMock()
            s.indicators.cache_ttl = 3600
            mock_settings.return_value = s
            result1 = svc.calculate("sma", sample_df, params={"period": 5}, use_cache=True)
            result2 = svc.calculate("sma", sample_df, params={"period": 5}, use_cache=True)
            assert "sma" in result1
            assert "sma" in result2


class TestAddIndicatorToFigure:
    def test_add_rsi(self, svc, sample_df):
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
        fig = make_subplots(rows=2, cols=1)
        fig = svc.add_indicator_to_figure(fig, "rsi", sample_df, row=2, col=1)
        assert any("RSI" in str(trace.name) for trace in fig.data if trace.name)

    def test_add_bollinger_bands(self, svc, sample_df):
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
        fig = make_subplots(rows=1, cols=1)
        fig = svc.add_indicator_to_figure(fig, "bollinger_bands", sample_df, row=1, col=1)
        assert any("BB" in str(trace.name) for trace in fig.data if trace.name)

    def test_add_obv(self, svc, sample_df):
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
        fig = make_subplots(rows=2, cols=1)
        fig = svc.add_indicator_to_figure(fig, "obv", sample_df, row=2, col=1)
        assert any("OBV" in str(trace.name) for trace in fig.data if trace.name)

    def test_add_vwap(self, svc, sample_df):
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
        fig = make_subplots(rows=1, cols=1)
        fig = svc.add_indicator_to_figure(fig, "vwap", sample_df, row=1, col=1)
        assert any("VWAP" in str(trace.name) for trace in fig.data if trace.name)

    def test_add_rps(self, svc, sample_df):
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
        fig = make_subplots(rows=2, cols=1)
        fig = svc.add_indicator_to_figure(fig, "rps", sample_df, row=2, col=1)
        assert any("RPS" in str(trace.name) for trace in fig.data if trace.name)


class TestListAndGetIndicators:
    def test_list_indicators(self, svc):
        with patch("app.services.indicator_service.list_custom_indicators", return_value=[]):
            result = svc.list_indicators()
            assert len(result) >= len(INDICATOR_REGISTRY)
            assert all("name" in r for r in result)

    def test_list_indicators_with_custom(self, svc):
        custom = [{"name": "custom1", "description": "test", "path": "/tmp/test.py"}]
        with patch("app.services.indicator_service.list_custom_indicators", return_value=custom):
            result = svc.list_indicators()
            custom_entries = [r for r in result if r["name"] == "custom1"]
            assert len(custom_entries) == 1
            assert custom_entries[0]["is_builtin"] is False

    def test_get_indicator_info_builtin(self, svc):
        info = svc.get_indicator_info("sma")
        assert info is not None
        assert info["is_builtin"] is True
        assert info["name"] == "sma"

    def test_get_indicator_info_unknown(self, svc):
        info = svc.get_indicator_info("nonexistent_indicator")
        assert info is None


class TestRunCustomIndicator:
    def test_run_custom_indicator(self, svc, sample_df):
        mock_result = sample_df.copy()
        mock_result["custom_col"] = 1.0
        with patch("app.services.indicator_service.execute_custom_indicator", return_value=mock_result):
            result = svc.run_custom_indicator("/tmp/test.py", sample_df)
            assert result is not None
            assert "custom_col" in result.columns

    def test_run_custom_indicator_with_params(self, svc, sample_df):
        with patch("app.services.indicator_service.execute_custom_indicator", return_value=sample_df) as mock_exec:
            svc.run_custom_indicator("/tmp/test.py", sample_df, params={"period": 10})
            mock_exec.assert_called_once_with("/tmp/test.py", sample_df, {"period": 10})
