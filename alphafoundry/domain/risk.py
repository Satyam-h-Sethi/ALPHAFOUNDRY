"""Risk domain models: limits, decisions, violations."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PositionLimit(BaseModel):
    """Gross and net position limits for one instrument or the whole portfolio."""

    model_config = ConfigDict(frozen=True)

    instrument_id: UUID | None = None  # None = portfolio-level
    max_gross_qty: int | None = None
    max_net_qty: int | None = None
    max_gross_notional: Decimal | None = None


class RiskConfig(BaseModel):
    """Full pre-trade risk configuration injected into the Risk Engine."""

    model_config = ConfigDict(frozen=True)

    position_limits: list[PositionLimit] = Field(default_factory=list)
    max_order_qty: int | None = None
    max_order_notional: Decimal | None = None
    max_adv_participation: float = Field(default=0.10, gt=0.0, le=1.0)
    max_quote_age_seconds: float = Field(default=60.0, gt=0.0)
    kill_switch_enabled: bool = False


class RuleViolation(BaseModel):
    """Records a single failed risk rule."""

    model_config = ConfigDict(frozen=True)

    rule: str
    measured_value: float
    limit_value: float
    unit: str = ""


class RiskDecision(BaseModel):
    """Result of one pre-trade risk evaluation."""

    model_config = ConfigDict(frozen=True)

    risk_decision_id: UUID = Field(default_factory=uuid.uuid4)
    parent_order_id: UUID
    approved: bool
    violations: list[RuleViolation] = Field(default_factory=list)
    evaluated_at: datetime
