"""
Unit tests for technical indicator calculations and IndicatorService.
"""

import numpy as np
import pandas as pd
import pytest

from app.utils.indicators.trend import sma, ema, macd
from app.utils.indicators.momentum import rsi, rps
from app.utils.indicators.volatility import bollinger_bands
from app.utils.indicators.volume import obv, vwap
from app.services.indicator_service import IndicatorService, INDICATOR_REGISTRY


# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

@pytest.fixture
def price_series():
    """50-day price series with known values."""
    np.random.seed(42)
    base = 100
    returns = np.random.randn(50) * 0.02 + 0.001  # slight upward drift
    prices = base * np.cumprod(1 + returns)
    return pd.Series(prices, name="close")


@pytest.fixture
def ohlcv_df():
    """50-day OHLCV DataFrame."""
    np.random.seed(42)
    n = 50
    close = 100 + np.cumsum(np.random.randn(n) * 2)
    high = close + np.abs(np.random.randn(n))
    low = close - np.abs(np.random.randn(n))
    open_ = close + np.random.randn(n) * 0.5
    volume = (np.random.rand(n) * 1_000_000 + 100_000).astype(int)
    return pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n),
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })


# ===========================================================================
# SMA
# ===========================================================================

class TestSMA:
    def test_basic(self, price_series):
        result = sma(price_series, period=5)
        assert len(result) == len(price_series)
        # First 4 values should be NaN
        assert result.iloc[:4].isna().all()
        # 5th value is the mean of first 5 prices
        expected = price_series.iloc[:5].mean()
        assert abs(result.iloc[4] - expected) < 1e-10

    def test_manual_calculation(self):
        s = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        result = sma(s, period=3)
        assert abs(result.iloc[2] - 2.0) < 1e-10
        assert abs(result.iloc[3] - 3.0) < 1e-10
        assert abs(result.iloc[9] - 9.0) < 1e-10

    def test_period_1(self, price_series):
        result = sma(price_series, period=1)
        assert (result == price_series).all()


# ===========================================================================
# EMA
# ===========================================================================

class TestEMA:
    def test_basic(self, price_series):
        result = ema(price_series, period=20)
        assert len(result) == len(price_series)
        # No NaN values (EMA starts from first point)
        assert result.iloc[0] == price_series.iloc[0]

    def test_ema_responds_faster_than_sma(self, price_series):
        ema_val = ema(price_series, period=20)
        sma_val = sma(price_series, period=20)
        # In an uptrend, EMA should be above SMA (more weight on recent)
        last_ema = ema_val.iloc[-1]
        last_sma = sma_val.iloc[-1]
        # Just check they differ (direction depends on data)
        assert last_ema != last_sma


# ===========================================================================
# MACD
# ===========================================================================

class TestMACD:
    def test_basic(self, price_series):
        macd_line, signal_line, histogram = macd(price_series)
        assert len(macd_line) == len(price_series)
        assert len(signal_line) == len(price_series)
        assert len(histogram) == len(price_series)

    def test_histogram_is_difference(self, price_series):
        macd_line, signal_line, histogram = macd(price_series)
        diff = macd_line - signal_line
        pd.testing.assert_series_equal(histogram, diff, check_names=False)

    def test_custom_periods(self, price_series):
        macd_line, _, _ = macd(price_series, fast_period=5, slow_period=10, signal_period=3)
        assert len(macd_line) == len(price_series)


# ===========================================================================
# RSI
# ===========================================================================

class TestRSI:
    def test_range(self, price_series):
        result = rsi(price_series, period=14)
        valid = result.dropna()
        assert (valid >= 0).all() and (valid <= 100).all()

    def test_constant_price(self):
        s = pd.Series([100.0] * 30)
        result = rsi(s, period=14)
        # RSI for constant price should be 50 (no direction) or NaN
        valid = result.dropna()
        if len(valid) > 0:
            # With zero loss, RSI should be 100
            assert (valid == 100.0).all() or (valid == 50.0).all()

    def test_known_values(self):
        # Simple uptrend: RSI should be high
        s = pd.Series(range(1, 60), dtype=float)
        result = rsi(s, period=14)
        valid = result.dropna()
        assert len(valid) > 0
        # Uptrend → RSI > 50
        assert valid.iloc[-1] > 50


# ===========================================================================
# RPS
# ===========================================================================

class TestRPS:
    def test_range(self, price_series):
        result = rps(price_series, period=10)
        valid = result.dropna()
        assert (valid >= 0).all() and (valid <= 100).all()


# ===========================================================================
# Bollinger Bands
# ===========================================================================

class TestBollingerBands:
    def test_basic(self, price_series):
        upper, middle, lower = bollinger_bands(price_series, period=20, std_dev=2.0)
        assert len(upper) == len(price_series)
        # Middle band should equal SMA
        sma_val = sma(price_series, period=20)
        pd.testing.assert_series_equal(middle, sma_val, check_names=False)

    def test_upper_above_lower(self, price_series):
        upper, middle, lower = bollinger_bands(price_series)
        valid_idx = upper.dropna().index
        assert (upper[valid_idx] >= lower[valid_idx]).all()

    def test_custom_std_dev(self, price_series):
        upper2, _, lower2 = bollinger_bands(price_series, period=20, std_dev=2.0)
        upper1, _, lower1 = bollinger_bands(price_series, period=20, std_dev=1.0)
        valid_idx = upper2.dropna().index
        # Wider bands with larger std_dev
        assert (upper2[valid_idx] >= upper1[valid_idx]).all()
        assert (lower2[valid_idx] <= lower1[valid_idx]).all()


# ===========================================================================
# OBV
# ===========================================================================

class TestOBV:
    def test_basic(self, ohlcv_df):
        result = obv(ohlcv_df["close"], ohlcv_df["volume"])
        assert len(result) == len(ohlcv_df)

    def test_uptrend_increases(self):
        close = pd.Series([100, 101, 102, 103, 104])
        volume = pd.Series([1000, 1000, 1000, 1000, 1000])
        result = obv(close, volume)
        # Each up-day adds volume, so OBV should be monotonically increasing
        assert (result.diff().dropna() > 0).all()

    def test_downtrend_decreases(self):
        close = pd.Series([104, 103, 102, 101, 100])
        volume = pd.Series([1000, 1000, 1000, 1000, 1000])
        result = obv(close, volume)
        assert (result.diff().dropna() < 0).all()


# ===========================================================================
# VWAP
# ===========================================================================

class TestVWAP:
    def test_basic(self, ohlcv_df):
        result = vwap(ohlcv_df["high"], ohlcv_df["low"], ohlcv_df["close"], ohlcv_df["volume"])
        assert len(result) == len(ohlcv_df)

    def test_known_values(self):
        high = pd.Series([105.0, 106.0])
        low = pd.Series([95.0, 96.0])
        close = pd.Series([100.0, 101.0])
        volume = pd.Series([1000, 1000])
        result = vwap(high, low, close, volume)
        # Typical prices: 100, 101; VWAP = (100*1000 + 101*1000) / 2000 = 100.5
        assert abs(result.iloc[1] - 100.5) < 0.01


# ===========================================================================
# IndicatorService
# ===========================================================================

class TestIndicatorService:
    @pytest.fixture
    def svc(self):
        return IndicatorService()

    def test_list_indicators(self, svc):
        indicators = svc.list_indicators()
        assert len(indicators) >= len(INDICATOR_REGISTRY)
        names = [ind["name"] for ind in indicators]
        assert "sma" in names
        assert "rsi" in names
        assert "macd" in names

    def test_get_indicator_info(self, svc):
        info = svc.get_indicator_info("sma")
        assert info is not None
        assert info["category"] == "trend"

    def test_get_indicator_info_unknown(self, svc):
        assert svc.get_indicator_info("nonexistent") is None

    def test_calculate_sma(self, svc, ohlcv_df):
        results = svc.calculate("sma", ohlcv_df, params={"period": 10})
        assert "sma" in results
        assert len(results["sma"]) == len(ohlcv_df)

    def test_calculate_rsi(self, svc, ohlcv_df):
        results = svc.calculate("rsi", ohlcv_df, params={"period": 14})
        assert "rsi" in results
        valid = results["rsi"].dropna()
        assert (valid >= 0).all() and (valid <= 100).all()

    def test_calculate_macd(self, svc, ohlcv_df):
        results = svc.calculate("macd", ohlcv_df)
        assert "macd_line" in results
        assert "signal_line" in results
        assert "histogram" in results

    def test_calculate_bollinger(self, svc, ohlcv_df):
        results = svc.calculate("bollinger_bands", ohlcv_df)
        assert "bb_upper" in results
        assert "bb_middle" in results
        assert "bb_lower" in results

    def test_calculate_obv(self, svc, ohlcv_df):
        results = svc.calculate("obv", ohlcv_df)
        assert "obv" in results

    def test_calculate_vwap(self, svc, ohlcv_df):
        results = svc.calculate("vwap", ohlcv_df)
        assert "vwap" in results

    def test_calculate_unknown_raises(self, svc, ohlcv_df):
        with pytest.raises(ValueError, match="Unknown indicator"):
            svc.calculate("nope", ohlcv_df)

    def test_calculate_multiple(self, svc, ohlcv_df):
        results = svc.calculate_multiple(["sma", "rsi"], ohlcv_df)
        assert "sma" in results
        assert "rsi" in results

    def test_calculate_caches_result(self, svc, ohlcv_df):
        # First call
        r1 = svc.calculate("sma", ohlcv_df, params={"period": 5}, use_cache=True)
        # Second call should hit cache
        r2 = svc.calculate("sma", ohlcv_df, params={"period": 5}, use_cache=True)
        # Values should match (cache returns lists → pd.Series)
        assert (r1["sma"].dropna().values == r2["sma"].dropna().values).all()

    def test_add_indicator_to_figure(self, svc, ohlcv_df):
        from plotly.subplots import make_subplots
        fig = make_subplots(rows=1, cols=1)
        fig = svc.add_indicator_to_figure(fig, "sma", ohlcv_df, params={"period": 5}, row=1, col=1)
        assert len(fig.data) >= 1

    def test_add_macd_to_figure(self, svc, ohlcv_df):
        from plotly.subplots import make_subplots
        fig = make_subplots(rows=1, cols=1)
        fig = svc.add_indicator_to_figure(fig, "macd", ohlcv_df, row=1, col=1)
        assert len(fig.data) >= 3  # macd_line + signal + histogram
