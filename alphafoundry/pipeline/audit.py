"""Audit log — records every ingest event and its outcome.

Schema (from data-model.md §6):

    Column            Type             Notes
    ────────────────  ───────────────  ─────────────────────────────────────
    ingest_id         UUID PRIMARY KEY Auto-generated per record
    adapter_id        VARCHAR(64)      Label from PipelineConfig
    received_at       TIMESTAMPTZ      Wall-clock time of pipeline processing
    raw_size_bytes    INT              Byte size of the serialised event
    outcome           VARCHAR(32)      ACCEPTED | DUPLICATE | VALIDATION_FAILED | STALE_REJECTED
    error_detail      TEXT             NULL for ACCEPTED/DUPLICATE; message otherwise
    idempotency_key   VARCHAR(256)     Key used for dedup check

The audit log is append-only; rows are never updated or deleted.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

import duckdb

from alphafoundry.pipeline.config import PipelineConfig


class IngestOutcome(StrEnum):
    """Possible outcomes for a single ingest event."""

    ACCEPTED = "ACCEPTED"
    DUPLICATE = "DUPLICATE"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    STALE_REJECTED = "STALE_REJECTED"


_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS ingest_events (
    ingest_id         VARCHAR PRIMARY KEY,
    adapter_id        VARCHAR(64)  NOT NULL,
    received_at       TIMESTAMP    NOT NULL,
    raw_size_bytes    INTEGER      NOT NULL,
    outcome           VARCHAR(32)  NOT NULL,
    error_detail      TEXT,
    idempotency_key   VARCHAR(256) NOT NULL
);
"""


class AuditLog:
    """Append-only audit log backed by DuckDB.

    A single ``AuditLog`` instance owns its DuckDB connection.  Callers that
    share a database file with ``MarketDataStore`` should pass the same
    ``db_path`` — DuckDB supports multiple tables in one file.
    """

    def __init__(self, cfg: PipelineConfig) -> None:
        self._adapter_id = cfg.adapter_id
        self._conn = duckdb.connect(cfg.db_path)
        self._conn.execute(_CREATE_TABLE)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def record(
        self,
        *,
        idempotency_key: str,
        outcome: IngestOutcome,
        raw_size_bytes: int = 0,
        error_detail: str | None = None,
    ) -> str:
        """Append one audit record; return its ``ingest_id``."""
        ingest_id = str(uuid4())
        received_at = datetime.now(UTC)
        self._conn.execute(
            """
            INSERT INTO ingest_events
                (ingest_id, adapter_id, received_at, raw_size_bytes,
                 outcome, error_detail, idempotency_key)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ingest_id,
                self._adapter_id,
                received_at,
                raw_size_bytes,
                outcome.value,
                error_detail,
                idempotency_key,
            ],
        )
        return ingest_id

    def query(
        self,
        outcome: IngestOutcome | None = None,
        limit: int = 1000,
    ) -> list[dict]:
        """Return audit records as a list of dicts.

        Parameters
        ----------
        outcome:
            Filter to a specific outcome; ``None`` returns all rows.
        limit:
            Maximum rows to return.
        """
        if outcome is not None:
            rows = self._conn.execute(
                "SELECT * FROM ingest_events WHERE outcome = ? ORDER BY received_at DESC LIMIT ?",
                [outcome.value, limit],
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM ingest_events ORDER BY received_at DESC LIMIT ?",
                [limit],
            ).fetchall()
        cols = [
            "ingest_id",
            "adapter_id",
            "received_at",
            "raw_size_bytes",
            "outcome",
            "error_detail",
            "idempotency_key",
        ]
        return [dict(zip(cols, row, strict=True)) for row in rows]

    def close(self) -> None:
        """Close the underlying DuckDB connection."""
        self._conn.close()
