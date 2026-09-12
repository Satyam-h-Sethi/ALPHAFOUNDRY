"""Shared fixtures and test helpers for execution module tests."""

from __future__ import annotations

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
    Urgency,
)
from alphafoundry.domain.market_data import Quote
from alphafoundry.domain.orders import ChildOrder, Fill, ParentOrder
from alphafoundry.domain.risk import RiskConfig
from alphafoundry.domain.sessions import Session
from alphafoundry.execution.config import ExecutionConfig, ImpactConfig, SlicerConfig
from alphafoundry.execution.fill_simulator import FillSimulator, MarketState
from alphafoundry.execution.position_tracker import PositionTracker
from alphafoundry.execution.session import ExecutionEngine
from alphafoundry.execution.slicer import OrderSlicer
from alphafoundry.risk.engine import RiskEngine

T0 = datetime(2026, 1, 15, 9, 15, 0, tzinfo=UTC)
INST_ID = uuid4()
SESSION_ID = uuid4()
VENUE_ID = "NSE"


def make_quote(
    bid: str = "999.00",
    ask: str = "1001.00",
    bid_qty: int = 500,
    ask_qty: int = 500,
    ltp: str = "1000.00",
    timestamp: datetime | None = None,
) -> Quote:
    ts = timestamp or T0
    return Quote(
        idempotency_key=f"NSE:quote:{ts.isoformat()}",
        instrument_id=INST_ID,
        venue_id=VENUE_ID,
        timestamp=ts,
        received_at=ts,
        sequence_id=1,
        bid_price=Decimal(bid),
        bid_qty=bid_qty,
        ask_price=Decimal(ask),
        ask_qty=ask_qty,
        last_trade_price=Decimal(ltp),
    )


def make_parent_order(
    side: Side = Side.BUY,
    qty: int | None = 100,
    notional: Decimal | None = None,
    algo: str = "MARKET",
    urgency: Urgency = Urgency.MEDIUM,
    price_limit: Decimal | None = None,
    signal_id: str = "sig-12345",
) -> ParentOrder:
    return ParentOrder(
        session_id=SESSION_ID,
        instrument_id=INST_ID,
        signal_id=signal_id,
        side=side,
        target_qty=qty,
        target_notional=notional,
        algo=algo,
        urgency=urgency,
        price_limit=price_limit,
        created_at=T0,
        updated_at=T0,
    )


def open_exchange_session() -> Session:
    return Session(
        venue_id=VENUE_ID,
        session_type=SessionType.NORMAL,
        open_time=T0 - timedelta(hours=1),
        close_time=T0 + timedelta(hours=6),
        status=SessionStatus.OPEN,
    )
