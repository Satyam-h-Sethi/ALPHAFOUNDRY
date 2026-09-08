"""Signal Engine — deterministic weighted linear combiner.

Generates scored, directional signals with full feature lineage and zero ML.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from alphafoundry.analytics.config import AnalyticsConfig
from alphafoundry.domain import Direction, FeatureLineageItem, FeatureVector, Signal


class SignalEngine:
    """Combines feature vectors into directional trading signals with full lineage."""

    def __init__(self, config: AnalyticsConfig | None = None) -> None:
        self._config = config or AnalyticsConfig()

    @property
    def config(self) -> AnalyticsConfig:
        return self._config

    def generate_signal(
        self,
        feature_vector: FeatureVector,
        supersedes: UUID | None = None,
    ) -> Signal:
        """Evaluate a FeatureVector to produce a deterministic Signal record.

        Formula:
          raw_score = sum(weight_i * feature_i)
          score = clip(raw_score, -1.0, 1.0)
          direction = LONG if score > threshold, SHORT if score < -threshold, else NEUTRAL
          confidence = min(1.0, abs(score))
        """
        lineage: list[FeatureLineageItem] = []
        raw_score = 0.0

        for feat_name, weight in self._config.feature_weights.items():
            val = float(feature_vector.features.get(feat_name, 0.0))
            contribution = weight * val
            raw_score += contribution
            lineage.append(
                FeatureLineageItem(
                    feature_name=feat_name,
                    weight=float(weight),
                    value=val,
                )
            )

        # Bound score in [-1.0, 1.0]
        score = max(-1.0, min(1.0, raw_score))

        # Directional mapping
        if score > self._config.signal_threshold:
            direction = Direction.LONG
        elif score < -self._config.signal_threshold:
            direction = Direction.SHORT
        else:
            direction = Direction.NEUTRAL

        # Confidence bounded in [0.0, 1.0]
        confidence = min(1.0, max(0.0, abs(score)))

        return Signal(
            instrument_id=feature_vector.instrument_id,
            as_of=feature_vector.as_of,
            emitted_at=datetime.now(UTC),
            direction=direction,
            score=round(score, 6),
            confidence=round(confidence, 6),
            lineage=lineage,
            signal_version=self._config.signal_version,
            supersedes=supersedes,
        )
