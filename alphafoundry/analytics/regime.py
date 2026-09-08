"""Regime Detector — price and volume-based market regime classification.

Classifies market states into TRENDING, MEAN_REVERTING, HIGH_VOL, LOW_VOL, or UNKNOWN.
Note: Regime outputs serve strictly as advisory metadata and never override signal or risk logic.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from alphafoundry.analytics.config import AnalyticsConfig
from alphafoundry.analytics.features import compute_realised_volatility, compute_returns
from alphafoundry.domain import OHLCBar, RegimeState, RegimeType


class RegimeDetector:
    """Evaluates historical market dynamics to produce advisory market regime states."""

    def __init__(self, config: AnalyticsConfig | None = None) -> None:
        self._config = config or AnalyticsConfig()

    @property
    def config(self) -> AnalyticsConfig:
        return self._config

    def detect_regime(
        self,
        instrument_id: UUID,
        as_of: datetime,
        bars: Sequence[OHLCBar],
    ) -> RegimeState:
        """Classify current market regime as-of a point in time (zero lookahead)."""
        as_of_utc = as_of if as_of.tzinfo is not None else as_of.replace(tzinfo=UTC)

        valid_bars = [
            b for b in bars if (b.bar_close if b.bar_close.tzinfo else b.bar_close.replace(tzinfo=UTC)) <= as_of_utc
        ]
        valid_bars.sort(key=lambda b: b.bar_close)

        if len(valid_bars) < 2:
            return RegimeState(
                instrument_id=instrument_id,
                as_of=as_of_utc,
                regime=RegimeType.UNKNOWN,
                confidence=0.0,
                metrics={
                    "realised_vol": 0.0,
                    "price_drift": 0.0,
                    "bar_count": float(len(valid_bars)),
                },
                detector_version=self._config.detector_version,
            )

        prices = [float(b.close) for b in valid_bars]
        volumes = [float(b.volume) for b in valid_bars]

        vol_lookback = min(len(prices) - 1, self._config.volatility_lookback)
        trend_lookback = min(len(prices) - 1, self._config.momentum_lookback)

        realised_vol = compute_realised_volatility(prices, lookback=vol_lookback)
        price_drift = compute_returns(prices, lookback=trend_lookback)
        mean_volume = sum(volumes) / len(volumes) if volumes else 0.0

        # Classification decision tree
        if realised_vol >= self._config.high_vol_threshold:
            regime = RegimeType.HIGH_VOL
            confidence = min(1.0, max(0.5, realised_vol / (self._config.high_vol_threshold * 1.5)))
        elif abs(price_drift) >= self._config.trend_threshold:
            regime = RegimeType.TRENDING
            confidence = min(1.0, max(0.5, abs(price_drift) / (self._config.trend_threshold * 1.5)))
        elif realised_vol <= self._config.low_vol_threshold:
            regime = RegimeType.LOW_VOL
            confidence = min(
                1.0,
                max(0.5, 1.0 - (realised_vol / max(1e-6, self._config.low_vol_threshold * 2.0))),
            )
        else:
            regime = RegimeType.MEAN_REVERTING
            confidence = 0.70

        return RegimeState(
            instrument_id=instrument_id,
            as_of=as_of_utc,
            regime=regime,
            confidence=round(confidence, 4),
            metrics={
                "realised_vol": round(realised_vol, 6),
                "price_drift": round(price_drift, 6),
                "mean_volume": round(mean_volume, 2),
                "bar_count": float(len(valid_bars)),
            },
            detector_version=self._config.detector_version,
        )
