"""
Data service — orchestrates data fetching, DuckDB storage, and source management.

This is the primary business-logic layer that Streamlit components and other
services call. It coordinates:
  1. DuckDBStore lookup (local persistent storage)
  2. Remote data fetching via TdxDataSource (on miss)
"""

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from app.config.settings import get_settings
from app.data.database import DatabaseManager
from app.data.duckdb_store import DuckDBStore
from app.data.models.import_record import DataType, ImportRecordModel, ImportStatus
from app.data.sources.tdxdata_source import TdxDataSource


class DataService:
    """High-level data access service."""

    def __init__(self):
        settings = get_settings()
        self._db = DatabaseManager()
        self._store = DuckDBStore(self._db)
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

    @staticmethod
    def _map_dividend_type(dividend_type: str) -> str:
        return {"front": "qfq", "back": "hfq", "none": "none"}.get(dividend_type, "none")

    # ------------------------------------------------------------------
    # Data quality: cleaning & continuity
    # ------------------------------------------------------------------

    @staticmethod
    def _clean_kline_data(df: pd.DataFrame) -> pd.DataFrame:
        """Remove anomalous rows from kline data.

        For each numeric field (volume, OHLC), compute the median of
        positive values as the baseline, then keep rows within
        [median * 0.1, median * 10].  Also enforces high >= low.

        When multiple stock_codes are present, cleaning is applied per
        symbol to respect different price levels.
        """
        if df.empty:
            return df

        # Multi-symbol: clean each group independently
        if "stock_code" in df.columns:
            parts = []
            for _, group in df.groupby("stock_code"):
                parts.append(DataService._clean_single(group))
            if not parts:
                return df.iloc[:0]
            return pd.concat(parts, ignore_index=True)

        return DataService._clean_single(df)

    @staticmethod
    def _clean_single(df: pd.DataFrame) -> pd.DataFrame:
        """Clean a single-symbol kline DataFrame."""
        if df.empty:
            return df

        mask = pd.Series(True, index=df.index)

        # Volume: [median * 0.1, median * 10]
        if "volume" in df.columns:
            vol = pd.to_numeric(df["volume"], errors="coerce")
            median_vol = vol[vol > 0].median()
            if pd.notna(median_vol) and median_vol > 0:
                mask &= (vol >= median_vol * 0.1) & (vol <= median_vol * 10)

        # OHLC: gather all prices, compute unified median
        price_vals = []
        for col in ("open", "high", "low", "close"):
            if col in df.columns:
                vals = pd.to_numeric(df[col], errors="coerce")
                price_vals.extend(vals[vals > 0].dropna().tolist())
        if price_vals:
            median_price = pd.Series(price_vals).median()
            if pd.notna(median_price) and median_price > 0:
                lo = median_price * 0.1
                hi = median_price * 10
                for col in ("open", "high", "low", "close"):
                    if col in df.columns:
                        vals = pd.to_numeric(df[col], errors="coerce")
                        mask &= ((vals >= lo) & (vals <= hi)) | vals.isna()

        # High >= Low
        if "high" in df.columns and "low" in df.columns:
            high = pd.to_numeric(df["high"], errors="coerce")
            low = pd.to_numeric(df["low"], errors="coerce")
            mask &= (high >= low) | high.isna() | low.isna()

        return df.loc[mask].reset_index(drop=True)

    @staticmethod
    def check_continuity(df: pd.DataFrame) -> Dict[str, Any]:
        """Check data continuity and return a report.

        Returns dict with:
          - total: total row count
          - valid: rows passing all checks
          - issues: list of issue descriptions
          - date_gaps: list of (gap_start, gap_end, missing_days) tuples
        """
        report: Dict[str, Any] = {
            "total": len(df),
            "valid": len(df),
            "issues": [],
            "date_gaps": [],
        }
        if df.empty or "date" not in df.columns:
            return report

        dates = pd.to_datetime(df["date"]).sort_values().reset_index(drop=True)
        report["date_range"] = (str(dates.iloc[0].date()), str(dates.iloc[-1].date()))

        # 1. Date gaps (> 1 calendar day = missing trading day)
        if len(dates) > 1:
            diffs = dates.diff().dropna()
            large_gaps = diffs[diffs > pd.Timedelta(days=1)]
            for idx in large_gaps.index:
                gap_start = dates.iloc[idx - 1]
                gap_end = dates.iloc[idx]
                missing = (gap_end - gap_start).days - 1
                report["date_gaps"].append((
                    str(gap_start.date()), str(gap_end.date()), missing,
                ))
            if report["date_gaps"]:
                report["issues"].append(
                    f"发现 {len(report['date_gaps'])} 处大于1天的日期间隔"
                )

        # 2. OHLC relationship: high >= low
        ohlc_issues = 0
        if all(c in df.columns for c in ("high", "low")):
            bad = df[pd.to_numeric(df["high"], errors="coerce")
                     < pd.to_numeric(df["low"], errors="coerce")]
            ohlc_issues = len(bad)
        if ohlc_issues:
            report["issues"].append(f"{ohlc_issues} 行 high < low")
            report["valid"] -= ohlc_issues

        # 3. Duplicate dates
        if "date" in df.columns:
            dup_count = df["date"].duplicated().sum()
            if dup_count:
                report["issues"].append(f"{dup_count} 个重复日期")
                report["valid"] -= dup_count

        # 4. Negative volume
        if "volume" in df.columns:
            neg_vol = (pd.to_numeric(df["volume"], errors="coerce") < 0).sum()
            if neg_vol:
                report["issues"].append(f"{neg_vol} 行成交量为负")
                report["valid"] -= neg_vol

        return report

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
        use_cache: bool = False,
    ) -> pd.DataFrame:
        """获取历史 K 线数据，每次直接调 tdxdata 接口。"""
        df = self.source.fetch_history(
            stock_list=symbols,
            start_date=start_date,
            end_date=end_date,
            period=period,
            dividend_type=dividend_type,
        )
        df = self._clean_kline_data(df)
        if df.empty:
            return df
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            if "stock_code" in df.columns:
                df = df.drop_duplicates(subset=["stock_code", "date"], keep="last")
                df = df.sort_values(["stock_code", "date"]).reset_index(drop=True)
            else:
                df = df.sort_values("date").reset_index(drop=True)
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
        """Get realtime quotes. Returns from DuckDB if fresh enough."""
        fresh_parts = []
        stale_symbols = []

        for symbol in stock_list:
            stored = self._store.load(symbol, data_type="realtime")
            if stored is not None and not stored.empty:
                # Check freshness via updated_at
                updated_at = stored.get("updated_at")
                if updated_at is not None and len(updated_at) > 0:
                    try:
                        updated = pd.to_datetime(updated_at.iloc[0])
                        if (datetime.now() - updated.to_pydatetime()).total_seconds() < cache_ttl:
                            fresh_parts.append(stored)
                            continue
                    except (ValueError, TypeError):
                        pass
            stale_symbols.append(symbol)

        if not stale_symbols:
            return pd.concat(fresh_parts, ignore_index=True) if fresh_parts else pd.DataFrame()

        # Fetch stale/missing symbols
        df = self.source.fetch_realtime(stock_list=stale_symbols)

        if not df.empty:
            df = df.loc[:, ~df.columns.duplicated()]
            # Save each symbol
            if "stock_code" in df.columns:
                for _, row in df.iterrows():
                    sym = row.get("stock_code") or row.get("symbol") or row.get("code")
                    if sym:
                        single = pd.DataFrame([row])
                        self._store.save(single, str(sym), data_type="realtime")
            else:
                for symbol in stale_symbols:
                    self._store.save(df, symbol, data_type="realtime")

        if fresh_parts and not df.empty:
            return pd.concat(fresh_parts + [df], ignore_index=True)
        if fresh_parts:
            return pd.concat(fresh_parts, ignore_index=True)
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
        stored = self._store.load(stock_code, date=date, data_type="tick")
        if stored is not None and not stored.empty:
            return stored

        df = self.source.fetch_tick(stock_code=stock_code, date=date)

        if not df.empty:
            self._store.save(df, stock_code, date=date, data_type="tick")

        return df

    # ------------------------------------------------------------------
    # Financial data
    # ------------------------------------------------------------------

    def get_financial(self, stock_code: str, use_cache: bool = True) -> pd.DataFrame:
        """Get financial statements."""
        stored = self._store.load(stock_code, data_type="financial")
        if stored is not None and not stored.empty:
            return stored

        df = self.source.fetch_financial(stock_code=stock_code)

        if not df.empty:
            df = df.loc[:, ~df.columns.duplicated()]
            self._store.save(df, stock_code, data_type="financial")

        return df

    # ------------------------------------------------------------------
    # F10 data
    # ------------------------------------------------------------------

    def get_f10(
        self,
        stock_code: str,
        sections: Optional[List[str]] = None,
        use_cache: bool = True,
    ) -> Dict[str, pd.DataFrame]:
        """Get F10 company information."""
        stored = self._store.load(stock_code, data_type="f10")
        if stored is not None and not stored.empty:
            result = {}
            if "section" in stored.columns:
                for section, group in stored.groupby("section"):
                    result[str(section)] = group.drop(columns=["section"]).reset_index(drop=True)
            else:
                result["default"] = stored
            # Filter by requested sections
            if sections:
                result = {k: v for k, v in result.items() if k in sections}
            return result if result else {}

        result = self.source.fetch_f10(stock_code=stock_code, sections=sections)

        if result:
            frames = []
            for section, df in result.items():
                if isinstance(df, pd.DataFrame) and not df.empty:
                    df = df.copy()
                    df.insert(0, "section", section)
                    frames.append(df)
            if frames:
                combined = pd.concat(frames, ignore_index=True)
                self._store.save(combined, stock_code, data_type="f10")

        return result

    # ------------------------------------------------------------------
    # Basic / ex-rights data
    # ------------------------------------------------------------------

    def get_basic(
        self,
        stock_code: str,
        date: Optional[str] = None,
        use_cache: bool = True,
    ) -> pd.DataFrame:
        """Get ex-rights/ex-dividend data."""
        stored = self._store.load(stock_code, date=date, data_type="basic")
        if stored is not None and not stored.empty:
            return stored

        df = self.source.fetch_basic(stock_code=stock_code, date=date)

        if not df.empty:
            df = df.loc[:, ~df.columns.duplicated()]
            # Synthesize ex_date from year/month/day columns if missing
            if "ex_date" not in df.columns and all(c in df.columns for c in ("year", "month", "day")):
                df["ex_date"] = (
                    df["year"].astype(str) + "-" +
                    df["month"].astype(str).str.zfill(2) + "-" +
                    df["day"].astype(str).str.zfill(2)
                )
            self._store.save(df, stock_code, date=date, data_type="basic")

        return df

    def get_factor(
        self,
        stock_code: str,
        adjust: str = "qfq",
        use_cache: bool = True,
    ) -> pd.DataFrame:
        """Get adjustment factor data.

        Args:
            stock_code: stock code, e.g. "600519"
            adjust: "qfq" (前复权), "hfq" (后复权)
            use_cache: whether to use local storage

        Returns:
            DataFrame with factor data.
        """
        stored = self._store.load(stock_code, data_type="factor", dividend=adjust)
        if stored is not None and not stored.empty:
            return stored

        df = self.source.fetch_factor(stock_code=stock_code, adjust=adjust)

        if not df.empty:
            df = df.loc[:, ~df.columns.duplicated()]
            self._store.save(df, stock_code, data_type="factor", dividend=adjust)

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
    # Data storage
    # ------------------------------------------------------------------

    def save_to_store(
        self,
        df: pd.DataFrame,
        symbol: str,
        date: Optional[str] = None,
        data_type: str = "history",
        period: Optional[str] = None,
        dividend: Optional[str] = None,
    ) -> str:
        """Save a DataFrame to DuckDB storage. Returns storage key."""
        return self._store.save(df, symbol, date=date, data_type=data_type,
                                period=period, dividend=dividend)

    def load_from_store(
        self,
        symbol: str,
        date: Optional[str] = None,
        data_type: str = "history",
        period: Optional[str] = None,
        dividend: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Optional[pd.DataFrame]:
        """Load a DataFrame from DuckDB storage."""
        return self._store.load(symbol, date=date, data_type=data_type,
                                period=period, dividend=dividend,
                                start_date=start_date, end_date=end_date)

    # Backward-compatible aliases
    def save_to_parquet(self, df, symbol, date=None, data_type="history"):
        return self.save_to_store(df, symbol, date=date, data_type=data_type)

    def load_from_parquet(self, symbol, date=None, data_type="history"):
        return self.load_from_store(symbol, date=date, data_type=data_type)

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
    ) -> Dict[str, str]:
        """Fetch historical data and save each symbol to DuckDB.

        Returns a mapping of symbol → storage key.
        """
        dividend = self._map_dividend_type(dividend_type)
        df = self.source.fetch_history(
            stock_list=symbols,
            start_date=start_date,
            end_date=end_date,
            period=period,
            dividend_type=dividend_type,
        )

        df = self._clean_kline_data(df)

        if df.empty:
            return {}

        results = {}
        if "stock_code" in df.columns:
            for symbol, group in df.groupby("stock_code"):
                key = self._store.save(
                    group, str(symbol), start_date[:7], data_type="history",
                    period=period, dividend=dividend,
                )
                results[str(symbol)] = key
        else:
            symbol = symbols[0] if len(symbols) == 1 else "multi"
            key = self._store.save(
                df, symbol, start_date[:7], data_type="history",
                period=period, dividend=dividend,
            )
            results[symbol] = key

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
        """Import data: fetch → save to DuckDB → upsert record."""
        start_time = time.time()
        record = ImportRecordModel(symbol=symbol, data_type=DataType(data_type))

        try:
            data = self._fetch_by_type(symbol, data_type, **kwargs)

            # Handle F10 which returns dict of DataFrames
            if data_type == "f10" and isinstance(data, dict):
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
                    key = self._store.save(combined, symbol, data_type="f10")
                    record.storage_key = key
                    record.record_count = len(combined)

            elif isinstance(data, pd.DataFrame):
                if not data.empty:
                    date_partition = kwargs.get("date") or kwargs.get("start_date", "")[:7] or None
                    key = self._store.save(data, symbol, date=date_partition, data_type=data_type)
                    record.storage_key = key
                    record.record_count = len(data)

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

    # ------------------------------------------------------------------
    # Import record persistence
    # ------------------------------------------------------------------

    def _upsert_import_record(self, record: ImportRecordModel) -> None:
        """Insert or update an import record in DuckDB."""
        self._db.execute(
            """INSERT OR REPLACE INTO data_imports
               (symbol, data_type, status, record_count, start_date, end_date,
                storage_key, file_size_bytes, error_message, import_duration_ms, imported_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                record.symbol,
                record.data_type.value if isinstance(record.data_type, DataType) else record.data_type,
                record.status.value if isinstance(record.status, ImportStatus) else record.status,
                record.record_count,
                record.start_date,
                record.end_date,
                record.storage_key,
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
            f"storage_key, file_size_bytes, error_message, import_duration_ms, imported_at "
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
            "storage_key, file_size_bytes, error_message, import_duration_ms, imported_at "
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
            storage_key=r[6],
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
        """Re-import: clear stored data + record, then full import."""
        self._store.delete(symbol, data_type=data_type)
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

        Returns a dict mapping symbol → storage key.
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
        stats = {"source_connected": self._source is not None, "tables": {}}
        for table in ["kline", "tick", "financial", "f10", "factor", "basic", "realtime"]:
            try:
                row = self._db.fetch_one(f"SELECT count(*) FROM {table}")
                stats["tables"][table] = row[0] if row else 0
            except Exception:
                stats["tables"][table] = 0

        # DB file size
        try:
            settings = get_settings()
            db_path = Path(settings.database.duckdb_path)
            if db_path.exists():
                stats["db_size_bytes"] = db_path.stat().st_size
        except Exception:
            pass

        return stats
