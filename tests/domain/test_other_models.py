"""Tests for orders, risk, TCA, and research domain models."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from alphafoundry.domain import (
    AnomalyReport,
    ChildOrder,
    Explanation,
    FeatureLineageItem,
    FeatureVector,
    Fill,
    InstrumentRank,
    ParentOrder,
    PositionLimit,
    RiskConfig,
    RiskDecision,
    RuleViolation,
    SessionSummary,
    Signal,
    TCAReport,
)
from alphafoundry.domain.enums import (
    BenchmarkType,
    Direction,
    OrderStatus,
    OrderType,
    Side,
    Urgency,
)


def _utc(
    year: int, month: int, day: int, hour: int = 0, minute: int = 0, second: int = 0
) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=UTC)


_IID = uuid.uuid4()
_SID = uuid.uuid4()


# ---------------------------------------------------------------------------
# Orders & Fills
# ---------------------------------------------------------------------------


class TestOrders:
    def test_parent_order(self):
        po = ParentOrder(
            session_id=_SID,
            instrument_id=_IID,
            side=Side.BUY,
            target_qty=1000,
            algo="TWAP",
            urgency=Urgency.MEDIUM,
            created_at=_utc(2024, 1, 2, 9, 15),
            updated_at=_utc(2024, 1, 2, 9, 15),
        )
        assert po.status == OrderStatus.PENDING_RISK
        assert po.target_qty == 1000

    def test_child_order(self):
        po_id = uuid.uuid4()
        co = ChildOrder(
            parent_order_id=po_id,
            sequence_num=0,
            instrument_id=_IID,
            side=Side.BUY,
            qty=100,
            order_type=OrderType.LIMIT,
            limit_price=Decimal("150.00"),
            created_at=_utc(2024, 1, 2, 9, 16),
        )
        assert co.status == OrderStatus.PENDING
        assert co.qty == 100

    def test_fill(self):
        co_id = uuid.uuid4()
        f = Fill(
            child_order_id=co_id,
            fill_qty=100,
            fill_price=Decimal("150.05"),
            simulated_impact=Decimal("0.02"),
            fill_timestamp=_utc(2024, 1, 2, 9, 16, 5),
            rng_seed=42,
        )
        assert f.fill_qty == 100
        assert f.fill_price == Decimal("150.05")
        assert f.rng_seed == 42


# ---------------------------------------------------------------------------
# Risk
# ---------------------------------------------------------------------------


class TestRisk:
    def test_risk_config_and_decision(self):
        cfg = RiskConfig(
            position_limits=[
                PositionLimit(max_gross_qty=10000, max_net_qty=5000, max_gross_notional=1000000.0)
            ],
            max_order_qty=500,
            max_order_notional=50000.0,
        )
        assert len(cfg.position_limits) == 1
        assert cfg.kill_switch_enabled is False

        dec = RiskDecision(
            parent_order_id=uuid.uuid4(),
            approved=False,
            violations=[
                RuleViolation(
                    rule="max_order_qty",
                    measured_value=600.0,
                    limit_value=500.0,
                    unit="shares",
                )
            ],
            evaluated_at=_utc(2024, 1, 2, 9, 15),
        )
        assert dec.approved is False
        assert len(dec.violations) == 1


# ---------------------------------------------------------------------------
# TCA
# ---------------------------------------------------------------------------


class TestTCA:
    def test_tca_report(self):
        tca = TCAReport(
            parent_order_id=uuid.uuid4(),
            benchmark_type=BenchmarkType.ARRIVAL,
            benchmark_price=Decimal("100.00"),
            execution_price=Decimal("100.10"),
            realized_slippage=Decimal("0.10"),
            spread_cost=Decimal("0.05"),
            impact_cost=Decimal("0.03"),
            timing_cost=Decimal("0.02"),
            implementation_shortfall=Decimal("0.10"),
            total_qty=1000,
            fill_count=5,
            execution_duration_seconds=300.0,
            computed_at=_utc(2024, 1, 2, 9, 20),
        )
        assert tca.total_qty == 1000
        assert tca.realized_slippage == Decimal("0.10")


# ---------------------------------------------------------------------------
# Research & AI Objects
# ---------------------------------------------------------------------------


class TestResearchAndAI:
    def test_feature_vector_and_signal(self):
        fv = FeatureVector(
            instrument_id=_IID,
            as_of=_utc(2024, 1, 2, 9, 15),
            computed_at=_utc(2024, 1, 2, 9, 15),
            feature_version="v1.0",
            features={"rsi_14": 65.5, "macd_hist": 0.12},
        )
        assert fv.features["rsi_14"] == 65.5

        sig = Signal(
            instrument_id=_IID,
            as_of=_utc(2024, 1, 2, 9, 15),
            emitted_at=_utc(2024, 1, 2, 9, 15),
            direction=Direction.LONG,
            score=0.75,
            confidence=0.85,
            lineage=[
                FeatureLineageItem(feature_name="rsi_14", weight=0.6, value=65.5),
                FeatureLineageItem(feature_name="macd_hist", weight=0.4, value=0.12),
            ],
            signal_version="v1.0",
        )
        assert sig.direction == Direction.LONG
        assert len(sig.lineage) == 2

    def test_instrument_rank(self):
        r = InstrumentRank(
            instrument_id=_IID,
            universe_id="NSE_NIFTY50",
            as_of=_utc(2024, 1, 2, 9, 15),
            rank=1,
            score=0.92,
        )
        assert r.rank == 1

    def test_explanation_and_session_summary(self):
        exp = Explanation(
            subject_type="SIGNAL",
            subject_id=_IID,
            narrative="Momentum breakdown observed.",
            model_version="claude-3-5-sonnet",
            input_refs=[_IID],
            generated_at=_utc(2024, 1, 2, 9, 15),
        )
        assert exp.narrative == "Momentum breakdown observed."

        ss = SessionSummary(
            session_id=_SID,
            narrative="Session completed normally.",
            model_version="claude-3-5-sonnet",
            generated_at=_utc(2024, 1, 2, 15, 30),
        )
        assert ss.narrative == "Session completed normally."

    def test_anomaly_report_severity_validator(self):
        ar = AnomalyReport(
            severity="WARN",
            description="High quote staleness observed",
            context_refs=[_IID],
            model_version="claude-3-5-sonnet",
            generated_at=_utc(2024, 1, 2, 9, 15),
        )
        assert ar.severity == "WARN"

        with pytest.raises(ValidationError):
            AnomalyReport(
                severity="CRITICAL",  # invalid; only INFO, WARN, ALERT allowed
                description="Invalid severity test",
                context_refs=[],
                model_version="test",
                generated_at=_utc(2024, 1, 2, 9, 15),
            )
