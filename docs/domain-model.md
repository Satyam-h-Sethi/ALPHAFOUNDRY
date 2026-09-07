# Domain Model

The domain model captures the concepts the platform reasons about. Implementations translate these to concrete types in Phase 1; the concepts are stable.

---

## 1. Market structure

### Venue
A trading exchange or market centre.

| Attribute | Description |
|-----------|-------------|
| `venue_id` | Canonical short code (`NSE_EQ`, `NSE_FO`, `BSE_EQ`) |
| `name` | Human-readable name |
| `timezone` | Exchange local timezone (`Asia/Kolkata`) |
| `sessions` | Ordered list of `Session` windows for a given calendar date |

### Session
A contiguous window during which a venue accepts orders.

| Attribute | Description |
|-----------|-------------|
| `session_type` | `PRE_OPEN`, `NORMAL`, `CLOSING`, `POST_CLOSE`, `MUHURAT` |
| `open_time` | Wall-clock open (timezone-aware) |
| `close_time` | Wall-clock close |
| `status` | `SCHEDULED`, `OPEN`, `CLOSED`, `HALTED` |

Session boundaries drive staleness thresholds in the risk engine: a quote with a timestamp outside the last open session is automatically stale.

---

## 2. Instrument

A tradable entity. The platform supports the instrument types relevant to Indian markets:

| `instrument_type` | Examples |
|-------------------|---------|
| `EQ` | Reliance, Infosys — NSE/BSE equities |
| `FUT` | NIFTY near-month futures |
| `OPT_CE` | Call option |
| `OPT_PE` | Put option |
| `IDX` | NIFTY 50, SENSEX — index (non-tradable, reference only) |
| `ETF` | NIFTYBEES |

### Instrument attributes

| Attribute | Description |
|-----------|-------------|
| `instrument_id` | Internal UUID |
| `isin` | ISIN (equity / ETF) |
| `symbol` | Venue-local symbol (`RELIANCE`, `NIFTY24NOVFUT`) |
| `venue_id` | Where this is listed |
| `instrument_type` | See table above |
| `lot_size` | Minimum tradable quantity (1 for equities, contract size for F&O) |
| `tick_size` | Minimum price increment (e.g. 0.05 INR) |
| `expiry` | Expiry date for futures and options (null for equities) |
| `strike` | Strike price for options (null otherwise) |
| `underlying_id` | Link to underlying `Instrument` for derivatives |
| `currency` | `INR` |
| `is_active` | Whether the instrument is currently tradable |

### Instrument identity rule
`instrument_id` is the stable key. `symbol` is venue-specific and can change (corporate actions, expiry roll); the platform never uses symbol as a join key across venues.

---

## 3. Market data events

### Quote (Level 1)
The best bid and ask at a point in time.

| Attribute | Description |
|-----------|-------------|
| `instrument_id` | |
| `venue_id` | |
| `timestamp` | Nanosecond-precision, timezone-aware (UTC internally) |
| `sequence_id` | Monotonic integer from the venue feed; deduplication key |
| `bid_price` | Best bid |
| `bid_qty` | Quantity at best bid |
| `ask_price` | Best ask |
| `ask_qty` | Quantity at best ask |
| `last_trade_price` | Last traded price at this moment |
| `session_status` | Propagated from session |

### Trade (Tick)
An executed transaction reported by the venue.

| Attribute | Description |
|-----------|-------------|
| `instrument_id` | |
| `venue_id` | |
| `timestamp` | |
| `sequence_id` | |
| `price` | Execution price |
| `qty` | Executed quantity |
| `side` | `BUY` / `SELL` / `UNKNOWN` (venue-dependent) |

### OHLC Bar
Aggregated price bar over a fixed interval.

| Attribute | Description |
|-----------|-------------|
| `instrument_id` | |
| `venue_id` | |
| `bar_open` | Interval start (timezone-aware) |
| `bar_close` | Interval end |
| `freq` | `1m`, `5m`, `15m`, `1d`, etc. |
| `open` | Opening price |
| `high` | High |
| `low` | Low |
| `close` | Close |
| `volume` | Total volume in interval |
| `num_trades` | Trade count |
| `vwap` | Volume-weighted average price |
| `is_complete` | False if the bar is still forming |

---

## 4. Feature and signal

### FeatureVector
A named, typed numerical snapshot computed from market data.

| Attribute | Description |
|-----------|-------------|
| `feature_vector_id` | UUID |
| `instrument_id` | |
| `as_of` | The market timestamp this vector reflects |
| `computed_at` | Wall-clock time of computation |
| `features` | `Dict[feature_name: str, value: float]` |
| `feature_version` | Version tag of the feature-engine configuration |

Feature names are namespaced: `price.return_1d`, `vol.realised_20d`, `flow.buy_imbalance_5m`.

### Signal
A scored, directional view on an instrument.

| Attribute | Description |
|-----------|-------------|
| `signal_id` | UUID |
| `instrument_id` | |
| `as_of` | Market timestamp |
| `emitted_at` | Wall-clock |
| `direction` | `LONG`, `SHORT`, `NEUTRAL` |
| `score` | Float in [-1, 1]; magnitude = conviction |
| `confidence` | Float in [0, 1] |
| `lineage` | List of `{feature_name, weight, value}` — full attribution |
| `signal_version` | Version of the signal engine configuration |
| `supersedes` | `signal_id` of the signal this corrects (nullable) |

### InstrumentRank
Cross-sectional rank within a universe at a timestamp.

| Attribute | Description |
|-----------|-------------|
| `rank_id` | UUID |
| `instrument_id` | |
| `universe_id` | Which universe this rank belongs to |
| `as_of` | |
| `rank` | Integer rank (1 = highest conviction) |
| `score` | Underlying signal score used |

---

## 5. Order lifecycle

Detailed field specs in `execution-model.md`. Conceptual states:

```
PENDING_RISK
  → REJECTED (risk engine refused)
  → APPROVED
      → PENDING_EXECUTION
          → [slicing]
          → child orders → PARTIALLY_FILLED / FILLED / CANCELLED
      → PARENT: PARTIALLY_FILLED / FILLED / CANCELLED
```

### ParentOrder
Research intent translated to a size and direction.

### ChildOrder
A slice of a parent order submitted to the simulation venue.

### Fill
A simulated execution event against a child order.

---

## 6. Risk concepts

| Concept | Description |
|---------|-------------|
| `PositionLimit` | Max gross / net exposure per instrument or portfolio |
| `OrderLimit` | Max notional or quantity per single order |
| `ParticipationLimit` | Max fraction of average daily volume (ADV) per order |
| `KillSwitch` | Global halt: when set, all orders are rejected immediately |
| `StaleDataThreshold` | Max age of a quote before it is considered invalid for risk purposes |
| `RuleViolation` | Records which rule failed, the measured value, and the limit breached |

---

## 7. Execution quality concepts

| Concept | Description |
|---------|-------------|
| `BenchmarkPrice` | Reference price for TCA (arrival price, VWAP, TWAP, close) |
| `ExecutionPrice` | Volume-weighted average fill price across all child fills |
| `RealizedSlippage` | `execution_price − benchmark_price` (signed; negative is adverse for buys) |
| `MarketImpact` | Estimated price movement caused by the order itself |
| `ImplementationShortfall` | Total cost = market impact + timing cost + explicit costs |
| `TCAReport` | Aggregated quality metrics for one parent order |

---

## 8. AI domain objects

| Object | Description |
|--------|-------------|
| `Explanation` | Natural-language narrative for a signal, fill, or risk decision, with source references |
| `SessionSummary` | Narrative overview of a complete simulation session |
| `AnomalyReport` | Advisory flag: pattern that warrants human review (does not block anything) |

All AI domain objects carry `generated_at`, `model_version`, and `input_refs` (list of IDs of the records the AI read). They are stored alongside the objects they explain but never alter them.
