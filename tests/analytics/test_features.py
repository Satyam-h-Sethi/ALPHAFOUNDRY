"""Unit tests for Feature Definitions, Math Functions, and Feature Registry."""

from __future__ import annotations

import pytest

from alphafoundry.analytics.features import (
    FeatureDefinition,
    FeatureRegistry,
    compute_bid_ask_spread,
    compute_market_depth_liquidity,
    compute_momentum,
    compute_realised_volatility,
    compute_returns,
    compute_volume_ratio,
)


def test_compute_returns() -> None:
    # Insufficient data
    assert compute_returns([]) == 0.0
    assert compute_returns([100.0]) == 0.0

    # Valid returns
    prices = [100.0, 105.0]
    assert pytest.approx(compute_returns(prices, lookback=1), rel=1e-5) == 0.05

    prices_5 = [100.0, 101.0, 102.0, 103.0, 104.0, 110.0]
    assert pytest.approx(compute_returns(prices_5, lookback=5), rel=1e-5) == 0.10

    # Zero divisor guard
    assert compute_returns([0.0, 100.0]) == 0.0


def test_compute_realised_volatility() -> None:
    # Insufficient data
    assert compute_realised_volatility([]) == 0.0
    assert compute_realised_volatility([100.0]) == 0.0
    assert compute_realised_volatility([100.0, 105.0]) == 0.0

    # Constant prices -> zero volatility
    assert compute_realised_volatility([100.0] * 10) == 0.0

    # Fluctuating prices
    prices = [100.0, 102.0, 99.0, 103.0, 101.0, 104.0, 98.0, 102.0]
    vol = compute_realised_volatility(prices, lookback=5)
    assert vol > 0.0


def test_compute_volume_ratio() -> None:
    assert compute_volume_ratio([]) == 1.0
    assert compute_volume_ratio([100]) == 1.0

    # 10 bars: 9 of 100, 1 of 200 -> mean = 110 -> 200/110 = 1.81818
    volumes = [100] * 9 + [200]
    assert pytest.approx(compute_volume_ratio(volumes, lookback=10), rel=1e-3) == (200.0 / 110.0)


def test_compute_momentum() -> None:
    assert compute_momentum([]) == 0.0
    assert compute_momentum([100.0]) == 0.0

    prices = [100.0, 102.0, 104.0, 106.0]
    # Price return over lookback=3: (106 - 100) / 100 = 0.06
    assert pytest.approx(compute_momentum(prices, lookback=3), rel=1e-5) == 0.06


def test_compute_bid_ask_spread() -> None:
    # (102 - 100) / 101 = 2 / 101 = ~0.01980198
    assert pytest.approx(compute_bid_ask_spread(100.0, 102.0), rel=1e-4) == (2.0 / 101.0)
    assert compute_bid_ask_spread(100.0, 99.0) == 0.0  # Inverted spread guard


def test_compute_market_depth_liquidity() -> None:
    assert compute_market_depth_liquidity(100, 200) == 300.0


def test_feature_registry_defaults() -> None:
    reg = FeatureRegistry()
    assert reg.is_registered("returns_1")
    assert reg.is_registered("returns_5")
    assert reg.is_registered("realised_vol_10")
    assert reg.is_registered("volume_ratio_10")
    assert reg.is_registered("momentum_10")
    assert reg.is_registered("bid_ask_spread")
    assert reg.is_registered("market_depth_liquidity")
    assert not reg.is_registered("non_existent_feature")


def test_feature_registry_register_and_unregister() -> None:
    reg = FeatureRegistry()
    custom_def = FeatureDefinition(
        name="custom_feat",
        description="Custom feature for testing",
        lookback_bars=2,
        version="1.0.0",
    )
    reg.register(custom_def)
    assert reg.is_registered("custom_feat")
    assert reg.get("custom_feat").description == "Custom feature for testing"

    # Duplicate registration raises ValueError
    with pytest.raises(ValueError, match="already registered"):
        reg.register(custom_def)

    # Unregister
    reg.unregister("custom_feat")
    assert not reg.is_registered("custom_feat")


def test_feature_registry_validation() -> None:
    reg = FeatureRegistry()
    valid_features = {
        "returns_1": 0.02,
        "momentum_10": 1.5,
    }
    assert reg.validate_features(valid_features) is True

    invalid_features = {
        "returns_1": 0.02,
        "unregistered_alpha_feature": 99.9,
    }
    with pytest.raises(ValueError, match="Unregistered feature.*unregistered_alpha_feature"):
        reg.validate_features(invalid_features)
