"""Deterministic Order Slicer for execution simulation.

Implements 5 algorithms specified in execution-model.md §4:
  1. TWAP   — Time-Weighted Average Price
  2. VWAP   — Volume-Weighted Average Price
  3. POV    — Percentage of Volume
  4. IS     — Implementation Shortfall
  5. MARKET — Immediate execution
"""

from __future__ import annotations

import logging
import math
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Sequence
from uuid import UUID, uuid4

from alphafoundry.domain.enums import OrderStatus, OrderType, Side, Urgency
from alphafoundry.domain.orders import ChildOrder, ParentOrder
from alphafoundry.execution.config import SlicerConfig

logger = logging.getLogger(__name__)


class OrderSlicer:
    """Slices approved ParentOrders into deterministic sequences of ChildOrders."""

    def __init__(
        self,
        config: SlicerConfig | None = None,
        now: datetime | None = None,
    ) -> None:
        self.config = config or SlicerConfig()
        self._now = now

    def slice_order(
        self,
        parent_order: ParentOrder,
        arrival_price: Decimal | None = None,
        volume_profile: Sequence[int] | None = None,
        observed_volumes: Sequence[int] | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[ChildOrder]:
        """Generate a deterministic sequence of ChildOrders for a ParentOrder.

        Parameters
        ----------
        parent_order:
            The approved ParentOrder to slice.
        arrival_price:
            Price used to resolve target_notional into target_qty if needed.
        volume_profile:
            Historical/expected volume profile buckets for VWAP slicing.
        observed_volumes:
            Observed volume sequence for POV slicing.
        start_time:
            Execution window start (defaults to parent_order.created_at or now).
        end_time:
            Execution window end.

        Returns
        -------
        list[ChildOrder]
            Ordered list of child orders preserving exact target quantity.
        """
        target_qty = self._resolve_target_qty(parent_order, arrival_price)
        if target_qty <= 0:
            raise ValueError(
                f"Target quantity must be > 0 (resolved: {target_qty})"
            )

        t_start = (
            start_time
            or parent_order.created_at
            or (self._now if self._now is not None else datetime.now(UTC))
        )
        if t_start.tzinfo is None:
            t_start = t_start.replace(tzinfo=UTC)

        algo = (parent_order.algo or "MARKET").upper().strip()

        if algo == "MARKET":
            quantities, timestamps = self._slice_market(target_qty, t_start)
        elif algo == "TWAP":
            quantities, timestamps = self._slice_twap(
                target_qty, t_start, end_time, self.config.twap_num_buckets
            )
        elif algo == "VWAP":
            quantities, timestamps = self._slice_vwap(
                target_qty, t_start, end_time, volume_profile
            )
        elif algo == "POV":
            quantities, timestamps = self._slice_pov(
                target_qty, t_start, observed_volumes
            )
        elif algo == "IS":
            quantities, timestamps = self._slice_is(
                target_qty, t_start, end_time, parent_order.urgency
            )
        else:
            logger.warning(
                "Unknown algo '%s'; defaulting to MARKET execution", algo
            )
            quantities, timestamps = self._slice_market(target_qty, t_start)

        # Build immutable ChildOrder domain objects
        order_type = (
            OrderType.LIMIT
            if parent_order.price_limit is not None
            else OrderType.MARKET
        )
        child_orders: list[ChildOrder] = []
        for seq_num, (qty, ts) in enumerate(zip(quantities, timestamps, strict=False)):
            if qty <= 0:
                continue
            child_orders.append(
                ChildOrder(
                    child_order_id=uuid4(),
                    parent_order_id=parent_order.parent_order_id,
                    sequence_num=seq_num,
                    instrument_id=parent_order.instrument_id,
                    side=parent_order.side,
                    qty=qty,
                    limit_price=parent_order.price_limit,
                    order_type=order_type,
                    status=OrderStatus.PENDING,
                    created_at=ts,
                )
            )

        # Verify exact quantity conservation
        total_sliced = sum(c.qty for c in child_orders)
        if total_sliced != target_qty:
            raise RuntimeError(
                f"Slicer quantity conservation violated: expected {target_qty}, got {total_sliced}"
            )

        return child_orders

    def _resolve_target_qty(
        self,
        parent_order: ParentOrder,
        arrival_price: Decimal | None,
    ) -> int:
        if parent_order.target_qty is not None:
            return int(parent_order.target_qty)

        if parent_order.target_notional is not None:
            if arrival_price is None or arrival_price <= Decimal("0"):
                raise ValueError(
                    "arrival_price must be positive to resolve target_notional"
                )
            return int(parent_order.target_notional / arrival_price)

        raise ValueError("ParentOrder has neither target_qty nor target_notional")

    def _slice_market(
        self, target_qty: int, start_time: datetime
    ) -> tuple[list[int], list[datetime]]:
        return [target_qty], [start_time]

    def _slice_twap(
        self,
        target_qty: int,
        start_time: datetime,
        end_time: datetime | None,
        num_buckets: int,
    ) -> tuple[list[int], list[datetime]]:
        n = max(1, min(num_buckets, target_qty))
        bucket_width = (
            (end_time - start_time) / n
            if end_time and end_time > start_time
            else timedelta(minutes=1)
        )

        base_qty = math.ceil(target_qty / n)
        quantities: list[int] = []
        remaining = target_qty

        for i in range(n):
            if i == n - 1:
                alloc = remaining
            else:
                alloc = min(base_qty, remaining)
            if alloc > 0:
                quantities.append(alloc)
                remaining -= alloc
            if remaining <= 0:
                break

        # Re-adjust last bucket if needed for exact conservation
        allocated_sum = sum(quantities)
        if allocated_sum != target_qty and quantities:
            quantities[-1] += target_qty - allocated_sum

        timestamps = [start_time + i * bucket_width for i in range(len(quantities))]
        return quantities, timestamps

    def _slice_vwap(
        self,
        target_qty: int,
        start_time: datetime,
        end_time: datetime | None,
        volume_profile: Sequence[int] | None,
    ) -> tuple[list[int], list[datetime]]:
        if not volume_profile or sum(volume_profile) <= 0:
            logger.info("No volume profile available for VWAP; falling back to TWAP")
            return self._slice_twap(
                target_qty, start_time, end_time, self.config.vwap_num_buckets
            )

        n = len(volume_profile)
        total_vol = sum(volume_profile)
        bucket_width = (
            (end_time - start_time) / n
            if end_time and end_time > start_time
            else timedelta(minutes=1)
        )

        quantities: list[int] = []
        allocated = 0

        for i in range(n):
            if i == n - 1:
                alloc = target_qty - allocated
            else:
                ratio = volume_profile[i] / total_vol
                alloc = int(math.floor(target_qty * ratio))
            alloc = max(0, alloc)
            quantities.append(alloc)
            allocated += alloc

        # Fix zero quantities if any, redistributing to maintain conservation
        quantities, timestamps = self._clean_and_conserve(
            quantities, target_qty, start_time, bucket_width
        )
        return quantities, timestamps

    def _slice_pov(
        self,
        target_qty: int,
        start_time: datetime,
        observed_volumes: Sequence[int] | None,
    ) -> tuple[list[int], list[datetime]]:
        pov_rate = self.config.pov_rate
        window_delta = timedelta(seconds=self.config.pov_window_seconds)

        if not observed_volumes:
            # Synthetic default: 10 uniform buckets at POV rate
            n = max(1, math.ceil(1.0 / pov_rate))
            return self._slice_twap(target_qty, start_time, None, n)

        quantities: list[int] = []
        timestamps: list[datetime] = []
        remaining = target_qty
        current_time = start_time

        for vol in observed_volumes:
            if remaining <= 0:
                break
            child_qty = min(int(vol * pov_rate), remaining)
            if child_qty > 0:
                quantities.append(child_qty)
                timestamps.append(current_time)
                remaining -= child_qty
            current_time += window_delta

        # If any remaining quantity after observed volume windows, allocate as final slice
        if remaining > 0:
            if quantities:
                quantities[-1] += remaining
            else:
                quantities.append(remaining)
                timestamps.append(current_time)

        return quantities, timestamps

    def _slice_is(
        self,
        target_qty: int,
        start_time: datetime,
        end_time: datetime | None,
        urgency: Urgency,
    ) -> tuple[list[int], list[datetime]]:
        weights = self.config.urgency_weights.get(
            urgency,
            self.config.urgency_weights[Urgency.MEDIUM],
        )
        n = len(weights)
        bucket_width = (
            (end_time - start_time) / n
            if end_time and end_time > start_time
            else timedelta(minutes=1)
        )

        quantities: list[int] = []
        allocated = 0

        for i in range(n):
            if i == n - 1:
                alloc = target_qty - allocated
            else:
                alloc = int(math.floor(target_qty * weights[i]))
            alloc = max(0, alloc)
            quantities.append(alloc)
            allocated += alloc

        quantities, timestamps = self._clean_and_conserve(
            quantities, target_qty, start_time, bucket_width
        )
        return quantities, timestamps

    def _clean_and_conserve(
        self,
        raw_quantities: list[int],
        target_qty: int,
        start_time: datetime,
        bucket_width: timedelta,
    ) -> tuple[list[int], list[datetime]]:
        """Ensure all quantities are > 0 and sum exactly to target_qty."""
        # Filter out 0 quantities while recording their scheduled times
        active_pairs: list[tuple[int, datetime]] = []
        for i, q in enumerate(raw_quantities):
            if q > 0:
                active_pairs.append((q, start_time + i * bucket_width))

        if not active_pairs:
            # If all were 0 (e.g. target_qty is small), assign full target_qty to bucket 0
            return [target_qty], [start_time]

        quantities = [p[0] for p in active_pairs]
        timestamps = [p[1] for p in active_pairs]

        # Conserve target_qty exactly into the last active slice
        diff = target_qty - sum(quantities)
        quantities[-1] += diff

        # If last slice became <= 0 due to negative adjustment, rebalance
        if quantities[-1] <= 0:
            return self._slice_twap(target_qty, start_time, None, len(quantities))

        return quantities, timestamps
