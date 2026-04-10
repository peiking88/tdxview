"""
集成测试共享fixture
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Temporary directories
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def tmp_base():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture(scope="session")
def tmp_db_path(tmp_base):
    return str(tmp_base / "test_tdxview.db")


@pytest.fixture(scope="session")
def tmp_parquet_dir(tmp_base):
    p = tmp_base / "parquet"
    p.mkdir(exist_ok=True)
    return str(p)


@pytest.fixture(scope="session")
def tmp_cache_dir(tmp_base):
    p = tmp_base / "cache"
    p.mkdir(exist_ok=True)
    return str(p)


# ---------------------------------------------------------------------------
# Patched settings so every service uses temp paths
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def _patched_settings(tmp_db_path, tmp_parquet_dir, tmp_cache_dir):
    """Override get_settings for the whole integration session by directly patching."""
    import sys
    import importlib
    
    # 直接修改设置对象
    from app.config.settings import get_settings
    settings = get_settings()
    
    # 直接修改设置对象的属性
    settings.database.duckdb_path = tmp_db_path
    settings.database.parquet_dir = tmp_parquet_dir
    settings.database.cache_dir = tmp_cache_dir
    settings.security.password_min_length = 4
    settings.security.password_require_special = False
    
    # 强制重新导入可能已经缓存了设置的模块
    modules_to_reload = [
        'app.data.database',
        'app.services.data_service',
        'app.services.user_service',
        'app.services.indicator_service'
    ]
    
    for module_name in modules_to_reload:
        if module_name in sys.modules:
            importlib.reload(sys.modules[module_name])
    
    return settings


@pytest.fixture(scope="function", autouse=True)
def _mock_bcrypt():
    """Mock bcrypt functions for faster and more predictable tests."""
    import unittest.mock as mock
    import bcrypt
    import base64
    
    # 存储密码哈希映射
    password_hash_map = {}
    
    def simple_hash(password_bytes, salt):
        # 创建一个简单的"哈希"：密码的base64编码
        # 存储映射
        password_str = password_bytes.decode('utf-8')
        fake_hash = base64.b64encode(f"mock_hash_{password_str}".encode()).decode()
        password_hash_map[password_str] = fake_hash.encode()
        return fake_hash.encode()
    
    def simple_checkpw(password_bytes, hashed_bytes):
        # 检查密码是否匹配存储的哈希
        password_str = password_bytes.decode('utf-8')
        fake_hash = base64.b64encode(f"mock_hash_{password_str}".encode()).decode()
        return hashed_bytes == fake_hash.encode()
    
    # Mock bcrypt函数
    with mock.patch.object(bcrypt, 'hashpw', side_effect=simple_hash):
        with mock.patch.object(bcrypt, 'checkpw', side_effect=simple_checkpw):
            # 也需要mock gensalt
            with mock.patch.object(bcrypt, 'gensalt', return_value=b"$2b$12$mocksaltmocksaltmocksa"):
                yield


# ---------------------------------------------------------------------------
# Database init — create users table once
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def _init_db(_patched_settings, tmp_db_path):
    from app.data.database import DatabaseManager
    import json

    db = DatabaseManager(db_path=tmp_db_path)
    
    # 创建用户表
    db.execute("CREATE SEQUENCE IF NOT EXISTS users_id_seq START 1")
    db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id        INTEGER PRIMARY KEY DEFAULT nextval('users_id_seq'),
            username  TEXT UNIQUE NOT NULL,
            email     TEXT UNIQUE,
            password_hash TEXT NOT NULL,
            role      TEXT NOT NULL DEFAULT 'user',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP,
            preferences TEXT DEFAULT '{}'
        )
    """)
    
    # 创建数据源表
    db.execute("CREATE SEQUENCE IF NOT EXISTS data_sources_id_seq START 1")
    db.execute("""
        CREATE TABLE IF NOT EXISTS data_sources (
            id        INTEGER PRIMARY KEY DEFAULT nextval('data_sources_id_seq'),
            name      TEXT NOT NULL,
            type      TEXT NOT NULL,
            config    TEXT NOT NULL,
            enabled   BOOLEAN DEFAULT TRUE,
            priority  INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 插入一个测试数据源
    default_config = json.dumps({
        "api_url": "https://api.tdxdata.com",
        "api_key": "test_key",
        "timeout": 30,
        "retry_count": 3
    })
    db.execute("""
        INSERT OR IGNORE INTO data_sources (name, type, config, enabled, priority)
        VALUES ('tdxdata_test', 'tdxdata', ?, TRUE, 1)
    """, [default_config])
    
    db.connection.commit()
    yield db


# ---------------------------------------------------------------------------
# Mock TdxDataSource
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def mock_source():
    src = MagicMock()

    src.fetch_history.return_value = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=31, freq="D"),
        "open": np.random.uniform(100, 200, 31),
        "high": np.random.uniform(110, 220, 31),
        "low":  np.random.uniform(90, 180, 31),
        "close": np.random.uniform(105, 210, 31),
        "volume": np.random.randint(100_000, 1_000_000, 31),
        "symbol": ["AAPL"] * 31,
    })

    src.fetch_realtime.return_value = pd.DataFrame({
        "symbol":  ["AAPL", "GOOGL"],
        "price":   [150.25, 2750.50],
        "change":  [1.25, -5.75],
        "change_percent": [0.84, -0.21],
        "volume":  [1_500_000, 750_000],
    })

    return src


# ---------------------------------------------------------------------------
# DataService with mocked source
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def data_service(_patched_settings, mock_source):
    with patch("app.services.data_service.TdxDataSource", return_value=mock_source):
        from app.services.data_service import DataService
        svc = DataService()
        yield svc


# ---------------------------------------------------------------------------
# user_service module (functions, not a class)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def us():
    from app.services import user_service
    return user_service


# ---------------------------------------------------------------------------
# IndicatorService
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def indicator_service(_patched_settings):
    from app.services.indicator_service import IndicatorService
    return IndicatorService()


# ---------------------------------------------------------------------------
# Sample data helpers
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def sample_stock_df():
    dates = pd.date_range("2024-01-01", "2024-01-31", freq="D")
    n = len(dates)
    return pd.DataFrame({
        "date": dates,
        "open":   np.random.uniform(100, 200, n),
        "high":   np.random.uniform(110, 220, n),
        "low":    np.random.uniform(90, 180, n),
        "close":  np.random.uniform(105, 210, n),
        "volume": np.random.randint(100_000, 1_000_000, n),
        "symbol": ["AAPL"] * n,
    })


@pytest.fixture()
def clean_db(tmp_db_path):
    """Truncate all user tables before each test."""
    from app.data.database import DatabaseManager
    db = DatabaseManager(db_path=tmp_db_path)
    for t in ("users",):
        db.execute(f"DELETE FROM {t}")
    db.connection.commit()
    yield
