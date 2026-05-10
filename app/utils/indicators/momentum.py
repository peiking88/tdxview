"""
Momentum indicators — RSI, RPS.
"""

from typing import Optional

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# RSI (Relative Strength Index)
# ---------------------------------------------------------------------------

def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index using Wilder's smoothing method.

    Values range from 0 to 100.  >70 overbought, <30 oversold.
    """
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)

    # Wilder's smoothing (exponential with alpha = 1/period)
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    # When avg_loss is 0 (pure uptrend), RSI = 100
    result = pd.Series(np.where(avg_loss == 0, 100.0, 100.0 - (100.0 / (1.0 + rs))),
                       index=close.index)
    # Preserve NaN where avg_gain hasn't accumulated enough periods
    result[avg_gain.isna()] = np.nan
    return result


# ---------------------------------------------------------------------------
# RPS (Relative Price Strength)
# ---------------------------------------------------------------------------

def rps(
    close: pd.Series,
    period: int = 20,
) -> pd.Series:
    """Relative Price Strength — percentage rank of current return over *period*.

    For each bar, compute the return over *period* days, then rank it
    as a percentile among the last *period* returns.
    """
    returns = close.pct_change(periods=period)
    # Rolling percentile rank
    result = returns.rolling(window=period).apply(
        lambda x: pd.Series(x).rank(pct=True).iloc[-1], raw=False
    )
    return result * 100  # 0..100 scale
