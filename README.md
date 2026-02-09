# Stock Anomaly Detection

**Author:** Jacob E. Thomas, PhD

A general-purpose anomaly detection system for stock market data. Runs four independent statistical methods against Yahoo Finance tickers, translates anomalies into **actionable trading signals** (Buy, Sell, Long, Short), and publishes an interactive dashboard to GitHub Pages — automatically, every trading day.

Built for decision-makers who need clear, actionable intelligence without deep statistical expertise.

---

## What it does

Each ticker is analyzed by four independent detection algorithms. When anomalies are detected, the system derives a trading signal based on how far price has deviated from its trend and which direction momentum is heading.

| Method | What it answers |
|--------|----------------|
| **Fourier Transform** | Has the *rhythm* of this stock changed? |
| **Matrix Profile** | Is this stock doing something it's *never done before*? |
| **Statistical Ensemble** | Do Z-scores, seasonal decomposition, and Isolation Forest all agree? |
| **EWMA Trend** | Is this stock's *momentum* abnormal? |

| Signal | Meaning |
|--------|---------|
| **Buy** | Oversold — price is far below trend, selling pressure fading. Mean-reversion opportunity. |
| **Sell** | Overbought — price is far above trend, buying pressure fading. Consider taking profits. |
| **Long** | Upward momentum accelerating — trend-following opportunity. |
| **Short** | Downward momentum accelerating — consider protective positions. |
| **Reduce** | Regime change detected — reduce exposure until new pattern clarifies. |
| **Watch** | Anomaly detected, awaiting confirmation before acting. |

---

## Default watchlist

| Sector | Tickers |
|--------|---------|
| Staffing & Recruitment | ZipRecruiter (ZIP), Kelly Services (KELYA), ASGN Inc. (ASGN), ManpowerGroup (MAN) |
| Market Benchmarks | S&P 500 (^GSPC), Nasdaq-100 (^NDX) |
| Ad Platforms | The Trade Desk (TTD), Meta Platforms (META), Alphabet (GOOGL) |
| AI Infrastructure | NVIDIA (NVDA), Microsoft (MSFT) |

---

## Quick start

```bash
pip install -r requirements.txt

# Run with defaults (11 tickers, medium sensitivity)
python -m anomaly_detection

# Specific tickers
python -m anomaly_detection --tickers "AAPL,MSFT,GOOGL,TSLA"

# High sensitivity, 6-month window
python -m anomaly_detection --sensitivity high --lookback 180
```

Results:
- **`docs/index.html`** — interactive dashboard (open in browser)
- **`data/alerts.json`** — structured signal data

---

## Automated runs (GitHub Actions)

The included workflow runs every weekday at 6:00 PM UTC (after US market close), commits results, and deploys the dashboard to GitHub Pages.

**Setup:** In repo settings, go to Pages > Source > select **GitHub Actions**.

Manual trigger: Actions > Stock Anomaly Detection > Run workflow.

---

## Project structure

```
anomaly_detection/
  config.py              # All tunable parameters + ticker names
  data_fetch.py          # Yahoo Finance API + feature engineering
  pipeline.py            # 5-stage orchestration
  alerts.py              # Trading signal derivation
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
  alerts.json            # Latest trading signals
docs/
  index.html             # Dashboard (GitHub Pages)
```

---

## Configuration

Edit `anomaly_detection/config.py` or pass CLI flags:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `DEFAULT_TICKERS` | 11 tickers | Staffing, benchmarks, ad platforms, AI infra |
| `--sensitivity` | medium | low (99.5%ile) / medium (97.5%ile) / high (95%ile) |
| `--lookback` | 365 | Days of historical data |
| `METHOD_WEIGHTS` | Ensemble 30%, MP 25%, EWMA 25%, Fourier 20% | Consensus score weighting |

Works with any Yahoo Finance symbol: US equities, ETFs, crypto (BTC-USD), indices (^GSPC).

---

## Derived from

Adapts the four-method detection architecture from a CPM anomaly detection system built for recruitment marketing (see `CPM_ANOMALY_DETECTION_SPEC (1).md`), re-engineered for general-purpose stock market surveillance with actionable trading signals.
