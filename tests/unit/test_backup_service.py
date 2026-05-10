"""
BackupService additional unit tests covering uncovered lines.
"""

import json
from pathlib import Path

import pytest

from app.services.backup_service import BackupService


@pytest.fixture
def backup_dirs(tmp_path, test_settings):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "test.duckdb"
    db_path.write_text("fake_db")
    parquet_dir = data_dir / "parquet"
    parquet_dir.mkdir()
    (parquet_dir / "test.parquet").write_text("fake_parquet")
    cache_dir = data_dir / "cache"
    cache_dir.mkdir()
    (cache_dir / "test.cache").write_text("fake_cache")
    config_path = tmp_path / "config.yaml"
    config_path.write_text("key: value")
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    originals = {
        "duckdb_path": test_settings.database.duckdb_path,
        "parquet_dir": test_settings.database.parquet_dir,
        "cache_dir": test_settings.database.cache_dir,
    }
    test_settings.database.duckdb_path = str(db_path)
    test_settings.database.parquet_dir = str(parquet_dir)
    test_settings.database.cache_dir = str(cache_dir)

    yield {
        "data_dir": data_dir,
        "db_path": db_path,
        "parquet_dir": parquet_dir,
        "cache_dir": cache_dir,
        "config_path": config_path,
        "backup_dir": backup_dir,
    }

    test_settings.database.duckdb_path = originals["duckdb_path"]
    test_settings.database.parquet_dir = originals["parquet_dir"]
    test_settings.database.cache_dir = originals["cache_dir"]


@pytest.fixture
def svc(backup_dirs):
    service = BackupService(backup_dir=str(backup_dirs["backup_dir"]))
    service._config_path = backup_dirs["config_path"]
    return service


class TestCreateBackup:
    def test_create_backup_no_compress(self, svc, backup_dirs):
        result = svc.create_backup(compress=False)
        assert result["compressed"] is False
        assert Path(result["archive_path"]).exists()
        assert result["archive_path"].endswith(".tar")

    def test_create_backup_with_label(self, svc):
        result = svc.create_backup(label="my_label")
        assert "my_label" in result.get("label", result.get("archive_path", ""))

    def test_create_backup_compress(self, svc):
        result = svc.create_backup(compress=True)
        assert result["compressed"] is True
        assert result["archive_path"].endswith(".tar.gz")


class TestListBackups:
    def test_list_empty(self, svc):
        result = svc.list_backups()
        assert isinstance(result, list)

    def test_list_after_create(self, svc):
        svc.create_backup()
        result = svc.list_backups()
        assert len(result) >= 1


class TestRestoreBackup:
    def test_restore_valid(self, svc, backup_dirs):
        meta = svc.create_backup()
        result = svc.restore_backup(meta["archive_path"])
        assert result["status"] in ("ok", "partial")

    def test_restore_invalid_path(self, svc):
        result = svc.restore_backup("/nonexistent/backup.tar")
        assert result["status"] == "error"
