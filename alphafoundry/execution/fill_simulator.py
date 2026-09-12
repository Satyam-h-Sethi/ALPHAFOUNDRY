"""Deterministic Fill Simulator for execution simulation.

Implements market/limit order execution, linear market impact, spread cost,
partial fills, and residual order rescheduling per execution-model.md §5.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID, uuid4

from alphafoundry.domain.enums import OrderStatus, OrderType, Side
from alphafoundry.domain.market_data import Quote
from alphafoundry.domain.orders import ChildOrder, Fill
from alphafoundry.execution.config import ExecutionConfig, ImpactConfig


@dataclass(frozen=True)
class MarketState:
    """Current market quote snapshot with liquidity and volatility parameters."""

    instrument_id: UUID
    timestamp: datetime
    bid_price: Decimal
    ask_price: Decimal
    bid_qty: int
    ask_qty: int
    last_trade_price: Decimal | None = None
    adv: int = 100_000
    sigma: float = 0.02

    @property
    def mid_price(self) -> Decimal:
        return (self.bid_price + self.ask_price) / Decimal("2")

    @property
    def spread(self) -> Decimal:
        return max(Decimal("0"), self.ask_price - self.bid_price)

    @property
    def half_spread(self) -> Decimal:
        return self.spread / Decimal("2")

    @classmethod
    def from_quote(
        cls,
        quote: Quote,
        adv: int = 100_000,
        sigma: float = 0.02,
    ) -> MarketState:
        return cls(
            instrument_id=quote.instrument_id,
            timestamp=quote.timestamp,
            bid_price=quote.bid_price,
            ask_price=quote.ask_price,
            bid_qty=quote.bid_qty,
            ask_qty=quote.ask_qty,
            last_trade_price=quote.last_trade_price,
            adv=adv,
            sigma=sigma,
        )


@dataclass(frozen=True)
class FillResult:
    """Outcome of attempting to fill a ChildOrder against a MarketState."""

    child_order_id: UUID
    status: OrderStatus
    fill: Fill | None
    residual_child: ChildOrder | None
    half_spread: Decimal
    mid_price: Decimal
    unfilled_reason: str | None = None


class FillSimulator:
    """Simulates child order execution against market state."""

    def __init__(
        self,
        config: ExecutionConfig | None = None,
        rng_seed: int | None = 42,
    ) -> None:
        self.config = config or ExecutionConfig()
        self.rng_seed = rng_seed

    def simulate_fill(
        self,
        child_order: ChildOrder,
        market_state: MarketState,
        arrival_price: Decimal | None = None,
    ) -> FillResult:
        """Simulate execution of a single child order against current market state.

        Parameters
        ----------
        child_order:
            ChildOrder to fill.
        market_state:
            Market price, spread, depth, ADV, and volatility.
        arrival_price:
            Reference arrival price (used for impact reference price if needed).
        """
        if child_order.status in (
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.EXPIRED,
        ):
            return FillResult(
                child_order_id=child_order.child_order_id,
                status=child_order.status,
                fill=None,
                residual_child=None,
                half_spread=market_state.half_spread,
                mid_price=market_state.mid_price,
                unfilled_reason=f"Order is already {child_order.status}",
            )

        if child_order.order_type == OrderType.MARKET:
            return self._fill_market_order(child_order, market_state, arrival_price)
        elif child_order.order_type == OrderType.LIMIT:
            return self._fill_limit_order(child_order, market_state, arrival_price)
        elif child_order.order_type == OrderType.IOC:
            return self._fill_ioc_order(child_order, market_state, arrival_price)
        else:
            return self._fill_market_order(child_order, market_state, arrival_price)

    def compute_market_impact(
        self,
        qty: int,
        market_state: MarketState,
        ref_price: Decimal | None = None,
    ) -> Decimal:
        """Calculate linear market impact: impact = eta * sigma * sqrt(qty / ADV) * price.

        Parameters
        ----------
        qty:
            Order execution quantity.
        market_state:
            Market state containing adv and sigma.
        ref_price:
            Reference price (defaults to mid_price).
        """
        if qty <= 0:
            return Decimal("0")

        eta = self.config.impact.eta
        adv = max(1, market_state.adv or self.config.impact.default_adv)
        sigma = market_state.sigma or self.config.impact.default_sigma
        price = ref_price or market_state.mid_price

        ratio = qty / adv
        sqrt_ratio = math.sqrt(ratio)
        impact_float = eta * sigma * sqrt_ratio * float(price)

        impact_decimal = Decimal(str(impact_float)).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP
        )
        return max(Decimal("0"), impact_decimal)

    def _fill_market_order(
        self,
        child_order: ChildOrder,
        market_state: MarketState,
        arrival_price: Decimal | None,
    ) -> FillResult:
        is_buy = child_order.side == Side.BUY
        available_qty = (
            market_state.ask_qty if is_buy else market_state.bid_qty
        )

        # Handle partial fill vs full fill
        if (
            self.config.allow_partial_fills
            and available_qty > 0
            and child_order.qty > available_qty
        ):
            fill_qty = available_qty
            residual_qty = child_order.qty - fill_qty
        else:
            fill_qty = child_order.qty
            residual_qty = 0

        # Calculate price & impact
        impact = self.compute_market_impact(
            fill_qty, market_state, arrival_price or market_state.mid_price
        )

        if is_buy:
            raw_price = market_state.ask_price
            fill_price = raw_price + impact
        else:
            raw_price = market_state.bid_price
            fill_price = max(Decimal("0.0001"), raw_price - impact)

        fill_price = fill_price.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

        fill = Fill(
            fill_id=uuid4(),
            child_order_id=child_order.child_order_id,
            fill_qty=fill_qty,
            fill_price=fill_price,
            simulated_impact=impact,
            fill_timestamp=market_state.timestamp,
            rng_seed=self.rng_seed,
        )

        residual_child: ChildOrder | None = None
        if residual_qty > 0 and self.config.reschedule_residuals:
            residual_child = ChildOrder(
                child_order_id=uuid4(),
                parent_order_id=child_order.parent_order_id,
                sequence_num=child_order.sequence_num + 1,
                instrument_id=child_order.instrument_id,
                side=child_order.side,
                qty=residual_qty,
                limit_price=child_order.limit_price,
                order_type=child_order.order_type,
                status=OrderStatus.PENDING,
                created_at=market_state.timestamp,
            )

        status = (
            OrderStatus.PARTIALLY_FILLED
            if residual_qty > 0
            else OrderStatus.FILLED
        )

        return FillResult(
            child_order_id=child_order.child_order_id,
            status=status,
            fill=fill,
            residual_child=residual_child,
            half_spread=market_state.half_spread,
            mid_price=market_state.mid_price,
        )

    def _fill_limit_order(
        self,
        child_order: ChildOrder,
        market_state: MarketState,
        arrival_price: Decimal | None,
    ) -> FillResult:
        if child_order.limit_price is None:
            return self._fill_market_order(child_order, market_state, arrival_price)

        is_buy = child_order.side == Side.BUY
        limit_price = child_order.limit_price

        # Limit check: Buy fills if ask <= limit; Sell fills if bid >= limit
        executable = (
            (market_state.ask_price <= limit_price)
            if is_buy
            else (market_state.bid_price >= limit_price)
        )

        if not executable:
            return FillResult(
                child_order_id=child_order.child_order_id,
                status=OrderStatus.EXPIRED,
                fill=None,
                residual_child=None,
                half_spread=market_state.half_spread,
                mid_price=market_state.mid_price,
                unfilled_reason=(
                    f"Limit breached: limit={limit_price}, "
                    f"market={'ask' if is_buy else 'bid'}="
                    f"{market_state.ask_price if is_buy else market_state.bid_price}"
                ),
            )

        # Passive fill at limit price per §5.1
        available_qty = (
            market_state.ask_qty if is_buy else market_state.bid_qty
        )
        if (
            self.config.allow_partial_fills
            and available_qty > 0
            and child_order.qty > available_qty
        ):
            fill_qty = available_qty
            residual_qty = child_order.qty - fill_qty
        else:
            fill_qty = child_order.qty
            residual_qty = 0

        impact = Decimal("0")  # Passive fill has 0 direct adverse impact

        fill = Fill(
            fill_id=uuid4(),
            child_order_id=child_order.child_order_id,
            fill_qty=fill_qty,
            fill_price=limit_price.quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_UP
            ),
            simulated_impact=impact,
            fill_timestamp=market_state.timestamp,
            rng_seed=self.rng_seed,
        )

        residual_child: ChildOrder | None = None
        if residual_qty > 0 and self.config.reschedule_residuals:
            residual_child = ChildOrder(
                child_order_id=uuid4(),
                parent_order_id=child_order.parent_order_id,
                sequence_num=child_order.sequence_num + 1,
                instrument_id=child_order.instrument_id,
                side=child_order.side,
                qty=residual_qty,
                limit_price=child_order.limit_price,
                order_type=child_order.order_type,
                status=OrderStatus.PENDING,
                created_at=market_state.timestamp,
            )

        status = (
            OrderStatus.PARTIALLY_FILLED
            if residual_qty > 0
            else OrderStatus.FILLED
        )

        return FillResult(
            child_order_id=child_order.child_order_id,
            status=status,
            fill=fill,
            residual_child=residual_child,
            half_spread=market_state.half_spread,
            mid_price=market_state.mid_price,
        )

    def _fill_ioc_order(
        self,
        child_order: ChildOrder,
        market_state: MarketState,
        arrival_price: Decimal | None,
    ) -> FillResult:
        # IOC executes immediately against available liquidity; remainder is cancelled immediately
        is_buy = child_order.side == Side.BUY
        available_qty = (
            market_state.ask_qty if is_buy else market_state.bid_qty
        )

        if child_order.limit_price is not None:
            executable = (
                (market_state.ask_price <= child_order.limit_price)
                if is_buy
                else (market_state.bid_price >= child_order.limit_price)
            )
            if not executable:
                return FillResult(
                    child_order_id=child_order.child_order_id,
                    status=OrderStatus.CANCELLED,
                    fill=None,
                    residual_child=None,
                    half_spread=market_state.half_spread,
                    mid_price=market_state.mid_price,
                    unfilled_reason="IOC limit price not satisfied",
                )

        fill_qty = min(child_order.qty, available_qty) if available_qty > 0 else 0
        if fill_qty <= 0:
            return FillResult(
                child_order_id=child_order.child_order_id,
                status=OrderStatus.CANCELLED,
                fill=None,
                residual_child=None,
                half_spread=market_state.half_spread,
                mid_price=market_state.mid_price,
                unfilled_reason="IOC zero liquidity available",
            )

        impact = self.compute_market_impact(
            fill_qty, market_state, arrival_price or market_state.mid_price
        )
        if is_buy:
            raw_price = market_state.ask_price
            fill_price = raw_price + impact
        else:
            raw_price = market_state.bid_price
            fill_price = max(Decimal("0.0001"), raw_price - impact)

        fill = Fill(
            fill_id=uuid4(),
            child_order_id=child_order.child_order_id,
            fill_qty=fill_qty,
            fill_price=fill_price.quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_UP
            ),
            simulated_impact=impact,
            fill_timestamp=market_state.timestamp,
            rng_seed=self.rng_seed,
        )

        status = (
            OrderStatus.FILLED
            if fill_qty == child_order.qty
            else OrderStatus.PARTIALLY_FILLED
        )

        return FillResult(
            child_order_id=child_order.child_order_id,
            status=status,
            fill=fill,
            residual_child=None,  # IOC never reschedules residuals
            half_spread=market_state.half_spread,
            mid_price=market_state.mid_price,
        )
