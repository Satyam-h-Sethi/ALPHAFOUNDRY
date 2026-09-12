"""Shared fixtures for risk engine tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from alphafoundry.domain.enums import (
    OrderStatus,
    SessionStatus,
    SessionType,
    Side,
)
from alphafoundry.domain.market_data import Quote
from alphafoundry.domain.orders import ParentOrder
from alphafoundry.domain.risk import PositionLimit, RiskConfig
from alphafoundry.domain.sessions import Session
from alphafoundry.risk import KillSwitch, RiskContext, RiskEngine


# ---------------------------------------------------------------------------
# Fixed reference times
# ---------------------------------------------------------------------------

T0 = datetime(2026, 1, 15, 4, 0, 0, tzinfo=UTC)   # "now" used in all tests


def _now() -> datetime:
    """Deterministic clock for tests."""
    return T0


# ---------------------------------------------------------------------------
# Instruments / IDs
# ---------------------------------------------------------------------------

INST_ID = uuid4()
SESSION_ID = uuid4()
VENUE_ID = "NSE"


# ---------------------------------------------------------------------------
# Session fixture helpers
# ---------------------------------------------------------------------------


def open_session() -> Session:
    return Session(
        venue_id=VENUE_ID,
        session_type=SessionType.NORMAL,
        open_time=T0 - timedelta(hours=1),
        close_time=T0 + timedelta(hours=5),
        status=SessionStatus.OPEN,
    )


def closed_session() -> Session:
    return Session(
        venue_id=VENUE_ID,
        session_type=SessionType.NORMAL,
        open_time=T0 - timedelta(hours=6),
        close_time=T0 - timedelta(hours=1),
        status=SessionStatus.CLOSED,
    )


def halted_session() -> Session:
    return Session(
        venue_id=VENUE_ID,
        session_type=SessionType.NORMAL,
        open_time=T0 - timedelta(hours=1),
        close_time=T0 + timedelta(hours=5),
        status=SessionStatus.HALTED,
    )


# ---------------------------------------------------------------------------
# Quote fixture helpers
# ---------------------------------------------------------------------------


def fresh_quote(*, age_seconds: float = 0.0) -> Quote:
    """Quote received ``age_seconds`` before T0."""
    received = T0 - timedelta(seconds=age_seconds)
    return Quote(
        idempotency_key=f"NSE:9999",
        instrument_id=INST_ID,
        venue_id=VENUE_ID,
        timestamp=received,
        received_at=received,
        sequence_id=1,
        bid_price=Decimal("999"),
        bid_qty=500,
        ask_price=Decimal("1001"),
        ask_qty=500,
        last_trade_price=Decimal("1000"),
    )


# ---------------------------------------------------------------------------
# ParentOrder fixture helpers
# ---------------------------------------------------------------------------


def buy_order(
    *,
    qty: int | None = 100,
    notional: Decimal | None = None,
) -> ParentOrder:
    return ParentOrder(
        session_id=SESSION_ID,
        instrument_id=INST_ID,
        side=Side.BUY,
        target_qty=qty,
        target_notional=notional,
        algo="MARKET",
        created_at=T0,
        updated_at=T0,
    )


# ---------------------------------------------------------------------------
# Default context
# ---------------------------------------------------------------------------


def default_context(
    *,
    session: Session | None = None,
    quote: Quote | None = None,
    current_position: int = 0,
    portfolio_gross_exposure: Decimal = Decimal("0"),
    adv: int = 100_000,
    arrival_price: Decimal = Decimal("1000"),
) -> RiskContext:
    return RiskContext(
        session=session or open_session(),
        quote=quote or fresh_quote(),
        current_position=current_position,
        portfolio_gross_exposure=portfolio_gross_exposure,
        adv=adv,
        arrival_price=arrival_price,
    )


# ---------------------------------------------------------------------------
# Engine factory
# ---------------------------------------------------------------------------


def make_engine(
    config: RiskConfig | None = None,
    kill_switch: KillSwitch | None = None,
) -> RiskEngine:
    cfg = config or RiskConfig()
    return RiskEngine(config=cfg, kill_switch=kill_switch, now=_now)
