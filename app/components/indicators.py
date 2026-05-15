"""
Indicators component — technical indicator selection, configuration, and display.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from typing import Any, Dict, List, Optional

from app.services.indicator_service import IndicatorService, INDICATOR_REGISTRY
from app.services.visualization_service import create_candlestick
from app.services.data_service import DataService

_data_service_cache: Optional[DataService] = None


def _get_data_service() -> DataService:
    global _data_service_cache
    if _data_service_cache is None:
        _data_service_cache = DataService()
    return _data_service_cache

INDICATOR_COLORS = {
    "sma": "#ff7f0e",
    "ema": "#2ca02c",
    "macd_line": "#1f77b4",
    "signal_line": "#ff7f0e",
    "rsi": "#9467bd",
    "rps": "#e377c2",
    "obv": "#17becf",
    "vwap": "#bcbd22",
    "bb_upper": "#ff9896",
    "bb_middle": "#ff7f0e",
    "bb_lower": "#ff9896",
}


def indicator_component():
    st.header("技术指标")

    svc = IndicatorService()

    # ---- 侧边栏：与图表分析页保持一致的布局 ----
    with st.sidebar:
        st.markdown("### 指标设置")

        symbol = st.text_input("股票代码", value="600519", key="ind_symbol")
        col1, col2 = st.columns(2)
        with col1:
            ind_start = st.date_input("开始日期", value=pd.Timestamp("2024-01-01"), key="ind_start")
        with col2:
            ind_end = st.date_input("结束日期", value=pd.Timestamp.now().date(), key="ind_end")

        period = st.selectbox(
            "K线周期",
            options=["1d", "1w", "1mon", "1m", "5m", "15m", "30m", "1h"],
            index=0,
            key="ind_period",
        )

        all_indicators = svc.list_indicators()
        categories = sorted(set(ind["category"] for ind in all_indicators))
        selected_category = st.selectbox("指标类别", ["全部"] + categories)

        if selected_category == "全部":
            filtered = all_indicators
        else:
            filtered = [ind for ind in all_indicators if ind["category"] == selected_category]

        indicator_names = [ind["display_name"] for ind in filtered]
        name_to_key = {ind["display_name"]: ind["name"] for ind in filtered}

        selected_display = st.selectbox("选择指标", indicator_names)
        indicator_key = name_to_key.get(selected_display)

        params: Dict[str, Any] = {}
        if indicator_key and indicator_key in INDICATOR_REGISTRY:
            default_params = INDICATOR_REGISTRY[indicator_key]["default_params"]
            for pname, pval in default_params.items():
                if isinstance(pval, int):
                    params[pname] = st.number_input(
                        pname, value=pval, min_value=1, step=1,
                    )
                elif isinstance(pval, float):
                    params[pname] = st.number_input(
                        pname, value=pval, min_value=0.1, step=0.1, format="%.1f",
                    )

        overlay_supported = _is_overlay_supported(indicator_key)
        overlay_enabled = False
        if overlay_supported:
            overlay_enabled = st.checkbox("叠加到K线", value=True)

        calculate_btn = st.button("计算指标", width='stretch', type="primary")

    if not indicator_key:
        st.info("请从左侧选择一个技术指标。")
        return

    if st.session_state.get("indicator_key") != indicator_key:
        st.session_state.indicator_result = None
        st.session_state.indicator_df = None
        st.session_state.indicator_key = indicator_key

    if st.session_state.get("indicator_overlay") != overlay_enabled:
        st.session_state.indicator_result = None
        st.session_state.indicator_df = None
        st.session_state.indicator_overlay = overlay_enabled

    if st.session_state.get("indicator_period") != period:
        st.session_state.indicator_result = None
        st.session_state.indicator_df = None
        st.session_state.indicator_period = period

    info = svc.get_indicator_info(indicator_key)
    if info:
        st.subheader(f"{info['display_name']}")
        mode = "叠加到K线" if overlay_enabled else "单独图表"
        st.caption(f"类别: {info['category']} | 显示: {mode}")

    if calculate_btn or st.session_state.get("indicator_result") is not None:
        if calculate_btn:
            with st.spinner("正在获取数据并计算指标..."):
                try:
                    data_svc = _get_data_service()
                    df = data_svc.get_history(
                        symbols=[symbol],
                        start_date=str(ind_start),
                        end_date=str(ind_end),
                        period=period,
                        dividend_type="front",
                    )
                    data_svc.close()
                    if df.empty:
                        st.warning("未获取到数据。")
                        return
                    results = svc.calculate(indicator_key, df, params=params)
                    st.session_state.indicator_result = results
                    st.session_state.indicator_df = df
                except Exception as e:
                    st.error(f"计算失败: {e}")
                    return

        results = st.session_state.get("indicator_result")
        df = st.session_state.get("indicator_df")

        if results is None or df is None:
            st.info("请点击「计算指标」开始。")
            return

        if overlay_enabled and overlay_supported:
            _render_overlay_chart(df, indicator_key, symbol, selected_display, results, params)
        else:
            _render_separate_chart(df, indicator_key, symbol, selected_display, results)

        with st.expander("指标数值"):
            for name, series in results.items():
                valid = series.dropna() if hasattr(series, "dropna") else pd.Series(series)
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("最新值", f"{valid.iloc[-1]:.4f}" if len(valid) > 0 else "N/A")
                with col2:
                    st.metric("最大值", f"{valid.max():.4f}" if len(valid) > 0 else "N/A")
                with col3:
                    st.metric("最小值", f"{valid.min():.4f}" if len(valid) > 0 else "N/A")
                with col4:
                    st.metric("均值", f"{valid.mean():.4f}" if len(valid) > 0 else "N/A")


def _is_overlay_supported(indicator_key: str) -> bool:
    if not indicator_key or indicator_key not in INDICATOR_REGISTRY:
        return False
    return INDICATOR_REGISTRY[indicator_key].get("overlay_supported", False)


def _get_x(df: pd.DataFrame):
    return df["date"] if "date" in df.columns else df.index


def _to_series(val):
    if isinstance(val, pd.Series):
        return val
    return pd.Series(val)


def _render_overlay_chart(df, indicator_key, symbol, display_name, results, params):
    ma_periods = []
    bollinger = False

    if indicator_key == "sma":
        ma_periods = [params.get("period", 20)]
    elif indicator_key == "ema":
        ma_periods = [params.get("period", 20)]
    elif indicator_key == "bollinger_bands":
        bollinger = True

    fig = create_candlestick(
        df,
        title=f"{symbol} K线 + {display_name}",
        show_volume=True,
        ma_periods=ma_periods,
        bollinger=bollinger,
    )

    x = _get_x(df)

    if indicator_key == "sma":
        series = results.get("sma")
        if series is not None:
            fig.add_trace(go.Scatter(
                x=x, y=series,
                mode="lines", name=f"SMA({params.get('period', 20)})",
                line=dict(width=2, color=INDICATOR_COLORS["sma"]),
            ), row=1, col=1)
    elif indicator_key == "ema":
        series = results.get("ema")
        if series is not None:
            fig.add_trace(go.Scatter(
                x=x, y=series,
                mode="lines", name=f"EMA({params.get('period', 20)})",
                line=dict(width=2, color=INDICATOR_COLORS["ema"]),
            ), row=1, col=1)
    elif indicator_key == "macd":
        _add_macd_overlay(fig, results, x)
    elif indicator_key == "rsi":
        _add_rsi_overlay(fig, results, x)
    elif indicator_key == "rps":
        _add_rps_overlay(fig, results, x)
    elif indicator_key == "obv":
        _add_obv_overlay(fig, results, x)
    elif indicator_key == "vwap":
        _add_vwap_overlay(fig, results, x)

    fig_w = fig.layout.width
    use_container = not (fig_w and fig.layout.autosize == False)
    st.plotly_chart(fig, use_container_width=use_container)


def _render_separate_chart(df, indicator_key, symbol, display_name, results):
    x = _get_x(df)

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.6, 0.4],
        vertical_spacing=0.08,
        subplot_titles=[f"{symbol} K线", display_name],
    )

    fig.add_trace(go.Candlestick(
        x=x, open=df["open"], high=df["high"],
        low=df["low"], close=df["close"],
        name="K线",
        increasing_line_color="#26a65b",
        decreasing_line_color="#ea4335",
    ), row=1, col=1)

    if indicator_key == "sma":
        _add_sma_traces(fig, results, x)
    elif indicator_key == "ema":
        _add_ema_traces(fig, results, x)
    elif indicator_key == "bollinger_bands":
        _add_bollinger_traces(fig, results, x)
    elif indicator_key == "macd":
        _add_macd_traces(fig, results, x)
    elif indicator_key == "rsi":
        _add_rsi_traces(fig, results, x)
    elif indicator_key == "rps":
        _add_rps_traces(fig, results, x)
    elif indicator_key == "obv":
        _add_obv_traces(fig, results, x)
    elif indicator_key == "vwap":
        _add_vwap_traces(fig, results, x)

    fig.update_layout(
        template="plotly_white",
        height=600,
        margin={"l": 60, "r": 30, "t": 50, "b": 50},
        xaxis2=dict(rangeslider=dict(visible=False)),
        hovermode="x unified",
    )
    fig.update_xaxes(rangeslider_visible=False, row=1, col=1)

    fig_w = fig.layout.width
    use_container = not (fig_w and fig.layout.autosize == False)
    st.plotly_chart(fig, use_container_width=use_container)


# ---------------------------------------------------------------------------
# Overlay helpers — add indicator traces on top of K-line (row=1, col=1)
# ---------------------------------------------------------------------------

def _add_macd_overlay(fig, results, x):
    macd_line = _to_series(results.get("macd_line", []))
    fig.add_trace(go.Scatter(
        x=x, y=macd_line,
        mode="lines", name="MACD",
        line=dict(width=1.5, color=INDICATOR_COLORS["macd_line"]),
    ), row=1, col=1)


def _add_rsi_overlay(fig, results, x):
    rsi_val = _to_series(results.get("rsi", []))
    fig.add_trace(go.Scatter(
        x=x, y=rsi_val,
        mode="lines", name="RSI",
        line=dict(width=1.5, color=INDICATOR_COLORS["rsi"]),
    ), row=1, col=1)


def _add_rps_overlay(fig, results, x):
    rps_val = _to_series(results.get("rps", []))
    fig.add_trace(go.Scatter(
        x=x, y=rps_val,
        mode="lines", name="RPS",
        line=dict(width=1.5, color=INDICATOR_COLORS["rps"]),
    ), row=1, col=1)


def _add_obv_overlay(fig, results, x):
    obv_val = _to_series(results.get("obv", []))
    fig.add_trace(go.Scatter(
        x=x, y=obv_val,
        mode="lines", name="OBV",
        line=dict(width=1.5, color=INDICATOR_COLORS["obv"]),
    ), row=1, col=1)


def _add_vwap_overlay(fig, results, x):
    vwap_val = _to_series(results.get("vwap", []))
    fig.add_trace(go.Scatter(
        x=x, y=vwap_val,
        mode="lines", name="VWAP",
        line=dict(width=1.5, color=INDICATOR_COLORS["vwap"]),
    ), row=1, col=1)


# ---------------------------------------------------------------------------
# Separate-chart helpers — add indicator traces in bottom subplot (row=2)
# ---------------------------------------------------------------------------

def _add_sma_traces(fig, results, x):
    series = _to_series(results.get("sma", []))
    fig.add_trace(go.Scatter(
        x=x, y=series,
        mode="lines", name="SMA", line=dict(width=1.8, color=INDICATOR_COLORS["sma"]),
    ), row=2, col=1)
    fig.update_yaxes(title_text="价格", row=2, col=1)


def _add_ema_traces(fig, results, x):
    series = _to_series(results.get("ema", []))
    fig.add_trace(go.Scatter(
        x=x, y=series,
        mode="lines", name="EMA", line=dict(width=1.8, color=INDICATOR_COLORS["ema"]),
    ), row=2, col=1)
    fig.update_yaxes(title_text="价格", row=2, col=1)


def _add_bollinger_traces(fig, results, x):
    upper = _to_series(results.get("bb_upper", []))
    middle = _to_series(results.get("bb_middle", []))
    lower = _to_series(results.get("bb_lower", []))
    fig.add_trace(go.Scatter(
        x=x, y=upper,
        mode="lines", name="上轨", line=dict(width=1.3, color=INDICATOR_COLORS["bb_upper"]),
    ), row=2, col=1)
    fig.add_trace(go.Scatter(
        x=x, y=middle,
        mode="lines", name="中轨", line=dict(width=1.5, color=INDICATOR_COLORS["bb_middle"]),
    ), row=2, col=1)
    fig.add_trace(go.Scatter(
        x=x, y=lower,
        mode="lines", name="下轨", line=dict(width=1.3, color=INDICATOR_COLORS["bb_lower"]),
        fill="tonexty", fillcolor="rgba(255,152,150,0.08)",
    ), row=2, col=1)
    fig.update_yaxes(title_text="价格", row=2, col=1)


def _add_macd_traces(fig, results, x):
    macd_line = _to_series(results.get("macd_line", []))
    signal_line = _to_series(results.get("signal_line", []))
    histogram = _to_series(results.get("histogram", []))
    fig.add_trace(go.Scatter(
        x=x, y=macd_line,
        mode="lines", name="MACD", line=dict(width=1.5, color=INDICATOR_COLORS["macd_line"]),
    ), row=2, col=1)
    fig.add_trace(go.Scatter(
        x=x, y=signal_line,
        mode="lines", name="Signal", line=dict(width=1.5, color=INDICATOR_COLORS["signal_line"]),
    ), row=2, col=1)
    colors = ["#26a65b" if v >= 0 else "#ea4335" for v in histogram.fillna(0)]
    fig.add_trace(go.Bar(
        x=x, y=histogram,
        name="Histogram", marker_color=colors,
    ), row=2, col=1)
    fig.add_hline(y=0, line_dash="dash", line_color="gray", row=2, col=1)


def _add_rsi_traces(fig, results, x):
    rsi_val = _to_series(results.get("rsi", []))
    fig.add_trace(go.Scatter(
        x=x, y=rsi_val,
        mode="lines", name="RSI", line=dict(width=1.5, color=INDICATOR_COLORS["rsi"]),
    ), row=2, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)
    fig.update_yaxes(range=[0, 100], row=2, col=1)


def _add_rps_traces(fig, results, x):
    rps_val = _to_series(results.get("rps", []))
    fig.add_trace(go.Scatter(
        x=x, y=rps_val,
        mode="lines", name="RPS", line=dict(width=1.5, color=INDICATOR_COLORS["rps"]),
    ), row=2, col=1)
    fig.add_hline(y=80, line_dash="dash", line_color="red", row=2, col=1)
    fig.add_hline(y=20, line_dash="dash", line_color="green", row=2, col=1)
    fig.update_yaxes(range=[0, 100], row=2, col=1)


def _add_obv_traces(fig, results, x):
    obv_val = _to_series(results.get("obv", []))
    fig.add_trace(go.Scatter(
        x=x, y=obv_val,
        mode="lines", name="OBV", line=dict(width=1.5, color=INDICATOR_COLORS["obv"]),
    ), row=2, col=1)


def _add_vwap_traces(fig, results, x):
    vwap_val = _to_series(results.get("vwap", []))
    fig.add_trace(go.Scatter(
        x=x, y=vwap_val,
        mode="lines", name="VWAP", line=dict(width=1.5, color=INDICATOR_COLORS["vwap"]),
    ), row=2, col=1)
