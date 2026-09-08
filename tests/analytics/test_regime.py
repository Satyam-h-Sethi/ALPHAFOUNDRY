"""Unit tests for RegimeDetector (advisory classification, zero lookahead, confidence)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from alphafoundry.analytics.config import AnalyticsConfig
from alphafoundry.analytics.regime import RegimeDetector
from alphafoundry.domain import OHLCBar, RegimeType


def test_regime_detector_insufficient_bars() -> None:
    detector = RegimeDetector()
    inst_id = uuid4()
    as_of = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)

    # 0 or 1 bar -> UNKNOWN
    res = detector.detect_regime(inst_id, as_of, bars=[])
    assert res.regime == RegimeType.UNKNOWN
    assert res.confidence == 0.0


def test_regime_detector_high_vol() -> None:
    config = AnalyticsConfig(high_vol_threshold=0.01)
    detector = RegimeDetector(config=config)
    inst_id = uuid4()
    start = datetime(2026, 1, 1, 9, 30, tzinfo=UTC)

    # Highly oscillating prices
    prices = [100.0, 110.0, 95.0, 115.0, 90.0, 120.0, 85.0, 125.0]
    bars = []
    for i, p in enumerate(prices):
        bars.append(
            OHLCBar(
                instrument_id=inst_id,
                venue_id="NSE",
                freq="1m",
                bar_open=start + timedelta(minutes=i),
                bar_close=start + timedelta(minutes=i + 1),
                open=Decimal(str(p)),
                high=Decimal(str(p + 2)),
                low=Decimal(str(p - 2)),
                close=Decimal(str(p)),
                volume=1000,
                num_trades=20,
            )
        )

    res = detector.detect_regime(inst_id, bars[-1].bar_close, bars)
    assert res.regime == RegimeType.HIGH_VOL
    assert res.confidence >= 0.5
    assert "realised_vol" in res.metrics


def test_regime_detector_trending() -> None:
    config = AnalyticsConfig(
        trend_threshold=0.02,
        high_vol_threshold=0.50,  # high threshold so it doesn't trigger high vol
    )
    detector = RegimeDetector(config=config)
    inst_id = uuid4()
    start = datetime(2026, 1, 1, 9, 30, tzinfo=UTC)

    # Steady upward drift
    prices = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0]
    bars = []
    for i, p in enumerate(prices):
        dec_p = Decimal(str(p))
        bars.append(
            OHLCBar(
                instrument_id=inst_id,
                venue_id="NSE",
                freq="1m",
                bar_open=start + timedelta(minutes=i),
                bar_close=start + timedelta(minutes=i + 1),
                open=dec_p,
                high=dec_p + Decimal("0.1"),
                low=dec_p - Decimal("0.1"),
                close=dec_p,
                volume=1000,
                num_trades=20,
            )
        )

    res = detector.detect_regime(inst_id, bars[-1].bar_close, bars)
    assert res.regime == RegimeType.TRENDING
    assert res.confidence >= 0.5
    assert res.metrics["price_drift"] > 0.05
