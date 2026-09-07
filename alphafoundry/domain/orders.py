"""Order lifecycle domain models: ParentOrder, ChildOrder, Fill."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .enums import OrderStatus, OrderType, Side, Urgency


class ParentOrder(BaseModel):
    """Research-level trading intent awaiting risk approval and slicing."""

    model_config = ConfigDict(frozen=True)

    parent_order_id: UUID = Field(default_factory=uuid.uuid4)
    session_id: UUID
    instrument_id: UUID
    signal_id: UUID | None = None  # signal that prompted this order
    side: Side
    target_qty: int | None = Field(default=None, gt=0)
    target_notional: Decimal | None = Field(default=None, gt=Decimal("0"))
    algo: str = Field(description="TWAP | VWAP | POV | IS | MARKET")
    urgency: Urgency = Urgency.MEDIUM
    price_limit: Decimal | None = None
    status: OrderStatus = OrderStatus.PENDING_RISK
    risk_decision_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class ChildOrder(BaseModel):
    """One slice of a ParentOrder submitted to the execution simulator."""

    model_config = ConfigDict(frozen=True)

    child_order_id: UUID = Field(default_factory=uuid.uuid4)
    parent_order_id: UUID
    sequence_num: int = Field(ge=0)
    instrument_id: UUID
    side: Side
    qty: int = Field(gt=0)
    limit_price: Decimal | None = None
    order_type: OrderType = OrderType.MARKET
    status: OrderStatus = OrderStatus.PENDING
    created_at: datetime


class Fill(BaseModel):
    """A simulated execution against a ChildOrder."""

    model_config = ConfigDict(frozen=True)

    fill_id: UUID = Field(default_factory=uuid.uuid4)
    child_order_id: UUID
    fill_qty: int = Field(gt=0)
    fill_price: Decimal = Field(gt=Decimal("0"))
    simulated_impact: Decimal = Field(
        default=Decimal("0"),
        description="Estimated price impact applied during simulation",
    )
    fill_timestamp: datetime
    rng_seed: int | None = None  # seed used for any randomness in simulation
