"""
Custom indicators additional unit tests covering uncovered lines.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

from app.utils.indicators.custom import (
    load_indicator_script,
    execute_custom_indicator,
    list_custom_indicators,
)


@pytest.fixture
def sample_df():
    return pd.DataFrame({"close": [100.0, 101.0, 102.0], "volume": [1000, 1100, 1200]})


@pytest.fixture
def script_dir(tmp_path, test_settings):
    sdir = tmp_path / "scripts"
    sdir.mkdir()
    good = sdir / "my_indicator.py"
    good.write_text(
        "def calculate(df, period=14):\n"
        "    return df.assign(result=df['close'] * period)\n"
    )

    original = test_settings.indicators.custom_path
    test_settings.indicators.custom_path = str(sdir)
    yield sdir
    test_settings.indicators.custom_path = original


class TestLoadIndicatorScript:
    def test_load_nonexistent(self):
        result = load_indicator_script("/nonexistent/script.py")
        assert result is None

    def test_load_bad_spec(self, script_dir):
        bad = script_dir / "bad.py"
        bad.write_text("syntax error {{{")
        result = load_indicator_script(str(bad))
        assert result is None

    def test_load_no_calculate(self, script_dir):
        no_calc = script_dir / "no_calc.py"
        no_calc.write_text("x = 1\n")
        result = load_indicator_script(str(no_calc))
        assert result is None

    def test_load_success(self, script_dir):
        result = load_indicator_script(str(script_dir / "my_indicator.py"))
        assert result is not None
        assert callable(result)


class TestExecuteCustomIndicator:
    def test_execute_nonexistent_script(self, sample_df):
        result = execute_custom_indicator("/nonexistent/script.py", sample_df)
        assert result is None

    def test_execute_script_with_error(self, script_dir, sample_df):
        err = script_dir / "error.py"
        err.write_text("def calculate(df):\n    raise RuntimeError('boom')\n")
        result = execute_custom_indicator(str(err), sample_df)
        assert result is None

    def test_execute_success(self, script_dir, sample_df):
        result = execute_custom_indicator(
            str(script_dir / "my_indicator.py"), sample_df, params={"period": 2}
        )
        assert result is not None
        assert "result" in result.columns
        assert result["result"].iloc[0] == 200.0


class TestListCustomIndicators:
    def test_list_empty_dir(self, tmp_path, test_settings):
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        original = test_settings.indicators.custom_path
        test_settings.indicators.custom_path = str(empty_dir)
        result = list_custom_indicators()
        test_settings.indicators.custom_path = original
        assert result == []

    def test_list_nonexistent_dir(self, test_settings):
        original = test_settings.indicators.custom_path
        test_settings.indicators.custom_path = "/nonexistent_xyz_abc"
        result = list_custom_indicators()
        test_settings.indicators.custom_path = original
        assert result == []

    def test_list_with_scripts(self, script_dir):
        result = list_custom_indicators()
        assert len(result) == 1
        assert result[0]["name"] == "my_indicator"
        assert "path" in result[0]

    def test_list_skips_underscore(self, script_dir):
        (script_dir / "__init__.py").write_text("")
        result = list_custom_indicators()
        names = [r["name"] for r in result]
        assert "__init__" not in names

    def test_list_extracts_docstring(self, script_dir):
        doc_script = script_dir / "doc_indicator.py"
        doc_script.write_text(
            '"""My custom indicator."""\n'
            "def calculate(df):\n    return df\n"
        )
        result = list_custom_indicators()
        doc_entry = [r for r in result if r["name"] == "doc_indicator"]
        assert len(doc_entry) == 1
        assert doc_entry[0]["description"] == "custom indicator."

    def test_list_extracts_comment_description(self, script_dir):
        comment_script = script_dir / "comment_indicator.py"
        comment_script.write_text(
            "# This is a comment description\n"
            "def calculate(df):\n    return df\n"
        )
        result = list_custom_indicators()
        comment_entry = [r for r in result if r["name"] == "comment_indicator"]
        assert len(comment_entry) == 1
        assert comment_entry[0]["description"] == "This is a comment description"
