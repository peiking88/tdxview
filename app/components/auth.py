"""
用户认证组件
"""

import streamlit as st
import hashlib
import time
from typing import Optional, Tuple
import duckdb
from pathlib import Path

from app.config.settings import get_settings


def login_component():
    """登录组件"""
    settings = get_settings()
    
    if not settings.security.authentication_enabled:
        st.info("认证功能已禁用")
        st.session_state.authenticated = True
        st.session_state.username = "guest"
        st.session_state.user_id = 0
        return
    
    with st.form("login_form"):
        username = st.text_input("用户名", placeholder="输入用户名")
        password = st.text_input("密码", type="password", placeholder="输入密码")
        remember_me = st.checkbox("记住我")
        
        col1, col2 = st.columns([1, 1])
        with col1:
            login_button = st.form_submit_button("登录", use_container_width=True)
        with col2:
            register_button = st.form_submit_button("注册", use_container_width=True)
    
    if login_button:
        if authenticate_user(username, password):
            st.success("登录成功!")
            st.session_state.authenticated = True
            st.session_state.username = username
            st.session_state.user_id = get_user_id(username)
            st.rerun()
        else:
            st.error("用户名或密码错误")
    
    if register_button:
        st.info("注册功能开发中...")


def authenticate_user(username: str, password: str) -> bool:
    """验证用户"""
    if not username or not password:
        return False
    
    settings = get_settings()
    db_path = Path(settings.database.duckdb_path)
    
    if not db_path.exists():
        # 开发模式下的默认用户
        return username == "admin" and password == "admin123"
    
    try:
        conn = duckdb.connect(str(db_path))
        
        # 查询用户
        result = conn.execute(
            "SELECT password_hash FROM users WHERE username = ? AND is_active = TRUE",
            [username]
        ).fetchone()
        
        conn.close()
        
        if not result:
            return False
        
        # 简单密码验证（生产环境应使用bcrypt）
        password_hash = result[0]
        
        # 临时简单验证（生产环境需要改进）
        expected_hash = hashlib.sha256(password.encode()).hexdigest()
        return password_hash == expected_hash
        
    except Exception as e:
        st.error(f"认证错误: {e}")
        return False


def get_user_id(username: str) -> Optional[int]:
    """获取用户ID"""
    settings = get_settings()
    db_path = Path(settings.database.duckdb_path)
    
    if not db_path.exists():
        return 1 if username == "admin" else None
    
    try:
        conn = duckdb.connect(str(db_path))
        result = conn.execute(
            "SELECT id FROM users WHERE username = ?",
            [username]
        ).fetchone()
        conn.close()
        
        return result[0] if result else None
    except Exception:
        return None


def logout_user():
    """用户登出"""
    st.session_state.authenticated = False
    st.session_state.username = None
    st.session_state.user_id = None
    st.session_state.current_page = "dashboard"


def get_current_user() -> Tuple[Optional[int], Optional[str]]:
    """获取当前用户"""
    return (
        st.session_state.get("user_id"),
        st.session_state.get("username")
    )


def check_permission(resource_type: str, resource_id: str, action: str) -> bool:
    """检查权限"""
    user_id, username = get_current_user()
    
    if not user_id:
        return False
    
    settings = get_settings()
    if not settings.security.authorization_enabled:
        return True
    
    # 简单权限检查（生产环境需要更复杂的RBAC）
    db_path = Path(settings.database.duckdb_path)
    
    try:
        conn = duckdb.connect(str(db_path))
        
        # 查询用户角色
        result = conn.execute(
            "SELECT role FROM users WHERE id = ?",
            [user_id]
        ).fetchone()
        
        conn.close()
        
        if not result:
            return False
        
        role = result[0]
        
        # 简单权限规则
        if role == "admin":
            return True
        elif role == "user":
            # 用户只能访问自己的资源
            if resource_type in ["dashboard", "chart"]:
                # 这里需要检查资源所有权
                return True
            else:
                return action in ["read", "view"]
        
        return False
        
    except Exception:
        return False


def update_last_login(user_id: int):
    """更新最后登录时间"""
    settings = get_settings()
    db_path = Path(settings.database.duckdb_path)
    
    if not db_path.exists():
        return
    
    try:
        conn = duckdb.connect(str(db_path))
        conn.execute(
            "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?",
            [user_id]
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


if __name__ == "__main__":
    # 测试代码
    st.title("认证组件测试")
    
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    
    if st.session_state.authenticated:
        st.success(f"已登录为: {st.session_state.get('username')}")
        if st.button("退出"):
            logout_user()
            st.rerun()
    else:
        login_component()