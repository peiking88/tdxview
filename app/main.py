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
from app.components.auth import login_component
from app.components.dashboard import dashboard_component
from app.components.charts import chart_component
from app.components.indicators import indicator_component
from app.components.config import config_component
from app.components.data_management import data_management_component

# 页面配置
st.set_page_config(
    page_title="tdxview - 数据可视化平台",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "Get Help": "https://github.com/tdxview/tdxview",
        "Report a bug": "https://github.com/tdxview/tdxview/issues",
        "About": """
        ## tdxview 数据可视化平台
        
        基于tdxdata的实时监控、历史数据分析和技术指标计算平台。
        
        版本: 1.0.0
        作者: tdxview团队
        """
    }
)

# 应用设置
settings = get_settings()

def main():
    """主应用函数"""
    
    # 初始化会话状态
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "user_id" not in st.session_state:
        st.session_state.user_id = None
    if "username" not in st.session_state:
        st.session_state.username = None
    if "current_page" not in st.session_state:
        st.session_state.current_page = "dashboard"
    
    # 应用标题
    st.title("📊 tdxview 数据可视化平台")
    st.markdown("---")
    
    # 侧边栏导航
    with st.sidebar:
        st.markdown(
            '<div style="text-align:center;padding:10px 0;">'
            '<svg width="150" height="50" viewBox="0 0 150 50" xmlns="http://www.w3.org/2000/svg">'
            '<rect width="150" height="50" rx="8" fill="#1f77b4"/>'
            '<text x="75" y="32" text-anchor="middle" fill="white" font-size="20" font-family="sans-serif" font-weight="bold">tdxview</text>'
            '</svg></div>',
            unsafe_allow_html=True,
        )
        st.caption("数据驱动决策")
        
        # 用户认证状态
        if st.session_state.authenticated:
            st.success(f"欢迎, {st.session_state.username}!")
            
            # 导航菜单
            st.markdown("### 导航")
            page = st.radio(
                "选择页面",
                ["仪表板", "图表分析", "技术指标", "数据管理", "系统配置"],
                index=["仪表板", "图表分析", "技术指标", "数据管理", "系统配置"]
                .index(st.session_state.current_page.replace("_", ""))
                if st.session_state.current_page.replace("_", "") in 
                ["仪表板", "图表分析", "技术指标", "数据管理", "系统配置"] else 0,
                label_visibility="collapsed"
            )
            
            # 更新当前页面
            page_mapping = {
                "仪表板": "dashboard",
                "图表分析": "charts",
                "技术指标": "indicators",
                "数据管理": "data_management",
                "系统配置": "config"
            }
            st.session_state.current_page = page_mapping.get(page, "dashboard")
            
            # 用户操作
            st.markdown("---")
            st.markdown("### 用户操作")
            if st.button("🚪 退出登录", use_container_width=True):
                st.session_state.authenticated = False
                st.session_state.user_id = None
                st.session_state.username = None
                st.session_state.current_page = "dashboard"
                st.rerun()
                
        else:
            # 登录表单
            st.markdown("### 用户登录")
            login_component()
    
    # 主内容区域
    if st.session_state.authenticated:
        # 根据当前页面显示相应内容
        if st.session_state.current_page == "dashboard":
            dashboard_component()
        elif st.session_state.current_page == "charts":
            chart_component()
        elif st.session_state.current_page == "indicators":
            indicator_component()
        elif st.session_state.current_page == "data_management":
            data_management_component()
        elif st.session_state.current_page == "config":
            config_component()
        else:
            dashboard_component()
    else:
        # 未登录时的欢迎页面
        col1, col2, col3 = st.columns([1, 2, 1])
        
        with col2:
            st.markdown("""
            ## 欢迎使用 tdxview
            
            tdxview是一个基于tdxdata的数据可视化平台，提供以下功能：
            
            ### 📈 实时监控
            - 实时数据监控和警报
            - 关键指标仪表板
            - 多数据源支持
            
            ### 📊 历史数据分析
            - 时间序列分析
            - 趋势识别和模式发现
            - 多时间框架支持
            
            ### 🔢 技术指标计算
            - 内置常用技术指标（MA、RSI、MACD、布林带等）
            - 自定义指标支持（Python脚本）
            - 参数调整和优化
            
            ### 🎨 交互式可视化
            - K线图、折线图、柱状图、热力图
            - 实时数据更新
            - 图表导出和分享
            
            ### 👤 用户管理
            - 多用户支持
            - 个人配置保存
            - 权限控制
            
            ### ⚡ 高性能
            - 快速查询和计算
            - 多级缓存机制
            - 并行处理支持
            """)
            
            st.markdown("---")
            st.info("请使用侧边栏登录以开始使用系统")
    
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
        except Exception:
            needs_init = True

    if needs_init:
        try:
            from scripts.init_database import init_database
            init_database()
        except Exception as e:
            st.error(f"数据库初始化失败: {e}")
    
    # 检查数据源配置
    if not settings.tdxdata.api_key:
        st.warning("未配置tdxdata API密钥，部分功能可能受限")

if __name__ == "__main__":
    # 初始化应用
    initialize_app()
    
    # 运行主应用
    try:
        main()
    except Exception as e:
        st.error(f"应用运行错误: {e}")
        st.exception(e)