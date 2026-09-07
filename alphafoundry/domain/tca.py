"""TCA domain model."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .enums import BenchmarkType


class TCAReport(BaseModel):
    """Execution quality metrics for one ParentOrder."""

    model_config = ConfigDict(frozen=True)

    tca_report_id: UUID = Field(default_factory=uuid.uuid4)
    parent_order_id: UUID
    benchmark_type: BenchmarkType
    benchmark_price: Decimal
    execution_price: Decimal  # fill VWAP
    realized_slippage: Decimal  # execution_price - benchmark_price (signed)
    spread_cost: Decimal = Decimal("0")
    impact_cost: Decimal = Decimal("0")
    timing_cost: Decimal = Decimal("0")
    implementation_shortfall: Decimal = Decimal("0")
    total_qty: int = Field(ge=0)
    fill_count: int = Field(ge=0)
    execution_duration_seconds: float = Field(ge=0.0)
    computed_at: datetime
