"""Unit tests for SignalEngine (linear combiner, score bounds, lineage, direction)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from alphafoundry.analytics.config import AnalyticsConfig
from alphafoundry.analytics.signals import SignalEngine
from alphafoundry.domain import Direction, FeatureVector


def test_signal_engine_deterministic_combiner() -> None:
    config = AnalyticsConfig(
        signal_threshold=0.1,
        feature_weights={
            "returns_1": 0.5,
            "momentum_10": 0.5,
        },
    )
    engine = SignalEngine(config=config)
    inst_id = uuid4()
    as_of = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)

    # 1. LONG signal
    fv_long = FeatureVector(
        instrument_id=inst_id,
        as_of=as_of,
        computed_at=datetime.now(UTC),
        feature_version="1.0.0",
        features={"returns_1": 0.4, "momentum_10": 0.6},
    )
    sig_long = engine.generate_signal(fv_long)
    # score = 0.5 * 0.4 + 0.5 * 0.6 = 0.5
    assert sig_long.direction == Direction.LONG
    assert pytest.approx(sig_long.score, rel=1e-5) == 0.5
    assert pytest.approx(sig_long.confidence, rel=1e-5) == 0.5
    assert len(sig_long.lineage) == 2

    # Verify lineage items
    lin_map = {item.feature_name: item for item in sig_long.lineage}
    assert lin_map["returns_1"].weight == 0.5
    assert lin_map["returns_1"].value == 0.4
    assert lin_map["momentum_10"].weight == 0.5
    assert lin_map["momentum_10"].value == 0.6

    # 2. SHORT signal
    fv_short = FeatureVector(
        instrument_id=inst_id,
        as_of=as_of,
        computed_at=datetime.now(UTC),
        feature_version="1.0.0",
        features={"returns_1": -0.4, "momentum_10": -0.6},
    )
    sig_short = engine.generate_signal(fv_short)
    assert sig_short.direction == Direction.SHORT
    assert pytest.approx(sig_short.score, rel=1e-5) == -0.5
    assert pytest.approx(sig_short.confidence, rel=1e-5) == 0.5

    # 3. NEUTRAL signal (below threshold)
    fv_neutral = FeatureVector(
        instrument_id=inst_id,
        as_of=as_of,
        computed_at=datetime.now(UTC),
        feature_version="1.0.0",
        features={"returns_1": 0.05, "momentum_10": 0.05},
    )
    sig_neutral = engine.generate_signal(fv_neutral)
    # score = 0.05 < 0.1 threshold
    assert sig_neutral.direction == Direction.NEUTRAL
    assert pytest.approx(sig_neutral.score, rel=1e-5) == 0.05
    assert pytest.approx(sig_neutral.confidence, rel=1e-5) == 0.05


def test_signal_score_bounding() -> None:
    config = AnalyticsConfig(
        feature_weights={"returns_1": 2.0, "momentum_10": 2.0}
    )
    engine = SignalEngine(config=config)
    inst_id = uuid4()
    as_of = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)

    # Exceeding +1.0
    fv_huge = FeatureVector(
        instrument_id=inst_id,
        as_of=as_of,
        computed_at=datetime.now(UTC),
        feature_version="1.0.0",
        features={"returns_1": 10.0, "momentum_10": 10.0},
    )
    sig = engine.generate_signal(fv_huge)
    assert sig.score == 1.0
    assert sig.confidence == 1.0
    assert sig.direction == Direction.LONG

    # Exceeding -1.0
    fv_neg_huge = FeatureVector(
        instrument_id=inst_id,
        as_of=as_of,
        computed_at=datetime.now(UTC),
        feature_version="1.0.0",
        features={"returns_1": -10.0, "momentum_10": -10.0},
    )
    sig_neg = engine.generate_signal(fv_neg_huge)
    assert sig_neg.score == -1.0
    assert sig_neg.confidence == 1.0
    assert sig_neg.direction == Direction.SHORT
