"""Unit tests for the Risk Engine — one test per rule, plus integration paths.

Coverage:
  Rule 1  — SESSION_OPEN
  Rule 2  — STALE_DATA
  Rule 3  — POSITION_LIMIT
  Rule 4  — GROSS_EXPOSURE
  Rule 5  — ORDER_NOTIONAL
  Rule 6  — ADV_PARTICIPATION
  Rule 7  — KILL_SWITCH
  Approval path
  Fail-fast (first failure terminates)
  Notional-to-qty conversion
  Determinism
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from alphafoundry.domain.risk import PositionLimit, RiskConfig
from alphafoundry.risk import KillSwitch, RiskContext, RiskEngine

from tests.risk.conftest import (
    T0,
    INST_ID,
    buy_order,
    closed_session,
    default_context,
    fresh_quote,
    halted_session,
    make_engine,
    open_session,
)


# ===========================================================================
# Approval path
# ===========================================================================


def test_approve_with_no_limits() -> None:
    """All rules pass when no limits are configured and session is open."""
    engine = make_engine()
    order = buy_order(qty=100)
    ctx = default_context()
    decision = engine.evaluate(order, ctx)

    assert decision.approved is True
    assert decision.violations == []
    assert decision.parent_order_id == order.parent_order_id
    assert decision.evaluated_at == T0


# ===========================================================================
# Rule 1 — SESSION_OPEN
# ===========================================================================


def test_rejects_closed_session() -> None:
    engine = make_engine()
    order = buy_order(qty=10)
    ctx = default_context(session=closed_session())
    decision = engine.evaluate(order, ctx)

    assert not decision.approved
    assert len(decision.violations) == 1
    assert decision.violations[0].rule == "SESSION_OPEN"
    assert decision.violations[0].unit == "session_status"


def test_rejects_halted_session() -> None:
    engine = make_engine()
    order = buy_order(qty=10)
    ctx = default_context(session=halted_session())
    decision = engine.evaluate(order, ctx)

    assert not decision.approved
    assert decision.violations[0].rule == "SESSION_OPEN"


def test_approves_open_session() -> None:
    engine = make_engine()
    order = buy_order(qty=10)
    ctx = default_context(session=open_session())
    assert engine.evaluate(order, ctx).approved is True


# ===========================================================================
# Rule 2 — STALE_DATA
# ===========================================================================


def test_rejects_stale_quote() -> None:
    """Quote older than max_quote_age_seconds must trigger STALE_DATA."""
    config = RiskConfig(max_quote_age_seconds=30.0)
    engine = make_engine(config=config)
    order = buy_order(qty=10)
    stale_quote = fresh_quote(age_seconds=31.0)
    ctx = default_context(quote=stale_quote)
    decision = engine.evaluate(order, ctx)

    assert not decision.approved
    v = decision.violations[0]
    assert v.rule == "STALE_DATA"
    assert v.measured_value > 30.0
    assert v.limit_value == 30.0
    assert v.unit == "seconds"


def test_approves_fresh_quote() -> None:
    config = RiskConfig(max_quote_age_seconds=60.0)
    engine = make_engine(config=config)
    order = buy_order(qty=10)
    ctx = default_context(quote=fresh_quote(age_seconds=5.0))
    assert engine.evaluate(order, ctx).approved is True


def test_quote_exactly_at_limit_is_approved() -> None:
    """A quote received exactly at the limit should pass (boundary inclusive)."""
    config = RiskConfig(max_quote_age_seconds=30.0)
    engine = make_engine(config=config)
    ctx = default_context(quote=fresh_quote(age_seconds=30.0))
    order = buy_order(qty=10)
    # age == limit means the condition `age > limit` is False → passes
    assert engine.evaluate(order, ctx).approved is True


# ===========================================================================
# Rule 3 — POSITION_LIMIT
# ===========================================================================


def test_rejects_when_net_position_limit_breached() -> None:
    limit = PositionLimit(instrument_id=INST_ID, max_net_qty=500)
    config = RiskConfig(position_limits=[limit])
    engine = make_engine(config=config)

    # Current position 450 + order 100 = 550 > 500
    order = buy_order(qty=100)
    ctx = default_context(current_position=450)
    decision = engine.evaluate(order, ctx)

    assert not decision.approved
    v = decision.violations[0]
    assert v.rule == "POSITION_LIMIT"
    assert v.measured_value == pytest.approx(550.0)
    assert v.limit_value == 500.0
    assert v.unit == "shares"


def test_approves_when_within_net_position_limit() -> None:
    limit = PositionLimit(instrument_id=INST_ID, max_net_qty=500)
    config = RiskConfig(position_limits=[limit])
    engine = make_engine(config=config)

    order = buy_order(qty=100)
    ctx = default_context(current_position=399)  # 399+100 = 499 < 500
    assert engine.evaluate(order, ctx).approved is True


def test_rejects_when_gross_qty_limit_breached() -> None:
    limit = PositionLimit(instrument_id=INST_ID, max_gross_qty=200)
    config = RiskConfig(position_limits=[limit])
    engine = make_engine(config=config)

    order = buy_order(qty=150)
    # abs(current=100) + 150 = 250 > 200
    ctx = default_context(current_position=100)
    decision = engine.evaluate(order, ctx)

    assert not decision.approved
    v = decision.violations[0]
    assert v.rule == "POSITION_LIMIT"
    assert v.unit == "shares"


def test_position_limit_ignores_different_instrument() -> None:
    """A limit on instrument X must not block an order on instrument Y."""
    from uuid import uuid4

    other_inst = uuid4()
    limit = PositionLimit(instrument_id=other_inst, max_net_qty=1)
    config = RiskConfig(position_limits=[limit])
    engine = make_engine(config=config)

    order = buy_order(qty=10_000)
    ctx = default_context()
    assert engine.evaluate(order, ctx).approved is True


def test_rejects_when_notional_position_limit_breached() -> None:
    limit = PositionLimit(
        instrument_id=INST_ID,
        max_gross_notional=Decimal("50_000"),
    )
    config = RiskConfig(position_limits=[limit])
    engine = make_engine(config=config)

    # arrival_price=1000, current=0, order qty=100 → notional 100_000 > 50_000
    order = buy_order(qty=100)
    ctx = default_context(arrival_price=Decimal("1000"))
    decision = engine.evaluate(order, ctx)

    assert not decision.approved
    assert decision.violations[0].unit == "INR"


# ===========================================================================
# Rule 4 — GROSS_EXPOSURE
# ===========================================================================


def test_rejects_when_portfolio_gross_exposure_breached() -> None:
    portfolio_limit = PositionLimit(
        instrument_id=None, max_gross_notional=Decimal("1_000_000")
    )
    config = RiskConfig(position_limits=[portfolio_limit])
    engine = make_engine(config=config)

    # Existing exposure 900_000 + new order 100 × 1000 = 1_000_000 — not exceeded
    order = buy_order(qty=100)
    ctx = default_context(
        portfolio_gross_exposure=Decimal("900_001"),
        arrival_price=Decimal("1000"),
    )
    decision = engine.evaluate(order, ctx)

    assert not decision.approved
    v = decision.violations[0]
    assert v.rule == "GROSS_EXPOSURE"
    assert v.unit == "INR"


def test_approves_when_portfolio_exposure_within_limit() -> None:
    portfolio_limit = PositionLimit(
        instrument_id=None, max_gross_notional=Decimal("1_000_000")
    )
    config = RiskConfig(position_limits=[portfolio_limit])
    engine = make_engine(config=config)

    order = buy_order(qty=50)  # 50 × 1000 = 50_000; total = 900_000 + 50_000 < 1_000_000
    ctx = default_context(
        portfolio_gross_exposure=Decimal("900_000"),
        arrival_price=Decimal("1000"),
    )
    assert engine.evaluate(order, ctx).approved is True


def test_no_portfolio_limit_configured_always_passes_rule4() -> None:
    config = RiskConfig()  # no portfolio PositionLimit
    engine = make_engine(config=config)
    order = buy_order(qty=1_000_000)
    ctx = default_context()
    # Rule 4 should pass; other rules may also pass since no limits set
    # (we only test rule 4 doesn't fire)
    decision = engine.evaluate(order, ctx)
    violations = [v for v in decision.violations if v.rule == "GROSS_EXPOSURE"]
    assert violations == []


# ===========================================================================
# Rule 5 — ORDER_NOTIONAL
# ===========================================================================


def test_rejects_when_single_order_notional_exceeded() -> None:
    config = RiskConfig(max_order_notional=Decimal("50_000"))
    engine = make_engine(config=config)

    order = buy_order(qty=100)  # 100 × 1000 = 100_000 > 50_000
    ctx = default_context(arrival_price=Decimal("1000"))
    decision = engine.evaluate(order, ctx)

    assert not decision.approved
    v = decision.violations[0]
    assert v.rule == "ORDER_NOTIONAL"
    assert v.measured_value == pytest.approx(100_000.0)
    assert v.limit_value == pytest.approx(50_000.0)
    assert v.unit == "INR"


def test_approves_when_order_notional_within_limit() -> None:
    config = RiskConfig(max_order_notional=Decimal("200_000"))
    engine = make_engine(config=config)

    order = buy_order(qty=100)  # 100 × 1000 = 100_000 < 200_000
    ctx = default_context(arrival_price=Decimal("1000"))
    assert engine.evaluate(order, ctx).approved is True


def test_no_notional_limit_always_passes_rule5() -> None:
    config = RiskConfig(max_order_notional=None)
    engine = make_engine(config=config)
    order = buy_order(qty=1_000_000)
    ctx = default_context()
    violations = [v for v in engine.evaluate(order, ctx).violations if v.rule == "ORDER_NOTIONAL"]
    assert violations == []


# ===========================================================================
# Rule 6 — ADV_PARTICIPATION
# ===========================================================================


def test_rejects_when_adv_participation_exceeded() -> None:
    config = RiskConfig(max_adv_participation=0.10)
    engine = make_engine(config=config)

    order = buy_order(qty=1_500)  # 1500 / 10_000 = 0.15 > 0.10
    ctx = default_context(adv=10_000)
    decision = engine.evaluate(order, ctx)

    assert not decision.approved
    v = decision.violations[0]
    assert v.rule == "ADV_PARTICIPATION"
    assert v.measured_value == pytest.approx(0.15, rel=1e-4)
    assert v.limit_value == pytest.approx(0.10)
    assert v.unit == "fraction_of_ADV"


def test_approves_when_adv_participation_within_limit() -> None:
    config = RiskConfig(max_adv_participation=0.10)
    engine = make_engine(config=config)

    order = buy_order(qty=500)  # 500 / 10_000 = 0.05 < 0.10
    ctx = default_context(adv=10_000)
    assert engine.evaluate(order, ctx).approved is True


def test_adv_zero_skips_participation_check() -> None:
    """If ADV is 0 or unknown, the participation rule is skipped."""
    config = RiskConfig(max_adv_participation=0.05)
    engine = make_engine(config=config)
    order = buy_order(qty=10_000)
    ctx = default_context(adv=0)
    violations = [v for v in engine.evaluate(order, ctx).violations if v.rule == "ADV_PARTICIPATION"]
    assert violations == []


# ===========================================================================
# Rule 7 — KILL_SWITCH
# ===========================================================================


def test_rejects_when_kill_switch_armed() -> None:
    ks = KillSwitch()
    ks.arm("emergency halt")
    engine = make_engine(kill_switch=ks)

    order = buy_order(qty=10)
    ctx = default_context()
    decision = engine.evaluate(order, ctx)

    assert not decision.approved
    v = decision.violations[0]
    assert v.rule == "KILL_SWITCH"
    assert v.measured_value == pytest.approx(1.0)  # 1 = armed
    assert v.limit_value == pytest.approx(0.0)     # 0 = required (disarmed)
    assert v.unit == "armed_flag"


def test_approves_after_kill_switch_disarmed() -> None:
    ks = KillSwitch()
    ks.arm("test arm")
    ks.disarm("test disarm")
    engine = make_engine(kill_switch=ks)

    order = buy_order(qty=10)
    ctx = default_context()
    assert engine.evaluate(order, ctx).approved is True


def test_kill_switch_blocks_all_subsequent_orders() -> None:
    ks = KillSwitch()
    engine = make_engine(kill_switch=ks)
    order = buy_order(qty=10)

    # Before arm: approved
    assert engine.evaluate(order, ctx=default_context()).approved is True

    ks.arm("triggered")

    # After arm: rejected
    assert engine.evaluate(order, ctx=default_context()).approved is False
    assert engine.evaluate(order, ctx=default_context()).approved is False


# ===========================================================================
# Fail-fast behaviour
# ===========================================================================


def test_only_first_violation_returned() -> None:
    """First failing rule terminates; only that one violation is recorded."""
    config = RiskConfig(
        max_order_notional=Decimal("10"),  # rule 5 — would fail
        max_adv_participation=0.001,       # rule 6 — would also fail
    )
    engine = make_engine(config=config)
    order = buy_order(qty=100)
    ctx = default_context()
    decision = engine.evaluate(order, ctx)

    assert not decision.approved
    assert len(decision.violations) == 1
    # Session is open, data is fresh, no position limits → first failure is rule 5
    assert decision.violations[0].rule == "ORDER_NOTIONAL"


def test_session_closed_terminates_before_stale_data() -> None:
    """Rule 1 fires before rule 2 even when data is also stale."""
    config = RiskConfig(max_quote_age_seconds=1.0)
    engine = make_engine(config=config)
    order = buy_order(qty=10)
    ctx = default_context(
        session=closed_session(),
        quote=fresh_quote(age_seconds=999.0),
    )
    decision = engine.evaluate(order, ctx)

    assert not decision.approved
    assert decision.violations[0].rule == "SESSION_OPEN"


# ===========================================================================
# Notional-to-qty conversion
# ===========================================================================


def test_notional_order_converts_to_qty_for_adv_check() -> None:
    """An order specified as target_notional must be converted for limit checks."""
    config = RiskConfig(max_adv_participation=0.10)
    engine = make_engine(config=config)

    # notional=50_000, price=1000 → effective_qty=50; ADV=100; 50/100 = 0.50 > 0.10
    order = buy_order(qty=None, notional=Decimal("50_000"))
    ctx = default_context(adv=100, arrival_price=Decimal("1000"))
    decision = engine.evaluate(order, ctx)

    assert not decision.approved
    assert decision.violations[0].rule == "ADV_PARTICIPATION"


def test_notional_order_converts_to_qty_for_order_notional_check() -> None:
    config = RiskConfig(max_order_notional=Decimal("5_000"))
    engine = make_engine(config=config)

    # notional=10_000, price=1000 → effective qty=10, notional=10×1000=10_000 > 5_000
    order = buy_order(qty=None, notional=Decimal("10_000"))
    ctx = default_context(arrival_price=Decimal("1000"))
    decision = engine.evaluate(order, ctx)

    assert not decision.approved
    assert decision.violations[0].rule == "ORDER_NOTIONAL"


# ===========================================================================
# Determinism
# ===========================================================================


def test_deterministic_same_inputs_same_decision() -> None:
    """Identical inputs must produce structurally identical decisions."""
    config = RiskConfig(max_order_notional=Decimal("50"))
    engine = make_engine(config=config)
    order = buy_order(qty=100)
    ctx = default_context()

    d1 = engine.evaluate(order, ctx)
    d2 = engine.evaluate(order, ctx)

    assert d1.approved == d2.approved
    assert len(d1.violations) == len(d2.violations)
    assert d1.violations[0].rule == d2.violations[0].rule
    assert d1.violations[0].measured_value == d2.violations[0].measured_value
    assert d1.evaluated_at == d2.evaluated_at  # deterministic clock injected


def test_deterministic_approved_path() -> None:
    engine = make_engine()
    order = buy_order(qty=10)
    ctx = default_context()

    d1 = engine.evaluate(order, ctx)
    d2 = engine.evaluate(order, ctx)

    assert d1.approved is True
    assert d2.approved is True
    assert d1.evaluated_at == d2.evaluated_at


# ===========================================================================
# RiskDecision fields
# ===========================================================================


def test_risk_decision_links_to_parent_order() -> None:
    engine = make_engine()
    order = buy_order(qty=10)
    ctx = default_context()
    decision = engine.evaluate(order, ctx)

    assert decision.parent_order_id == order.parent_order_id


def test_risk_decision_has_evaluation_timestamp() -> None:
    engine = make_engine()
    order = buy_order(qty=10)
    ctx = default_context()
    decision = engine.evaluate(order, ctx)

    assert decision.evaluated_at == T0  # from injected _now


def test_violation_records_measured_and_limit_values() -> None:
    config = RiskConfig(max_order_notional=Decimal("1_000"))
    engine = make_engine(config=config)

    order = buy_order(qty=5)  # 5 × 1000 = 5_000 > 1_000
    ctx = default_context(arrival_price=Decimal("1000"))
    decision = engine.evaluate(order, ctx)

    v = decision.violations[0]
    assert v.measured_value == pytest.approx(5_000.0)
    assert v.limit_value == pytest.approx(1_000.0)
    assert v.rule == "ORDER_NOTIONAL"
