"""
Unit tests for user_service — password hashing, JWT, user CRUD,
preferences, config import/export, and permission checks.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------
from app.services.user_service import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
    register_user,
    authenticate_user,
    get_user_by_username,
    get_user_by_id,
    get_user_preferences,
    set_user_preferences,
    update_user_preferences,
    export_user_config,
    import_user_config,
    check_permission,
    set_default_view,
    get_default_view,
    list_users,
    update_user_role,
    deactivate_user,
)


class TestPasswordHashing:
    def test_hash_and_verify_success(self):
        hashed = hash_password("secret123")
        assert hashed != "secret123"
        assert verify_password("secret123", hashed) is True

    def test_verify_wrong_password(self):
        hashed = hash_password("secret123")
        assert verify_password("wrong", hashed) is False

    def test_different_hashes_for_same_password(self):
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2  # bcrypt uses random salt
        assert verify_password("same", h1)
        assert verify_password("same", h2)


class TestJWT:
    def test_create_and_decode(self):
        token = create_access_token({"sub": "admin", "uid": 1, "role": "admin"})
        payload = decode_access_token(token)
        assert payload is not None
        assert payload["sub"] == "admin"
        assert payload["uid"] == 1
        assert payload["role"] == "admin"

    def test_decode_invalid_token(self):
        assert decode_access_token("invalid.token.here") is None

    def test_expired_token(self):
        from datetime import timedelta
        token = create_access_token({"sub": "admin"}, expires_delta=timedelta(seconds=-1))
        assert decode_access_token(token) is None


# ---------------------------------------------------------------------------
# User CRUD — requires a temporary DuckDB database
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_db(tmp_dir, test_settings):
    """Create a temporary database and init the schema."""
    db_path = str(tmp_dir / "test.db")

    import duckdb

    conn = duckdb.connect(db_path)
    conn.execute("CREATE SEQUENCE IF NOT EXISTS users_id_seq START 1")
    conn.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY DEFAULT nextval('users_id_seq'),
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE,
        password_hash TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_login TIMESTAMP,
        preferences JSON,
        is_active BOOLEAN DEFAULT TRUE,
        role TEXT DEFAULT 'user'
    )
    """)
    conn.execute("CREATE SEQUENCE IF NOT EXISTS dashboards_id_seq START 1")
    conn.execute("""
    CREATE TABLE IF NOT EXISTS dashboards (
        id INTEGER PRIMARY KEY DEFAULT nextval('dashboards_id_seq'),
        user_id INTEGER REFERENCES users(id),
        name TEXT NOT NULL,
        description TEXT,
        layout JSON NOT NULL,
        widgets JSON NOT NULL,
        is_public BOOLEAN DEFAULT FALSE,
        is_default BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    conn.commit()
    conn.close()

    original = test_settings.database.duckdb_path
    test_settings.database.duckdb_path = db_path
    yield db_path
    test_settings.database.duckdb_path = original


class TestRegisterUser:
    def test_register_success(self, tmp_db):
        ok, msg = register_user("testuser", "Pass!123", "test@example.com")
        assert ok is True
        user = get_user_by_username("testuser")
        assert user is not None
        assert user["username"] == "testuser"
        assert user["role"] == "user"

    def test_register_duplicate_username(self, tmp_db):
        register_user("dup", "Pass!123")
        ok, msg = register_user("dup", "Pass!456")
        assert ok is False
        assert "already exists" in msg

    def test_register_short_password(self, tmp_db):
        ok, msg = register_user("shortpw", "A!1")
        assert ok is False
        assert "at least" in msg.lower() or "Password" in msg

    def test_register_no_special_char(self, tmp_db):
        ok, msg = register_user("nospecial", "abcdefgh1")
        assert ok is False
        assert "special" in msg.lower()

    def test_register_short_username(self, tmp_db):
        ok, msg = register_user("ab", "Pass!123")
        assert ok is False
        assert "3" in msg

    def test_register_duplicate_email(self, tmp_db):
        register_user("user1", "Pass!123", email="same@example.com")
        ok, msg = register_user("user2", "Pass!456", email="same@example.com")
        assert ok is False
        assert "email" in msg.lower()


class TestAuthenticateUser:
    def test_authenticate_success(self, tmp_db):
        register_user("loginuser", "Pass!123")
        user = authenticate_user("loginuser", "Pass!123")
        assert user is not None
        assert user["username"] == "loginuser"
        assert "id" in user

    def test_authenticate_wrong_password(self, tmp_db):
        register_user("loginuser2", "Pass!123")
        user = authenticate_user("loginuser2", "wrong")
        assert user is None

    def test_authenticate_nonexistent_user(self, tmp_db):
        user = authenticate_user("ghost", "Pass!123")
        assert user is None

    def test_authenticate_empty_credentials(self, tmp_db):
        assert authenticate_user("", "Pass!123") is None
        assert authenticate_user("admin", "") is None

    def test_authenticate_deactivated_user(self, tmp_db):
        register_user("deact", "Pass!123")
        user = get_user_by_username("deact")
        deactivate_user(user["id"])
        result = authenticate_user("deact", "Pass!123")
        assert result is None


class TestUserQueries:
    def test_get_user_by_id(self, tmp_db):
        register_user("byid", "Pass!123")
        user_by_name = get_user_by_username("byid")
        user_by_id = get_user_by_id(user_by_name["id"])
        assert user_by_id is not None
        assert user_by_id["username"] == "byid"

    def test_get_user_nonexistent(self, tmp_db):
        assert get_user_by_id(9999) is None
        assert get_user_by_username("nobody") is None

    def test_list_users(self, tmp_db):
        register_user("user1", "Pass!123")
        register_user("user2", "Pass!456")
        users = list_users()
        assert len(users) >= 2

    def test_update_user_role(self, tmp_db):
        register_user("roleuser", "Pass!123")
        user = get_user_by_username("roleuser")
        update_user_role(user["id"], "admin")
        updated = get_user_by_id(user["id"])
        assert updated["role"] == "admin"

    def test_deactivate_user(self, tmp_db):
        register_user("todeact", "Pass!123")
        user = get_user_by_username("todeact")
        deactivate_user(user["id"])
        updated = get_user_by_id(user["id"])
        assert updated["is_active"] is False


class TestPermissions:
    def test_admin_has_all_permissions(self, tmp_db):
        register_user("adm", "Pass!123", role="admin")
        user = get_user_by_username("adm")
        assert check_permission(user["id"], "dashboard", "delete") is True
        assert check_permission(user["id"], "data", "update") is True

    def test_user_read_permissions(self, tmp_db):
        register_user("normal", "Pass!123")
        user = get_user_by_username("normal")
        assert check_permission(user["id"], "dashboard", "read") is True
        assert check_permission(user["id"], "dashboard", "create") is True
        assert check_permission(user["id"], "data", "delete") is False

    def test_no_user_no_permission(self, tmp_db):
        assert check_permission(9999, "dashboard", "read") is False


class TestPreferences:
    def test_get_default_preferences(self, tmp_db):
        register_user("prefs", "Pass!123")
        user = get_user_by_username("prefs")
        prefs = get_user_preferences(user["id"])
        assert isinstance(prefs, dict)

    def test_set_and_get_preferences(self, tmp_db):
        register_user("setpref", "Pass!123")
        user = get_user_by_username("setpref")
        set_user_preferences(user["id"], {"theme": "dark", "lang": "zh"})
        prefs = get_user_preferences(user["id"])
        assert prefs["theme"] == "dark"
        assert prefs["lang"] == "zh"

    def test_update_preferences_merge(self, tmp_db):
        register_user("mergepref", "Pass!123")
        user = get_user_by_username("mergepref")
        set_user_preferences(user["id"], {"theme": "light"})
        update_user_preferences(user["id"], {"lang": "en"})
        prefs = get_user_preferences(user["id"])
        assert prefs["theme"] == "light"
        assert prefs["lang"] == "en"


class TestDefaultView:
    def test_set_and_get_default_view(self, tmp_db):
        register_user("viewuser", "Pass!123")
        user = get_user_by_username("viewuser")
        set_default_view(user["id"], "charts")
        assert get_default_view(user["id"]) == "charts"

    def test_default_view_fallback(self, tmp_db):
        register_user("noview", "Pass!123")
        user = get_user_by_username("noview")
        assert get_default_view(user["id"]) == "dashboard"


class TestConfigImportExport:
    def test_export_user_config(self, tmp_db):
        register_user("exporter", "Pass!123", email="exp@test.com")
        user = get_user_by_username("exporter")
        set_user_preferences(user["id"], {"theme": "dark"})
        config = export_user_config(user["id"])
        assert config is not None
        assert config["username"] == "exporter"
        assert config["email"] == "exp@test.com"
        assert config["preferences"]["theme"] == "dark"
        assert "exported_at" in config

    def test_import_user_config(self, tmp_db):
        register_user("importer", "Pass!123")
        user = get_user_by_username("importer")

        config = {
            "preferences": {"theme": "light", "lang": "en"},
            "dashboards": [
                {
                    "name": "Test Dashboard",
                    "description": "imported",
                    "layout": {"type": "grid"},
                    "widgets": [{"id": "w1", "type": "candlestick"}],
                    "is_default": True,
                }
            ],
        }
        ok, msg = import_user_config(user["id"], config)
        assert ok is True

        prefs = get_user_preferences(user["id"])
        assert prefs["theme"] == "light"
        assert prefs["lang"] == "en"

    def test_export_nonexistent_user(self, tmp_db):
        assert export_user_config(9999) is None

    def test_roundtrip_export_import(self, tmp_db):
        register_user("roundtrip", "Pass!123")
        user = get_user_by_username("roundtrip")
        update_user_preferences(user["id"], {"theme": "dark"})
        set_default_view(user["id"], "indicators")

        config = export_user_config(user["id"])
        # Simulate importing into a fresh user
        register_user("roundtrip2", "Pass!456")
        user2 = get_user_by_username("roundtrip2")
        ok, _ = import_user_config(user2["id"], config)
        assert ok is True
        prefs2 = get_user_preferences(user2["id"])
        assert prefs2["theme"] == "dark"
        assert prefs2.get("default_page") == "indicators"
