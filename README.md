# Stock Anomaly Detection System

A general-purpose anomaly detection engine for stock market data. Monitors any ticker available on Yahoo Finance using four independent statistical methods, generates severity-ranked alerts, and publishes an interactive dashboard to GitHub Pages.

Built for analysts and decision-makers who need actionable anomaly signals without requiring deep statistical expertise.

---

## How It Works

The system runs four independent detection algorithms on each ticker's price history. When multiple methods agree something is unusual, the system flags it as an anomaly with a confidence-based severity rating.

| Method | What It Detects | Plain-English Question |
|--------|----------------|----------------------|
| **Fourier Transform** | Structural changes in trading patterns | *"Has the rhythm of this stock changed?"* |
| **Matrix Profile** | Novel price patterns with no historical match | *"Is this stock doing something it's never done?"* |
| **Statistical Ensemble** | Z-score outliers + seasonal deviations + ML isolation | *"Do multiple statistical tests agree it's unusual?"* |
| **EWMA Trend** | Abnormal momentum and trend deviation | *"Is this stock's momentum abnormal right now?"* |

### Severity Levels

| Level | Meaning | Methods in Agreement |
|-------|---------|---------------------|
| **CRITICAL** | All 4 methods flag anomaly | 4/4 |
| **HIGH** | Strong agreement across methods | 3/4 |
| **MODERATE** | Multiple signals detected | 2/4 |
| **LOW** | Single method flag or elevated consensus score | 1/4 |

### Sensitivity Presets

| Preset | Percentile Threshold | Best For |
|--------|---------------------|----------|
| `low` | 99.5th | Production monitoring — only extreme events |
| `medium` | 97.5th | General use — balanced signal vs. noise |
| `high` | 95th | Research — catch emerging patterns early |

---

## Quick Start

### 1. Install

```bash
pip install -r requirements.txt
```

### 2. Run

```bash
# Default watchlist (20 major tickers), medium sensitivity
python -m anomaly_detection

# Specific tickers
python -m anomaly_detection --tickers "AAPL,MSFT,GOOGL,TSLA"

# High sensitivity, 6-month lookback
python -m anomaly_detection --sensitivity high --lookback 180
```

### 3. View Results

Open `docs/index.html` in a browser for the interactive dashboard, or check:
- `data/alerts.json` — structured alert data
- `data/detection_results.csv` — full scored dataset
- `data/stock_data.csv` — raw fetched data with features

---

## Automated Runs (GitHub Actions)

The included workflow runs automatically **every weekday at 6:00 PM UTC** (after US market close) and deploys results to GitHub Pages.

To run manually:
1. Go to **Actions** > **Stock Anomaly Detection**
2. Click **Run workflow**
3. Optionally customize tickers, sensitivity, and lookback

### Setup

1. In your repo settings, go to **Pages** > Source > **GitHub Actions**
2. The workflow handles everything else — fetches data, runs detection, commits results, and deploys

---

## Project Structure

```
AnomalyDetection/
├── anomaly_detection/
│   ├── __init__.py
│   ├── __main__.py              # Entry point
│   ├── config.py                # All configuration and presets
│   ├── data_fetch.py            # Yahoo Finance data fetching + feature engineering
│   ├── pipeline.py              # Main orchestration pipeline
│   ├── alerts.py                # Alert generation (JSON, Markdown)
│   ├── detection/
│   │   ├── engine.py            # Orchestrates all 4 methods + consensus scoring
│   │   ├── fourier.py           # Frequency-domain structural change detection
│   │   ├── matrix_profile.py    # STUMPY-based novelty detection
│   │   ├── ensemble.py          # Z-score + Seasonal + Isolation Forest
│   │   └── ewma.py              # Trend deviation and trajectory classification
│   └── visualization/
│       ├── charts.py            # Plotly chart generation
│       ├── dashboard.py         # Jinja2 HTML dashboard renderer
│       └── templates/
│           └── dashboard.html   # GitHub Pages template
├── data/                        # Generated data (gitignored except results)
├── docs/                        # GitHub Pages output (index.html)
├── .github/workflows/
│   └── detect.yml               # Automated daily detection + Pages deploy
├── requirements.txt
└── README.md
```

---

## Customization

### Add/Change Tickers

Edit `DEFAULT_TICKERS` in `anomaly_detection/config.py`, or pass them at runtime:

```bash
python -m anomaly_detection --tickers "NVDA,AMD,INTC,TSM"
```

### Tune Detection Parameters

All parameters are in `anomaly_detection/config.py`:

```python
METHOD_WEIGHTS       # Relative weight of each detection method
EWMA_SPAN            # EWMA smoothing window (default: 20 days)
MP_SUBSEQUENCE_LENGTH  # Matrix profile pattern length (default: 10)
FOURIER_TOP_K        # Number of frequency components (default: 5)
ENSEMBLE_WEIGHTS     # Z-score / Seasonal / Isolation Forest split
```

---

## Data Source

All data is fetched from [Yahoo Finance](https://finance.yahoo.com/) via the `yfinance` library. No API keys required. Supports any ticker symbol available on Yahoo Finance including:
- US equities (AAPL, MSFT, etc.)
- ETFs (SPY, QQQ, XLE, etc.)
- International stocks (available via Yahoo Finance symbols)
- Crypto (BTC-USD, ETH-USD, etc.)
- Indices (^GSPC, ^DJI, etc.)

---

## Derived from

This system adapts the four-method detection architecture originally developed for CPM anomaly detection in recruitment marketing (documented in `CPM_ANOMALY_DETECTION_SPEC (1).md`), re-engineered for general-purpose stock market surveillance.
