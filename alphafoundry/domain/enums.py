"""Enumeration types used across the domain model."""

from enum import StrEnum


class InstrumentType(StrEnum):
    EQ = "EQ"  # equity share
    FUT = "FUT"  # futures contract
    OPT_CE = "OPT_CE"  # call option
    OPT_PE = "OPT_PE"  # put option
    IDX = "IDX"  # index (non-tradable reference)
    ETF = "ETF"  # exchange-traded fund


class SessionType(StrEnum):
    PRE_OPEN = "PRE_OPEN"
    NORMAL = "NORMAL"
    CLOSING = "CLOSING"
    POST_CLOSE = "POST_CLOSE"
    MUHURAT = "MUHURAT"


class SessionStatus(StrEnum):
    SCHEDULED = "SCHEDULED"
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    HALTED = "HALTED"


class SimulationSessionStatus(StrEnum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    ABORTED = "ABORTED"


class TradeSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    UNKNOWN = "UNKNOWN"


class Direction(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"
    NEUTRAL = "NEUTRAL"


class Side(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(StrEnum):
    PENDING_RISK = "PENDING_RISK"
    REJECTED = "REJECTED"
    APPROVED = "APPROVED"
    ACTIVE = "ACTIVE"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    # child-order specific
    PENDING = "PENDING"
    EXPIRED = "EXPIRED"


class OrderType(StrEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    IOC = "IOC"


class Urgency(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class BenchmarkType(StrEnum):
    ARRIVAL = "ARRIVAL"
    VWAP = "VWAP"
    TWAP = "TWAP"
    CLOSE = "CLOSE"


class RegimeType(StrEnum):
    TRENDING = "TRENDING"
    MEAN_REVERTING = "MEAN_REVERTING"
    HIGH_VOL = "HIGH_VOL"
    LOW_VOL = "LOW_VOL"
    UNKNOWN = "UNKNOWN"


class AnomalySeverity(StrEnum):
    INFO = "INFO"
    WARN = "WARN"
    ALERT = "ALERT"


class SubjectType(StrEnum):
    SIGNAL = "SIGNAL"
    FILL = "FILL"
    RISK_DECISION = "RISK_DECISION"
    TCA = "TCA"
    SESSION = "SESSION"
