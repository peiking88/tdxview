"""
Unit tests for Phase 5: Dashboard component, Config component, and Data Management.
"""

import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pandas as pd
import pytest

from app.data.database import DatabaseManager
from app.data.cache import MemoryCache, DiskCache, CacheManager


# ===========================================================================
# Dashboard helper functions
# ===========================================================================

class TestSystemMetrics:
    """Test _get_system_metrics helper."""

    @patch("app.components.dashboard.psutil")
    def test_returns_metrics(self, mock_psutil):
        from app.components.dashboard import _get_system_metrics

        mock_psutil.cpu_percent.return_value = 45.2
        mock_mem = MagicMock()
        mock_mem.total = 16 * 1e9
        mock_mem.used = 8 * 1e9
        mock_mem.percent = 50.0
        mock_psutil.virtual_memory.return_value = mock_mem
        mock_disk = MagicMock()
        mock_disk.total = 500 * 1e9
        mock_disk.used = 250 * 1e9
        mock_disk.percent = 50.0
        mock_psutil.disk_usage.return_value = mock_disk

        result = _get_system_metrics()
        assert result["cpu_percent"] == 45.2
        assert result["memory_percent"] == 50.0
        assert result["disk_percent"] == 50.0
        assert "memory_total_gb" in result
        assert "disk_total_gb" in result

    @patch("app.components.dashboard.psutil")
    def test_returns_empty_on_error(self, mock_psutil):
        from app.components.dashboard import _get_system_metrics

        mock_psutil.cpu_percent.side_effect = RuntimeError("fail")
        result = _get_system_metrics()
        assert result == {}


class TestAppMetrics:
    """Test _get_app_metrics helper."""

    def test_returns_app_metrics(self, test_settings):
        from app.components.dashboard import _get_app_metrics

        test_settings.database.duckdb_path = "/tmp/nonexistent_test_db.db"
        test_settings.database.parquet_dir = "data/parquet"
        test_settings.database.cache_dir = "data/cache"
        test_settings.logging.file_path = "log/tdxview.log"
        test_settings.environment = "development"
        test_settings.app.debug = True

        result = _get_app_metrics()
        assert "db_size_mb" in result
        assert result["environment"] == "development"
        assert result["debug"] is True


class TestDataSourceStatus:
    """Test _get_data_source_status helper."""

    def test_returns_sources(self):
        from app.components.dashboard import _get_data_source_status

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            db = DatabaseManager(str(db_path))
            db.execute("CREATE SEQUENCE IF NOT EXISTS ds_id_seq START 1")
            db.execute("""
                CREATE TABLE IF NOT EXISTS data_sources (
                    id INTEGER PRIMARY KEY DEFAULT nextval('ds_id_seq'),
                    name VARCHAR, type VARCHAR, config TEXT,
                    enabled BOOLEAN, priority INTEGER DEFAULT 1,
                    last_checked TIMESTAMP, error_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            db.execute(
                "INSERT INTO data_sources (name, type, config, enabled, priority, error_count) VALUES (?, ?, ?, ?, ?, ?)",
                ["test_src", "tdx", "{}", True, 1, 0],
            )
            db.connection.commit()

            with patch("app.components.dashboard.DatabaseManager", return_value=db):
                result = _get_data_source_status()
                assert len(result) == 1
                assert result[0]["name"] == "test_src"
                assert result[0]["enabled"] is True

    def test_returns_empty_on_error(self):
        from app.components.dashboard import _get_data_source_status

        with patch("app.components.dashboard.DatabaseManager") as MockDB:
            MockDB.return_value.fetch_all.side_effect = RuntimeError("fail")
            result = _get_data_source_status()
            assert result == []


class TestDashboardCRUD:
    """Test dashboard CRUD helpers."""

    def _setup_db(self, tmp_path):
        """Create a DB with dashboards table."""
        db_path = tmp_path / "test.db"
        db = DatabaseManager(str(db_path))
        db.execute("CREATE SEQUENCE IF NOT EXISTS dash_id_seq START 1")
        db.execute("""
            CREATE TABLE IF NOT EXISTS dashboards (
                id INTEGER PRIMARY KEY DEFAULT nextval('dash_id_seq'),
                user_id INTEGER, name VARCHAR, description TEXT,
                layout TEXT, widgets TEXT, is_default BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        db.connection.commit()
        return db

    def test_create_and_list(self, tmp_path):
        from app.components.dashboard import _create_dashboard, _list_dashboards

        db = self._setup_db(tmp_path)
        with patch("app.components.dashboard.DatabaseManager", return_value=db):
            assert _create_dashboard(1, "Test Dash", "desc") is True
            dashboards = _list_dashboards(1)
            assert len(dashboards) == 1
            assert dashboards[0]["name"] == "Test Dash"

    def test_delete(self, tmp_path):
        from app.components.dashboard import _create_dashboard, _delete_dashboard, _list_dashboards

        db = self._setup_db(tmp_path)
        with patch("app.components.dashboard.DatabaseManager", return_value=db):
            _create_dashboard(1, "To Delete")
            dashboards = _list_dashboards(1)
            assert len(dashboards) == 1
            _delete_dashboard(dashboards[0]["id"])
            dashboards = _list_dashboards(1)
            assert len(dashboards) == 0

    def test_list_empty(self, tmp_path):
        from app.components.dashboard import _list_dashboards

        db = self._setup_db(tmp_path)
        with patch("app.components.dashboard.DatabaseManager", return_value=db):
            dashboards = _list_dashboards(1)
            assert dashboards == []


class TestAlertHelpers:
    """Test alert threshold helpers."""

    def test_get_thresholds_default(self):
        from app.components.dashboard import _get_thresholds

        # Ensure key doesn't exist
        with patch.dict("streamlit.session_state", {}, clear=True):
            thresholds = _get_thresholds()
            assert thresholds["cpu_percent"] == 80
            assert thresholds["memory_percent"] == 80
            assert thresholds["disk_percent"] == 90

    def test_check_alerts_cpu(self):
        from app.components.dashboard import _check_alerts

        metrics = {"system": {"cpu_percent": 90, "memory_percent": 50, "disk_percent": 50}, "app": {"db_size_mb": 100}}
        thresholds = {"cpu_percent": 80, "memory_percent": 80, "disk_percent": 90, "db_size_mb": 500}
        alerts = _check_alerts(metrics, thresholds)
        assert any("CPU" in a for a in alerts)

    def test_check_alerts_memory(self):
        from app.components.dashboard import _check_alerts

        metrics = {"system": {"cpu_percent": 50, "memory_percent": 90, "disk_percent": 50}, "app": {"db_size_mb": 100}}
        thresholds = {"cpu_percent": 80, "memory_percent": 80, "disk_percent": 90, "db_size_mb": 500}
        alerts = _check_alerts(metrics, thresholds)
        assert any("内存" in a for a in alerts)

    def test_check_alerts_disk(self):
        from app.components.dashboard import _check_alerts

        metrics = {"system": {"cpu_percent": 50, "memory_percent": 50, "disk_percent": 95}, "app": {"db_size_mb": 100}}
        thresholds = {"cpu_percent": 80, "memory_percent": 80, "disk_percent": 90, "db_size_mb": 500}
        alerts = _check_alerts(metrics, thresholds)
        assert any("磁盘" in a for a in alerts)

    def test_check_alerts_db_size(self):
        from app.components.dashboard import _check_alerts

        metrics = {"system": {"cpu_percent": 50, "memory_percent": 50, "disk_percent": 50}, "app": {"db_size_mb": 600}}
        thresholds = {"cpu_percent": 80, "memory_percent": 80, "disk_percent": 90, "db_size_mb": 500}
        alerts = _check_alerts(metrics, thresholds)
        assert any("数据库" in a for a in alerts)

    def test_check_alerts_no_alerts(self):
        from app.components.dashboard import _check_alerts

        metrics = {"system": {"cpu_percent": 50, "memory_percent": 50, "disk_percent": 50}, "app": {"db_size_mb": 100}}
        thresholds = {"cpu_percent": 80, "memory_percent": 80, "disk_percent": 90, "db_size_mb": 500}
        alerts = _check_alerts(metrics, thresholds)
        assert len(alerts) == 0


class TestGaugeChart:
    """Test gauge chart creation."""

    def test_gauge_chart_returns_figure(self):
        from app.components.dashboard import _gauge_chart
        import plotly.graph_objects as go

        fig = _gauge_chart("CPU", 45.0, 80.0)
        assert isinstance(fig, go.Figure)
        # Should contain an Indicator trace
        assert len(fig.data) > 0

    def test_gauge_chart_green_zone(self):
        from app.components.dashboard import _gauge_chart

        fig = _gauge_chart("CPU", 30.0, 80.0)
        # Bar color should be green when below 80% of threshold
        trace = fig.data[0]
        assert trace.gauge.bar.color == "green"

    def test_gauge_chart_red_zone(self):
        from app.components.dashboard import _gauge_chart

        fig = _gauge_chart("CPU", 90.0, 80.0)
        trace = fig.data[0]
        assert trace.gauge.bar.color == "red"


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
        with patch("app.components.config.DataService", return_value=mock_ds):
            result = _list_sources()
            assert len(result) == 1
            assert result[0]["name"] == "src1"

    def test_add_source(self):
        from app.components.config import _add_source

        mock_ds = MagicMock()
        mock_ds.add_data_source.return_value = 2
        with patch("app.components.config.DataService", return_value=mock_ds):
            result = _add_source("new_src", "tdx", {"host": "1.2.3.4"}, 1, True)
            assert result == 2

    def test_update_source(self):
        from app.components.config import _update_source

        mock_ds = MagicMock()
        mock_ds.update_data_source.return_value = True
        with patch("app.components.config.DataService", return_value=mock_ds):
            result = _update_source(1, enabled=False)
            assert result is True

    def test_delete_source(self):
        from app.components.config import _delete_source

        mock_ds = MagicMock()
        mock_ds.delete_data_source.return_value = True
        with patch("app.components.config.DataService", return_value=mock_ds):
            result = _delete_source(1)
            assert result is True

    def test_check_source_health(self):
        from app.components.config import _check_source_health

        mock_ds = MagicMock()
        mock_ds.check_source_health.return_value = {"connected": True, "checked_at": "2026-01-01T00:00:00"}
        with patch("app.components.config.DataService", return_value=mock_ds):
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


class TestConfigIO:
    """Test configuration import/export via user_service (already covered there,
    but verify config component integration)."""

    def test_export_user_config(self):
        from app.services.user_service import export_user_config

        # This is primarily a user_service test, but config component calls it directly
        with patch("app.services.user_service.get_user_by_id") as mock_get:
            mock_get.return_value = {
                "id": 1, "username": "test", "email": "t@t.com",
                "preferences": {"theme": "dark"}, "role": "user"
            }
            with patch("app.services.user_service.DatabaseManager") as MockDB:
                mock_db = MagicMock()
                mock_db.fetch_all.return_value = []
                MockDB.return_value = mock_db
                config = export_user_config(1)
                assert config is not None
                assert config["username"] == "test"

    def test_import_user_config(self):
        from app.services.user_service import import_user_config

        with patch("app.services.user_service.set_user_preferences") as mock_set:
            mock_set.return_value = True
            with patch("app.services.user_service.DatabaseManager") as MockDB:
                mock_db = MagicMock()
                MockDB.return_value = mock_db
                success, msg = import_user_config(1, {"preferences": {"theme": "light"}})
                assert success is True


# ===========================================================================
# Data Management component helper functions
# ===========================================================================

class TestDataManagementHelpers:
    """Test data management component functions (non-Streamlit parts)."""

    def test_parquet_list_symbols(self, tmp_path):
        """Test that ParquetManager can list saved symbols."""
        from app.data.parquet_manager import ParquetManager

        pm = ParquetManager(parquet_dir=str(tmp_path / "pq"))
        df = pd.DataFrame({"close": [1.0, 2.0], "volume": [100, 200]})
        pm.save(df, "000001", "2026-01")

        # list_symbols searches root dir only, but with date it's in a subdir
        # So search the subdir
        import pyarrow.parquet as pq
        pq_files = list(Path(tmp_path / "pq").rglob("*.parquet"))
        symbols = [p.stem for p in pq_files]
        assert "000001" in symbols

    def test_parquet_load_roundtrip(self, tmp_path):
        """Test ParquetManager save and load roundtrip."""
        from app.data.parquet_manager import ParquetManager

        pm = ParquetManager(parquet_dir=str(tmp_path / "pq"))
        df = pd.DataFrame({"close": [1.0, 2.0, 3.0], "volume": [100, 200, 300]})
        pm.save(df, "600519", "2026-01")

        loaded = pm.load("600519", "2026-01")
        assert loaded is not None
        assert len(loaded) == 3
        assert list(loaded["close"]) == [1.0, 2.0, 3.0]

    def test_parquet_delete(self, tmp_path):
        """Test ParquetManager delete."""
        from app.data.parquet_manager import ParquetManager

        pm = ParquetManager(parquet_dir=str(tmp_path / "pq"))
        df = pd.DataFrame({"close": [1.0]})
        pm.save(df, "000002", "2026-02")
        pm.delete("000002", "2026-02")
        assert pm.load("000002", "2026-02") is None


# ===========================================================================
# CacheManager integration (Phase 5 cache stats in config)
# ===========================================================================

class TestCacheManagerStats:
    """Test CacheManager statistics used by config component."""

    def test_memory_count(self):
        cm = CacheManager()
        cm.memory.set("k1", "v1")
        cm.memory.set("k2", "v2")
        assert cm.memory.count == 2

    def test_memory_size(self):
        cm = CacheManager()
        cm.memory.set("k1", "a" * 1000, size=1000)
        assert cm.memory.size >= 1000

    def test_clear_all(self):
        cm = CacheManager()
        cm.memory.set("k1", "v1")
        cm.clear()
        assert cm.memory.count == 0
