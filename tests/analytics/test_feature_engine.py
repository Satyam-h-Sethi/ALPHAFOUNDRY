"""Unit tests for FeatureEngine (point-in-time boundaries, zero lookahead)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from alphafoundry.analytics.feature_engine import FeatureEngine
from alphafoundry.domain import OHLCBar, Quote


def _create_bars(start: datetime, count: int, start_price: float = 100.0) -> list[OHLCBar]:
    inst_id = uuid4()
    bars = []
    for i in range(count):
        close_time = start + timedelta(minutes=i + 1)
        open_time = start + timedelta(minutes=i)
        p = Decimal(str(start_price + i))
        bars.append(
            OHLCBar(
                instrument_id=inst_id,
                venue_id="NSE",
                freq="1m",
                bar_open=open_time,
                bar_close=close_time,
                open=p,
                high=p + Decimal("1"),
                low=p - Decimal("1"),
                close=p,
                volume=1000 + i * 100,
                num_trades=50,
            )
        )
    return bars


def test_feature_engine_zero_lookahead() -> None:
    engine = FeatureEngine()
    start = datetime(2026, 1, 1, 9, 30, tzinfo=UTC)
    bars = _create_bars(start, count=10, start_price=100.0)
    inst_id = bars[0].instrument_id

    # as_of set to 5th bar close
    as_of = bars[4].bar_close

    fv = engine.compute_features(
        instrument_id=inst_id,
        as_of=as_of,
        bars=bars,  # entire 10 bars passed
    )

    assert fv.instrument_id == inst_id
    assert fv.as_of == as_of
    assert "returns_1" in fv.features
    assert "momentum_10" in fv.features

    # The 5th bar close is 104.0, 4th bar close is 103.0 -> returns_1 = (104 - 103) / 103
    expected_returns_1 = (104.0 - 103.0) / 103.0
    assert pytest.approx(fv.features["returns_1"], rel=1e-4) == expected_returns_1


def test_feature_engine_quote_integration() -> None:
    engine = FeatureEngine()
    start = datetime(2026, 1, 1, 9, 30, tzinfo=UTC)
    bars = _create_bars(start, count=5, start_price=100.0)
    inst_id = bars[0].instrument_id
    as_of = bars[-1].bar_close

    valid_quote = Quote(
        idempotency_key="NSE:1",
        instrument_id=inst_id,
        venue_id="NSE",
        timestamp=as_of - timedelta(seconds=10),
        received_at=as_of - timedelta(seconds=9),
        sequence_id=1,
        bid_price=Decimal("104.00"),
        ask_price=Decimal("104.50"),
        bid_qty=500,
        ask_qty=700,
    )

    fv = engine.compute_features(
        instrument_id=inst_id,
        as_of=as_of,
        bars=bars,
        quote=valid_quote,
    )

    expected_spread = (104.50 - 104.00) / ((104.50 + 104.00) / 2.0)
    assert pytest.approx(fv.features["bid_ask_spread"], rel=1e-4) == expected_spread
    assert pytest.approx(fv.features["market_depth_liquidity"], rel=1e-4) == 1200.0


def test_feature_engine_future_quote_excluded() -> None:
    engine = FeatureEngine()
    start = datetime(2026, 1, 1, 9, 30, tzinfo=UTC)
    bars = _create_bars(start, count=5, start_price=100.0)
    inst_id = bars[0].instrument_id
    as_of = bars[-1].bar_close

    # Future quote ahead of as_of
    future_quote = Quote(
        idempotency_key="NSE:2",
        instrument_id=inst_id,
        venue_id="NSE",
        timestamp=as_of + timedelta(seconds=30),
        received_at=as_of + timedelta(seconds=31),
        sequence_id=2,
        bid_price=Decimal("105.00"),
        ask_price=Decimal("106.00"),
        bid_qty=500,
        ask_qty=700,
    )

    fv = engine.compute_features(
        instrument_id=inst_id,
        as_of=as_of,
        bars=bars,
        quote=future_quote,
    )

    # Future quote must be ignored
    assert fv.features["bid_ask_spread"] == 0.0
    assert fv.features["market_depth_liquidity"] == 0.0
