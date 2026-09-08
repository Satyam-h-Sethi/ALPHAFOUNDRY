"""CsvFileAdapter — replay historical market data from CSV files.

File format
-----------
Quotes CSV columns (order matters; header row required):

    idempotency_key, instrument_id, venue_id, timestamp, received_at,
    sequence_id, bid_price, bid_qty, ask_price, ask_qty,
    last_trade_price, session_status, is_stale

Trades CSV columns:

    idempotency_key, instrument_id, venue_id, timestamp, received_at,
    sequence_id, price, qty, side

OHLC bars CSV columns:

    instrument_id, venue_id, freq, bar_open, bar_close,
    open, high, low, close, volume, num_trades, vwap, is_complete

All timestamps must be ISO-8601 strings with UTC offset (e.g.
``2024-01-15T03:45:00+00:00``).  Prices are decimal strings.

Usage::

    from alphafoundry.adapters.csv_file import CsvFileAdapter, CsvAdapterConfig

    cfg = CsvAdapterConfig(
        quotes_path="tests/fixtures/sample_quotes.csv",
        trades_path="tests/fixtures/sample_trades.csv",
    )
    adapter = CsvFileAdapter(cfg)
    async for quote in adapter.stream_quotes():
        ...
"""

from __future__ import annotations

import csv
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from alphafoundry.adapters import IMarketDataAdapter
from alphafoundry.domain import OHLCBar, Quote, Trade
from alphafoundry.domain.enums import SessionStatus, TradeSide
from alphafoundry.domain.instruments import Instrument


@dataclass(frozen=True)
class CsvAdapterConfig:
    """Paths to the CSV files the adapter will replay.

    All paths are optional; omit a path to produce an empty stream for
    that event type.
    """

    quotes_path: str | None = None
    trades_path: str | None = None
    bars_path: str | None = None
    # Instruments are either loaded from a CSV or injected directly.
    instruments: list[Instrument] = field(default_factory=list)


def _parse_dt(s: str) -> datetime:
    """Parse an ISO-8601 datetime string."""
    return datetime.fromisoformat(s)


def _parse_decimal(s: str) -> Decimal:
    return Decimal(s)


def _opt_decimal(s: str) -> Decimal | None:
    return Decimal(s) if s else None


def _opt_bool(s: str) -> bool:
    return s.strip().lower() in ("true", "1", "yes")


class CsvFileAdapter(IMarketDataAdapter):
    """Replay market-data events from CSV files through the standard adapter interface.

    Events are yielded in file order (i.e. chronological order is the
    responsibility of the CSV producer).
    """

    def __init__(self, cfg: CsvAdapterConfig) -> None:
        self._cfg = cfg

    # ------------------------------------------------------------------
    # IMarketDataAdapter
    # ------------------------------------------------------------------

    def get_instruments(self) -> list[Instrument]:
        return list(self._cfg.instruments)

    def get_ohlc(
        self,
        instrument_id: UUID,
        from_dt: datetime,
        to_dt: datetime,
        freq: str,
    ) -> list[OHLCBar]:
        """Return bars matching the given filters from the bars CSV."""
        bars = list(self._iter_bars())
        return [
            b
            for b in bars
            if b.instrument_id == instrument_id
            and b.freq == freq
            and b.bar_open >= from_dt
            and b.bar_open <= to_dt
        ]

    async def stream_quotes(self) -> AsyncIterator[Quote]:  # type: ignore[override]
        """Yield quotes from the quotes CSV in file order."""
        if self._cfg.quotes_path is None:
            return
        path = Path(self._cfg.quotes_path)
        with path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                yield self._parse_quote(row)

    async def stream_trades(self) -> AsyncIterator[Trade]:  # type: ignore[override]
        """Yield trades from the trades CSV in file order."""
        if self._cfg.trades_path is None:
            return
        path = Path(self._cfg.trades_path)
        with path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                yield self._parse_trade(row)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _iter_bars(self):
        if self._cfg.bars_path is None:
            return
        path = Path(self._cfg.bars_path)
        with path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                yield self._parse_bar(row)

    @staticmethod
    def _parse_quote(row: dict[str, str]) -> Quote:
        return Quote(
            idempotency_key=row["idempotency_key"],
            instrument_id=UUID(row["instrument_id"]),
            venue_id=row["venue_id"],
            timestamp=_parse_dt(row["timestamp"]),
            received_at=_parse_dt(row["received_at"]),
            sequence_id=int(row["sequence_id"]),
            bid_price=_parse_decimal(row["bid_price"]),
            bid_qty=int(row["bid_qty"]),
            ask_price=_parse_decimal(row["ask_price"]),
            ask_qty=int(row["ask_qty"]),
            last_trade_price=_opt_decimal(row.get("last_trade_price", "")),
            session_status=SessionStatus(row.get("session_status", "OPEN")),
            is_stale=_opt_bool(row.get("is_stale", "false")),
        )

    @staticmethod
    def _parse_trade(row: dict[str, str]) -> Trade:
        return Trade(
            idempotency_key=row["idempotency_key"],
            instrument_id=UUID(row["instrument_id"]),
            venue_id=row["venue_id"],
            timestamp=_parse_dt(row["timestamp"]),
            received_at=_parse_dt(row["received_at"]),
            sequence_id=int(row["sequence_id"]),
            price=_parse_decimal(row["price"]),
            qty=int(row["qty"]),
            side=TradeSide(row.get("side", "UNKNOWN")),
        )

    @staticmethod
    def _parse_bar(row: dict[str, str]) -> OHLCBar:
        return OHLCBar(
            instrument_id=UUID(row["instrument_id"]),
            venue_id=row["venue_id"],
            freq=row["freq"],
            bar_open=_parse_dt(row["bar_open"]),
            bar_close=_parse_dt(row["bar_close"]),
            open=_parse_decimal(row["open"]),
            high=_parse_decimal(row["high"]),
            low=_parse_decimal(row["low"]),
            close=_parse_decimal(row["close"]),
            volume=int(row["volume"]),
            num_trades=int(row["num_trades"]),
            vwap=_opt_decimal(row.get("vwap", "")),
            is_complete=_opt_bool(row.get("is_complete", "true")),
        )
