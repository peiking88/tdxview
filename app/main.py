#!/usr/bin/env python3
"""
tdxview 主应用入口
基于Streamlit的数据可视化平台
"""

import streamlit as st
import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config.settings import get_settings
from app.components.charts import chart_component
from app.components.indicators import indicator_component
from app.components.config import config_component
from app.components.data_management import data_management_component

# 页面配置
st.set_page_config(
    page_title="tdxview - 数据可视化平台",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "Get Help": "https://github.com/tdxview/tdxview",
        "Report a bug": "https://github.com/tdxview/tdxview/issues",
        "About": """
        ## tdxview 数据可视化平台

        基于tdxdata的历史数据分析和技术指标计算平台。

        版本: 1.1.0
        """
    }
)

# 应用设置
settings = get_settings()

def main():
    """主应用函数"""

    if "current_page" not in st.session_state:
        st.session_state.current_page = "charts"

    # 应用标题
    st.title("📈 tdxview 数据可视化平台")
    st.markdown("---")

    # 侧边栏导航
    with st.sidebar:
        st.markdown(
            '<div style="text-align:center;padding:10px 0;">'
            '<svg width="180" height="52" viewBox="0 0 180 52" xmlns="http://www.w3.org/2000/svg">'
            '<defs>'
            '<linearGradient id="logoGrad" x1="0%" y1="0%" x2="100%" y2="100%">'
            '<stop offset="0%" style="stop-color:#1a73e8;stop-opacity:1"/>'
            '<stop offset="100%" style="stop-color:#0d47a1;stop-opacity:1"/>'
            '</linearGradient>'
            '<linearGradient id="chartGrad" x1="0%" y1="100%" x2="0%" y2="0%">'
            '<stop offset="0%" style="stop-color:#1a73e8;stop-opacity:0.15"/>'
            '<stop offset="100%" style="stop-color:#1a73e8;stop-opacity:0.02"/>'
            '</linearGradient>'
            '</defs>'
            '<rect x="0" y="6" width="40" height="40" rx="10" fill="url(#logoGrad)"/>'
            '<polyline points="6,38 13,30 20,34 27,18 34,22" fill="none" stroke="white" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>'
            '<polygon points="6,38 13,30 20,34 27,18 34,22 34,40 6,40" fill="url(#chartGrad)"/>'
            '<circle cx="34" cy="22" r="2.5" fill="#4fc3f7"/>'
            '<text x="48" y="24" fill="#1a73e8" font-size="22" font-family="Segoe UI,Arial,sans-serif" font-weight="700" letter-spacing="-0.5">tdx</text>'
            '<text x="95" y="24" fill="#5f6368" font-size="22" font-family="Segoe UI,Arial,sans-serif" font-weight="300" letter-spacing="-0.5">view</text>'
            '<text x="48" y="42" fill="#80868b" font-size="10" font-family="Segoe UI,Arial,sans-serif" font-weight="400" letter-spacing="2">DATA INSIGHTS</text>'
            '</svg></div>',
            unsafe_allow_html=True,
        )
        st.caption("数据驱动决策")

        # 导航菜单
        st.markdown("### 导航")
        pages = ["图表分析", "技术指标", "数据管理", "系统配置"]
        page_index = pages.index(st.session_state.current_page) if st.session_state.current_page in pages else 0
        page = st.radio(
            "选择页面",
            pages,
            index=page_index,
            label_visibility="collapsed",
        )

        page_mapping = {
            "图表分析": "charts",
            "技术指标": "indicators",
            "数据管理": "data_management",
            "系统配置": "config",
        }
        st.session_state.current_page = page_mapping.get(page, "charts")

    # 主内容区域
    if st.session_state.current_page == "charts":
        chart_component()
    elif st.session_state.current_page == "indicators":
        indicator_component()
    elif st.session_state.current_page == "data_management":
        data_management_component()
    elif st.session_state.current_page == "config":
        config_component()

    # 页脚
    st.markdown("---")
    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown(f"**版本**: {settings.app.version}")

    with col2:
        st.markdown("**环境**: 开发" if settings.app.debug else "**环境**: 生产")

    with col3:
        st.markdown("**状态**: 🟢 运行中")

def initialize_app():
    """初始化应用"""
    # 检查必要目录
    data_dir = Path(settings.database.parquet_dir)
    cache_dir = Path(settings.database.cache_dir)
    log_dir = Path(settings.logging.file_path).parent

    for directory in [data_dir, cache_dir, log_dir]:
        directory.mkdir(parents=True, exist_ok=True)

    # 初始化数据库（如果表不存在）
    db_path = Path(settings.database.duckdb_path)
    needs_init = True
    if db_path.exists():
        try:
            import duckdb
            conn = duckdb.connect(str(db_path), read_only=True)
            tables = [r[0] for r in conn.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'").fetchall()]
            conn.close()
            required = {"users", "data_sources", "indicators", "dashboards"}
            needs_init = not required.issubset(set(tables))
            if not needs_init and "data_imports" not in tables:
                needs_init = True
        except Exception:
            needs_init = True

    if needs_init:
        try:
            from scripts.init_database import init_database
            init_database()
        except Exception as e:
            st.error(f"数据库初始化失败: {e}")

if __name__ == "__main__":
    # 初始化应用
    initialize_app()

    # 运行主应用
    try:
        main()
    except Exception as e:
        st.error(f"应用运行错误: {e}")
        st.exception(e)