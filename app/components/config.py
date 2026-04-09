"""
Config component — data source management, cache settings, log viewer,
user preferences, and configuration import/export.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st

from app.config.settings import get_settings, reload_settings
from app.data.cache import CacheManager, MemoryCache, DiskCache
from app.data.database import DatabaseManager
from app.services.data_service import DataService
from app.services.user_service import (
    get_user_preferences,
    update_user_preferences,
    export_user_config,
    import_user_config,
)


# ---------------------------------------------------------------------------
# Data source helpers
# ---------------------------------------------------------------------------

def _list_sources() -> List[Dict[str, Any]]:
    """List all data sources from DB."""
    ds = DataService()
    return ds.list_data_sources()


def _add_source(name: str, source_type: str, config: Dict, priority: int, enabled: bool) -> int:
    ds = DataService()
    return ds.add_data_source(name, source_type, config, priority, enabled)


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

    tab_ds, tab_cache, tab_log, tab_prefs, tab_io = st.tabs(
        ["数据源管理", "缓存配置", "日志查看", "用户偏好", "配置导入导出"]
    )

    with tab_ds:
        _render_data_sources()

    with tab_cache:
        _render_cache_config()

    with tab_log:
        _render_log_viewer()

    with tab_prefs:
        _render_user_preferences()

    with tab_io:
        _render_config_io()


# ======================================================================
# Tab 1: Data Source Management
# ======================================================================

def _render_data_sources():
    """CRUD for data sources."""
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
        st.info("暂无数据源，请添加一个。")

    # --- Health check ---
    st.markdown("---")
    if st.button("检查连接", key="check_ds_health"):
        with st.spinner("正在检查数据源连接..."):
            result = _check_source_health()
            if result.get("connected"):
                st.success(f"数据源连接正常 (检查时间: {result.get('checked_at', '')})")
            else:
                st.error("数据源连接失败")

    # --- Add new source ---
    st.markdown("---")
    st.subheader("添加数据源")
    with st.form("add_source_form"):
        new_name = st.text_input("名称", placeholder="例如: 通达信主站")
        new_type = st.selectbox("类型", ["tdx", "custom"], index=0)
        new_host = st.text_input("主机地址", value="119.147.212.81")
        new_port_val = st.number_input("端口", value=7709, min_value=1, max_value=65535)
        new_priority = st.number_input("优先级", value=1, min_value=1, max_value=100)
        new_enabled = st.checkbox("启用", value=True)

        if st.form_submit_button("添加"):
            if not new_name:
                st.error("请输入数据源名称")
            else:
                config = {"host": new_host, "port": int(new_port_val)}
                source_id = _add_source(new_name, new_type, config, int(new_priority), new_enabled)
                st.success(f"数据源「{new_name}」已添加 (ID: {source_id})")
                st.rerun()


# ======================================================================
# Tab 2: Cache Configuration
# ======================================================================

def _render_cache_config():
    """Cache settings and management."""
    st.subheader("缓存配置")
    settings = get_settings()

    # --- Current cache settings display ---
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### 内存缓存")
        st.metric("最大容量", f"{settings.cache.memory_max_size_mb} MB")
        st.metric("默认 TTL", f"{settings.cache.memory_default_ttl} 秒")
        st.metric("是否启用", "是" if settings.cache.memory_enabled else "否")

    with col2:
        st.markdown("#### 磁盘缓存")
        st.metric("最大容量", f"{settings.cache.disk_max_size_gb} GB")
        st.metric("是否压缩", "是" if settings.cache.disk_compression else "否")
        st.metric("是否启用", "是" if settings.cache.disk_enabled else "否")

    # --- Query cache ---
    st.markdown("---")
    st.markdown("#### 查询缓存")
    st.metric("默认 TTL", f"{settings.cache.query_ttl} 秒")
    st.metric("最大条目数", f"{settings.cache.query_max_items}")

    # --- Cache operations ---
    st.markdown("---")
    st.subheader("缓存操作")

    col_clear1, col_clear2, col_stats = st.columns(3)

    with col_clear1:
        if st.button("清空内存缓存", key="clear_mem_cache"):
            try:
                cm = CacheManager()
                cm.memory.clear()
                st.success("内存缓存已清空")
            except Exception as e:
                st.error(f"清空失败: {e}")

    with col_clear2:
        if st.button("清空磁盘缓存", key="clear_disk_cache"):
            try:
                cm = CacheManager()
                cm.disk.clear()
                st.success("磁盘缓存已清空")
            except Exception as e:
                st.error(f"清空失败: {e}")

    with col_stats:
        if st.button("清空全部缓存", key="clear_all_cache"):
            try:
                cm = CacheManager()
                cm.clear()
                st.success("全部缓存已清空")
            except Exception as e:
                st.error(f"清空失败: {e}")

    # --- Cache stats ---
    st.markdown("---")
    st.subheader("缓存统计")
    try:
        cm = CacheManager()
        col_s1, col_s2 = st.columns(2)
        with col_s1:
            st.metric("内存缓存条目数", cm.memory.count)
            st.metric("内存缓存大小", f"{cm.memory.size / 1024:.1f} KB")
        with col_s2:
            cache_dir = Path(settings.database.cache_dir) / "queries"
            if cache_dir.exists():
                disk_files = list(cache_dir.rglob("*.json"))
                disk_size = sum(f.stat().st_size for f in disk_files) / 1024
                st.metric("磁盘缓存文件数", len(disk_files))
                st.metric("磁盘缓存大小", f"{disk_size:.1f} KB")
            else:
                st.info("磁盘缓存目录为空")
    except Exception as e:
        st.warning(f"获取缓存统计失败: {e}")


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
# Tab 4: User Preferences
# ======================================================================

def _render_user_preferences():
    """User preference settings (theme, defaults, etc.)."""
    st.subheader("用户偏好设置")

    user_id = st.session_state.get("user_id", 0)
    if not user_id:
        st.warning("请先登录")
        return

    prefs = get_user_preferences(user_id)

    # --- Default page ---
    st.markdown("#### 默认页面")
    current_default = prefs.get("default_page", "dashboard")
    page_options = {
        "dashboard": "仪表板",
        "charts": "图表分析",
        "indicators": "技术指标",
        "config": "系统配置",
    }
    selected_page = st.selectbox(
        "登录后默认页面",
        list(page_options.keys()),
        index=list(page_options.keys()).index(current_default) if current_default in page_options else 0,
        format_func=lambda k: page_options[k],
        key="pref_default_page",
    )

    # --- Chart defaults ---
    st.markdown("#### 图表默认设置")
    chart_prefs = prefs.get("chart", {})
    default_period = st.selectbox(
        "默认周期",
        ["1d", "1w", "1M", "3M", "6M", "1y"],
        index=["1d", "1w", "1M", "3M", "6M", "1y"].index(chart_prefs.get("period", "1d")),
        key="pref_chart_period",
    )
    default_dividend = st.selectbox(
        "默认复权",
        ["front", "back", "none"],
        index=["front", "back", "none"].index(chart_prefs.get("dividend_type", "front")),
        key="pref_chart_dividend",
    )
    show_volume = st.checkbox("默认显示成交量", value=chart_prefs.get("show_volume", True), key="pref_show_volume")

    # --- Indicator defaults ---
    st.markdown("#### 指标默认设置")
    indicator_prefs = prefs.get("indicators", {})
    default_ma = st.text_input(
        "默认 MA 周期 (逗号分隔)",
        value=",".join(str(p) for p in indicator_prefs.get("ma_periods", [5, 10, 20, 60])),
        key="pref_ma_periods",
    )

    # --- Save ---
    st.markdown("---")
    if st.button("保存偏好", key="save_prefs"):
        try:
            ma_list = [int(x.strip()) for x in default_ma.split(",") if x.strip().isdigit()]
            updates = {
                "default_page": selected_page,
                "chart": {
                    "period": default_period,
                    "dividend_type": default_dividend,
                    "show_volume": show_volume,
                },
                "indicators": {
                    "ma_periods": ma_list,
                },
            }
            update_user_preferences(user_id, updates)
            st.success("偏好已保存！")
        except Exception as e:
            st.error(f"保存失败: {e}")


# ======================================================================
# Tab 5: Configuration Import/Export
# ======================================================================

def _render_config_io():
    """Import and export user configuration."""
    st.subheader("配置导入导出")

    user_id = st.session_state.get("user_id", 0)
    if not user_id:
        st.warning("请先登录")
        return

    col_exp, col_imp = st.columns(2)

    # --- Export ---
    with col_exp:
        st.markdown("#### 导出配置")
        st.markdown("将当前用户的偏好、仪表板等配置导出为 JSON 文件。")
        if st.button("导出配置", key="export_config"):
            config = export_user_config(user_id)
            if config:
                config_json = json.dumps(config, ensure_ascii=False, indent=2)
                st.download_button(
                    label="下载配置文件",
                    data=config_json,
                    file_name=f"tdxview_config_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    mime="application/json",
                    key="download_config_btn",
                )
                with st.expander("预览配置"):
                    st.json(config)
            else:
                st.error("导出失败，用户不存在")

    # --- Import ---
    with col_imp:
        st.markdown("#### 导入配置")
        st.markdown("从 JSON 文件恢复用户配置。")
        uploaded = st.file_uploader("选择配置文件", type=["json"], key="import_config_file")
        if uploaded is not None:
            try:
                config_data = json.loads(uploaded.read().decode("utf-8"))
                with st.expander("预览导入内容"):
                    st.json(config_data)
                if st.button("确认导入", key="confirm_import"):
                    success, msg = import_user_config(user_id, config_data)
                    if success:
                        st.success(msg)
                    else:
                        st.error(msg)
            except json.JSONDecodeError:
                st.error("无效的 JSON 文件")
            except Exception as e:
                st.error(f"导入失败: {e}")

    # --- System config ---
    st.markdown("---")
    st.subheader("系统配置信息")
    settings = get_settings()

    with st.expander("查看当前系统配置"):
        config_summary = {
            "应用": {
                "名称": settings.app.name,
                "版本": settings.app.version,
                "环境": settings.environment,
                "调试模式": settings.app.debug,
            },
            "数据库": {
                "路径": settings.database.duckdb_path,
                "Parquet目录": settings.database.parquet_dir,
                "缓存目录": settings.database.cache_dir,
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

    # --- Reload config ---
    if st.button("重新加载配置", key="reload_config"):
        reload_settings()
        st.success("配置已重新加载")
        st.rerun()
