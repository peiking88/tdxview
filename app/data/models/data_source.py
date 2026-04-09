"""
Data source configuration model.
"""

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class DataSourceModel(BaseModel):
    """Represents a data source configuration record."""

    id: Optional[int] = None
    name: str
    type: str  # 'tdxdata', 'csv', 'api'
    config: Dict[str, Any] = Field(default_factory=dict)
    enabled: bool = Field(default=True)
    priority: int = Field(default=1)
