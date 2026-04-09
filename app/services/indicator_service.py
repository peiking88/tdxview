"""
Indicator service — calculates technical indicators, caches results,
and integrates with visualization.
"""

import json
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import plotly.graph_objects as go

from app.config.settings import get_settings
from app.data.cache import CacheManager, generate_cache_key
from app.data.database import DatabaseManager
from app.utils.indicators.trend import sma, ema, macd
from app.utils.indicators.momentum import rsi, rps
from app.utils.indicators.volatility import bollinger_bands
from app.utils.indicators.volume import obv, vwap
from app.utils.indicators.custom import execute_custom_indicator, list_custom_indicators


# ---------------------------------------------------------------------------
# Registry: maps indicator name → (calculation_fn, default_params, category)
# ---------------------------------------------------------------------------

INDICATOR_REGISTRY: Dict[str, Dict[str, Any]] = {
    "sma": {
        "fn": sma,
        "default_params": {"period": 20},
        "category": "trend",
        "display_name": "SMA 简单移动平均线",
        "input": "close",
    },
    "ema": {
        "fn": ema,
        "default_params": {"period": 20},
        "category": "trend",
        "display_name": "EMA 指数移动平均线",
        "input": "close",
    },
    "macd": {
        "fn": macd,
        "default_params": {"fast_period": 12, "slow_period": 26, "signal_period": 9},
        "category": "trend",
        "display_name": "MACD",
        "input": "close",
        "multi_output": True,  # returns tuple of 3 series
    },
    "rsi": {
        "fn": rsi,
        "default_params": {"period": 14},
        "category": "momentum",
        "display_name": "RSI 相对强弱指数",
        "input": "close",
    },
    "rps": {
        "fn": rps,
        "default_params": {"period": 20},
        "category": "momentum",
        "display_name": "RPS 相对价格强度",
        "input": "close",
    },
    "bollinger_bands": {
        "fn": bollinger_bands,
        "default_params": {"period": 20, "std_dev": 2.0},
        "category": "volatility",
        "display_name": "布林带",
        "input": "close",
        "multi_output": True,  # returns tuple of 3 series
    },
    "obv": {
        "fn": obv,
        "default_params": {},
        "category": "volume",
        "display_name": "OBV 能量潮",
        "input": "close,volume",
    },
    "vwap": {
        "fn": vwap,
        "default_params": {},
        "category": "volume",
        "display_name": "VWAP 成交量加权平均价",
        "input": "high,low,close,volume",
    },
}


class IndicatorService:
    """Service layer for technical indicator calculation and management."""

    def __init__(self):
        self._cache = CacheManager()

    # ------------------------------------------------------------------
    # Calculate a single indicator
    # ------------------------------------------------------------------

    def calculate(
        self,
        indicator_name: str,
        df: pd.DataFrame,
        params: Optional[Dict[str, Any]] = None,
        use_cache: bool = True,
    ) -> Dict[str, pd.Series]:
        """Calculate a named indicator and return a dict of result series.

        For multi-output indicators (MACD, Bollinger), the dict contains
        multiple keys (e.g. "macd_line", "signal_line", "histogram").

        For single-output indicators, the dict has one key matching the
        indicator name.
        """
        if indicator_name not in INDICATOR_REGISTRY:
            raise ValueError(f"Unknown indicator: {indicator_name}")

        entry = INDICATOR_REGISTRY[indicator_name]
        merged_params = {**entry["default_params"], **(params or {})}

        # Cache check
        if use_cache:
            cache_key = generate_cache_key("indicator", {
                "name": indicator_name,
                "params": merged_params,
                "data_hash": hash(tuple(df["close"].values.tobytes() if "close" in df.columns else [])),
            })
            cached = self._cache.get(cache_key)
            if cached is not None:
                return {k: pd.Series(v) for k, v in cached.items()}

        # Compute
        fn = entry["fn"]
        input_key = entry["input"]

        if input_key == "close":
            result = fn(df["close"], **merged_params)
        elif input_key == "close,volume":
            result = fn(df["close"], df["volume"], **merged_params)
        elif input_key == "high,low,close,volume":
            result = fn(df["high"], df["low"], df["close"], df["volume"], **merged_params)
        else:
            raise ValueError(f"Unsupported input spec: {input_key}")

        # Normalize output to dict
        if entry.get("multi_output"):
            if indicator_name == "macd":
                macd_line, signal_line, histogram = result
                output = {
                    "macd_line": macd_line,
                    "signal_line": signal_line,
                    "histogram": histogram,
                }
            elif indicator_name == "bollinger_bands":
                upper, middle, lower = result
                output = {
                    "bb_upper": upper,
                    "bb_middle": middle,
                    "bb_lower": lower,
                }
            else:
                output = {indicator_name: result}
        else:
            output = {indicator_name: result}

        # Cache
        if use_cache:
            cache_data = {k: v.tolist() for k, v in output.items()}
            settings = get_settings()
            self._cache.set(cache_key, cache_data, ttl=settings.indicators.cache_ttl)

        return output

    # ------------------------------------------------------------------
    # Calculate multiple indicators at once
    # ------------------------------------------------------------------

    def calculate_multiple(
        self,
        indicator_names: List[str],
        df: pd.DataFrame,
        params_map: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Dict[str, pd.Series]]:
        """Calculate several indicators and return {name: {series_name: Series}}."""
        params_map = params_map or {}
        results = {}
        for name in indicator_names:
            results[name] = self.calculate(name, df, params=params_map.get(name))
        return results

    # ------------------------------------------------------------------
    # Add indicator traces to an existing figure
    # ------------------------------------------------------------------

    def add_indicator_to_figure(
        self,
        fig: go.Figure,
        indicator_name: str,
        df: pd.DataFrame,
        params: Optional[Dict[str, Any]] = None,
        row: int = 1,
        col: int = 1,
    ) -> go.Figure:
        """Overlay an indicator on an existing Plotly figure.

        Trend / volatility indicators are added to the price subplot.
        Momentum / volume indicators are added to a new or existing subplot.
        """
        entry = INDICATOR_REGISTRY[indicator_name]
        results = self.calculate(indicator_name, df, params=params)
        x = df["date"] if "date" in df.columns else df.index

        if indicator_name in ("sma", "ema"):
            series = results[indicator_name]
            fig.add_trace(go.Scatter(
                x=x, y=series,
                mode="lines",
                name=f"{indicator_name.upper()}({(params or entry['default_params']).get('period', '')})",
                line=dict(width=1.5),
            ), row=row, col=col)

        elif indicator_name == "macd":
            fig.add_trace(go.Scatter(
                x=x, y=results["macd_line"],
                mode="lines", name="MACD", line=dict(width=1.5),
            ), row=row, col=col)
            fig.add_trace(go.Scatter(
                x=x, y=results["signal_line"],
                mode="lines", name="Signal", line=dict(width=1.5),
            ), row=row, col=col)
            fig.add_trace(go.Bar(
                x=x, y=results["histogram"],
                name="Histogram", marker_color="rgba(100,100,100,0.5)",
            ), row=row, col=col)

        elif indicator_name == "rsi":
            fig.add_trace(go.Scatter(
                x=x, y=results["rsi"],
                mode="lines", name="RSI", line=dict(width=1.5),
            ), row=row, col=col)

        elif indicator_name == "bollinger_bands":
            fig.add_trace(go.Scatter(
                x=x, y=results["bb_upper"],
                mode="lines", name="BB Upper",
                line=dict(width=1, dash="dash"),
            ), row=row, col=col)
            fig.add_trace(go.Scatter(
                x=x, y=results["bb_lower"],
                mode="lines", name="BB Lower",
                line=dict(width=1, dash="dash"),
                fill="tonexty", fillcolor="rgba(0,100,200,0.1)",
            ), row=row, col=col)

        elif indicator_name in ("obv", "vwap"):
            series = results[indicator_name]
            fig.add_trace(go.Scatter(
                x=x, y=series,
                mode="lines", name=indicator_name.upper(),
                line=dict(width=1.5),
            ), row=row, col=col)

        elif indicator_name == "rps":
            fig.add_trace(go.Scatter(
                x=x, y=results["rps"],
                mode="lines", name="RPS",
                line=dict(width=1.5),
            ), row=row, col=col)

        return fig

    # ------------------------------------------------------------------
    # List available indicators
    # ------------------------------------------------------------------

    def list_indicators(self) -> List[Dict[str, Any]]:
        """List all built-in and custom indicators."""
        built_in = [
            {
                "name": name,
                "display_name": entry["display_name"],
                "category": entry["category"],
                "default_params": entry["default_params"],
                "is_builtin": True,
            }
            for name, entry in INDICATOR_REGISTRY.items()
        ]
        custom = [
            {
                "name": ci["name"],
                "display_name": ci["description"] or ci["name"],
                "category": "custom",
                "default_params": {},
                "is_builtin": False,
                "script_path": ci["path"],
            }
            for ci in list_custom_indicators()
        ]
        return built_in + custom

    def get_indicator_info(self, indicator_name: str) -> Optional[Dict[str, Any]]:
        """Get info about a specific indicator."""
        if indicator_name in INDICATOR_REGISTRY:
            entry = INDICATOR_REGISTRY[indicator_name]
            return {
                "name": indicator_name,
                "display_name": entry["display_name"],
                "category": entry["category"],
                "default_params": entry["default_params"],
                "is_builtin": True,
            }
        return None

    # ------------------------------------------------------------------
    # Custom indicator execution
    # ------------------------------------------------------------------

    def run_custom_indicator(
        self,
        script_path: str,
        df: pd.DataFrame,
        params: Optional[Dict[str, Any]] = None,
    ) -> Optional[pd.DataFrame]:
        """Run a custom indicator script and return the result."""
        return execute_custom_indicator(script_path, df, params)
