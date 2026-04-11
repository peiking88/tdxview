"""
Parquet file manager.
"""

from pathlib import Path
from typing import List, Optional

import pandas as pd

from app.config.settings import get_settings


class ParquetManager:
    """Manages Parquet file storage for market data."""

    def __init__(self, parquet_dir: Optional[str] = None):
        settings = get_settings()
        self._parquet_dir = Path(parquet_dir or settings.database.parquet_dir)
        self._parquet_dir.mkdir(parents=True, exist_ok=True)

    def save(self, df: pd.DataFrame, symbol: str, date: Optional[str] = None) -> Path:
        """Save a DataFrame as a Parquet file, partitioned by date/symbol."""
        if date is not None:
            parts = date.split("-")
            subdir = self._parquet_dir.joinpath(*parts)
        else:
            subdir = self._parquet_dir
        subdir.mkdir(parents=True, exist_ok=True)
        path = subdir / f"{symbol}.parquet"
        df.to_parquet(path, engine="pyarrow", compression="snappy", index=False)
        return path

    def load(self, symbol: str, date: Optional[str] = None) -> Optional[pd.DataFrame]:
        """Load a Parquet file for a given symbol and optional date partition."""
        if date is not None:
            parts = date.split("-")
            path = self._parquet_dir.joinpath(*parts) / f"{symbol}.parquet"
            if path.exists():
                return pd.read_parquet(path, engine="pyarrow")
        else:
            matches = sorted(self._parquet_dir.rglob(f"{symbol}.parquet"), reverse=True)
            if matches:
                return pd.read_parquet(matches[0], engine="pyarrow")
        return None

    def list_symbols(self) -> List[str]:
        """List all available symbols (recursive search across partitions)."""
        seen = set()
        for p in self._parquet_dir.rglob("*.parquet"):
            seen.add(p.stem)
        return sorted(seen)

    def delete(self, symbol: str, date: Optional[str] = None) -> bool:
        """Delete a Parquet file."""
        if date is not None:
            parts = date.split("-")
            path = self._parquet_dir.joinpath(*parts) / f"{symbol}.parquet"
            if path.exists():
                path.unlink()
                return True
        else:
            deleted = False
            for p in self._parquet_dir.rglob(f"{symbol}.parquet"):
                p.unlink()
                deleted = True
            return deleted
        return False
