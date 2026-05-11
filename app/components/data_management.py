"""
Data management component — import, browse, and manage all stock data types.
"""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st
import pandas as pd

from app.config.settings import get_settings
from app.data.parquet_manager import ParquetManager
from app.services.data_service import DataService

PAGE_SIZE = 50

DATA_TYPE_OPTIONS = {
    "历史 K 线": "history",
    "实时行情": "realtime",
    "分笔数据": "tick",
    "财务数据": "financial",
    "F10 资料": "f10",
    "除权除息": "basic",
}

DIVIDEND_TYPE_MAP = {"前复权": "front", "后复权": "back", "不复权": "none"}


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
        if st.button("上一页", key=f"{key_prefix}_prev", disabled=current_page <= 1):
            st.session_state[page_key] = current_page - 1
            st.rerun()
    with col2:
        st.markdown(
            f"<div style='text-align:center;padding-top:6px;'>"
            f"第 <b>{current_page}</b> / {total_pages} 页  (共 {total} 条)</div>",
            unsafe_allow_html=True,
        )
    with col3:
        if st.button("下一页", key=f"{key_prefix}_next", disabled=current_page >= total_pages):
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
        use_container_width=True,
        hide_index=True,
        column_config=col_config if col_config else None,
    )


def _format_size(size_bytes: Optional[int]) -> str:
    if size_bytes is None:
        return "-"
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.2f} MB"


def data_management_component():
    st.header("数据管理")

    tab_import, tab_status, tab_browse, tab_sources = st.tabs(
        ["数据导入", "导入状态", "数据浏览", "数据源列表"]
    )

    with tab_import:
        _render_import()

    with tab_status:
        _render_import_status()

    with tab_browse:
        _render_data_browser()

    with tab_sources:
        _render_source_list()


# ======================================================================
# Tab 1: Import
# ======================================================================

def _render_import():
    st.subheader("数据导入")

    if "data_service" not in st.session_state:
        st.session_state.data_service = DataService()
    svc: DataService = st.session_state.data_service

    col_left, col_right = st.columns([1, 2])

    with col_left:
        with st.form("import_form"):
            symbol = st.text_input(
                "股票代码",
                value="600519",
                placeholder="例如: 000001, 600519",
            )

            type_display = st.selectbox("数据类型", list(DATA_TYPE_OPTIONS.keys()))
            data_type = DATA_TYPE_OPTIONS[type_display]

            # Dynamic parameters based on data type
            start_date = end_date = period = dividend_display = tick_date = None

            if data_type == "history":
                col1, col2 = st.columns(2)
                with col1:
                    start_date = st.date_input("开始日期", value=datetime.now() - timedelta(days=90))
                with col2:
                    end_date = st.date_input("结束日期", value=datetime.now().date())
                period = st.selectbox("周期", ["1d", "1w", "1M", "5m", "15m", "30m", "60m"], index=0)
                dividend_display = st.selectbox("复权类型", list(DIVIDEND_TYPE_MAP.keys()), index=0)
            elif data_type == "tick":
                tick_date = st.date_input("日期", value=datetime.now())

            import_mode = st.selectbox("导入模式", ["增量导入", "完整重导"], index=0)

            submitted = st.form_submit_button("导入", type="primary")

    with col_right:
        if submitted:
            if not symbol.strip():
                st.error("请输入股票代码")
            else:
                symbol = symbol.strip()
                kwargs = _build_kwargs(data_type, start_date, end_date, period, dividend_display, tick_date)
                is_reimport = import_mode == "完整重导"

                with st.spinner("正在导入数据..."):
                    try:
                        if is_reimport:
                            record = svc.reimport_data(symbol, data_type, **kwargs)
                        else:
                            record = svc.incremental_import(symbol, data_type, **kwargs)

                        _display_import_result(record)

                        if record.status.value == "success" and record.record_count > 0:
                            df = svc.load_from_parquet(symbol, data_type=data_type)
                            if df is not None and not df.empty:
                                st.session_state.import_preview_df = df
                            else:
                                st.session_state.import_preview_df = None
                        else:
                            st.session_state.import_preview_df = None

                    except Exception as e:
                        st.error(f"导入失败: {e}")

        # Preview imported data
        preview_df = st.session_state.get("import_preview_df")
        if preview_df is not None:
            with st.expander("数据预览", expanded=True):
                _render_paginated_table(preview_df, key_prefix="import_preview")


def _build_kwargs(data_type, start_date, end_date, period, dividend_display, tick_date) -> dict:
    kwargs = {}
    if data_type == "history":
        kwargs["start_date"] = str(start_date)
        kwargs["end_date"] = str(end_date)
        kwargs["period"] = period or "1d"
        kwargs["dividend_type"] = DIVIDEND_TYPE_MAP.get(dividend_display, "front")
    elif data_type == "tick":
        kwargs["date"] = str(tick_date) if tick_date else None
    return kwargs


def _display_import_result(record):
    status = record.status.value
    if status == "success":
        st.success("导入成功")
    elif status == "partial":
        st.warning("部分导入成功")
    else:
        st.error(f"导入失败: {record.error_message or '未知错误'}")
        return

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("记录数", f"{record.record_count}")
    with col2:
        st.metric("耗时", f"{record.import_duration_ms} ms")
    with col3:
        st.metric("文件大小", _format_size(record.file_size_bytes))
    with col4:
        if record.start_date and record.end_date:
            st.metric("数据范围", f"{record.start_date} ~ {record.end_date}")
        else:
            st.metric("数据范围", "-")


# ======================================================================
# Tab 2: Import Status
# ======================================================================

def _render_import_status():
    st.subheader("导入状态")

    if "data_service" not in st.session_state:
        st.session_state.data_service = DataService()
    svc: DataService = st.session_state.data_service

    col_filter1, col_filter2 = st.columns(2)
    with col_filter1:
        filter_symbol = st.text_input("股票代码筛选", value="", key="status_filter_symbol")
    with col_filter2:
        filter_type_display = st.selectbox(
            "数据类型筛选",
            ["全部"] + list(DATA_TYPE_OPTIONS.keys()),
            key="status_filter_type",
        )

    filter_type = DATA_TYPE_OPTIONS.get(filter_type_display) if filter_type_display != "全部" else None

    try:
        records = svc.get_import_status(
            symbol=filter_symbol.strip() or None,
            data_type=filter_type,
        )
    except Exception:
        records = []

    if not records:
        st.info("暂无导入记录")
        return

    # Display as table
    rows = []
    for r in records:
        type_cn = r.data_type.value
        for cn, en in DATA_TYPE_OPTIONS.items():
            if en == r.data_type.value:
                type_cn = cn
                break

        date_range = ""
        if r.start_date and r.end_date:
            date_range = f"{r.start_date} ~ {r.end_date}"

        status_icon = {"success": "成功", "partial": "部分", "failed": "失败"}.get(r.status.value, r.status.value)

        rows.append({
            "股票代码": r.symbol,
            "数据类型": type_cn,
            "状态": status_icon,
            "记录数": r.record_count,
            "数据范围": date_range,
            "导入时间": r.imported_at[:19] if r.imported_at else "-",
            "耗时(ms)": r.import_duration_ms or 0,
            "文件大小": _format_size(r.file_size_bytes),
        })

    df_status = pd.DataFrame(rows)
    st.dataframe(df_status, use_container_width=True, hide_index=True)

    # Actions
    st.markdown("---")
    st.markdown("### 操作")

    col_a1, col_a2, col_a3 = st.columns(3)
    with col_a1:
        action_symbol = st.text_input("股票代码", value="", key="action_symbol")
    with col_a2:
        action_type_display = st.selectbox("数据类型", list(DATA_TYPE_OPTIONS.keys()), key="action_type")
        action_type = DATA_TYPE_OPTIONS[action_type_display]
    with col_a3:
        st.markdown("<br>", unsafe_allow_html=True)
        col_b1, col_b2 = st.columns(2)
        with col_b1:
            if st.button("增量导入", key="status_incremental"):
                if action_symbol.strip():
                    with st.spinner("正在增量导入..."):
                        record = svc.incremental_import(action_symbol.strip(), action_type)
                        _display_import_result(record)
                        st.rerun()
        with col_b2:
            if st.button("完整重导", key="status_reimport"):
                if action_symbol.strip():
                    with st.spinner("正在重导..."):
                        record = svc.reimport_data(action_symbol.strip(), action_type)
                        _display_import_result(record)
                        st.rerun()


# ======================================================================
# Tab 3: Data Browser
# ======================================================================

def _render_data_browser():
    st.subheader("数据浏览")

    if "data_service" not in st.session_state:
        st.session_state.data_service = DataService()
    svc: DataService = st.session_state.data_service

    col_b1, col_b2 = st.columns(2)
    with col_b1:
        browse_type_display = st.selectbox(
            "数据类型",
            list(DATA_TYPE_OPTIONS.keys()),
            key="browse_type",
        )
        browse_type = DATA_TYPE_OPTIONS[browse_type_display]
    with col_b2:
        pm = ParquetManager()
        symbols = pm.list_symbols(data_type=browse_type)
        if not symbols:
            st.info(f"暂无 {browse_type_display} 数据")
            return
        selected_symbol = st.selectbox("股票代码", symbols, key="browse_symbol")

    if selected_symbol:
        df = svc.load_from_parquet(selected_symbol, data_type=browse_type)
        if df is not None and not df.empty:
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("记录数", len(df))
            with col2:
                st.metric("列数", len(df.columns))
            with col3:
                cols_display = ", ".join(df.columns[:5])
                if len(df.columns) > 5:
                    cols_display += "..."
                st.metric("列名", cols_display)

            _render_paginated_table(df, key_prefix=f"browse_{browse_type}")

            st.markdown("---")
            if st.button(f"删除 {selected_symbol} 的{browse_type_display}数据", key=f"del_browse_{browse_type}_{selected_symbol}"):
                pm.delete(selected_symbol, data_type=browse_type)
                st.success(f"已删除 {selected_symbol} 的{browse_type_display}数据")
                st.rerun()
        else:
            st.warning("无法加载该文件")


# ======================================================================
# Tab 4: Source List (unchanged)
# ======================================================================

def _render_source_list():
    st.subheader("数据源列表")

    ds = DataService()
    sources = ds.list_data_sources()

    if not sources:
        st.info("暂无数据源配置。请在「系统配置」→「数据源管理」中添加。")
        return

    for src in sources:
        status_icon = "启用" if src["enabled"] else "禁用"
        st.markdown(f"**{src['name']}** — 类型: {src['type']} | 优先级: {src.get('priority', 0)} | {status_icon}")
