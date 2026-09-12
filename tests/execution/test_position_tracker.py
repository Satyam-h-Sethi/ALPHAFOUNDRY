"""Unit tests for Position and Exposure Tracker (Phase 05)."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4
import pytest

from alphafoundry.domain.enums import Side
from alphafoundry.domain.orders import Fill
from alphafoundry.execution.position_tracker import PositionTracker
from tests.execution.conftest import INST_ID, T0


class TestPositionTracker:
    def _make_fill(self, qty: int, price: str) -> Fill:
        return Fill(
            child_order_id=uuid4(),
            fill_qty=qty,
            fill_price=Decimal(price),
            simulated_impact=Decimal("0.05"),
            fill_timestamp=T0,
        )

    def test_long_accumulation_and_average_price(self) -> None:
        tracker = PositionTracker()
        f1 = self._make_fill(100, "100.00")
        pos = tracker.record_fill(f1, Side.BUY, INST_ID)

        assert pos.net_qty == 100
        assert pos.average_entry_price == Decimal("100.00")
        assert pos.realized_pnl == Decimal("0")

        f2 = self._make_fill(100, "110.00")
        pos2 = tracker.record_fill(f2, Side.BUY, INST_ID)

        assert pos2.net_qty == 200
        # (100*100 + 100*110)/200 = 21000/200 = 105.00
        assert pos2.average_entry_price == Decimal("105.00")

    def test_closing_long_position_realized_pnl(self) -> None:
        tracker = PositionTracker()
        f_buy = self._make_fill(100, "100.00")
        tracker.record_fill(f_buy, Side.BUY, INST_ID)

        # Sell 60 at 120 -> gain is 60 * (120 - 100) = 1200
        f_sell = self._make_fill(60, "120.00")
        pos = tracker.record_fill(f_sell, Side.SELL, INST_ID)

        assert pos.net_qty == 40
        assert pos.realized_pnl == Decimal("1200.00")
        assert tracker.get_realized_pnl() == Decimal("1200.00")

    def test_flipping_position_from_long_to_short(self) -> None:
        tracker = PositionTracker()
        f_buy = self._make_fill(50, "100.00")
        tracker.record_fill(f_buy, Side.BUY, INST_ID)

        # Sell 80 at 110: closes 50 at gain 50*(110-100)=500, opens short 30 at 110
        f_sell = self._make_fill(80, "110.00")
        pos = tracker.record_fill(f_sell, Side.SELL, INST_ID)

        assert pos.net_qty == -30
        assert pos.realized_pnl == Decimal("500.00")
        assert pos.average_entry_price == Decimal("110.00")

    def test_portfolio_gross_exposure_calculation(self) -> None:
        tracker = PositionTracker()
        inst2 = uuid4()

        tracker.record_fill(self._make_fill(100, "50.00"), Side.BUY, INST_ID)
        tracker.record_fill(self._make_fill(50, "200.00"), Side.SELL, inst2)

        prices = {
            INST_ID: Decimal("60.00"),
            inst2: Decimal("210.00"),
        }
        # Gross = abs(100)*60 + abs(-50)*210 = 6000 + 10500 = 16500
        gross = tracker.get_portfolio_gross_exposure(prices)
        assert gross == Decimal("16500.00")
