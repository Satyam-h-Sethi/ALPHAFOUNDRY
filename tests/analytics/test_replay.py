"""Unit and integration tests for HistoricalReplayEngine."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import duckdb

from alphafoundry.analytics.replay import HistoricalReplayEngine
from alphafoundry.analytics.store import AnalyticsStore
from alphafoundry.domain import OHLCBar


def _create_synthetic_series(
    inst_id: UUID,
    start: datetime,
    count: int,
    base_price: float,
    trend: float,
) -> list[OHLCBar]:
    bars = []
    for i in range(count):
        p = Decimal(str(base_price + i * trend))
        open_time = start + timedelta(minutes=i)
        close_time = start + timedelta(minutes=i + 1)
        bars.append(
            OHLCBar(
                instrument_id=inst_id,
                venue_id="NSE",
                freq="1m",
                bar_open=open_time,
                bar_close=close_time,
                open=p,
                high=p + Decimal("0.5"),
                low=p - Decimal("0.5"),
                close=p,
                volume=1000 + i * 50,
                num_trades=25,
            )
        )
    return bars


def test_historical_replay_pipeline() -> None:
    start = datetime(2026, 1, 1, 9, 30, tzinfo=UTC)
    inst1 = uuid4()
    inst2 = uuid4()

    bars1 = _create_synthetic_series(inst1, start, count=15, base_price=100.0, trend=1.0)
    bars2 = _create_synthetic_series(inst2, start, count=15, base_price=200.0, trend=-0.5)

    conn = duckdb.connect(":memory:")
    store = AnalyticsStore(conn=conn)
    replay = HistoricalReplayEngine(store=store)

    results = replay.run(
        bars_by_instrument={inst1: bars1, inst2: bars2},
        universe_id="TEST_REPLAY_UNIVERSE",
        persist=True,
    )

    # 15 time steps
    assert len(results) == 15

    # Check first step (t=1)
    step1 = results[0]
    assert inst1 in step1.feature_vectors
    assert inst2 in step1.feature_vectors
    assert inst1 in step1.signals
    assert inst2 in step1.signals
    assert len(step1.ranks) == 2

    # Check persistence
    assert store.count_feature_vectors() == 30  # 15 steps * 2 instruments
    assert store.count_signals() == 30
    assert store.count_regime_states() == 30
    assert store.count_ranks() == 30

    # Ensure ranking at later step reflects upward trend for inst1 vs downward for inst2
    final_step = results[-1]
    assert final_step.signals[inst1].score > final_step.signals[inst2].score
    assert final_step.ranks[0].instrument_id == inst1
    assert final_step.ranks[0].rank == 1
