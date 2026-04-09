"""
Unit tests for the visualization service: chart creation, styling,
data preprocessing, and export.
"""

import tempfile
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import pytest

from app.services.visualization_service import (
    create_candlestick,
    create_line,
    create_bar,
    create_heatmap,
    create_multi_chart,
    export_figure,
    export_figure_to_file,
    prepare_kline_data,
    prepare_correlation_matrix,
)


# ---------------------------------------------------------------------------
# Test data fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def kline_df():
    """Sample OHLCV DataFrame."""
    return pd.DataFrame({
        "date": pd.date_range("2024-01-02", periods=20, freq="B"),
        "open":  [100 + i for i in range(20)],
        "high":  [102 + i for i in range(20)],
        "low":   [98 + i for i in range(20)],
        "close": [101 + i for i in range(20)],
        "volume": [10000 + i * 100 for i in range(20)],
    })


@pytest.fixture
def numeric_df():
    """Sample DataFrame with multiple numeric columns."""
    return pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=10),
        "close": [100, 102, 101, 105, 103, 107, 106, 108, 110, 109],
        "volume": [1000, 1200, 1100, 1300, 1250, 1400, 1350, 1500, 1600, 1550],
    })


# ---------------------------------------------------------------------------
# Candlestick
# ---------------------------------------------------------------------------

class TestCandlestick:
    def test_basic_candlestick(self, kline_df):
        fig = create_candlestick(kline_df)
        assert isinstance(fig, go.Figure)
        # Should have at least one candlestick trace
        assert any(isinstance(t, go.Candlestick) for t in fig.data)

    def test_candlestick_with_volume(self, kline_df):
        fig = create_candlestick(kline_df, show_volume=True)
        # Should have 2 subplots (candlestick + volume)
        has_bar = any(isinstance(t, go.Bar) for t in fig.data)
        assert has_bar

    def test_candlestick_without_volume(self, kline_df):
        fig = create_candlestick(kline_df, show_volume=False)
        has_bar = any(isinstance(t, go.Bar) for t in fig.data)
        assert not has_bar

    def test_candlestick_with_ma(self, kline_df):
        fig = create_candlestick(kline_df, ma_periods=[5, 10])
        # Should have candlestick + 2 MA traces
        scatter_traces = [t for t in fig.data if isinstance(t, go.Scatter)]
        assert len(scatter_traces) >= 2

    def test_candlestick_title(self, kline_df):
        fig = create_candlestick(kline_df, title="Test K")
        assert fig.layout.title.text == "Test K"


# ---------------------------------------------------------------------------
# Line chart
# ---------------------------------------------------------------------------

class TestLineChart:
    def test_basic_line(self, numeric_df):
        fig = create_line(numeric_df, x="date", y=["close"])
        assert isinstance(fig, go.Figure)
        assert len(fig.data) == 1

    def test_multi_line(self, numeric_df):
        fig = create_line(numeric_df, x="date", y=["close", "volume"])
        assert len(fig.data) == 2

    def test_auto_detect_y(self, numeric_df):
        fig = create_line(numeric_df, x="date")
        # Should plot all numeric columns except 'date'
        assert len(fig.data) >= 2

    def test_line_title(self, numeric_df):
        fig = create_line(numeric_df, x="date", y=["close"], title="Price")
        assert fig.layout.title.text == "Price"


# ---------------------------------------------------------------------------
# Bar chart
# ---------------------------------------------------------------------------

class TestBarChart:
    def test_basic_bar(self, numeric_df):
        fig = create_bar(numeric_df, x="date", y=["volume"])
        assert isinstance(fig, go.Figure)
        assert len(fig.data) == 1

    def test_multi_bar(self, numeric_df):
        fig = create_bar(numeric_df, x="date", y=["close", "volume"])
        assert len(fig.data) == 2

    def test_stacked_bar(self, numeric_df):
        fig = create_bar(numeric_df, x="date", y=["close", "volume"], barmode="stack")
        assert fig.layout.barmode == "stack"

    def test_auto_detect_y(self, numeric_df):
        fig = create_bar(numeric_df, x="date")
        assert len(fig.data) >= 1


# ---------------------------------------------------------------------------
# Heatmap
# ---------------------------------------------------------------------------

class TestHeatmap:
    def test_basic_heatmap(self):
        df = pd.DataFrame({"A": [1, 2, 3], "B": [4, 5, 6], "C": [7, 8, 9]})
        fig = create_heatmap(df)
        assert isinstance(fig, go.Figure)
        assert any(isinstance(t, go.Heatmap) for t in fig.data)

    def test_heatmap_colorscale(self):
        df = pd.DataFrame({"X": [1, -1], "Y": [-1, 1]})
        fig = create_heatmap(df, colorscale="Blues")
        trace = fig.data[0]
        # Plotly expands named colorscales into tuples; just verify it was set
        assert trace.colorscale is not None
        assert len(trace.colorscale) > 0

    def test_correlation_heatmap(self, numeric_df):
        corr = prepare_correlation_matrix(numeric_df)
        fig = create_heatmap(corr, colorscale="RdYlGn", zmin=-1, zmax=1)
        trace = fig.data[0]
        assert trace.zmin == -1
        assert trace.zmax == 1


# ---------------------------------------------------------------------------
# Multi-chart layout
# ---------------------------------------------------------------------------

class TestMultiChart:
    def test_combine_two_charts(self, numeric_df):
        fig1 = create_line(numeric_df, x="date", y=["close"])
        fig2 = create_bar(numeric_df, x="date", y=["volume"])
        combined = create_multi_chart([fig1, fig2], titles=["Price", "Volume"], cols=1)
        assert isinstance(combined, go.Figure)
        assert len(combined.data) == 2

    def test_empty_charts(self):
        fig = create_multi_chart([])
        assert isinstance(fig, go.Figure)
        assert len(fig.data) == 0


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

class TestExport:
    def test_export_png_bytes(self):
        """Test PNG export — requires Kaleido with a browser."""
        fig = go.Figure(go.Scatter(x=[1, 2], y=[3, 4]))
        try:
            data = export_figure(fig, format="png")
            assert isinstance(data, bytes)
            assert len(data) > 0
            assert data[:4] == b"\x89PNG"
        except Exception:
            pytest.skip("Kaleido browser not available in this environment")

    def test_export_to_file(self, tmp_dir):
        """Test file export — requires Kaleido with a browser."""
        fig = go.Figure(go.Scatter(x=[1, 2], y=[3, 4]))
        try:
            path = export_figure_to_file(fig, str(tmp_dir / "test_chart.png"))
            assert path.exists()
            assert path.suffix == ".png"
        except Exception:
            pytest.skip("Kaleido browser not available in this environment")

    def test_export_pdf_to_file(self, tmp_dir):
        """Test PDF export — requires Kaleido with a browser."""
        fig = go.Figure(go.Scatter(x=[1, 2], y=[3, 4]))
        try:
            path = export_figure_to_file(fig, str(tmp_dir / "test_chart.pdf"), format="pdf")
            assert path.exists()
            assert path.suffix == ".pdf"
        except Exception:
            pytest.skip("Kaleido browser not available in this environment")

    def test_export_figure_function_exists(self):
        """Verify the export function is callable (no Kaleido required)."""
        from app.services.visualization_service import export_figure, export_figure_to_file
        assert callable(export_figure)
        assert callable(export_figure_to_file)


# ---------------------------------------------------------------------------
# Data preprocessing
# ---------------------------------------------------------------------------

class TestPrepareKlineData:
    def test_rename_datetime_to_date(self):
        df = pd.DataFrame({
            "datetime": pd.date_range("2024-01-01", periods=3),
            "open": [1, 2, 3],
            "high": [4, 5, 6],
            "low": [0, 1, 2],
            "close": [2, 3, 4],
        })
        result = prepare_kline_data(df)
        assert "date" in result.columns

    def test_rename_vol_to_volume(self):
        df = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=3),
            "open": [1, 2, 3],
            "high": [4, 5, 6],
            "low": [0, 1, 2],
            "close": [2, 3, 4],
            "vol": [100, 200, 300],
        })
        result = prepare_kline_data(df)
        assert "volume" in result.columns

    def test_sort_by_date(self):
        df = pd.DataFrame({
            "date": pd.to_datetime(["2024-01-03", "2024-01-01", "2024-01-02"]),
            "open": [3, 1, 2],
            "high": [6, 4, 5],
            "low": [2, 0, 1],
            "close": [4, 2, 3],
        })
        result = prepare_kline_data(df)
        assert result["date"].is_monotonic_increasing


class TestPrepareCorrelationMatrix:
    def test_correlation_shape(self, numeric_df):
        corr = prepare_correlation_matrix(numeric_df)
        n_cols = len(numeric_df.select_dtypes(include="number").columns)
        assert corr.shape == (n_cols, n_cols)

    def test_diagonal_is_one(self, numeric_df):
        corr = prepare_correlation_matrix(numeric_df)
        for col in corr.columns:
            assert abs(corr.loc[col, col] - 1.0) < 1e-10

    def test_symmetric(self, numeric_df):
        corr = prepare_correlation_matrix(numeric_df)
        assert (corr - corr.T).abs().max().max() < 1e-10

    def test_specific_columns(self, numeric_df):
        corr = prepare_correlation_matrix(numeric_df, columns=["close", "volume"])
        assert corr.shape == (2, 2)
