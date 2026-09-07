"""Market data event domain models: Quote, Trade, OHLCBar."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .enums import SessionStatus, TradeSide


class Quote(BaseModel):
    """Level-1 best bid/ask snapshot."""

    model_config = ConfigDict(frozen=True)

    quote_id: UUID = Field(default_factory=uuid.uuid4)
    idempotency_key: str  # "{venue_id}:{sequence_id}"
    instrument_id: UUID
    venue_id: str
    timestamp: datetime  # event time, UTC
    received_at: datetime  # ingest wall-clock, UTC
    sequence_id: int = Field(ge=0)
    bid_price: Decimal = Field(gt=Decimal("0"))
    bid_qty: int = Field(gt=0)
    ask_price: Decimal = Field(gt=Decimal("0"))
    ask_qty: int = Field(gt=0)
    last_trade_price: Decimal | None = Field(default=None, gt=Decimal("0"))
    session_status: SessionStatus = SessionStatus.OPEN
    is_stale: bool = False

    @model_validator(mode="after")
    def _spread_non_negative(self) -> Quote:
        if self.ask_price < self.bid_price:
            raise ValueError("ask_price must be >= bid_price")
        return self


class Trade(BaseModel):
    """A single executed transaction as reported by the venue."""

    model_config = ConfigDict(frozen=True)

    trade_id: UUID = Field(default_factory=uuid.uuid4)
    idempotency_key: str
    instrument_id: UUID
    venue_id: str
    timestamp: datetime
    received_at: datetime
    sequence_id: int = Field(ge=0)
    price: Decimal = Field(gt=Decimal("0"))
    qty: int = Field(gt=0)
    side: TradeSide = TradeSide.UNKNOWN


class OHLCBar(BaseModel):
    """Aggregated price bar over a fixed time interval."""

    model_config = ConfigDict(frozen=True)

    bar_id: UUID = Field(default_factory=uuid.uuid4)
    instrument_id: UUID
    venue_id: str
    freq: str = Field(description="'1m', '5m', '15m', '1d', …", min_length=1)
    bar_open: datetime  # interval start, UTC
    bar_close: datetime  # interval end, UTC
    open: Decimal = Field(gt=Decimal("0"))
    high: Decimal = Field(gt=Decimal("0"))
    low: Decimal = Field(gt=Decimal("0"))
    close: Decimal = Field(gt=Decimal("0"))
    volume: int = Field(ge=0)
    num_trades: int = Field(ge=0)
    vwap: Decimal | None = Field(default=None, gt=Decimal("0"))
    is_complete: bool = True

    @model_validator(mode="after")
    def _ohlc_consistency(self) -> OHLCBar:
        if self.high < self.open or self.high < self.close:
            raise ValueError("high must be >= open and close")
        if self.low > self.open or self.low > self.close:
            raise ValueError("low must be <= open and close")
        if self.high < self.low:
            raise ValueError("high must be >= low")
        if self.bar_close <= self.bar_open:
            raise ValueError("bar_close must be after bar_open")
        return self
