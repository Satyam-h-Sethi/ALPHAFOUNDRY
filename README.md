# ALPHAFOUNDRY

**Market-intelligence and execution-research platform for Indian equities and derivatives.**

> Research / paper-trading only. No live brokerage execution. No scraping or redistribution of licensed market data.

---

## What it is

ALPHAFOUNDRY is a modular, auditable pipeline for:

- Ingesting and normalising market data (synthetic by default; real data plugs in via provider adapters)
- Generating features, signals, and instrument rankings
- Simulating order execution with realistic market-impact and slippage models
- Measuring execution quality (TCA)
- Explaining signals, anomalies, and execution outcomes through an AI research assistant

## What it is NOT

- A live trading system
- A brokerage integration
- A NSE/BSE data redistributor
- A black-box strategy factory

## Core principles

| Principle | Meaning |
|-----------|---------|
| **Deterministic logic** | Signal generation, risk checks, and order simulation produce identical output for identical input. No hidden randomness. |
| **Auditability** | Every decision—signal, risk gate, fill—carries a lineage record linking it to the inputs that produced it. |
| **AI assists, never decides** | The AI layer explains and summarises; it cannot generate signals, override risk rules, or alter order state. |
| **Data sovereignty** | Licensed market data never leaves the owner's environment. The platform handles synthetic data out of the box; adapters let owners plug in their own feeds. |

## Repository layout

```
ALPHAFOUNDRY/
├── README.md
├── DEVELOPMENT.md          — developer setup and environment guide
├── pyproject.toml          — project metadata, dependencies, tool configurations
├── .github/
│   └── workflows/ci.yml    — CI workflow (lint, type-check, pytest)
├── docs/
│   ├── architecture.md     — system overview, component boundaries, data flow
│   ├── domain-model.md     — core concepts: instrument, quote, order, fill …
│   ├── data-model.md       — field-level schemas and storage contracts
│   ├── execution-model.md  — order lifecycle, slicing, simulation, TCA
│   └── roadmap.md          — phases and delivery milestones
├── alphafoundry/           — core package
│   ├── adapters/           — data provider adapters (IMarketDataAdapter, SyntheticAdapter)
│   ├── ai/                 — AI assistant stubs (explainer, summariser)
│   ├── analytics/          — analytics stubs (features, signals, rankings)
│   ├── config/             — configuration loading and dataclasses
│   ├── domain/             — immutable Pydantic v2 domain models
│   ├── execution/          — execution simulation stubs
│   ├── pipeline/           — data pipeline stubs
│   ├── risk/               — risk engine stubs
│   └── tca/                — transaction cost analysis stubs
└── tests/                  — comprehensive test suite
    ├── adapters/           — synthetic generator determinism & streaming tests
    ├── domain/             — domain model validation and immutability tests
    └── test_config.py      — configuration loading tests
```

## Quickstart

### Installation

```bash
# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\Activate.ps1

# Install package in editable mode with development dependencies
pip install -e ".[dev]"
```

### Deterministic Synthetic Data Generation

```python
from alphafoundry.adapters.synthetic import SyntheticAdapter
from alphafoundry.config import SyntheticAdapterConfig

# Identical seed + config produces bit-exact reproducible results
cfg = SyntheticAdapterConfig(seed=42, num_days=252, base_price=1000.0)
adapter = SyntheticAdapter(cfg)

instruments = adapter.get_instruments()
print(f"Loaded {len(instruments)} instruments: {[i.symbol for i in instruments]}")

# Fetch OHLC daily bars
bars = adapter.get_ohlc(
    instrument_id=instruments[0].instrument_id,
    from_dt=instruments[0].created_at,
    to_dt=instruments[0].created_at,
    freq="1d",
)
```

### Running Checks & Tests

```bash
# Code formatting check
ruff format --check .

# Linting
ruff check .

# Strict type checking
mypy alphafoundry tests

# Unit test suite with coverage
pytest --cov=alphafoundry
```

## Roadmap & Status

| Phase | Status | Scope |
|-------|--------|-------|
| **00 – Architecture** | Completed | Design documents, domain specifications, data contracts |
| **01 – Foundation** | Completed | Package scaffolding, immutable domain models, SyntheticAdapter, CI pipeline |
| **02 – Data Pipeline** | Planned | Ingestion → normalisation → validation → storage |
| **03 – Analytics** | Planned | Feature engine → signal engine → ranking |
| **04 – Risk** | Planned | Pre-trade risk engine, kill-switch |
| **05 – Execution Simulation** | Planned | Parent/child orders, fill simulation, market-impact |
| **06 – TCA** | Planned | Benchmark computation, slippage attribution |
| **07 – AI Layer** | Planned | Research assistant integration |
| **08 – Research UI** | Planned | Read-only dashboard |
