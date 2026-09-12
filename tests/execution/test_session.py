"""Integration tests for Simulation Session Runner and Execution Engine (Phase 05)."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4
import pytest

from alphafoundry.domain.enums import (
    OrderStatus,
    OrderType,
    SessionStatus,
    SessionType,
    Side,
    SimulationSessionStatus,
)
from alphafoundry.domain.orders import ParentOrder
from alphafoundry.domain.risk import PositionLimit, RiskConfig
from alphafoundry.domain.sessions import Session
from alphafoundry.execution.session import ExecutionEngine
from alphafoundry.risk.engine import RiskEngine
from tests.execution.conftest import (
    INST_ID,
    SESSION_ID,
    T0,
    make_parent_order,
    make_quote,
    open_exchange_session,
)


class TestExecutionEngine:
    def _make_engine(
        self,
        risk_config: RiskConfig | None = None,
    ) -> ExecutionEngine:
        rcfg = risk_config or RiskConfig()
        risk_engine = RiskEngine(config=rcfg, now=lambda: T0)
        return ExecutionEngine(risk_engine=risk_engine, now=lambda: T0)

    def test_session_lifecycle(self) -> None:
        engine = self._make_engine()
        session = engine.start_session(name="test_sim_run")
        assert session.status == SimulationSessionStatus.RUNNING
        assert session.name == "test_sim_run"

        completed = engine.complete_session()
        assert completed.status == SimulationSessionStatus.COMPLETED

    def test_session_abort(self) -> None:
        engine = self._make_engine()
        engine.start_session(name="abort_test")
        aborted = engine.abort_session(reason="Risk limit breach")
        assert aborted.status == SimulationSessionStatus.ABORTED

    def test_execute_parent_order_end_to_end_approval(self) -> None:
        engine = self._make_engine()
        engine.start_session()
        parent = make_parent_order(qty=200, algo="TWAP", signal_id="sig-alpha-1")
        quote = make_quote(bid="999.00", ask="1001.00", bid_qty=500, ask_qty=500, ltp="1000.00")
        exch_session = open_exchange_session()

        res = engine.execute_parent_order(
            parent_order=parent,
            quote=quote,
            exchange_session=exch_session,
        )

        # 1. Verification of risk gate approval
        assert res.is_approved is True
        assert res.risk_decision.approved is True
        assert res.parent_order.status == OrderStatus.FILLED
        assert res.parent_order.risk_decision_id == res.risk_decision.risk_decision_id
        assert res.parent_order.signal_id == "sig-alpha-1"

        # 2. Verification of child slicing and fills
        assert len(res.child_orders) > 0
        assert sum(c.qty for c in res.child_orders) == 200
        assert res.total_filled_qty == 200
        assert len(res.fills) > 0
        for f in res.fills:
            assert f.fill_qty > 0
            assert f.fill_price > Decimal("0")

        # 3. Verification of position updates
        pos = engine.position_tracker.get_position(INST_ID)
        assert pos == 200

        # 4. Verification of TCA reports
        assert len(res.tca_reports) == 3  # ARRIVAL, VWAP, TWAP
        arrival_tca = next(r for r in res.tca_reports if r.benchmark_type.value == "ARRIVAL")
        assert arrival_tca.total_qty == 200
        assert arrival_tca.fill_count == len(res.fills)

    def test_execute_parent_order_rejection_at_risk_gate(self) -> None:
        # Configure strict position limit that rejects order of qty 500
        rcfg = RiskConfig(
            position_limits={
                INST_ID: PositionLimit(
                    instrument_id=INST_ID,
                    max_long_qty=100,
                    max_short_qty=100,
                    max_gross_qty=100,
                )
            }
        )
        engine = self._make_engine(risk_config=rcfg)
        engine.start_session()

        parent = make_parent_order(qty=500, algo="MARKET")
        quote = make_quote()
        exch_session = open_exchange_session()

        res = engine.execute_parent_order(
            parent_order=parent,
            quote=quote,
            exchange_session=exch_session,
        )

        assert res.is_approved is False
        assert res.parent_order.status == OrderStatus.REJECTED
        assert res.parent_order.risk_decision_id is not None
        assert len(res.child_orders) == 0
        assert len(res.fills) == 0
        assert engine.position_tracker.get_position(INST_ID) == 0

    def test_cancel_parent_order(self) -> None:
        engine = self._make_engine()
        parent = make_parent_order(qty=100)
        quote = make_quote()
        exch_session = open_exchange_session()

        res = engine.execute_parent_order(
            parent_order=parent,
            quote=quote,
            exchange_session=exch_session,
        )
        # Already filled cannot be cancelled
        assert engine.cancel_parent_order(parent.parent_order_id).status == OrderStatus.FILLED
