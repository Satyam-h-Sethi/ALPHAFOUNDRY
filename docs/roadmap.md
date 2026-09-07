# Roadmap

Phases are sequential by default; later phases may run in parallel once the foundation is stable. Each phase produces a defined artefact set and ends with a review gate.

---

## Phase 00 — Architecture (current)

**Goal:** Establish the design foundation before any code is written.

**Deliverables:**
- `README.md`
- `docs/architecture.md`
- `docs/domain-model.md`
- `docs/data-model.md`
- `docs/execution-model.md`
- `docs/roadmap.md`

**Exit criteria:** Design documents reviewed and committed; no runnable code.

---

## Phase 01 — Foundation

**Goal:** Runnable project skeleton with CI and synthetic data.

**Deliverables:**
- Python package structure (`alphafoundry/`) with module stubs for every component
- Typed interfaces (dataclasses / pydantic models) for every domain object
- `SyntheticAdapter`: deterministic OHLC + quote generator seeded from config
- Unit-test harness; initial test suite covering domain object validation
- CI pipeline (lint, type-check, test)
- Developer setup guide

**Decisions resolved here:**
- Python version and dependency manager
- Serialisation library (pydantic vs dataclasses + marshmallow)
- Configuration approach (YAML / TOML / env)

---

## Phase 02 — Data Pipeline

**Goal:** End-to-end ingest from adapter through to validated, deduplicated, persisted market data.

**Deliverables:**
- Ingestion loop consuming `SyntheticAdapter`
- Normaliser, Validator, Deduplicator, Staleness detector — all with full unit tests
- Market-data store (technology chosen in this phase: timescale, DuckDB, or Parquet files — decision based on write throughput benchmarks against synthetic load)
- `CsvFileAdapter` for replaying historical data files
- Ingest audit log
- Integration tests: full pipeline round-trip on synthetic data

**Decisions resolved here:**
- Persistence technology for time-series (benchmark first)
- In-process vs external message bus (start in-process; extract if needed)

---

## Phase 03 — Analytics

**Goal:** Feature computation, signal generation, and cross-sectional ranking on ingested data.

**Deliverables:**
- Feature registry with versioned feature definitions
- Feature engine computing initial feature set (returns, volatility, volume ratios, momentum)
- Signal engine with configurable weighted linear combiner (not ML; deterministic formula)
- Regime detector using volatility + trend metrics
- Ranking engine with universe-filter support
- Full lineage recorded on every signal
- Backtest-compatible replay mode: process historical data window and produce signal history

---

## Phase 04 — Risk Engine

**Goal:** Pre-trade risk gate with all rules from `execution-model.md §9`.

**Deliverables:**
- Risk config schema (position limits, order limits, participation limits, stale-data threshold)
- All 7 risk rules implemented and unit-tested
- Kill-switch API
- Risk decision stored with full violation detail
- Integration tests: risk engine correctly blocks/approves orders given fixture data

---

## Phase 05 — Execution Simulation

**Goal:** End-to-end order lifecycle from parent order to filled + TCA.

**Deliverables:**
- All five slicing algorithms (TWAP, VWAP, POV, IS, MARKET)
- Fill simulator with linear market-impact model
- Partial-fill handling and residual re-queuing
- Position tracker
- Simulation session management
- TCA engine computing all metrics from `execution-model.md §7`
- Integration tests: full session with synthetic data, assertions on fills and TCA

---

## Phase 06 — Research Harness

**Goal:** A programmable research workflow: configure a session, run it, inspect results.

**Deliverables:**
- Python API for composing and running simulation sessions
- Jupyter-compatible result objects (DataFrames for fills, TCA, signals)
- Scenario comparison: run multiple sessions with different algo configs; diff TCA results
- Research store query API

---

## Phase 07 — AI Research Assistant

**Goal:** Natural-language explanation and anomaly detection over platform outputs.

**Deliverables:**
- `IResearchAssistant` implementation backed by injected LLM client
- `explain_signal`, `explain_fill`, `explain_risk_decision`, `summarise_session`
- Anomaly detector: statistical z-score baseline; AI narrates flagged anomalies
- AI artefact schemas written to research store
- Guardrails verified: assistant cannot write to signal/order/fill stores

**Decisions resolved here:**
- LLM provider and model (adapter pattern means this is swappable)
- Prompt templating approach

---

## Phase 08 — Research UI

**Goal:** Read-only dashboard for exploring signals, fills, and TCA results.

**Deliverables:**
- Web application (technology chosen in this phase)
- Signal explorer: filter by instrument, date, regime
- Execution explorer: parent orders, child orders, fill chart, TCA table
- AI explanation panel alongside each view
- No write operations in the UI; all mutations go through the Python API

---

## Deferred (no phase assigned)

These are out of scope until explicitly scheduled:

| Item | Why deferred |
|------|-------------|
| Live market-data connectors | Requires licensed data agreement and vendor API access |
| Live order routing | Out of scope by design (paper trading only) |
| ML-based signal models | Requires training infrastructure; deterministic baseline first |
| Kubernetes / Terraform | Premature until deployment target is confirmed |
| Multi-user auth | Single-researcher tool initially |
| Strategy library | Strategies are composed by researchers in Phase 06; no pre-built library planned |

---

## Decision log

Decisions deferred to later phases are tracked here to avoid revisiting them prematurely.

| Decision | Phase | Options | Constraint |
|----------|-------|---------|------------|
| Time-series store engine | 02 | DuckDB, TimescaleDB, Parquet files | Benchmark write throughput at synthetic load before choosing |
| Message bus | 02 | In-process dispatcher, Redis Streams, Kafka | Start in-process; extract only if throughput requires it |
| LLM provider | 07 | Claude API, OpenAI API, local model | Adapter pattern; no lock-in |
| UI framework | 08 | React, Streamlit, Dash | Deferred; depends on team familiarity |
| ML signal models | TBD | sklearn, XGBoost, PyTorch | Only after deterministic baseline is validated |
