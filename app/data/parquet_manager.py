"""
Parquet file manager — supports multiple data types with partitioned storage.
"""

from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from app.config.settings import get_settings


class ParquetManager:
    """Manages Parquet file storage for market data, partitioned by data type."""

    def __init__(self, parquet_dir: Optional[str] = None):
        settings = get_settings()
        self._parquet_dir = Path(parquet_dir or settings.database.parquet_dir)
        self._parquet_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Path resolution
    # ------------------------------------------------------------------

    def _resolve_path(self, data_type: str, symbol: str, date: Optional[str] = None) -> Path:
        """Compute Parquet file path based on data type and optional date partition."""
        type_dir = self._parquet_dir / data_type

        if data_type == "history" and date is not None:
            parts = date.split("-")
            subdir = type_dir.joinpath(parts[0], parts[1])
        elif data_type == "tick" and date is not None:
            subdir = type_dir / date
        else:
            subdir = type_dir

        subdir.mkdir(parents=True, exist_ok=True)
        return subdir / f"{symbol}.parquet"

    def _legacy_path(self, symbol: str, date: Optional[str] = None) -> Optional[Path]:
        """Try to locate a file written with the old path layout (no data_type prefix)."""
        if date is not None:
            parts = date.split("-")
            path = self._parquet_dir.joinpath(*parts) / f"{symbol}.parquet"
        else:
            matches = sorted(self._parquet_dir.rglob(f"{symbol}.parquet"), reverse=True)
            # Only return if the match is directly under the parquet root (no data_type dir)
            for m in matches:
                try:
                    m.relative_to(self._parquet_dir)
                    parts = m.relative_to(self._parquet_dir).parts
                    # Old layout: {year}/{month}/{symbol}.parquet (3 parts)
                    if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
                        return m
                except ValueError:
                    continue
            return None
        return path if path.exists() else None

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def save(
        self,
        df: pd.DataFrame,
        symbol: str,
        date: Optional[str] = None,
        data_type: str = "history",
    ) -> Path:
        """Save a DataFrame as a Parquet file, partitioned by data type and date."""
        path = self._resolve_path(data_type, symbol, date)
        df.to_parquet(path, engine="pyarrow", compression="snappy", index=False)
        return path

    def load(
        self,
        symbol: str,
        date: Optional[str] = None,
        data_type: str = "history",
    ) -> Optional[pd.DataFrame]:
        """Load a Parquet file. Falls back to legacy path if new path not found."""
        path = self._resolve_path(data_type, symbol, date)
        if path.exists():
            return pd.read_parquet(path, engine="pyarrow")

        # Fallback: try legacy path (no data_type prefix)
        legacy = self._legacy_path(symbol, date)
        if legacy is not None and legacy.exists():
            return pd.read_parquet(legacy, engine="pyarrow")

        # For history without date: search newest across partitions
        if data_type == "history" and date is None:
            type_dir = self._parquet_dir / data_type
            matches = sorted(type_dir.rglob(f"{symbol}.parquet"), reverse=True)
            if matches:
                return pd.read_parquet(matches[0], engine="pyarrow")
            # Legacy fallback
            matches = sorted(self._parquet_dir.rglob(f"{symbol}.parquet"), reverse=True)
            for m in matches:
                parts = m.relative_to(self._parquet_dir).parts
                if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
                    return pd.read_parquet(m, engine="pyarrow")

        return None

    def delete(
        self,
        symbol: str,
        date: Optional[str] = None,
        data_type: str = "history",
    ) -> bool:
        """Delete Parquet file(s) for a symbol and data type."""
        deleted = False

        if date is not None:
            path = self._resolve_path(data_type, symbol, date)
            if path.exists():
                path.unlink()
                deleted = True
        else:
            type_dir = self._parquet_dir / data_type
            for p in type_dir.rglob(f"{symbol}.parquet"):
                p.unlink()
                deleted = True

        return deleted

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def list_symbols(self, data_type: str = "history") -> List[str]:
        """List all available symbols for a given data type."""
        seen = set()
        type_dir = self._parquet_dir / data_type
        if type_dir.exists():
            for p in type_dir.rglob("*.parquet"):
                seen.add(p.stem)
        return sorted(seen)

    def list_data_types(self, symbol: Optional[str] = None) -> List[str]:
        """List data types that have stored data, optionally filtered by symbol."""
        result = []
        for dtype_dir in sorted(self._parquet_dir.iterdir()):
            if not dtype_dir.is_dir():
                continue
            if symbol is not None:
                if any(dtype_dir.rglob(f"{symbol}.parquet")):
                    result.append(dtype_dir.name)
            else:
                if any(dtype_dir.rglob("*.parquet")):
                    result.append(dtype_dir.name)
        return result

    def get_parquet_info(self, symbol: str, data_type: str) -> Optional[Dict]:
        """Get file info for a symbol's data type (size, path)."""
        type_dir = self._parquet_dir / data_type
        matches = sorted(type_dir.rglob(f"{symbol}.parquet"), reverse=True)
        if matches:
            p = matches[0]
            stat = p.stat()
            return {"path": str(p), "size_bytes": stat.st_size}
        return None
