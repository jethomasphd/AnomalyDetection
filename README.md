# RG Anomaly Detection Suite

**Author:** Jacob E. Thomas, PhD | Results Generation

An in-house anomaly detection system applied to securities adjacent to recruitment marketing, advertising platforms, AI infrastructure, and market benchmarks. Four independent statistical methods analyze each ticker daily, identify anomalous behavior, and translate it into **actionable trading signals** — Buy, Sell, Long, Short, Reduce, or Watch.

Built for decision-makers who need clear, actionable intelligence without deep statistical expertise. Updated automatically every trading day with **incremental processing** — each run preserves previous signals and highlights what's new.

**[View the live dashboard](https://jethomasphd.github.io/AnomalyDetection/)**  |  **[Read the User Manual](USERMANUAL.md)**

---

## How it works

Four detection methods run independently against each ticker — **all causal**:
every score for bar *t* uses only data through bar *t* (enforced by the test
suite). That single property makes the historical backfill a true walk-forward
backtest and makes live operation identical to the backtest by construction.

| Method | The question it answers | Causality |
|--------|------------------------|-----------|
| **Fourier Transform** | Has the *rhythm* of this stock changed? | Expanding baseline ends at today |
| **Matrix Profile (STUMPY)** | Is this stock doing something it's *never done before*? | *Left* matrix profile — nearest neighbor strictly in the past |
| **Statistical Ensemble** | Do Z-scores, seasonal decomposition, and Isolation Forest all agree? | Trailing vols, past-only seasonal means, walk-forward forest refits |
| **EWMA Trend Analysis** | Is this stock's *momentum* abnormal *for this stock*? | Deviation standardized by its own trailing volatility |

All scores live on one fixed scale (0.5 = 2σ, 1.0 = 4σ+). Thresholds are fixed
sigma cutoffs, never percentiles of the run's own output — a quiet tape produces
a quiet report.

## Signals

| Signal | When it fires (σ = the ticker's own deviation volatility) | What to do |
|--------|---------------|------------|
| **Buy** | ≤ −2.5σ below trend: capitulation extreme (fade it) or stretch already contracting | Mean-reversion long targeting the trend line |
| **Sell** | ≥ +2.5σ above trend: blowoff extreme (fade it) or stretch already contracting | Take profits or tighten stops |
| **Long** | ≥ +1.5σ above trend and still *building* (not yet climactic) | Ride the trend with a trailing stop |
| **Short** | ≤ −1.5σ below trend and still *building* (not yet climactic) | Protective positions or short exposure |
| **Reduce** | Structural regime change (Fourier + Matrix Profile agree) | Cut position size until the new pattern clarifies |
| **Watch** | Anomaly detected, no tradable setup | Monitor for follow-through |

A trade call additionally requires **2+ methods in agreement** and a **1%
materiality floor** — statistically unusual but economically trivial moves
(a 0.1% wiggle in a T-bill ETF) stay informational.

## The backtest is real

- Fills at the **next session's close** after a signal exists — never the same
  bar, never a backdated price. 5 bps costs per side. 30-bar time stop.
- Mean-reversion trades exit at the trend target **frozen at detection time**;
  any trade exits on an opposite signal.
- **SPY buy-and-hold benchmark** on the same average deployed capital.
- Walk-forward (simulated history) and **live out-of-sample** results are
  tagged by provenance and reported separately, always.

## Watchlist

75 tickers across 11 categories — the full registry lives in `config.TICKER_REGISTRY`:

| Category | Examples |
|----------|----------|
| Engines of the Republic | CAT, DE, LMT, WMT, JNJ, BRK-B … |
| Critical Choke Points | V, MA, JPM, MSFT, AMZN, UNP, MCK … |
| Big Tech | AAPL, NVDA, META, TSLA, AMD, ORCL … |
| Consumer Leaders | PG, KO, MCD, NKE, TGT … |
| Financial Titans | GS, MS, BAC, BLK … |
| Healthcare & Pharma | LLY, ABBV, MRK … |
| Energy & Commodities | XOM, CVX, COP |
| Wall Street's Darlings | SPY, QQQ, IWM, VTI, ARKK … |
| The Clergy House | ASTS, STM |
| Reserve / UBS Funds | BIL, DVRUX, QGRPX, BNUEX |

---

## Quick start

```bash
pip install -r requirements.txt
python -m anomaly_detection
```

The dashboard opens at `docs/index.html`. Signal data is written to `data/alerts.json`.

For custom runs:

```bash
# Specific tickers
python -m anomaly_detection --tickers "AAPL,MSFT,GOOGL,TSLA"

# High sensitivity
python -m anomaly_detection --sensitivity high

# Rebuild the ledger from scratch (after a detection-regime change)
python -m anomaly_detection --reset
```

## Automated runs

GitHub Actions runs the full pipeline every weekday at 10:00 PM UTC (after US
market close), runs the test suite (including the causality invariant), commits
results, and deploys the dashboard to GitHub Pages.

**Durable by design:** the append-only record lives in `data/ledger/*.jsonl`,
committed by every run — git history is the audit trail. On each fresh CI
checkout the SQLite cache and per-ticker watermarks are rebuilt from the
ledger, so verdicts are written exactly once: new bars get **live** rows
(`detected_at` = run date), never-seen tickers get **walk-forward backfill**
rows. Fresh signals get a **NEW** badge on the dashboard; `data/run_health.json`
tracks fetch coverage and surfaces degraded days on the dashboard.

**Setup:** Repo settings > Pages > Source > **GitHub Actions**.

---

## Project structure

```
anomaly_detection/
  config.py              # Tickers, names, sectors, all tunable parameters
  data_fetch.py          # Yahoo Finance API (retry/backoff) + feature engineering
  pipeline.py            # 6-stage orchestration with provenance + health
  alerts.py              # Signal derivation (sigma-based + materiality gate)
  backtest.py            # Walk-forward backtest: next-bar fills, costs, benchmark
  storage.py             # Append-only SQLite cache + git-committed JSONL ledger
  detection/
    causal.py            # Shared causal scoring (trailing robust-z, one scale)
    engine.py            # Consensus scoring across all 4 methods (fixed cutoffs)
    fourier.py           # Frequency-domain structural change (expanding baseline)
    matrix_profile.py    # STUMPY LEFT-profile novelty (past-only neighbors)
    ensemble.py          # Return z-score + causal seasonal + walk-forward IForest
    ewma.py              # Standardized trend deviation + trajectory
  tests/
    test_causality.py    # THE invariant: appending future data never changes a verdict
  visualization/
    charts.py            # Plotly interactive charts
    dashboard.py         # Jinja2 HTML rendering
    templates/
      dashboard.html     # Dashboard template (GitHub Pages)
data/
  ledger/                # Committed append-only truth (anomalies, signals, watermarks)
  alerts.json            # Display view for the dashboard (capped)
  run_health.json        # Coverage + fetch failures for the latest run
```

---

## Provenance

Adapts the four-method anomaly detection architecture originally developed for CPM monitoring in recruitment marketing campaigns, re-engineered for general-purpose securities surveillance. See the [User Manual](USERMANUAL.md) for full technical details, configuration reference, and signal derivation logic.

---

*Results Generation — Jacob E. Thomas, PhD*
