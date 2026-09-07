"""Venue and Instrument domain models."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .enums import InstrumentType


class Venue(BaseModel):
    """A trading exchange or market centre."""

    model_config = ConfigDict(frozen=True)

    venue_id: str = Field(description="Canonical short code, e.g. 'NSE_EQ'")
    name: str
    timezone: str = Field(default="Asia/Kolkata")


class Instrument(BaseModel):
    """A tradable (or reference) entity listed on a Venue.

    ``instrument_id`` is the stable platform key.  ``symbol`` is venue-local
    and must never be used as a join key across venues.
    """

    model_config = ConfigDict(frozen=True)

    instrument_id: UUID = Field(default_factory=uuid.uuid4)
    isin: str | None = Field(default=None, min_length=12, max_length=12)
    symbol: str = Field(min_length=1, max_length=32)
    venue_id: str
    instrument_type: InstrumentType
    lot_size: int = Field(default=1, ge=1)
    tick_size: Decimal = Field(default=Decimal("0.05"), gt=Decimal("0"))
    expiry: date | None = None  # futures / options only
    strike: Decimal | None = None  # options only
    underlying_id: UUID | None = None  # derivatives only
    currency: str = Field(default="INR", min_length=3, max_length=3)
    is_active: bool = True

    @field_validator("isin")
    @classmethod
    def _isin_alphanumeric(cls, v: str | None) -> str | None:
        if v is not None and not v.isalnum():
            raise ValueError("ISIN must be alphanumeric")
        return v

    @field_validator("strike")
    @classmethod
    def _strike_requires_option(cls, v: Decimal | None, info: object) -> Decimal | None:  # noqa: ARG002
        # Validation of cross-field constraints is done in model_validator if needed;
        # here we just ensure non-negative when present.
        if v is not None and v <= Decimal("0"):
            raise ValueError("strike must be positive")
        return v
