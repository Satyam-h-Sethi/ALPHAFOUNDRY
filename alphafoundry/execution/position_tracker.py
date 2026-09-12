"""In-memory position and exposure tracker for execution simulation.

Maintains signed positions per instrument per simulation session,
updating after every fill to provide accurate state to the Risk Engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Mapping
from uuid import UUID

from alphafoundry.domain.enums import Side
from alphafoundry.domain.orders import Fill


@dataclass
class InstrumentPosition:
    """Tracking state for a single instrument's position and PnL."""

    instrument_id: UUID
    net_qty: int = 0
    realized_pnl: Decimal = Decimal("0")
    total_bought_qty: int = 0
    total_sold_qty: int = 0
    total_bought_notional: Decimal = Decimal("0")
    total_sold_notional: Decimal = Decimal("0")
    average_entry_price: Decimal = Decimal("0")
    fills: list[Fill] = field(default_factory=list)

    @property
    def gross_qty(self) -> int:
        return abs(self.net_qty)

    def gross_notional(self, current_price: Decimal) -> Decimal:
        return Decimal(str(self.gross_qty)) * current_price

    def update(self, fill: Fill, side: Side) -> None:
        """Apply a Fill to this instrument's position."""
        self.fills.append(fill)
        fill_qty = fill.fill_qty
        fill_price = fill.fill_price
        fill_notional = Decimal(str(fill_qty)) * fill_price

        old_net_qty = self.net_qty

        if side == Side.BUY:
            self.total_bought_qty += fill_qty
            self.total_bought_notional += fill_notional
            self.net_qty += fill_qty

            if old_net_qty >= 0:
                # Adding to long or opening long: update weighted average entry price
                new_total_qty = old_net_qty + fill_qty
                if new_total_qty > 0:
                    old_cost = Decimal(str(old_net_qty)) * self.average_entry_price
                    self.average_entry_price = (old_cost + fill_notional) / Decimal(str(new_total_qty))
            else:
                # Closing short position partially or fully
                closed_qty = min(abs(old_net_qty), fill_qty)
                # Short PnL = (entry_price - exit_price) * closed_qty
                pnl = (self.average_entry_price - fill_price) * Decimal(str(closed_qty))
                self.realized_pnl += pnl

                if self.net_qty > 0:
                    # Flipped to long: new entry price is fill_price
                    self.average_entry_price = fill_price
                elif self.net_qty == 0:
                    self.average_entry_price = Decimal("0")

        else:  # Side.SELL
            self.total_sold_qty += fill_qty
            self.total_sold_notional += fill_notional
            self.net_qty -= fill_qty

            if old_net_qty <= 0:
                # Adding to short or opening short: update weighted average entry price
                new_total_qty = abs(old_net_qty) + fill_qty
                if new_total_qty > 0:
                    old_cost = Decimal(str(abs(old_net_qty))) * self.average_entry_price
                    self.average_entry_price = (old_cost + fill_notional) / Decimal(str(new_total_qty))
            else:
                # Closing long position partially or fully
                closed_qty = min(old_net_qty, fill_qty)
                # Long PnL = (exit_price - entry_price) * closed_qty
                pnl = (fill_price - self.average_entry_price) * Decimal(str(closed_qty))
                self.realized_pnl += pnl

                if self.net_qty < 0:
                    # Flipped to short: new entry price is fill_price
                    self.average_entry_price = fill_price
                elif self.net_qty == 0:
                    self.average_entry_price = Decimal("0")


class PositionTracker:
    """Portfolio position and exposure tracker across all simulated instruments."""

    def __init__(self) -> None:
        self._positions: dict[UUID, InstrumentPosition] = {}

    def get_position(self, instrument_id: UUID) -> int:
        """Return net signed quantity for instrument (positive=long, negative=short)."""
        pos = self._positions.get(instrument_id)
        return pos.net_qty if pos else 0

    def get_instrument_position(self, instrument_id: UUID) -> InstrumentPosition:
        """Return full InstrumentPosition state."""
        if instrument_id not in self._positions:
            self._positions[instrument_id] = InstrumentPosition(instrument_id=instrument_id)
        return self._positions[instrument_id]

    def record_fill(
        self,
        fill: Fill,
        side: Side,
        instrument_id: UUID,
    ) -> InstrumentPosition:
        """Record a fill and update signed inventory immediately."""
        pos = self.get_instrument_position(instrument_id)
        pos.update(fill, side)
        return pos

    def get_portfolio_gross_exposure(
        self, prices: Mapping[UUID, Decimal]
    ) -> Decimal:
        """Calculate total gross exposure: sum(abs(net_qty) * price)."""
        total = Decimal("0")
        for inst_id, pos in self._positions.items():
            if pos.net_qty != 0:
                price = prices.get(inst_id, pos.average_entry_price)
                total += Decimal(str(abs(pos.net_qty))) * price
        return total

    def get_all_positions(self) -> dict[UUID, int]:
        """Return mapping of instrument_id to signed net quantity."""
        return {k: v.net_qty for k, v in self._positions.items()}

    def get_realized_pnl(self, instrument_id: UUID | None = None) -> Decimal:
        """Return total realized PnL across all instruments or for a single instrument."""
        if instrument_id is not None:
            pos = self._positions.get(instrument_id)
            return pos.realized_pnl if pos else Decimal("0")
        return sum((p.realized_pnl for p in self._positions.values()), Decimal("0"))

    def reset(self) -> None:
        """Reset all positions."""
        self._positions.clear()
