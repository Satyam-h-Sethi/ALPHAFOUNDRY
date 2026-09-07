"""Tests for market data domain models: Quote, Trade, OHLCBar."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from alphafoundry.domain import OHLCBar, Quote, Trade
from alphafoundry.domain.enums import TradeSide


def _utc(
    year: int, month: int, day: int, hour: int = 0, minute: int = 0, second: int = 0
) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=UTC)


_IID = uuid.uuid4()


class TestQuote:
    def _quote(self, **kwargs) -> Quote:
        defaults = {
            "idempotency_key": "NSE_EQ:1001",
            "instrument_id": _IID,
            "venue_id": "NSE_EQ",
            "timestamp": _utc(2024, 1, 2, 4, 0),
            "received_at": _utc(2024, 1, 2, 4, 0),
            "sequence_id": 1001,
            "bid_price": Decimal("100.00"),
            "bid_qty": 500,
            "ask_price": Decimal("100.05"),
            "ask_qty": 300,
        }
        defaults.update(kwargs)
        return Quote(**defaults)

    def test_valid_quote(self):
        q = self._quote()
        assert q.bid_price < q.ask_price
        assert q.is_stale is False

    def test_ask_below_bid_is_invalid(self):
        with pytest.raises(ValidationError):
            self._quote(bid_price=Decimal("100.10"), ask_price=Decimal("100.00"))

    def test_zero_bid_price_is_invalid(self):
        with pytest.raises(ValidationError):
            self._quote(bid_price=Decimal("0"))

    def test_zero_bid_qty_is_invalid(self):
        with pytest.raises(ValidationError):
            self._quote(bid_qty=0)

    def test_equal_prices_are_valid(self):
        # Crossed/locked markets are technically invalid, but we allow bid==ask
        # at the model level; the validator enforces ask >= bid.
        q = self._quote(bid_price=Decimal("100.00"), ask_price=Decimal("100.00"))
        assert q.bid_price == q.ask_price

    def test_is_immutable(self):
        q = self._quote()
        with pytest.raises(ValidationError):
            q.bid_price = Decimal("99.00")  # type: ignore[misc]


class TestTrade:
    def test_valid_trade(self):
        t = Trade(
            idempotency_key="NSE_EQ:T:2001",
            instrument_id=_IID,
            venue_id="NSE_EQ",
            timestamp=_utc(2024, 1, 2, 4, 1),
            received_at=_utc(2024, 1, 2, 4, 1),
            sequence_id=2001,
            price=Decimal("100.05"),
            qty=100,
            side=TradeSide.BUY,
        )
        assert t.side == TradeSide.BUY

    def test_zero_qty_is_invalid(self):
        with pytest.raises(ValidationError):
            Trade(
                idempotency_key="k",
                instrument_id=_IID,
                venue_id="NSE_EQ",
                timestamp=_utc(2024, 1, 2, 4, 1),
                received_at=_utc(2024, 1, 2, 4, 1),
                sequence_id=1,
                price=Decimal("100.00"),
                qty=0,
            )


class TestOHLCBar:
    def _bar(self, **kwargs) -> OHLCBar:
        defaults = {
            "instrument_id": _IID,
            "venue_id": "NSE_EQ",
            "freq": "1d",
            "bar_open": _utc(2024, 1, 2, 3, 45),
            "bar_close": _utc(2024, 1, 2, 10, 0),
            "open": Decimal("100.00"),
            "high": Decimal("105.00"),
            "low": Decimal("98.00"),
            "close": Decimal("103.00"),
            "volume": 50_000,
            "num_trades": 500,
        }
        defaults.update(kwargs)
        return OHLCBar(**defaults)

    def test_valid_bar(self):
        b = self._bar()
        assert b.high >= b.open
        assert b.low <= b.close

    def test_high_below_open_is_invalid(self):
        with pytest.raises(ValidationError):
            self._bar(high=Decimal("99.00"))

    def test_low_above_close_is_invalid(self):
        with pytest.raises(ValidationError):
            self._bar(low=Decimal("110.00"))

    def test_high_below_low_is_invalid(self):
        with pytest.raises(ValidationError):
            self._bar(high=Decimal("95.00"), low=Decimal("96.00"))

    def test_bar_close_before_open_is_invalid(self):
        with pytest.raises(ValidationError):
            self._bar(
                bar_open=_utc(2024, 1, 2, 10, 0),
                bar_close=_utc(2024, 1, 2, 3, 45),
            )
