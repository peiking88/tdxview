"""
Plugin hot-reload service.

Monitors plugin directories for changes and dynamically reloads
custom indicator scripts without restarting the application.
"""

import hashlib
import importlib
import importlib.util
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from app.config.settings import get_settings


class PluginInfo:
    """Metadata about a loaded plugin."""

    def __init__(
        self,
        name: str,
        path: Path,
        module: Any,
        calculate_fn: Optional[Callable],
        file_hash: str,
        loaded_at: float,
    ):
        self.name = name
        self.path = path
        self.module = module
        self.calculate_fn = calculate_fn
        self.file_hash = file_hash
        self.loaded_at = loaded_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "path": str(self.path),
            "has_calculate": self.calculate_fn is not None,
            "file_hash": self.file_hash[:12],
            "loaded_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.loaded_at)),
        }


class PluginService:
    """Manages discovery, loading, hot-reload, and lifecycle of plugins."""

    def __init__(self):
        settings = get_settings()
        self._indicator_dir = Path(settings.indicators.custom_path)
        self._plugins: Dict[str, PluginInfo] = {}
        self._watching = False
        self._last_scan_time = 0.0
        self._scan_interval = 5.0

    @staticmethod
    def _file_hash(path: Path) -> str:
        """Compute an MD5 hash of a file's contents."""
        return hashlib.md5(path.read_bytes()).hexdigest()

    def _load_plugin(self, path: Path) -> Optional[PluginInfo]:
        """Load a single plugin script as a Python module."""
        name = path.stem
        module_name = f"plugin_indicator_{name}"

        try:
            sys.modules.pop(module_name, None)
            spec = importlib.util.spec_from_file_location(module_name, str(path))
            if spec is None or spec.loader is None:
                return None
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            calculate_fn = getattr(module, "calculate", None)
            file_hash = self._file_hash(path)

            return PluginInfo(
                name=name,
                path=path,
                module=module,
                calculate_fn=calculate_fn,
                file_hash=file_hash,
                loaded_at=time.time(),
            )
        except Exception:
            return None

    def discover_plugins(self) -> List[str]:
        """Scan the plugin directory and return names of available plugins."""
        if not self._indicator_dir.exists():
            return []
        return [
            p.stem
            for p in sorted(self._indicator_dir.glob("*.py"))
            if not p.name.startswith("_")
        ]

    def load_all(self) -> Dict[str, bool]:
        """Load or reload all plugins. Returns {name: success}."""
        results = {}
        for py_file in sorted(self._indicator_dir.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            info = self._load_plugin(py_file)
            if info is not None:
                self._plugins[info.name] = info
                results[info.name] = True
            else:
                results[py_file.stem] = False
        return results

    def load_plugin(self, name: str) -> bool:
        """Load or reload a single plugin by name."""
        path = self._indicator_dir / f"{name}.py"
        if not path.exists():
            return False
        info = self._load_plugin(path)
        if info is not None:
            self._plugins[name] = info
            return True
        return False

    def unload_plugin(self, name: str) -> bool:
        """Unload a plugin, removing it from the registry."""
        if name not in self._plugins:
            return False
        module_name = f"plugin_indicator_{name}"
        sys.modules.pop(module_name, None)
        del self._plugins[name]
        return True

    def reload_plugin(self, name: str) -> bool:
        """Force-reload a plugin from disk."""
        return self.load_plugin(name)

    def reload_changed(self) -> List[str]:
        """Check all loaded plugins and reload those whose files have changed.

        Returns list of reloaded plugin names.
        """
        reloaded = []
        for name, info in list(self._plugins.items()):
            if not info.path.exists():
                continue
            current_hash = self._file_hash(info.path)
            if current_hash != info.file_hash:
                if self.reload_plugin(name):
                    reloaded.append(name)
        return reloaded

    def get_plugin(self, name: str) -> Optional[PluginInfo]:
        """Get a loaded plugin's info."""
        return self._plugins.get(name)

    def list_plugins(self) -> List[Dict[str, Any]]:
        """List all loaded plugins with metadata."""
        return [info.to_dict() for info in self._plugins.values()]

    def execute_plugin(
        self,
        name: str,
        df: Any,
        params: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Execute a plugin's calculate function."""
        info = self._plugins.get(name)
        if info is None or info.calculate_fn is None:
            return None
        try:
            return info.calculate_fn(df, **(params or {}))
        except Exception:
            return None

    def start_watching(self, scan_interval: float = 5.0) -> None:
        """Enable periodic change detection (hot-reload mode)."""
        self._watching = True
        self._scan_interval = scan_interval

    def stop_watching(self) -> None:
        """Disable periodic change detection."""
        self._watching = False

    def tick(self) -> List[str]:
        """Call periodically to check for file changes.

        Only performs a scan if enough time has elapsed since the last scan
        and watching is enabled. Returns list of reloaded plugin names.
        """
        if not self._watching:
            return []
        now = time.time()
        if now - self._last_scan_time < self._scan_interval:
            return []
        self._last_scan_time = now
        return self.reload_changed()

    @property
    def plugin_count(self) -> int:
        return len(self._plugins)

    @property
    def is_watching(self) -> bool:
        return self._watching
