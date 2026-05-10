"""
Tdxdata source adapter — wraps external/tdxdata for use inside tdxview.

This adapter delegates all data fetching to the tdxdata library while adding:
- Connection lifecycle management with auto-reconnect
- Retry and circuit-breaker via tdxdata's built-in error handling
- Parquet output support via tdxdata's storage backends
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from app.config.settings import get_settings
from app.data.sources.base_source import DataSourceBase


class TdxDataSource(DataSourceBase):
    """Adapter that delegates to the external tdxdata library."""

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
        """Fetch historical kline data via tdxdata."""
        self._ensure_api()
        return self._api.fetch_history(
            stock_list=symbols,
            start_date=start_date,
            end_date=end_date,
            period=period,
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
        """Fetch historical kline data."""
        self._ensure_api()
        return self._api.fetch_history(
            stock_list=stock_list,
            start_date=start_date,
            end_date=end_date,
            period=period,
            dividend_type=dividend_type,
            output=output,
            output_path=output_path,
        )

    def fetch_realtime(
        self,
        stock_code: Optional[str] = None,
        stock_list: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """Fetch realtime quotes."""
        self._ensure_api()
        return self._api.fetch_realtime(
            stock_code=stock_code,
            stock_list=stock_list,
        )

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

    def fetch_to_parquet(
        self,
        source: str,
        output_path: str,
        **kwargs: Any,
    ) -> Any:
        """Fetch data and save directly to Parquet via tdxdata's storage backend."""
        self._ensure_api()
        return self._api.fetch(
            source=source,
            output="parquet",
            output_path=output_path,
            **kwargs,
        )

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
