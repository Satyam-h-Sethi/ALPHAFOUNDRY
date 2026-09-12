"""Pre-trade Risk Engine — Phase 04.

Implements all seven rules from execution-model.md §9 in the prescribed order.
Rules are evaluated sequentially; the first failure terminates evaluation and
produces a REJECTED RiskDecision.  Approved orders produce a RiskDecision with
``approved = True`` and an empty violations list.

Determinism guarantee
---------------------
Given identical (order, quote, positions, adv, session, config, kill_switch),
``evaluate()`` returns a structurally identical RiskDecision every time.  The
only non-deterministic field is ``evaluated_at``, which callers may override
in tests by injecting a fixed ``now`` callable.

Phase 05 interface
------------------
Phase 05 should call::

    decision = engine.evaluate(order, context)
    if not decision.approved:
        # update order status to REJECTED, store decision, stop
        ...
    # update order status to APPROVED, store decision, proceed to slicing
    ...
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Callable
from uuid import UUID

from alphafoundry.domain.enums import SessionStatus
from alphafoundry.domain.market_data import Quote
from alphafoundry.domain.orders import ParentOrder
from alphafoundry.domain.risk import RiskConfig, RiskDecision, RuleViolation
from alphafoundry.domain.sessions import Session
from alphafoundry.risk.kill_switch import KillSwitch

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Context object passed into evaluate()
# ---------------------------------------------------------------------------


class RiskContext:
    """All external state required by the risk rules.

    This is a plain data container — no business logic lives here.  Phase 05
    constructs one and passes it to :meth:`RiskEngine.evaluate`.

    Attributes:
        session: The trading session the order targets.
        quote: Most recent Level-1 quote for the order's instrument.
        current_position: Signed net position currently held in the instrument
            (positive = long, negative = short).  Pass 0 if no position exists.
        portfolio_gross_exposure: Sum of absolute notional values across all
            current positions in INR.  Pass Decimal("0") if portfolio is flat.
        adv: Average daily volume (in shares) for the instrument over the
            trailing window used for ADV participation checks.
        arrival_price: Price used to convert target_notional orders to
            an effective quantity for notional and ADV limit checks.
            Typically the mid-price at order creation time.
        instrument_positions: All per-instrument signed positions keyed by
            UUID.  Used to compute gross exposure from individual price
            snapshots when portfolio_gross_exposure is not aggregated upstream.
            Optional — ``portfolio_gross_exposure`` is used directly if provided.
    """

    def __init__(
        self,
        *,
        session: Session,
        quote: Quote,
        current_position: int,
        portfolio_gross_exposure: Decimal,
        adv: int,
        arrival_price: Decimal,
    ) -> None:
        self.session = session
        self.quote = quote
        self.current_position = current_position
        self.portfolio_gross_exposure = portfolio_gross_exposure
        self.adv = adv
        self.arrival_price = arrival_price


# ---------------------------------------------------------------------------
# Risk Engine
# ---------------------------------------------------------------------------

_RULE_ORDER = [
    "SESSION_OPEN",
    "STALE_DATA",
    "POSITION_LIMIT",
    "GROSS_EXPOSURE",
    "ORDER_NOTIONAL",
    "ADV_PARTICIPATION",
    "KILL_SWITCH",
]


class RiskEngine:
    """Evaluates all pre-trade risk rules synchronously.

    Args:
        config: Frozen :class:`~alphafoundry.domain.risk.RiskConfig` describing
            all limits.  Injected at construction so the engine is stateless
            between calls (except for sharing a KillSwitch instance).
        kill_switch: Shared :class:`~alphafoundry.risk.kill_switch.KillSwitch`
            instance.  Defaults to a fresh, disarmed switch if not provided.
        now: Callable returning the current UTC datetime used to stamp
            ``evaluated_at``.  Override in tests for determinism.
    """

    def __init__(
        self,
        config: RiskConfig,
        kill_switch: KillSwitch | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._config = config
        self._kill_switch = kill_switch or KillSwitch()
        self._now: Callable[[], datetime] = now or (lambda: datetime.now(UTC))

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @property
    def config(self) -> RiskConfig:
        return self._config

    @property
    def kill_switch(self) -> KillSwitch:
        return self._kill_switch

    def evaluate(self, order: ParentOrder, context: RiskContext) -> RiskDecision:
        """Run all seven risk rules and return a RiskDecision.

        Rules are evaluated in the order mandated by execution-model.md §9.
        First failure terminates evaluation immediately (fail-fast).

        Args:
            order: The :class:`~alphafoundry.domain.orders.ParentOrder` in
                ``PENDING_RISK`` state requesting approval.
            context: Runtime market state and position data.

        Returns:
            A frozen :class:`~alphafoundry.domain.risk.RiskDecision`.
        """
        now = self._now()
        violation = self._run_rules(order, context)

        decision = RiskDecision(
            parent_order_id=order.parent_order_id,
            approved=(violation is None),
            violations=[violation] if violation is not None else [],
            evaluated_at=now,
        )

        _log.info(
            "risk decision parent_order_id=%s approved=%s rule=%s",
            order.parent_order_id,
            decision.approved,
            violation.rule if violation else "—",
        )
        return decision

    # ------------------------------------------------------------------
    # Rule dispatch
    # ------------------------------------------------------------------

    def _run_rules(
        self, order: ParentOrder, ctx: RiskContext
    ) -> RuleViolation | None:
        """Return the first violated rule, or None if all rules pass."""
        rules = [
            self._rule_session_open,
            self._rule_stale_data,
            self._rule_position_limit,
            self._rule_gross_exposure,
            self._rule_order_notional,
            self._rule_adv_participation,
            self._rule_kill_switch,
        ]
        for rule_fn in rules:
            violation = rule_fn(order, ctx)
            if violation is not None:
                return violation
        return None

    # ------------------------------------------------------------------
    # Rule 1 — Session open / tradable check
    # ------------------------------------------------------------------

    def _rule_session_open(
        self, order: ParentOrder, ctx: RiskContext
    ) -> RuleViolation | None:
        """Reject if the session is not OPEN."""
        status = ctx.session.status
        if status != SessionStatus.OPEN:
            return RuleViolation(
                rule="SESSION_OPEN",
                measured_value=0.0,  # 0 = not open, 1 would be open
                limit_value=1.0,
                unit="session_status",
            )
        return None

    # ------------------------------------------------------------------
    # Rule 2 — Stale data check
    # ------------------------------------------------------------------

    def _rule_stale_data(
        self, order: ParentOrder, ctx: RiskContext
    ) -> RuleViolation | None:
        """Reject if the most recent quote is older than max_quote_age_seconds."""
        now = self._now()
        age_seconds = (now - ctx.quote.received_at).total_seconds()
        limit = self._config.max_quote_age_seconds
        if age_seconds > limit:
            return RuleViolation(
                rule="STALE_DATA",
                measured_value=round(age_seconds, 3),
                limit_value=limit,
                unit="seconds",
            )
        return None

    # ------------------------------------------------------------------
    # Rule 3 — Instrument-level position limit
    # ------------------------------------------------------------------

    def _rule_position_limit(
        self, order: ParentOrder, ctx: RiskContext
    ) -> RuleViolation | None:
        """Reject if adding the order would breach any per-instrument position limit."""
        effective_qty = self._effective_qty(order, ctx)
        post_trade_net = ctx.current_position + effective_qty

        for limit in self._config.position_limits:
            if limit.instrument_id is not None and limit.instrument_id != order.instrument_id:
                continue
            if limit.instrument_id is None:
                # Portfolio-level limit — handled in rule 4; skip here.
                continue

            if limit.max_net_qty is not None and abs(post_trade_net) > limit.max_net_qty:
                return RuleViolation(
                    rule="POSITION_LIMIT",
                    measured_value=float(abs(post_trade_net)),
                    limit_value=float(limit.max_net_qty),
                    unit="shares",
                )

            gross_after = abs(ctx.current_position) + effective_qty
            if limit.max_gross_qty is not None and gross_after > limit.max_gross_qty:
                return RuleViolation(
                    rule="POSITION_LIMIT",
                    measured_value=float(gross_after),
                    limit_value=float(limit.max_gross_qty),
                    unit="shares",
                )

            if limit.max_gross_notional is not None:
                notional_after = Decimal(gross_after) * ctx.arrival_price
                if notional_after > limit.max_gross_notional:
                    return RuleViolation(
                        rule="POSITION_LIMIT",
                        measured_value=float(notional_after),
                        limit_value=float(limit.max_gross_notional),
                        unit="INR",
                    )
        return None

    # ------------------------------------------------------------------
    # Rule 4 — Portfolio gross exposure limit
    # ------------------------------------------------------------------

    def _rule_gross_exposure(
        self, order: ParentOrder, ctx: RiskContext
    ) -> RuleViolation | None:
        """Reject if the portfolio-level gross exposure limit would be breached.

        A portfolio-level PositionLimit with ``instrument_id = None`` and
        ``max_gross_notional`` set is checked here.  If no such limit is
        configured this rule always passes.
        """
        portfolio_limit: Decimal | None = None
        for lim in self._config.position_limits:
            if lim.instrument_id is None and lim.max_gross_notional is not None:
                portfolio_limit = lim.max_gross_notional
                break

        if portfolio_limit is None:
            return None

        effective_qty = self._effective_qty(order, ctx)
        order_notional = Decimal(effective_qty) * ctx.arrival_price
        new_exposure = ctx.portfolio_gross_exposure + order_notional

        if new_exposure > portfolio_limit:
            return RuleViolation(
                rule="GROSS_EXPOSURE",
                measured_value=float(new_exposure),
                limit_value=float(portfolio_limit),
                unit="INR",
            )
        return None

    # ------------------------------------------------------------------
    # Rule 5 — Single-order notional limit
    # ------------------------------------------------------------------

    def _rule_order_notional(
        self, order: ParentOrder, ctx: RiskContext
    ) -> RuleViolation | None:
        """Reject if this single order's notional exceeds max_order_notional."""
        if self._config.max_order_notional is None:
            return None

        effective_qty = self._effective_qty(order, ctx)
        notional = Decimal(effective_qty) * ctx.arrival_price
        limit = self._config.max_order_notional

        if notional > limit:
            return RuleViolation(
                rule="ORDER_NOTIONAL",
                measured_value=float(notional),
                limit_value=float(limit),
                unit="INR",
            )
        return None

    # ------------------------------------------------------------------
    # Rule 6 — ADV participation limit
    # ------------------------------------------------------------------

    def _rule_adv_participation(
        self, order: ParentOrder, ctx: RiskContext
    ) -> RuleViolation | None:
        """Reject if the order quantity would exceed max_adv_participation × ADV."""
        if ctx.adv <= 0:
            # Cannot check participation without a valid ADV; treat as pass.
            return None

        effective_qty = self._effective_qty(order, ctx)
        participation = effective_qty / ctx.adv
        limit = self._config.max_adv_participation

        if participation > limit:
            return RuleViolation(
                rule="ADV_PARTICIPATION",
                measured_value=round(participation, 6),
                limit_value=limit,
                unit="fraction_of_ADV",
            )
        return None

    # ------------------------------------------------------------------
    # Rule 7 — Kill switch
    # ------------------------------------------------------------------

    def _rule_kill_switch(
        self, order: ParentOrder, ctx: RiskContext
    ) -> RuleViolation | None:
        """Reject if the kill switch is armed."""
        if self._kill_switch.is_armed:
            return RuleViolation(
                rule="KILL_SWITCH",
                measured_value=1.0,  # 1 = armed
                limit_value=0.0,    # 0 = disarmed (required)
                unit="armed_flag",
            )
        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _effective_qty(self, order: ParentOrder, ctx: RiskContext) -> int:
        """Resolve the effective integer quantity for limit checks.

        If the order specifies ``target_qty``, that value is used directly.
        If only ``target_notional`` is given, the quantity is derived by
        dividing by ``arrival_price`` and rounding down to a whole share.
        """
        if order.target_qty is not None:
            return order.target_qty

        if order.target_notional is not None and ctx.arrival_price > Decimal("0"):
            return int(order.target_notional / ctx.arrival_price)

        return 0
