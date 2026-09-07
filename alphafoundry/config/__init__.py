"""Configuration for ALPHAFOUNDRY.

Uses a plain dataclass (no extra dependencies).  Settings can be created
programmatically or loaded from a TOML file; both paths produce the same
frozen object so tests can override any field without touching files.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class SyntheticAdapterConfig:
    """Configuration for the SyntheticAdapter (Phase 01)."""

    # RNG seed — identical seed + config → identical output.
    seed: int = 42

    # Number of trading days of daily bars to generate per instrument.
    num_days: int = 252

    # Starting reference price for each generated instrument (INR).
    base_price: float = 1000.0

    # Daily return volatility (annualised σ → daily σ = annual_vol / sqrt(252)).
    annual_vol: float = 0.25

    # Intra-day interval for quote generation ('1m', '5m').
    quote_interval: str = "1m"

    # Average bid-ask spread as a fraction of mid-price.
    spread_fraction: float = 0.0005

    # Average volume per bar (lot units).
    avg_volume: int = 10_000


@dataclass(frozen=True)
class AppConfig:
    """Top-level application configuration."""

    # Identifies the configuration for audit / reproducibility.
    config_version: str = "0.1.0"

    # Exchange timezone used for session scheduling.
    exchange_timezone: str = "Asia/Kolkata"

    synthetic_adapter: SyntheticAdapterConfig = field(default_factory=SyntheticAdapterConfig)


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def load_config(path: Path | None = None) -> AppConfig:
    """Return an AppConfig from *path* (TOML) or default values.

    The TOML file may contain a ``[synthetic_adapter]`` table whose keys
    override SyntheticAdapterConfig defaults.  Unknown keys are ignored.
    """
    if path is None or not path.exists():
        return AppConfig()

    with path.open("rb") as fh:
        raw = tomllib.load(fh)

    syn_raw = raw.get("synthetic_adapter", {})
    syn_cfg = SyntheticAdapterConfig(
        seed=int(syn_raw.get("seed", SyntheticAdapterConfig.seed)),
        num_days=int(syn_raw.get("num_days", SyntheticAdapterConfig.num_days)),
        base_price=float(syn_raw.get("base_price", SyntheticAdapterConfig.base_price)),
        annual_vol=float(syn_raw.get("annual_vol", SyntheticAdapterConfig.annual_vol)),
        quote_interval=str(syn_raw.get("quote_interval", SyntheticAdapterConfig.quote_interval)),
        spread_fraction=float(
            syn_raw.get("spread_fraction", SyntheticAdapterConfig.spread_fraction)
        ),
        avg_volume=int(syn_raw.get("avg_volume", SyntheticAdapterConfig.avg_volume)),
    )

    app_raw = raw.get("app", {})
    config_version = str(
        app_raw.get("config_version") or raw.get("config_version") or AppConfig.config_version
    )
    exchange_timezone = str(
        app_raw.get("exchange_timezone")
        or raw.get("exchange_timezone")
        or AppConfig.exchange_timezone
    )

    return AppConfig(
        config_version=config_version,
        exchange_timezone=exchange_timezone,
        synthetic_adapter=syn_cfg,
    )
