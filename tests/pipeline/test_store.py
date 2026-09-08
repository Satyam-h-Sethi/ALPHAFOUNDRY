"""Tests for MarketDataStore."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from alphafoundry.domain import OHLCBar, Quote, Trade
from alphafoundry.domain.enums import SessionStatus, TradeSide
from alphafoundry.pipeline.config import PipelineConfig
from alphafoundry.pipeline.store import MarketDataStore


@pytest.fixture
def store() -> MarketDataStore:
    cfg = PipelineConfig(db_path=":memory:")
    return MarketDataStore(cfg)


_INSTR_ID = uuid4()
_TS = datetime(2024, 1, 15, 4, 0, 0, tzinfo=UTC)


def _make_quote(seq: int = 0) -> Quote:
    return Quote(
        idempotency_key=f"v:i:{seq}",
        instrument_id=_INSTR_ID,
        venue_id="TEST",
        timestamp=_TS + timedelta(seconds=seq),
        received_at=_TS + timedelta(seconds=seq + 1),
        sequence_id=seq,
        bid_price=Decimal("100.05"),
        bid_qty=50,
        ask_price=Decimal("100.10"),
        ask_qty=50,
        session_status=SessionStatus.OPEN,
    )


def _make_trade(seq: int = 0) -> Trade:
    return Trade(
        idempotency_key=f"v:trade:i:{seq}",
        instrument_id=_INSTR_ID,
        venue_id="TEST",
        timestamp=_TS + timedelta(seconds=seq),
        received_at=_TS + timedelta(seconds=seq + 1),
        sequence_id=seq,
        price=Decimal("100.05"),
        qty=50,
        side=TradeSide.BUY,
    )


def _make_bar() -> OHLCBar:
    return OHLCBar(
        instrument_id=_INSTR_ID,
        venue_id="TEST",
        freq="1m",
        bar_open=_TS,
        bar_close=_TS + timedelta(minutes=1),
        open=Decimal("100.00"),
        high=Decimal("100.20"),
        low=Decimal("99.90"),
        close=Decimal("100.10"),
        volume=500,
        num_trades=10,
    )


class TestMarketDataStore:
    def test_empty_store_has_zero_counts(self, store: MarketDataStore):
        assert store.count_quotes() == 0
        assert store.count_trades() == 0
        assert store.count_bars() == 0

    def test_insert_quote_increments_count(self, store: MarketDataStore):
        store.insert_quote(_make_quote())
        assert store.count_quotes() == 1

    def test_insert_trade_increments_count(self, store: MarketDataStore):
        store.insert_trade(_make_trade())
        assert store.count_trades() == 1

    def test_insert_bar_increments_count(self, store: MarketDataStore):
        store.insert_bar(_make_bar())
        assert store.count_bars() == 1

    def test_multiple_quotes_inserted(self, store: MarketDataStore):
        for i in range(5):
            store.insert_quote(_make_quote(i))
        assert store.count_quotes() == 5

    def test_fetch_quotes_returns_dicts(self, store: MarketDataStore):
        store.insert_quote(_make_quote())
        rows = store.fetch_quotes()
        assert len(rows) == 1
        row = rows[0]
        assert "quote_id" in row
        assert "bid_price" in row

    def test_fetch_quotes_by_instrument_id(self, store: MarketDataStore):
        other_id = uuid4()
        store.insert_quote(_make_quote(0))  # _INSTR_ID
        other_quote = _make_quote(1)
        other_quote = other_quote.model_copy(
            update={"instrument_id": other_id, "idempotency_key": "v:other:1"}
        )
        store.insert_quote(other_quote)
        rows = store.fetch_quotes(instrument_id=_INSTR_ID)
        assert len(rows) == 1

    def test_fetch_trades_returns_dicts(self, store: MarketDataStore):
        store.insert_trade(_make_trade())
        rows = store.fetch_trades()
        assert len(rows) == 1
        assert "price" in rows[0]
