"""
DuckDB-based persistent storage — replaces ParquetManager.

Stores all market data (kline, tick, financial, f10, factor, basic, realtime)
as structured DuckDB tables instead of scattered Parquet files.
"""

import json
import logging
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from app.data.database import DatabaseManager

logger = logging.getLogger(__name__)

# data_type → DuckDB table name
_TABLE_MAP = {
    "history": "kline",
    "kline": "kline",
    "tick": "tick",
    "financial": "financial",
    "f10": "f10",
    "factor": "factor",
    "basic": "basic",
    "realtime": "realtime",
}

_CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS kline (
    symbol       VARCHAR NOT NULL,
    trade_date   DATE NOT NULL,
    period       VARCHAR NOT NULL DEFAULT '1d',
    dividend     VARCHAR NOT NULL DEFAULT 'none',
    open         DOUBLE,
    high         DOUBLE,
    low          DOUBLE,
    close        DOUBLE,
    volume       BIGINT,
    amount       DOUBLE,
    PRIMARY KEY (symbol, trade_date, period, dividend)
);

CREATE TABLE IF NOT EXISTS tick (
    symbol       VARCHAR NOT NULL,
    trade_date   DATE NOT NULL,
    trade_time   TIMESTAMP NOT NULL,
    price        DOUBLE,
    volume       BIGINT,
    amount       DOUBLE,
    direction    VARCHAR,
    PRIMARY KEY (symbol, trade_date, trade_time)
);

CREATE TABLE IF NOT EXISTS financial (
    symbol       VARCHAR NOT NULL,
    report_date  DATE NOT NULL,
    data         JSON,
    PRIMARY KEY (symbol, report_date)
);

CREATE TABLE IF NOT EXISTS f10 (
    symbol       VARCHAR NOT NULL,
    section      VARCHAR NOT NULL,
    data         JSON,
    updated_at   TIMESTAMP,
    PRIMARY KEY (symbol, section)
);

CREATE TABLE IF NOT EXISTS factor (
    symbol       VARCHAR NOT NULL,
    trade_date   DATE NOT NULL,
    adjust       VARCHAR NOT NULL DEFAULT 'qfq',
    factor       DOUBLE NOT NULL,
    PRIMARY KEY (symbol, adjust, trade_date)
);

CREATE TABLE IF NOT EXISTS basic (
    symbol       VARCHAR NOT NULL,
    ex_date      DATE NOT NULL,
    dividend     DOUBLE,
    allotment    DOUBLE,
    data         JSON,
    PRIMARY KEY (symbol, ex_date)
);

CREATE TABLE IF NOT EXISTS realtime (
    symbol       VARCHAR NOT NULL PRIMARY KEY,
    price        DOUBLE,
    change       DOUBLE,
    change_pct   DOUBLE,
    open         DOUBLE,
    high         DOUBLE,
    low          DOUBLE,
    prev_close   DOUBLE,
    volume       BIGINT,
    amount       DOUBLE,
    updated_at   TIMESTAMP
);
"""

_ALL_DATA_TABLES = ["kline", "tick", "financial", "f10", "factor", "basic", "realtime"]


class DuckDBStore:
    """Persistent storage backed by DuckDB tables, replacing ParquetManager."""

    def __init__(self, db: DatabaseManager):
        self._db = db
        self._tables_ready = False

    def _ensure_tables(self):
        if self._tables_ready:
            return
        self._db.execute(_CREATE_TABLES_SQL)
        self._db.connection.commit()
        self._tables_ready = True

    @staticmethod
    def _table_for_type(data_type: str) -> str:
        table = _TABLE_MAP.get(data_type)
        if table is None:
            raise ValueError(f"未知数据类型: {data_type}")
        return table

    # ------------------------------------------------------------------
    # NaN / None handling
    # ------------------------------------------------------------------

    @staticmethod
    def _sanitize_df(df: pd.DataFrame) -> pd.DataFrame:
        """Replace NaN / NaT with None for DuckDB compatibility."""
        df = df.copy()
        df = df.where(df.notna(), None)
        return df

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def save(
        self,
        df: pd.DataFrame,
        symbol: str,
        date: Optional[str] = None,
        data_type: str = "history",
        period: Optional[str] = None,
        dividend: Optional[str] = None,
    ) -> str:
        """Write DataFrame into the corresponding DuckDB table.

        Returns a storage key string like "kline/000001".
        """
        self._ensure_tables()
        if df.empty:
            return ""

        table = self._table_for_type(data_type)
        clean = self._sanitize_df(df)
        row_count = len(clean)

        if table == "kline":
            self._save_kline(clean, symbol, period or "1d", dividend or "none")
        elif table == "tick":
            self._save_tick(clean, symbol)
        elif table == "financial":
            self._save_json_table(clean, symbol, "financial", "report_date")
        elif table == "f10":
            self._save_f10(clean, symbol)
        elif table == "factor":
            self._save_factor(clean, symbol, dividend or "qfq")
        elif table == "basic":
            self._save_json_table(clean, symbol, "basic", "ex_date")
        elif table == "realtime":
            self._save_realtime(clean, symbol)
        else:
            raise ValueError(f"不支持的表: {table}")

        self._db.connection.commit()
        logger.debug("保存 %d 行到 %s/%s", row_count, table, symbol)
        return f"{table}/{symbol}"

    def _save_kline(self, df: pd.DataFrame, symbol: str, period: str, dividend: str):
        cols = []
        for col in df.columns:
            if col in ("date", "trade_date", "datetime", "time"):
                cols.append(("trade_date", col))
            elif col in ("open", "high", "low", "close", "volume", "amount"):
                cols.append((col, col))

        for _, row in df.iterrows():
            trade_date = None
            vals: dict = {"symbol": symbol, "period": period, "dividend": dividend}
            for target_col, src_col in cols:
                v = row.get(src_col)
                if target_col == "trade_date":
                    trade_date = str(v)[:10] if v is not None else None
                else:
                    vals[target_col] = v
            if trade_date is None:
                continue

            self._db.execute(
                "INSERT OR REPLACE INTO kline (symbol, trade_date, period, dividend, open, high, low, close, volume, amount) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    symbol, trade_date, period, dividend,
                    vals.get("open"), vals.get("high"), vals.get("low"),
                    vals.get("close"), vals.get("volume"), vals.get("amount"),
                ],
            )

    def _save_tick(self, df: pd.DataFrame, symbol: str):
        for i, (_, row) in enumerate(df.iterrows()):
            date_val = row.get("date") or row.get("trade_date")
            time_val = row.get("time") or row.get("trade_time")
            # tdxdata returns 'datetime' column (e.g. "2026-05-12 09:25:00")
            dt_val = row.get("datetime")
            if dt_val is not None and date_val is None:
                dt_str = str(dt_val)
                date_val = dt_str[:10]
                if time_val is None:
                    time_val = dt_str
            if time_val is None:
                # 无 time 列时用行号构造唯一时间戳
                time_val = f"{str(date_val)[:10]} 00:00:{i:02d}" if date_val is not None else None
            self._db.execute(
                "INSERT OR REPLACE INTO tick (symbol, trade_date, trade_time, price, volume, amount, direction) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    symbol,
                    str(date_val)[:10] if date_val is not None else None,
                    str(time_val) if time_val is not None else None,
                    row.get("price"), row.get("volume"), row.get("amount"),
                    row.get("direction"),
                ],
            )

    def _save_json_table(self, df: pd.DataFrame, symbol: str, table: str, date_col: str):
        for i, (_, row) in enumerate(df.iterrows()):
            row_dict = {k: self._pyval(v) for k, v in row.items() if k != date_col}
            date_val = row.get(date_col) or row.get("date")
            # Fallback: use row index as synthetic date, capped at day 28
            fallback_day = (i % 28) + 1
            date_str = str(date_val)[:10] if date_val is not None else f"1970-01-{fallback_day:02d}"
            self._db.execute(
                f"INSERT OR REPLACE INTO {table} (symbol, {date_col}, data) VALUES (?, ?, ?)",
                [symbol, date_str,
                 json.dumps(row_dict, ensure_ascii=False, default=str)],
            )

    def _save_f10(self, df: pd.DataFrame, symbol: str):
        if "section" in df.columns:
            for section, group in df.groupby("section"):
                rows = []
                for _, row in group.iterrows():
                    rows.append({k: self._pyval(v) for k, v in row.items() if k != "section"})
                self._db.execute(
                    "INSERT OR REPLACE INTO f10 (symbol, section, data, updated_at) VALUES (?, ?, ?, ?)",
                    [symbol, str(section), json.dumps(rows, ensure_ascii=False, default=str),
                     datetime.now().isoformat()],
                )
        else:
            rows = []
            for _, row in df.iterrows():
                rows.append({k: self._pyval(v) for k, v in row.items()})
            self._db.execute(
                "INSERT OR REPLACE INTO f10 (symbol, section, data, updated_at) VALUES (?, ?, ?, ?)",
                [symbol, "default", json.dumps(rows, ensure_ascii=False, default=str),
                 datetime.now().isoformat()],
            )

    def _save_factor(self, df: pd.DataFrame, symbol: str, adjust: str):
        for _, row in df.iterrows():
            date_val = row.get("date") or row.get("trade_date")
            factor_val = row.get("factor")
            if date_val is None or factor_val is None:
                continue
            self._db.execute(
                "INSERT OR REPLACE INTO factor (symbol, trade_date, adjust, factor) VALUES (?, ?, ?, ?)",
                [symbol, str(date_val)[:10], adjust, float(factor_val)],
            )

    def _save_realtime(self, df: pd.DataFrame, symbol: str):
        for _, row in df.iterrows():
            sym = row.get("stock_code") or row.get("symbol") or row.get("code") or symbol
            self._db.execute(
                "INSERT OR REPLACE INTO realtime "
                "(symbol, price, change, change_pct, open, high, low, prev_close, volume, amount, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    sym, row.get("price"), row.get("change"), row.get("change_pct") or row.get("change_percent"),
                    row.get("open"), row.get("high"), row.get("low"), row.get("prev_close"),
                    row.get("volume"), row.get("amount"), datetime.now().isoformat(),
                ],
            )

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    def load(
        self,
        symbol: str,
        date: Optional[str] = None,
        data_type: str = "history",
        period: Optional[str] = None,
        dividend: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Optional[pd.DataFrame]:
        """Load data from DuckDB table. Returns DataFrame or None."""
        self._ensure_tables()
        table = self._table_for_type(data_type)

        if table == "kline":
            return self._load_kline(symbol, period or "1d", dividend or "none",
                                    start_date, end_date)
        elif table == "tick":
            return self._load_tick(symbol, date)
        elif table in ("financial", "basic"):
            return self._load_json_table(symbol, table)
        elif table == "f10":
            return self._load_f10(symbol)
        elif table == "factor":
            return self._load_factor(symbol, dividend or "qfq")
        elif table == "realtime":
            return self._load_realtime(symbol)
        return None

    def _load_kline(self, symbol: str, period: str, dividend: str,
                    start_date: Optional[str], end_date: Optional[str]) -> Optional[pd.DataFrame]:
        conditions = ["symbol = ?", "period = ?", "dividend = ?"]
        params: list = [symbol, period, dividend]

        if start_date:
            conditions.append("trade_date >= ?")
            params.append(start_date)
        if end_date:
            conditions.append("trade_date <= ?")
            params.append(end_date)

        where = " AND ".join(conditions)
        try:
            df = self._db.fetch_df(
                f"SELECT trade_date AS date, open, high, low, close, volume, amount "
                f"FROM kline WHERE {where} ORDER BY trade_date", params,
            )
            return df if not df.empty else None
        except Exception:
            return None

    def _load_tick(self, symbol: str, date: Optional[str]) -> Optional[pd.DataFrame]:
        conditions = ["symbol = ?"]
        params: list = [symbol]
        if date:
            conditions.append("trade_date = ?")
            params.append(date[:10])

        where = " AND ".join(conditions)
        try:
            df = self._db.fetch_df(
                f"SELECT trade_date AS date, trade_time AS time, price, volume, amount, direction "
                f"FROM tick WHERE {where} ORDER BY trade_time", params,
            )
            return df if not df.empty else None
        except Exception:
            return None

    def _load_json_table(self, symbol: str, table: str) -> Optional[pd.DataFrame]:
        try:
            rows = self._db.fetch_all(
                f"SELECT * FROM {table} WHERE symbol = ? ORDER BY 2", [symbol],
            )
        except Exception:
            return None
        if not rows:
            return None

        records = []
        for r in rows:
            date_col_val = str(r[1]) if r[1] is not None else None
            data_dict = json.loads(r[2]) if isinstance(r[2], str) else (r[2] or {})
            if date_col_val:
                col_name = "report_date" if table == "financial" else "ex_date"
                data_dict[col_name] = date_col_val
            records.append(data_dict)
        return pd.DataFrame(records)

    def _load_f10(self, symbol: str) -> Optional[pd.DataFrame]:
        try:
            rows = self._db.fetch_all(
                "SELECT section, data, updated_at FROM f10 WHERE symbol = ? ORDER BY section",
                [symbol],
            )
        except Exception:
            return None
        if not rows:
            return None

        records = []
        for section, data, updated_at in rows:
            items = json.loads(data) if isinstance(data, str) else (data or [])
            for item in items:
                item["section"] = section
                records.append(item)
        return pd.DataFrame(records) if records else None

    def _load_factor(self, symbol: str, adjust: str) -> Optional[pd.DataFrame]:
        try:
            df = self._db.fetch_df(
                "SELECT trade_date AS date, factor FROM factor "
                "WHERE symbol = ? AND adjust = ? ORDER BY trade_date",
                [symbol, adjust],
            )
            return df if not df.empty else None
        except Exception:
            return None

    def _load_realtime(self, symbol: str) -> Optional[pd.DataFrame]:
        try:
            df = self._db.fetch_df(
                "SELECT symbol AS stock_code, price, change, change_pct AS change_percent, "
                "open, high, low, prev_close, volume, amount, updated_at "
                "FROM realtime WHERE symbol = ?", [symbol],
            )
            return df if not df.empty else None
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(self, symbol: str, date: Optional[str] = None, data_type: str = "history") -> bool:
        """Delete data for a symbol. Returns True if any rows were deleted."""
        self._ensure_tables()
        table = self._table_for_type(data_type)

        if table == "kline":
            result = self._db.fetch_one("SELECT count(*) FROM kline WHERE symbol = ?", [symbol])
            self._db.execute("DELETE FROM kline WHERE symbol = ?", [symbol])
        elif table == "tick":
            if date:
                result = self._db.fetch_one(
                    "SELECT count(*) FROM tick WHERE symbol = ? AND trade_date = ?",
                    [symbol, date[:10]],
                )
                self._db.execute("DELETE FROM tick WHERE symbol = ? AND trade_date = ?",
                                 [symbol, date[:10]])
            else:
                result = self._db.fetch_one(
                    "SELECT count(*) FROM tick WHERE symbol = ?", [symbol],
                )
                self._db.execute("DELETE FROM tick WHERE symbol = ?", [symbol])
        else:
            result = self._db.fetch_one(
                f"SELECT count(*) FROM {table} WHERE symbol = ?", [symbol],
            )
            self._db.execute(f"DELETE FROM {table} WHERE symbol = ?", [symbol])

        self._db.connection.commit()
        return result[0] > 0 if result else False

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def list_symbols(self, data_type: str = "history") -> List[str]:
        """List distinct symbols for a data type."""
        self._ensure_tables()
        table = self._table_for_type(data_type)
        try:
            rows = self._db.fetch_all(f"SELECT DISTINCT symbol FROM {table} ORDER BY symbol")
            return [r[0] for r in rows]
        except Exception:
            return []

    def list_data_types(self, symbol: Optional[str] = None) -> List[str]:
        """List data types that have stored data, optionally filtered by symbol."""
        self._ensure_tables()
        result = []
        for table in _ALL_DATA_TABLES:
            try:
                if symbol:
                    row = self._db.fetch_one(
                        f"SELECT 1 FROM {table} WHERE symbol = ? LIMIT 1", [symbol],
                    )
                else:
                    row = self._db.fetch_one(f"SELECT 1 FROM {table} LIMIT 1")
                if row:
                    # map back to external data_type name
                    for dtype, tbl in _TABLE_MAP.items():
                        if tbl == table and dtype not in result:
                            result.append(dtype)
                            break
            except Exception:
                continue
        return sorted(result)

    # ------------------------------------------------------------------
    # Info
    # ------------------------------------------------------------------

    def get_info(self, symbol: str, data_type: str = "history") -> Optional[Dict]:
        """Return row count and storage key for a symbol's data type."""
        self._ensure_tables()
        table = self._table_for_type(data_type)
        try:
            row = self._db.fetch_one(
                f"SELECT count(*) FROM {table} WHERE symbol = ?", [symbol],
            )
            if row and row[0] > 0:
                return {"storage_key": f"{table}/{symbol}", "row_count": row[0]}
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _pyval(v):
        """Convert numpy/pandas scalar to Python native for JSON serialization."""
        if v is None:
            return None
        if isinstance(v, (np.integer,)):
            return int(v)
        if isinstance(v, (np.floating,)):
            if np.isnan(v):
                return None
            return float(v)
        if isinstance(v, (np.bool_,)):
            return bool(v)
        if isinstance(v, pd.Timestamp):
            return str(v)
        return v
