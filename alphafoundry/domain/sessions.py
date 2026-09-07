"""Session domain model."""

from __future__ import annotations

import uuid
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .enums import SessionStatus, SessionType


class Session(BaseModel):
    """A contiguous window during which a Venue accepts orders."""

    model_config = ConfigDict(frozen=True)

    session_id: UUID = Field(default_factory=uuid.uuid4)
    venue_id: str
    session_type: SessionType
    open_time: datetime  # timezone-aware UTC
    close_time: datetime  # timezone-aware UTC
    status: SessionStatus = SessionStatus.SCHEDULED

    @model_validator(mode="after")
    def _times_are_aware_and_ordered(self) -> Session:
        if self.open_time.tzinfo is None:
            raise ValueError("open_time must be timezone-aware")
        if self.close_time.tzinfo is None:
            raise ValueError("close_time must be timezone-aware")
        if self.close_time <= self.open_time:
            raise ValueError("close_time must be after open_time")
        return self
