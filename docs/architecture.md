# Architecture

## 1. Design goals

1. **Separation of concerns** — each layer has a single job and a typed interface; layers never reach across.
2. **Determinism** — given the same inputs, any component produces the same outputs; randomness is seeded and logged.
3. **Pluggability** — market-data providers, persistence backends, and AI models are injected through adapters; the core knows nothing about concrete implementations.
4. **Fail-safe defaults** — missing data, staleness, and validation failures cause rejection, not silent degradation.

---

## 2. System context

```
┌─────────────────────────────────────────────────────────────────┐
│                        ALPHAFOUNDRY                             │
│                                                                 │
│  [Market Data     ]   [Synthetic    ]   [Historical    ]        │
│  [Provider Adapter]   [Data Gen     ]   [Replay        ]        │
│         │                  │                  │                 │
│         └──────────────────┴──────────────────┘                 │
│                            │                                    │
│                   [Data Pipeline]                               │
│              ingest → normalise → validate                      │
│              deduplicate → store                                │
│                            │                                    │
│               ┌────────────┴────────────┐                       │
│               │                         │                       │
│       [Feature Engine]          [Market State]                  │
│               │                         │                       │
│       [Signal Engine]           [Regime Detector]               │
│               │                         │                       │
│           [Ranking]                     │                       │
│               └────────────┬────────────┘                       │
│                            │                                    │
│                    [Risk Engine]                                 │
│                            │                                    │
│                  [Execution Simulator]                          │
│             parent order → slicing → fills                      │
│                            │                                    │
│                    [TCA Engine]                                  │
│                            │                                    │
│              [AI Research Assistant]                             │
│         (read-only: explain, summarise, annotate)               │
│                            │                                    │
│                   [Research Store]                              │
│           (audit log + results persistence)                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Component inventory

### 3.1 Market Data Provider Adapter

**Job:** translate an external data source into the platform's canonical `MarketDataEvent`.

- Interface: `IMarketDataAdapter`
  - `stream_quotes() → AsyncIterator[QuoteEvent]`
  - `stream_trades() → AsyncIterator[TradeEvent]`
  - `get_ohlc(instrument, from, to, freq) → List[OHLCBar]`
  - `get_instruments() → List[Instrument]`
- Implementations (all concrete, none built in Phase 0):
  - `SyntheticAdapter` — deterministic random-walk generator (Phase 1)
  - `CsvFileAdapter` — CSV replay for backtesting
  - `RealTimeAdapter` — placeholder for legitimately licensed feed (Phase N)

**Why this boundary:** keeps all licensed-data handling outside the core. Only the adapter ever touches raw vendor data.

---

### 3.2 Data Pipeline

**Job:** ingest raw events, normalise to canonical schema, validate, deduplicate, detect staleness, and write to the market-data store.

Sub-components:

| Sub-component | Responsibility |
|---------------|---------------|
| Ingestion | Consume adapter output; buffer into processing queue |
| Normaliser | Map vendor field names, units, and conventions to canonical schema |
| Validator | Schema check, bounds check, cross-field consistency |
| Deduplicator | Idempotency key (venue + instrument + sequence_id); reject exact duplicates |
| Staleness detector | Compare event timestamp to wall-clock; flag or reject if beyond threshold |
| Store writer | Persist validated events to market-data store |

Interface: `IDataPipeline`
- `submit(event: RawMarketDataEvent) → ValidationResult`
- `subscribe(filter: EventFilter) → AsyncIterator[NormalisedEvent]`

---

### 3.3 Market State

**Job:** maintain the current best-bid/ask, last trade, and session status for every active instrument. Acts as the shared read model for downstream components.

- No logic beyond state maintenance and query
- Subscribers receive a delta stream, not a full snapshot on every tick
- Staleness flag propagated from the pipeline

---

### 3.4 Feature Engine

**Job:** derive numerical features from normalised market data. Features are named, versioned, and reproducible.

- Input: normalised OHLC + quote stream
- Output: `FeatureVector{instrument, timestamp, features: Dict[str, float]}`
- Feature definitions are declarative (e.g., a YAML/Python spec listing lookback, formula, normalisation method)
- No ML inference here; pure arithmetic

Design constraint: a feature must compute in O(1) or O(k) with fixed look-back k. Unbounded scans are prohibited.

---

### 3.5 Signal Engine

**Job:** combine feature vectors into scored, directional signals.

- Input: `FeatureVector`
- Output: `Signal{instrument, timestamp, direction, score, confidence, lineage}`
- `lineage` lists every feature ID and weight that contributed to the score
- Signals are immutable once emitted; corrections produce a new signal with a `supersedes` link
- AI layer may NOT write to the signal stream; it may only read and annotate

---

### 3.6 Ranking

**Job:** cross-sectional ranking of instruments by signal strength within a universe.

- Input: batch of signals for the same timestamp
- Output: `RankedUniverse{timestamp, ranks: List[InstrumentRank]}`
- Configurable ranking metric and universe filter

---

### 3.7 Regime Detector

**Job:** classify the current market regime (e.g., trending / mean-reverting / high-vol) using only price and volume features.

- Output: `RegimeState{timestamp, regime, confidence}`
- Regime is advisory metadata consumed by the signal engine and risk engine; it does not override either

---

### 3.8 Risk Engine

**Job:** pre-trade gate. Every order request passes through before reaching the execution simulator.

Rules evaluated (in order, first failure rejects the order):

1. Instrument tradable (session open, not halted)
2. Stale data rejection (last quote not older than threshold)
3. Position limit (gross and net, per instrument and portfolio)
4. Order size limit (notional and share quantity)
5. Participation limit (order size vs. average daily volume)
6. Kill-switch check (global halt flag)

- Output: `RiskDecision{approved: bool, violations: List[RuleViolation]}`
- Rules are stateless functions; state (positions, ADV) is injected
- Kill switch is a single settable flag; setting it causes all subsequent checks to fail immediately

---

### 3.9 Execution Simulator

**Job:** simulate order execution against synthetic or historical market data. Produces realistic fills with market-impact and slippage estimates.

See `execution-model.md` for full detail.

---

### 3.10 TCA Engine

**Job:** measure execution quality after fills arrive.

See `execution-model.md §TCA`.

---

### 3.11 AI Research Assistant

**Job:** natural-language explanation and summarisation layer. Read-only with respect to all financial data and decisions.

Permitted operations:
- Read signals, features, fills, TCA results, risk decisions
- Generate natural-language explanations of any of the above
- Summarise execution sessions
- Flag anomalies for human review (advisory only)

Prohibited operations:
- Write to signal, order, or fill stores
- Override or suppress risk decisions
- Infer or generate numeric signals

Interface: `IResearchAssistant`
- `explain_signal(signal_id) → Explanation`
- `explain_fill(fill_id) → Explanation`
- `summarise_session(session_id) → SessionSummary`
- `flag_anomaly(context) → AnomalyReport`

The assistant is always backed by an injected LLM client; the platform has no hard dependency on any specific model.

---

### 3.12 Research Store

**Job:** durable, append-only storage for all platform artefacts.

- Market data events (time-series optimised)
- Feature vectors
- Signals
- Risk decisions
- Orders and fills
- TCA results
- AI explanations and anomaly flags
- Audit log (every state transition with actor + timestamp)

All writes are immutable by convention; corrections are new records with a `supersedes` reference.

---

## 4. Data flow (happy path)

```
Adapter emits QuoteEvent
  → Pipeline: normalise → validate → deduplicate → store
  → Market State updated
  → Feature Engine computes FeatureVector
  → Signal Engine emits Signal
  → Ranking updates RankedUniverse
  → [Research intent triggers order request]
  → Risk Engine: approve or reject
  → Execution Simulator: slice into child orders → simulate fills
  → Fill events written to Research Store
  → TCA Engine computes execution quality
  → AI Assistant reads results; generates explanation on demand
```

---

## 5. Interface contracts

All cross-component communication uses:
- Typed value objects (dataclasses / pydantic models — decided in Phase 1)
- No shared mutable state; data passed by value
- Async iterators for streaming; synchronous calls for point-in-time queries

Eventual technology choices (deferred to Phase 1):
- **Language:** Python (numerics, ecosystem) — decision made; no alternatives needed
- **Persistence:** evaluated in Phase 2 against write throughput and time-series query patterns
- **Message bus:** evaluated in Phase 2; in-process event dispatcher sufficient for Phase 1
- **LLM provider:** injected via adapter; no lock-in to a specific API

---

## 6. What is explicitly out of scope

- Live order routing or brokerage API
- Real-time market data redistribution
- Strategy optimisation / hyper-parameter search
- Cloud orchestration (Kubernetes, Terraform)
- User-facing UI (deferred to Phase 8)
