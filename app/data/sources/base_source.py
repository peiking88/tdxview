"""
Data source base class — defines the interface for all data sources.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import pandas as pd


class DataSourceBase(ABC):
    """Abstract base class for data sources."""

    @abstractmethod
    def fetch(
        self,
        symbols: List[str],
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        **kwargs: Any,
    ) -> pd.DataFrame:
        """Fetch data for the given symbols and date range."""
        ...

    @abstractmethod
    def validate_connection(self) -> bool:
        """Check whether the data source is reachable."""
        ...
