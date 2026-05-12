"""
BackupService 单元测试 — 覆盖 DuckDB + config 备份恢复。
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
    config_path = tmp_path / "config.yaml"
    config_path.write_text("key: value")
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    originals = {
        "duckdb_path": test_settings.database.duckdb_path,
    }
    test_settings.database.duckdb_path = str(db_path)

    yield {
        "data_dir": data_dir,
        "db_path": db_path,
        "config_path": config_path,
        "backup_dir": backup_dir,
    }

    test_settings.database.duckdb_path = originals["duckdb_path"]


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

    def test_archive_contains_db(self, svc):
        import tarfile
        meta = svc.create_backup()
        with tarfile.open(meta["archive_path"], "r:gz") as tar:
            names = tar.getnames()
        assert any(n.endswith(".duckdb") or n.endswith(".db") for n in names)


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
        # 删除原始 DB 文件
        backup_dirs["db_path"].unlink()
        assert not backup_dirs["db_path"].exists()

        result = svc.restore_backup(meta["archive_path"])
        assert result["status"] in ("ok", "partial")
        # 验证文件已恢复
        assert backup_dirs["db_path"].exists()

    def test_restore_invalid_path(self, svc):
        result = svc.restore_backup("/nonexistent/backup.tar")
        assert result["status"] == "error"


class TestDeleteBackup:
    def test_delete_existing(self, svc):
        meta = svc.create_backup()
        path = meta["archive_path"]
        assert svc.delete_backup(path) is True
        assert not Path(path).exists()

    def test_delete_nonexistent(self, svc):
        assert svc.delete_backup("/nonexistent") is False


class TestPruneBackups:
    def test_prune_keeps_latest(self, svc):
        for i in range(5):
            svc.create_backup(label=f"b{i}")
        result = svc.prune_old_backups(keep_count=2)
        assert result["pruned_count"] == 3
        assert result["kept_count"] == 2

    def test_prune_nothing_when_few(self, svc):
        svc.create_backup()
        result = svc.prune_old_backups(keep_count=7)
        assert result["pruned_count"] == 0


class TestVerifyBackup:
    def test_verify_valid(self, svc):
        meta = svc.create_backup()
        result = svc.verify_backup(meta["archive_path"])
        assert result["valid"] is True
        assert result["member_count"] >= 1

    def test_verify_missing(self, svc):
        result = svc.verify_backup("/nonexistent.tar.gz")
        assert result["valid"] is False
