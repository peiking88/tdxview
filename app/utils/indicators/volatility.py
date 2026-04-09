"""
Volatility indicators — Bollinger Bands.
"""

from typing import Tuple

import numpy as np
import pandas as pd


def bollinger_bands(
    close: pd.Series,
    period: int = 20,
    std_dev: float = 2.0,
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Bollinger Bands.

    Returns (upper_band, middle_band, lower_band).
    middle_band = SMA(close, period)
    upper_band = middle + std_dev * rolling_std
    lower_band = middle - std_dev * rolling_std
    """
    middle = close.rolling(window=period, min_periods=period).mean()
    rolling_std = close.rolling(window=period, min_periods=period).std()
    upper = middle + std_dev * rolling_std
    lower = middle - std_dev * rolling_std
    return upper, middle, lower
