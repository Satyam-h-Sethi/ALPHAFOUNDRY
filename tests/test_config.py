"""Tests for config loading and dataclasses."""

from pathlib import Path

from alphafoundry.config import AppConfig, SyntheticAdapterConfig, load_config


def test_default_config():
    cfg = load_config(None)
    assert isinstance(cfg, AppConfig)
    assert cfg.config_version == "0.1.0"
    assert cfg.exchange_timezone == "Asia/Kolkata"
    assert isinstance(cfg.synthetic_adapter, SyntheticAdapterConfig)
    assert cfg.synthetic_adapter.seed == 42
    assert cfg.synthetic_adapter.num_days == 252


def test_load_from_toml(tmp_path: Path):
    toml_file = tmp_path / "config.toml"
    toml_file.write_text(
        """
[app]
config_version = "0.2.0"
exchange_timezone = "UTC"

[synthetic_adapter]
seed = 999
num_days = 50
base_price = 500.0
annual_vol = 0.30
quote_interval = "5m"
spread_fraction = 0.001
avg_volume = 20000
"""
    )
    cfg = load_config(toml_file)
    assert cfg.config_version == "0.2.0"
    assert cfg.exchange_timezone == "UTC"
    assert cfg.synthetic_adapter.seed == 999
    assert cfg.synthetic_adapter.num_days == 50
    assert cfg.synthetic_adapter.base_price == 500.0
    assert cfg.synthetic_adapter.annual_vol == 0.30
    assert cfg.synthetic_adapter.quote_interval == "5m"
    assert cfg.synthetic_adapter.spread_fraction == 0.001
    assert cfg.synthetic_adapter.avg_volume == 20000
