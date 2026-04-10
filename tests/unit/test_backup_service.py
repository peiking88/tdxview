"""
BackupService additional unit tests covering uncovered lines.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.services.backup_service import BackupService


@pytest.fixture
def backup_dirs(tmp_path):
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
    return {
        "data_dir": data_dir,
        "db_path": db_path,
        "parquet_dir": parquet_dir,
        "cache_dir": cache_dir,
        "config_path": config_path,
        "backup_dir": backup_dir,
    }


@pytest.fixture
def svc(backup_dirs):
    with patch("app.services.backup_service.get_settings") as mock_settings:
        s = MagicMock()
        s.database.duckdb_path = str(backup_dirs["db_path"])
        s.database.parquet_dir = str(backup_dirs["parquet_dir"])
        s.database.cache_dir = str(backup_dirs["cache_dir"])
        mock_settings.return_value = s
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
        result = svc.create_backup(label="test_label")
        assert "test_label" in result.get("label", "")

    def test_create_backup_include_cache(self, svc, backup_dirs):
        result = svc.create_backup(include_cache=True)
        assert result["include_cache"] is True
        assert "cache" in result["files"]

    def test_create_backup_no_parquet(self, svc):
        result = svc.create_backup(include_parquet=False)
        assert result["include_parquet"] is False
        assert "parquet" not in result["files"]


class TestListBackups:
    def test_list_backups_empty(self, svc, backup_dirs):
        result = svc.list_backups()
        assert result == []

    def test_list_backups_with_data(self, svc, backup_dirs):
        svc.create_backup()
        result = svc.list_backups()
        assert len(result) >= 1

    def test_list_backups_corrupted_meta(self, svc, backup_dirs):
        bad_meta = backup_dirs["backup_dir"] / "backup_20240101_000000_corrupt.json"
        bad_meta.write_text("{invalid json", encoding="utf-8")
        result = svc.list_backups()
        assert isinstance(result, list)


class TestRestoreBackup:
    def test_restore_nonexistent(self, svc):
        result = svc.restore_backup("/nonexistent/path.tar.gz")
        assert result["status"] == "error"
        assert "message" in result

    def test_restore_with_errors(self, svc, backup_dirs):
        result = svc.restore_backup(str(backup_dirs["backup_dir"] / "nonexistent.tar.gz"))
        assert result["status"] == "error"


class TestDeleteBackup:
    def test_delete_existing(self, svc, backup_dirs):
        meta = svc.create_backup()
        archive_path = meta["archive_path"]
        result = svc.delete_backup(archive_path)
        assert result is True

    def test_delete_nonexistent(self, svc):
        result = svc.delete_backup("/tmp/nonexistent_abc123.tar.gz")
        assert result is False


class TestPruneOldBackups:
    def test_prune_fewer_than_keep(self, svc):
        svc.create_backup()
        result = svc.prune_old_backups(keep_count=5)
        assert result["pruned_count"] == 0

    def test_prune_removes_old(self, svc, backup_dirs):
        for i in range(5):
            meta = svc.create_backup(label=f"backup_{i}")
        result = svc.prune_old_backups(keep_count=2)
        assert result["pruned_count"] == 3
        assert result["kept_count"] == 2


class TestVerifyBackup:
    def test_verify_nonexistent(self, svc):
        result = svc.verify_backup("/tmp/nonexistent_abc123.tar.gz")
        assert result["valid"] is False

    def test_verify_valid(self, svc):
        meta = svc.create_backup()
        result = svc.verify_backup(meta["archive_path"])
        assert result["valid"] is True
        assert result["member_count"] > 0

    def test_verify_corrupted(self, svc, backup_dirs):
        bad_file = backup_dirs["backup_dir"] / "corrupt.tar.gz"
        bad_file.write_bytes(b"not a tar file")
        result = svc.verify_backup(str(bad_file))
        assert result["valid"] is False
