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


def data_management_component():
    """Render the data management page."""
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


# ======================================================================
# Tab 1: Fetch data
# ======================================================================

def _render_fetch():
    """Fetch historical data and save to Parquet."""
    st.subheader("获取历史数据")

    with st.form("fetch_form"):
        col1, col2 = st.columns(2)
        with col1:
            symbols_input = st.text_input(
                "股票代码 (逗号分隔)",
                placeholder="例如: 000001,600519",
                help="支持多个代码，用英文逗号分隔",
            )
            start_date = st.date_input("开始日期", value=datetime.now() - timedelta(days=90))
            end_date = st.date_input("结束日期", value=datetime.now())
        with col2:
            period = st.selectbox("周期", ["1d", "1w", "1M", "5m", "15m", "30m", "60m"], index=0)
            dividend_type = st.selectbox("复权类型", ["front", "back", "none"], index=0)
            save_to_parquet = st.checkbox("保存到 Parquet", value=True)

        submitted = st.form_submit_button("获取数据")

        if submitted:
            if not symbols_input:
                st.error("请输入股票代码")
            else:
                symbols = [s.strip() for s in symbols_input.split(",") if s.strip()]
                start_str = start_date.strftime("%Y-%m-%d")
                end_str = end_date.strftime("%Y-%m-%d")

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
                        st.dataframe(df.head(20), use_container_width=True, hide_index=True)

                        if save_to_parquet:
                            results = ds.fetch_and_store(
                                symbols=symbols,
                                start_date=start_str,
                                end_date=end_str,
                                period=period,
                                dividend_type=dividend_type,
                            )
                            if results:
                                for sym, path in results.items():
                                    st.info(f"{sym} → {path}")
                            else:
                                st.warning("Parquet 保存未成功")

                except Exception as e:
                    st.error(f"获取数据失败: {e}")


# ======================================================================
# Tab 2: Parquet browser
# ======================================================================

def _render_parquet_browser():
    """Browse and manage Parquet files."""
    st.subheader("Parquet 文件浏览器")

    pm = ParquetManager()

    # List symbols
    try:
        symbols = pm.list_symbols()
    except Exception:
        symbols = []

    if not symbols:
        st.info("暂无 Parquet 数据文件")
        return

    st.markdown(f"**共 {len(symbols)} 个股票代码**")

    # Select symbol
    selected = st.selectbox("选择股票代码", symbols, key="pq_symbol_select")

    if selected:
        # Load and display
        df = pm.load(selected)
        if df is not None and not df.empty:
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("记录数", len(df))
            with col2:
                st.metric("列数", len(df.columns))
            with col3:
                st.metric("列名", ", ".join(df.columns[:5]) + ("..." if len(df.columns) > 5 else ""))

            st.dataframe(df.head(50), use_container_width=True, hide_index=True)

            # Delete
            st.markdown("---")
            if st.button(f"删除 {selected} 的数据", key=f"del_pq_{selected}"):
                pm.delete(selected)
                st.success(f"已删除 {selected}")
                st.rerun()
        else:
            st.warning("无法加载该文件")


# ======================================================================
# Tab 3: Data source list
# ======================================================================

def _render_source_list():
    """Show all configured data sources with status."""
    st.subheader("数据源列表")

    ds = DataService()
    sources = ds.list_data_sources()

    if not sources:
        st.info("暂无数据源配置。请在「系统配置」→「数据源管理」中添加。")
        return

    for src in sources:
        status_icon = "🟢" if src["enabled"] else "🔴"
        st.markdown(f"{status_icon} **{src['name']}** — 类型: {src['type']} 优先级: {src.get('priority', 0)}")
