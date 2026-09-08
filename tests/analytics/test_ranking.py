"""Unit tests for RankingEngine (cross-sectional ranking, conviction ranking, deterministic ordering)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from alphafoundry.analytics.ranking import RankingEngine
from alphafoundry.domain import Direction, Signal


def _create_signal(
    score: float,
    confidence: float,
    direction: Direction = Direction.LONG,
    as_of: datetime | None = None,
) -> Signal:
    ts = as_of or datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    return Signal(
        instrument_id=uuid4(),
        as_of=ts,
        emitted_at=datetime.now(UTC),
        direction=direction,
        score=score,
        confidence=confidence,
        lineage=[],
        signal_version="1.0.0",
    )


def test_ranking_by_score_descending() -> None:
    engine = RankingEngine()
    as_of = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)

    s1 = _create_signal(score=0.2, confidence=0.2, as_of=as_of)
    s2 = _create_signal(score=0.8, confidence=0.8, as_of=as_of)
    s3 = _create_signal(score=-0.5, confidence=0.5, direction=Direction.SHORT, as_of=as_of)

    ranks = engine.rank_universe(
        signals=[s1, s2, s3],
        universe_id="NIFTY50_TOP",
        as_of=as_of,
    )

    assert len(ranks) == 3
    # Rank 1: s2 (score 0.8)
    assert ranks[0].instrument_id == s2.instrument_id
    assert ranks[0].rank == 1
    assert ranks[0].score == 0.8

    # Rank 2: s1 (score 0.2)
    assert ranks[1].instrument_id == s1.instrument_id
    assert ranks[1].rank == 2

    # Rank 3: s3 (score -0.5)
    assert ranks[2].instrument_id == s3.instrument_id
    assert ranks[2].rank == 3


def test_ranking_by_conviction() -> None:
    engine = RankingEngine()
    as_of = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)

    # s1 has score 0.4, conf 0.5 -> conviction = 0.20
    s1 = _create_signal(score=0.4, confidence=0.5, as_of=as_of)
    # s2 has score -0.9, conf 0.8 -> conviction = 0.72
    s2 = _create_signal(score=-0.9, confidence=0.8, direction=Direction.SHORT, as_of=as_of)
    # s3 has score 0.5, conf 0.6 -> conviction = 0.30
    s3 = _create_signal(score=0.5, confidence=0.6, as_of=as_of)

    ranks = engine.rank_universe(
        signals=[s1, s2, s3],
        universe_id="TEST_UNIVERSE",
        as_of=as_of,
        by_conviction=True,
    )

    # Rank 1: s2 (conviction 0.72)
    assert ranks[0].instrument_id == s2.instrument_id
    assert ranks[0].rank == 1

    # Rank 2: s3 (conviction 0.30)
    assert ranks[1].instrument_id == s3.instrument_id
    assert ranks[1].rank == 2

    # Rank 3: s1 (conviction 0.20)
    assert ranks[2].instrument_id == s1.instrument_id
    assert ranks[2].rank == 3


def test_ranking_universe_filter_and_temporal() -> None:
    engine = RankingEngine()
    as_of = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)

    s1 = _create_signal(score=0.9, confidence=0.9, as_of=as_of)
    s2 = _create_signal(score=0.8, confidence=0.8, as_of=as_of)
    # s_future is after as_of -> must be excluded
    s_future = _create_signal(score=1.0, confidence=1.0, as_of=as_of + timedelta(hours=1))

    # Filter only allows s2
    ranks = engine.rank_universe(
        signals=[s1, s2, s_future],
        universe_id="FILTERED_UNIVERSE",
        as_of=as_of,
        instrument_filter={s2.instrument_id},
    )

    assert len(ranks) == 1
    assert ranks[0].instrument_id == s2.instrument_id
    assert ranks[0].rank == 1
