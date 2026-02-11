# User Manual — RG Anomaly Detection Suite

**Author:** Jacob E. Thomas, PhD | Results Generation

---

## Purpose

This system monitors securities that are adjacent to the recruitment marketing industry and informative to our competitive landscape. It runs four independent anomaly detection algorithms against each ticker every trading day, identifies statistically unusual behavior, and translates those anomalies into **actionable trading signals** — Buy, Sell, Long, Short, Reduce, or Watch.

The goal is straightforward: surface the moments that matter. When a staffing competitor's stock is doing something it has never done before, when an ad platform's momentum shifts structurally, when a benchmark index breaks from its historical rhythm — this system flags it, explains it in plain English, and tells you what to do about it.

Everything runs automatically via GitHub Actions and publishes to a live dashboard on GitHub Pages.

### Incremental Processing

The system preserves signals across runs. When the pipeline executes:

1. **Previous alerts are loaded** from `data/alerts.json` before new detection begins.
2. **New alerts are generated** from the current detection run and tagged with a **NEW** badge.
3. **Alerts are merged** — new signals take precedence for the same (ticker, date) pair; previous signals that are no longer in the current window are preserved as historical context.
4. **Signals are sorted by date** — the most recent detections appear at the top of the dashboard, so you always see what's new first.
5. **The alert history is capped at 200 entries** to prevent unbounded growth while retaining meaningful context.

This means you can check the dashboard daily or weekly and immediately see what changed since your last visit. Historical signals remain visible (slightly dimmed) for reference, while fresh detections are highlighted with an orange **NEW** badge.

---

## The Watchlist

The default watchlist is curated around our industry and adjacent sectors:

| Sector | Companies | Why we watch them |
|--------|-----------|-------------------|
| **Staffing & Recruitment** | ZipRecruiter (ZIP), Kelly Services (KELYA), ASGN Inc. (ASGN), ManpowerGroup (MAN) | Direct competitors and industry bellwethers. Anomalous price action here often precedes earnings surprises, leadership changes, or shifts in labor market demand. |
| **Market Benchmarks** | S&P 500 (^GSPC), Nasdaq-100 (^NDX) | Baseline context. Distinguishes stock-specific anomalies from broad market moves. If the S&P 500 itself is anomalous, individual stock signals should be interpreted differently. |
| **Advertising Platforms** | The Trade Desk (TTD), Meta Platforms (META), Alphabet (GOOGL) | Adjacent to recruitment marketing spend. These platforms are where job advertising dollars flow. Structural shifts in their stock behavior can signal changes in digital ad pricing, platform strategy, or advertiser demand. |
| **AI Infrastructure** | NVIDIA (NVDA), Microsoft (MSFT) | The infrastructure layer powering LLM-driven recruitment tools. Anomalies here can signal shifts in the AI buildout that will eventually affect our technology stack and competitive positioning. |

The watchlist is fully customizable. Any Yahoo Finance symbol works — US equities, ETFs, indices, even crypto.

---

## Reading the Dashboard

### At a Glance

The top of the dashboard shows four summary statistics:
- **Tickers Monitored** — how many securities are in the current run
- **Anomalies Detected** — total anomalous days found across all tickers (over the lookback window)
- **Actionable Signals** — the subset of anomalies that translate into a clear Buy, Sell, Long, or Short recommendation
- **Lookback Window** — how many trading days of history were analyzed (default: 365)

### The Scoreboard

A horizontal bar chart ranks every ticker by its recent anomaly score (5-day average). Tickers that need attention are at the top, colored by severity. This answers: *"Where should I look first?"*

### Trading Signals

This is the core output. Each row represents a detected anomaly that has been translated into a trading signal:

| Column | What it tells you |
|--------|-------------------|
| **Signal** | The recommended action — color-coded pill showing Buy, Sell, Long, Short, Reduce, or Watch |
| **Confidence** | How many detection methods independently agree — Strong (3-4), Moderate (2), or Developing (1) |
| **Ticker** | The stock symbol and full company name |
| **Date** | When the anomaly occurred |
| **Close** | The closing price on that date |
| **Methods** | Visual indicator (filled dots) showing how many of the 4 detection methods flagged this date |
| **What to do & why** | Plain-English explanation: what the stock is doing, why it matters, and what action to consider |

**Signal types explained:**

| Signal | Color | When it fires | What it means |
|--------|-------|---------------|---------------|
| **Buy** | Green | Stock is far below its trend and selling pressure is fading | Mean-reversion opportunity. The stock appears oversold. Consider entering a long position targeting the moving average. |
| **Sell** | Red | Stock is far above its trend and buying pressure is fading | The rally may be exhausting. Consider taking profits or tightening stops. |
| **Long** | Teal | Stock is breaking above trend with accelerating momentum | Trend-following opportunity. Momentum is building — ride the wave with a trailing stop. |
| **Short** | Orange | Stock is breaking below trend with accelerating momentum | Downward momentum is strengthening. Consider protective positions or short exposure. |
| **Reduce** | Amber | Structural regime change detected (Fourier + Matrix Profile agree) | The stock's behavior has fundamentally shifted. Reduce position size until the new pattern clarifies. |
| **Watch** | Blue | Anomaly detected but no clear directional signal | Something unusual is happening, but it is too early to act. Monitor for follow-through. |

### Ticker Deep Dive

Click any ticker button to see its full analysis:

1. **Main chart** (top) — Price line with the 20-day EWMA trend overlay. Color-coded circles mark anomaly dates directly on the price line (green = Buy, red = Sell, etc.). Below the price, a bar chart shows the consensus anomaly score over time.

2. **Method detail charts** (2x2 grid below) — Each of the four detection methods gets its own panel:
   - **Fourier Transform** — "Has the rhythm changed?" Shows spectral divergence over time.
   - **Matrix Profile** — "Never-before-seen pattern?" Shows nearest-neighbor distance (higher = more novel).
   - **Statistical Ensemble** — "Do independent tests agree?" Stacked area showing the three component scores (Z-score, seasonal, Isolation Forest).
   - **EWMA Trend** — "Is momentum abnormal?" Price vs. EWMA on top, deviation percentage bars below.

---

## The Four Detection Methods

Each method looks for a different type of anomaly. When multiple methods independently flag the same date, confidence increases.

### 1. Fourier Transform — Frequency-Domain Structural Change

Every stock has a characteristic oscillation pattern. The Fourier Transform decomposes the price series into frequency components and measures whether the energy distribution across those frequencies has shifted from the historical baseline. This detects *structural regime changes* — the stock is behaving in a fundamentally different way.

- **Window:** 60-day sliding window compared against the full-history baseline
- **Metric:** Symmetric KL divergence between local and historical frequency spectra
- **Best at catching:** Transitions from choppy to trending behavior, volatility regime shifts, structural breaks that other methods miss

### 2. Matrix Profile (STUMPY) — Subsequence Novelty Detection

For every recent 10-day window of price action, the algorithm asks: *"What is the most similar 10-day window in this stock's entire history?"* If even the best match is poor, the current pattern is genuinely unprecedented.

- **Algorithm:** STUMPY (Scalable Time series Unsupervised Matrix Profile)
- **Subsequence length:** 10 trading days
- **Best at catching:** First-time moves, breakouts into entirely new price territory, earnings reactions with no historical analog

### 3. Statistical Ensemble — Three Independent Tests

Three complementary statistical approaches, each normalized and weighted:

| Component | Weight | What it measures |
|-----------|--------|------------------|
| Z-Score | 40% | How many standard deviations the price is from its rolling 60-day mean |
| Seasonal Decomposition (STL) | 30% | The unexplained residual after removing trend and weekly seasonality |
| Isolation Forest | 30% | Multivariate outlier detection across price level, daily return, and 20-day volatility simultaneously |

- **Best at catching:** Statistical outliers, unusual combinations of price/return/volatility that no single metric would flag

### 4. EWMA Trend Analysis — Momentum Deviation

The Exponentially Weighted Moving Average (20-day span) creates a responsive trend line. The system measures how far price has deviated from this trend and classifies the *trajectory* of that deviation:

| Trajectory | What it means |
|------------|---------------|
| **Breakout** | Deviation exceeds 80% of the historical range — extreme move |
| **Accelerating** | Deviation is increasing (slope > 0.02) — momentum building |
| **Decelerating** | Deviation is decreasing (slope < -0.02) — momentum fading |
| **Normal** | Deviation is stable — no unusual trajectory |

- **Best at catching:** Overextended rallies and selloffs, momentum reversals, stocks drifting persistently from trend
- **Key role:** Trajectory classification is the primary driver of signal direction (Buy/Sell vs. Long/Short)

---

## How Signals Are Derived

The signal derivation logic combines two dimensions:

1. **Deviation magnitude** — How far is the price from its 20-day EWMA? (measured as a percentage)
2. **Momentum trajectory** — Is the deviation accelerating, decelerating, or breaking out?

The decision tree:

```
IF price is far below trend AND momentum is decelerating:
    → BUY (mean-reversion: oversold, selling exhaustion)

IF price is far above trend AND momentum is decelerating:
    → SELL (mean-reversion: overbought, buying exhaustion)

IF price is below trend AND momentum is accelerating downward:
    → SHORT (trend-following: downward momentum building)

IF price is above trend AND momentum is accelerating upward:
    → LONG (trend-following: upward momentum building)

IF Fourier AND Matrix Profile both flag structural change:
    → REDUCE EXPOSURE (regime change: unprecedented structural shift)

OTHERWISE:
    → WATCH (anomaly detected, no clear directional signal)
```

**Confidence** is determined by method agreement:
- **Strong** — 3 or 4 of 4 methods independently flag the same date
- **Moderate** — 2 of 4 methods agree
- **Developing** — 1 method flags, but the consensus score is elevated

---

## Consensus Scoring

The four individual method scores are combined into a single consensus score using a weighted average:

| Method | Weight | Rationale |
|--------|--------|-----------|
| Ensemble | 30% | Three independent sub-methods provide the broadest statistical coverage |
| Matrix Profile | 25% | Novelty detection catches what statistical methods cannot |
| EWMA | 25% | Most directly actionable — deviation and trajectory drive signal direction |
| Fourier | 20% | Structural detection is powerful but produces fewer signals |

A day is flagged as anomalous when:
- Two or more individual methods flag it, **OR**
- The consensus score exceeds the 97.5th percentile of its full historical distribution

---

## Running the System

### Automatic (recommended)

The system runs automatically every weekday at 6:00 PM UTC (after US market close) via GitHub Actions. Results are committed to the repository and the dashboard is deployed to GitHub Pages. No manual intervention required.

### Manual — via GitHub Actions

1. Navigate to **Actions** > **Stock Anomaly Detection**
2. Click **Run workflow**
3. Optionally specify custom tickers, sensitivity, or lookback window
4. Wait for the run to complete (~90 seconds)
5. View the updated dashboard on GitHub Pages

### Manual — local execution

```bash
# Install dependencies (one-time)
pip install -r requirements.txt

# Run with defaults
python -m anomaly_detection

# Custom tickers
python -m anomaly_detection --tickers "AAPL,TSLA,AMZN"

# High sensitivity, 6-month lookback
python -m anomaly_detection --sensitivity high --lookback 180

# Low sensitivity (only extreme anomalies)
python -m anomaly_detection --sensitivity low
```

### Output files

| File | Description |
|------|-------------|
| `docs/index.html` | The interactive dashboard — open in any browser |
| `data/alerts.json` | Structured signal data in JSON format — **persisted across runs** for incremental processing |
| `data/stock_data.csv` | Raw price data with computed features (regenerated each run) |
| `data/detection_results.csv` | Full detection results with all method scores (regenerated each run) |

**Note:** `alerts.json` now includes additional fields per signal: `run_date` (when the signal was last evaluated), `is_new` (whether it appeared in the most recent run), and `first_detected` (when the signal was first seen). The file also includes a top-level `new_signals` count.

---

## Configuration Reference

All parameters live in `anomaly_detection/config.py`:

| Parameter | Default | What it controls |
|-----------|---------|------------------|
| `DEFAULT_TICKERS` | 11 tickers (see watchlist above) | Which securities to analyze |
| `TICKER_NAMES` | Company name mapping | Display names shown in dashboard and signals |
| `TICKER_SECTORS` | Sector groupings | Sector labels for each ticker |
| `DEFAULT_LOOKBACK_DAYS` | 365 | How many days of history to fetch from Yahoo Finance |
| `DEFAULT_SENSITIVITY` | medium | Detection threshold — low / medium / high |
| `METHOD_WEIGHTS` | Ensemble 30%, MP 25%, EWMA 25%, Fourier 20% | How individual method scores are weighted in the consensus |
| `EWMA_SPAN` | 20 | EWMA lookback (roughly one trading month) |
| `MP_SUBSEQUENCE_LENGTH` | 10 | Matrix Profile window size (two trading weeks) |
| `FOURIER_TOP_K` | 5 | Number of frequency components to track |
| `ENSEMBLE_WEIGHTS` | Z-Score 40%, Seasonal 30%, IForest 30% | Sub-method weights within the ensemble |

### Sensitivity Presets

| Level | Percentile Threshold | Z-Score Threshold | Behavior |
|-------|---------------------|-------------------|----------|
| **Low** | 99.5th | 3.0 | Only the most extreme anomalies. Fewer signals, highest confidence. |
| **Medium** | 97.5th | 2.5 | Balanced. The default for daily monitoring. |
| **High** | 95.0th | 2.0 | Sensitive. Catches early-stage signals. More noise, but earlier detection. |

### Adding new tickers

1. Add the Yahoo Finance symbol to `DEFAULT_TICKERS` in `config.py`
2. Add the company name to `TICKER_NAMES`
3. Add the sector to `TICKER_SECTORS`
4. Run the pipeline — the system handles everything else

Any valid Yahoo Finance symbol works: US equities (`AAPL`), ETFs (`SPY`), indices (`^GSPC`, `^DJI`), crypto (`BTC-USD`), international (`TSM`, `BABA`).

---

## Architecture

```
                    Yahoo Finance API
                          |
                    [1. Fetch Data]
                          |
                    [2. Compute Features]
                    (returns, volatility, z-scores)
                          |
              +-----------+-----------+
              |           |           |
         [Fourier]   [Matrix     [Ensemble]   [EWMA]
                     Profile]
              |           |           |           |
              +-----------+-----------+-----------+
                          |
                    [3. Consensus Scoring]
                    (weighted average, 2+ method agreement)
                          |
                    [4. Signal Derivation]
                    (deviation + trajectory → Buy/Sell/Long/Short)
                          |
              +-----------+-----------+
              |                       |
        [alerts.json]          [Dashboard HTML]
        (structured data)      (GitHub Pages)
```

The pipeline runs in five stages and typically completes in under 90 seconds for the default 11-ticker watchlist.

---

## Provenance

This system adapts the four-method anomaly detection architecture originally developed for CPM (cost-per-media) monitoring in recruitment marketing campaigns. The core statistical methods — Fourier Transform, Matrix Profile, Statistical Ensemble, and EWMA Trend Analysis — were designed to detect anomalous spend patterns in programmatic job advertising.

The architecture has been re-engineered for general-purpose securities surveillance while preserving the same multi-method consensus approach that made it effective at identifying real anomalies in noisy, high-frequency data.

---

*Results Generation — Jacob E. Thomas, PhD*
