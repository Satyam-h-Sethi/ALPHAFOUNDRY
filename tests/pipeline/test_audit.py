"""Tests for AuditLog."""

from __future__ import annotations

import pytest

from alphafoundry.pipeline.audit import AuditLog, IngestOutcome
from alphafoundry.pipeline.config import PipelineConfig


@pytest.fixture
def audit() -> AuditLog:
    cfg = PipelineConfig(db_path=":memory:", adapter_id="test_adapter")
    return AuditLog(cfg)


class TestAuditLog:
    def test_record_accepted(self, audit: AuditLog):
        iid = audit.record(
            idempotency_key="v:i:0",
            outcome=IngestOutcome.ACCEPTED,
            raw_size_bytes=128,
        )
        assert iid  # non-empty UUID string

    def test_record_validation_failed_stores_detail(self, audit: AuditLog):
        audit.record(
            idempotency_key="v:i:1",
            outcome=IngestOutcome.VALIDATION_FAILED,
            error_detail="price_sanity: bid_price=0 must be in (0, 1000000]",
        )
        rows = audit.query(outcome=IngestOutcome.VALIDATION_FAILED)
        assert len(rows) == 1
        assert "price_sanity" in rows[0]["error_detail"]

    def test_query_all_returns_all_rows(self, audit: AuditLog):
        for outcome in IngestOutcome:
            audit.record(idempotency_key=f"v:i:{outcome.value}", outcome=outcome)
        rows = audit.query()
        assert len(rows) == len(IngestOutcome)

    def test_query_by_outcome_filters_correctly(self, audit: AuditLog):
        audit.record(idempotency_key="k:ACCEPTED", outcome=IngestOutcome.ACCEPTED)
        audit.record(idempotency_key="k:DUP", outcome=IngestOutcome.DUPLICATE)
        accepted = audit.query(outcome=IngestOutcome.ACCEPTED)
        assert all(r["outcome"] == "ACCEPTED" for r in accepted)
        assert len(accepted) == 1

    def test_adapter_id_stored(self, audit: AuditLog):
        audit.record(idempotency_key="k:0", outcome=IngestOutcome.ACCEPTED)
        rows = audit.query()
        assert rows[0]["adapter_id"] == "test_adapter"

    def test_duplicate_records_null_error_detail(self, audit: AuditLog):
        audit.record(idempotency_key="k:0", outcome=IngestOutcome.DUPLICATE)
        rows = audit.query(outcome=IngestOutcome.DUPLICATE)
        assert rows[0]["error_detail"] is None
