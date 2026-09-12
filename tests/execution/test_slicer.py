"""Unit tests for Order Slicer (Phase 05)."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import pytest

from alphafoundry.domain.enums import OrderStatus, OrderType, Side, Urgency
from alphafoundry.domain.orders import ParentOrder
from alphafoundry.execution.config import SlicerConfig
from alphafoundry.execution.slicer import OrderSlicer
from tests.execution.conftest import T0, make_parent_order


class TestOrderSlicer:
    def test_market_algo_single_slice(self) -> None:
        slicer = OrderSlicer()
        order = make_parent_order(qty=500, algo="MARKET")
        children = slicer.slice_order(order, arrival_price=Decimal("1000"))

        assert len(children) == 1
        assert children[0].qty == 500
        assert children[0].parent_order_id == order.parent_order_id
        assert children[0].instrument_id == order.instrument_id
        assert children[0].side == Side.BUY
        assert children[0].status == OrderStatus.PENDING
        assert children[0].sequence_num == 0

    def test_twap_algo_conservation_and_buckets(self) -> None:
        cfg = SlicerConfig(twap_num_buckets=5)
        slicer = OrderSlicer(config=cfg)
        order = make_parent_order(qty=103, algo="TWAP")
        end_t = T0 + timedelta(minutes=5)
        children = slicer.slice_order(
            order,
            arrival_price=Decimal("1000"),
            start_time=T0,
            end_time=end_t,
        )

        assert len(children) == 5
        assert sum(c.qty for c in children) == 103
        for i, c in enumerate(children):
            assert c.sequence_num == i
            assert c.qty > 0
            assert c.created_at >= T0

    def test_vwap_algo_with_volume_profile(self) -> None:
        slicer = OrderSlicer()
        order = make_parent_order(qty=1000, algo="VWAP")
        profile = [1000, 2000, 3000, 2000, 2000]  # sums to 10000 -> 10%, 20%, 30%, 20%, 20%
        end_t = T0 + timedelta(minutes=10)
        children = slicer.slice_order(
            order,
            arrival_price=Decimal("1000"),
            volume_profile=profile,
            start_time=T0,
            end_time=end_t,
        )

        assert len(children) == 5
        assert sum(c.qty for c in children) == 1000
        # Expected shares: 100, 200, 300, 200, 200
        assert [c.qty for c in children] == [100, 200, 300, 200, 200]

    def test_vwap_fallback_to_twap_if_empty_profile(self) -> None:
        cfg = SlicerConfig(vwap_num_buckets=4)
        slicer = OrderSlicer(config=cfg)
        order = make_parent_order(qty=100, algo="VWAP")
        children = slicer.slice_order(order, arrival_price=Decimal("1000"), volume_profile=[])

        assert len(children) == 4
        assert sum(c.qty for c in children) == 100

    def test_pov_algo_with_observed_volumes(self) -> None:
        cfg = SlicerConfig(pov_rate=0.10, pov_window_seconds=60.0)
        slicer = OrderSlicer(config=cfg)
        order = make_parent_order(qty=250, algo="POV")
        observed = [1000, 1000, 500]  # 100 + 100 + 50 = 250
        children = slicer.slice_order(
            order,
            arrival_price=Decimal("1000"),
            observed_volumes=observed,
            start_time=T0,
        )

        assert len(children) == 3
        assert sum(c.qty for c in children) == 250
        assert [c.qty for c in children] == [100, 100, 50]

    def test_is_algo_urgency_weights(self) -> None:
        slicer = OrderSlicer()
        order_high = make_parent_order(qty=1000, algo="IS", urgency=Urgency.HIGH)
        children_high = slicer.slice_order(
            order_high,
            arrival_price=Decimal("1000"),
            start_time=T0,
            end_time=T0 + timedelta(minutes=5),
        )

        assert sum(c.qty for c in children_high) == 1000
        # High urgency should front-load (bucket 0 has highest qty)
        assert children_high[0].qty > children_high[-1].qty

        order_low = make_parent_order(qty=1000, algo="IS", urgency=Urgency.LOW)
        children_low = slicer.slice_order(
            order_low,
            arrival_price=Decimal("1000"),
            start_time=T0,
            end_time=T0 + timedelta(minutes=5),
        )
        assert sum(c.qty for c in children_low) == 1000
        # Low urgency should back-load (bucket 0 has lower qty than last bucket)
        assert children_low[0].qty < children_low[-1].qty

    def test_resolve_target_notional_into_target_qty(self) -> None:
        slicer = OrderSlicer()
        order = make_parent_order(qty=None, notional=Decimal("100000"), algo="MARKET")
        children = slicer.slice_order(order, arrival_price=Decimal("500"))

        assert len(children) == 1
        assert children[0].qty == 200

    def test_limit_order_type_propagation(self) -> None:
        slicer = OrderSlicer()
        order = make_parent_order(qty=100, price_limit=Decimal("995.50"), algo="MARKET")
        children = slicer.slice_order(order, arrival_price=Decimal("1000"))

        assert len(children) == 1
        assert children[0].order_type == OrderType.LIMIT
        assert children[0].limit_price == Decimal("995.50")

    def test_zero_or_negative_target_qty_raises(self) -> None:
        slicer = OrderSlicer()
        order = make_parent_order(qty=0)
        with pytest.raises(ValueError, match="Target quantity must be > 0"):
            slicer.slice_order(order, arrival_price=Decimal("1000"))
