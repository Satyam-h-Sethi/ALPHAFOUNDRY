"""Unit tests for TCA Engine (Phase 05)."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4
import pytest

from alphafoundry.domain.enums import BenchmarkType, Side
from alphafoundry.domain.orders import Fill
from alphafoundry.tca.engine import TCAEngine
from tests.execution.conftest import T0, make_parent_order


class TestTCAEngine:
    def _make_fill(
        self,
        qty: int,
        price: str,
        impact: str = "0.05",
        delta_sec: float = 0.0,
    ) -> Fill:
        return Fill(
            child_order_id=uuid4(),
            fill_qty=qty,
            fill_price=Decimal(price),
            simulated_impact=Decimal(impact),
            fill_timestamp=T0 + timedelta(seconds=delta_sec),
        )

    def test_tca_arrival_benchmark_buy(self) -> None:
        engine = TCAEngine(now=T0)
        parent = make_parent_order(side=Side.BUY, qty=100)

        # 2 fills: 60 @ 1002.00 (impact 0.10), 40 @ 1004.00 (impact 0.20)
        # arrival_price = 1000.00
        # Fill VWAP = (60*1002 + 40*1004) / 100 = (60120 + 40160) / 100 = 1002.8000
        # Realized Slippage = 1002.8000 - 1000.0000 = 2.8000
        f1 = self._make_fill(60, "1002.0000", impact="0.1000", delta_sec=0)
        f2 = self._make_fill(40, "1004.0000", impact="0.2000", delta_sec=60)
        half_spreads = [Decimal("1.0000"), Decimal("1.0000")]

        report = engine.compute_report(
            parent_order=parent,
            fills=[f1, f2],
            benchmark_type=BenchmarkType.ARRIVAL,
            benchmark_price=Decimal("1000.0000"),
            arrival_price=Decimal("1000.0000"),
            half_spreads=half_spreads,
        )

        assert report.execution_price == Decimal("1002.8000")
        assert report.realized_slippage == Decimal("2.8000")
        assert report.spread_cost == Decimal("1.0000")
        # Impact cost = (60*0.10 + 40*0.20)/100 = (6 + 8)/100 = 0.1400
        assert report.impact_cost == Decimal("0.1400")
        assert report.timing_cost == Decimal("0.0000")
        # IS = spread (1.0) + impact (0.14) + timing (0.0) = 1.1400
        assert report.implementation_shortfall == Decimal("1.1400")
        assert report.total_qty == 100
        assert report.fill_count == 2
        assert report.execution_duration_seconds == 60.0

    def test_tca_arrival_benchmark_sell(self) -> None:
        engine = TCAEngine(now=T0)
        parent = make_parent_order(side=Side.SELL, qty=100)

        # Fills: 100 @ 995.0000, arrival = 1000.0000
        # Realized Slippage for SELL = benchmark - execution = 1000.0000 - 995.0000 = 5.0000
        f1 = self._make_fill(100, "995.0000", impact="0.5000")
        report = engine.compute_report(
            parent_order=parent,
            fills=[f1],
            benchmark_type=BenchmarkType.ARRIVAL,
            benchmark_price=Decimal("1000.0000"),
            arrival_price=Decimal("1000.0000"),
        )

        assert report.execution_price == Decimal("995.0000")
        assert report.realized_slippage == Decimal("5.0000")

    def test_tca_vwap_and_timing_cost(self) -> None:
        engine = TCAEngine(now=T0)
        parent = make_parent_order(side=Side.BUY, qty=100)

        # arrival = 1000.00, VWAP benchmark = 1005.00
        # timing cost = 1005.00 - 1000.00 = 5.00
        f1 = self._make_fill(100, "1006.0000", impact="0.2000")
        half_spreads = [Decimal("0.5000")]

        report = engine.compute_report(
            parent_order=parent,
            fills=[f1],
            benchmark_type=BenchmarkType.VWAP,
            benchmark_price=Decimal("1005.0000"),
            arrival_price=Decimal("1000.0000"),
            half_spreads=half_spreads,
        )

        assert report.timing_cost == Decimal("5.0000")
        assert report.spread_cost == Decimal("0.5000")
        assert report.impact_cost == Decimal("0.2000")
        assert report.implementation_shortfall == Decimal("5.7000")

    def test_calculate_bps_helper(self) -> None:
        # 5 rupees on 1000 rupee benchmark = (5 / 1000) * 10000 = 50.0 bps
        bps = TCAEngine.calculate_bps(Decimal("5.0000"), Decimal("1000.0000"))
        assert bps == 50.0

    def test_zero_fills_graceful_handling(self) -> None:
        engine = TCAEngine(now=T0)
        parent = make_parent_order(qty=100)
        report = engine.compute_report(
            parent_order=parent,
            fills=[],
            benchmark_price=Decimal("1000.0000"),
        )
        assert report.total_qty == 0
        assert report.fill_count == 0
        assert report.realized_slippage == Decimal("0.0000")
