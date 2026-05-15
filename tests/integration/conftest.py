"""
集成测试共享fixture

原则：真实环境优先于 mock
- 通达信服务器可用时使用真实连接，不可用时自动降级为 mock
- get_settings 已由 tests/conftest.py autouse patch 统一管理
- 使用方式：
    pytest                     # 自动检测服务器
    TDX_LIVE=0 pytest          # 强制 mock
    TDX_LIVE=1 pytest          # 强制真实连接
"""

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
def mock_source(tdx_source):
    """数据源 fixture —— 可能是真实 TdxDataSource 也可能是 mock。"""
    return tdx_source


@pytest.fixture(scope="session")
def data_service(tdx_source, tdx_available):
    """创建 DataService 实例。"""
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
