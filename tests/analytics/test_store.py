"""Unit and integration tests for AnalyticsStore (DuckDB persistence)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import duckdb
import pytest

from alphafoundry.analytics.store import AnalyticsStore
from alphafoundry.domain import (
    Direction,
    FeatureLineageItem,
    FeatureVector,
    InstrumentRank,
    RegimeState,
    RegimeType,
    Signal,
)


@pytest.fixture
def store() -> AnalyticsStore:
    conn = duckdb.connect(":memory:")
    return AnalyticsStore(conn=conn)


def test_store_feature_vectors(store: AnalyticsStore) -> None:
    inst_id = uuid4()
    as_of = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)

    fv = FeatureVector(
        instrument_id=inst_id,
        as_of=as_of,
        computed_at=datetime.now(UTC),
        feature_version="1.0.0",
        features={"returns_1": 0.05, "momentum_10": 1.2},
    )

    store.insert_feature_vector(fv)
    assert store.count_feature_vectors() == 1

    fetched = store.fetch_feature_vectors(instrument_id=inst_id)
    assert len(fetched) == 1
    assert fetched[0]["features"]["returns_1"] == 0.05
    assert fetched[0]["features"]["momentum_10"] == 1.2


def test_store_unregistered_feature_rejected(store: AnalyticsStore) -> None:
    inst_id = uuid4()
    as_of = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)

    fv = FeatureVector(
        instrument_id=inst_id,
        as_of=as_of,
        computed_at=datetime.now(UTC),
        feature_version="1.0.0",
        features={"unregistered_feature_x": 123.45},
    )

    with pytest.raises(ValueError, match="Unregistered feature"):
        store.insert_feature_vector(fv)


def test_store_signals(store: AnalyticsStore) -> None:
    inst_id = uuid4()
    as_of = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)

    sig = Signal(
        instrument_id=inst_id,
        as_of=as_of,
        emitted_at=datetime.now(UTC),
        direction=Direction.LONG,
        score=0.75,
        confidence=0.75,
        lineage=[
            FeatureLineageItem(feature_name="returns_1", weight=0.5, value=0.05),
            FeatureLineageItem(feature_name="momentum_10", weight=0.5, value=1.0),
        ],
        signal_version="1.0.0",
    )

    store.insert_signal(sig)
    assert store.count_signals() == 1

    fetched = store.fetch_signals(instrument_id=inst_id, direction=Direction.LONG)
    assert len(fetched) == 1
    assert fetched[0]["score"] == 0.75
    assert len(fetched[0]["lineage"]) == 2
    assert fetched[0]["lineage"][0]["feature_name"] == "returns_1"


def test_store_ranks(store: AnalyticsStore) -> None:
    inst_id = uuid4()
    as_of = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)

    rank = InstrumentRank(
        instrument_id=inst_id,
        universe_id="NIFTY50",
        as_of=as_of,
        rank=1,
        score=0.85,
    )

    store.insert_rank(rank)
    assert store.count_ranks() == 1

    fetched = store.fetch_ranks(universe_id="NIFTY50")
    assert len(fetched) == 1
    assert fetched[0]["rank"] == 1
    assert fetched[0]["score"] == 0.85


def test_store_regime_states(store: AnalyticsStore) -> None:
    inst_id = uuid4()
    as_of = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)

    reg = RegimeState(
        instrument_id=inst_id,
        as_of=as_of,
        regime=RegimeType.TRENDING,
        confidence=0.88,
        metrics={"realised_vol": 0.015, "price_drift": 0.035},
        detector_version="1.0.0",
    )

    store.insert_regime_state(reg)
    assert store.count_regime_states() == 1

    fetched = store.fetch_regime_states(instrument_id=inst_id)
    assert len(fetched) == 1
    assert fetched[0]["regime"] == RegimeType.TRENDING.value
    assert fetched[0]["confidence"] == 0.88
    assert fetched[0]["metrics"]["price_drift"] == 0.035
