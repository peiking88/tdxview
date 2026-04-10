"""
PluginService additional unit tests covering uncovered lines.
"""

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.services.plugin_service import PluginService, PluginInfo


@pytest.fixture
def plugin_dir(tmp_path):
    pdir = tmp_path / "indicators"
    pdir.mkdir()
    plugin = pdir / "my_indicator.py"
    plugin.write_text(
        "def calculate(df, period=14):\n"
        "    return df * period\n"
    )
    return pdir


@pytest.fixture
def svc(plugin_dir):
    with patch("app.services.plugin_service.get_settings") as mock_settings:
        s = MagicMock()
        s.indicators.custom_path = str(plugin_dir)
        mock_settings.return_value = s
        service = PluginService()
    return service


class TestLoadPlugin:
    def test_load_plugin_bad_spec(self, svc, plugin_dir):
        bad_plugin = plugin_dir / "bad.py"
        bad_plugin.write_text("syntax error {{{")
        result = svc._load_plugin(bad_plugin)
        assert result is None

    def test_load_plugin_success(self, svc, plugin_dir):
        result = svc._load_plugin(plugin_dir / "my_indicator.py")
        assert result is not None
        assert result.name == "my_indicator"
        assert result.calculate_fn is not None

    def test_load_plugin_no_calculate(self, svc, plugin_dir):
        no_calc = plugin_dir / "no_calc.py"
        no_calc.write_text("x = 1\n")
        result = svc._load_plugin(no_calc)
        assert result is not None
        assert result.calculate_fn is None


class TestLoadAll:
    def test_load_all_success(self, svc, plugin_dir):
        results = svc.load_all()
        assert "my_indicator" in results
        assert results["my_indicator"] is True

    def test_load_all_with_bad_plugin(self, svc, plugin_dir):
        bad = plugin_dir / "bad_plugin.py"
        bad.write_text("raise RuntimeError('fail')\n")
        results = svc.load_all()
        assert "bad_plugin" in results
        assert results["bad_plugin"] is False

    def test_load_all_skips_underscore(self, svc, plugin_dir):
        init_file = plugin_dir / "__init__.py"
        init_file.write_text("")
        results = svc.load_all()
        assert "__init__" not in results


class TestLoadSinglePlugin:
    def test_load_nonexistent(self, svc):
        assert svc.load_plugin("nonexistent") is False

    def test_load_existing(self, svc, plugin_dir):
        assert svc.load_plugin("my_indicator") is True

    def test_reload_changed(self, svc, plugin_dir):
        svc.load_plugin("my_indicator")
        time.sleep(0.1)
        (plugin_dir / "my_indicator.py").write_text(
            "def calculate(df, period=20):\n    return df * period * 2\n"
        )
        reloaded = svc.reload_changed()
        assert "my_indicator" in reloaded


class TestUnloadPlugin:
    def test_unload_nonexistent(self, svc):
        assert svc.unload_plugin("nonexistent") is False

    def test_unload_loaded(self, svc):
        svc.load_plugin("my_indicator")
        assert svc.unload_plugin("my_indicator") is True
        assert svc.get_plugin("my_indicator") is None


class TestExecutePlugin:
    def test_execute_nonexistent(self, svc):
        result = svc.execute_plugin("nonexistent", [1, 2, 3])
        assert result is None

    def test_execute_no_calculate(self, svc, plugin_dir):
        no_calc = plugin_dir / "nocalc.py"
        no_calc.write_text("x = 1\n")
        svc.load_plugin("nocalc")
        result = svc.execute_plugin("nocalc", [1, 2])
        assert result is None

    def test_execute_with_exception(self, svc, plugin_dir):
        err_plugin = plugin_dir / "error_plugin.py"
        err_plugin.write_text("def calculate(df):\n    raise ValueError('boom')\n")
        svc.load_plugin("error_plugin")
        result = svc.execute_plugin("error_plugin", [1, 2])
        assert result is None

    def test_execute_success(self, svc):
        svc.load_plugin("my_indicator")
        result = svc.execute_plugin("my_indicator", 10, params={"period": 2})
        assert result == 20


class TestWatching:
    def test_start_stop_watching(self, svc):
        assert not svc.is_watching
        svc.start_watching(scan_interval=1.0)
        assert svc.is_watching
        svc.stop_watching()
        assert not svc.is_watching

    def test_tick_not_watching(self, svc):
        assert svc.tick() == []

    def test_tick_too_soon(self, svc):
        svc.start_watching(scan_interval=100.0)
        svc._last_scan_time = time.time()
        assert svc.tick() == []


class TestListPlugins:
    def test_list_empty(self, svc):
        assert svc.list_plugins() == []

    def test_list_loaded(self, svc):
        svc.load_plugin("my_indicator")
        result = svc.list_plugins()
        assert len(result) == 1
        assert result[0]["name"] == "my_indicator"

    def test_plugin_count(self, svc):
        assert svc.plugin_count == 0
        svc.load_plugin("my_indicator")
        assert svc.plugin_count == 1


class TestDiscoverPlugins:
    def test_discover(self, svc):
        result = svc.discover_plugins()
        assert "my_indicator" in result

    def test_discover_nonexistent_dir(self, svc):
        svc._indicator_dir = Path("/nonexistent_dir_xyz")
        assert svc.discover_plugins() == []
