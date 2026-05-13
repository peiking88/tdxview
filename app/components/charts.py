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

COLUMN_ORDER = ["code", "name", "open", "high", "low", "close", "volume", "amount", "date"]
DIVIDEND_TYPE_MAP = {"前复权": "front", "后复权": "back", "不复权": "none"}
PAGE_SIZE = 50


def _reorder_columns(df: pd.DataFrame) -> pd.DataFrame:
    ordered = [c for c in COLUMN_ORDER if c in df.columns]
    remaining = [c for c in df.columns if c not in ordered]
    return df[ordered + remaining]


def _render_paginated_table(df: pd.DataFrame, key_prefix: str):
    total = len(df)
    if total == 0:
        st.info("无数据")
        return

    # 按日期倒序（近日在前）
    if "date" in df.columns:
        df = df.sort_values("date", ascending=False).reset_index(drop=True)

    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    page_key = f"{key_prefix}_page"

    if page_key not in st.session_state:
        st.session_state[page_key] = 1

    current_page = max(1, min(st.session_state[page_key], total_pages))
    st.session_state[page_key] = current_page

    col1, col2, col3 = st.columns([1, 3, 1])
    with col1:
        if st.button("◀ 上一页", key=f"{key_prefix}_prev", disabled=current_page <= 1):
            st.session_state[page_key] = current_page - 1
            st.rerun()
    with col2:
        st.markdown(
            f"<div class='pagination-text'>"
            f"第 <b>{current_page}</b> / {total_pages} 页  (共 {total} 条)</div>",
            unsafe_allow_html=True,
        )
    with col3:
        if st.button("下一页 ▶", key=f"{key_prefix}_next", disabled=current_page >= total_pages):
            st.session_state[page_key] = current_page + 1
            st.rerun()

    start_idx = (current_page - 1) * PAGE_SIZE
    end_idx = min(start_idx + PAGE_SIZE, total)
    page_df = df.iloc[start_idx:end_idx]

    # 价位/金额列格式化为 %.2f
    price_cols = {"open", "high", "low", "close", "amount", "price", "settlement", "pre_close"}
    col_config = {}
    for col in page_df.columns:
        if col.lower() in price_cols:
            col_config[col] = st.column_config.NumberColumn(format="%.2f")

    st.dataframe(
        page_df,
        width='stretch',
        hide_index=True,
        column_config=col_config if col_config else None,
    )


def _render_factor_panel(svc: DataService, symbol: str):
    """展示复权因子信息：按 <日期, 复权因子> 多列展示。"""
    try:
        factor_df = svc.get_factor(stock_code=symbol, adjust="qfq")
    except Exception:
        factor_df = pd.DataFrame()

    if factor_df is None or factor_df.empty:
        try:
            factor_df = svc.get_factor(stock_code=symbol, adjust="hfq")
        except Exception:
            factor_df = pd.DataFrame()

    if factor_df is None or factor_df.empty:
        st.info("暂无复权因子数据")
        return

    # 摘要指标
    if "factor" in factor_df.columns:
        factor_series = factor_df["factor"]
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("最新因子", f"{factor_series.iloc[-1]:.6f}" if len(factor_series) > 0 else "N/A")
        with col2:
            st.metric("最早因子", f"{factor_series.iloc[0]:.6f}" if len(factor_series) > 0 else "N/A")
        with col3:
            st.metric("数据点数", f"{len(factor_series)}")

    # 按 <日期, 复权因子> 多列展示（每列4对，从新到旧）
    n_cols = 4
    if "date" in factor_df.columns:
        rows = sorted(
            [{"date": str(d)[:10], "factor": f"{f:.6f}"} for d, f in
             zip(factor_df["date"], factor_df["factor"])],
            key=lambda x: x["date"], reverse=True,
        )
    else:
        rows = [{"date": f"#{i}", "factor": f"{f:.6f}"}
                for i, f in enumerate(factor_df["factor"])]

    # 分块：每块 n_cols 对，按列优先填充
    chunk_size = n_cols
    for start in range(0, len(rows), chunk_size):
        chunk = rows[start:start + chunk_size]
        cols = st.columns(n_cols)
        for i in range(n_cols):
            idx = i
            if idx < len(chunk):
                cols[i].markdown(
                    f'<div class="factor-row">'
                    f'<span class="factor-label">{chunk[idx]["date"]}</span><br>'
                    f'<span class="factor-value">{chunk[idx]["factor"]}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )


def chart_component():
    st.header("图表分析")

    if "data_service" not in st.session_state:
        st.session_state.data_service = DataService()
    svc: DataService = st.session_state.data_service

    with st.sidebar:
        st.markdown("### 图表设置")

        symbol = st.text_input(
            "股票代码",
            value="600519",
            help="输入股票代码，如 600519、000001",
        )

        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("开始日期", value=pd.Timestamp("2024-01-01"))
        with col2:
            end_date = st.date_input("结束日期", value=pd.Timestamp.now().date())

        chart_types = ["K线图", "折线图", "柱状图"]
        is_multi = "," in symbol
        if is_multi:
            chart_types.append("热力图")

        chart_type = st.selectbox(
            "图表类型",
            options=chart_types,
            index=0,
        )

        period = st.selectbox(
            "K线周期",
            options=["1d", "1w", "1mon", "1m", "5m", "15m", "30m", "1h"],
            index=0,
        )

        dividend_display = st.selectbox(
            "复权方式",
            options=list(DIVIDEND_TYPE_MAP.keys()),
            index=0,
        )

        ma_periods = []
        bollinger_enabled = False
        if chart_type == "K线图":
            ma_checked = st.multiselect(
                "均线叠加",
                options=[5, 10, 20, 30, 60, 120, 250],
                default=[5, 20],
            )
            ma_periods = ma_checked
            bollinger_enabled = st.checkbox("布林带叠加", value=False)

        fetch_btn = st.button("获取数据", width='stretch', type="primary")

    chart_type_map = {
        "K线图": "candlestick",
        "折线图": "line",
        "柱状图": "bar",
        "热力图": "heatmap",
    }
    selected_type = chart_type_map[chart_type]

    if fetch_btn or st.session_state.get("chart_df") is not None:
        if fetch_btn:
            with st.spinner("正在获取数据..."):
                try:
                    dividend_type = DIVIDEND_TYPE_MAP[dividend_display]
                    df = svc.get_history(
                        symbols=[symbol],
                        start_date=str(start_date),
                        end_date=str(end_date),
                        period=period,
                        dividend_type=dividend_type,
                        use_cache=True,
                    )
                    if df.empty:
                        st.session_state.chart_df = None
                        st.session_state.chart_symbol = None
                        st.warning("未获取到数据，请检查股票代码和日期范围。")
                        return
                    st.session_state.chart_df = df
                    st.session_state.chart_symbol = symbol
                    st.session_state.chart_ma_periods = ma_periods
                    st.session_state.chart_bollinger = bollinger_enabled
                except Exception as e:
                    st.error(f"数据获取失败: {e}")
                    return

        df: pd.DataFrame = st.session_state.get("chart_df")
        sym = st.session_state.get("chart_symbol", symbol)
        ma_periods = st.session_state.get("chart_ma_periods", ma_periods)
        bollinger_enabled = st.session_state.get("chart_bollinger", bollinger_enabled)

        if df is None or df.empty:
            st.info("请在左侧设置参数并点击「获取数据」。")
            return

        df = prepare_kline_data(df)

        # 主区域：图表
        tabs = st.tabs([chart_type])

        with tabs[0]:
            fig = _render_chart(df, selected_type, sym, ma_periods, bollinger_enabled)
            if fig is not None:
                st.plotly_chart(fig, width='stretch')

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

        # 数据预览
        with st.expander("数据预览"):
            preview_df = _reorder_columns(df)
            _render_paginated_table(preview_df, key_prefix="chart_preview")

        # 复权因子面板
        with st.expander("复权因子"):
            _render_factor_panel(svc, sym)


def _render_chart(
    df: pd.DataFrame,
    chart_type: str,
    symbol: str,
    ma_periods: list,
    bollinger_enabled: bool = False,
) -> Optional[object]:
    try:
        if chart_type == "candlestick":
            fig = create_candlestick(
                df,
                title=f"{symbol} K线图",
                show_volume=True,
                ma_periods=ma_periods,
                bollinger=bollinger_enabled,
            )
            return fig
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
