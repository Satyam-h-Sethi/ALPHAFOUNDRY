"""Validator — enforces all Phase 02 data-quality rules.

Rules (from data-model.md §8):

    Rule                  Check
    ──────────────────    ──────────────────────────────────────────────
    Price sanity          0 < price <= 1_000_000 INR
    Spread sanity         ask_price >= bid_price
    Quantity sanity       qty > 0
    Timestamp future-gate timestamp <= received_at + 5 s
    Timestamp past-gate   timestamp >= session_open - 5 min
    Lot-size conformance  qty % lot_size == 0
    Tick conformance      (price / tick_size) is integer within tolerance

Any failure → VALIDATION_FAILED; event must not enter primary storage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from uuid import UUID

from alphafoundry.domain import OHLCBar, Quote, Trade
from alphafoundry.domain.instruments import Instrument
from alphafoundry.pipeline.config import PipelineConfig

_TICK_TOLERANCE = Decimal("0.001")  # fractional tolerance for tick conformance
_MAX_PRICE = Decimal("1000000")
_MIN_PRICE = Decimal("0")


@dataclass
class ValidationResult:
    """Outcome of a single validation pass.

    Attributes
    ----------
    is_valid:
        True iff every rule passed.
    failures:
        List of human-readable failure descriptions (empty when valid).
    """

    is_valid: bool = True
    failures: list[str] = field(default_factory=list)

    def fail(self, reason: str) -> None:
        self.is_valid = False
        self.failures.append(reason)

    @property
    def error_detail(self) -> str | None:
        return "; ".join(self.failures) if self.failures else None


class Validator:
    """Stateless validation of normalised market-data events.

    Instruments are injected so the validator can check lot-size and
    tick-size without coupling to any particular data source.
    """

    def __init__(
        self,
        cfg: PipelineConfig,
        instruments: dict[UUID, Instrument] | None = None,
    ) -> None:
        self._cfg = cfg
        self._instruments: dict[UUID, Instrument] = instruments or {}
        self._max_price = Decimal(str(cfg.max_price_inr))
        self._future_gate = timedelta(seconds=cfg.future_gate_seconds)
        self._past_gate = timedelta(seconds=cfg.past_gate_seconds)

    def register_instrument(self, instr: Instrument) -> None:
        self._instruments[instr.instrument_id] = instr

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def validate_quote(self, quote: Quote) -> ValidationResult:
        result = ValidationResult()
        self._check_price(quote.bid_price, "bid_price", result)
        self._check_price(quote.ask_price, "ask_price", result)
        self._check_spread(quote.bid_price, quote.ask_price, result)
        self._check_qty(quote.bid_qty, "bid_qty", result)
        self._check_qty(quote.ask_qty, "ask_qty", result)
        self._check_timestamps(quote.timestamp, quote.received_at, result)
        # Lot-size and tick checks require instrument context.
        instr = self._instruments.get(quote.instrument_id)
        if instr is not None:
            self._check_tick(quote.bid_price, instr.tick_size, "bid_price", result)
            self._check_tick(quote.ask_price, instr.tick_size, "ask_price", result)
        return result

    def validate_trade(self, trade: Trade) -> ValidationResult:
        result = ValidationResult()
        self._check_price(trade.price, "price", result)
        self._check_qty(trade.qty, "qty", result)
        self._check_timestamps(trade.timestamp, trade.received_at, result)
        instr = self._instruments.get(trade.instrument_id)
        if instr is not None:
            self._check_tick(trade.price, instr.tick_size, "price", result)
            self._check_lot(trade.qty, instr.lot_size, result)
        return result

    def validate_bar(self, bar: OHLCBar) -> ValidationResult:
        result = ValidationResult()
        for name, val in [
            ("open", bar.open),
            ("high", bar.high),
            ("low", bar.low),
            ("close", bar.close),
        ]:
            self._check_price(val, name, result)
        self._check_qty(bar.volume, "volume", result)
        instr = self._instruments.get(bar.instrument_id)
        if instr is not None:
            self._check_tick(bar.close, instr.tick_size, "close", result)
        return result

    # ------------------------------------------------------------------
    # Rule implementations
    # ------------------------------------------------------------------

    def _check_price(self, price: Decimal, field: str, result: ValidationResult) -> None:
        if price <= _MIN_PRICE or price > self._max_price:
            result.fail(f"price_sanity: {field}={price} must be in (0, {self._max_price}]")

    def _check_spread(self, bid: Decimal, ask: Decimal, result: ValidationResult) -> None:
        if ask < bid:
            result.fail(f"spread_sanity: ask={ask} < bid={bid}")

    def _check_qty(self, qty: int, field: str, result: ValidationResult) -> None:
        if qty <= 0:
            result.fail(f"quantity_sanity: {field}={qty} must be > 0")

    def _check_timestamps(
        self,
        timestamp: datetime,
        received_at: datetime,
        result: ValidationResult,
    ) -> None:
        # Normalise to UTC for comparison
        ts = timestamp if timestamp.tzinfo is not None else timestamp.replace(tzinfo=UTC)
        ra = received_at if received_at.tzinfo is not None else received_at.replace(tzinfo=UTC)
        if ts > ra + self._future_gate:
            result.fail(
                f"timestamp_future_gate: event timestamp {ts} is more than "
                f"{self._cfg.future_gate_seconds}s ahead of received_at {ra}"
            )
        # Past gate: compare against estimated session open on the same day.
        session_open = ts.replace(
            hour=self._cfg.session_open_utc_hour,
            minute=self._cfg.session_open_utc_minute,
            second=0,
            microsecond=0,
        )
        earliest = session_open - self._past_gate
        if ts < earliest:
            result.fail(
                f"timestamp_past_gate: event timestamp {ts} is before earliest allowed {earliest}"
            )

    def _check_lot(self, qty: int, lot_size: int, result: ValidationResult) -> None:
        if lot_size > 1 and qty % lot_size != 0:
            result.fail(f"lot_size_conformance: qty={qty} is not a multiple of lot_size={lot_size}")

    def _check_tick(
        self,
        price: Decimal,
        tick_size: Decimal,
        field: str,
        result: ValidationResult,
    ) -> None:
        try:
            ratio = price / tick_size
            # Fraction away from the nearest whole number
            remainder = abs(ratio - ratio.to_integral_value())
            if remainder > _TICK_TOLERANCE:
                result.fail(
                    f"tick_conformance: {field}={price} is not a multiple of "
                    f"tick_size={tick_size} (remainder={remainder})"
                )
        except InvalidOperation:
            result.fail(f"tick_conformance: could not evaluate {field}={price} / {tick_size}")
