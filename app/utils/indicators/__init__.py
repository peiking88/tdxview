"""
Built-in technical indicator functions.

Categories:
  - trend: SMA, EMA, MACD
  - momentum: RSI, RPS
  - volatility: Bollinger Bands
  - volume: OBV, VWAP
  - custom: user-defined indicator scripts
"""

from app.utils.indicators.trend import sma, ema, macd
from app.utils.indicators.momentum import rsi, rps
from app.utils.indicators.volatility import bollinger_bands
from app.utils.indicators.volume import obv, vwap
from app.utils.indicators.custom import (
    execute_custom_indicator,
    list_custom_indicators,
    load_indicator_script,
)

__all__ = [
    "sma", "ema", "macd",
    "rsi", "rps",
    "bollinger_bands",
    "obv", "vwap",
    "execute_custom_indicator",
    "list_custom_indicators",
    "load_indicator_script",
]
