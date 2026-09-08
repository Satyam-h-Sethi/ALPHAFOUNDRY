"""Tests for the Validator — one test per data-quality rule."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from alphafoundry.domain import OHLCBar, Quote, Trade
from alphafoundry.domain.enums import InstrumentType, SessionStatus, TradeSide
from alphafoundry.domain.instruments import Instrument
from alphafoundry.pipeline.config import PipelineConfig
from alphafoundry.pipeline.validator import Validator

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CFG = PipelineConfig(
    max_price_inr=1_000_000.0,
    future_gate_seconds=5.0,
    past_gate_seconds=300.0,
    session_open_utc_hour=3,
    session_open_utc_minute=45,
)

# A timestamp well within session hours (04:00 UTC = 09:30 IST).
_SESSION_TS = datetime(2024, 1, 15, 4, 0, 0, tzinfo=UTC)
_RECEIVED = datetime(2024, 1, 15, 4, 0, 1, tzinfo=UTC)

_INSTR_ID = uuid4()
_INSTR = Instrument(
    instrument_id=_INSTR_ID,
    symbol="TESTX",
    venue_id="NSE_EQ",
    instrument_type=InstrumentType.EQ,
    lot_size=5,
    tick_size=Decimal("0.05"),
)


def _validator_with_instr() -> Validator:
    v = Validator(_CFG)
    v.register_instrument(_INSTR)
    return v


def _make_quote(**overrides) -> Quote:
    defaults = {
        "idempotency_key": "v:i:0",
        "instrument_id": _INSTR_ID,
        "venue_id": "TEST",
        "timestamp": _SESSION_TS,
        "received_at": _RECEIVED,
        "sequence_id": 0,
        "bid_price": Decimal("100.05"),
        "bid_qty": 5,
        "ask_price": Decimal("100.10"),
        "ask_qty": 5,
        "session_status": SessionStatus.OPEN,
        "is_stale": False,
    }
    defaults.update(overrides)
    return Quote(**defaults)


def _make_trade(**overrides) -> Trade:
    defaults = {
        "idempotency_key": "v:trade:i:0",
        "instrument_id": _INSTR_ID,
        "venue_id": "TEST",
        "timestamp": _SESSION_TS,
        "received_at": _RECEIVED,
        "sequence_id": 0,
        "price": Decimal("100.05"),
        "qty": 5,
        "side": TradeSide.BUY,
    }
    defaults.update(overrides)
    return Trade(**defaults)


def _make_bar(**overrides) -> OHLCBar:
    defaults = {
        "instrument_id": _INSTR_ID,
        "venue_id": "TEST",
        "freq": "1m",
        "bar_open": _SESSION_TS,
        "bar_close": _SESSION_TS + timedelta(minutes=1),
        "open": Decimal("100.00"),
        "high": Decimal("100.20"),
        "low": Decimal("99.90"),
        "close": Decimal("100.10"),
        "volume": 100,
        "num_trades": 10,
    }
    defaults.update(overrides)
    return OHLCBar(**defaults)


# ---------------------------------------------------------------------------
# Rule 1 — Price sanity
# ---------------------------------------------------------------------------


class TestPriceSanity:
    def test_valid_price_passes(self):
        v = _validator_with_instr()
        result = v.validate_quote(_make_quote())
        assert result.is_valid

    def test_zero_price_fails(self):
        # Quote model itself rejects bid_price=0 (Field(gt=0)), so test via
        # a price that just clears domain validation but hits our rule.
        # Use internal method directly.
        v = Validator(_CFG)
        from alphafoundry.pipeline.validator import ValidationResult

        r = ValidationResult()
        v._check_price(Decimal("0"), "bid_price", r)
        assert not r.is_valid
        assert "price_sanity" in r.failures[0]

    def test_above_max_price_fails(self):
        v = Validator(_CFG)
        from alphafoundry.pipeline.validator import ValidationResult

        r = ValidationResult()
        v._check_price(Decimal("1000001"), "bid_price", r)
        assert not r.is_valid

    def test_max_price_exactly_passes(self):
        v = Validator(_CFG)
        from alphafoundry.pipeline.validator import ValidationResult

        r = ValidationResult()
        v._check_price(Decimal("1000000"), "bid_price", r)
        assert r.is_valid


# ---------------------------------------------------------------------------
# Rule 2 — Spread sanity
# ---------------------------------------------------------------------------


class TestSpreadSanity:
    def test_equal_bid_ask_passes(self):
        # Quote model prevents ask < bid, but equal is allowed.
        v = Validator(_CFG)
        from alphafoundry.pipeline.validator import ValidationResult

        r = ValidationResult()
        v._check_spread(Decimal("100"), Decimal("100"), r)
        assert r.is_valid

    def test_ask_less_than_bid_fails(self):
        v = Validator(_CFG)
        from alphafoundry.pipeline.validator import ValidationResult

        r = ValidationResult()
        v._check_spread(Decimal("100.10"), Decimal("100.05"), r)
        assert not r.is_valid
        assert "spread_sanity" in r.failures[0]


# ---------------------------------------------------------------------------
# Rule 3 — Quantity sanity
# ---------------------------------------------------------------------------


class TestQuantitySanity:
    def test_positive_qty_passes(self):
        v = Validator(_CFG)
        from alphafoundry.pipeline.validator import ValidationResult

        r = ValidationResult()
        v._check_qty(1, "qty", r)
        assert r.is_valid

    def test_zero_qty_fails(self):
        v = Validator(_CFG)
        from alphafoundry.pipeline.validator import ValidationResult

        r = ValidationResult()
        v._check_qty(0, "qty", r)
        assert not r.is_valid

    def test_negative_qty_fails(self):
        v = Validator(_CFG)
        from alphafoundry.pipeline.validator import ValidationResult

        r = ValidationResult()
        v._check_qty(-5, "qty", r)
        assert not r.is_valid
        assert "quantity_sanity" in r.failures[0]


# ---------------------------------------------------------------------------
# Rule 4 — Timestamp future-gate
# ---------------------------------------------------------------------------


class TestTimestampFutureGate:
    def test_timestamp_within_gate_passes(self):
        v = Validator(_CFG)
        from alphafoundry.pipeline.validator import ValidationResult

        r = ValidationResult()
        ts = _RECEIVED + timedelta(seconds=4)  # 4 s ahead — within 5 s gate
        v._check_timestamps(ts, _RECEIVED, r)
        assert r.is_valid

    def test_timestamp_beyond_gate_fails(self):
        v = Validator(_CFG)
        from alphafoundry.pipeline.validator import ValidationResult

        r = ValidationResult()
        ts = _RECEIVED + timedelta(seconds=10)  # 10 s ahead — beyond 5 s gate
        v._check_timestamps(ts, _RECEIVED, r)
        assert not r.is_valid
        assert "timestamp_future_gate" in r.failures[0]


# ---------------------------------------------------------------------------
# Rule 5 — Timestamp past-gate
# ---------------------------------------------------------------------------


class TestTimestampPastGate:
    def test_timestamp_at_session_open_passes(self):
        v = Validator(_CFG)
        from alphafoundry.pipeline.validator import ValidationResult

        r = ValidationResult()
        # Session open = 03:45 UTC; timestamp = 03:45 UTC (exactly)
        ts = datetime(2024, 1, 15, 3, 45, 0, tzinfo=UTC)
        v._check_timestamps(ts, ts, r)
        assert r.is_valid

    def test_timestamp_before_earliest_fails(self):
        v = Validator(_CFG)
        from alphafoundry.pipeline.validator import ValidationResult

        r = ValidationResult()
        # 03:38 UTC is 7 min before 03:45; past-gate allows 5 min → fail
        ts = datetime(2024, 1, 15, 3, 38, 0, tzinfo=UTC)
        v._check_timestamps(ts, ts, r)
        assert not r.is_valid
        assert "timestamp_past_gate" in r.failures[0]


# ---------------------------------------------------------------------------
# Rule 6 — Lot-size conformance
# ---------------------------------------------------------------------------


class TestLotSizeConformance:
    def test_conforming_qty_passes(self):
        v = _validator_with_instr()
        result = v.validate_trade(_make_trade(qty=10))  # 10 % 5 == 0
        assert result.is_valid

    def test_non_conforming_qty_fails(self):
        v = _validator_with_instr()
        # Trade domain model requires qty > 0 and doesn't enforce lot-size.
        # qty=7 is not a multiple of lot_size=5.
        result = v.validate_trade(_make_trade(qty=7))
        assert not result.is_valid
        assert any("lot_size_conformance" in f for f in result.failures)

    def test_lot_size_one_always_passes(self):
        """Instruments with lot_size=1 (equities) skip the check."""
        instr1 = Instrument(
            instrument_id=uuid4(),
            symbol="EQ",
            venue_id="NSE_EQ",
            instrument_type=InstrumentType.EQ,
            lot_size=1,
            tick_size=Decimal("0.05"),
        )
        v = Validator(_CFG)
        v.register_instrument(instr1)
        quote = _make_quote(instrument_id=instr1.instrument_id, bid_qty=3, ask_qty=3)
        result = v.validate_quote(quote)
        assert result.is_valid


# ---------------------------------------------------------------------------
# Rule 7 — Tick-size conformance
# ---------------------------------------------------------------------------


class TestTickConformance:
    def test_conforming_price_passes(self):
        v = _validator_with_instr()
        # 100.05 / 0.05 = 2001.0 — integer
        result = v.validate_trade(_make_trade(price=Decimal("100.05")))
        assert result.is_valid

    def test_non_conforming_price_fails(self):
        v = _validator_with_instr()
        # 100.03 / 0.05 = 2000.6 — not integer
        result = v.validate_trade(_make_trade(price=Decimal("100.03")))
        assert not result.is_valid
        assert any("tick_conformance" in f for f in result.failures)


# ---------------------------------------------------------------------------
# Bar validation
# ---------------------------------------------------------------------------


class TestBarValidation:
    def test_valid_bar_passes(self):
        v = _validator_with_instr()
        result = v.validate_bar(_make_bar())
        assert result.is_valid

    def test_multiple_failures_collected(self):
        """A bar with several bad prices records all failures."""
        v = Validator(_CFG)  # no instrument registered
        from alphafoundry.pipeline.validator import ValidationResult

        r = ValidationResult()
        v._check_price(Decimal("0"), "open", r)
        v._check_price(Decimal("0"), "high", r)
        assert len(r.failures) == 2
        assert r.error_detail is not None
        assert ";" in r.error_detail
