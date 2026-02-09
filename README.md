# Stock Anomaly Detection

**Author:** Jacob E. Thomas, PhD

A general-purpose anomaly detection system for stock market data. Runs four independent statistical methods against any Yahoo Finance ticker, generates plain-English alerts ranked by severity, and publishes an interactive dashboard to GitHub Pages — automatically, every trading day.

Built for decision-makers who need actionable signals without deep statistical expertise.

---

## What it does

Each ticker is analyzed by four independent detection algorithms. When multiple methods independently flag the same day, the system assigns a severity level:

| Method | What it answers |
|--------|----------------|
| **Fourier Transform** | Has the *rhythm* of this stock changed? |
| **Matrix Profile** | Is this stock doing something it's *never done before*? |
| **Statistical Ensemble** | Do Z-scores, seasonal decomposition, and Isolation Forest all agree? |
| **EWMA Trend** | Is this stock's *momentum* abnormal? |

| Severity | Meaning |
|----------|---------|
| CRITICAL | All 4 methods agree |
| HIGH | 3 of 4 methods agree |
| MODERATE | 2 of 4 methods agree |
| LOW | 1 method or elevated consensus score |

---

## Quick start

```bash
pip install -r requirements.txt

# Run with defaults (20 major tickers, medium sensitivity)
python -m anomaly_detection

# Specific tickers
python -m anomaly_detection --tickers "AAPL,MSFT,GOOGL,TSLA"

# High sensitivity, 6-month window
python -m anomaly_detection --sensitivity high --lookback 180
```

Results:
- **`docs/index.html`** — interactive dashboard (open in browser)
- **`data/alerts.json`** — structured alert data
- **`data/history/`** — run-over-run snapshots for trend tracking

---

## Automated runs (GitHub Actions)

The included workflow runs every weekday at 6:00 PM UTC (after US market close), commits results, and deploys the dashboard to GitHub Pages.

**Setup:** In repo settings, go to Pages > Source > select **GitHub Actions**.

Manual trigger: Actions > Stock Anomaly Detection > Run workflow.

---

## Historical tracking

Each run saves a snapshot to `data/history/`. The dashboard shows anomaly count trends over time, so you can see whether the market is getting noisier or calmer run-over-run.

---

## Project structure

```
anomaly_detection/
  config.py              # All tunable parameters
  data_fetch.py          # Yahoo Finance API + feature engineering
  pipeline.py            # Orchestration + history management
  alerts.py              # Plain-English alert generation
  detection/
    engine.py            # Runs all 4 methods, computes consensus
    fourier.py           # Frequency-domain structural change
    matrix_profile.py    # STUMPY novelty detection
    ensemble.py          # Z-score + seasonal + Isolation Forest
    ewma.py              # Trend deviation + trajectory
  visualization/
    charts.py            # Plotly chart generation
    dashboard.py         # Jinja2 HTML renderer
    templates/
      dashboard.html     # GitHub Pages template
data/
  alerts.json            # Latest alerts
  history/               # Run-over-run snapshots
docs/
  index.html             # Dashboard (GitHub Pages)
```

---

## Configuration

Edit `anomaly_detection/config.py` or pass CLI flags:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `DEFAULT_TICKERS` | 20 majors | SPY, QQQ, AAPL, MSFT, NVDA, etc. |
| `--sensitivity` | medium | low (99.5%ile) / medium (97.5%ile) / high (95%ile) |
| `--lookback` | 365 | Days of historical data |
| `METHOD_WEIGHTS` | Ensemble 30%, MP 25%, EWMA 25%, Fourier 20% | Consensus score weighting |

Works with any Yahoo Finance symbol: US equities, ETFs, crypto (BTC-USD), indices (^GSPC).

---

## Derived from

Adapts the four-method detection architecture from a CPM anomaly detection system built for recruitment marketing (see `CPM_ANOMALY_DETECTION_SPEC (1).md`), re-engineered for general-purpose stock market surveillance.
