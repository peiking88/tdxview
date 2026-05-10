"""
Backup service — automated backup and restore for DuckDB, Parquet, and config.

Creates timestamped snapshots of critical data and supports restoring
from any saved backup.
"""

import gzip
import json
import shutil
import tarfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config.settings import get_settings


class BackupService:
    """Manages backup creation, listing, and restoration."""

    def __init__(self, backup_dir: Optional[str] = None):
        settings = get_settings()
        self._data_dir = Path(settings.database.duckdb_path).parent
        self._db_path = Path(settings.database.duckdb_path)
        self._parquet_dir = Path(settings.database.parquet_dir)
        self._cache_dir = Path(settings.database.cache_dir)
        self._config_path = Path("config.yaml")
        self._backup_dir = Path(backup_dir) if backup_dir else self._data_dir / "backups"
        self._backup_dir.mkdir(parents=True, exist_ok=True)

    def create_backup(
        self,
        label: Optional[str] = None,
        include_parquet: bool = True,
        include_cache: bool = False,
        compress: bool = True,
    ) -> Dict[str, Any]:
        """Create a timestamped backup archive.

        Parameters
        ----------
        label : optional tag for this backup
        include_parquet : include Parquet data files
        include_cache : include disk cache files
        compress : gzip-compress the archive

        Returns
        -------
        dict with backup metadata
        """
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        tag = f"_{label}" if label else ""
        archive_name = f"backup_{ts}{tag}"
        archive_path = self._backup_dir / (archive_name + ".tar.gz" if compress else ".tar")

        metadata: Dict[str, Any] = {
            "timestamp": ts,
            "label": label,
            "include_parquet": include_parquet,
            "include_cache": include_cache,
            "compressed": compress,
            "files": {},
        }

        with tarfile.open(archive_path, "w:gz" if compress else "w") as tar:
            if self._db_path.exists():
                tar.add(self._db_path, arcname=f"{archive_name}/db/{self._db_path.name}")
                metadata["files"]["database"] = str(self._db_path)

            if self._config_path.exists():
                tar.add(self._config_path, arcname=f"{archive_name}/config/config.yaml")
                metadata["files"]["config"] = str(self._config_path)

            if include_parquet and self._parquet_dir.exists():
                tar.add(self._parquet_dir, arcname=f"{archive_name}/parquet")
                metadata["files"]["parquet"] = str(self._parquet_dir)

            if include_cache and self._cache_dir.exists():
                tar.add(self._cache_dir, arcname=f"{archive_name}/cache")
                metadata["files"]["cache"] = str(self._cache_dir)

        metadata["archive_path"] = str(archive_path)
        metadata["archive_size_bytes"] = archive_path.stat().st_size

        meta_path = self._backup_dir / f"{archive_name}.json"
        meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

        return metadata

    def list_backups(self) -> List[Dict[str, Any]]:
        """List all available backups with metadata."""
        backups = []
        for meta_file in sorted(self._backup_dir.glob("backup_*.json"), reverse=True):
            try:
                data = json.loads(meta_file.read_text(encoding="utf-8"))
                data["meta_path"] = str(meta_file)
                backups.append(data)
            except Exception:
                continue
        return backups

    def restore_backup(
        self,
        archive_path: str,
        restore_parquet: bool = True,
        restore_cache: bool = False,
        restore_config: bool = False,
    ) -> Dict[str, Any]:
        """Restore data from a backup archive.

        Parameters
        ----------
        archive_path : path to the .tar.gz or .tar backup file
        restore_parquet : restore Parquet data files
        restore_cache : restore disk cache
        restore_config : restore config.yaml

        Returns
        -------
        dict with restoration summary
        """
        path = Path(archive_path)
        if not path.exists():
            return {"status": "error", "message": f"Archive not found: {archive_path}"}

        restored: List[str] = []
        errors: List[str] = []

        try:
            with tarfile.open(path, "r:gz" if path.suffix == ".gz" else "r") as tar:
                members = tar.getmembers()

                for member in members:
                    name = member.name

                    if "db/" in name and name.endswith(".db"):
                        tar.extract(member, path=str(self._data_dir))
                        restored.append(f"database: {name}")

                    elif "parquet/" in name and restore_parquet:
                        tar.extract(member, path=str(self._data_dir))
                        restored.append(f"parquet: {name}")

                    elif "cache/" in name and restore_cache:
                        tar.extract(member, path=str(self._data_dir))
                        restored.append(f"cache: {name}")

                    elif "config/" in name and restore_config:
                        tar.extract(member, path=".")
                        restored.append(f"config: {name}")

        except Exception as e:
            errors.append(str(e))

        return {
            "status": "ok" if not errors else "partial",
            "restored": restored,
            "errors": errors,
            "source_archive": str(path),
        }

    def delete_backup(self, archive_path: str) -> bool:
        """Delete a backup archive and its metadata file."""
        path = Path(archive_path)
        deleted = False

        if path.exists():
            path.unlink()
            deleted = True

        meta_path = path.with_suffix(".json")
        if meta_path.exists():
            meta_path.unlink()

        return deleted

    def prune_old_backups(self, keep_count: int = 7) -> Dict[str, Any]:
        """Remove oldest backups, keeping only the latest *keep_count*.

        Returns
        -------
        dict with pruned backup paths
        """
        backups = self.list_backups()
        if len(backups) <= keep_count:
            return {"pruned_count": 0, "kept_count": len(backups)}

        to_prune = backups[keep_count:]
        pruned = []
        for b in to_prune:
            archive = b.get("archive_path", "")
            if archive and self.delete_backup(archive):
                pruned.append(archive)

        return {
            "pruned_count": len(pruned),
            "kept_count": len(backups) - len(pruned),
            "pruned": pruned,
        }

    def verify_backup(self, archive_path: str) -> Dict[str, Any]:
        """Verify the integrity of a backup archive.

        Returns
        -------
        dict with verification result
        """
        path = Path(archive_path)
        if not path.exists():
            return {"valid": False, "error": "Archive not found"}

        try:
            mode = "r:gz" if path.suffix == ".gz" else "r"
            with tarfile.open(path, mode) as tar:
                members = tar.getnames()
            return {
                "valid": True,
                "member_count": len(members),
                "members": members[:50],
                "size_bytes": path.stat().st_size,
            }
        except Exception as e:
            return {"valid": False, "error": str(e)}
