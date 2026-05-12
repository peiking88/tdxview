"""
Import record model — tracks data import state per stock and data type.
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class DataType(str, Enum):
    HISTORY = "history"
    REALTIME = "realtime"
    TICK = "tick"
    FINANCIAL = "financial"
    F10 = "f10"
    BASIC = "basic"
    FACTOR = "factor"


class ImportStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class ImportRecordModel(BaseModel):
    """Represents a single data import record."""

    id: Optional[int] = None
    symbol: str
    data_type: DataType
    status: ImportStatus = ImportStatus.SUCCESS
    record_count: int = 0
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    storage_key: Optional[str] = None

    @property
    def parquet_path(self) -> Optional[str]:
        return self.storage_key

    @parquet_path.setter
    def parquet_path(self, value: Optional[str]):
        self.storage_key = value
    file_size_bytes: Optional[int] = None
    error_message: Optional[str] = None
    import_duration_ms: Optional[int] = None
    imported_at: Optional[str] = None
