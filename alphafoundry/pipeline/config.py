"""Pipeline configuration."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PipelineConfig:
    """Configuration for the data pipeline.

    Attributes
    ----------
    db_path:
        DuckDB database file path.  Use ``:memory:`` for in-process tests.
    staleness_seconds:
        Events whose ``timestamp`` pre-dates ``received_at`` by more than this
        threshold are marked / rejected as stale.
    future_gate_seconds:
        Events whose ``timestamp`` exceeds ``received_at`` by more than this
        tolerance are rejected (clock-skew allowance = 5 s per data-model spec).
    past_gate_seconds:
        Events more than this many seconds before the estimated session open
        are rejected.
    session_open_utc_hour:
        UTC hour of NSE Normal session open (03:45 UTC = 09:15 IST).
    session_open_utc_minute:
        UTC minute of NSE Normal session open.
    max_price_inr:
        Upper bound for price sanity check (INR).
    adapter_id:
        Label recorded in the audit log for every event from this adapter.
    """

    db_path: str = ":memory:"
    staleness_seconds: float = 60.0
    future_gate_seconds: float = 5.0
    past_gate_seconds: float = 300.0  # 5 minutes
    session_open_utc_hour: int = 3
    session_open_utc_minute: int = 45
    max_price_inr: float = 1_000_000.0
    adapter_id: str = "synthetic"
    # Extra fields reserved for later phases
    extra: dict[str, object] = field(default_factory=dict)
