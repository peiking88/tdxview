"""
Cache layer — MemoryCache (LRU + TTL), DiskCache, and CacheManager.

CacheManager provides a two-tier lookup: memory first, then disk.
"""

import hashlib
import json
import os
import pickle
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Optional

from app.config.settings import get_settings


# ---------------------------------------------------------------------------
# Public helper
# ---------------------------------------------------------------------------


def generate_cache_key(prefix: str, params: dict) -> str:
    """Deterministic cache key from prefix + sorted params."""
    raw = json.dumps({"prefix": prefix, **params}, sort_keys=True)
    return f"{prefix}:{hashlib.md5(raw.encode()).hexdigest()}"


# ---------------------------------------------------------------------------
# MemoryCache (LRU + TTL)
# ---------------------------------------------------------------------------


class MemoryCache:
    """In-memory LRU cache with per-item TTL."""

    def __init__(
        self,
        max_size_mb: int = 100,
        default_ttl: int = 300,
        max_items: int = 1000,
    ):
        self._max_bytes = max_size_mb * 1024 * 1024
        self._default_ttl = default_ttl
        self._max_items = max_items
        self._store: OrderedDict[str, tuple[float, Any, int]] = OrderedDict()
        self._sizes: dict[str, int] = {}

    def _item_size(self, value: Any) -> int:
        try:
            return len(pickle.dumps(value))
        except Exception:
            return sys.getsizeof(value)

    def get(self, key: str) -> Optional[Any]:
        if key not in self._store:
            return None
        expires_at, value, _ = self._store[key]
        if time.time() > expires_at:
            self._remove_key(key)
            return None
        self._store.move_to_end(key)
        return value

    def set(self, key: str, value: Any, ttl: Optional[int] = None, size: Optional[int] = None) -> None:
        expires_at = time.time() + (ttl if ttl is not None else self._default_ttl)
        item_size = size if size is not None else self._item_size(value)
        self._store[key] = (expires_at, value, item_size)
        self._sizes[key] = item_size
        self._store.move_to_end(key)
        self._evict()

    def _remove_key(self, key: str) -> None:
        if key in self._store:
            del self._store[key]
        self._sizes.pop(key, None)

    def delete(self, key: str) -> bool:
        if key in self._store:
            self._remove_key(key)
            return True
        return False

    def clear(self) -> None:
        self._store.clear()

    @property
    def count(self) -> int:
        return len(self._store)

    @property
    def size(self) -> int:
        return sum(self._sizes.values())

    def _evict(self) -> None:
        while len(self._store) > self._max_items:
            k, _ = self._store.popitem(last=False)
            self._sizes.pop(k, None)
        while self.size > self._max_bytes and self._store:
            self._remove_key(next(iter(self._store)))


# ---------------------------------------------------------------------------
# DiskCache
# ---------------------------------------------------------------------------


class DiskCache:
    """File-based cache with TTL, stored as JSON."""

    def __init__(
        self,
        cache_dir: str = "",
        default_ttl: int = 300,
        compression: bool = True,
    ):
        if cache_dir:
            self._cache_dir = Path(cache_dir)
        else:
            settings = get_settings()
            self._cache_dir = Path(settings.database.cache_dir)
        self._default_ttl = default_ttl
        self._compression = compression
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        safe = hashlib.md5(key.encode()).hexdigest()
        return self._cache_dir / f"{safe}.cache"

    def get(self, key: str) -> Optional[Any]:
        p = self._path(key)
        if not p.exists():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if time.time() > data.get("expires_at", 0):
                p.unlink(missing_ok=True)
                return None
            return data["value"]
        except Exception:
            return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        p = self._path(key)
        expires_at = time.time() + (ttl if ttl is not None else self._default_ttl)
        p.write_text(
            json.dumps({"expires_at": expires_at, "value": value}, ensure_ascii=False),
            encoding="utf-8",
        )

    def delete(self, key: str) -> bool:
        p = self._path(key)
        if p.exists():
            p.unlink()
            return True
        return False

    def clear(self) -> None:
        for f in self._cache_dir.glob("*.cache"):
            f.unlink(missing_ok=True)

    @property
    def count(self) -> int:
        return len(list(self._cache_dir.glob("*.cache")))

    @property
    def size(self) -> int:
        return sum(f.stat().st_size for f in self._cache_dir.glob("*.cache"))


# ---------------------------------------------------------------------------
# CacheManager (two-tier: memory → disk)
# ---------------------------------------------------------------------------


class CacheManager:
    """Unified cache that checks memory first, then falls back to disk."""

    def __init__(self):
        settings = get_settings()
        self.memory = MemoryCache(
            max_size_mb=settings.cache.memory_max_size_mb,
            default_ttl=settings.cache.memory_default_ttl,
        )
        self.disk = DiskCache(
            cache_dir=settings.database.cache_dir,
            default_ttl=settings.cache.query_ttl if settings.cache.disk_enabled else 0,
            compression=settings.cache.disk_compression,
        )
        self._query_enabled = settings.cache.query_enabled

    def get(self, key: str) -> Optional[Any]:
        if not self._query_enabled:
            return None
        value = self.memory.get(key)
        if value is not None:
            return value
        value = self.disk.get(key)
        if value is not None:
            self.memory.set(key, value)
            return value
        return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        if not self._query_enabled:
            return
        self.memory.set(key, value, ttl=ttl)
        self.disk.set(key, value, ttl=ttl)

    def delete(self, key: str) -> bool:
        m = self.memory.delete(key)
        d = self.disk.delete(key)
        return m or d

    def clear(self) -> None:
        self.memory.clear()
        self.disk.clear()
