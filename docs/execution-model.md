# Execution Model

Covers the full lifecycle of a simulated order: from research intent to fills, market-impact modelling, and TCA.

---

## 1. Scope and constraints

- **Paper trading only.** Nothing in this layer sends instructions to a real venue.
- **No licensed data redistribution.** Fill simulation uses either synthetic prices or legitimately-owned historical data provided through an adapter.
- **Deterministic.** Given identical inputs (order parameters + market data snapshot), the simulator produces identical fills. Random elements (e.g. queue-position simulation) use a seeded RNG whose seed is recorded in the fill record.

---

## 2. Order lifecycle

```
Research intent
    ↓
ParentOrder created (status: PENDING_RISK)
    ↓
Risk Engine evaluation
    ├─ REJECTED → RiskDecision stored; parent status = REJECTED; stop
    └─ APPROVED → RiskDecision stored; parent status = APPROVED
        ↓
Execution Simulator activates parent (status: ACTIVE)
    ↓
Order Slicer → ChildOrder[1..N]
    ↓  (for each child, in scheduled sequence)
Fill Simulator → Fill[1..M] per child
    ↓
Parent aggregates fills → PARTIALLY_FILLED / FILLED
    ↓
TCA Engine computes TCAReport
```

---

## 3. Parent order

A parent order represents a complete research-level trading intent.

| Field | Notes |
|-------|-------|
| `algo` | Slicing algorithm to apply (VWAP, TWAP, POV, IS, MARKET) |
| `target_qty` | Total quantity to execute; mutually exclusive with `target_notional` |
| `target_notional` | Target in INR; converted to qty using arrival price |
| `urgency` | `LOW`, `MEDIUM`, `HIGH` — feeds into IS and POV algorithms |
| `time_in_force` | `DAY`, `SESSION`, `GTT` (good-till-time: explicit deadline) |
| `price_limit` | Optional worst-case price; child orders will not execute beyond this |

### Cancellation
A parent order can be cancelled at any time before fully filled. Outstanding child orders are marked CANCELLED; partially received fills are retained.

---

## 4. Order slicing

The slicer translates a parent order into a schedule of child orders. Each algorithm has a documented, deterministic formula.

### 4.1 TWAP — Time-Weighted Average Price

Divide target quantity equally across N time buckets spanning the execution window.

```
bucket_qty = ceil(target_qty / N)
schedule   = [bucket_open + i * bucket_width for i in range(N)]
```

Last bucket absorbs rounding remainder.

### 4.2 VWAP — Volume-Weighted Average Price

Weight each bucket by the instrument's historical or intraday volume profile.

```
bucket_qty[i] = target_qty * volume_profile[i] / sum(volume_profile)
```

Volume profile sourced from historical OHLC bars. Falls back to TWAP if no profile available; the fallback is logged.

### 4.3 POV — Percentage of Volume

Child orders participate at a fixed fraction (`pov_rate`, e.g. 10%) of observed market volume.

```
child_qty = min(observed_volume_in_window * pov_rate, remaining_qty)
```

Execution windows are fixed-length (e.g. 1 minute); child orders are emitted at the end of each window.

### 4.4 IS — Implementation Shortfall

A front-loaded schedule that balances market impact against timing risk. Urgency drives the front-loading factor:

```
schedule[i] = target_qty * urgency_weight[i]   # weights sum to 1.0
```

`urgency_weight` vectors for LOW / MEDIUM / HIGH are config-defined constants, not learned.

### 4.5 MARKET (immediate)

Single child order for the full quantity; scheduled immediately. Used for research scenarios where speed is the only criterion.

---

## 5. Fill simulation

The fill simulator processes each child order against the current market state.

### 5.1 Base fill logic

```
if order_type == MARKET:
    fill_price = mid_price + signed_half_spread + impact
elif order_type == LIMIT:
    if (BUY and ask_price <= limit_price) or (SELL and bid_price >= limit_price):
        fill_price = limit_price  # passive fill at limit
    else:
        child unfilled → status EXPIRED / rescheduled
```

`signed_half_spread`: positive for buys (we lift the ask), negative for sells (we hit the bid).

### 5.2 Market-impact model

A linear temporary-impact approximation:

```
impact = eta * sigma * (child_qty / ADV) ^ 0.5 * price
```

| Parameter | Meaning |
|-----------|---------|
| `eta` | Impact coefficient (config; default 0.1) |
| `sigma` | Realised daily volatility of the instrument |
| `ADV` | Average daily volume over trailing N days |

This is a simplified single-factor model. Almgren–Chriss or empirical models can replace it in later phases without changing the interface.

### 5.3 Partial fills

If `child_qty > ask_qty` (available liquidity), the fill is partial:

```
filled_qty  = min(child_qty, available_qty)
residual_qty = child_qty - filled_qty
```

Residual is re-queued for the next simulation tick, subject to the parent's time-in-force.

### 5.4 Slippage recording

Every fill records:

```
gross_fill_price = raw_fill_price (unadjusted)
simulated_impact = impact component applied
net_fill_price   = gross_fill_price + simulated_impact (for buys)
```

Both components are stored so TCA can decompose slippage into spread-cost and impact-cost.

---

## 6. Position tracking

The execution simulator maintains a running position per instrument per simulation session:

```
position[instrument_id] += signed_fill_qty   # +ve = long, -ve = short
```

Position is updated after every fill. The risk engine reads this state before approving the next parent order.

---

## 7. TCA — Transaction Cost Analysis

### 7.1 Benchmark prices

| Benchmark | Definition | When to use |
|-----------|------------|-------------|
| `ARRIVAL` | Mid-price at the moment the parent order was approved | IS and urgency studies |
| `VWAP` | Market VWAP over the execution interval | VWAP algo evaluation |
| `TWAP` | Time average of mid-prices over execution interval | TWAP algo evaluation |
| `CLOSE` | Official session close price | End-of-day comparison |

### 7.2 TCA metrics

```
execution_price = sum(fill_qty[i] * fill_price[i]) / sum(fill_qty[i])  # fill VWAP

realized_slippage = execution_price - benchmark_price  # positive = adverse for buys

spread_cost  = sum(fill_qty[i] * half_spread[i]) / total_qty
impact_cost  = sum(fill_qty[i] * simulated_impact[i]) / total_qty
timing_cost  = benchmark_price - arrival_price         # for non-ARRIVAL benchmarks

implementation_shortfall = spread_cost + impact_cost + timing_cost
```

### 7.3 TCA report contents

```
parent_order_id
benchmark_type
benchmark_price
execution_price
realized_slippage           (bps and INR)
spread_cost                 (bps)
impact_cost                 (bps)
timing_cost                 (bps)
implementation_shortfall    (bps and INR)
fill_count
total_qty
execution_duration_seconds
```

Basis-point values: `slippage_bps = (slippage / benchmark_price) * 10_000`

---

## 8. Simulation session

A simulation session groups a set of parent orders executed against the same market-data window for a controlled research experiment.

```
simulation_session_id UUID
name                  VARCHAR
market_data_window    (start: TIMESTAMPTZ, end: TIMESTAMPTZ)
adapter_id            VARCHAR    — which data adapter was used
universe_id           VARCHAR    — instrument universe
algo_config           JSONB      — snapshot of algo parameters used
created_at            TIMESTAMPTZ
status                ENUM(RUNNING, COMPLETED, ABORTED)
```

All fills, TCA reports, and AI explanations reference `simulation_session_id` for grouped analysis.

---

## 9. Risk engine interaction

The risk engine is called **synchronously** before any parent order leaves `PENDING_RISK` state. The execution simulator must not proceed on an order without a stored `RiskDecision` with `approved = true`.

Rules evaluated (in order; first failure terminates evaluation):

| # | Rule | Inputs | Threshold source |
|---|------|--------|-----------------|
| 1 | Session open check | current session status | session store |
| 2 | Stale data check | last quote `received_at` | config: `max_quote_age_seconds` |
| 3 | Instrument-level position limit | current position, order qty | risk config |
| 4 | Portfolio gross exposure limit | sum of abs positions | risk config |
| 5 | Single-order notional limit | order qty × price | risk config |
| 6 | ADV participation limit | order qty / ADV | risk config |
| 7 | Kill switch | global flag | in-memory flag |

Each violation records the rule name, the value measured, and the limit that was breached. This is stored and is available to the AI assistant for explanation.

---

## 10. Kill switch

The kill switch is a single in-memory boolean flag accessible to the risk engine. Setting it to `True`:

- Causes rule 7 to fail for all subsequent orders
- Does NOT cancel orders already in `ACTIVE` state (those continue to fill)
- Is logged with a timestamp and the reason provided by the operator

Clearing the kill switch is a deliberate operator action that is also logged. The switch state persists for the duration of the process; it is not persisted to the database (by design: a restart is a clean state).
