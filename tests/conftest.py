"""
Shared pytest fixtures for tdxview test suite.

原则：真实环境优先于 mock
- test_settings: 指向临时目录的真实 Settings 实例（autouse patch 所有模块）
- tdx_available: 自动检测通达信服务器是否可用
- tdx_source: 可用时返回真实 TdxDataSource，否则返回 mock
- 仅 mock 外部网络依赖 TdxDataSource（且仅在服务器不可用时）
"""

import sys
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

_SETTINGS_PATCH_TARGETS = [
    "app.config.settings.get_settings",
    "app.services.data_service.get_settings",
    "app.services.retention_service.get_settings",
    "app.services.backup_service.get_settings",
    "app.services.plugin_service.get_settings",
    "app.services.indicator_service.get_settings",
    "app.services.visualization_service.get_settings",
    "app.services.user_service.get_settings",
    "app.data.cache.get_settings",
    "app.data.database.get_settings",
    "app.data.parquet_manager.get_settings",
    "app.data.sources.tdxdata_source.get_settings",
    "app.components.dashboard.get_settings",
    "app.components.config.get_settings",
    "app.components.data_management.get_settings",
    "app.components.auth.get_settings",
    "app.utils.indicators.custom.get_settings",
    "app.main.get_settings",
]


@pytest.fixture(scope="session")
def test_settings(tmp_path_factory):
    """创建指向临时目录的 Settings 实例，所有测试共享。"""
    from app.config.settings import Settings

    tmp = tmp_path_factory.mktemp("tdxview_test")
    settings = Settings()
    settings.database.duckdb_path = str(tmp / "test.duckdb")
    settings.database.parquet_dir = str(tmp / "parquet")
    settings.database.cache_dir = str(tmp / "cache")
    settings.indicators.custom_path = str(tmp / "custom_indicators")
    settings.logging.file_path = str(tmp / "log" / "test.log")
    return settings


@pytest.fixture(scope="session", autouse=True)
def _patch_all_get_settings(test_settings):
    """autouse: patch 所有模块的 get_settings 返回 test_settings。"""
    from unittest.mock import patch

    patches = []
    for target in _SETTINGS_PATCH_TARGETS:
        p = patch(target, return_value=test_settings)
        p.start()
        patches.append(p)
    yield test_settings
    for p in patches:
        p.stop()


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def project_root():
    return PROJECT_ROOT


@pytest.fixture(scope="session")
def tdx_available():
    """检测通达信服务器是否可用，返回 bool。

    使用方式：
    - pytest 默认执行时自动检测
    - 强制跳过真实网络：TDX_LIVE=0 pytest
    - 强制启用真实网络：TDX_LIVE=1 pytest
    """
    env = os.environ.get("TDX_LIVE", "").strip()
    if env == "0":
        return False
    if env == "1":
        return True

    try:
        from app.data.sources.tdxdata_source import TdxDataSource
        source = TdxDataSource()
        available = source.validate_connection()
        source.close()
        return available
    except Exception:
        return False


def _create_mock_source():
    """创建标准 mock 数据源，用于通达信不可用时。"""
    src = MagicMock()
    src.validate_connection.return_value = True
    src.fetch_history.return_value = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=31, freq="D"),
        "open": np.random.uniform(10, 30, 31),
        "high": np.random.uniform(11, 33, 31),
        "low":  np.random.uniform(9, 27, 31),
        "close": np.random.uniform(10, 32, 31),
        "volume": np.random.randint(100_000, 1_000_000, 31),
        "symbol": ["000001"] * 31,
    })
    src.fetch_realtime.return_value = pd.DataFrame({
        "symbol":  ["000001", "600000"],
        "price":   [15.25, 8.50],
        "change":  [0.25, -0.15],
        "change_percent": [1.67, -1.73],
        "volume":  [1_500_000, 750_000],
    })
    src.fetch_tick.return_value = pd.DataFrame({
        "price": [15.0, 15.01, 15.02],
        "volume": [100, 200, 150],
    })
    src.fetch_financial.return_value = pd.DataFrame({"revenue": [100]})
    src.fetch_f10.return_value = {"summary": pd.DataFrame({"item": ["EPS"], "value": [5.0]})}
    src.fetch_basic.return_value = pd.DataFrame({"name": ["Ping An Bank"]})
    src.fetch_local.return_value = pd.DataFrame({"close": [15.0]})
    src.fetch_hybrid.return_value = pd.DataFrame({"close": [15.0, 15.1]})
    src.close.return_value = None
    return src


@pytest.fixture(scope="session")
def tdx_source(tdx_available):
    """返回真实或 mock 的 TdxDataSource 实例。

    - 服务器可用时：真实 TdxDataSource（已连接）
    - 服务器不可用时：MagicMock（预设返回值）
    """
    if tdx_available:
        from app.data.sources.tdxdata_source import TdxDataSource
        source = TdxDataSource()
        source.connect()
        yield source
        source.close()
    else:
        yield _create_mock_source()
