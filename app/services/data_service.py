"""
Data service — orchestrates data fetching, caching, storage, and source management.

This is the primary business-logic layer that Streamlit components and other
services call. It coordinates:
  1. Cache lookup (memory → disk)
  2. DuckDB metadata queries
  3. Parquet file reads/writes
  4. Remote data fetching via TdxDataSource
"""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from app.config.settings import get_settings
from app.data.cache import CacheManager, generate_cache_key
from app.data.database import DatabaseManager
from app.data.parquet_manager import ParquetManager
from app.data.sources.tdxdata_source import TdxDataSource


class DataService:
    """High-level data access service."""

    def __init__(self):
        settings = get_settings()
        self._cache = CacheManager()
        self._db = DatabaseManager()
        self._parquet = ParquetManager()
        self._source: Optional[TdxDataSource] = None
        self._source_config = {
            "timeout": settings.tdxdata.timeout,
            "retry_count": settings.tdxdata.retry_count,
        }

    @property
    def source(self) -> TdxDataSource:
        """Lazy-initialize the data source."""
        if self._source is None:
            self._source = TdxDataSource(timeout=self._source_config["timeout"])
        return self._source

    # ------------------------------------------------------------------
    # Historical kline
    # ------------------------------------------------------------------

    def get_history(
        self,
        symbols: List[str],
        start_date: str,
        end_date: str,
        period: str = "1d",
        dividend_type: str = "front",
        use_cache: bool = True,
    ) -> pd.DataFrame:
        """Get historical kline data, checking cache first."""
        cache_key = generate_cache_key("history", {
            "symbols": sorted(symbols),
            "start": start_date,
            "end": end_date,
            "period": period,
            "dividend": dividend_type,
        })

        # 1. Memory / disk cache
        if use_cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return pd.DataFrame(cached)

        # 2. Fetch from source
        df = self.source.fetch_history(
            stock_list=symbols,
            start_date=start_date,
            end_date=end_date,
            period=period,
            dividend_type=dividend_type,
        )

        # 3. Store in cache
        if use_cache and not df.empty:
            self._cache.set(cache_key, json.loads(df.to_json(orient="columns", date_format="iso")))

        return df

    # ------------------------------------------------------------------
    # Realtime quotes
    # ------------------------------------------------------------------

    def get_realtime(
        self,
        stock_list: List[str],
        use_cache: bool = True,
        cache_ttl: int = 60,
    ) -> pd.DataFrame:
        """Get realtime quotes. Short TTL by default (60s)."""
        cache_key = generate_cache_key("realtime", {"symbols": sorted(stock_list)})

        if use_cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return pd.DataFrame(cached)

        df = self.source.fetch_realtime(stock_list=stock_list)

        if use_cache and not df.empty:
            df = df.loc[:, ~df.columns.duplicated()]
            self._cache.set(cache_key, json.loads(df.to_json(orient="columns", date_format="iso")), ttl=cache_ttl)

        return df

    # ------------------------------------------------------------------
    # Tick data
    # ------------------------------------------------------------------

    def get_tick(
        self,
        stock_code: str,
        date: Optional[str] = None,
        use_cache: bool = True,
    ) -> pd.DataFrame:
        """Get tick-by-tick data for a single stock."""
        cache_key = generate_cache_key("tick", {
            "code": stock_code,
            "date": date or "latest",
        })

        if use_cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return pd.DataFrame(cached)

        df = self.source.fetch_tick(stock_code=stock_code, date=date)

        if use_cache and not df.empty:
            self._cache.set(cache_key, json.loads(df.to_json(orient="columns", date_format="iso")), ttl=300)

        return df

    # ------------------------------------------------------------------
    # Financial data
    # ------------------------------------------------------------------

    def get_financial(self, stock_code: str) -> pd.DataFrame:
        return self.source.fetch_financial(stock_code=stock_code)

    def get_f10(
        self,
        stock_code: str,
        sections: Optional[List[str]] = None,
    ) -> Dict[str, pd.DataFrame]:
        return self.source.fetch_f10(stock_code=stock_code, sections=sections)

    def get_basic(
        self,
        stock_code: str,
        date: Optional[str] = None,
    ) -> pd.DataFrame:
        return self.source.fetch_basic(stock_code=stock_code, date=date)

    # ------------------------------------------------------------------
    # Local / hybrid data
    # ------------------------------------------------------------------

    def get_local(
        self,
        stock_code: str,
        period: str = "1d",
        tdxdir: Optional[str] = None,
        dividend_type: str = "none",
    ) -> pd.DataFrame:
        return self.source.fetch_local(
            stock_code=stock_code,
            period=period,
            tdxdir=tdxdir,
            dividend_type=dividend_type,
        )

    def get_hybrid(
        self,
        stock_code: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        period: str = "1d",
        tdxdir: Optional[str] = None,
        dividend_type: str = "none",
    ) -> pd.DataFrame:
        return self.source.fetch_hybrid(
            stock_code=stock_code,
            start_date=start_date,
            end_date=end_date,
            period=period,
            tdxdir=tdxdir,
            dividend_type=dividend_type,
        )

    # ------------------------------------------------------------------
    # Data source configuration CRUD
    # ------------------------------------------------------------------

    def list_data_sources(self) -> List[Dict[str, Any]]:
        """List all configured data sources."""
        rows = self._db.fetch_all("SELECT id, name, type, config, enabled, priority FROM data_sources ORDER BY priority")
        return [
            {"id": r[0], "name": r[1], "type": r[2],
             "config": json.loads(r[3]) if isinstance(r[3], str) else r[3],
             "enabled": r[4], "priority": r[5]}
            for r in rows
        ]

    def get_data_source(self, source_id: int) -> Optional[Dict[str, Any]]:
        """Get a single data source by ID."""
        row = self._db.fetch_one(
            "SELECT id, name, type, config, enabled, priority FROM data_sources WHERE id = ?",
            [source_id],
        )
        if not row:
            return None
        return {
            "id": row[0], "name": row[1], "type": row[2],
            "config": json.loads(row[3]) if isinstance(row[3], str) else row[3],
            "enabled": row[4], "priority": row[5],
        }

    def add_data_source(
        self,
        name: str,
        source_type: str,
        config: Dict[str, Any],
        priority: int = 1,
        enabled: bool = True,
    ) -> int:
        """Add a new data source configuration. Returns the new ID."""
        self._db.execute(
            "INSERT INTO data_sources (name, type, config, priority, enabled) VALUES (?, ?, ?, ?, ?)",
            [name, source_type, json.dumps(config, ensure_ascii=False), priority, enabled],
        )
        self._db.connection.commit()
        row = self._db.fetch_one("SELECT id FROM data_sources WHERE name = ? ORDER BY id DESC", [name])
        return row[0] if row else -1

    def update_data_source(
        self,
        source_id: int,
        name: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        enabled: Optional[bool] = None,
        priority: Optional[int] = None,
    ) -> bool:
        """Update an existing data source."""
        updates = []
        params = []
        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if config is not None:
            updates.append("config = ?")
            params.append(json.dumps(config, ensure_ascii=False))
        if enabled is not None:
            updates.append("enabled = ?")
            params.append(enabled)
        if priority is not None:
            updates.append("priority = ?")
            params.append(priority)

        if not updates:
            return False

        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(source_id)
        self._db.execute(
            f"UPDATE data_sources SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        self._db.connection.commit()
        return True

    def delete_data_source(self, source_id: int) -> bool:
        """Delete a data source configuration."""
        self._db.execute("DELETE FROM data_sources WHERE id = ?", [source_id])
        self._db.connection.commit()
        return True

    # ------------------------------------------------------------------
    # Data storage to Parquet
    # ------------------------------------------------------------------

    def save_to_parquet(
        self,
        df: pd.DataFrame,
        symbol: str,
        date: Optional[str] = None,
    ) -> Path:
        """Save a DataFrame to Parquet storage."""
        return self._parquet.save(df, symbol, date)

    def load_from_parquet(
        self,
        symbol: str,
        date: Optional[str] = None,
    ) -> Optional[pd.DataFrame]:
        """Load a DataFrame from Parquet storage."""
        return self._parquet.load(symbol, date)

    # ------------------------------------------------------------------
    # Fetch & store workflow
    # ------------------------------------------------------------------

    def fetch_and_store(
        self,
        symbols: List[str],
        start_date: str,
        end_date: str,
        period: str = "1d",
        dividend_type: str = "front",
    ) -> Dict[str, Path]:
        """Fetch historical data and save each symbol to Parquet.

        Returns a mapping of symbol → Parquet file path.
        """
        df = self.get_history(
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            period=period,
            dividend_type=dividend_type,
            use_cache=False,
        )
        if df.empty:
            return {}

        results = {}
        if "stock_code" in df.columns:
            for symbol, group in df.groupby("stock_code"):
                path = self._parquet.save(group, str(symbol), start_date[:7])
                results[str(symbol)] = path
        else:
            symbol = symbols[0] if len(symbols) == 1 else "multi"
            path = self._parquet.save(df, symbol, start_date[:7])
            results[symbol] = path

        return results

    # ------------------------------------------------------------------
    # Source health check
    # ------------------------------------------------------------------

    def check_source_health(self) -> Dict[str, Any]:
        """Check whether the data source is reachable."""
        connected = self.source.validate_connection()
        return {
            "connected": connected,
            "checked_at": datetime.now().isoformat(),
        }

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def close(self):
        """Release all resources."""
        if self._source is not None:
            self._source.close()
        self._db.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ------------------------------------------------------------------
    # Performance: parallel queries
    # ------------------------------------------------------------------

    def parallel_get_history(
        self,
        symbols: List[str],
        start_date: str,
        end_date: str,
        period: str = "1d",
        dividend_type: str = "front",
        max_workers: int = 4,
    ) -> Dict[str, pd.DataFrame]:
        """Fetch historical data for multiple symbols in parallel.

        Returns a dict mapping symbol → DataFrame.
        """
        results: Dict[str, pd.DataFrame] = {}

        def _fetch_one(symbol: str) -> Tuple[str, pd.DataFrame]:
            df = self.get_history(
                symbols=[symbol],
                start_date=start_date,
                end_date=end_date,
                period=period,
                dividend_type=dividend_type,
            )
            return symbol, df

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_fetch_one, s): s for s in symbols}
            for future in as_completed(futures):
                try:
                    symbol, df = future.result()
                    results[symbol] = df
                except Exception:
                    symbol = futures[future]
                    results[symbol] = pd.DataFrame()

        return results

    def parallel_fetch_and_store(
        self,
        symbols: List[str],
        start_date: str,
        end_date: str,
        period: str = "1d",
        dividend_type: str = "front",
        max_workers: int = 4,
    ) -> Dict[str, Path]:
        """Fetch and store data for multiple symbols in parallel.

        Returns a dict mapping symbol → Parquet file path.
        """
        all_results: Dict[str, Path] = {}

        def _fetch_store_one(symbol: str) -> Dict[str, Path]:
            return self.fetch_and_store(
                symbols=[symbol],
                start_date=start_date,
                end_date=end_date,
                period=period,
                dividend_type=dividend_type,
            )

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_fetch_store_one, s): s for s in symbols}
            for future in as_completed(futures):
                try:
                    result = future.result()
                    all_results.update(result)
                except Exception:
                    pass

        return all_results

    def batch_query_symbols(
        self,
        symbols: List[str],
        query_fn_name: str = "get_history",
        **query_kwargs: Any,
    ) -> Dict[str, Any]:
        """Execute a named query method for each symbol and collect results.

        *query_fn_name* must be a method name on this class (e.g. "get_history",
        "get_realtime", "get_tick").

        Returns {symbol: result}.
        """
        fn = getattr(self, query_fn_name, None)
        if fn is None:
            raise ValueError(f"Unknown method: {query_fn_name}")

        results = {}
        for symbol in symbols:
            try:
                if query_fn_name == "get_history":
                    result = fn(symbols=[symbol], **query_kwargs)
                elif query_fn_name == "get_tick":
                    result = fn(stock_code=symbol, **query_kwargs)
                else:
                    result = fn(stock_list=[symbol], **query_kwargs)
                results[symbol] = result
            except Exception:
                results[symbol] = None
        return results

    def get_stats(self) -> Dict[str, Any]:
        """Return runtime statistics about the data service."""
        cache_stats = {
            "memory_count": self._cache.memory.count,
            "memory_size": self._cache.memory.size,
        }
        return {
            "source_connected": self._source is not None,
            "cache": cache_stats,
        }
