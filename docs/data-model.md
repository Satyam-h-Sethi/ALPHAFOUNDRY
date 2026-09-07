# Data Model

Defines field-level schemas, storage contracts, and data-pipeline rules. Concrete technology choices (database engine, serialisation format) are deferred to Phase 2.

---

## 1. Storage contract principles

| Principle | Rule |
|-----------|------|
| **Immutability** | Records are never updated in place. Corrections create a new record with a `supersedes` field. |
| **Timezone** | All timestamps stored in UTC. Local timezone is a display concern only. |
| **Precision** | Prices: decimal with 4 decimal places (INR). Quantities: integer (shares / lots). Ratios/scores: float64. |
| **Partitioning key** | Market-data tables partition by `(instrument_id, date)`. Order/fill tables partition by `(session_id, date)`. |
| **Idempotency** | Every raw event carries an `idempotency_key` = `venue_id + ":" + sequence_id`. Duplicate keys are silently dropped after the first write. |

---

## 2. Market data schemas

### 2.1 `instruments`

```
instrument_id     UUID        PK
isin              CHAR(12)    nullable; unique where non-null
symbol            VARCHAR(32)
venue_id          VARCHAR(16) FK → venues
instrument_type   ENUM(EQ, FUT, OPT_CE, OPT_PE, IDX, ETF)
lot_size          INT         default 1
tick_size         DECIMAL(10,4)
expiry            DATE        nullable
strike            DECIMAL(12,4) nullable
underlying_id     UUID        nullable FK → instruments
currency          CHAR(3)     default 'INR'
is_active         BOOL
created_at        TIMESTAMPTZ
```

### 2.2 `venues`

```
venue_id          VARCHAR(16) PK   e.g. 'NSE_EQ'
name              VARCHAR(64)
timezone          VARCHAR(32)      e.g. 'Asia/Kolkata'
```

### 2.3 `sessions`

```
session_id        UUID        PK
venue_id          VARCHAR(16) FK → venues
calendar_date     DATE
session_type      ENUM(PRE_OPEN, NORMAL, CLOSING, POST_CLOSE, MUHURAT)
open_time         TIMESTAMPTZ
close_time        TIMESTAMPTZ
status            ENUM(SCHEDULED, OPEN, CLOSED, HALTED)
```

### 2.4 `quotes`

Primary time-series table. Write throughput is highest here.

```
quote_id          UUID        PK
idempotency_key   VARCHAR(64) UNIQUE
instrument_id     UUID        FK → instruments
venue_id          VARCHAR(16)
timestamp         TIMESTAMPTZ  — event time (from feed)
received_at       TIMESTAMPTZ  — ingest wall-clock
sequence_id       BIGINT
bid_price         DECIMAL(14,4)
bid_qty           INT
ask_price         DECIMAL(14,4)
ask_qty           INT
last_trade_price  DECIMAL(14,4) nullable
session_status    ENUM(OPEN, CLOSED, HALTED, PRE_OPEN)
is_stale          BOOL         computed on ingest
```

### 2.5 `trades`

```
trade_id          UUID        PK
idempotency_key   VARCHAR(64) UNIQUE
instrument_id     UUID
venue_id          VARCHAR(16)
timestamp         TIMESTAMPTZ
received_at       TIMESTAMPTZ
sequence_id       BIGINT
price             DECIMAL(14,4)
qty               INT
side              ENUM(BUY, SELL, UNKNOWN)
```

### 2.6 `ohlc_bars`

```
bar_id            UUID        PK
instrument_id     UUID
venue_id          VARCHAR(16)
freq              VARCHAR(8)   e.g. '1m', '5m', '1d'
bar_open          TIMESTAMPTZ  — interval start (PK component for time-series)
bar_close         TIMESTAMPTZ
open              DECIMAL(14,4)
high              DECIMAL(14,4)
low               DECIMAL(14,4)
close             DECIMAL(14,4)
volume            BIGINT
num_trades        INT
vwap              DECIMAL(14,4) nullable
is_complete       BOOL
```

---

## 3. Feature and signal schemas

### 3.1 `feature_vectors`

```
feature_vector_id UUID        PK
instrument_id     UUID
as_of             TIMESTAMPTZ  — market time
computed_at       TIMESTAMPTZ  — wall-clock
feature_version   VARCHAR(32)
features          JSONB        — {feature_name: float64}
```

Feature names are validated against a registered feature registry; unknown names are rejected on write.

### 3.2 `signals`

```
signal_id         UUID        PK
instrument_id     UUID
as_of             TIMESTAMPTZ
emitted_at        TIMESTAMPTZ
direction         ENUM(LONG, SHORT, NEUTRAL)
score             FLOAT8       CHECK (-1 <= score <= 1)
confidence        FLOAT8       CHECK (0 <= confidence <= 1)
lineage           JSONB        — [{feature_name, weight, value}]
signal_version    VARCHAR(32)
supersedes        UUID         nullable FK → signals
```

### 3.3 `instrument_ranks`

```
rank_id           UUID        PK
instrument_id     UUID
universe_id       VARCHAR(64)
as_of             TIMESTAMPTZ
rank              INT
score             FLOAT8
```

---

## 4. Order and fill schemas

See `execution-model.md` for lifecycle detail. Data model summary:

### 4.1 `parent_orders`

```
parent_order_id   UUID        PK
session_id        UUID        FK → simulation_sessions
instrument_id     UUID
signal_id         UUID        nullable FK → signals — what prompted this order
direction         ENUM(BUY, SELL)
target_qty        INT
target_notional   DECIMAL(16,4) nullable
algo              VARCHAR(32)  e.g. 'VWAP', 'TWAP', 'POV'
status            ENUM(PENDING_RISK, REJECTED, APPROVED, ACTIVE, FILLED, PARTIALLY_FILLED, CANCELLED)
risk_decision_id  UUID        FK → risk_decisions
created_at        TIMESTAMPTZ
updated_at        TIMESTAMPTZ
```

### 4.2 `child_orders`

```
child_order_id    UUID        PK
parent_order_id   UUID        FK → parent_orders
sequence_num      INT          — slice index within parent
instrument_id     UUID
direction         ENUM(BUY, SELL)
qty               INT
limit_price       DECIMAL(14,4) nullable
order_type        ENUM(MARKET, LIMIT, IOC)
status            ENUM(PENDING, ACTIVE, FILLED, PARTIALLY_FILLED, CANCELLED, EXPIRED)
created_at        TIMESTAMPTZ
```

### 4.3 `fills`

```
fill_id           UUID        PK
child_order_id    UUID        FK → child_orders
fill_qty          INT
fill_price        DECIMAL(14,4)
simulated_impact  DECIMAL(14,4) — estimated price impact applied
fill_timestamp    TIMESTAMPTZ
```

### 4.4 `risk_decisions`

```
risk_decision_id  UUID        PK
parent_order_id   UUID
approved          BOOL
violations        JSONB        — [{rule, measured_value, limit, unit}]
evaluated_at      TIMESTAMPTZ
```

---

## 5. TCA schema

```
tca_report_id     UUID        PK
parent_order_id   UUID        FK → parent_orders
benchmark_type    ENUM(ARRIVAL, VWAP, TWAP, CLOSE)
benchmark_price   DECIMAL(14,4)
execution_price   DECIMAL(14,4)  — fill VWAP
realized_slippage DECIMAL(14,4)  — execution_price - benchmark_price (signed)
market_impact     DECIMAL(14,4)  — model estimate
timing_cost       DECIMAL(14,4)
implementation_shortfall DECIMAL(14,4)
total_qty         INT
computed_at       TIMESTAMPTZ
```

---

## 6. AI artefact schemas

### 6.1 `ai_explanations`

```
explanation_id    UUID        PK
subject_type      ENUM(SIGNAL, FILL, RISK_DECISION, TCA, SESSION)
subject_id        UUID
narrative         TEXT
model_version     VARCHAR(64)
input_refs        JSONB        — list of IDs the model was given
generated_at      TIMESTAMPTZ
```

### 6.2 `anomaly_reports`

```
anomaly_id        UUID        PK
severity          ENUM(INFO, WARN, ALERT)
description       TEXT
context_refs      JSONB        — related record IDs
model_version     VARCHAR(64)
generated_at      TIMESTAMPTZ
reviewed          BOOL         default false
```

---

## 7. Data pipeline metadata

### 7.1 `ingest_events` (audit)

Every raw event that enters the pipeline, regardless of outcome:

```
ingest_id         UUID        PK
adapter_id        VARCHAR(64)
received_at       TIMESTAMPTZ
raw_size_bytes    INT
outcome           ENUM(ACCEPTED, DUPLICATE, VALIDATION_FAILED, STALE_REJECTED)
error_detail      TEXT         nullable
idempotency_key   VARCHAR(64)
```

---

## 8. Data-quality rules (enforced by Validator)

| Rule | Check |
|------|-------|
| Price sanity | `0 < price <= 1_000_000` INR |
| Spread sanity | `ask_price >= bid_price` |
| Quantity sanity | `qty > 0` |
| Timestamp future-gate | `timestamp <= received_at + 5s` (clock skew allowance) |
| Timestamp past-gate | `timestamp >= session.open_time - 5m` |
| Lot-size conformance | `qty % lot_size == 0` |
| Tick conformance | `(price / tick_size)` is an integer within tolerance |

Any failed rule → `ingest_event.outcome = VALIDATION_FAILED`; event is not written to the primary tables.
