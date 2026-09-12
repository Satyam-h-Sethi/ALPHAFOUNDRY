"""Configuration models for the execution simulator."""

from __future__ import annotations

from decimal import Decimal
from typing import Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator

from alphafoundry.domain.enums import Urgency


def _default_urgency_weights() -> dict[Urgency, list[float]]:
    return {
        Urgency.LOW: [0.20, 0.20, 0.20, 0.20, 0.20],
        Urgency.MEDIUM: [0.35, 0.25, 0.20, 0.12, 0.08],
        Urgency.HIGH: [0.50, 0.30, 0.15, 0.05, 0.00],
    }


class SlicerConfig(BaseModel):
    """Configuration for order slicing algorithms."""

    model_config = ConfigDict(frozen=True)

    twap_num_buckets: int = Field(default=5, ge=1)
    vwap_num_buckets: int = Field(default=5, ge=1)
    pov_rate: float = Field(default=0.10, gt=0.0, le=1.0)
    pov_window_seconds: float = Field(default=60.0, gt=0.0)
    urgency_weights: Mapping[Urgency, list[float]] = Field(
        default_factory=_default_urgency_weights
    )

    @field_validator("urgency_weights")
    @classmethod
    def _validate_urgency_weights(
        cls, v: Mapping[Urgency, list[float]]
    ) -> Mapping[Urgency, list[float]]:
        for urgency, weights in v.items():
            if not weights:
                raise ValueError(f"Urgency {urgency} must have non-empty weights")
            if any(w < 0.0 for w in weights):
                raise ValueError(f"Urgency {urgency} has negative weight")
            total = sum(weights)
            if abs(total - 1.0) > 1e-4:
                raise ValueError(
                    f"Urgency {urgency} weights must sum to 1.0, got {total}"
                )
        return v


class ImpactConfig(BaseModel):
    """Configuration for the linear market impact model."""

    model_config = ConfigDict(frozen=True)

    eta: float = Field(
        default=0.1,
        ge=0.0,
        description="Linear impact coefficient: impact = eta * sigma * sqrt(child_qty / ADV) * price",
    )
    default_sigma: float = Field(
        default=0.02,
        ge=0.0,
        description="Default annualized or daily volatility if instrument value missing",
    )
    default_adv: int = Field(
        default=100_000,
        gt=0,
        description="Default average daily volume (shares) if instrument ADV missing",
    )


class ExecutionConfig(BaseModel):
    """Top-level configuration for the execution simulator."""

    model_config = ConfigDict(frozen=True)

    slicer: SlicerConfig = Field(default_factory=SlicerConfig)
    impact: ImpactConfig = Field(default_factory=ImpactConfig)
    allow_partial_fills: bool = True
    reschedule_residuals: bool = True
    default_rng_seed: int | None = 42
