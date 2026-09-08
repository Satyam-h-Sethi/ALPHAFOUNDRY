"""Feature Engine — computes versioned FeatureVectors from point-in-time market data."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from alphafoundry.analytics.config import AnalyticsConfig
from alphafoundry.analytics.features import (
    FeatureRegistry,
    compute_bid_ask_spread,
    compute_market_depth_liquidity,
    compute_momentum,
    compute_realised_volatility,
    compute_returns,
    compute_volume_ratio,
)
from alphafoundry.domain import FeatureVector, OHLCBar, Quote


class FeatureEngine:
    """Computes deterministic numerical features from validated stored market data."""

    def __init__(
        self,
        config: AnalyticsConfig | None = None,
        registry: FeatureRegistry | None = None,
    ) -> None:
        self._config = config or AnalyticsConfig()
        self._registry = registry or FeatureRegistry()

    @property
    def config(self) -> AnalyticsConfig:
        return self._config

    @property
    def registry(self) -> FeatureRegistry:
        return self._registry

    def compute_features(
        self,
        instrument_id: UUID,
        as_of: datetime,
        bars: Sequence[OHLCBar],
        quote: Quote | None = None,
    ) -> FeatureVector:
        """Compute a FeatureVector for an instrument as-of a specific point in time.

        Strictly enforces point-in-time boundaries (zero lookahead):
          - Only bars with `bar_close <= as_of` are considered.
          - Only quotes with `timestamp <= as_of` are considered.
        """
        as_of_utc = as_of if as_of.tzinfo is not None else as_of.replace(tzinfo=UTC)

        # 1. Point-in-time filtering for OHLC bars
        valid_bars = [
            b for b in bars if (b.bar_close if b.bar_close.tzinfo else b.bar_close.replace(tzinfo=UTC)) <= as_of_utc
        ]
        # Sort chronologically by bar_close
        valid_bars.sort(key=lambda b: b.bar_close)

        prices = [float(b.close) for b in valid_bars]
        volumes = [b.volume for b in valid_bars]

        # 2. Point-in-time filtering for Quote
        valid_quote: Quote | None = None
        if quote is not None:
            q_ts = quote.timestamp if quote.timestamp.tzinfo else quote.timestamp.replace(tzinfo=UTC)
            if q_ts <= as_of_utc:
                valid_quote = quote

        # 3. Compute registered features
        features: dict[str, float] = {}

        if self._registry.is_registered("returns_1"):
            features["returns_1"] = compute_returns(prices, lookback=self._config.returns_lookback)

        if self._registry.is_registered("returns_5"):
            features["returns_5"] = compute_returns(prices, lookback=self._config.returns_5_lookback)

        if self._registry.is_registered("realised_vol_10"):
            features["realised_vol_10"] = compute_realised_volatility(
                prices, lookback=self._config.volatility_lookback
            )

        if self._registry.is_registered("volume_ratio_10"):
            features["volume_ratio_10"] = compute_volume_ratio(
                volumes, lookback=self._config.volume_lookback
            )

        if self._registry.is_registered("momentum_10"):
            features["momentum_10"] = compute_momentum(
                prices, lookback=self._config.momentum_lookback
            )

        if self._registry.is_registered("bid_ask_spread"):
            if valid_quote is not None:
                features["bid_ask_spread"] = compute_bid_ask_spread(
                    float(valid_quote.bid_price), float(valid_quote.ask_price)
                )
            else:
                features["bid_ask_spread"] = 0.0

        if self._registry.is_registered("market_depth_liquidity"):
            if valid_quote is not None:
                features["market_depth_liquidity"] = compute_market_depth_liquidity(
                    valid_quote.bid_qty, valid_quote.ask_qty
                )
            else:
                features["market_depth_liquidity"] = 0.0

        # Validate against registry
        self._registry.validate_features(features)

        return FeatureVector(
            instrument_id=instrument_id,
            as_of=as_of_utc,
            computed_at=datetime.now(UTC),
            feature_version=self._config.feature_version,
            features=features,
        )
