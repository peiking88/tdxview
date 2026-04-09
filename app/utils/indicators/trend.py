"""
Trend indicators — SMA, EMA, MACD.
"""

from typing import Optional, Tuple

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Moving Averages
# ---------------------------------------------------------------------------

def sma(series: pd.Series, period: int = 20) -> pd.Series:
    """Simple Moving Average."""
    return series.rolling(window=period, min_periods=period).mean()


def ema(series: pd.Series, period: int = 20) -> pd.Series:
    """Exponential Moving Average."""
    return series.ewm(span=period, adjust=False).mean()


# ---------------------------------------------------------------------------
# MACD
# ---------------------------------------------------------------------------

def macd(
    close: pd.Series,
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """MACD indicator.

    Returns (macd_line, signal_line, histogram).
    """
    fast_ema = ema(close, fast_period)
    slow_ema = ema(close, slow_period)
    macd_line = fast_ema - slow_ema
    signal_line = ema(macd_line, signal_period)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram
