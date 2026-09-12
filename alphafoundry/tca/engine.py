"""Transaction Cost Analysis (TCA) Engine.

Computes execution quality benchmarks and cost breakdowns per execution-model.md §7:
  - Benchmarks: ARRIVAL, VWAP, TWAP, CLOSE
  - Metrics: Execution price (fill VWAP), realized slippage, spread cost,
    simulated impact cost, timing cost, implementation shortfall, duration.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Sequence
from uuid import UUID, uuid4

from alphafoundry.domain.enums import BenchmarkType, Side
from alphafoundry.domain.orders import Fill, ParentOrder
from alphafoundry.domain.tca import TCAReport


class TCAEngine:
    """Computes comprehensive post-trade Transaction Cost Analysis for ParentOrders."""

    def __init__(self, now: datetime | None = None) -> None:
        self._now = now

    def compute_report(
        self,
        parent_order: ParentOrder,
        fills: Sequence[Fill],
        benchmark_type: BenchmarkType = BenchmarkType.ARRIVAL,
        benchmark_price: Decimal | None = None,
        arrival_price: Decimal | None = None,
        half_spreads: Sequence[Decimal] | None = None,
        computed_at: datetime | None = None,
    ) -> TCAReport:
        """Compute full TCAReport for an executed ParentOrder and its Fills.

        Parameters
        ----------
        parent_order:
            The executed ParentOrder.
        fills:
            Sequence of Fill records for this parent order.
        benchmark_type:
            Type of benchmark (ARRIVAL, VWAP, TWAP, CLOSE).
        benchmark_price:
            Price of the selected benchmark. Defaults to arrival_price or first fill price.
        arrival_price:
            Arrival price at the moment parent order was approved.
        half_spreads:
            Optional sequence of half-spreads corresponding to each fill.
        computed_at:
            Timestamp of report generation.
        """
        now_ts = (
            computed_at
            or self._now
            or datetime.now(UTC)
        )
        if now_ts.tzinfo is None:
            now_ts = now_ts.replace(tzinfo=UTC)

        total_qty = sum(f.fill_qty for f in fills)
        fill_count = len(fills)

        # Determine reference benchmark price
        if benchmark_price is None:
            if arrival_price is not None:
                bench_p = arrival_price
            elif fills:
                bench_p = fills[0].fill_price
            else:
                bench_p = Decimal("1000.0000")
        else:
            bench_p = benchmark_price

        arr_p = arrival_price if arrival_price is not None else bench_p

        # Handle zero-fill case gracefully
        if total_qty == 0 or not fills:
            return TCAReport(
                tca_report_id=uuid4(),
                parent_order_id=parent_order.parent_order_id,
                benchmark_type=benchmark_type,
                benchmark_price=bench_p.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP),
                execution_price=bench_p.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP),
                realized_slippage=Decimal("0.0000"),
                spread_cost=Decimal("0.0000"),
                impact_cost=Decimal("0.0000"),
                timing_cost=Decimal("0.0000"),
                implementation_shortfall=Decimal("0.0000"),
                total_qty=0,
                fill_count=0,
                execution_duration_seconds=0.0,
                computed_at=now_ts,
            )

        # 1. Execution Price = Fill VWAP = sum(qty * price) / total_qty
        total_notional = sum(Decimal(str(f.fill_qty)) * f.fill_price for f in fills)
        execution_price = (total_notional / Decimal(str(total_qty))).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP
        )

        is_buy = parent_order.side == Side.BUY

        # 2. Realized Slippage = (execution_price - benchmark_price) for BUY
        #                      = (benchmark_price - execution_price) for SELL
        if is_buy:
            realized_slippage = execution_price - bench_p
        else:
            realized_slippage = bench_p - execution_price
        realized_slippage = realized_slippage.quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP
        )

        # 3. Spread Cost = sum(fill_qty * half_spread) / total_qty
        if half_spreads and len(half_spreads) == len(fills):
            total_spread_cost = sum(
                Decimal(str(f.fill_qty)) * hs for f, hs in zip(fills, half_spreads, strict=False)
            )
            spread_cost = (total_spread_cost / Decimal(str(total_qty))).quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_UP
            )
        else:
            spread_cost = Decimal("0.0000")

        # 4. Impact Cost = sum(fill_qty * simulated_impact) / total_qty
        total_impact = sum(
            Decimal(str(f.fill_qty)) * f.simulated_impact for f in fills
        )
        impact_cost = (total_impact / Decimal(str(total_qty))).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP
        )

        # 5. Timing Cost = (benchmark_price - arrival_price) for BUY
        #                = (arrival_price - benchmark_price) for SELL
        if benchmark_type == BenchmarkType.ARRIVAL:
            timing_cost = Decimal("0.0000")
        else:
            if is_buy:
                timing_cost = bench_p - arr_p
            else:
                timing_cost = arr_p - bench_p
            timing_cost = timing_cost.quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_UP
            )

        # 6. Implementation Shortfall = spread_cost + impact_cost + timing_cost
        # If spread_cost wasn't separately provided, IS against arrival is realized_slippage
        if spread_cost == Decimal("0.0000") and benchmark_type == BenchmarkType.ARRIVAL:
            implementation_shortfall = realized_slippage
        else:
            implementation_shortfall = (
                spread_cost + impact_cost + timing_cost
            ).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

        # 7. Execution Duration
        timestamps = [f.fill_timestamp for f in fills]
        min_ts = min(timestamps)
        max_ts = max(timestamps)
        duration_seconds = max(0.0, (max_ts - min_ts).total_seconds())

        return TCAReport(
            tca_report_id=uuid4(),
            parent_order_id=parent_order.parent_order_id,
            benchmark_type=benchmark_type,
            benchmark_price=bench_p.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP),
            execution_price=execution_price,
            realized_slippage=realized_slippage,
            spread_cost=spread_cost,
            impact_cost=impact_cost,
            timing_cost=timing_cost,
            implementation_shortfall=implementation_shortfall,
            total_qty=total_qty,
            fill_count=fill_count,
            execution_duration_seconds=duration_seconds,
            computed_at=now_ts,
        )

    @staticmethod
    def calculate_bps(amount: Decimal, benchmark_price: Decimal) -> float:
        """Convert a rupee cost/slippage amount to basis points (bps)."""
        if benchmark_price <= Decimal("0"):
            return 0.0
        return float((amount / benchmark_price) * Decimal("10000"))
