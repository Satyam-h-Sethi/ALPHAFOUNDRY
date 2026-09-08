"""Tests for the Normaliser."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from alphafoundry.domain import Quote, Trade
from alphafoundry.domain.enums import SessionStatus, TradeSide
from alphafoundry.pipeline.normaliser import Normaliser


def _make_quote(**overrides) -> Quote:
    defaults = {
        "idempotency_key": "venue:instr:0",
        "instrument_id": uuid4(),
        "venue_id": "TEST",
        "timestamp": datetime(2024, 1, 15, 4, 0, 0, tzinfo=UTC),
        "received_at": datetime(2024, 1, 15, 4, 0, 1, tzinfo=UTC),
        "sequence_id": 0,
        "bid_price": Decimal("100.05"),
        "bid_qty": 50,
        "ask_price": Decimal("100.10"),
        "ask_qty": 50,
        "session_status": SessionStatus.OPEN,
        "is_stale": False,
    }
    defaults.update(overrides)
    return Quote(**defaults)


def _make_trade(**overrides) -> Trade:
    defaults = {
        "idempotency_key": "venue:trade:instr:0",
        "instrument_id": uuid4(),
        "venue_id": "TEST",
        "timestamp": datetime(2024, 1, 15, 4, 0, 0, tzinfo=UTC),
        "received_at": datetime(2024, 1, 15, 4, 0, 1, tzinfo=UTC),
        "sequence_id": 0,
        "price": Decimal("100.05"),
        "qty": 50,
        "side": TradeSide.BUY,
    }
    defaults.update(overrides)
    return Trade(**defaults)


class TestNormaliserQuote:
    def test_utc_quote_passes_through_unchanged(self):
        n = Normaliser()
        q = _make_quote()
        result = n.normalise_quote(q)
        assert result is q

    def test_naive_received_at_is_restamped(self):
        n = Normaliser()
        naive_ra = datetime(2024, 1, 15, 4, 0, 1)  # no tzinfo
        q = _make_quote(received_at=naive_ra)
        result = n.normalise_quote(q)
        assert result.received_at.tzinfo is not None
        # Should be approximately now (within a generous delta)
        delta = abs((result.received_at - datetime.now(UTC)).total_seconds())
        assert delta < 5.0


class TestNormaliserTrade:
    def test_utc_trade_passes_through_unchanged(self):
        n = Normaliser()
        t = _make_trade()
        result = n.normalise_trade(t)
        assert result is t

    def test_naive_received_at_is_restamped(self):
        n = Normaliser()
        naive_ra = datetime(2024, 1, 15, 4, 0, 1)
        t = _make_trade(received_at=naive_ra)
        result = n.normalise_trade(t)
        assert result.received_at.tzinfo is not None
