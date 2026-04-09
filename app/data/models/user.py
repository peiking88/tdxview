"""
User data model.
"""

from typing import Optional
from pydantic import BaseModel, Field


class UserModel(BaseModel):
    """Represents a user record."""

    id: Optional[int] = None
    username: str
    email: Optional[str] = None
    role: str = Field(default="user")
    is_active: bool = Field(default=True)
    preferences: Optional[dict] = None
