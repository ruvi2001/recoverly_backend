"""
Common Pydantic schemas shared across services
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class UserBase(BaseModel):
    """Base user schema"""
    user_id: str = Field(..., description="Unique user identifier")


class MessageBase(BaseModel):
    """Base message schema"""
    message_id: int
    user_id: str
    message_text: str
    timestamp: datetime
    conversation_type: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response"""
    service: str
    status: str = "healthy"
    timestamp: datetime = Field(default_factory=datetime.now)
    version: str = "1.0.0"


class ErrorResponse(BaseModel):
    """Error response schema"""
    error: str
    detail: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)
