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
└── docs/
    ├── architecture.md     — system overview, component boundaries, data flow
    ├── domain-model.md     — core concepts: instrument, quote, order, fill …
    ├── data-model.md       — field-level schemas and storage contracts
    ├── execution-model.md  — order lifecycle, slicing, simulation, TCA
    └── roadmap.md          — phases and delivery milestones
```

## Phases

| Phase | Scope |
|-------|-------|
| **00 – Architecture** | Design documents (this commit) |
| **01 – Foundation** | Project scaffolding, CI skeleton, synthetic data generator |
| **02 – Data Pipeline** | Ingestion → normalisation → validation → storage |
| **03 – Analytics** | Feature engine → signal engine → ranking |
| **04 – Risk** | Pre-trade risk engine, kill-switch |
| **05 – Execution Simulation** | Parent/child orders, fill simulation, market-impact |
| **06 – TCA** | Benchmark computation, slippage attribution |
| **07 – AI Layer** | Research assistant integration |
| **08 – Research UI** | Read-only dashboard |

---

*Phase 0 — Architecture only. No runnable code yet.*
