"""
Multi-level cache — in-memory LRU + disk cache.
"""

import hashlib
import json
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, Optional

from app.config.settings import get_settings


class MemoryCache:
    """Thread-unsafe LRU cache with TTL support."""

    def __init__(self, max_size_mb: int = 100, default_ttl: int = 300):
        self._max_bytes = max_size_mb * 1024 * 1024
        self._default_ttl = default_ttl
        self._store: OrderedDict[str, tuple] = OrderedDict()  # key -> (value, expire_at, size)

    def get(self, key: str) -> Optional[Any]:
        if key in self._store:
            value, expire_at, _ = self._store[key]
            if expire_at and time.time() > expire_at:
                del self._store[key]
                return None
            self._store.move_to_end(key)
            return value
        return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None, size: int = 0):
        if key in self._store:
            del self._store[key]
        expire_at = time.time() + (ttl or self._default_ttl)
        self._store[key] = (value, expire_at, size)
        self._evict()

    def delete(self, key: str):
        self._store.pop(key, None)

    def clear(self):
        self._store.clear()

    def _evict(self):
        total = sum(s for _, _, s in self._store.values())
        while total > self._max_bytes and self._store:
            _, (_, _, size) = self._store.popitem(last=False)
            total -= size

    @property
    def size(self) -> int:
        return sum(s for _, _, s in self._store.values())

    @property
    def count(self) -> int:
        return len(self._store)


class DiskCache:
    """File-based cache stored under the configured cache directory."""

    def __init__(self, cache_dir: Optional[str] = None, compression: bool = True):
        settings = get_settings()
        self._cache_dir = Path(cache_dir or settings.database.cache_dir) / "queries"
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._compression = compression

    @staticmethod
    def _key_to_path(key: str) -> Path:
        h = hashlib.md5(key.encode()).hexdigest()
        return Path(h[:2]) / f"{h}.json"

    def get(self, key: str) -> Optional[Dict]:
        path = self._cache_dir / self._key_to_path(key)
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("expires_at") and time.time() > data["expires_at"]:
                path.unlink(missing_ok=True)
                return None
            return data.get("value")
        return None

    def set(self, key: str, value: Dict, ttl: int = 3600):
        path = self._cache_dir / self._key_to_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "value": value,
            "expires_at": time.time() + ttl,
            "created_at": time.time(),
        }
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def delete(self, key: str):
        path = self._cache_dir / self._key_to_path(key)
        path.unlink(missing_ok=True)

    def clear(self):
        import shutil
        if self._cache_dir.exists():
            shutil.rmtree(self._cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)


class CacheManager:
    """Multi-level cache combining memory and disk caches."""

    def __init__(self):
        settings = get_settings()
        self.memory = MemoryCache(
            max_size_mb=settings.cache.memory_max_size_mb,
            default_ttl=settings.cache.memory_default_ttl,
        )
        self.disk = DiskCache()

    def get(self, key: str) -> Optional[Any]:
        """Try memory first, then disk."""
        result = self.memory.get(key)
        if result is not None:
            return result
        result = self.disk.get(key)
        if result is not None:
            self.memory.set(key, result)
            return result
        return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """Set in both memory and disk."""
        self.memory.set(key, value, ttl=ttl)
        if isinstance(value, (dict, list, str, int, float, bool)):
            self.disk.set(key, value, ttl=ttl or 3600)

    def delete(self, key: str):
        self.memory.delete(key)
        self.disk.delete(key)

    def clear(self):
        self.memory.clear()
        self.disk.clear()


def generate_cache_key(query_type: str, params: Dict) -> str:
    """Generate a standardized cache key."""
    param_str = json.dumps(params, sort_keys=True, ensure_ascii=False)
    h = hashlib.md5(param_str.encode()).hexdigest()
    return f"{query_type}:{h}"
