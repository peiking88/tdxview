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

        版本: 1.4.1
        """
    }
)

# 加载全局暗色主题 CSS
_css_path = Path(__file__).parent / "static" / "style.css"
if _css_path.exists():
    st.markdown(f"<style>{_css_path.read_text()}</style>", unsafe_allow_html=True)

# 应用设置
settings = get_settings()

def main():
    """主应用函数"""

    if "current_page" not in st.session_state:
        st.session_state.current_page = "charts"

    # 侧边栏导航
    with st.sidebar:
        st.markdown(
            '<div style="text-align:center;padding:16px 0 10px 0;margin-top:-30px">'
            '<svg width="280" height="90" viewBox="0 0 280 90" xmlns="http://www.w3.org/2000/svg">'
            '<defs>'
            '  <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">'
            '    <stop offset="0%" stop-color="#1a56db"/>'
            '    <stop offset="100%" stop-color="#3b82f6"/>'
            '  </linearGradient>'
            '  <linearGradient id="area" x1="0" y1="1" x2="0" y2="0">'
            '    <stop offset="0%" stop-color="#1a56db" stop-opacity="0.3"/>'
            '    <stop offset="100%" stop-color="#3b82f6" stop-opacity="0.02"/>'
            '  </linearGradient>'
            '</defs>'
            ''
            '<!-- Logo Icon (72x72) -->'
            '<rect x="0" y="4" width="72" height="72" rx="18" fill="url(#bg)"/>'
            ''
            '<!-- Grid lines -->'
            '<line x1="16" y1="22" x2="56" y2="22" stroke="white" stroke-opacity="0.12" stroke-width="0.8"/>'
            '<line x1="16" y1="35" x2="56" y2="35" stroke="white" stroke-opacity="0.12" stroke-width="0.8"/>'
            '<line x1="16" y1="48" x2="56" y2="48" stroke="white" stroke-opacity="0.12" stroke-width="0.8"/>'
            '<line x1="16" y1="61" x2="56" y2="61" stroke="white" stroke-opacity="0.12" stroke-width="0.8"/>'
            ''
            '<!-- Candlestick 1 (green) -->'
            '<line x1="22" y1="28" x2="22" y2="60" stroke="#34d399" stroke-width="1.2"/>'
            '<rect x="18.5" y="35" width="7" height="15" rx="1.5" fill="#34d399"/>'
            ''
            '<!-- Candlestick 2 (red) -->'
            '<line x1="36" y1="25" x2="36" y2="58" stroke="#f87171" stroke-width="1.2"/>'
            '<rect x="32.5" y="30" width="7" height="18" rx="1.5" fill="#f87171"/>'
            ''
            '<!-- Candlestick 3 (green, tall breakout) -->'
            '<line x1="50" y1="18" x2="50" y2="62" stroke="#34d399" stroke-width="1.2"/>'
            '<rect x="46.5" y="24" width="7" height="24" rx="1.5" fill="#34d399"/>'
            ''
            '<!-- Area fill -->'
            '<polygon points="22,50 36,48 50,48 50,65 36,65 22,65" fill="url(#area)"/>'
            ''
            '<!-- Title -->'
            '<text x="84" y="40" fill="#111827" font-size="36" font-family="system-ui,-apple-system,sans-serif" font-weight="800" letter-spacing="-1.5">tdx</text>'
            '<text x="152" y="40" fill="#6b7280" font-size="36" font-family="system-ui,-apple-system,sans-serif" font-weight="200" letter-spacing="-1.5">view</text>'
            ''
            '<!-- Tagline -->'
            '<text x="84" y="66" fill="#9ca3af" font-size="12" font-family="system-ui,-apple-system,sans-serif" font-weight="500" letter-spacing="4">DATA INSIGHTS</text>'
            ''
            '</svg></div>',
            unsafe_allow_html=True,
        )

        # 导航菜单 — 水平平铺按钮
        pages = [
            ("图表分析", "charts", "📊"),
            ("技术指标", "indicators", "📐"),
            ("系统配置", "config", "⚙️"),
        ]
        page_names = [p[0] for p in pages]
        cols = st.columns(len(pages))
        for i, (label, key, icon) in enumerate(pages):
            with cols[i]:
                is_active = st.session_state.current_page == key
                btn_type = "primary" if is_active else "secondary"
                if st.button(f"{icon} {label}", key=f"nav_{key}", use_container_width=True, type=btn_type):
                    st.session_state.current_page = key
                    st.rerun()

    # 主内容区域
    if st.session_state.current_page == "charts":
        chart_component()
    elif st.session_state.current_page == "indicators":
        indicator_component()
    elif st.session_state.current_page == "config":
        config_component()

    # 页脚
    st.markdown("---")
    st.markdown(
        f'<div class="app-footer">'
        f'<strong>tdxview</strong> {settings.app.version}  ·  '
        f'{"开发环境" if settings.app.debug else "生产环境"}  ·  '
        f'运行中'
        f'</div>',
        unsafe_allow_html=True,
    )

def initialize_app():
    """初始化应用"""
    # 检查必要目录
    log_dir = Path(settings.logging.file_path).parent

    for directory in [log_dir]:
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
