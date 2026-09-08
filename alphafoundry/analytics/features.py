"""Feature definitions, deterministic calculations, and versioned registry.

All formulas are purely mathematical, deterministic, and ML-free.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class FeatureDefinition:
    """Metadata describing a named, versioned feature."""

    name: str
    description: str
    lookback_bars: int = 1
    version: str = "1.0.0"


# ---------------------------------------------------------------------------
# Pure mathematical formulas
# ---------------------------------------------------------------------------


def compute_returns(prices: Sequence[float], lookback: int = 1) -> float:
    """Compute simple return over lookback periods: (P_t - P_{t-k}) / P_{t-k}.

    Returns 0.0 if there are insufficient data points or base price is <= 0.
    """
    if len(prices) <= lookback:
        return 0.0
    base_price = prices[-1 - lookback]
    current_price = prices[-1]
    if base_price <= 0:
        return 0.0
    return (current_price - base_price) / base_price


def compute_realised_volatility(prices: Sequence[float], lookback: int = 10) -> float:
    """Compute sample standard deviation of 1-period returns over lookback window.

    Returns 0.0 if insufficient data points (< 2 returns available).
    """
    if len(prices) < 2:
        return 0.0

    # Calculate 1-period returns for the window
    window_prices = prices[-(lookback + 1) :] if len(prices) > lookback + 1 else prices
    returns: list[float] = []
    for i in range(1, len(window_prices)):
        prev = window_prices[i - 1]
        curr = window_prices[i]
        if prev > 0:
            returns.append((curr - prev) / prev)

    if len(returns) < 2:
        return 0.0

    mean_ret = sum(returns) / len(returns)
    variance = sum((r - mean_ret) ** 2 for r in returns) / (len(returns) - 1)
    return math.sqrt(max(0.0, variance))


def compute_volume_ratio(volumes: Sequence[int | float], lookback: int = 10) -> float:
    """Compute ratio of current volume to average volume over lookback window: V_t / mean(V).

    Returns 1.0 if insufficient data or mean volume is 0.
    """
    if not volumes:
        return 1.0

    window = volumes[-lookback:] if len(volumes) >= lookback else volumes
    mean_vol = sum(window) / len(window)
    if mean_vol <= 0:
        return 1.0

    return float(volumes[-1]) / mean_vol


def compute_momentum(prices: Sequence[float], lookback: int = 10) -> float:
    """Compute price momentum over lookback periods: (P_t - P_{t-k}) / P_{t-k}.

    Returns 0.0 if insufficient data or base price <= 0.
    """
    return compute_returns(prices, lookback=lookback)


def compute_bid_ask_spread(bid_price: float, ask_price: float) -> float:
    """Compute relative bid-ask spread: (ask - bid) / mid.

    Returns 0.0 if mid price is <= 0 or ask < bid.
    """
    if bid_price <= 0 or ask_price <= 0 or ask_price < bid_price:
        return 0.0
    mid = (bid_price + ask_price) / 2.0
    if mid <= 0:
        return 0.0
    return (ask_price - bid_price) / mid


def compute_market_depth_liquidity(bid_qty: int | float, ask_qty: int | float) -> float:
    """Compute total visible quote liquidity: bid_qty + ask_qty."""
    return float(max(0, bid_qty) + max(0, ask_qty))


# ---------------------------------------------------------------------------
# Default feature definitions
# ---------------------------------------------------------------------------

DEFAULT_FEATURES: list[FeatureDefinition] = [
    FeatureDefinition(
        name="returns_1",
        description="1-bar simple price return (close-to-close)",
        lookback_bars=1,
        version="1.0.0",
    ),
    FeatureDefinition(
        name="returns_5",
        description="5-bar simple price return (close-to-close)",
        lookback_bars=5,
        version="1.0.0",
    ),
    FeatureDefinition(
        name="realised_vol_10",
        description="10-bar sample standard deviation of 1-bar returns",
        lookback_bars=10,
        version="1.0.0",
    ),
    FeatureDefinition(
        name="volume_ratio_10",
        description="Current bar volume divided by 10-bar moving average volume",
        lookback_bars=10,
        version="1.0.0",
    ),
    FeatureDefinition(
        name="momentum_10",
        description="10-bar price momentum / rate of change",
        lookback_bars=10,
        version="1.0.0",
    ),
    FeatureDefinition(
        name="bid_ask_spread",
        description="Relative bid-ask spread (ask - bid) / mid from quote",
        lookback_bars=1,
        version="1.0.0",
    ),
    FeatureDefinition(
        name="market_depth_liquidity",
        description="Total top-of-book depth (bid_qty + ask_qty) from quote",
        lookback_bars=1,
        version="1.0.0",
    ),
]


class FeatureRegistry:
    """Central registry of valid, versioned feature definitions."""

    def __init__(self, features: Sequence[FeatureDefinition] | None = None) -> None:
        self._registry: dict[str, FeatureDefinition] = {}
        if features is None:
            for feat in DEFAULT_FEATURES:
                self.register(feat, allow_overwrite=True)
        else:
            for feat in features:
                self.register(feat, allow_overwrite=True)

    def register(self, feature_def: FeatureDefinition, allow_overwrite: bool = False) -> None:
        """Register a feature definition. Raises ValueError if already registered unless allow_overwrite=True."""
        if feature_def.name in self._registry and not allow_overwrite:
            raise ValueError(f"Feature '{feature_def.name}' is already registered.")
        self._registry[feature_def.name] = feature_def

    def unregister(self, name: str) -> None:
        """Unregister a feature definition by name."""
        self._registry.pop(name, None)

    def get(self, name: str) -> FeatureDefinition:
        """Return the feature definition by name, or raise KeyError."""
        if name not in self._registry:
            raise KeyError(f"Feature '{name}' is not registered.")
        return self._registry[name]

    def is_registered(self, name: str) -> bool:
        """Return True if the feature name is registered."""
        return name in self._registry

    def list_features(self) -> list[FeatureDefinition]:
        """Return all registered feature definitions."""
        return list(self._registry.values())

    def validate_features(self, features: dict[str, float]) -> bool:
        """Validate that all keys in the feature dictionary are registered.

        Raises ValueError if any unregistered feature name is encountered.
        Returns True if all features are valid.
        """
        unregistered = [name for name in features if name not in self._registry]
        if unregistered:
            raise ValueError(
                f"Unregistered feature(s): {unregistered}. "
                f"All features must be registered in FeatureRegistry."
            )
        return True
