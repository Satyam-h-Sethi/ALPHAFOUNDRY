# ALPHAFOUNDRY — Developer Setup

This guide takes you from a fresh clone to a fully working local development
environment. All commands are PowerShell unless noted otherwise.

---

## Prerequisites

| Tool | Minimum version | Notes |
|------|----------------|-------|
| Python | **3.12** | See "Finding Python" below |
| Git | any recent | Used for branching and commits |

### Finding Python on Windows

The Microsoft Store shim at `%LOCALAPPDATA%\Microsoft\WindowsApps\python.exe`
is a redirect stub — it exits immediately with code 49 and cannot run packages.
Use the real interpreter:

```powershell
# Confirm you have the right one (should print "Python 3.12.x")
& "C:\Users\$env:USERNAME\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" --version
```

Create a shell alias for the session:

```powershell
Set-Alias python "C:\Users\$env:USERNAME\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
```

Or add it permanently to your `$PROFILE`.

---

## 1  Clone and enter the repo

```powershell
git clone <repo-url> C:\SS\ALPHAFOUNDRY
cd C:\SS\ALPHAFOUNDRY
```

---

## 2  Create and activate a virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

> **Tip — execution policy**: if the activate script is blocked, run:
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
> ```

---

## 3  Install the package with dev extras

```powershell
pip install -e ".[dev]"
```

This installs `alphafoundry` in editable mode plus all development tools:
`pytest`, `pytest-cov`, `mypy`, and `ruff`.

---

## 4  Run the checks

### Formatting & lint (ruff)

```powershell
# Auto-fix safe issues, then check
ruff format .
ruff check . --fix
```

### Static type checking (mypy)

```powershell
mypy alphafoundry
```

Expected output: `Success: no issues found`.

### Unit tests (pytest)

```powershell
pytest --tb=short -q
```

Run with coverage:

```powershell
pytest --cov=alphafoundry --cov-report=term-missing -q
```

---

## 5  Project layout

```
alphafoundry/
  adapters/       # IMarketDataAdapter + SyntheticAdapter
  ai/             # stub
  analytics/      # stub
  config/         # AppConfig, SyntheticAdapterConfig, load_config()
  domain/         # Pydantic v2 frozen domain models
  execution/      # stub
  pipeline/       # stub
  risk/           # stub
  tca/            # stub
tests/
  domain/         # unit tests for domain models
  adapters/       # unit tests for SyntheticAdapter
docs/             # Phase 0 architecture documents
.github/
  workflows/
    ci.yml        # lint → type-check → test on every push/PR
```

---

## 6  Synthetic adapter quick-start

```python
from alphafoundry.adapters.synthetic import SyntheticAdapter
from alphafoundry.config import SyntheticAdapterConfig

cfg = SyntheticAdapterConfig(seed=42, num_days=252)
adapter = SyntheticAdapter(cfg)

instruments = adapter.get_instruments()  # 5 NSE_EQ equities
bars = adapter.get_ohlc(
    instruments[0].instrument_id,
    bars_from,  # datetime (UTC, tz-aware)
    bars_to,  # datetime (UTC, tz-aware)
    "1d",  # freq: "1d", "5m", "1m"
)
```

Setting the same `seed` always produces the same prices — this is guaranteed by
the implementation and tested in `tests/adapters/test_synthetic.py`.

---

## 7  Constraints — read before contributing

- **No live brokerage execution.** This repo is research / paper-trading only.
- **Do not commit real market data.** NSE/BSE data is licensed; use only the
  `SyntheticAdapter` or data you have explicit rights to redistribute.
- **AI assists, never decides.** The AI layer may not write to signal, order, or
  fill stores, and may not override risk rules.
- **Determinism.** Numerical logic (GBM, volume, slippage) must be reproducible
  given the same seed — do not introduce `random` calls outside the adapter RNG.
- **UTC everywhere.** All timestamps must be `datetime` objects with
  `tzinfo=timezone.utc`. Local timezone is display-only.

---

## 8  Branch conventions

| Branch | Purpose |
|--------|---------|
| `main` | stable, tagged releases |
| `phase/NN-name` | phase deliverable (e.g. `phase/01-foundation`) |
| `feat/short-desc` | feature work in progress |

CI runs on every push and every PR targeting `main` or any `phase/**` branch.
