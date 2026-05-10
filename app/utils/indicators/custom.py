"""
Custom indicator execution environment.

Allows users to provide Python scripts that define a `calculate(df, **params)`
function. Scripts are loaded from the plugins/indicators directory or
uploaded at runtime.
"""

import importlib.util
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import pandas as pd

from app.config.settings import get_settings


def load_indicator_script(script_path: str) -> Optional[Callable]:
    """Load a Python script and return its `calculate` function.

    The script must define a top-level function:

        def calculate(df: pd.DataFrame, **params) -> pd.DataFrame:
            ...

    Returns None if the script cannot be loaded or has no `calculate` function.
    """
    path = Path(script_path)
    if not path.exists():
        return None

    module_name = f"custom_indicator_{path.stem}"
    try:
        spec = importlib.util.spec_from_file_location(module_name, str(path))
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return getattr(module, "calculate", None)
    except Exception:
        return None


def execute_custom_indicator(
    script_path: str,
    df: pd.DataFrame,
    params: Optional[Dict[str, Any]] = None,
) -> Optional[pd.DataFrame]:
    """Execute a custom indicator script and return its result.

    Returns None on failure.
    """
    calc_fn = load_indicator_script(script_path)
    if calc_fn is None:
        return None
    try:
        return calc_fn(df, **(params or {}))
    except Exception:
        return None


def list_custom_indicators() -> list[Dict[str, str]]:
    """Scan the custom indicator directory and list available scripts.

    Returns a list of dicts with keys: name, path, description.
    """
    settings = get_settings()
    custom_dir = Path(settings.indicators.custom_path)
    if not custom_dir.exists():
        return []

    results = []
    for py_file in sorted(custom_dir.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        # Try to extract a docstring description
        description = ""
        try:
            content = py_file.read_text(encoding="utf-8")
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith('"""') or stripped.startswith("'''"):
                    end = stripped[3:]
                    if end.endswith('"""') or end.endswith("'''"):
                        description = end[3:-3].strip() if len(end) > 3 else ""
                    break
                elif stripped.startswith("#"):
                    description = stripped.lstrip("# ").strip()
                    break
        except Exception:
            pass

        results.append({
            "name": py_file.stem,
            "path": str(py_file),
            "description": description,
        })
    return results
