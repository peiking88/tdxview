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
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from app.config.settings import get_settings
from app.data.cache import CacheManager, generate_cache_key
from app.data.database import DatabaseManager
from app.data.models.import_record import DataType, ImportRecordModel, ImportStatus
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
    # TTL mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _ttl_for_type(data_type: str) -> int:
        return {
            "history": 3600,
            "realtime": 60,
            "tick": 300,
            "financial": 3600,
            "f10": 3600,
            "basic": 3600,
        }.get(data_type, 300)

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

        if use_cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return pd.DataFrame(cached)

        df = self.source.fetch_history(
            stock_list=symbols,
            start_date=start_date,
            end_date=end_date,
            period=period,
            dividend_type=dividend_type,
        )

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
    # Financial data (with cache)
    # ------------------------------------------------------------------

    def get_financial(self, stock_code: str, use_cache: bool = True) -> pd.DataFrame:
        """Get financial statements, with cache."""
        cache_key = generate_cache_key("financial", {"code": stock_code})

        if use_cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return pd.DataFrame(cached)

        df = self.source.fetch_financial(stock_code=stock_code)

        if use_cache and not df.empty:
            df = df.loc[:, ~df.columns.duplicated()]
            self._cache.set(
                cache_key,
                json.loads(df.to_json(orient="columns", date_format="iso")),
                ttl=self._ttl_for_type("financial"),
            )

        return df

    # ------------------------------------------------------------------
    # F10 data (with cache)
    # ------------------------------------------------------------------

    def get_f10(
        self,
        stock_code: str,
        sections: Optional[List[str]] = None,
        use_cache: bool = True,
    ) -> Dict[str, pd.DataFrame]:
        """Get F10 company information, with cache."""
        cache_key = generate_cache_key("f10", {
            "code": stock_code,
            "sections": sorted(sections) if sections else [],
        })

        if use_cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return {k: pd.DataFrame(v) for k, v in cached.items()}

        result = self.source.fetch_f10(stock_code=stock_code, sections=sections)

        if use_cache and result:
            serialized = {
                k: json.loads(v.to_json(orient="columns", date_format="iso"))
                for k, v in result.items()
            }
            self._cache.set(cache_key, serialized, ttl=self._ttl_for_type("f10"))

        return result

    # ------------------------------------------------------------------
    # Basic / ex-rights data (with cache)
    # ------------------------------------------------------------------

    def get_basic(
        self,
        stock_code: str,
        date: Optional[str] = None,
        use_cache: bool = True,
    ) -> pd.DataFrame:
        """Get ex-rights/ex-dividend data, with cache."""
        cache_key = generate_cache_key("basic", {"code": stock_code, "date": date or "latest"})

        if use_cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return pd.DataFrame(cached)

        df = self.source.fetch_basic(stock_code=stock_code, date=date)

        if use_cache and not df.empty:
            df = df.loc[:, ~df.columns.duplicated()]
            self._cache.set(
                cache_key,
                json.loads(df.to_json(orient="columns", date_format="iso")),
                ttl=self._ttl_for_type("basic"),
            )

        return df

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
        existing = self._db.fetch_one(
            "SELECT id FROM data_sources WHERE name = ? AND type = ?", [name, source_type]
        )
        if existing:
            return existing[0]
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
        data_type: str = "history",
    ) -> Path:
        """Save a DataFrame to Parquet storage."""
        return self._parquet.save(df, symbol, date=date, data_type=data_type)

    def load_from_parquet(
        self,
        symbol: str,
        date: Optional[str] = None,
        data_type: str = "history",
    ) -> Optional[pd.DataFrame]:
        """Load a DataFrame from Parquet storage."""
        return self._parquet.load(symbol, date=date, data_type=data_type)

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
                path = self._parquet.save(group, str(symbol), start_date[:7], data_type="history")
                results[str(symbol)] = path
        else:
            symbol = symbols[0] if len(symbols) == 1 else "multi"
            path = self._parquet.save(df, symbol, start_date[:7], data_type="history")
            results[symbol] = path

        return results

    # ------------------------------------------------------------------
    # Import workflow (unified entry for all data types)
    # ------------------------------------------------------------------

    def _fetch_by_type(self, symbol: str, data_type: str, **kwargs: Any) -> Any:
        """Fetch data from source based on data type."""
        if data_type == "history":
            return self.source.fetch_history(
                stock_list=[symbol],
                start_date=kwargs.get("start_date", ""),
                end_date=kwargs.get("end_date", ""),
                period=kwargs.get("period", "1d"),
                dividend_type=kwargs.get("dividend_type", "front"),
            )
        elif data_type == "financial":
            return self.source.fetch_financial(stock_code=symbol)
        elif data_type == "f10":
            return self.source.fetch_f10(
                stock_code=symbol,
                sections=kwargs.get("sections"),
            )
        elif data_type == "basic":
            return self.source.fetch_basic(
                stock_code=symbol,
                date=kwargs.get("date"),
            )
        elif data_type == "tick":
            return self.source.fetch_tick(
                stock_code=symbol,
                date=kwargs.get("date"),
            )
        elif data_type == "realtime":
            return self.source.fetch_realtime(stock_list=[symbol])
        else:
            raise ValueError(f"Unknown data type: {data_type}")

    def import_data(
        self,
        symbol: str,
        data_type: str,
        **kwargs: Any,
    ) -> ImportRecordModel:
        """Import data: fetch → save Parquet → write cache → upsert record."""
        start_time = time.time()
        record = ImportRecordModel(symbol=symbol, data_type=DataType(data_type))

        try:
            data = self._fetch_by_type(symbol, data_type, **kwargs)

            # Handle F10 which returns dict of DataFrames
            if data_type == "f10" and isinstance(data, dict):
                # Merge all F10 sections into one DataFrame for storage
                frames = []
                for section, df in data.items():
                    if isinstance(df, pd.DataFrame) and not df.empty:
                        df = df.copy()
                        df.insert(0, "section", section)
                        frames.append(df)
                if frames:
                    combined = pd.concat(frames, ignore_index=True)
                else:
                    combined = pd.DataFrame()

                if not combined.empty:
                    path = self._parquet.save(combined, symbol, data_type="f10")
                    record.parquet_path = str(path)
                    record.record_count = len(combined)
                    record.file_size_bytes = path.stat().st_size

                # Cache the original dict form
                serialized = {
                    k: json.loads(v.to_json(orient="columns", date_format="iso"))
                    for k, v in data.items() if isinstance(v, pd.DataFrame)
                }
                cache_key = generate_cache_key("f10", {
                    "code": symbol,
                    "sections": sorted(kwargs.get("sections", [])),
                })
                self._cache.set(cache_key, serialized, ttl=self._ttl_for_type("f10"))

            elif isinstance(data, pd.DataFrame):
                if not data.empty:
                    date_partition = kwargs.get("date") or kwargs.get("start_date", "")[:7] or None
                    path = self._parquet.save(data, symbol, date=date_partition, data_type=data_type)
                    record.parquet_path = str(path)
                    record.record_count = len(data)
                    record.file_size_bytes = path.stat().st_size

                    cache_key = generate_cache_key(data_type, self._cache_params(symbol, data_type, **kwargs))
                    self._cache.set(
                        cache_key,
                        json.loads(data.to_json(orient="columns", date_format="iso")),
                        ttl=self._ttl_for_type(data_type),
                    )

                # Extract date range for history/tick
                if data_type in ("history", "tick") and not data.empty and "date" in data.columns:
                    dates = pd.to_datetime(data["date"])
                    record.start_date = str(dates.min().date())
                    record.end_date = str(dates.max().date())
                elif data_type == "history":
                    record.start_date = kwargs.get("start_date")
                    record.end_date = kwargs.get("end_date")

            record.status = ImportStatus.SUCCESS

        except Exception as e:
            record.status = ImportStatus.FAILED
            record.error_message = str(e)

        finally:
            record.import_duration_ms = int((time.time() - start_time) * 1000)
            record.imported_at = datetime.now().isoformat()
            self._upsert_import_record(record)

        return record

    @staticmethod
    def _cache_params(symbol: str, data_type: str, **kwargs: Any) -> dict:
        """Build cache key params for a data type."""
        if data_type == "history":
            return {
                "symbols": [symbol],
                "start": kwargs.get("start_date", ""),
                "end": kwargs.get("end_date", ""),
                "period": kwargs.get("period", "1d"),
                "dividend": kwargs.get("dividend_type", "front"),
            }
        elif data_type == "tick":
            return {"code": symbol, "date": kwargs.get("date", "latest")}
        elif data_type == "realtime":
            return {"symbols": [symbol]}
        elif data_type == "financial":
            return {"code": symbol}
        elif data_type == "basic":
            return {"code": symbol, "date": kwargs.get("date", "latest")}
        else:
            return {"symbol": symbol}

    # ------------------------------------------------------------------
    # Import record persistence
    # ------------------------------------------------------------------

    def _upsert_import_record(self, record: ImportRecordModel) -> None:
        """Insert or update an import record in DuckDB."""
        self._db.execute(
            """INSERT OR REPLACE INTO data_imports
               (symbol, data_type, status, record_count, start_date, end_date,
                parquet_path, file_size_bytes, error_message, import_duration_ms, imported_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                record.symbol,
                record.data_type.value if isinstance(record.data_type, DataType) else record.data_type,
                record.status.value if isinstance(record.status, ImportStatus) else record.status,
                record.record_count,
                record.start_date,
                record.end_date,
                record.parquet_path,
                record.file_size_bytes,
                record.error_message,
                record.import_duration_ms,
                record.imported_at,
            ],
        )
        self._db.connection.commit()

    def get_import_status(
        self,
        symbol: Optional[str] = None,
        data_type: Optional[str] = None,
    ) -> List[ImportRecordModel]:
        """Query import records, optionally filtered."""
        conditions = []
        params: list = []
        if symbol is not None:
            conditions.append("symbol = ?")
            params.append(symbol)
        if data_type is not None:
            conditions.append("data_type = ?")
            params.append(data_type)

        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = self._db.fetch_all(
            f"SELECT symbol, data_type, status, record_count, start_date, end_date, "
            f"parquet_path, file_size_bytes, error_message, import_duration_ms, imported_at "
            f"FROM data_imports{where} ORDER BY imported_at DESC",
            params,
        )

        results = []
        for r in rows:
            results.append(self._row_to_record(r))
        return results

    def get_last_import(self, symbol: str, data_type: str) -> Optional[ImportRecordModel]:
        """Get the latest import record for a symbol and data type."""
        rows = self._db.fetch_all(
            "SELECT symbol, data_type, status, record_count, start_date, end_date, "
            "parquet_path, file_size_bytes, error_message, import_duration_ms, imported_at "
            "FROM data_imports WHERE symbol = ? AND data_type = ?",
            [symbol, data_type],
        )
        if not rows:
            return None
        return self._row_to_record(rows[0])

    @staticmethod
    def _row_to_record(r) -> ImportRecordModel:
        """Convert a DB row to ImportRecordModel, handling DuckDB date types."""
        return ImportRecordModel(
            symbol=r[0],
            data_type=DataType(r[1]),
            status=ImportStatus(r[2]),
            record_count=r[3],
            start_date=str(r[4]) if r[4] is not None else None,
            end_date=str(r[5]) if r[5] is not None else None,
            parquet_path=r[6],
            file_size_bytes=r[7],
            error_message=r[8],
            import_duration_ms=r[9],
            imported_at=str(r[10]) if r[10] else None,
        )

    # ------------------------------------------------------------------
    # Incremental import
    # ------------------------------------------------------------------

    def incremental_import(
        self,
        symbol: str,
        data_type: str,
        **kwargs: Any,
    ) -> ImportRecordModel:
        """Incremental import: only fetch new data since last import."""
        last = self.get_last_import(symbol, data_type)

        if last is None:
            return self.import_data(symbol, data_type, **kwargs)

        if data_type == "history" and last.end_date:
            next_day = (
                datetime.strptime(last.end_date, "%Y-%m-%d") + timedelta(days=1)
            ).strftime("%Y-%m-%d")
            today = datetime.now().strftime("%Y-%m-%d")
            if next_day > today:
                return last  # Already up to date
            kwargs.setdefault("start_date", next_day)
            kwargs.setdefault("end_date", today)
            return self.import_data(symbol, data_type, **kwargs)

        # For non-time-series types, re-import (overwrite)
        return self.import_data(symbol, data_type, **kwargs)

    # ------------------------------------------------------------------
    # Re-import (clear + full import)
    # ------------------------------------------------------------------

    def reimport_data(
        self,
        symbol: str,
        data_type: str,
        **kwargs: Any,
    ) -> ImportRecordModel:
        """Re-import: clear Parquet + record, then full import."""
        self._parquet.delete(symbol, data_type=data_type)
        self._db.execute(
            "DELETE FROM data_imports WHERE symbol = ? AND data_type = ?",
            [symbol, data_type],
        )
        self._db.connection.commit()
        return self.import_data(symbol, data_type, **kwargs)

    # ------------------------------------------------------------------
    # Source health check
    # ------------------------------------------------------------------

    def check_source_health(self) -> Dict[str, Any]:
        """Check whether the data source is reachable."""
        connected = self.source.validate_connection()
        now = datetime.now().isoformat()
        self._db.execute(
            "UPDATE data_sources SET last_checked = ?, error_count = 0 WHERE type = 'tdxdata'",
            [now],
        )
        self._db.connection.commit()
        return {
            "connected": connected,
            "checked_at": now,
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
        """Execute a named query method for each symbol and collect results."""
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
