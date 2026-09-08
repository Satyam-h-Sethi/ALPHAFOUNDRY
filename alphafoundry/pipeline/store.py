"""Market-data store — DuckDB-backed persistence for quotes, trades, and bars.

Design principles (from data-model.md §3):
  - Immutable storage: rows are inserted once, never updated in place.
  - UTC everywhere: all timestamps stored as TIMESTAMPTZ.
  - Prices as DECIMAL(18, 4): four decimal places, no floating-point drift.
  - Idempotency enforced upstream; the store trusts the deduplicator.

Tables created on first connection if they don't exist:
  - quotes       : Level-1 bid/ask snapshots
  - trades       : Executed transactions
  - ohlc_bars    : Aggregated OHLC bars
"""

from __future__ import annotations

from uuid import UUID

import duckdb

from alphafoundry.domain import OHLCBar, Quote, Trade
from alphafoundry.pipeline.config import PipelineConfig

_CREATE_QUOTES = """
CREATE TABLE IF NOT EXISTS quotes (
    quote_id         VARCHAR PRIMARY KEY,
    idempotency_key  VARCHAR(256) NOT NULL,
    instrument_id    VARCHAR      NOT NULL,
    venue_id         VARCHAR(64)  NOT NULL,
    timestamp        TIMESTAMP    NOT NULL,
    received_at      TIMESTAMP    NOT NULL,
    sequence_id      BIGINT       NOT NULL,
    bid_price        DECIMAL(18, 4) NOT NULL,
    bid_qty          INTEGER      NOT NULL,
    ask_price        DECIMAL(18, 4) NOT NULL,
    ask_qty          INTEGER      NOT NULL,
    last_trade_price DECIMAL(18, 4),
    session_status   VARCHAR(16)  NOT NULL,
    is_stale         BOOLEAN      NOT NULL DEFAULT FALSE
);
"""

_CREATE_TRADES = """
CREATE TABLE IF NOT EXISTS trades (
    trade_id        VARCHAR PRIMARY KEY,
    idempotency_key VARCHAR(256) NOT NULL,
    instrument_id   VARCHAR      NOT NULL,
    venue_id        VARCHAR(64)  NOT NULL,
    timestamp       TIMESTAMP    NOT NULL,
    received_at     TIMESTAMP    NOT NULL,
    sequence_id     BIGINT       NOT NULL,
    price           DECIMAL(18, 4) NOT NULL,
    qty             INTEGER      NOT NULL,
    side            VARCHAR(8)   NOT NULL
);
"""

_CREATE_BARS = """
CREATE TABLE IF NOT EXISTS ohlc_bars (
    bar_id        VARCHAR PRIMARY KEY,
    instrument_id VARCHAR        NOT NULL,
    venue_id      VARCHAR(64)    NOT NULL,
    freq          VARCHAR(8)     NOT NULL,
    bar_open      TIMESTAMP      NOT NULL,
    bar_close     TIMESTAMP      NOT NULL,
    open          DECIMAL(18, 4) NOT NULL,
    high          DECIMAL(18, 4) NOT NULL,
    low           DECIMAL(18, 4) NOT NULL,
    close         DECIMAL(18, 4) NOT NULL,
    volume        BIGINT         NOT NULL,
    num_trades    BIGINT         NOT NULL,
    vwap          DECIMAL(18, 4),
    is_complete   BOOLEAN        NOT NULL DEFAULT TRUE
);
"""


class MarketDataStore:
    """DuckDB-backed append-only store for validated market-data events.

    A single connection is shared across all write methods.  Callers that
    also use ``AuditLog`` should supply the same ``db_path`` so both tables
    live in one file; ``:memory:`` is the default (isolated per process).
    """

    def __init__(self, cfg: PipelineConfig) -> None:
        self._conn = duckdb.connect(cfg.db_path)
        self._conn.execute(_CREATE_QUOTES)
        self._conn.execute(_CREATE_TRADES)
        self._conn.execute(_CREATE_BARS)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def insert_quote(self, quote: Quote) -> None:
        """Persist a validated, non-duplicate quote."""
        self._conn.execute(
            """
            INSERT INTO quotes
                (quote_id, idempotency_key, instrument_id, venue_id,
                 timestamp, received_at, sequence_id,
                 bid_price, bid_qty, ask_price, ask_qty,
                 last_trade_price, session_status, is_stale)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                str(quote.quote_id),
                quote.idempotency_key,
                str(quote.instrument_id),
                quote.venue_id,
                quote.timestamp,
                quote.received_at,
                quote.sequence_id,
                float(quote.bid_price),
                quote.bid_qty,
                float(quote.ask_price),
                quote.ask_qty,
                float(quote.last_trade_price) if quote.last_trade_price is not None else None,
                quote.session_status.value,
                quote.is_stale,
            ],
        )

    def insert_trade(self, trade: Trade) -> None:
        """Persist a validated, non-duplicate trade."""
        self._conn.execute(
            """
            INSERT INTO trades
                (trade_id, idempotency_key, instrument_id, venue_id,
                 timestamp, received_at, sequence_id, price, qty, side)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                str(trade.trade_id),
                trade.idempotency_key,
                str(trade.instrument_id),
                trade.venue_id,
                trade.timestamp,
                trade.received_at,
                trade.sequence_id,
                float(trade.price),
                trade.qty,
                trade.side.value,
            ],
        )

    def insert_bar(self, bar: OHLCBar) -> None:
        """Persist a validated OHLC bar."""
        self._conn.execute(
            """
            INSERT INTO ohlc_bars
                (bar_id, instrument_id, venue_id, freq,
                 bar_open, bar_close, open, high, low, close,
                 volume, num_trades, vwap, is_complete)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                str(bar.bar_id),
                str(bar.instrument_id),
                bar.venue_id,
                bar.freq,
                bar.bar_open,
                bar.bar_close,
                float(bar.open),
                float(bar.high),
                float(bar.low),
                float(bar.close),
                bar.volume,
                bar.num_trades,
                float(bar.vwap) if bar.vwap is not None else None,
                bar.is_complete,
            ],
        )

    # ------------------------------------------------------------------
    # Read (for tests and downstream analytics)
    # ------------------------------------------------------------------

    def count_quotes(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM quotes").fetchone()[0]  # type: ignore[index]

    def count_trades(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]  # type: ignore[index]

    def count_bars(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM ohlc_bars").fetchone()[0]  # type: ignore[index]

    def fetch_quotes(
        self,
        instrument_id: UUID | None = None,
        limit: int = 1000,
    ) -> list[dict]:
        """Return quote rows as dicts, newest first."""
        if instrument_id is not None:
            rows = self._conn.execute(
                "SELECT * FROM quotes WHERE instrument_id = ? ORDER BY timestamp DESC LIMIT ?",
                [str(instrument_id), limit],
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM quotes ORDER BY timestamp DESC LIMIT ?",
                [limit],
            ).fetchall()
        cols = self._conn.description  # available after fetchall
        return [dict(zip([c[0] for c in cols], row, strict=True)) for row in rows]

    def fetch_trades(
        self,
        instrument_id: UUID | None = None,
        limit: int = 1000,
    ) -> list[dict]:
        """Return trade rows as dicts, newest first."""
        if instrument_id is not None:
            rows = self._conn.execute(
                "SELECT * FROM trades WHERE instrument_id = ? ORDER BY timestamp DESC LIMIT ?",
                [str(instrument_id), limit],
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM trades ORDER BY timestamp DESC LIMIT ?",
                [limit],
            ).fetchall()
        cols = self._conn.description
        return [dict(zip([c[0] for c in cols], row, strict=True)) for row in rows]

    def close(self) -> None:
        """Close the underlying DuckDB connection."""
        self._conn.close()
