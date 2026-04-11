"""
Data management component — browse Parquet files, fetch & store data.
"""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st
import pandas as pd

from app.config.settings import get_settings
from app.data.database import DatabaseManager
from app.data.parquet_manager import ParquetManager
from app.services.data_service import DataService

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

    total_pages = max(1, (total - 1) // PAGE_SIZE + 1)
    page_key = f"{key_prefix}_page"

    if page_key not in st.session_state:
        st.session_state[page_key] = 1

    current_page = st.session_state[page_key]

    col1, col2, col3 = st.columns([1, 3, 1])
    with col1:
        if st.button("◀ 上一页", key=f"{key_prefix}_prev", disabled=current_page <= 1):
            st.session_state[page_key] = current_page - 1
            st.rerun()
    with col2:
        st.markdown(f"<div style='text-align:center;padding-top:6px;'>第 <b>{current_page}</b> / {total_pages} 页  (共 {total} 条)</div>", unsafe_allow_html=True)
    with col3:
        if st.button("下一页 ▶", key=f"{key_prefix}_next", disabled=current_page >= total_pages):
            st.session_state[page_key] = current_page + 1
            st.rerun()

    start_idx = (current_page - 1) * PAGE_SIZE
    end_idx = min(start_idx + PAGE_SIZE, total)
    page_df = df.iloc[start_idx:end_idx]
    st.dataframe(page_df, use_container_width=True, hide_index=True)


def data_management_component():
    st.header("数据管理")

    tab_fetch, tab_parquet, tab_sources = st.tabs(
        ["数据获取", "Parquet 文件", "数据源列表"]
    )

    with tab_fetch:
        _render_fetch()

    with tab_parquet:
        _render_parquet_browser()

    with tab_sources:
        _render_source_list()


def _render_fetch():
    st.subheader("获取历史数据")

    with st.form("fetch_form"):
        col1, col2 = st.columns(2)
        with col1:
            symbols_input = st.text_input(
                "股票代码 (逗号分隔)",
                value="600519",
                placeholder="例如: 000001,600519",
                help="支持多个代码，用英文逗号分隔",
            )
            start_date = st.date_input("开始日期", value=datetime.now() - timedelta(days=90))
            end_date = st.date_input("结束日期", value=datetime.now())
        with col2:
            period = st.selectbox("周期", ["1d", "1w", "1M", "5m", "15m", "30m", "60m"], index=0)
            dividend_display = st.selectbox("复权类型", list(DIVIDEND_TYPE_MAP.keys()), index=0)
            save_to_parquet = st.checkbox("保存到 Parquet", value=True)

        submitted = st.form_submit_button("获取数据")

    if submitted:
        if not symbols_input:
            st.error("请输入股票代码")
        else:
            symbols = [s.strip() for s in symbols_input.split(",") if s.strip()]
            start_str = start_date.strftime("%Y-%m-%d")
            end_str = end_date.strftime("%Y-%m-%d")
            dividend_type = DIVIDEND_TYPE_MAP[dividend_display]

            try:
                ds = DataService()
                df = ds.get_history(
                    symbols=symbols,
                    start_date=start_str,
                    end_date=end_str,
                    period=period,
                    dividend_type=dividend_type,
                    use_cache=False,
                )

                if df.empty:
                    st.warning("未获取到数据")
                else:
                    st.success(f"获取到 {len(df)} 条记录")
                    df = _reorder_columns(df)
                    st.session_state.fetch_result = df
                    st.session_state.fetch_symbols = symbols
                    st.session_state.fetch_start = start_str
                    st.session_state.fetch_end = end_str
                    st.session_state.fetch_period = period
                    st.session_state.fetch_dividend = dividend_type
                    st.session_state.fetch_save_parquet = save_to_parquet

                ds.close()
            except Exception as e:
                st.error(f"获取数据失败: {e}")

    if "fetch_result" in st.session_state and st.session_state.fetch_result is not None:
        df = st.session_state.fetch_result
        _render_paginated_table(df, key_prefix="fetch_preview")

        if st.session_state.get("fetch_save_parquet"):
            if st.button("保存到 Parquet", key="save_parquet_btn"):
                try:
                    ds = DataService()
                    results = ds.fetch_and_store(
                        symbols=st.session_state.fetch_symbols,
                        start_date=st.session_state.fetch_start,
                        end_date=st.session_state.fetch_end,
                        period=st.session_state.fetch_period,
                        dividend_type=st.session_state.fetch_dividend,
                    )
                    ds.close()
                    if results:
                        for sym, path in results.items():
                            st.info(f"{sym} → {path}")
                    else:
                        st.warning("Parquet 保存未成功")
                except Exception as e:
                    st.error(f"保存失败: {e}")


def _render_parquet_browser():
    st.subheader("Parquet 文件浏览器")

    pm = ParquetManager()

    try:
        symbols = pm.list_symbols()
    except Exception:
        symbols = []

    if not symbols:
        st.info("暂无 Parquet 数据文件")
        return

    st.markdown(f"**共 {len(symbols)} 个股票代码**")

    selected = st.selectbox("选择股票代码", symbols, key="pq_symbol_select")

    if selected:
        df = pm.load(selected)
        if df is not None and not df.empty:
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("记录数", len(df))
            with col2:
                st.metric("列数", len(df.columns))
            with col3:
                st.metric("列名", ", ".join(df.columns[:5]) + ("..." if len(df.columns) > 5 else ""))

            df = _reorder_columns(df)
            _render_paginated_table(df, key_prefix="pq_preview")

            st.markdown("---")
            if st.button(f"删除 {selected} 的数据", key=f"del_pq_{selected}"):
                pm.delete(selected)
                st.success(f"已删除 {selected}")
                st.rerun()
        else:
            st.warning("无法加载该文件")


def _render_source_list():
    st.subheader("数据源列表")

    ds = DataService()
    sources = ds.list_data_sources()

    if not sources:
        st.info("暂无数据源配置。请在「系统配置」→「数据源管理」中添加。")
        return

    for src in sources:
        status_icon = "🟢" if src["enabled"] else "🔴"
        st.markdown(f"{status_icon} **{src['name']}** — 类型: {src['type']} 优先级: {src.get('priority', 0)}")
