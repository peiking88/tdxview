"""
Visualization service — chart creation, styling, and export.

Generates Plotly figures from DataFrames with consistent theming and
provides export to PNG / PDF via Kaleido.
"""

import io
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from app.config.settings import get_settings


# ---------------------------------------------------------------------------
# Default theme helpers
# ---------------------------------------------------------------------------

def _default_layout(**overrides: Any) -> Dict[str, Any]:
    """Return a base layout dict that matches the project's visual identity."""
    layout: Dict[str, Any] = {
        "template": "plotly_white",
        "margin": {"l": 60, "r": 30, "t": 40, "b": 50},
        "autosize": True,
        "height": 500,
        "xaxis": {"showgrid": True, "gridcolor": "#e8e8e8"},
        "yaxis": {"showgrid": True, "gridcolor": "#e8e8e8"},
        "hovermode": "x unified",
    }
    layout.update(overrides)
    return layout


def _volume_colors(opens: pd.Series, closes: pd.Series) -> List[str]:
    """Return per-bar colours: green if close >= open, red otherwise."""
    return [
        "rgba(38,166,91,0.5)" if c >= o else "rgba(234,67,53,0.5)"
        for o, c in zip(opens, closes)
    ]


# ---------------------------------------------------------------------------
# Candlestick (K-line)
# ---------------------------------------------------------------------------

def create_candlestick(
    df: pd.DataFrame,
    title: Optional[str] = None,
    show_volume: bool = True,
    ma_periods: Optional[List[int]] = None,
    bollinger: bool = False,
) -> go.Figure:
    """Create a candlestick chart with optional volume, MA, and Bollinger overlays.

    Expected df columns: date (or datetime), open, high, low, close, volume.
    """
    ma_periods = ma_periods or []
    has_vol = show_volume and "volume" in df.columns

    if has_vol:
        fig = make_subplots(
            rows=2, cols=1, shared_xaxes=True,
            row_heights=[0.75, 0.25],
            vertical_spacing=0.03,
        )
    else:
        fig = go.Figure()

    x_data = df["date"] if "date" in df.columns else df.index

    # --- Candlestick trace ---
    candle = go.Candlestick(
        x=x_data,
        open=df["open"],
        high=df["high"],
        low=df["low"],
        close=df["close"],
        name="K线",
        increasing_line_color="#26a65b",
        decreasing_line_color="#ea4335",
    )
    if has_vol:
        fig.add_trace(candle, row=1, col=1)
    else:
        fig.add_trace(candle)

    # --- MA overlays ---
    for period in ma_periods:
        if len(df) >= period:
            ma = df["close"].rolling(window=period).mean()
            ma_trace = go.Scatter(
                x=x_data,
                y=ma,
                mode="lines",
                name=f"MA{period}",
                line=dict(width=1.5),
            )
            if has_vol:
                fig.add_trace(ma_trace, row=1, col=1)
            else:
                fig.add_trace(ma_trace)

    # --- Bollinger Bands overlay ---
    if bollinger and len(df) >= 20:
        from app.utils.indicators.volatility import bollinger_bands
        bb_period = 20
        bb_std = 2.0
        upper, middle, lower = bollinger_bands(df["close"], period=bb_period, std_dev=bb_std)
        if has_vol:
            fig.add_trace(go.Scatter(
                x=x_data, y=upper,
                mode="lines", name=f"BB上轨({bb_period})",
                line=dict(width=1, dash="dash", color="rgba(0,100,200,0.7)"),
            ), row=1, col=1)
            fig.add_trace(go.Scatter(
                x=x_data, y=middle,
                mode="lines", name=f"BB中轨({bb_period})",
                line=dict(width=1, color="rgba(0,100,200,0.5)"),
            ), row=1, col=1)
            fig.add_trace(go.Scatter(
                x=x_data, y=lower,
                mode="lines", name=f"BB下轨({bb_period})",
                line=dict(width=1, dash="dash", color="rgba(0,100,200,0.7)"),
                fill="tonexty", fillcolor="rgba(0,100,200,0.08)",
            ), row=1, col=1)
        else:
            fig.add_trace(go.Scatter(
                x=x_data, y=upper,
                mode="lines", name=f"BB上轨({bb_period})",
                line=dict(width=1, dash="dash", color="rgba(0,100,200,0.7)"),
            ))
            fig.add_trace(go.Scatter(
                x=x_data, y=middle,
                mode="lines", name=f"BB中轨({bb_period})",
                line=dict(width=1, color="rgba(0,100,200,0.5)"),
            ))
            fig.add_trace(go.Scatter(
                x=x_data, y=lower,
                mode="lines", name=f"BB下轨({bb_period})",
                line=dict(width=1, dash="dash", color="rgba(0,100,200,0.7)"),
                fill="tonexty", fillcolor="rgba(0,100,200,0.08)",
            ))

    # --- Volume bars ---
    if has_vol:
        vol_colors = _volume_colors(df["open"], df["close"])
        fig.add_trace(
            go.Bar(
                x=df["date"] if "date" in df.columns else df.index,
                y=df["volume"],
                marker_color=vol_colors,
                name="成交量",
                showlegend=False,
            ),
            row=2, col=1,
        )

    layout_overrides = {"title": title or "K线图"}
    if has_vol:
        fig.update_layout(**_default_layout(**layout_overrides))
        fig.update_xaxes(rangeslider_visible=False, row=1, col=1)
        fig.update_yaxes(title_text="价格", row=1, col=1)
        fig.update_yaxes(title_text="成交量", row=2, col=1)
    else:
        fig.update_layout(**_default_layout(**layout_overrides))
        fig.update_xaxes(rangeslider_visible=False)

    return fig


# ---------------------------------------------------------------------------
# Line chart
# ---------------------------------------------------------------------------

def create_line(
    df: pd.DataFrame,
    x: str = "date",
    y: Optional[List[str]] = None,
    title: Optional[str] = None,
) -> go.Figure:
    """Create a line chart.

    If *y* is None, all numeric columns (except *x*) are plotted.
    """
    y_cols = y or [c for c in df.select_dtypes(include="number").columns if c != x]
    fig = go.Figure()
    for col in y_cols:
        fig.add_trace(go.Scatter(
            x=df[x] if x in df.columns else df.index,
            y=df[col],
            mode="lines",
            name=col,
        ))
    fig.update_layout(**_default_layout(title=title or "折线图"))
    return fig


# ---------------------------------------------------------------------------
# Bar chart
# ---------------------------------------------------------------------------

def create_bar(
    df: pd.DataFrame,
    x: str = "date",
    y: Optional[List[str]] = None,
    title: Optional[str] = None,
    barmode: str = "group",
) -> go.Figure:
    """Create a bar chart.

    If *y* is None, the first numeric column is used.
    """
    y_cols = y or [df.select_dtypes(include="number").columns[0]]
    fig = go.Figure()
    for col in y_cols:
        fig.add_trace(go.Bar(
            x=df[x] if x in df.columns else df.index,
            y=df[col],
            name=col,
        ))
    fig.update_layout(**_default_layout(title=title or "柱状图", barmode=barmode))
    return fig


# ---------------------------------------------------------------------------
# Heatmap
# ---------------------------------------------------------------------------

def create_heatmap(
    df: pd.DataFrame,
    title: Optional[str] = None,
    colorscale: str = "RdYlGn",
    zmin: Optional[float] = None,
    zmax: Optional[float] = None,
) -> go.Figure:
    """Create a heatmap from a DataFrame (columns = x-axis, index = y-axis)."""
    fig = go.Figure(go.Heatmap(
        z=df.values,
        x=df.columns.tolist(),
        y=df.index.tolist(),
        colorscale=colorscale,
        zmin=zmin,
        zmax=zmax,
    ))
    fig.update_layout(**_default_layout(title=title or "热力图"))
    return fig


# ---------------------------------------------------------------------------
# Multi-chart layout
# ---------------------------------------------------------------------------

def create_multi_chart(
    charts: List[go.Figure],
    titles: Optional[List[str]] = None,
    rows: Optional[int] = None,
    cols: int = 1,
) -> go.Figure:
    """Combine several figures into a subplot grid.

    Each input *chart* must have exactly one trace (for simplicity).
    """
    n = len(charts)
    if n == 0:
        return go.Figure()
    if rows is None:
        rows = (n + cols - 1) // cols

    fig = make_subplots(
        rows=rows, cols=cols,
        subplot_titles=titles or [f"Chart {i+1}" for i in range(n)],
    )

    for idx, chart in enumerate(charts):
        r = idx // cols + 1
        c = idx % cols + 1
        for trace in chart.data:
            fig.add_trace(trace, row=r, col=c)

    fig.update_layout(**_default_layout(height=400 * rows))
    return fig


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def export_figure(
    fig: go.Figure,
    format: str = "png",
    width: int = 1200,
    height: int = 600,
    scale: float = 2.0,
) -> bytes:
    """Export a figure to PNG or PDF bytes.

    Returns the raw file content.
    """
    img_bytes = fig.to_image(format=format, width=width, height=height, scale=scale)
    return img_bytes


def export_figure_to_file(
    fig: go.Figure,
    path: str,
    format: Optional[str] = None,
    width: int = 1200,
    height: int = 600,
    scale: float = 2.0,
) -> Path:
    """Export a figure to a file. Format is inferred from the extension if not given."""
    p = Path(path)
    fmt = format or p.suffix.lstrip(".") or "png"
    data = export_figure(fig, format=fmt, width=width, height=height, scale=scale)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


# ---------------------------------------------------------------------------
# Data preprocessing
# ---------------------------------------------------------------------------

def prepare_kline_data(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure a DataFrame has the required columns for a candlestick chart.

    Renames common alternate column names and sorts by date.
    """
    if "vol" in df.columns and "volume" in df.columns:
        df = df.drop(columns=["vol"])
    elif "vol" in df.columns:
        df = df.rename(columns={"vol": "volume"})

    if "stock_code" in df.columns and "code" in df.columns:
        df = df.drop(columns=["stock_code"])

    rename_map = {
        "stock_code": "code",
        "symbol": "code",
        "datetime": "date",
        "time": "date",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

    df = df.loc[:, ~df.columns.duplicated()]

    if "date" in df.columns:
        df = df.sort_values("date").reset_index(drop=True)

    return df


def prepare_correlation_matrix(
    df: pd.DataFrame,
    columns: Optional[List[str]] = None,
    method: str = "pearson",
) -> pd.DataFrame:
    """Compute a correlation matrix suitable for heatmap display."""
    cols = columns or df.select_dtypes(include="number").columns.tolist()
    return df[cols].corr(method=method)


# ---------------------------------------------------------------------------
# Advanced chart features — data sampling & real-time update support
# ---------------------------------------------------------------------------

def downsample_dataframe(
    df: pd.DataFrame,
    max_points: int = 5000,
    date_column: str = "date",
) -> pd.DataFrame:
    """Downsample a DataFrame for efficient chart rendering.

    When the DataFrame exceeds *max_points* rows, an evenly-spaced
    subset is returned that preserves the first and last rows.

    Parameters
    ----------
    df : source DataFrame
    max_points : maximum number of rows to keep
    date_column : name of the date/datetime column

    Returns
    -------
    Downsampled DataFrame (or the original if under the limit).
    """
    if len(df) <= max_points:
        return df

    step = len(df) / max_points
    indices = [int(i * step) for i in range(max_points)]
    if indices[-1] != len(df) - 1:
        indices.append(len(df) - 1)
    indices = sorted(set(indices))
    return df.iloc[indices].reset_index(drop=True)


def create_realtime_candlestick(
    df: pd.DataFrame,
    title: Optional[str] = None,
    max_points: int = 500,
    ma_periods: Optional[List[int]] = None,
    show_volume: bool = True,
) -> go.Figure:
    """Create a candlestick chart optimized for real-time updates.

    Uses a capped number of data points and lightweight traces for
    efficient re-rendering on each tick.
    """
    if len(df) > max_points:
        df = df.iloc[-max_points:].reset_index(drop=True)

    fig = create_candlestick(
        df, title=title or "实时K线", show_volume=show_volume, ma_periods=ma_periods
    )
    fig.update_layout(
        uirevision="constant",
        xaxis=dict(rangeslider=dict(visible=False)),
        transition_duration=0,
    )
    return fig


def update_figure_data(
    fig: go.Figure,
    trace_index: int,
    x_data: list,
    y_data: list,
) -> go.Figure:
    """Efficiently update data for a specific trace in a figure.

    This avoids recreating the entire figure when only data changes.
    """
    if trace_index < len(fig.data):
        fig.data[trace_index].x = x_data
        fig.data[trace_index].y = y_data
    return fig


def create_gauge_chart(
    value: float,
    title: str = "",
    min_val: float = 0,
    max_val: float = 100,
    threshold_warning: Optional[float] = None,
    threshold_critical: Optional[float] = None,
) -> go.Figure:
    """Create a gauge (speedometer) chart for metric display.

    Parameters
    ----------
    value : current metric value
    title : gauge title
    min_val, max_val : range of the gauge
    threshold_warning : yellow-zone start
    threshold_critical : red-zone start
    """
    steps = [
        {"range": [min_val, threshold_warning or max_val * 0.6], "color": "#26a65b"},
    ]
    if threshold_warning is not None:
        steps.append({
            "range": [threshold_warning, threshold_critical or max_val],
            "color": "#ffdd57",
        })
    if threshold_critical is not None:
        steps.append({"range": [threshold_critical, max_val], "color": "#ea4335"})

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value,
        title={"text": title},
        gauge={
            "axis": {"range": [min_val, max_val]},
            "bar": {"color": "#1f77b4"},
            "steps": steps,
        },
    ))
    fig.update_layout(height=250, margin={"t": 50, "b": 20, "l": 30, "r": 30})
    return fig
