"""
Unit tests for Config component, Data Management helpers, and storage stats.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


# ===========================================================================
# Config component helper functions
# ===========================================================================

class TestConfigDataSources:
    """Test config component data source helpers."""

    def test_list_sources(self):
        from app.components.config import _list_sources

        mock_ds = MagicMock()
        mock_ds.list_data_sources.return_value = [
            {"id": 1, "name": "src1", "type": "tdx", "config": {}, "enabled": True, "priority": 1}
        ]
        with patch("app.components.config._get_data_service", return_value=mock_ds):
            result = _list_sources()
            assert len(result) == 1
            assert result[0]["name"] == "src1"

    def test_update_source(self):
        from app.components.config import _update_source

        mock_ds = MagicMock()
        mock_ds.update_data_source.return_value = True
        with patch("app.components.config._get_data_service", return_value=mock_ds):
            result = _update_source(1, enabled=False)
            assert result is True

    def test_delete_source(self):
        from app.components.config import _delete_source

        mock_ds = MagicMock()
        mock_ds.delete_data_source.return_value = True
        with patch("app.components.config._get_data_service", return_value=mock_ds):
            result = _delete_source(1)
            assert result is True

    def test_check_source_health(self):
        from app.components.config import _check_source_health

        mock_ds = MagicMock()
        mock_ds.check_source_health.return_value = {"connected": True, "checked_at": "2026-01-01T00:00:00"}
        with patch("app.components.config._get_data_service", return_value=mock_ds):
            result = _check_source_health()
            assert result["connected"] is True


class TestLogViewer:
    """Test log viewer helpers."""

    def test_read_log_lines_existing_file(self, tmp_path):
        from app.components.config import _read_log_lines

        log_file = tmp_path / "test.log"
        log_file.write_text("line1\nline2\nline3\n", encoding="utf-8")
        lines = _read_log_lines(str(log_file), n=2)
        assert len(lines) == 2
        assert "line2" in lines[0]
        assert "line3" in lines[1]

    def test_read_log_lines_missing_file(self, tmp_path):
        from app.components.config import _read_log_lines

        lines = _read_log_lines(str(tmp_path / "nonexistent.log"))
        assert lines == []

    def test_read_log_lines_empty_file(self, tmp_path):
        from app.components.config import _read_log_lines

        log_file = tmp_path / "empty.log"
        log_file.write_text("", encoding="utf-8")
        lines = _read_log_lines(str(log_file))
        assert lines == []

    def test_read_log_lines_n_greater_than_file(self, tmp_path):
        from app.components.config import _read_log_lines

        log_file = tmp_path / "short.log"
        log_file.write_text("only_line\n", encoding="utf-8")
        lines = _read_log_lines(str(log_file), n=100)
        assert len(lines) == 1


# ===========================================================================
# Data Management component helper functions
# ===========================================================================

class TestDataManagementHelpers:
    """Test data management component functions (non-Streamlit parts)."""

    def test_store_list_symbols(self, tmp_path):
        """Test that DuckDBStore can list saved symbols."""
        from app.data.database import DatabaseManager
        from app.data.duckdb_store import DuckDBStore

        db = DatabaseManager(db_path=str(tmp_path / "test.duckdb"))
        store = DuckDBStore(db)
        df = pd.DataFrame({
            "date": ["2026-01-02"], "open": [1.0], "high": [1.5],
            "low": [0.8], "close": [1.2], "volume": [100], "amount": [120.0],
        })
        store.save(df, "000001", data_type="history")
        symbols = store.list_symbols(data_type="history")
        assert "000001" in symbols
        db.close()

    def test_store_load_roundtrip(self, tmp_path):
        """Test DuckDBStore save and load roundtrip."""
        from app.data.database import DatabaseManager
        from app.data.duckdb_store import DuckDBStore

        db = DatabaseManager(db_path=str(tmp_path / "test.duckdb"))
        store = DuckDBStore(db)
        df = pd.DataFrame({
            "date": ["2026-01-02", "2026-01-03", "2026-01-04"],
            "open": [1.0, 2.0, 3.0], "high": [1.5, 2.5, 3.5],
            "low": [0.8, 1.8, 2.8], "close": [1.2, 2.3, 3.4],
            "volume": [100, 200, 300], "amount": [120.0, 460.0, 1020.0],
        })
        store.save(df, "600519", data_type="history")
        loaded = store.load("600519", data_type="history")
        assert loaded is not None
        assert len(loaded) == 3
        assert list(loaded["close"]) == [1.2, 2.3, 3.4]
        db.close()

    def test_store_delete(self, tmp_path):
        """Test DuckDBStore delete."""
        from app.data.database import DatabaseManager
        from app.data.duckdb_store import DuckDBStore

        db = DatabaseManager(db_path=str(tmp_path / "test.duckdb"))
        store = DuckDBStore(db)
        df = pd.DataFrame({
            "date": ["2026-01-02"], "open": [1.0], "high": [1.5],
            "low": [0.8], "close": [1.2], "volume": [100], "amount": [120.0],
        })
        store.save(df, "000002", data_type="history")
        store.delete("000002", data_type="history")
        assert store.load("000002", data_type="history") is None
        db.close()
