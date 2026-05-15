"""
Unit tests for plugin_service and visualization enhancements.
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def tmp_data(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    return data_dir


@pytest.fixture
def mock_settings(tmp_data, test_settings):
    originals = {
        "custom_path": test_settings.indicators.custom_path,
    }
    test_settings.indicators.custom_path = str(tmp_data / "plugins" / "indicators")
    yield test_settings
    test_settings.indicators.custom_path = originals["custom_path"]


# ======================================================================
# PluginService tests
# ======================================================================


class TestPluginService:
    def test_discover_empty(self, mock_settings):
        plugin_dir = Path(mock_settings.indicators.custom_path)
        plugin_dir.mkdir(parents=True, exist_ok=True)
        from app.services.plugin_service import PluginService
        svc = PluginService()
        assert svc.discover_plugins() == []

    def test_discover_with_script(self, mock_settings):
        plugin_dir = Path(mock_settings.indicators.custom_path)
        plugin_dir.mkdir(parents=True, exist_ok=True)
        script = plugin_dir / "test_indicator.py"
        script.write_text(
            "import pandas as pd\n"
            "def calculate(df, **params):\n"
            "    return df['close'] * 2\n"
        )
        from app.services.plugin_service import PluginService
        svc = PluginService()
        names = svc.discover_plugins()
        assert "test_indicator" in names

    def test_load_plugin(self, mock_settings):
        plugin_dir = Path(mock_settings.indicators.custom_path)
        plugin_dir.mkdir(parents=True, exist_ok=True)
        script = plugin_dir / "demo_ind.py"
        script.write_text(
            "import pandas as pd\n"
            "def calculate(df, **params):\n"
            "    return df['close'] * 3\n"
        )
        from app.services.plugin_service import PluginService
        svc = PluginService()
        assert svc.load_plugin("demo_ind") is True
        info = svc.get_plugin("demo_ind")
        assert info is not None
        assert info.calculate_fn is not None

    def test_load_nonexistent(self, mock_settings):
        from app.services.plugin_service import PluginService
        svc = PluginService()
        assert svc.load_plugin("nonexistent") is False

    def test_load_bad_script(self, mock_settings):
        plugin_dir = Path(mock_settings.indicators.custom_path)
        plugin_dir.mkdir(parents=True, exist_ok=True)
        script = plugin_dir / "bad_ind.py"
        script.write_text("raise RuntimeError('broken')\n")
        from app.services.plugin_service import PluginService
        svc = PluginService()
        assert svc.load_plugin("bad_ind") is False

    def test_unload_plugin(self, mock_settings):
        plugin_dir = Path(mock_settings.indicators.custom_path)
        plugin_dir.mkdir(parents=True, exist_ok=True)
        script = plugin_dir / "unload_me.py"
        script.write_text("def calculate(df, **params): return df\n")
        from app.services.plugin_service import PluginService
        svc = PluginService()
        svc.load_plugin("unload_me")
        assert svc.unload_plugin("unload_me") is True
        assert svc.get_plugin("unload_me") is None

    def test_reload_plugin(self, mock_settings):
        plugin_dir = Path(mock_settings.indicators.custom_path)
        plugin_dir.mkdir(parents=True, exist_ok=True)
        script = plugin_dir / "reload_me.py"
        script.write_text("def calculate(df, **params): return df['close'] * 2\n")
        from app.services.plugin_service import PluginService
        svc = PluginService()
        svc.load_plugin("reload_me")
        info = svc.get_plugin("reload_me")
        assert info is not None
        assert info.calculate_fn is not None

        info.file_hash = "stale_hash"
        reloaded = svc.reload_changed()
        assert "reload_me" in reloaded
        new_info = svc.get_plugin("reload_me")
        assert new_info.file_hash != "stale_hash"

    def test_load_all(self, mock_settings):
        plugin_dir = Path(mock_settings.indicators.custom_path)
        plugin_dir.mkdir(parents=True, exist_ok=True)
        for name in ("a_ind", "b_ind"):
            (plugin_dir / f"{name}.py").write_text(
                f"def calculate(df, **params): return df\n"
            )
        from app.services.plugin_service import PluginService
        svc = PluginService()
        results = svc.load_all()
        assert results.get("a_ind") is True
        assert results.get("b_ind") is True

    def test_execute_plugin(self, mock_settings):
        plugin_dir = Path(mock_settings.indicators.custom_path)
        plugin_dir.mkdir(parents=True, exist_ok=True)
        script = plugin_dir / "exec_me.py"
        script.write_text(
            "def calculate(df, **params):\n"
            "    multiplier = params.get('mult', 2)\n"
            "    return df['close'] * multiplier\n"
        )
        from app.services.plugin_service import PluginService
        svc = PluginService()
        svc.load_plugin("exec_me")
        df = pd.DataFrame({"close": [10.0, 20.0, 30.0]})
        result = svc.execute_plugin("exec_me", df, {"mult": 3})
        assert list(result) == [30.0, 60.0, 90.0]

    def test_execute_missing_plugin(self, mock_settings):
        from app.services.plugin_service import PluginService
        svc = PluginService()
        assert svc.execute_plugin("missing", pd.DataFrame()) is None

    def test_list_plugins(self, mock_settings):
        plugin_dir = Path(mock_settings.indicators.custom_path)
        plugin_dir.mkdir(parents=True, exist_ok=True)
        (plugin_dir / "list_me.py").write_text("def calculate(df, **params): return df\n")
        from app.services.plugin_service import PluginService
        svc = PluginService()
        svc.load_all()
        plugins = svc.list_plugins()
        assert len(plugins) >= 1
        assert any(p["name"] == "list_me" for p in plugins)

    def test_watch_tick(self, mock_settings):
        from app.services.plugin_service import PluginService
        svc = PluginService()
        assert svc.tick() == []
        svc.start_watching(scan_interval=0)
        svc._last_scan_time = 0
        assert svc.is_watching is True
        svc.stop_watching()
        assert svc.is_watching is False

    def test_plugin_count(self, mock_settings):
        plugin_dir = Path(mock_settings.indicators.custom_path)
        plugin_dir.mkdir(parents=True, exist_ok=True)
        (plugin_dir / "cnt.py").write_text("def calculate(df, **params): return df\n")
        from app.services.plugin_service import PluginService
        svc = PluginService()
        assert svc.plugin_count == 0
        svc.load_all()
        assert svc.plugin_count >= 1


# ======================================================================
# Visualization enhancements tests
# ======================================================================


class TestVisualizationEnhancements:
    @pytest.fixture(autouse=True)
    def _import(self):
        from app.services import visualization_service as vs
        self.vs = vs

    def test_downsample_under_limit(self):
        df = pd.DataFrame({"close": range(100)})
        result = self.vs.downsample_dataframe(df, max_points=200)
        assert len(result) == 100

    def test_downsample_over_limit(self):
        df = pd.DataFrame({"close": range(10000)})
        result = self.vs.downsample_dataframe(df, max_points=1000)
        assert len(result) <= 1002
        assert result.iloc[0]["close"] == 0
        assert result.iloc[-1]["close"] == 9999

    def test_downsample_exact_limit(self):
        df = pd.DataFrame({"close": range(100)})
        result = self.vs.downsample_dataframe(df, max_points=100)
        assert len(result) == 100

    def test_create_realtime_candlestick(self):
        df = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=100, freq="D"),
            "open": [10.0] * 100,
            "high": [11.0] * 100,
            "low": [9.0] * 100,
            "close": [10.5] * 100,
            "volume": [1000] * 100,
        })
        fig = self.vs.create_realtime_candlestick(df, max_points=50)
        assert fig is not None
        assert fig.layout.uirevision == "constant"

    def test_update_figure_data(self):
        fig = self.vs.create_line(
            pd.DataFrame({"date": [1, 2, 3], "value": [10, 20, 30]})
        )
        updated = self.vs.update_figure_data(fig, 0, [1, 2, 3], [100, 200, 300])
        assert list(updated.data[0].y) == [100, 200, 300]

    def test_update_figure_data_invalid_index(self):
        fig = self.vs.create_line(
            pd.DataFrame({"date": [1], "value": [10]})
        )
        updated = self.vs.update_figure_data(fig, 99, [1], [100])
        assert updated is fig

    def test_create_gauge_chart(self):
        fig = self.vs.create_gauge_chart(
            value=75, title="CPU", threshold_warning=60, threshold_critical=85
        )
        assert fig is not None
        assert len(fig.data) == 1

    def test_create_gauge_chart_no_thresholds(self):
        fig = self.vs.create_gauge_chart(value=50, title="Memory")
        assert fig is not None
