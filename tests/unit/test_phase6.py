"""
Unit tests for Phase 6 advanced features.
Tests retention_service, backup_service, plugin_service,
visualization enhancements, and data_service performance features.
"""

import json
import os
import sys
import tarfile
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def tmp_data(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    parquet_dir = data_dir / "parquet"
    parquet_dir.mkdir()
    cache_dir = data_dir / "cache"
    cache_dir.mkdir()
    (cache_dir / "queries").mkdir()
    return data_dir


@pytest.fixture
def sample_parquet(tmp_data):
    parquet_dir = tmp_data / "parquet"
    df = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=10, freq="D"),
        "open": [10.0] * 10,
        "high": [11.0] * 10,
        "low": [9.0] * 10,
        "close": [10.5] * 10,
        "volume": [1000] * 10,
    })
    path = parquet_dir / "000001.SZ.parquet"
    df.to_parquet(path, index=False)
    return path


@pytest.fixture
def old_parquet(tmp_data):
    parquet_dir = tmp_data / "parquet"
    df = pd.DataFrame({"date": ["2020-01-01"], "close": [5.0]})
    path = parquet_dir / "OLD.parquet"
    df.to_parquet(path, index=False)
    old_mtime = time.time() - 86400 * 400
    os.utime(path, (old_mtime, old_mtime))
    return path


@pytest.fixture
def mock_settings(tmp_data):
    mock = MagicMock()
    mock.database.parquet_dir = str(tmp_data / "parquet")
    mock.database.cache_dir = str(tmp_data / "cache")
    mock.database.duckdb_path = str(tmp_data / "tdxview.db")
    mock.indicators.custom_path = str(tmp_data / "plugins" / "indicators")
    mock.cache.memory_max_size_mb = 10
    mock.cache.memory_default_ttl = 300
    return mock


# ======================================================================
# RetentionService tests
# ======================================================================


class TestRetentionService:
    def test_scan_parquet_files(self, sample_parquet, mock_settings):
        with patch("app.services.retention_service.get_settings", return_value=mock_settings):
            from app.services.retention_service import RetentionService
            svc = RetentionService()
            files = svc.scan_parquet_files()
            assert len(files) >= 1
            assert any("000001.SZ" in f["symbol"] for f in files)

    def test_scan_empty_dir(self, mock_settings):
        with patch("app.services.retention_service.get_settings", return_value=mock_settings):
            from app.services.retention_service import RetentionService
            svc = RetentionService()
            files = svc.scan_parquet_files()
            assert files == []

    def test_archive_candidates_empty(self, sample_parquet, mock_settings):
        with patch("app.services.retention_service.get_settings", return_value=mock_settings):
            from app.services.retention_service import RetentionService
            svc = RetentionService()
            svc._archive_threshold_days = 9999
            candidates = svc.get_archive_candidates()
            assert candidates == []

    def test_archive_candidates_found(self, old_parquet, mock_settings):
        with patch("app.services.retention_service.get_settings", return_value=mock_settings):
            from app.services.retention_service import RetentionService
            svc = RetentionService()
            svc._archive_threshold_days = 30
            candidates = svc.get_archive_candidates()
            assert len(candidates) >= 1
            assert any("OLD" in c["symbol"] for c in candidates)

    def test_archive_files(self, old_parquet, mock_settings):
        with patch("app.services.retention_service.get_settings", return_value=mock_settings):
            from app.services.retention_service import RetentionService
            svc = RetentionService()
            svc._archive_threshold_days = 30
            result = svc.archive_files()
            assert result["archived_count"] >= 1
            assert result["total_bytes"] > 0

    def test_purge_expired_files(self, old_parquet, mock_settings):
        with patch("app.services.retention_service.get_settings", return_value=mock_settings):
            from app.services.retention_service import RetentionService
            svc = RetentionService()
            svc._retention_days = 300
            result = svc.purge_expired_files(archive_first=False)
            assert result["purged_count"] >= 1
            assert result["total_bytes_freed"] > 0

    def test_cleanup_cache(self, tmp_data, mock_settings):
        queries_dir = tmp_data / "cache" / "queries"
        sub = queries_dir / "ab"
        sub.mkdir(parents=True, exist_ok=True)
        expired_file = sub / "expired.json"
        expired_file.write_text(json.dumps({
            "value": {"test": 1},
            "expires_at": time.time() - 100,
            "created_at": time.time() - 200,
        }))
        valid_file = sub / "valid.json"
        valid_file.write_text(json.dumps({
            "value": {"test": 2},
            "expires_at": time.time() + 3600,
            "created_at": time.time(),
        }))

        with patch("app.services.retention_service.get_settings", return_value=mock_settings):
            from app.services.retention_service import RetentionService
            svc = RetentionService()
            result = svc.cleanup_cache()
            assert result["removed_count"] == 1

    def test_get_storage_stats(self, sample_parquet, mock_settings):
        with patch("app.services.retention_service.get_settings", return_value=mock_settings):
            from app.services.retention_service import RetentionService
            svc = RetentionService()
            stats = svc.get_storage_stats()
            assert stats["parquet_bytes"] > 0
            assert stats["total_bytes"] > 0

    def test_set_policy(self, mock_settings):
        with patch("app.services.retention_service.get_settings", return_value=mock_settings):
            from app.services.retention_service import RetentionService
            svc = RetentionService()
            svc.set_policy(retention_days=180, archive_threshold_days=14)
            assert svc._retention_days == 180
            assert svc._archive_threshold_days == 14

    def test_run_full_retention(self, sample_parquet, mock_settings):
        with patch("app.services.retention_service.get_settings", return_value=mock_settings):
            from app.services.retention_service import RetentionService
            svc = RetentionService()
            result = svc.run_full_retention()
            assert "archive" in result
            assert "purge" in result
            assert "cache_cleanup" in result
            assert "storage_after" in result
            assert "timestamp" in result


# ======================================================================
# BackupService tests
# ======================================================================


class TestBackupService:
    def test_create_backup(self, tmp_data, mock_settings):
        db_path = tmp_data / "tdxview.db"
        db_path.write_text("fake db content")
        with patch("app.services.backup_service.get_settings", return_value=mock_settings):
            from app.services.backup_service import BackupService
            svc = BackupService(backup_dir=str(tmp_data / "backups"))
            meta = svc.create_backup(label="test")
            assert "archive_path" in meta
            assert Path(meta["archive_path"]).exists()
            assert meta["archive_size_bytes"] > 0

    def test_create_backup_with_parquet(self, sample_parquet, mock_settings):
        db_path = Path(mock_settings.database.duckdb_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        db_path.write_text("fake db")
        with patch("app.services.backup_service.get_settings", return_value=mock_settings):
            from app.services.backup_service import BackupService
            svc = BackupService(backup_dir=str(Path(mock_settings.database.duckdb_path).parent / "backups"))
            meta = svc.create_backup(include_parquet=True)
            assert Path(meta["archive_path"]).exists()

    def test_list_backups_empty(self, mock_settings):
        with patch("app.services.backup_service.get_settings", return_value=mock_settings):
            from app.services.backup_service import BackupService
            svc = BackupService(backup_dir=str(tempfile.mkdtemp()))
            assert svc.list_backups() == []

    def test_list_backups(self, tmp_data, mock_settings):
        db_path = tmp_data / "tdxview.db"
        db_path.write_text("fake db")
        with patch("app.services.backup_service.get_settings", return_value=mock_settings):
            from app.services.backup_service import BackupService
            svc = BackupService(backup_dir=str(tmp_data / "backups"))
            svc.create_backup(label="b1")
            svc.create_backup(label="b2")
            backups = svc.list_backups()
            assert len(backups) == 2

    def test_delete_backup(self, tmp_data, mock_settings):
        db_path = tmp_data / "tdxview.db"
        db_path.write_text("fake db")
        with patch("app.services.backup_service.get_settings", return_value=mock_settings):
            from app.services.backup_service import BackupService
            svc = BackupService(backup_dir=str(tmp_data / "backups"))
            meta = svc.create_backup(label="del_test")
            assert svc.delete_backup(meta["archive_path"])
            assert not Path(meta["archive_path"]).exists()

    def test_prune_old_backups(self, tmp_data, mock_settings):
        db_path = tmp_data / "tdxview.db"
        db_path.write_text("fake db")
        with patch("app.services.backup_service.get_settings", return_value=mock_settings):
            from app.services.backup_service import BackupService
            svc = BackupService(backup_dir=str(tmp_data / "backups"))
            for i in range(5):
                svc.create_backup(label=f"prune_{i}")
            result = svc.prune_old_backups(keep_count=2)
            assert result["pruned_count"] == 3
            assert result["kept_count"] == 2

    def test_verify_backup_valid(self, tmp_data, mock_settings):
        db_path = tmp_data / "tdxview.db"
        db_path.write_text("fake db")
        with patch("app.services.backup_service.get_settings", return_value=mock_settings):
            from app.services.backup_service import BackupService
            svc = BackupService(backup_dir=str(tmp_data / "backups"))
            meta = svc.create_backup()
            result = svc.verify_backup(meta["archive_path"])
            assert result["valid"] is True

    def test_verify_backup_missing(self, mock_settings):
        with patch("app.services.backup_service.get_settings", return_value=mock_settings):
            from app.services.backup_service import BackupService
            svc = BackupService()
            result = svc.verify_backup("/nonexistent/path.tar.gz")
            assert result["valid"] is False

    def test_restore_backup(self, tmp_data, mock_settings):
        db_path = tmp_data / "tdxview.db"
        db_path.write_text("original db")
        with patch("app.services.backup_service.get_settings", return_value=mock_settings):
            from app.services.backup_service import BackupService
            svc = BackupService(backup_dir=str(tmp_data / "backups"))
            meta = svc.create_backup()
            result = svc.restore_backup(meta["archive_path"])
            assert result["status"] in ("ok", "partial")

    def test_restore_missing_archive(self, mock_settings):
        with patch("app.services.backup_service.get_settings", return_value=mock_settings):
            from app.services.backup_service import BackupService
            svc = BackupService()
            result = svc.restore_backup("/nonexistent.tar.gz")
            assert result["status"] == "error"


# ======================================================================
# PluginService tests
# ======================================================================


class TestPluginService:
    def test_discover_empty(self, mock_settings):
        plugin_dir = Path(mock_settings.indicators.custom_path)
        plugin_dir.mkdir(parents=True, exist_ok=True)
        with patch("app.services.plugin_service.get_settings", return_value=mock_settings):
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
        with patch("app.services.plugin_service.get_settings", return_value=mock_settings):
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
        with patch("app.services.plugin_service.get_settings", return_value=mock_settings):
            from app.services.plugin_service import PluginService
            svc = PluginService()
            assert svc.load_plugin("demo_ind") is True
            info = svc.get_plugin("demo_ind")
            assert info is not None
            assert info.calculate_fn is not None

    def test_load_nonexistent(self, mock_settings):
        with patch("app.services.plugin_service.get_settings", return_value=mock_settings):
            from app.services.plugin_service import PluginService
            svc = PluginService()
            assert svc.load_plugin("nonexistent") is False

    def test_load_bad_script(self, mock_settings):
        plugin_dir = Path(mock_settings.indicators.custom_path)
        plugin_dir.mkdir(parents=True, exist_ok=True)
        script = plugin_dir / "bad_ind.py"
        script.write_text("raise RuntimeError('broken')\n")
        with patch("app.services.plugin_service.get_settings", return_value=mock_settings):
            from app.services.plugin_service import PluginService
            svc = PluginService()
            assert svc.load_plugin("bad_ind") is False

    def test_unload_plugin(self, mock_settings):
        plugin_dir = Path(mock_settings.indicators.custom_path)
        plugin_dir.mkdir(parents=True, exist_ok=True)
        script = plugin_dir / "unload_me.py"
        script.write_text("def calculate(df, **params): return df\n")
        with patch("app.services.plugin_service.get_settings", return_value=mock_settings):
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
        with patch("app.services.plugin_service.get_settings", return_value=mock_settings):
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
        with patch("app.services.plugin_service.get_settings", return_value=mock_settings):
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
        with patch("app.services.plugin_service.get_settings", return_value=mock_settings):
            from app.services.plugin_service import PluginService
            svc = PluginService()
            svc.load_plugin("exec_me")
            df = pd.DataFrame({"close": [10.0, 20.0, 30.0]})
            result = svc.execute_plugin("exec_me", df, {"mult": 3})
            assert list(result) == [30.0, 60.0, 90.0]

    def test_execute_missing_plugin(self, mock_settings):
        with patch("app.services.plugin_service.get_settings", return_value=mock_settings):
            from app.services.plugin_service import PluginService
            svc = PluginService()
            assert svc.execute_plugin("missing", pd.DataFrame()) is None

    def test_list_plugins(self, mock_settings):
        plugin_dir = Path(mock_settings.indicators.custom_path)
        plugin_dir.mkdir(parents=True, exist_ok=True)
        (plugin_dir / "list_me.py").write_text("def calculate(df, **params): return df\n")
        with patch("app.services.plugin_service.get_settings", return_value=mock_settings):
            from app.services.plugin_service import PluginService
            svc = PluginService()
            svc.load_all()
            plugins = svc.list_plugins()
            assert len(plugins) >= 1
            assert any(p["name"] == "list_me" for p in plugins)

    def test_watch_tick(self, mock_settings):
        with patch("app.services.plugin_service.get_settings", return_value=mock_settings):
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
        with patch("app.services.plugin_service.get_settings", return_value=mock_settings):
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


# ======================================================================
# DataService performance feature tests
# ======================================================================


class TestDataServicePerformance:
    def test_get_stats(self, mock_settings):
        with patch("app.services.data_service.get_settings", return_value=mock_settings):
            from app.services.data_service import DataService
            svc = DataService()
            stats = svc.get_stats()
            assert "source_connected" in stats
            assert "cache" in stats
            assert "memory_count" in stats["cache"]

    def test_batch_query_unknown_method(self, mock_settings):
        with patch("app.services.data_service.get_settings", return_value=mock_settings):
            from app.services.data_service import DataService
            svc = DataService()
            with pytest.raises(ValueError, match="Unknown method"):
                svc.batch_query_symbols(["000001.SZ"], query_fn_name="nonexistent")
