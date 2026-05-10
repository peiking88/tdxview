"""
Dashboard component — real-time monitoring, widgets, alerts, and system status.
"""

import json
import os
import platform
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import psutil
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

from app.config.settings import get_settings
from app.data.database import DatabaseManager


# ---------------------------------------------------------------------------
# System monitoring helpers
# ---------------------------------------------------------------------------

def _get_system_metrics() -> Dict[str, Any]:
    """Collect system performance metrics."""
    try:
        cpu_percent = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        return {
            "cpu_percent": cpu_percent,
            "memory_total_gb": round(mem.total / 1e9, 1),
            "memory_used_gb": round(mem.used / 1e9, 1),
            "memory_percent": mem.percent,
            "disk_total_gb": round(disk.total / 1e9, 1),
            "disk_used_gb": round(disk.used / 1e9, 1),
            "disk_percent": disk.percent,
        }
    except Exception:
        return {}


def _get_app_metrics() -> Dict[str, Any]:
    """Collect application-specific metrics."""
    settings = get_settings()
    db_path = Path(settings.database.duckdb_path)
    db_size_mb = round(db_path.stat().st_size / 1e6, 2) if db_path.exists() else 0

    return {
        "db_size_mb": db_size_mb,
        "db_path": str(db_path),
        "parquet_dir": settings.database.parquet_dir,
        "cache_dir": settings.database.cache_dir,
        "log_dir": str(Path(settings.logging.file_path).parent),
        "environment": settings.environment,
        "debug": settings.app.debug,
    }


def _get_data_source_status() -> List[Dict[str, Any]]:
    """Get status of all configured data sources."""
    db = DatabaseManager()
    try:
        rows = db.fetch_all(
            "SELECT id, name, type, enabled, last_checked, error_count FROM data_sources ORDER BY priority"
        )
        return [
            {"id": r[0], "name": r[1], "type": r[2], "enabled": r[3],
             "last_checked": str(r[4]) if r[4] else "Never", "error_count": r[5]}
            for r in rows
        ]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Dashboard CRUD helpers (session state backed by DB)
# ---------------------------------------------------------------------------

def _list_dashboards(user_id: int) -> List[Dict[str, Any]]:
    db = DatabaseManager()
    try:
        rows = db.fetch_all(
            "SELECT id, name, description, is_default, created_at FROM dashboards WHERE user_id = ? ORDER BY id",
            [user_id],
        )
        return [
            {"id": r[0], "name": r[1], "description": r[2], "is_default": r[3], "created_at": str(r[4])}
            for r in rows
        ]
    except Exception:
        return []


def _create_dashboard(user_id: int, name: str, description: str = "") -> bool:
    db = DatabaseManager()
    try:
        layout = json.dumps({"type": "grid", "columns": 12, "row_height": 30})
        widgets = json.dumps([])
        db.execute(
            "INSERT INTO dashboards (user_id, name, description, layout, widgets) VALUES (?, ?, ?, ?, ?)",
            [user_id, name, description, layout, widgets],
        )
        db.connection.commit()
        return True
    except Exception:
        return False


def _delete_dashboard(dashboard_id: int) -> bool:
    db = DatabaseManager()
    try:
        db.execute("DELETE FROM dashboards WHERE id = ?", [dashboard_id])
        db.connection.commit()
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Alert helpers
# ---------------------------------------------------------------------------

ALERT_THRESHOLDS_KEY = "alert_thresholds"

def _get_thresholds() -> Dict[str, Any]:
    return st.session_state.get(ALERT_THRESHOLDS_KEY, {
        "cpu_percent": 80,
        "memory_percent": 80,
        "disk_percent": 90,
        "db_size_mb": 500,
        "error_count": 5,
    })


def _set_thresholds(thresholds: Dict[str, Any]):
    st.session_state[ALERT_THRESHOLDS_KEY] = thresholds


def _check_alerts(metrics: Dict[str, Any], thresholds: Dict[str, Any]) -> List[str]:
    alerts = []
    sys_m = metrics.get("system", {})
    app_m = metrics.get("app", {})

    if sys_m.get("cpu_percent", 0) > thresholds.get("cpu_percent", 80):
        alerts.append(f"CPU 使用率过高: {sys_m['cpu_percent']:.1f}%")
    if sys_m.get("memory_percent", 0) > thresholds.get("memory_percent", 80):
        alerts.append(f"内存使用率过高: {sys_m['memory_percent']:.1f}%")
    if sys_m.get("disk_percent", 0) > thresholds.get("disk_percent", 90):
        alerts.append(f"磁盘使用率过高: {sys_m['disk_percent']:.1f}%")
    if app_m.get("db_size_mb", 0) > thresholds.get("db_size_mb", 500):
        alerts.append(f"数据库体积过大: {app_m['db_size_mb']:.1f} MB")
    return alerts


# ---------------------------------------------------------------------------
# Main dashboard component
# ---------------------------------------------------------------------------

def dashboard_component():
    """Render the dashboard page."""
    st.header("仪表板")

    user_id = st.session_state.get("user_id", 0)

    # ---- Tab layout ----
    tab_overview, tab_manage, tab_alerts = st.tabs(["系统概览", "仪表板管理", "警报设置"])

    # ======================================================================
    # Tab 1: System Overview
    # ======================================================================
    with tab_overview:
        _render_overview()

    # ======================================================================
    # Tab 2: Dashboard Management
    # ======================================================================
    with tab_manage:
        _render_dashboard_management(user_id)

    # ======================================================================
    # Tab 3: Alert Settings
    # ======================================================================
    with tab_alerts:
        _render_alert_settings()


def _render_overview():
    """System overview with metrics, charts, and data source status."""
    sys_metrics = _get_system_metrics()
    app_metrics = _get_app_metrics()
    thresholds = _get_thresholds()

    # Alert banner
    alerts = _check_alerts({"system": sys_metrics, "app": app_metrics}, thresholds)
    for alert in alerts:
        st.warning(f"⚠ {alert}")

    # --- Metric cards ---
    st.subheader("系统状态")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        cpu = sys_metrics.get("cpu_percent", 0)
        st.metric("CPU", f"{cpu:.1f}%", delta=None,
                  delta_color="inverse" if cpu > 80 else "normal")
    with col2:
        mem = sys_metrics.get("memory_percent", 0)
        mem_used = sys_metrics.get("memory_used_gb", 0)
        mem_total = sys_metrics.get("memory_total_gb", 0)
        st.metric("内存", f"{mem_used}/{mem_total} GB ({mem:.1f}%)")
    with col3:
        disk = sys_metrics.get("disk_percent", 0)
        disk_used = sys_metrics.get("disk_used_gb", 0)
        disk_total = sys_metrics.get("disk_total_gb", 0)
        st.metric("磁盘", f"{disk_used}/{disk_total} GB ({disk:.1f}%)")
    with col4:
        db_size = app_metrics.get("db_size_mb", 0)
        st.metric("数据库", f"{db_size} MB")

    # --- Usage gauges ---
    col_g1, col_g2 = st.columns(2)
    with col_g1:
        fig_cpu = _gauge_chart("CPU 使用率", cpu, thresholds.get("cpu_percent", 80))
        st.plotly_chart(fig_cpu, use_container_width=True)
    with col_g2:
        fig_mem = _gauge_chart("内存使用率", mem, thresholds.get("memory_percent", 80))
        st.plotly_chart(fig_mem, use_container_width=True)

    # --- App info ---
    st.subheader("应用信息")
    col_a1, col_a2, col_a3 = st.columns(3)
    with col_a1:
        st.info(f"环境: **{app_metrics.get('environment', '?')}**")
    with col_a2:
        st.info(f"调试模式: **{app_metrics.get('debug', False)}**")
    with col_a3:
        st.info(f"平台: **{platform.system()} {platform.release()}**")

    # --- Data sources ---
    st.subheader("数据源状态")
    sources = _get_data_source_status()
    if sources:
        df_sources = pd.DataFrame(sources)
        st.dataframe(df_sources, use_container_width=True, hide_index=True)
    else:
        st.info("暂无数据源配置。请在「系统配置」页面添加。")

    # Refresh button
    if st.button("刷新状态", key="refresh_overview"):
        st.rerun()


def _render_dashboard_management(user_id: int):
    """Create, switch, and delete dashboards."""
    st.subheader("我的仪表板")

    # List existing dashboards
    dashboards = _list_dashboards(user_id)
    if dashboards:
        for db in dashboards:
            col1, col2, col3 = st.columns([6, 1, 1])
            with col1:
                default_tag = " (默认)" if db["is_default"] else ""
                st.markdown(f"**{db['name']}**{default_tag}")
                if db["description"]:
                    st.caption(db["description"])
            with col2:
                if st.button("切换", key=f"switch_{db['id']}"):
                    st.session_state.current_dashboard_id = db["id"]
                    st.success(f"已切换到: {db['name']}")
            with col3:
                if st.button("删除", key=f"del_{db['id']}"):
                    _delete_dashboard(db["id"])
                    st.rerun()
    else:
        st.info("暂无仪表板，请创建一个。")

    # Create new dashboard
    st.markdown("---")
    with st.form("create_dashboard_form"):
        new_name = st.text_input("仪表板名称", placeholder="输入名称")
        new_desc = st.text_input("描述 (可选)", placeholder="输入描述")
        submit = st.form_submit_button("创建仪表板")
        if submit and new_name:
            if _create_dashboard(user_id, new_name, new_desc):
                st.success(f"仪表板「{new_name}」创建成功！")
                st.rerun()
            else:
                st.error("创建失败")


def _render_alert_settings():
    """Alert threshold configuration."""
    st.subheader("警报阈值设置")

    thresholds = _get_thresholds()

    with st.form("alert_form"):
        st.markdown("设置各项指标的警报阈值：")
        t_cpu = st.number_input("CPU 使用率 (%)", value=thresholds.get("cpu_percent", 80), min_value=0, max_value=100)
        t_mem = st.number_input("内存使用率 (%)", value=thresholds.get("memory_percent", 80), min_value=0, max_value=100)
        t_disk = st.number_input("磁盘使用率 (%)", value=thresholds.get("disk_percent", 90), min_value=0, max_value=100)
        t_db = st.number_input("数据库体积 (MB)", value=thresholds.get("db_size_mb", 500), min_value=0)
        t_err = st.number_input("数据源错误次数", value=thresholds.get("error_count", 5), min_value=0)

        if st.form_submit_button("保存阈值"):
            _set_thresholds({
                "cpu_percent": t_cpu,
                "memory_percent": t_mem,
                "disk_percent": t_disk,
                "db_size_mb": t_db,
                "error_count": t_err,
            })
            st.success("阈值已保存！")


def _gauge_chart(title: str, value: float, threshold: float) -> go.Figure:
    """Create a semi-circle gauge chart."""
    color = "green" if value < threshold * 0.8 else ("orange" if value < threshold else "red")
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value,
        title={"text": title},
        gauge={
            "axis": {"range": [0, 100]},
            "bar": {"color": color},
            "steps": [
                {"range": [0, threshold * 0.8], "color": "rgba(0,200,0,0.1)"},
                {"range": [threshold * 0.8, threshold], "color": "rgba(255,165,0,0.1)"},
                {"range": [threshold, 100], "color": "rgba(255,0,0,0.1)"},
            ],
            "threshold": {"line": {"color": "red", "width": 2}, "value": threshold},
        },
    ))
    fig.update_layout(height=250, margin={"l": 30, "r": 30, "t": 50, "b": 10})
    return fig
