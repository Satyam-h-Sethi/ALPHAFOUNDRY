"""DataPipeline — end-to-end ingest orchestrator.

Flow for each event::

    Adapter → Normaliser → Validator → Deduplicator
            → StalenessDetector → MarketDataStore → AuditLog

Every event produces exactly one ``IngestOutcome`` recorded in the audit
log.  Invalid, duplicate, or stale events are rejected before storage.

Usage::

    from alphafoundry.pipeline import DataPipeline, PipelineConfig

    cfg = PipelineConfig(db_path=":memory:", adapter_id="synthetic")
    pipeline = DataPipeline(cfg)

    # Register instruments for lot-size / tick-size checks
    for instr in adapter.get_instruments():
        pipeline.register_instrument(instr)

    # Ingest a batch of quotes
    async for quote in adapter.stream_quotes():
        outcome = await pipeline.ingest_quote(quote)
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from alphafoundry.domain import OHLCBar, Quote, Trade
from alphafoundry.domain.instruments import Instrument
from alphafoundry.pipeline.audit import AuditLog, IngestOutcome
from alphafoundry.pipeline.config import PipelineConfig
from alphafoundry.pipeline.deduplicator import Deduplicator
from alphafoundry.pipeline.normaliser import Normaliser
from alphafoundry.pipeline.staleness import StalenessDetector
from alphafoundry.pipeline.store import MarketDataStore
from alphafoundry.pipeline.validator import Validator


class DataPipeline:
    """Orchestrate the full ingest pipeline for a single adapter.

    All sub-components share the same ``PipelineConfig`` so they read from
    and write to the same DuckDB database file.
    """

    def __init__(self, cfg: PipelineConfig) -> None:
        self._cfg = cfg
        self._normaliser = Normaliser()
        self._validator = Validator(cfg)
        self._deduplicator = Deduplicator()
        self._staleness = StalenessDetector(cfg)
        self._store = MarketDataStore(cfg)
        self._audit = AuditLog(cfg)

    # ------------------------------------------------------------------
    # Instrument registry
    # ------------------------------------------------------------------

    def register_instrument(self, instr: Instrument) -> None:
        """Register an instrument for tick-size / lot-size validation."""
        self._validator.register_instrument(instr)

    # ------------------------------------------------------------------
    # Per-event ingest
    # ------------------------------------------------------------------

    async def ingest_quote(self, raw: Quote) -> IngestOutcome:
        """Process one quote through the full pipeline."""
        quote = self._normaliser.normalise_quote(raw)

        # --- Deduplication -------------------------------------------
        if self._deduplicator.is_duplicate(quote.idempotency_key):
            self._audit.record(
                idempotency_key=quote.idempotency_key,
                outcome=IngestOutcome.DUPLICATE,
                raw_size_bytes=len(quote.model_dump_json().encode()),
            )
            return IngestOutcome.DUPLICATE

        # --- Validation ----------------------------------------------
        result = self._validator.validate_quote(quote)
        if not result.is_valid:
            self._audit.record(
                idempotency_key=quote.idempotency_key,
                outcome=IngestOutcome.VALIDATION_FAILED,
                raw_size_bytes=len(quote.model_dump_json().encode()),
                error_detail=result.error_detail,
            )
            return IngestOutcome.VALIDATION_FAILED

        # --- Staleness -----------------------------------------------
        if self._staleness.is_stale_quote(quote):
            self._audit.record(
                idempotency_key=quote.idempotency_key,
                outcome=IngestOutcome.STALE_REJECTED,
                raw_size_bytes=len(quote.model_dump_json().encode()),
                error_detail=(
                    f"received_at={quote.received_at} lags "
                    f"timestamp={quote.timestamp} by more than "
                    f"{self._cfg.staleness_seconds}s"
                ),
            )
            return IngestOutcome.STALE_REJECTED

        # --- Store ---------------------------------------------------
        self._store.insert_quote(quote)
        self._audit.record(
            idempotency_key=quote.idempotency_key,
            outcome=IngestOutcome.ACCEPTED,
            raw_size_bytes=len(quote.model_dump_json().encode()),
        )
        return IngestOutcome.ACCEPTED

    async def ingest_trade(self, raw: Trade) -> IngestOutcome:
        """Process one trade through the full pipeline."""
        trade = self._normaliser.normalise_trade(raw)

        if self._deduplicator.is_duplicate(trade.idempotency_key):
            self._audit.record(
                idempotency_key=trade.idempotency_key,
                outcome=IngestOutcome.DUPLICATE,
                raw_size_bytes=len(trade.model_dump_json().encode()),
            )
            return IngestOutcome.DUPLICATE

        result = self._validator.validate_trade(trade)
        if not result.is_valid:
            self._audit.record(
                idempotency_key=trade.idempotency_key,
                outcome=IngestOutcome.VALIDATION_FAILED,
                raw_size_bytes=len(trade.model_dump_json().encode()),
                error_detail=result.error_detail,
            )
            return IngestOutcome.VALIDATION_FAILED

        if self._staleness.is_stale_trade(trade):
            self._audit.record(
                idempotency_key=trade.idempotency_key,
                outcome=IngestOutcome.STALE_REJECTED,
                raw_size_bytes=len(trade.model_dump_json().encode()),
                error_detail=(
                    f"received_at={trade.received_at} lags "
                    f"timestamp={trade.timestamp} by more than "
                    f"{self._cfg.staleness_seconds}s"
                ),
            )
            return IngestOutcome.STALE_REJECTED

        self._store.insert_trade(trade)
        self._audit.record(
            idempotency_key=trade.idempotency_key,
            outcome=IngestOutcome.ACCEPTED,
            raw_size_bytes=len(trade.model_dump_json().encode()),
        )
        return IngestOutcome.ACCEPTED

    async def ingest_bar(self, raw: OHLCBar) -> IngestOutcome:
        """Process one OHLC bar through the full pipeline."""
        bar = self._normaliser.normalise_bar(raw)
        key = f"{bar.venue_id}:{bar.instrument_id}:{bar.freq}:{bar.bar_open.isoformat()}"

        if self._deduplicator.is_duplicate(key):
            self._audit.record(
                idempotency_key=key,
                outcome=IngestOutcome.DUPLICATE,
                raw_size_bytes=len(bar.model_dump_json().encode()),
            )
            return IngestOutcome.DUPLICATE

        result = self._validator.validate_bar(bar)
        if not result.is_valid:
            self._audit.record(
                idempotency_key=key,
                outcome=IngestOutcome.VALIDATION_FAILED,
                raw_size_bytes=len(bar.model_dump_json().encode()),
                error_detail=result.error_detail,
            )
            return IngestOutcome.VALIDATION_FAILED

        if self._staleness.is_stale_bar(bar):
            self._audit.record(
                idempotency_key=key,
                outcome=IngestOutcome.STALE_REJECTED,
                raw_size_bytes=len(bar.model_dump_json().encode()),
                error_detail=(
                    f"bar_close={bar.bar_close} is more than "
                    f"{self._cfg.staleness_seconds}s in the past"
                ),
            )
            return IngestOutcome.STALE_REJECTED

        self._store.insert_bar(bar)
        self._audit.record(
            idempotency_key=key,
            outcome=IngestOutcome.ACCEPTED,
            raw_size_bytes=len(bar.model_dump_json().encode()),
        )
        return IngestOutcome.ACCEPTED

    # ------------------------------------------------------------------
    # Batch helpers — consume entire async streams
    # ------------------------------------------------------------------

    async def run_quotes(self, stream: AsyncIterator[Quote]) -> dict[str, int]:
        """Drain a quote stream; return outcome counts."""
        counts: dict[str, int] = {o.value: 0 for o in IngestOutcome}
        async for quote in stream:
            outcome = await self.ingest_quote(quote)
            counts[outcome.value] += 1
        return counts

    async def run_trades(self, stream: AsyncIterator[Trade]) -> dict[str, int]:
        """Drain a trade stream; return outcome counts."""
        counts: dict[str, int] = {o.value: 0 for o in IngestOutcome}
        async for trade in stream:
            outcome = await self.ingest_trade(trade)
            counts[outcome.value] += 1
        return counts

    # ------------------------------------------------------------------
    # Accessors (pass-through for tests and downstream components)
    # ------------------------------------------------------------------

    @property
    def store(self) -> MarketDataStore:
        return self._store

    @property
    def audit(self) -> AuditLog:
        return self._audit

    def close(self) -> None:
        """Flush and close all underlying connections."""
        self._store.close()
        self._audit.close()
