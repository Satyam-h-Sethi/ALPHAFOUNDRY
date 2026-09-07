"""Tests for Instrument and Venue domain models."""

import uuid
from decimal import Decimal

import pytest
from pydantic import ValidationError

from alphafoundry.domain import Instrument, Venue
from alphafoundry.domain.enums import InstrumentType

# ---------------------------------------------------------------------------
# Venue
# ---------------------------------------------------------------------------


class TestVenue:
    def test_valid_venue(self):
        v = Venue(venue_id="NSE_EQ", name="National Stock Exchange", timezone="Asia/Kolkata")
        assert v.venue_id == "NSE_EQ"
        assert v.timezone == "Asia/Kolkata"

    def test_venue_is_immutable(self):
        v = Venue(venue_id="NSE_EQ", name="NSE")
        with pytest.raises(ValidationError):
            v.venue_id = "BSE_EQ"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Instrument
# ---------------------------------------------------------------------------


class TestInstrument:
    def _equity(self, **kwargs) -> Instrument:
        defaults = {
            "symbol": "TESTCO",
            "venue_id": "NSE_EQ",
            "instrument_type": InstrumentType.EQ,
        }
        defaults.update(kwargs)
        return Instrument(**defaults)

    def test_valid_equity(self):
        inst = self._equity()
        assert inst.instrument_type == InstrumentType.EQ
        assert inst.lot_size == 1
        assert inst.tick_size == Decimal("0.05")
        assert inst.currency == "INR"

    def test_instrument_id_is_uuid(self):
        inst = self._equity()
        assert isinstance(inst.instrument_id, uuid.UUID)

    def test_explicit_instrument_id(self):
        uid = uuid.uuid4()
        inst = self._equity(instrument_id=uid)
        assert inst.instrument_id == uid

    def test_isin_must_be_12_chars(self):
        with pytest.raises(ValidationError):
            self._equity(isin="SHORT")

    def test_isin_must_be_alphanumeric(self):
        with pytest.raises(ValidationError):
            self._equity(isin="INE!00A01036")

    def test_valid_isin(self):
        inst = self._equity(isin="INE009A01021")
        assert inst.isin == "INE009A01021"

    def test_lot_size_must_be_positive(self):
        with pytest.raises(ValidationError):
            self._equity(lot_size=0)

    def test_tick_size_must_be_positive(self):
        with pytest.raises(ValidationError):
            self._equity(tick_size=Decimal("0"))

    def test_strike_must_be_positive(self):
        with pytest.raises(ValidationError):
            Instrument(
                symbol="NIFTY24500CE",
                venue_id="NSE_FO",
                instrument_type=InstrumentType.OPT_CE,
                strike=Decimal("-100"),
            )

    def test_instrument_is_immutable(self):
        inst = self._equity()
        with pytest.raises(ValidationError):
            inst.symbol = "OTHER"  # type: ignore[misc]
