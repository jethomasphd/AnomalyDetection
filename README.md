# RG Anomaly Detection Suite

**Author:** Jacob E. Thomas, PhD | Results Generation

An in-house anomaly detection system applied to securities adjacent to recruitment marketing, advertising platforms, AI infrastructure, and market benchmarks. Four independent statistical methods analyze each ticker daily, identify anomalous behavior, and translate it into **actionable trading signals** — Buy, Sell, Long, Short, Reduce, or Watch.

Built for decision-makers who need clear, actionable intelligence without deep statistical expertise. Updated automatically every trading day with **incremental processing** — each run preserves previous signals and highlights what's new.

**[View the live dashboard](https://jethomasphd.github.io/AnomalyDetection/)**  |  **[Read the User Manual](USERMANUAL.md)**

---

## How it works

Four detection methods run independently against each ticker. When multiple methods flag the same date, the system derives a signal based on price deviation and momentum trajectory.

| Method | The question it answers |
|--------|------------------------|
| **Fourier Transform** | Has the *rhythm* of this stock changed? |
| **Matrix Profile (STUMPY)** | Is this stock doing something it's *never done before*? |
| **Statistical Ensemble** | Do Z-scores, seasonal decomposition, and Isolation Forest all agree? |
| **EWMA Trend Analysis** | Is this stock's *momentum* abnormal? |

## Signals

| Signal | When it fires | What to do |
|--------|---------------|------------|
| **Buy** | Oversold + selling pressure fading | Mean-reversion long targeting the moving average |
| **Sell** | Overbought + buying pressure fading | Take profits or tighten stops |
| **Long** | Accelerating upward momentum | Ride the trend with a trailing stop |
| **Short** | Accelerating downward momentum | Protective positions or short exposure |
| **Reduce** | Structural regime change | Cut position size until the new pattern clarifies |
| **Watch** | Anomaly detected, direction unclear | Monitor for follow-through |

## Watchlist

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
python -m anomaly_detection
```

The dashboard opens at `docs/index.html`. Signal data is written to `data/alerts.json`.

For custom runs:

```bash
# Specific tickers
python -m anomaly_detection --tickers "AAPL,MSFT,GOOGL,TSLA"

# High sensitivity, 6-month window
python -m anomaly_detection --sensitivity high --lookback 180
```

## Automated runs

GitHub Actions runs the full pipeline every weekday at 6:00 PM UTC (after US market close), commits results, and deploys the dashboard to GitHub Pages.

**Incremental by default:** Each run loads previous `alerts.json`, merges new detections, and sorts by date (newest first). Fresh signals get a **NEW** badge. Historical signals are preserved and dimmed. No data is lost between runs.

**Setup:** Repo settings > Pages > Source > **GitHub Actions**.

---

## Project structure

```
anomaly_detection/
  config.py              # Tickers, names, sectors, all tunable parameters
  data_fetch.py          # Yahoo Finance API + feature engineering
  pipeline.py            # 5-stage orchestration
  alerts.py              # Signal derivation (Buy/Sell/Long/Short/Reduce/Watch)
  detection/
    engine.py            # Consensus scoring across all 4 methods
    fourier.py           # Frequency-domain structural change
    matrix_profile.py    # STUMPY novelty detection
    ensemble.py          # Z-score + seasonal decomposition + Isolation Forest
    ewma.py              # Trend deviation + trajectory classification
  visualization/
    charts.py            # Plotly interactive charts
    dashboard.py         # Jinja2 HTML rendering
    templates/
      dashboard.html     # Dashboard template (GitHub Pages)
```

---

## Provenance

Adapts the four-method anomaly detection architecture originally developed for CPM monitoring in recruitment marketing campaigns, re-engineered for general-purpose securities surveillance. See the [User Manual](USERMANUAL.md) for full technical details, configuration reference, and signal derivation logic.

---

*Results Generation — Jacob E. Thomas, PhD*
