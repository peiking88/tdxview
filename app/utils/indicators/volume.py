"""
Volume indicators — OBV, VWAP.
"""

import numpy as np
import pandas as pd


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """On-Balance Volume.

    Adds volume on up-days, subtracts on down-days.
    """
    direction = np.sign(close.diff().fillna(0))
    direction = direction.replace(0, 0)  # flat days contribute nothing
    return (direction * volume).cumsum()


def vwap(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    volume: pd.Series,
) -> pd.Series:
    """Volume-Weighted Average Price (cumulative within the series).

    VWAP = cumsum(typical_price * volume) / cumsum(volume)
    typical_price = (high + low + close) / 3
    """
    typical = (high + low + close) / 3.0
    cum_tp_vol = (typical * volume).cumsum()
    cum_vol = volume.cumsum()
    return cum_tp_vol / cum_vol.replace(0, np.nan)
