"""
User service — authentication, JWT, user CRUD, and configuration management.

All business logic related to users lives here. The Streamlit auth component
should only call this service, never touch the database directly.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config.settings import get_settings
from app.data.database import DatabaseManager

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    return _pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    return _pwd_context.verify(plain, hashed)


# ---------------------------------------------------------------------------
# JWT tokens
# ---------------------------------------------------------------------------

_ALGORITHM = "HS256"


def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a signed JWT access token."""
    settings = get_settings()
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(seconds=settings.security.session_timeout)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.security.secret_key, algorithm=_ALGORITHM)


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode and validate a JWT access token. Returns None on failure."""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.security.secret_key, algorithms=[_ALGORITHM])
        return payload
    except JWTError:
        return None


# ---------------------------------------------------------------------------
# User CRUD
# ---------------------------------------------------------------------------

def register_user(
    username: str,
    password: str,
    email: Optional[str] = None,
    role: str = "user",
) -> Tuple[bool, str]:
    """Register a new user.

    Returns (success, message).
    """
    settings = get_settings()

    # Validate password strength
    if len(password) < settings.security.password_min_length:
        return False, f"Password must be at least {settings.security.password_min_length} characters"
    if settings.security.password_require_special:
        special = set("!@#$%^&*()-_=+[]{}|;:',.<>?/`~")
        if not any(c in special for c in password):
            return False, "Password must contain at least one special character"

    if not username or len(username) < 3:
        return False, "Username must be at least 3 characters"

    db = DatabaseManager()
    try:
        # Check uniqueness
        existing = db.fetch_one("SELECT id FROM users WHERE username = ?", [username])
        if existing:
            return False, "Username already exists"
        if email:
            existing_email = db.fetch_one("SELECT id FROM users WHERE email = ?", [email])
            if existing_email:
                return False, "Email already registered"

        password_hash = hash_password(password)
        db.execute(
            "INSERT INTO users (username, email, password_hash, role, is_active, preferences) VALUES (?, ?, ?, ?, TRUE, '{}')",
            [username, email, password_hash, role],
        )
        db.connection.commit()
        return True, "Registration successful"
    except Exception as e:
        return False, f"Registration failed: {e}"


def authenticate_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    """Authenticate a user by username and password.

    Returns user dict on success, None on failure.
    """
    if not username or not password:
        return None

    db = DatabaseManager()
    try:
        row = db.fetch_one(
            "SELECT id, username, email, password_hash, role, is_active FROM users WHERE username = ?",
            [username],
        )
        if not row:
            return None

        user_id, uname, uemail, pw_hash, urole, is_active = row
        if not is_active:
            return None

        if not verify_password(password, pw_hash):
            return None

        # Update last login
        db.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?", [user_id])
        db.connection.commit()

        return {
            "id": user_id,
            "username": uname,
            "email": uemail,
            "role": urole,
        }
    except Exception:
        return None


def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    """Fetch a user by ID."""
    db = DatabaseManager()
    row = db.fetch_one(
        "SELECT id, username, email, role, is_active, preferences FROM users WHERE id = ?",
        [user_id],
    )
    if not row:
        return None
    return {
        "id": row[0],
        "username": row[1],
        "email": row[2],
        "role": row[3],
        "is_active": row[4],
        "preferences": json.loads(row[5]) if row[5] else {},
    }


def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    """Fetch a user by username."""
    db = DatabaseManager()
    row = db.fetch_one(
        "SELECT id, username, email, role, is_active, preferences FROM users WHERE username = ?",
        [username],
    )
    if not row:
        return None
    return {
        "id": row[0],
        "username": row[1],
        "email": row[2],
        "role": row[3],
        "is_active": row[4],
        "preferences": json.loads(row[5]) if row[5] else {},
    }


def list_users() -> List[Dict[str, Any]]:
    """List all users (admin utility)."""
    db = DatabaseManager()
    rows = db.fetch_all("SELECT id, username, email, role, is_active FROM users ORDER BY id")
    return [
        {"id": r[0], "username": r[1], "email": r[2], "role": r[3], "is_active": r[4]}
        for r in rows
    ]


def update_user_role(user_id: int, role: str) -> bool:
    """Update a user's role."""
    db = DatabaseManager()
    db.execute("UPDATE users SET role = ? WHERE id = ?", [role, user_id])
    db.connection.commit()
    return True


def deactivate_user(user_id: int) -> bool:
    """Deactivate a user account."""
    db = DatabaseManager()
    db.execute("UPDATE users SET is_active = FALSE WHERE id = ?", [user_id])
    db.connection.commit()
    return True


# ---------------------------------------------------------------------------
# Permission checks
# ---------------------------------------------------------------------------

def check_permission(user_id: int, resource_type: str, action: str) -> bool:
    """Check whether a user has permission for the given action."""
    settings = get_settings()
    if not settings.security.authorization_enabled:
        return True

    user = get_user_by_id(user_id)
    if not user:
        return False

    role = user["role"]
    if role == "admin":
        return True
    elif role == "user":
        if resource_type in ("dashboard", "chart", "indicator"):
            return action in ("read", "view", "create", "update")
        return action in ("read", "view")
    return False


# ---------------------------------------------------------------------------
# User configuration
# ---------------------------------------------------------------------------

def get_user_preferences(user_id: int) -> Dict[str, Any]:
    """Get a user's preferences JSON."""
    user = get_user_by_id(user_id)
    if user:
        return user.get("preferences", {})
    return {}


def set_user_preferences(user_id: int, preferences: Dict[str, Any]) -> bool:
    """Overwrite a user's preferences JSON."""
    db = DatabaseManager()
    db.execute(
        "UPDATE users SET preferences = ? WHERE id = ?",
        [json.dumps(preferences, ensure_ascii=False), user_id],
    )
    db.connection.commit()
    return True


def update_user_preferences(user_id: int, updates: Dict[str, Any]) -> Dict[str, Any]:
    """Merge *updates* into the existing preferences and return the result."""
    current = get_user_preferences(user_id)
    current.update(updates)
    set_user_preferences(user_id, current)
    return current


def export_user_config(user_id: int) -> Optional[Dict[str, Any]]:
    """Export all user configuration as a portable dict."""
    user = get_user_by_id(user_id)
    if not user:
        return None

    db = DatabaseManager()

    # Dashboards
    dash_rows = db.fetch_all(
        "SELECT name, description, layout, widgets, is_default FROM dashboards WHERE user_id = ?",
        [user_id],
    )
    dashboards = [
        {
            "name": r[0],
            "description": r[1],
            "layout": json.loads(r[2]) if isinstance(r[2], str) else r[2],
            "widgets": json.loads(r[3]) if isinstance(r[3], str) else r[3],
            "is_default": r[4],
        }
        for r in dash_rows
    ]

    return {
        "username": user["username"],
        "email": user["email"],
        "preferences": user.get("preferences", {}),
        "dashboards": dashboards,
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }


def import_user_config(user_id: int, config: Dict[str, Any]) -> Tuple[bool, str]:
    """Import user configuration from a portable dict."""
    db = DatabaseManager()
    try:
        # Restore preferences
        if "preferences" in config:
            set_user_preferences(user_id, config["preferences"])

        # Restore dashboards
        for dash in config.get("dashboards", []):
            db.execute(
                "INSERT INTO dashboards (user_id, name, description, layout, widgets, is_default) VALUES (?, ?, ?, ?, ?, ?)",
                [
                    user_id,
                    dash["name"],
                    dash.get("description", ""),
                    json.dumps(dash.get("layout", {})),
                    json.dumps(dash.get("widgets", [])),
                    dash.get("is_default", False),
                ],
            )
        db.connection.commit()
        return True, "Configuration imported successfully"
    except Exception as e:
        return False, f"Import failed: {e}"


# ---------------------------------------------------------------------------
# Default view
# ---------------------------------------------------------------------------

def set_default_view(user_id: int, page: str) -> bool:
    """Save the user's default landing page."""
    update_user_preferences(user_id, {"default_page": page})
    return True


def get_default_view(user_id: int) -> str:
    """Get the user's default landing page (defaults to 'dashboard')."""
    prefs = get_user_preferences(user_id)
    return prefs.get("default_page", "dashboard")
