"""Session domain model."""

from __future__ import annotations

import uuid
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .enums import SessionStatus, SessionType, SimulationSessionStatus


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


class SimulationSession(BaseModel):
    """Controlled execution context grouping parent orders for research/backtesting."""

    model_config = ConfigDict(frozen=True)

    simulation_session_id: UUID = Field(default_factory=uuid.uuid4)
    name: str = Field(default="default_sim_session")
    window_start: datetime  # timezone-aware UTC
    window_end: datetime  # timezone-aware UTC
    adapter_id: str = "synthetic"
    universe_id: str = "NSE_NIFTY50"
    algo_config: dict[str, object] = Field(default_factory=dict)
    status: SimulationSessionStatus = SimulationSessionStatus.CREATED
    created_at: datetime
    updated_at: datetime | None = None

    @model_validator(mode="after")
    def _window_is_valid(self) -> SimulationSession:
        if self.window_start.tzinfo is None:
            raise ValueError("window_start must be timezone-aware")
        if self.window_end.tzinfo is None:
            raise ValueError("window_end must be timezone-aware")
        if self.window_end < self.window_start:
            raise ValueError("window_end must be >= window_start")
        return self
