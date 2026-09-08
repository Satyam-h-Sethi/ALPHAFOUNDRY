"""Staleness detector — flags events that arrived too late to be actionable.

Per data-model.md §8 an event is stale when its ``received_at`` timestamp
lags its ``timestamp`` by more than ``staleness_seconds`` (default 60 s).
Stale events are recorded in the audit log with outcome STALE_REJECTED and
not written to primary storage.

The domain model's ``Quote.is_stale`` field is *informational*: adapters may
pre-set it, but the pipeline re-evaluates it independently so the store
always reflects the pipeline's authoritative judgement.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from alphafoundry.domain import OHLCBar, Quote, Trade
from alphafoundry.pipeline.config import PipelineConfig


class StalenessDetector:
    """Evaluate whether a market-data event is stale on arrival."""

    def __init__(self, cfg: PipelineConfig) -> None:
        self._threshold = timedelta(seconds=cfg.staleness_seconds)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def is_stale_quote(self, quote: Quote) -> bool:
        """Return True if the quote is stale (received too long after event time)."""
        return self._is_stale(quote.timestamp, quote.received_at)

    def is_stale_trade(self, trade: Trade) -> bool:
        """Return True if the trade is stale."""
        return self._is_stale(trade.timestamp, trade.received_at)

    def is_stale_bar(self, bar: OHLCBar) -> bool:
        """Return True if the OHLC bar is stale.

        OHLCBar has no ``received_at``; staleness is measured from
        ``bar_close`` (the interval end) against the current wall clock.
        A bar whose close time is more than ``staleness_seconds`` in the
        past is considered stale.
        """
        now = datetime.now(UTC)
        return self._is_stale(bar.bar_close, now)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _is_stale(self, event_time: datetime, received_at: datetime) -> bool:
        ts = event_time if event_time.tzinfo is not None else event_time.replace(tzinfo=UTC)
        ra = received_at if received_at.tzinfo is not None else received_at.replace(tzinfo=UTC)
        return (ra - ts) > self._threshold
