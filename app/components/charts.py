"""
Charts component — interactive chart page for tdxview.

Provides stock selection, date range, chart type switching,
technical indicator overlays, zoom/pan, and export.
"""

import streamlit as st
import pandas as pd
from typing import Optional

from app.services.data_service import DataService
from app.services.visualization_service import (
    create_candlestick,
    create_line,
    create_bar,
    create_heatmap,
    prepare_kline_data,
    prepare_correlation_matrix,
    export_figure_to_file,
)


def chart_component():
    """Render the charts page."""
    st.header("图表分析")

    # Initialise data service
    if "data_service" not in st.session_state:
        st.session_state.data_service = DataService()
    svc: DataService = st.session_state.data_service

    # ---- Sidebar controls ----
    with st.sidebar:
        st.markdown("### 图表设置")

        # Stock code input
        symbol = st.text_input(
            "股票代码",
            value="600519",
            help="输入股票代码，如 600519、000001",
        )

        # Date range
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("开始日期", value=pd.Timestamp("2024-01-01"))
        with col2:
            end_date = st.date_input("结束日期", value=pd.Timestamp("2024-12-31"))

        # Chart type
        chart_type = st.selectbox(
            "图表类型",
            options=["K线图", "折线图", "柱状图", "热力图"],
            index=0,
        )

        # Period
        period = st.selectbox(
            "K线周期",
            options=["1d", "1w", "1mon", "1m", "5m", "15m", "30m", "1h"],
            index=0,
        )

        # Dividend type
        dividend_type = st.selectbox(
            "复权方式",
            options={"前复权": "front", "后复权": "back", "不复权": "none"},
            index=0,
        )

        # MA overlays (for candlestick)
        ma_periods = []
        if chart_type == "K线图":
            ma_checked = st.multiselect(
                "均线叠加",
                options=[5, 10, 20, 30, 60, 120, 250],
                default=[5, 20],
            )
            ma_periods = ma_checked

        # Fetch button
        fetch_btn = st.button("获取数据", use_container_width=True, type="primary")

    # ---- Main content ----
    chart_type_map = {
        "K线图": "candlestick",
        "折线图": "line",
        "柱状图": "bar",
        "热力图": "heatmap",
    }
    selected_type = chart_type_map[chart_type]

    # Trigger data fetch
    if fetch_btn or st.session_state.get("chart_df") is not None:
        if fetch_btn:
            with st.spinner("正在获取数据..."):
                try:
                    df = svc.get_history(
                        symbols=[symbol],
                        start_date=str(start_date),
                        end_date=str(end_date),
                        period=period,
                        dividend_type=dividend_type,
                        use_cache=True,
                    )
                    if df.empty:
                        st.warning("未获取到数据，请检查股票代码和日期范围。")
                        return
                    st.session_state.chart_df = df
                    st.session_state.chart_symbol = symbol
                except Exception as e:
                    st.error(f"数据获取失败: {e}")
                    return

        df: pd.DataFrame = st.session_state.get("chart_df")
        sym = st.session_state.get("chart_symbol", symbol)

        if df is None or df.empty:
            st.info("请在左侧设置参数并点击「获取数据」。")
            return

        # Prepare data
        df = prepare_kline_data(df)

        # Chart type tabs
        tabs = st.tabs([chart_type])

        with tabs[0]:
            fig = _render_chart(df, selected_type, sym, ma_periods)
            if fig is not None:
                st.plotly_chart(fig, use_container_width=True)

                # Export buttons
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("导出 PNG", key="export_png"):
                        try:
                            path = export_figure_to_file(
                                fig, f"log/{sym}_{selected_type}.png", format="png"
                            )
                            st.success(f"已导出: {path}")
                        except Exception as e:
                            st.error(f"导出失败: {e}")
                with col2:
                    if st.button("导出 PDF", key="export_pdf"):
                        try:
                            path = export_figure_to_file(
                                fig, f"log/{sym}_{selected_type}.pdf", format="pdf"
                            )
                            st.success(f"已导出: {path}")
                        except Exception as e:
                            st.error(f"导出失败: {e}")

        # Data preview
        with st.expander("数据预览"):
            st.dataframe(df.tail(20), use_container_width=True)


def _render_chart(
    df: pd.DataFrame,
    chart_type: str,
    symbol: str,
    ma_periods: list,
) -> Optional[object]:
    """Dispatch to the correct chart creator and return the Figure."""
    try:
        if chart_type == "candlestick":
            return create_candlestick(
                df,
                title=f"{symbol} K线图",
                show_volume=True,
                ma_periods=ma_periods,
            )
        elif chart_type == "line":
            return create_line(
                df,
                x="date",
                y=["close"],
                title=f"{symbol} 折线图",
            )
        elif chart_type == "bar":
            return create_bar(
                df,
                x="date",
                y=["volume"],
                title=f"{symbol} 成交量",
            )
        elif chart_type == "heatmap":
            corr = prepare_correlation_matrix(df)
            return create_heatmap(
                corr,
                title=f"{symbol} 相关性热力图",
            )
    except Exception as e:
        st.error(f"图表渲染错误: {e}")
        return None
    return None
