"""
用户认证组件 — Streamlit UI layer only.

All business logic is delegated to app.services.user_service.
"""

import streamlit as st
from typing import Optional, Tuple

from app.config.settings import get_settings
from app.services import user_service


def login_component():
    """Render login / register form in the sidebar."""
    settings = get_settings()

    if not settings.security.authentication_enabled:
        st.info("认证功能已禁用")
        st.session_state.authenticated = True
        st.session_state.username = "guest"
        st.session_state.user_id = 0
        return

    tab_login, tab_register = st.tabs(["登录", "注册"])

    # ---- Login tab ----
    with tab_login:
        with st.form("login_form"):
            username = st.text_input("用户名", placeholder="输入用户名")
            password = st.text_input("密码", type="password", placeholder="输入密码")
            login_button = st.form_submit_button("登录", use_container_width=True)

        if login_button:
            user = user_service.authenticate_user(username, password)
            if user:
                # Generate JWT token
                token = user_service.create_access_token(
                    {"sub": user["username"], "uid": user["id"], "role": user["role"]}
                )
                st.session_state.authenticated = True
                st.session_state.username = user["username"]
                st.session_state.user_id = user["id"]
                st.session_state.role = user["role"]
                st.session_state.jwt_token = token
                st.success("登录成功!")
                st.rerun()
            else:
                st.error("用户名或密码错误")

    # ---- Register tab ----
    with tab_register:
        with st.form("register_form"):
            new_username = st.text_input("用户名", placeholder="至少3个字符", key="reg_user")
            new_email = st.text_input("邮箱 (可选)", placeholder="your@email.com", key="reg_email")
            new_password = st.text_input("密码", type="password", placeholder="至少8位，含特殊字符", key="reg_pw")
            new_password2 = st.text_input("确认密码", type="password", key="reg_pw2")
            register_button = st.form_submit_button("注册", use_container_width=True)

        if register_button:
            if new_password != new_password2:
                st.error("两次输入的密码不一致")
            else:
                ok, msg = user_service.register_user(
                    username=new_username,
                    password=new_password,
                    email=new_email or None,
                )
                if ok:
                    st.success(msg + " 请登录。")
                else:
                    st.error(msg)


def authenticate_user(username: str, password: str) -> bool:
    """Backward-compatible wrapper — returns bool."""
    user = user_service.authenticate_user(username, password)
    return user is not None


def get_user_id(username: str) -> Optional[int]:
    """Get user ID by username."""
    user = user_service.get_user_by_username(username)
    return user["id"] if user else None


def logout_user():
    """Clear session state on logout."""
    for key in ("authenticated", "username", "user_id", "role", "jwt_token", "current_page"):
        st.session_state.pop(key, None)
    st.session_state.current_page = "dashboard"


def get_current_user() -> Tuple[Optional[int], Optional[str]]:
    """Return (user_id, username) from session state."""
    return (
        st.session_state.get("user_id"),
        st.session_state.get("username"),
    )


def check_permission(resource_type: str, resource_id: str, action: str) -> bool:
    """Check whether the current session user has permission."""
    user_id = st.session_state.get("user_id")
    if not user_id:
        return False
    return user_service.check_permission(user_id, resource_type, action)


def update_last_login(user_id: int):
    """No-op — last_login is now updated inside user_service.authenticate_user()."""
    pass
