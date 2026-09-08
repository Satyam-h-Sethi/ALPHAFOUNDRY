"""Analytics domain models: FeatureVector, Signal, InstrumentRank."""

from __future__ import annotations

import uuid
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .enums import Direction, RegimeType


class FeatureLineageItem(BaseModel):
    """One feature's contribution recorded in Signal.lineage."""

    model_config = ConfigDict(frozen=True)

    feature_name: str
    weight: float
    value: float


class FeatureVector(BaseModel):
    """Named numerical features computed from market data for one instrument."""

    model_config = ConfigDict(frozen=True)

    feature_vector_id: UUID = Field(default_factory=uuid.uuid4)
    instrument_id: UUID
    as_of: datetime  # market timestamp this vector reflects
    computed_at: datetime  # wall-clock time of computation
    feature_version: str  # version tag of the feature-engine config
    features: dict[str, float] = Field(default_factory=dict)


class Signal(BaseModel):
    """Scored, directional view on an instrument with full lineage."""

    model_config = ConfigDict(frozen=True)

    signal_id: UUID = Field(default_factory=uuid.uuid4)
    instrument_id: UUID
    as_of: datetime
    emitted_at: datetime
    direction: Direction
    score: float = Field(ge=-1.0, le=1.0, description="[-1, 1]; magnitude = conviction")
    confidence: float = Field(ge=0.0, le=1.0)
    lineage: list[FeatureLineageItem] = Field(default_factory=list)
    signal_version: str
    supersedes: UUID | None = None  # signal_id this corrects


class InstrumentRank(BaseModel):
    """Cross-sectional rank of one instrument within a universe."""

    model_config = ConfigDict(frozen=True)

    rank_id: UUID = Field(default_factory=uuid.uuid4)
    instrument_id: UUID
    universe_id: str
    as_of: datetime
    rank: int = Field(ge=1)
    score: float


class RegimeState(BaseModel):
    """Market regime classification advisory output."""

    model_config = ConfigDict(frozen=True)

    regime_id: UUID = Field(default_factory=uuid.uuid4)
    instrument_id: UUID
    as_of: datetime
    regime: RegimeType
    confidence: float = Field(ge=0.0, le=1.0)
    metrics: dict[str, float] = Field(default_factory=dict)
    detector_version: str


class Explanation(BaseModel):
    """AI-generated natural-language explanation for a domain object.

    Read-only artefact — the AI layer may create these but may not use them
    to alter any financial object.
    """

    model_config = ConfigDict(frozen=True)

    explanation_id: UUID = Field(default_factory=uuid.uuid4)
    subject_type: str  # SubjectType enum value kept as str to avoid import cycle
    subject_id: UUID
    narrative: str
    model_version: str
    input_refs: list[UUID] = Field(default_factory=list)
    generated_at: datetime


class SessionSummary(BaseModel):
    """AI-generated narrative summary for a simulation session."""

    model_config = ConfigDict(frozen=True)

    summary_id: UUID = Field(default_factory=uuid.uuid4)
    session_id: UUID
    narrative: str
    model_version: str
    generated_at: datetime


class AnomalyReport(BaseModel):
    """Advisory anomaly flag produced by the AI assistant.

    Does NOT block any order or signal; advisory use only.
    """

    model_config = ConfigDict(frozen=True)

    anomaly_id: UUID = Field(default_factory=uuid.uuid4)
    severity: str  # AnomalySeverity enum value
    description: str
    context_refs: list[UUID] = Field(default_factory=list)
    model_version: str
    generated_at: datetime
    reviewed: bool = False

    @field_validator("severity")
    @classmethod
    def _valid_severity(cls, v: str) -> str:
        valid = {"INFO", "WARN", "ALERT"}
        if v not in valid:
            raise ValueError(f"severity must be one of {valid}")
        return v
