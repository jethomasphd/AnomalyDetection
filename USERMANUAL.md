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
| **Close** | The closing price on that date, **frozen at detection time**. Underneath, `now $X (±Y%)` shows the ticker's latest fetched close so a weeks-old frozen price is never mistaken for the current one. If a stock split after the verdict was frozen, a purple `×N basis` badge marks that the row's dollar values are in the pre-split price basis (the % is computed basis-adjusted). |
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

**Every method is causal:** the score for any trading day uses only data through that day — never the future. This is enforced by the test suite (`test_causality.py`) and is what makes the walk-forward backtest legitimate and live monitoring identical to it. Every method's raw measurement is standardized against its own trailing history (robust z) and mapped onto one fixed scale: **0.5 = 2 sigma, 0.625 = 2.5 sigma, 1.0 = 4 sigma and beyond**. There are no percentile-of-own-output thresholds: a quiet stock produces a quiet report.

### 1. Fourier Transform — Frequency-Domain Structural Change

Every stock has a characteristic oscillation pattern. The Fourier Transform decomposes the price series into frequency components and measures whether the energy distribution across those frequencies has shifted from the baseline. This detects *structural regime changes* — the stock is behaving in a fundamentally different way.

- **Window:** trailing 60-day spectrum compared against the expanding baseline *up to the same day*
- **Metric:** Symmetric KL divergence between local and baseline frequency-energy profiles
- **Best at catching:** Transitions from choppy to trending behavior, volatility regime shifts, structural breaks that other methods miss

### 2. Matrix Profile (STUMPY) — Subsequence Novelty Detection

For every 10-day window of price action, the algorithm asks: *"What is the most similar 10-day window that came BEFORE this one?"* If even the best past match is poor, the pattern is genuinely unprecedented. This uses STUMPY's incremental **left matrix profile** (`stumpy.stumpi`) — the honest formulation of novelty, which cannot match a pattern against its own future.

- **Algorithm:** STUMPY (Scalable Time series Unsupervised Matrix Profile), left profile
- **Subsequence length:** 10 trading days
- **Best at catching:** First-time moves, breakouts into entirely new price territory, earnings reactions with no historical analog

### 3. Statistical Ensemble — Three Independent Tests

Three complementary statistical approaches, each causal, normalized, and weighted:

| Component | Weight | What it measures |
|-----------|--------|------------------|
| Z-Score | 40% | Today's return relative to the ticker's own trailing 60-day return volatility (excluding today) |
| Seasonal Decomposition | 30% | The residual after removing a one-sided (past-only) trend and weekday pattern learned from prior bars |
| Isolation Forest | 30% | Multivariate outlier detection across return, volatility, volume ratio, and intraday range — the forest is refit walk-forward and never scores bars it trained on |

- **Best at catching:** Statistical outliers, unusual combinations of return/volatility/volume that no single metric would flag

### 4. EWMA Trend Analysis — Momentum Deviation

The Exponentially Weighted Moving Average (20-day span) creates a responsive trend line. The system measures how far price has deviated from this trend, **standardized by that deviation's own trailing volatility** (`dev_z`) — so a 3-sigma stretch means the same thing for a sleepy T-bill fund as for NVIDIA — and classifies the *trajectory* of the stretch:

| Trajectory | What it means |
|------------|---------------|
| **Breakout** | The standardized deviation is at extremes (beyond threshold + 1 sigma) |
| **Extending** | The stretch is growing — price pulling further from trend |
| **Reverting** | The stretch is shrinking — price snapping back toward trend |
| **Stable** | The stretch is holding steady |

- **Best at catching:** Overextended rallies and selloffs, momentum reversals, stocks drifting persistently from trend
- **Key role:** `dev_z` magnitude and trajectory drive signal direction (Buy/Sell vs. Long/Short)

---

## How Signals Are Derived

The signal derivation logic combines three dimensions:

1. **Standardized deviation (`dev_z`)** — how stretched is price from its 20-day EWMA, in units of this ticker's own typical variability?
2. **Momentum trajectory** — is the stretch extending, reverting, breaking out, or stable?
3. **Materiality** — is the move economically meaningful in absolute terms?

The decision tree (medium sensitivity):

```
TRADABLE requires: 2+ methods agree AND |deviation| >= 1% (materiality gate)

IF trajectory is BREAKOUT (climactic extreme):        # fade the overreaction
    dev_z <= -2.5  -> BUY  (capitulation washout: such extremes rebound on average)
    dev_z >= +2.5  -> SELL (blowoff top: such extremes stall or revert)

ELIF trajectory is EXTENDING (stretch still building): # ride the momentum
    dev_z >= +1.5  -> LONG
    dev_z <= -1.5  -> SHORT

ELSE (reverting/stable — stretch fading):              # reversion under way
    dev_z <= -2.5  -> BUY
    dev_z >= +2.5  -> SELL

IF Fourier AND Matrix Profile both flag structural change:
    -> REDUCE EXPOSURE (regime change: unprecedented structural shift)

OTHERWISE:
    -> WATCH (anomaly detected, no tradable directional setup)
```

The fade-the-breakout rule is calibrated to measured behavior: in this universe,
bars stretched more than ~3.5 sigma below trend rebounded +2.3% on average over
the next 10 sessions (the classic short-term overreaction reversal), so the
naive momentum response — shorting a capitulation — is systematically wrong-way.

The materiality gate is why a 4-sigma move of 0.15% in a T-bill ETF shows up as WATCH (it is genuinely unusual *for that fund*) but can never become a trade call.

**Confidence** is determined by method agreement:
- **Strong** — 3 or 4 of 4 methods independently flag the same date
- **Moderate** — 2 of 4 methods agree
- **Developing** — fewer

---

## Consensus Scoring

The four individual method scores are combined into a single consensus score using a weighted average:

| Method | Weight | Rationale |
|--------|--------|-----------|
| Ensemble | 30% | Three independent sub-methods provide the broadest statistical coverage |
| Matrix Profile | 25% | Novelty detection catches what statistical methods cannot |
| EWMA | 25% | Most directly actionable — deviation and trajectory drive signal direction |
| Fourier | 20% | Structural detection is powerful but produces fewer signals |

All four scores share the same fixed sigma scale, so the weights mean what they say. A day is flagged as anomalous when:
- Two or more individual methods flag it, **OR**
- The consensus score crosses the sensitivity cutoff (medium: 0.625, the 2.5-sigma equivalent)

Both cutoffs are fixed and documented — never a quantile of the run's own output.

---

## The Backtest and the Live Record

The Signal Performance section of the dashboard is a **walk-forward simulation** over the full signals ledger:

- **Invest/divest capital model — no shorts, ever.** A $100k portfolio starts 100% in the baseline (SPY). An entry signal *invests* a $10k slice into the ticker at the **next session's close** after the signal existed (no same-bar fills, no backdated entries). Bearish signals (SELL/SHORT) *divest* the ticker's slices back to the baseline — they carry exit information, never short positions.
- Slices also return when price touches the trend target frozen at detection time (BUY) or at the 30-bar time stop. If the baseline cannot fund a slice, the signal is skipped and counted — capital is conserved, not invented. 5 bps costs per stock transaction.
- The benchmark is the identical capital left 100% in the baseline, so the strategy-vs-benchmark gap is exactly the value the signal overlay added.
- The dashed benchmark line is SPY buy-and-hold on the strategy's average deployed capital.
- Trades are tagged by **provenance**: `backfill` (simulated history — legitimate because detection is causal) vs `live` (signals produced by scheduled runs on new bars, i.e., true out-of-sample). The dashboard reports both separately.

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

# High sensitivity
python -m anomaly_detection --sensitivity high

# Rebuild the ledger from scratch (after a detection-regime change)
python -m anomaly_detection --reset

# Low sensitivity (only extreme anomalies)
python -m anomaly_detection --sensitivity low
```

### Output files

| File | Description |
|------|-------------|
| `docs/index.html` | The interactive dashboard — open in any browser |
| `data/ledger/anomalies.jsonl` | **Committed append-only truth**: every anomaly verdict ever recorded |
| `data/ledger/signals.jsonl` | **Committed append-only truth**: every signal ever produced (backtest input) |
| `data/ledger/watermarks.json` | Per-ticker high-water mark of scored bars (edge-only cursor) |
| `data/alerts.json` | Display view for the dashboard (capped at 200, newest first). Also carries a `run` block (bars scored, latest bar date — proof the model ran even on 0-signal days) and a `ticker_status` block (each ticker's current close/date, stale-feed and price-basis flags), both refreshed every run |
| `data/run_health.json` | Latest run's fetch coverage, failures, stale feeds, and price-basis breaks |
| `data/history/run_*.json` | One summary per run + `index.json` |
| `data/stock_data.csv` | Raw price data with computed features (regenerated each run, gitignored) |
| `data/detection_results.csv` | Full detection results with all method scores (regenerated each run, gitignored) |

Each signal carries `run_date`, `is_new`, `first_detected`, `detected_at`, and `provenance` (`backfill` = walk-forward simulated history, `live` = out-of-sample). The SQLite store (`data/anomaly_store.db`) is a local cache rebuilt from the ledger on fresh checkouts.

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
| `STALE_FEED_MIN_BARS` | 5 | Identical trailing closes before a ticker's feed is declared frozen (its new bars stay out of the frozen record until the feed moves) |
| `PRICE_BASIS_TOLERANCE` | 0.02 | Frozen-vs-current close divergence (same bar) beyond which a corporate action is declared and frozen dollar values are basis-translated |

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
