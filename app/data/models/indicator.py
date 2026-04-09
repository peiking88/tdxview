"""
Indicator definition model.
"""

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class IndicatorModel(BaseModel):
    """Represents a technical indicator definition."""

    id: Optional[int] = None
    name: str
    display_name: str
    category: str  # 'trend', 'momentum', 'volatility', 'volume', 'custom'
    description: Optional[str] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)
    script_path: Optional[str] = None
    is_builtin: bool = Field(default=True)
    is_enabled: bool = Field(default=True)
