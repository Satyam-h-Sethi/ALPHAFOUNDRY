"""Configuration for the Phase 03 Analytics layer."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class AnalyticsConfig(BaseModel):
    """Configuration for Feature Engine, Signal Engine, Regime Detector, and Ranking."""

    model_config = ConfigDict(frozen=True)

    # Version tags
    feature_version: str = "1.0.0"
    signal_version: str = "1.0.0"
    detector_version: str = "1.0.0"

    # Persistence
    db_path: str = ":memory:"

    # Signal Engine parameters
    signal_threshold: float = Field(
        default=0.1,
        ge=0.0,
        le=1.0,
        description="Threshold score magnitude above which Direction is LONG/SHORT instead of NEUTRAL.",
    )
    feature_weights: dict[str, float] = Field(
        default_factory=lambda: {
            "returns_1": 0.25,
            "momentum_10": 0.35,
            "volume_ratio_10": 0.15,
            "realised_vol_10": -0.25,
        },
        description="Deterministic weights for linear signal combination.",
    )

    # Feature lookback windows (number of bars)
    returns_lookback: int = Field(default=1, ge=1)
    returns_5_lookback: int = Field(default=5, ge=1)
    momentum_lookback: int = Field(default=10, ge=1)
    volatility_lookback: int = Field(default=10, ge=2)
    volume_lookback: int = Field(default=10, ge=1)

    # Regime Detector thresholds
    trend_threshold: float = Field(
        default=0.005,
        ge=0.0,
        description="Minimum absolute price drift to classify as TRENDING.",
    )
    high_vol_threshold: float = Field(
        default=0.02,
        ge=0.0,
        description="Realised volatility threshold above which regime is HIGH_VOL.",
    )
    low_vol_threshold: float = Field(
        default=0.005,
        ge=0.0,
        description="Realised volatility threshold below which regime is LOW_VOL.",
    )
