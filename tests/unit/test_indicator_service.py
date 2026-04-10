"""
IndicatorService additional unit tests covering uncovered lines.

原则：真实环境优先于 mock
- 自定义指标使用真实脚本文件测试
- 仅在必要时 mock get_settings（设置自定义指标路径）
"""

from pathlib import Path
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
def custom_indicator_dir(tmp_path):
    d = tmp_path / "custom_indicators"
    d.mkdir()
    indicator_script = d / "my_custom.py"
    indicator_script.write_text(
        "def calculate(df, period=14):\n"
        "    return df.assign(custom_result=df['close'] * period)\n"
    )
    return d


@pytest.fixture
def svc():
    return IndicatorService()


class TestCalculateUnsupportedInput:
    def test_calculate_unknown_indicator(self, svc, sample_df):
        with pytest.raises(ValueError, match="Unknown indicator"):
            svc.calculate("nonexistent_indicator_xyz", sample_df, use_cache=False)


class TestCalculateWithCache:
    def test_calculate_caches_result(self, svc, sample_df):
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
    def test_list_indicators_empty_custom(self, svc, custom_indicator_dir):
        with patch("app.services.indicator_service.list_custom_indicators", return_value=[]):
            result = svc.list_indicators()
            assert len(result) >= len(INDICATOR_REGISTRY)
            assert all("name" in r for r in result)

    def test_list_indicators_with_real_custom(self, svc, custom_indicator_dir):
        with patch("app.services.indicator_service.list_custom_indicators") as mock_list:
            mock_list.return_value = [{
                "name": "my_custom",
                "description": "custom test indicator",
                "path": str(custom_indicator_dir / "my_custom.py"),
            }]
            result = svc.list_indicators()
            custom_entries = [r for r in result if r["name"] == "my_custom"]
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
    def test_run_custom_indicator_real_script(self, svc, sample_df, custom_indicator_dir):
        result = svc.run_custom_indicator(
            str(custom_indicator_dir / "my_custom.py"), sample_df, params={"period": 2}
        )
        assert result is not None
        assert "custom_result" in result.columns
        assert result["custom_result"].iloc[0] == sample_df["close"].iloc[0] * 2

    def test_run_custom_indicator_nonexistent(self, svc, sample_df):
        result = svc.run_custom_indicator("/nonexistent/script.py", sample_df)
        assert result is None

    def test_run_custom_indicator_error_script(self, svc, sample_df, custom_indicator_dir):
        err_script = custom_indicator_dir / "error_ind.py"
        err_script.write_text("def calculate(df):\n    raise RuntimeError('indicator boom')\n")
        result = svc.run_custom_indicator(str(err_script), sample_df)
        assert result is None
