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

        版本: 1.5.0
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
            '<div style="text-align:center;padding:16px 0 8px 0;margin-top:-30px">'
            '<svg width="260" height="80" viewBox="0 0 260 80" xmlns="http://www.w3.org/2000/svg">'
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
            '<rect x="0" y="4" width="64" height="64" rx="16" fill="url(#bg)"/>'
            '<line x1="14" y1="20" x2="50" y2="20" stroke="white" stroke-opacity="0.12" stroke-width="0.7"/>'
            '<line x1="14" y1="31" x2="50" y2="31" stroke="white" stroke-opacity="0.12" stroke-width="0.7"/>'
            '<line x1="14" y1="42" x2="50" y2="42" stroke="white" stroke-opacity="0.12" stroke-width="0.7"/>'
            '<line x1="14" y1="53" x2="50" y2="53" stroke="white" stroke-opacity="0.12" stroke-width="0.7"/>'
            '<line x1="20" y1="25" x2="20" y2="53" stroke="#34d399" stroke-width="1.1"/>'
            '<rect x="17" y="31" width="6" height="13" rx="1.2" fill="#34d399"/>'
            '<line x1="32" y1="22" x2="32" y2="51" stroke="#f87171" stroke-width="1.1"/>'
            '<rect x="29" y="26" width="6" height="16" rx="1.2" fill="#f87171"/>'
            '<line x1="44" y1="16" x2="44" y2="55" stroke="#34d399" stroke-width="1.1"/>'
            '<rect x="41" y="21" width="6" height="21" rx="1.2" fill="#34d399"/>'
            '<polygon points="20,45 32,43 44,43 44,58 32,58 20,58" fill="url(#area)"/>'
            '<text x="74" y="37" fill="#d1d4dc" font-size="32" font-family="system-ui,-apple-system,sans-serif" font-weight="800" letter-spacing="-1.2">tdx</text>'
            '<text x="134" y="37" fill="#787b86" font-size="32" font-family="system-ui,-apple-system,sans-serif" font-weight="200" letter-spacing="-1.2">view</text>'
            '<text x="74" y="58" fill="#4c525e" font-size="11" font-family="system-ui,-apple-system,sans-serif" font-weight="500" letter-spacing="3.5">DATA INSIGHTS</text>'
            '</svg></div>',
            unsafe_allow_html=True,
        )

        # 导航菜单 — 水平平铺按钮
        pages = [
            ("图表\n分析", "charts"),
            ("技术\n指标", "indicators"),
        ]
        cols = st.columns(len(pages))
        for i, (label, key) in enumerate(pages):
            with cols[i]:
                is_active = st.session_state.current_page == key
                btn_type = "primary" if is_active else "secondary"
                if st.button(label, key=f"nav_{key}", width='stretch', type=btn_type):
                    st.session_state.current_page = key
                    st.rerun()

    # 主内容区域
    if st.session_state.current_page == "charts":
        chart_component()
    elif st.session_state.current_page == "indicators":
        indicator_component()
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
    log_dir = Path(settings.logging.file_path).parent
    for directory in [log_dir]:
        directory.mkdir(parents=True, exist_ok=True)

if __name__ == "__main__":
    # 初始化应用
    initialize_app()

    # 运行主应用
    try:
        main()
    except Exception as e:
        st.error(f"应用运行错误: {e}")
        st.exception(e)
