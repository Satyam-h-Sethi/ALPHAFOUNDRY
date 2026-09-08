"""Tests for the StalenessDetector."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from alphafoundry.domain import Quote, Trade
from alphafoundry.domain.enums import SessionStatus, TradeSide
from alphafoundry.pipeline.config import PipelineConfig
from alphafoundry.pipeline.staleness import StalenessDetector

_CFG = PipelineConfig(staleness_seconds=60.0)

_TS = datetime(2024, 1, 15, 4, 0, 0, tzinfo=UTC)


def _make_quote(timestamp: datetime, received_at: datetime) -> Quote:
    return Quote(
        idempotency_key="v:i:0",
        instrument_id=uuid4(),
        venue_id="TEST",
        timestamp=timestamp,
        received_at=received_at,
        sequence_id=0,
        bid_price=Decimal("100.05"),
        bid_qty=5,
        ask_price=Decimal("100.10"),
        ask_qty=5,
        session_status=SessionStatus.OPEN,
    )


def _make_trade(timestamp: datetime, received_at: datetime) -> Trade:
    return Trade(
        idempotency_key="v:trade:i:0",
        instrument_id=uuid4(),
        venue_id="TEST",
        timestamp=timestamp,
        received_at=received_at,
        sequence_id=0,
        price=Decimal("100.05"),
        qty=5,
        side=TradeSide.BUY,
    )


class TestStalenessDetector:
    def test_fresh_quote_not_stale(self):
        sd = StalenessDetector(_CFG)
        q = _make_quote(_TS, _TS + timedelta(seconds=1))
        assert not sd.is_stale_quote(q)

    def test_quote_exactly_at_threshold_not_stale(self):
        sd = StalenessDetector(_CFG)
        ra = _TS + timedelta(seconds=60)
        q = _make_quote(_TS, ra)
        # exactly 60 s → not stale (> threshold, not >=)
        assert not sd.is_stale_quote(q)

    def test_quote_beyond_threshold_is_stale(self):
        sd = StalenessDetector(_CFG)
        ra = _TS + timedelta(seconds=61)
        q = _make_quote(_TS, ra)
        assert sd.is_stale_quote(q)

    def test_fresh_trade_not_stale(self):
        sd = StalenessDetector(_CFG)
        t = _make_trade(_TS, _TS + timedelta(seconds=30))
        assert not sd.is_stale_trade(t)

    def test_stale_trade_detected(self):
        sd = StalenessDetector(_CFG)
        t = _make_trade(_TS, _TS + timedelta(seconds=120))
        assert sd.is_stale_trade(t)

    def test_naive_timestamps_handled(self):
        """Naive timestamps are treated as UTC without raising."""
        sd = StalenessDetector(_CFG)
        ts_naive = datetime(2024, 1, 15, 4, 0, 0)  # no tzinfo
        ra_naive = datetime(2024, 1, 15, 4, 0, 30)  # 30 s later — not stale
        q = _make_quote(ts_naive, ra_naive)
        assert not sd.is_stale_quote(q)
