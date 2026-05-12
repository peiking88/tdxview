"""
Verify project structure and basic imports.
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent


class TestProjectStructure:
    """Ensure all expected directories and packages exist."""

    EXPECTED_DIRS = [
        "app",
        "app/components",
        "app/config",
        "app/services",
        "app/data",
        "app/data/sources",
        "app/data/models",
        "app/utils",
        "app/utils/indicators",
        "plugins",
        "plugins/indicators",
        "log",
        "tests",
        "tests/unit",
        "tests/integration",
        "tests/fixtures",
        "scripts",
        "docs",
    ]

    EXPECTED_PACKAGES = [
        "app",
        "app.components",
        "app.config",
        "app.services",
        "app.data",
        "app.data.sources",
        "app.data.models",
        "app.utils",
        "app.utils.indicators",
        "plugins",
        "plugins.indicators",
        "tests",
    ]

    @pytest.mark.parametrize("dir_path", EXPECTED_DIRS)
    def test_directory_exists(self, dir_path):
        path = PROJECT_ROOT / dir_path
        assert path.is_dir(), f"Missing directory: {dir_path}"

    @pytest.mark.parametrize("package", EXPECTED_PACKAGES)
    def test_package_has_init(self, package):
        parts = package.split(".")
        init_file = PROJECT_ROOT.joinpath(*parts) / "__init__.py"
        assert init_file.is_file(), f"Missing __init__.py for package: {package}"


class TestBasicImports:
    """Ensure core modules can be imported."""

    def test_import_settings(self):
        from app.config.settings import get_settings
        settings = get_settings()
        assert settings.app.name == "tdxview"

    def test_import_cache_module_removed(self):
        """Cache module should no longer exist."""
        import importlib
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module("app.data.cache")

    def test_import_database(self):
        from app.data.database import DatabaseManager
        assert DatabaseManager is not None

    def test_import_duckdb_store(self):
        from app.data.duckdb_store import DuckDBStore
        assert DuckDBStore is not None

    def test_import_tdxdata_source(self):
        from app.data.sources.tdxdata_source import TdxDataSource
        assert TdxDataSource is not None

    def test_import_logging_utils(self):
        from app.utils.logging import setup_logger, get_logger
        assert setup_logger is not None

    def test_import_models(self):
        from app.data.models.user import UserModel
        from app.data.models.data_source import DataSourceModel
        from app.data.models.indicator import IndicatorModel
        u = UserModel(username="test")
        assert u.username == "test"
