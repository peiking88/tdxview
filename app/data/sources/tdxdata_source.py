"""
Tdxdata source adapter — wraps tdxdata library for use inside tdxview.

This adapter delegates all data fetching to the tdxdata library while adding:
- Connection lifecycle management with auto-reconnect
- Retry and circuit-breaker via tdxdata's built-in error handling
- Parquet output support via tdxdata's storage backends
"""

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from app.config.settings import get_settings
from app.data.sources.base_source import DataSourceBase

logger = logging.getLogger(__name__)


class TdxDataSource(DataSourceBase):
    """Adapter that delegates to the tdxdata library."""

    def __init__(
        self,
        server: Optional[tuple] = None,
        timeout: int = 15,
        tdxdir: Optional[str] = None,
    ):
        settings = get_settings()
        self._server = server
        self._timeout = timeout or settings.tdxdata.timeout
        self._tdxdir = tdxdir
        self._api = None
        self._connected = False

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def _ensure_api(self):
        """Lazy-initialize the TdxData API instance with auto-reconnect."""
        if self._api is not None and self._connected:
            return
        from tdxdata import TdxData

        self._api = TdxData(server=self._server, timeout=self._timeout)
        self._api.connect()
        self._connected = True

    def connect(self) -> None:
        """Explicitly open a connection."""
        self._ensure_api()

    def close(self):
        """Close the underlying connection."""
        if self._api is not None:
            try:
                self._api.close()
            except Exception:
                pass
            self._api = None
            self._connected = False

    def validate_connection(self) -> bool:
        """Check whether tdxdata can connect to a server."""
        try:
            self._ensure_api()
            return self._connected
        except Exception:
            self._connected = False
            return False

    def _reconnect(self):
        """Force a reconnection attempt."""
        self.close()
        self._ensure_api()

    # ------------------------------------------------------------------
    # BaseSource interface
    # ------------------------------------------------------------------

    def fetch(
        self,
        symbols: List[str],
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        period: str = "1d",
        dividend_type: str = "front",
        **kwargs: Any,
    ) -> pd.DataFrame:
        """Fetch historical kline data via tdxdata.

        tdxdata >=0.8.0 内置重采样，所有周期统一走 hybrid（本地+网络）。
        """
        self._ensure_api()
        return self._api.fetch_hybrid(
            stock_list=symbols,
            start_date=start_date,
            end_date=end_date,
            period=period,
            tdxdir=self._tdxdir,
            dividend_type=dividend_type,
        )

    # ------------------------------------------------------------------
    # Full tdxdata API proxy
    # ------------------------------------------------------------------

    def fetch_history(
        self,
        stock_list: List[str],
        start_date: str,
        end_date: str,
        period: str = "1d",
        dividend_type: str = "front",
        output: str = "dataframe",
        output_path: Optional[str] = None,
    ) -> pd.DataFrame:
        """Fetch historical kline data.

        tdxdata >=0.8.0 内置重采样，所有周期统一走 hybrid（本地+网络）。
        """
        self._ensure_api()
        return self._api.fetch_hybrid(
            stock_list=stock_list,
            start_date=start_date,
            end_date=end_date,
            period=period,
            tdxdir=self._tdxdir,
            dividend_type=dividend_type,
        )

    def fetch_realtime(
        self,
        stock_code: Optional[str] = None,
        stock_list: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """获取实时行情快照，空结果时自动重试一次。

        通达信实时接口在非交易时段或网络抖动时可能返回空数据，
        重试一次可排除瞬态故障；两次均空则大概率是市场关闭。
        """
        self._ensure_api()
        codes = stock_list or ([stock_code] if stock_code else [])
        for attempt in range(2):
            result = self._api.fetch_realtime(
                stock_code=stock_code,
                stock_list=stock_list,
            )
            if not result.empty:
                return result
            if attempt == 0:
                logger.warning(
                    "realtime 返回空数据 (codes=%s)，1s 后重试", codes
                )
                time.sleep(1.0)
        logger.warning("realtime 重试后仍为空 (codes=%s)，可能非交易时段", codes)
        return result

    def fetch_tick(
        self,
        stock_code: str,
        date: Optional[str] = None,
    ) -> pd.DataFrame:
        """Fetch tick-by-tick transaction data."""
        self._ensure_api()
        return self._api.fetch_tick(stock_code=stock_code, date=date)

    def fetch_financial(self, stock_code: str) -> pd.DataFrame:
        """Fetch financial statements."""
        self._ensure_api()
        return self._api.fetch_financial(stock_code=stock_code)

    def fetch_f10(
        self,
        stock_code: str,
        sections: Optional[List[str]] = None,
    ) -> Dict[str, pd.DataFrame]:
        """Fetch F10 company information."""
        self._ensure_api()
        return self._api.fetch_f10(stock_code=stock_code, sections=sections)

    def fetch_basic(
        self,
        stock_code: str,
        date: Optional[str] = None,
    ) -> pd.DataFrame:
        """Fetch ex-rights/ex-dividend data."""
        self._ensure_api()
        return self._api.fetch_basic(stock_code=stock_code, date=date)

    def fetch_factor(
        self,
        stock_code: str,
        adjust: str = "qfq",
    ) -> pd.DataFrame:
        """获取复权因子数据（前复权/后复权）。

        tdxdata v0.7.0 将 fetch_factor 收为内部实现，此处通过公有 API
        fetch_basic（XDXR 除权除息事件） + fetch_history（全量 K 线）
        配合 tdxdata 内置的 compute_factor_from_xdzr 完成因子计算。

        前复权因子归一化：最新日期因子 = 1.0，确保前复权最新价 = 原始收盘价。
        """
        from datetime import date

        from tdxdata.sources.adjust import compute_factor_from_xdxr

        self._ensure_api()

        xdxr = self._api.fetch_basic(stock_code=stock_code)
        if xdxr is None or xdxr.empty:
            return pd.DataFrame(columns=["date", "factor"])

        kline = self._api.fetch_history(
            stock_list=[stock_code],
            start_date="1990-01-01",
            end_date=date.today().isoformat(),
            period="1d",
            dividend_type="none",
        )

        result = compute_factor_from_xdxr(xdxr, kline, adjust)
        if result.empty:
            return pd.DataFrame(columns=["date", "factor"])

        result = result.reset_index()
        result.rename(columns={"index": "date"}, inplace=True)
        return result

    def fetch_local(
        self,
        stock_list: Optional[List[str]] = None,
        stock_code: Optional[str] = None,
        period: str = "1d",
        tdxdir: Optional[str] = None,
        dividend_type: str = "none",
    ) -> pd.DataFrame:
        """Fetch kline data from local TDX binary files."""
        self._ensure_api()
        return self._api.fetch_local(
            stock_list=stock_list,
            stock_code=stock_code,
            period=period,
            tdxdir=tdxdir or self._tdxdir,
            dividend_type=dividend_type,
        )

    def fetch_hybrid(
        self,
        stock_list: Optional[List[str]] = None,
        stock_code: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        period: str = "1d",
        tdxdir: Optional[str] = None,
        dividend_type: str = "none",
    ) -> pd.DataFrame:
        """Fetch kline data from local files, filling gaps from network."""
        self._ensure_api()
        return self._api.fetch_hybrid(
            stock_list=stock_list,
            stock_code=stock_code,
            start_date=start_date,
            end_date=end_date,
            period=period,
            tdxdir=tdxdir or self._tdxdir,
            dividend_type=dividend_type,
        )

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
