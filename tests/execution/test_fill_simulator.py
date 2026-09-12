"""Unit tests for Fill Simulator and Market Impact (Phase 05)."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4
import pytest

from alphafoundry.domain.enums import OrderStatus, OrderType, Side
from alphafoundry.domain.orders import ChildOrder
from alphafoundry.execution.config import ExecutionConfig, ImpactConfig
from alphafoundry.execution.fill_simulator import FillSimulator, MarketState
from tests.execution.conftest import INST_ID, SESSION_ID, T0, make_quote


class TestFillSimulator:
    def _make_child(
        self,
        side: Side = Side.BUY,
        qty: int = 100,
        order_type: OrderType = OrderType.MARKET,
        limit_price: Decimal | None = None,
    ) -> ChildOrder:
        return ChildOrder(
            parent_order_id=uuid4(),
            sequence_num=0,
            instrument_id=INST_ID,
            side=side,
            qty=qty,
            limit_price=limit_price,
            order_type=order_type,
            status=OrderStatus.PENDING,
            created_at=T0,
        )

    def test_market_buy_execution_with_impact_and_spread(self) -> None:
        quote = make_quote(bid="999.00", ask="1001.00", ltp="1000.00")
        mkt_state = MarketState.from_quote(quote, adv=100_000, sigma=0.02)
        sim = FillSimulator()
        child = self._make_child(side=Side.BUY, qty=100)

        result = sim.simulate_fill(child, mkt_state)

        assert result.status == OrderStatus.FILLED
        assert result.fill is not None
        assert result.fill.fill_qty == 100
        # Buy fills at ask (1001.00) + impact
        assert result.fill.fill_price >= Decimal("1001.00")
        assert result.fill.simulated_impact >= Decimal("0")
        assert result.half_spread == Decimal("1.00")

    def test_market_sell_execution_with_impact(self) -> None:
        quote = make_quote(bid="999.00", ask="1001.00", ltp="1000.00")
        mkt_state = MarketState.from_quote(quote, adv=100_000, sigma=0.02)
        sim = FillSimulator()
        child = self._make_child(side=Side.SELL, qty=100)

        result = sim.simulate_fill(child, mkt_state)

        assert result.status == OrderStatus.FILLED
        assert result.fill is not None
        assert result.fill.fill_qty == 100
        # Sell fills at bid (999.00) - impact
        assert result.fill.fill_price <= Decimal("999.00")

    def test_linear_impact_formula(self) -> None:
        cfg = ExecutionConfig(impact=ImpactConfig(eta=0.1, default_sigma=0.02, default_adv=100_000))
        sim = FillSimulator(config=cfg)
        quote = make_quote(bid="1000.00", ask="1000.00")
        mkt_state = MarketState.from_quote(quote, adv=100_000, sigma=0.02)

        # impact = eta * sigma * sqrt(qty / adv) * price
        # for qty=100, adv=100000: sqrt(100/100000) = sqrt(0.001) ~ 0.03162277
        # impact = 0.1 * 0.02 * 0.03162277 * 1000 = 0.06324555
        impact = sim.compute_market_impact(100, mkt_state, ref_price=Decimal("1000"))
        assert Decimal("0.0600") <= impact <= Decimal("0.0650")

    def test_partial_fill_and_residual_rescheduling(self) -> None:
        # Order for 200, but market ask_qty is only 120
        quote = make_quote(bid="999.00", ask="1001.00", ask_qty=120)
        mkt_state = MarketState.from_quote(quote)
        cfg = ExecutionConfig(allow_partial_fills=True, reschedule_residuals=True)
        sim = FillSimulator(config=cfg)

        child = self._make_child(side=Side.BUY, qty=200)
        result = sim.simulate_fill(child, mkt_state)

        assert result.status == OrderStatus.PARTIALLY_FILLED
        assert result.fill is not None
        assert result.fill.fill_qty == 120
        assert result.residual_child is not None
        assert result.residual_child.qty == 80
        assert result.residual_child.status == OrderStatus.PENDING

    def test_limit_order_executable_vs_expired(self) -> None:
        quote = make_quote(bid="999.00", ask="1001.00")
        mkt_state = MarketState.from_quote(quote)
        sim = FillSimulator()

        # Limit Buy with limit 1005 (ask is 1001 <= 1005 -> executes passively at 1005)
        child_exec = self._make_child(
            side=Side.BUY, qty=50, order_type=OrderType.LIMIT, limit_price=Decimal("1005.00")
        )
        res_exec = sim.simulate_fill(child_exec, mkt_state)
        assert res_exec.status == OrderStatus.FILLED
        assert res_exec.fill is not None
        assert res_exec.fill.fill_price == Decimal("1005.00")
        assert res_exec.fill.simulated_impact == Decimal("0")

        # Limit Buy with limit 995 (ask is 1001 > 995 -> cannot execute, expires)
        child_unexec = self._make_child(
            side=Side.BUY, qty=50, order_type=OrderType.LIMIT, limit_price=Decimal("995.00")
        )
        res_unexec = sim.simulate_fill(child_unexec, mkt_state)
        assert res_unexec.status == OrderStatus.EXPIRED
        assert res_unexec.fill is None

    def test_ioc_order_partial_no_reschedule(self) -> None:
        quote = make_quote(bid="999.00", ask="1001.00", ask_qty=60)
        mkt_state = MarketState.from_quote(quote)
        sim = FillSimulator()

        child_ioc = self._make_child(side=Side.BUY, qty=100, order_type=OrderType.IOC)
        res = sim.simulate_fill(child_ioc, mkt_state)

        assert res.status == OrderStatus.PARTIALLY_FILLED
        assert res.fill is not None
        assert res.fill.fill_qty == 60
        assert res.residual_child is None  # IOC never reschedules
