"""
集成测试共享fixture

原则：真实环境优先于 mock
- DuckDB / Parquet / Cache 使用真实临时实例
- 通达信服务器可用时使用真实连接，不可用时自动降级为 mock
- get_settings 已由 tests/conftest.py autouse patch 统一管理
- 使用方式：
    pytest                     # 自动检测服务器
    TDX_LIVE=0 pytest          # 强制 mock
    TDX_LIVE=1 pytest          # 强制真实连接
"""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(scope="session")
def tmp_base():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture(scope="session")
def tmp_db_path(tmp_base, test_settings):
    db_path = str(tmp_base / "test_tdxview.db")
    original = test_settings.database.duckdb_path
    test_settings.database.duckdb_path = db_path
    yield db_path
    test_settings.database.duckdb_path = original


@pytest.fixture(scope="session")
def tmp_parquet_dir(tmp_base, test_settings):
    p = tmp_base / "parquet"
    p.mkdir(exist_ok=True)
    original = test_settings.database.parquet_dir
    test_settings.database.parquet_dir = str(p)
    yield str(p)
    test_settings.database.parquet_dir = original


@pytest.fixture(scope="session")
def tmp_cache_dir(tmp_base, test_settings):
    p = tmp_base / "cache"
    p.mkdir(exist_ok=True)
    original = test_settings.database.cache_dir
    test_settings.database.cache_dir = str(p)
    yield str(p)
    test_settings.database.cache_dir = original


@pytest.fixture(scope="session", autouse=True)
def _init_db(tmp_db_path):
    from app.data.database import DatabaseManager

    db = DatabaseManager(db_path=tmp_db_path)

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


@pytest.fixture(scope="session")
def mock_source(tdx_source):
    """数据源 fixture —— 可能是真实 TdxDataSource 也可能是 mock。

    名称保留 mock_source 是为了向后兼容已有测试的参数名。
    实际行为取决于 tdx_available 检测结果。
    """
    return tdx_source


@pytest.fixture(scope="session")
def data_service(tdx_source, tdx_available):
    """创建 DataService 实例。

    - 服务器可用时：不 patch TdxDataSource，使用真实连接
    - 服务器不可用时：patch TdxDataSource 返回 mock
    """
    from app.services.data_service import DataService

    if tdx_available:
        svc = DataService()
        svc._source = tdx_source
        yield svc
    else:
        with patch("app.services.data_service.TdxDataSource", return_value=tdx_source):
            svc = DataService()
        svc._source = tdx_source
        yield svc


@pytest.fixture(scope="session")
def us():
    from app.services import user_service
    return user_service


@pytest.fixture(scope="session")
def indicator_service():
    from app.services.indicator_service import IndicatorService
    return IndicatorService()


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
    from app.data.database import DatabaseManager
    db = DatabaseManager(db_path=tmp_db_path)
    for t in ("users",):
        db.execute(f"DELETE FROM {t}")
    db.connection.commit()
    yield
