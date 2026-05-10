"""
PluginService additional unit tests covering uncovered lines.
"""

import sys
import time
from pathlib import Path

import pytest

from app.services.plugin_service import PluginService, PluginInfo


@pytest.fixture
def plugin_dir(tmp_path, test_settings):
    pdir = tmp_path / "indicators"
    pdir.mkdir()
    plugin = pdir / "my_indicator.py"
    plugin.write_text(
        "def calculate(df, period=14):\n"
        "    return df * period\n"
    )

    original = test_settings.indicators.custom_path
    test_settings.indicators.custom_path = str(pdir)
    yield pdir
    test_settings.indicators.custom_path = original


@pytest.fixture
def svc(plugin_dir):
    return PluginService()


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
