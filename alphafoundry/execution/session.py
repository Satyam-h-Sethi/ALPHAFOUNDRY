"""Simulation Session Runner and Execution Engine.

Orchestrates the entire paper execution lifecycle per execution-model.md:
  ParentOrder (PENDING_RISK)
      ↓
  RiskEngine evaluation (APPROVED / REJECTED)
      ↓
  Order Slicer → ChildOrder[1..N]
      ↓
  Fill Simulator → Fill[1..M]
      ↓
  Position Tracker (updates signed inventory)
      ↓
  TCA Engine → TCAReport
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Callable, Sequence
from uuid import UUID, uuid4

from alphafoundry.domain.enums import (
    BenchmarkType,
    OrderStatus,
    Side,
    SimulationSessionStatus,
)
from alphafoundry.domain.market_data import Quote
from alphafoundry.domain.orders import ChildOrder, Fill, ParentOrder
from alphafoundry.domain.risk import RiskDecision
from alphafoundry.domain.sessions import Session, SimulationSession
from alphafoundry.domain.tca import TCAReport
from alphafoundry.execution.config import ExecutionConfig
from alphafoundry.execution.fill_simulator import FillSimulator, MarketState
from alphafoundry.execution.position_tracker import PositionTracker
from alphafoundry.execution.slicer import OrderSlicer
from alphafoundry.risk.engine import RiskContext, RiskEngine
from alphafoundry.tca.engine import TCAEngine

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """Consolidated result of executing a single ParentOrder through the lifecycle."""

    parent_order: ParentOrder
    risk_decision: RiskDecision
    child_orders: list[ChildOrder] = field(default_factory=list)
    fills: list[Fill] = field(default_factory=list)
    tca_reports: list[TCAReport] = field(default_factory=list)

    @property
    def is_approved(self) -> bool:
        return self.risk_decision.approved

    @property
    def total_filled_qty(self) -> int:
        return sum(f.fill_qty for f in self.fills)


class ExecutionEngine:
    """Core simulation orchestrator managing risk, slicing, fills, positions, and TCA."""

    def __init__(
        self,
        risk_engine: RiskEngine,
        config: ExecutionConfig | None = None,
        slicer: OrderSlicer | None = None,
        fill_simulator: FillSimulator | None = None,
        position_tracker: PositionTracker | None = None,
        tca_engine: TCAEngine | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.risk_engine = risk_engine
        self.config = config or ExecutionConfig()
        self.slicer = slicer or OrderSlicer(config=self.config.slicer)
        self.fill_simulator = fill_simulator or FillSimulator(
            config=self.config, rng_seed=self.config.default_rng_seed
        )
        self.position_tracker = position_tracker or PositionTracker()
        self.tca_engine = tca_engine or TCAEngine()
        self._now_fn = now

        # Active session state
        self._current_session: SimulationSession | None = None
        self._parent_orders: dict[UUID, ParentOrder] = {}
        self._child_orders: dict[UUID, list[ChildOrder]] = {}
        self._fills: dict[UUID, list[Fill]] = {}
        self._tca_reports: dict[UUID, list[TCAReport]] = {}
        self._risk_decisions: dict[UUID, RiskDecision] = {}

    def _now(self) -> datetime:
        if self._now_fn is not None:
            return self._now_fn()
        return datetime.now(UTC)

    def start_session(
        self,
        name: str = "simulation_session",
        window_start: datetime | None = None,
        window_end: datetime | None = None,
        adapter_id: str = "synthetic",
        universe_id: str = "NSE_NIFTY50",
        algo_config: dict[str, object] | None = None,
    ) -> SimulationSession:
        """Create and start a new SimulationSession."""
        now = self._now()
        start = window_start or now
        end = window_end or (start.replace(hour=23, minute=59, second=59))

        session = SimulationSession(
            simulation_session_id=uuid4(),
            name=name,
            window_start=start,
            window_end=end,
            adapter_id=adapter_id,
            universe_id=universe_id,
            algo_config=algo_config or {},
            status=SimulationSessionStatus.RUNNING,
            created_at=now,
            updated_at=now,
        )
        self._current_session = session
        return session

    def abort_session(self, reason: str = "") -> SimulationSession:
        """Abort current simulation session."""
        if self._current_session is None:
            raise RuntimeError("No active simulation session to abort")
        now = self._now()
        aborted = SimulationSession(
            simulation_session_id=self._current_session.simulation_session_id,
            name=self._current_session.name,
            window_start=self._current_session.window_start,
            window_end=self._current_session.window_end,
            adapter_id=self._current_session.adapter_id,
            universe_id=self._current_session.universe_id,
            algo_config=self._current_session.algo_config,
            status=SimulationSessionStatus.ABORTED,
            created_at=self._current_session.created_at,
            updated_at=now,
        )
        self._current_session = aborted
        logger.warning("Simulation session %s aborted: %s", aborted.simulation_session_id, reason)
        return aborted

    def complete_session(self) -> SimulationSession:
        """Mark current simulation session as completed."""
        if self._current_session is None:
            raise RuntimeError("No active simulation session to complete")
        now = self._now()
        completed = SimulationSession(
            simulation_session_id=self._current_session.simulation_session_id,
            name=self._current_session.name,
            window_start=self._current_session.window_start,
            window_end=self._current_session.window_end,
            adapter_id=self._current_session.adapter_id,
            universe_id=self._current_session.universe_id,
            algo_config=self._current_session.algo_config,
            status=SimulationSessionStatus.COMPLETED,
            created_at=self._current_session.created_at,
            updated_at=now,
        )
        self._current_session = completed
        return completed

    def execute_parent_order(
        self,
        parent_order: ParentOrder,
        quote: Quote,
        exchange_session: Session,
        adv: int = 100_000,
        sigma: float = 0.02,
        market_quotes: Sequence[Quote] | None = None,
        volume_profile: Sequence[int] | None = None,
        observed_volumes: Sequence[int] | None = None,
    ) -> ExecutionResult:
        """Execute a ParentOrder through the full lifecycle:

        1. Synchronous Risk Engine Evaluation
        2. Status Transition -> APPROVED / ACTIVE (or REJECTED)
        3. Order Slicing into Child Orders
        4. Fill Simulation against Quote(s)
        5. Position & Exposure Updates
        6. Parent Order Status update (FILLED / PARTIALLY_FILLED)
        7. TCA Computation
        """
        now = self._now()
        arrival_price = quote.last_trade_price or quote.bid_price

        # 1. Prepare Risk Context with current positions & exposures
        current_pos = self.position_tracker.get_position(parent_order.instrument_id)
        gross_exposure = self.position_tracker.get_portfolio_gross_exposure(
            {parent_order.instrument_id: arrival_price}
        )
        risk_ctx = RiskContext(
            session=exchange_session,
            quote=quote,
            current_position=current_pos,
            portfolio_gross_exposure=gross_exposure,
            adv=adv,
            arrival_price=arrival_price,
        )

        # 2. Risk Gate Evaluation
        risk_decision = self.risk_engine.evaluate(parent_order, risk_ctx)
        self._risk_decisions[parent_order.parent_order_id] = risk_decision

        if not risk_decision.approved:
            # Reject parent order
            rejected_order = ParentOrder(
                parent_order_id=parent_order.parent_order_id,
                session_id=parent_order.session_id,
                instrument_id=parent_order.instrument_id,
                signal_id=parent_order.signal_id,
                side=parent_order.side,
                target_qty=parent_order.target_qty,
                target_notional=parent_order.target_notional,
                algo=parent_order.algo,
                urgency=parent_order.urgency,
                price_limit=parent_order.price_limit,
                status=OrderStatus.REJECTED,
                risk_decision_id=risk_decision.risk_decision_id,
                created_at=parent_order.created_at,
                updated_at=now,
            )
            self._parent_orders[parent_order.parent_order_id] = rejected_order
            return ExecutionResult(
                parent_order=rejected_order,
                risk_decision=risk_decision,
            )

        # Approved: update status to APPROVED / ACTIVE
        active_order = ParentOrder(
            parent_order_id=parent_order.parent_order_id,
            session_id=parent_order.session_id,
            instrument_id=parent_order.instrument_id,
            signal_id=parent_order.signal_id,
            side=parent_order.side,
            target_qty=parent_order.target_qty,
            target_notional=parent_order.target_notional,
            algo=parent_order.algo,
            urgency=parent_order.urgency,
            price_limit=parent_order.price_limit,
            status=OrderStatus.ACTIVE,
            risk_decision_id=risk_decision.risk_decision_id,
            created_at=parent_order.created_at,
            updated_at=now,
        )
        self._parent_orders[parent_order.parent_order_id] = active_order

        # 3. Order Slicing
        child_orders = self.slicer.slice_order(
            active_order,
            arrival_price=arrival_price,
            volume_profile=volume_profile,
            observed_volumes=observed_volumes,
            start_time=quote.timestamp,
        )
        self._child_orders[parent_order.parent_order_id] = list(child_orders)

        # 4. Fill Simulation
        # If a sequence of quotes is given, match children against quotes; else match against base quote
        quote_seq = list(market_quotes) if market_quotes else [quote]
        fills: list[Fill] = []
        half_spreads: list[Decimal] = []

        pending_queue = list(child_orders)
        quote_idx = 0

        while pending_queue:
            child = pending_queue.pop(0)
            current_q = quote_seq[min(quote_idx, len(quote_seq) - 1)]
            mkt_state = MarketState.from_quote(current_q, adv=adv, sigma=sigma)

            fill_result = self.fill_simulator.simulate_fill(
                child, mkt_state, arrival_price=arrival_price
            )

            if fill_result.fill is not None:
                fills.append(fill_result.fill)
                half_spreads.append(fill_result.half_spread)

                # 5. Update position tracker
                self.position_tracker.record_fill(
                    fill_result.fill,
                    active_order.side,
                    active_order.instrument_id,
                )

            # Re-queue residual if any
            if fill_result.residual_child is not None:
                pending_queue.append(fill_result.residual_child)

            if quote_idx < len(quote_seq) - 1:
                quote_idx += 1

        self._fills[parent_order.parent_order_id] = fills

        # 6. Finalize Parent Order Status
        total_filled = sum(f.fill_qty for f in fills)
        target_qty = self.slicer._resolve_target_qty(active_order, arrival_price)
        final_status = (
            OrderStatus.FILLED
            if total_filled >= target_qty
            else (OrderStatus.PARTIALLY_FILLED if total_filled > 0 else OrderStatus.CANCELLED)
        )

        final_parent_order = ParentOrder(
            parent_order_id=active_order.parent_order_id,
            session_id=active_order.session_id,
            instrument_id=active_order.instrument_id,
            signal_id=active_order.signal_id,
            side=active_order.side,
            target_qty=active_order.target_qty,
            target_notional=active_order.target_notional,
            algo=active_order.algo,
            urgency=active_order.urgency,
            price_limit=active_order.price_limit,
            status=final_status,
            risk_decision_id=active_order.risk_decision_id,
            created_at=active_order.created_at,
            updated_at=self._now(),
        )
        self._parent_orders[parent_order.parent_order_id] = final_parent_order

        # 7. TCA Computation for standard benchmarks
        tca_reports: list[TCAReport] = []
        for btype in [BenchmarkType.ARRIVAL, BenchmarkType.VWAP, BenchmarkType.TWAP]:
            report = self.tca_engine.compute_report(
                parent_order=final_parent_order,
                fills=fills,
                benchmark_type=btype,
                benchmark_price=arrival_price,
                arrival_price=arrival_price,
                half_spreads=half_spreads,
                computed_at=self._now(),
            )
            tca_reports.append(report)

        self._tca_reports[parent_order.parent_order_id] = tca_reports

        return ExecutionResult(
            parent_order=final_parent_order,
            risk_decision=risk_decision,
            child_orders=child_orders,
            fills=fills,
            tca_reports=tca_reports,
        )

    def cancel_parent_order(self, parent_order_id: UUID) -> ParentOrder:
        """Cancel an active or pending ParentOrder."""
        order = self._parent_orders.get(parent_order_id)
        if order is None:
            raise KeyError(f"ParentOrder {parent_order_id} not found")

        if order.status in (OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED):
            return order

        cancelled_order = ParentOrder(
            parent_order_id=order.parent_order_id,
            session_id=order.session_id,
            instrument_id=order.instrument_id,
            signal_id=order.signal_id,
            side=order.side,
            target_qty=order.target_qty,
            target_notional=order.target_notional,
            algo=order.algo,
            urgency=order.urgency,
            price_limit=order.price_limit,
            status=OrderStatus.CANCELLED,
            risk_decision_id=order.risk_decision_id,
            created_at=order.created_at,
            updated_at=self._now(),
        )
        self._parent_orders[parent_order_id] = cancelled_order
        return cancelled_order
