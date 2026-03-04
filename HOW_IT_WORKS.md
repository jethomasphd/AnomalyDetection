# How It Works — Stock Anomaly Detection System

## Storage Schema

### SQLite Database (`data/anomaly_store.db`)

#### `anomalies` table
| Column | Type | Description |
|--------|------|-------------|
| date | TEXT | Trading date (YYYY-MM-DD) |
| ticker | TEXT | Stock/fund ticker symbol |
| anomaly_type | TEXT | Detection method: `fourier`, `matrix_profile`, `ensemble`, `ewma`, or `consensus` |
| severity_score | REAL | Normalized score (0-1 scale) |
| direction | TEXT | `above`, `below`, or `neutral` relative to trend |
| features_snapshot | TEXT | JSON blob with close, volume, deviation_pct, trajectory, etc. |
| model_version | TEXT | Version string (e.g., "1.1.0") for reproducibility |
| threshold_params | TEXT | JSON blob with threshold configuration used |
| created_at | TEXT | ISO timestamp of when row was written |

**Primary Key:** `(date, ticker, anomaly_type, model_version)`

#### `signals` table
| Column | Type | Description |
|--------|------|-------------|
| date | TEXT | Signal date |
| ticker | TEXT | Stock/fund ticker |
| signal | TEXT | `BUY`, `SELL`, `LONG`, `SHORT`, `REDUCE`, or `WATCH` |
| confidence | TEXT | `Strong`, `Moderate`, or `Developing` |
| rationale | TEXT | JSON blob with description, scores, details |
| model_version | TEXT | Model version for traceability |
| created_at | TEXT | ISO timestamp |

**Primary Key:** `(date, ticker, model_version)`

## Idempotency Approach

All writes use SQLite `INSERT OR REPLACE` (upsert):

1. **Same day re-run:** If the pipeline runs twice for the same date, the primary key constraint ensures no duplicate rows — the second run replaces the first.
2. **Consecutive days:** New dates are appended; existing dates are untouched.
3. **Backfill:** If lookback fetches data that overlaps with stored history, upsert preserves the latest computation without duplicating.

### Integrity Guarantee

```
Run Day 1 → anomalies table has N rows
Run Day 1 again → anomalies table still has N rows (idempotent)
Run Day 2 → anomalies table has N + new_anomalies rows (append)
```

Tests in `anomaly_detection/tests/test_storage.py` verify:
- `test_upsert_anomalies_idempotent` — re-insert same rows, count unchanged
- `test_upsert_signals_idempotent` — same for signals
- `test_consecutive_days_preserved` — day 2 doesn't lose day 1

## Signal Logic

Signals are derived from two dimensions of the EWMA analysis:

| Deviation (%) | Trajectory | Signal | Type |
|---------------|------------|--------|------|
| < -8% | decelerating/normal | **BUY** | Mean-reversion |
| < -5% | decelerating | **BUY** | Mean-reversion |
| > +8% | decelerating/normal | **SELL** | Mean-reversion |
| > +5% | decelerating | **SELL** | Mean-reversion |
| < -3% | accelerating/breakout | **SHORT** | Momentum |
| > +3% | accelerating/breakout | **LONG** | Momentum |
| any | fourier + mp both flag | **REDUCE** | Regime change |
| any | none of above | **WATCH** | Monitor |

All signals require 2+ detection methods to agree (except REDUCE which requires fourier + matrix profile).

**Confidence:** Strong (3-4 methods), Moderate (2), Developing (1 + high score).

## Ticker Registry

34 tickers organized into 5 categories:
- **Engines of the Republic** (15): Core economic infrastructure stocks
- **Critical Choke Points** (14): Essential system gatekeepers
- **Reserve** (1): Treasury bill ETF as cash proxy
- **Broad Index** (1): SPY for market context
- **UBS Funds** (3): Actively managed mutual funds

Each ticker is validated against yfinance before inclusion. Failed tickers are logged and excluded with a warning in the dashboard UI.

## Dashboard Architecture

The dashboard is a single self-contained HTML file with embedded Plotly.js charts:

1. **Attention Queue** — Ranked table of tickers by composite attention score (recency + severity + persistence + signal strength)
2. **Trading Signals** — Top 12 most recent signals with collapsible remainder
3. **Ticker Deep Dive** — Top 12 by market cap as buttons + dropdown for rest
4. **Signal Performance** — 3-month backtest with equity curve
5. **Learn Panel** — Curated educational resources
6. **Technical Details** — Collapsible method explanations

All sections share a single `selectedTicker` state — clicking any ticker anywhere updates the Deep Dive view.
