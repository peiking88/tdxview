"""
Data service — orchestrates data fetching and source management.

This is the primary business-logic layer that Streamlit components and other
services call.
"""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from app.config.settings import get_settings
from app.data.sources.tdxdata_source import TdxDataSource


class DataService:
    """High-level data access service."""

    _FACTOR_CACHE_PATH = Path("data/factors.json")

    def __init__(self):
        settings = get_settings()
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
        """Remove anomalous rows from kline data."""
        if df.empty:
            return df

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

        if "volume" in df.columns:
            vol = pd.to_numeric(df["volume"], errors="coerce")
            median_vol = vol[vol > 0].median()
            if pd.notna(median_vol) and median_vol > 0:
                mask &= (vol >= median_vol * 0.1) & (vol <= median_vol * 10)

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

        if "high" in df.columns and "low" in df.columns:
            high = pd.to_numeric(df["high"], errors="coerce")
            low = pd.to_numeric(df["low"], errors="coerce")
            mask &= (high >= low) | high.isna() | low.isna()

        return df.loc[mask].reset_index(drop=True)

    @staticmethod
    def check_continuity(df: pd.DataFrame) -> Dict[str, Any]:
        """Check data continuity and return a report."""
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

        ohlc_issues = 0
        if all(c in df.columns for c in ("high", "low")):
            bad = df[pd.to_numeric(df["high"], errors="coerce")
                     < pd.to_numeric(df["low"], errors="coerce")]
            ohlc_issues = len(bad)
        if ohlc_issues:
            report["issues"].append(f"{ohlc_issues} 行 high < low")
            report["valid"] -= ohlc_issues

        if "date" in df.columns:
            dup_count = df["date"].duplicated().sum()
            if dup_count:
                report["issues"].append(f"{dup_count} 个重复日期")
                report["valid"] -= dup_count

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
        """获取历史 K 线数据。"""
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
        """Get realtime quotes."""
        df = self.source.fetch_realtime(stock_list=stock_list)
        if not df.empty:
            df = df.loc[:, ~df.columns.duplicated()]
        return df

    # ------------------------------------------------------------------
    # Factor data (复权因子)
    # ------------------------------------------------------------------

    def get_factor(
        self,
        stock_code: str,
        adjust: str = "qfq",
        use_cache: bool = True,
    ) -> pd.DataFrame:
        """Get adjustment factor data, with JSON file cache."""
        if use_cache:
            cached = self._load_factor_cache(stock_code, adjust)
            if cached is not None:
                return cached

        df = self.source.fetch_factor(stock_code=stock_code, adjust=adjust)
        if not df.empty:
            df = df.loc[:, ~df.columns.duplicated()]
            self._save_factor_cache(stock_code, adjust, df)
        return df

    @classmethod
    def _factor_cache_path(cls) -> Path:
        return cls._FACTOR_CACHE_PATH

    @classmethod
    def _load_factor_cache(cls, stock_code: str, adjust: str) -> Optional[pd.DataFrame]:
        path = cls._factor_cache_path()
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            key = f"{stock_code}:{adjust}"
            if key in data:
                df = pd.DataFrame(data[key])
                if "date" in df.columns:
                    df["date"] = pd.to_datetime(df["date"])
                return df
        except Exception:
            return None
        return None

    @classmethod
    def _save_factor_cache(cls, stock_code: str, adjust: str, df: pd.DataFrame):
        path = cls._factor_cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        data: Dict[str, list] = {}
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                pass
        key = f"{stock_code}:{adjust}"
        records = df.to_dict(orient="records")
        for r in records:
            for k, v in r.items():
                if hasattr(v, "isoformat"):
                    r[k] = v.isoformat()
        data[key] = records
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

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
        """Fetch historical data for multiple symbols in parallel."""
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

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def close(self):
        """Release all resources."""
        if self._source is not None:
            self._source.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ------------------------------------------------------------------
    # Runtime statistics
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return runtime statistics about the data service."""
        return {"source_connected": self._source is not None}
