"""IMarketDataAdapter — interface every data provider must implement.

Concrete implementations live in sub-modules (synthetic, csv_file, …).
The core platform imports only this interface; it never imports a concrete
adapter directly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from datetime import datetime
from uuid import UUID

from alphafoundry.domain import OHLCBar, Quote, Trade
from alphafoundry.domain.instruments import Instrument


class IMarketDataAdapter(ABC):
    """Abstract base for all market-data providers."""

    @abstractmethod
    def get_instruments(self) -> list[Instrument]:
        """Return the list of instruments this adapter can supply."""

    @abstractmethod
    def get_ohlc(
        self,
        instrument_id: UUID,
        from_dt: datetime,
        to_dt: datetime,
        freq: str,
    ) -> list[OHLCBar]:
        """Return OHLC bars for *instrument_id* in [from_dt, to_dt] at *freq*."""

    @abstractmethod
    def stream_quotes(self) -> AsyncIterator[Quote]:
        """Yield quotes in chronological order."""

    @abstractmethod
    def stream_trades(self) -> AsyncIterator[Trade]:
        """Yield trades in chronological order."""
