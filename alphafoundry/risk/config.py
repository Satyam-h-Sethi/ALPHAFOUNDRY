"""Risk engine configuration — limits, thresholds, participation cap."""

from __future__ import annotations

from decimal import Decimal

from alphafoundry.domain.risk import PositionLimit, RiskConfig

__all__ = ["PositionLimit", "RiskConfig", "default_risk_config"]


def default_risk_config() -> RiskConfig:
    """Return a permissive RiskConfig suitable for tests and development.

    All dollar limits are in INR.  Production deployments should supply
    explicit values rather than relying on this default.
    """
    return RiskConfig(
        position_limits=[],
        max_order_qty=None,
        max_order_notional=None,
        max_adv_participation=0.10,
        max_quote_age_seconds=60.0,
        kill_switch_enabled=False,
    )
