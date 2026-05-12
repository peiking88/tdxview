"""
Config component — data source management, storage info, log viewer.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st

from app.config.settings import get_settings, reload_settings
from app.data.database import DatabaseManager
from app.services.data_service import DataService


# ---------------------------------------------------------------------------
# Data source helpers
# ---------------------------------------------------------------------------

def _list_sources() -> List[Dict[str, Any]]:
    """List all data sources from DB."""
    ds = DataService()
    return ds.list_data_sources()


def _update_source(source_id: int, **kwargs) -> bool:
    ds = DataService()
    return ds.update_data_source(source_id, **kwargs)


def _delete_source(source_id: int) -> bool:
    ds = DataService()
    return ds.delete_data_source(source_id)


def _check_source_health() -> Dict[str, Any]:
    ds = DataService()
    return ds.check_source_health()


# ---------------------------------------------------------------------------
# Log viewer helpers
# ---------------------------------------------------------------------------

def _read_log_lines(log_path: str, n: int = 200) -> List[str]:
    """Read the last *n* lines from the log file."""
    path = Path(log_path)
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return lines[-n:]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Main config component
# ---------------------------------------------------------------------------

def config_component():
    """Render the system configuration page."""
    st.header("系统配置")

    tab_ds, tab_storage, tab_log, tab_sys = st.tabs(
        ["数据源管理", "存储管理", "日志查看", "系统信息"]
    )

    with tab_ds:
        _render_data_sources()

    with tab_storage:
        _render_storage_config()

    with tab_log:
        _render_log_viewer()

    with tab_sys:
        _render_system_info()


# ======================================================================
# Tab 1: Data Source Management
# ======================================================================

def _render_data_sources():
    """View and manage data sources."""
    st.subheader("数据源管理")

    # --- Existing sources ---
    sources = _list_sources()
    if sources:
        for src in sources:
            with st.expander(f"**{src['name']}** ({src['type']}) — {'启用' if src['enabled'] else '禁用'}"):
                col1, col2, col3 = st.columns([4, 1, 1])
                with col1:
                    st.json(src.get("config", {}))
                    st.caption(f"优先级: {src.get('priority', 0)}  |  ID: {src['id']}")
                with col2:
                    new_status = not src["enabled"]
                    label = "启用" if new_status else "禁用"
                    if st.button(label, key=f"toggle_src_{src['id']}"):
                        _update_source(src["id"], enabled=new_status)
                        st.success(f"已{label}数据源「{src['name']}」")
                        st.rerun()
                with col3:
                    if st.button("删除", key=f"del_src_{src['id']}"):
                        _delete_source(src["id"])
                        st.success(f"已删除数据源「{src['name']}」")
                        st.rerun()
    else:
        st.info("暂无数据源。")

    # --- Health check ---
    st.markdown("---")
    if st.button("检查连接", key="check_ds_health"):
        with st.spinner("正在检查数据源连接..."):
            result = _check_source_health()
            if result.get("connected"):
                st.success(f"数据源连接正常 (检查时间: {result.get('checked_at', '')})")
            else:
                st.error("数据源连接失败")


# ======================================================================
# Tab 2: Storage Configuration
# ======================================================================

def _render_storage_config():
    """DuckDB storage statistics and management."""
    st.subheader("存储管理")
    settings = get_settings()

    # --- Database file info ---
    db_path = Path(settings.database.duckdb_path)
    db_size_mb = round(db_path.stat().st_size / 1e6, 2) if db_path.exists() else 0

    c1, c2, c3 = st.columns(3)
    c1.metric("数据库路径", str(db_path))
    c2.metric("数据库大小", f"{db_size_mb} MB")
    c3.metric("WAL模式", "启用" if settings.database.wal_mode else "禁用")

    # --- Table row counts ---
    st.markdown("##### 各表数据量")
    db = DatabaseManager()
    table_labels = {
        "kline": "K线", "tick": "逐笔", "financial": "财务",
        "f10": "F10", "factor": "复权因子", "basic": "除权除息",
        "realtime": "实时行情",
    }
    cols = st.columns(len(table_labels))
    for i, (table, label) in enumerate(table_labels.items()):
        try:
            row = db.fetch_one(f"SELECT count(*) FROM {table}")
            count = row[0] if row else 0
        except Exception:
            count = 0
        with cols[i]:
            st.metric(label, f"{count:,}")

    # --- Optimize database ---
    st.markdown("##### 数据库操作")
    if st.button("优化数据库 (CHECKPOINT)", key="optimize_db", use_container_width=True):
        try:
            db.execute("CHECKPOINT")
            db.connection.commit()
            st.success("数据库优化完成")
            st.rerun()
        except Exception as e:
            st.error(f"优化失败: {e}")


# ======================================================================
# Tab 3: Log Viewer
# ======================================================================

def _render_log_viewer():
    """View and search application logs."""
    st.subheader("日志查看")
    settings = get_settings()
    log_path = settings.logging.file_path

    # --- Controls ---
    col_lines, col_level, col_refresh = st.columns([1, 1, 1])
    with col_lines:
        line_count = st.number_input("显示行数", value=100, min_value=10, max_value=2000, step=50)
    with col_level:
        level_filter = st.selectbox("过滤级别", ["ALL", "INFO", "WARNING", "ERROR", "DEBUG"], index=0)
    with col_refresh:
        if st.button("刷新", key="refresh_logs"):
            st.rerun()

    # --- Log content ---
    lines = _read_log_lines(log_path, n=int(line_count))
    if not lines:
        st.info(f"日志文件为空或不存在 ({log_path})")
        return

    # Apply level filter
    if level_filter != "ALL":
        lines = [l for l in lines if f" {level_filter} " in l or f"| {level_filter} " in l]

    # Display in a code block
    log_text = "".join(lines)
    st.code(log_text, language="log")

    # --- Log file info ---
    st.markdown("---")
    log_file = Path(log_path)
    if log_file.exists():
        col_l1, col_l2, col_l3 = st.columns(3)
        with col_l1:
            st.metric("日志文件", log_path)
        with col_l2:
            st.metric("文件大小", f"{log_file.stat().st_size / 1024:.1f} KB")
        with col_l3:
            mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
            st.metric("最后修改", mtime.strftime("%Y-%m-%d %H:%M:%S"))
    else:
        st.warning(f"日志文件不存在: {log_path}")

    # --- Log level configuration ---
    st.markdown("---")
    st.subheader("日志级别设置")
    current_level = settings.logging.level
    new_level = st.selectbox(
        "日志级别",
        ["DEBUG", "INFO", "WARNING", "ERROR"],
        index=["DEBUG", "INFO", "WARNING", "ERROR"].index(current_level) if current_level in ["DEBUG", "INFO", "WARNING", "ERROR"] else 1,
        key="log_level_select",
    )
    if st.button("应用日志级别", key="apply_log_level"):
        from app.utils.logging import setup_logger
        setup_logger(level=new_level, log_path=log_path)
        st.success(f"日志级别已切换为 {new_level}")


# ======================================================================
# Tab 4: System Info
# ======================================================================

def _render_system_info():
    """Display system configuration summary and reload controls."""
    st.subheader("系统配置信息")
    settings = get_settings()

    config_summary = {
        "应用": {
            "名称": settings.app.name,
            "版本": settings.app.version,
            "环境": settings.environment,
            "调试模式": settings.app.debug,
        },
        "数据库": {
            "路径": settings.database.duckdb_path,
            "WAL模式": settings.database.wal_mode,
        },
        "数据源": {
            "API地址": settings.tdxdata.api_url,
            "超时时间": f"{settings.tdxdata.timeout}秒",
            "重试次数": settings.tdxdata.retry_count,
            "API密钥已设置": bool(settings.tdxdata.api_key),
        },
        "安全": {
            "认证启用": settings.security.authentication_enabled,
            "授权启用": settings.security.authorization_enabled,
            "会话超时": f"{settings.security.session_timeout}秒",
        },
        "日志": {
            "级别": settings.logging.level,
            "文件路径": settings.logging.file_path,
            "文件日志": settings.logging.file_enabled,
        },
    }
    st.json(config_summary)

    st.markdown("---")
    if st.button("重新加载配置", key="reload_config"):
        reload_settings()
        st.success("配置已重新加载")
        st.rerun()
