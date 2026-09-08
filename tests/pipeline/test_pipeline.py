"""End-to-end pipeline integration tests."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from alphafoundry.domain import Quote, Trade
from alphafoundry.domain.enums import InstrumentType, SessionStatus, TradeSide
from alphafoundry.domain.instruments import Instrument
from alphafoundry.pipeline import DataPipeline, IngestOutcome, PipelineConfig

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_INSTR_ID = uuid4()
_TS = datetime(2024, 1, 15, 4, 0, 0, tzinfo=UTC)  # within session hours

_INSTR = Instrument(
    instrument_id=_INSTR_ID,
    symbol="E2ETEST",
    venue_id="E2E",
    instrument_type=InstrumentType.EQ,
    lot_size=1,
    tick_size=Decimal("0.05"),
)


@pytest.fixture
def cfg() -> PipelineConfig:
    return PipelineConfig(
        db_path=":memory:",
        adapter_id="e2e_test",
        staleness_seconds=60.0,
        future_gate_seconds=5.0,
        past_gate_seconds=300.0,
    )


@pytest.fixture
def pipeline(cfg: PipelineConfig) -> DataPipeline:
    p = DataPipeline(cfg)
    p.register_instrument(_INSTR)
    return p


def _make_quote(seq: int = 0, **overrides) -> Quote:
    defaults = {
        "idempotency_key": f"e2e:i:{seq}",
        "instrument_id": _INSTR_ID,
        "venue_id": "E2E",
        "timestamp": _TS + timedelta(seconds=seq),
        "received_at": _TS + timedelta(seconds=seq + 1),
        "sequence_id": seq,
        "bid_price": Decimal("100.05"),
        "bid_qty": 10,
        "ask_price": Decimal("100.10"),
        "ask_qty": 10,
        "session_status": SessionStatus.OPEN,
    }
    defaults.update(overrides)
    return Quote(**defaults)


def _make_trade(seq: int = 0, **overrides) -> Trade:
    defaults = {
        "idempotency_key": f"e2e:trade:i:{seq}",
        "instrument_id": _INSTR_ID,
        "venue_id": "E2E",
        "timestamp": _TS + timedelta(seconds=seq),
        "received_at": _TS + timedelta(seconds=seq + 1),
        "sequence_id": seq,
        "price": Decimal("100.05"),
        "qty": 10,
        "side": TradeSide.BUY,
    }
    defaults.update(overrides)
    return Trade(**defaults)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPipelineAccepted:
    def test_valid_quote_accepted(self, pipeline: DataPipeline):
        outcome = asyncio.run(pipeline.ingest_quote(_make_quote()))
        assert outcome == IngestOutcome.ACCEPTED
        assert pipeline.store.count_quotes() == 1

    def test_valid_trade_accepted(self, pipeline: DataPipeline):
        outcome = asyncio.run(pipeline.ingest_trade(_make_trade()))
        assert outcome == IngestOutcome.ACCEPTED
        assert pipeline.store.count_trades() == 1

    def test_accepted_event_recorded_in_audit(self, pipeline: DataPipeline):
        asyncio.run(pipeline.ingest_quote(_make_quote()))
        rows = pipeline.audit.query(outcome=IngestOutcome.ACCEPTED)
        assert len(rows) == 1
        assert rows[0]["outcome"] == "ACCEPTED"


class TestPipelineDuplicate:
    def test_duplicate_quote_rejected(self, pipeline: DataPipeline):
        q = _make_quote()
        asyncio.run(pipeline.ingest_quote(q))
        outcome = asyncio.run(pipeline.ingest_quote(q))
        assert outcome == IngestOutcome.DUPLICATE
        assert pipeline.store.count_quotes() == 1  # only first stored

    def test_duplicate_recorded_in_audit(self, pipeline: DataPipeline):
        q = _make_quote()
        asyncio.run(pipeline.ingest_quote(q))
        asyncio.run(pipeline.ingest_quote(q))
        dups = pipeline.audit.query(outcome=IngestOutcome.DUPLICATE)
        assert len(dups) == 1


class TestPipelineValidationFailed:
    def test_invalid_quote_not_stored(self, pipeline: DataPipeline):
        # Future-gate: timestamp 10 s ahead of received_at
        q = _make_quote(
            timestamp=_TS + timedelta(seconds=10),
            received_at=_TS,
        )
        outcome = asyncio.run(pipeline.ingest_quote(q))
        assert outcome == IngestOutcome.VALIDATION_FAILED
        assert pipeline.store.count_quotes() == 0

    def test_validation_failure_recorded_with_detail(self, pipeline: DataPipeline):
        q = _make_quote(
            timestamp=_TS + timedelta(seconds=10),
            received_at=_TS,
        )
        asyncio.run(pipeline.ingest_quote(q))
        rows = pipeline.audit.query(outcome=IngestOutcome.VALIDATION_FAILED)
        assert len(rows) == 1
        assert rows[0]["error_detail"] is not None


class TestPipelineStale:
    def test_stale_quote_rejected(self, pipeline: DataPipeline):
        # received_at is 2 min after timestamp → staleness_seconds=60 → stale
        q = _make_quote(
            timestamp=_TS,
            received_at=_TS + timedelta(seconds=120),
        )
        outcome = asyncio.run(pipeline.ingest_quote(q))
        assert outcome == IngestOutcome.STALE_REJECTED
        assert pipeline.store.count_quotes() == 0

    def test_stale_event_recorded_in_audit(self, pipeline: DataPipeline):
        q = _make_quote(
            timestamp=_TS,
            received_at=_TS + timedelta(seconds=120),
        )
        asyncio.run(pipeline.ingest_quote(q))
        rows = pipeline.audit.query(outcome=IngestOutcome.STALE_REJECTED)
        assert len(rows) == 1


class TestPipelineBatchRun:
    async def _stream(self, items):
        for item in items:
            yield item

    def test_run_quotes_returns_counts(self, pipeline: DataPipeline):
        quotes = [_make_quote(i) for i in range(5)]

        async def _run():
            async def _gen():
                for q in quotes:
                    yield q

            return await pipeline.run_quotes(_gen())

        counts = asyncio.run(_run())
        assert counts["ACCEPTED"] == 5
        assert pipeline.store.count_quotes() == 5

    def test_run_trades_returns_counts(self, pipeline: DataPipeline):
        trades = [_make_trade(i) for i in range(3)]

        async def _run():
            async def _gen():
                for t in trades:
                    yield t

            return await pipeline.run_trades(_gen())

        counts = asyncio.run(_run())
        assert counts["ACCEPTED"] == 3


class TestEndToEndRoundTrip:
    """Ingest synthetic-style quotes, then verify they are queryable."""

    def test_round_trip_quotes(self, pipeline: DataPipeline):
        n = 10
        for i in range(n):
            asyncio.run(pipeline.ingest_quote(_make_quote(i)))

        assert pipeline.store.count_quotes() == n
        rows = pipeline.store.fetch_quotes(instrument_id=_INSTR_ID)
        assert len(rows) == n
        # Audit has n ACCEPTED records
        accepted = pipeline.audit.query(outcome=IngestOutcome.ACCEPTED)
        assert len(accepted) == n

    def test_round_trip_trades(self, pipeline: DataPipeline):
        n = 5
        for i in range(n):
            asyncio.run(pipeline.ingest_trade(_make_trade(i)))

        assert pipeline.store.count_trades() == n
        rows = pipeline.store.fetch_trades(instrument_id=_INSTR_ID)
        assert len(rows) == n
