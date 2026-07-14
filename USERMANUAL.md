# User Manual — RG Anomaly Detection Suite

**Author:** Jacob E. Thomas, PhD | Results Generation

---

## Purpose

This system monitors securities adjacent to recruitment marketing, advertising platforms, AI infrastructure, and market benchmarks — plus the full top-100 US-listed tickers by market capitalization. It runs four independent anomaly detection algorithms against each ticker every trading day, identifies statistically unusual behavior, and translates those anomalies into **actionable trading signals** — Buy, Sell, Long, Short, Reduce, or Watch.

The goal is straightforward: surface the moments that matter. When a stock is doing something it has never done before, when a platform's momentum shifts structurally, when a benchmark index breaks from its historical rhythm — this system flags it, explains it in plain English, and tells you what to do about it.

Everything runs automatically via GitHub Actions and publishes to a live dashboard on GitHub Pages.

### Incremental Processing

The system scores each new trading day exactly once and never revises a verdict. When the pipeline executes:

1. **The durable record is restored** — the SQLite cache and per-ticker watermarks are rebuilt from the committed ledger (`data/ledger/*.jsonl`), so every run knows precisely which bars have already been judged.
2. **Only new bars produce verdicts** — detection runs over the full anchored history (the detectors need it for their baselines), but only bars strictly newer than each ticker's watermark are persisted. Verdicts are frozen once written: the ledger is append-only, enforced by `INSERT OR IGNORE` and auditable in git history.
3. **New signals are tagged** with an orange **NEW** badge; previously recorded signals are preserved untouched as frozen history (slightly dimmed on the dashboard). Because persistence is edge-only, new and historical signals can never collide — and if legacy data ever conflicts, the frozen record wins.
4. **Signals are sorted newest-first** so you always see what changed since your last visit.
5. **The dashboard view is capped at 200 entries** (`data/alerts.json`); the complete record lives in the signals ledger and is never truncated.

Every run also stamps a `run` block into `data/alerts.json` (bars scored, latest bar date) — so a day with zero new signals is verifiably a quiet market, not a job that failed to run.

---

## The Watchlist

130 tickers across 12 strategic categories — Engines of the Republic, Critical Choke Points, Big Tech, Consumer Leaders, Financial Titans, Healthcare & Pharma, Energy & Commodities, Wall Street's Darlings, The Mega-Cap 100 (completion of the top 100 US-listed names by market capitalization), The Clergy House, Reserve, and UBS Funds. The full registry — ticker, display name, category, sector — lives in `config.TICKER_REGISTRY`; the README shows the category table with examples.

The watchlist is fully customizable. Any Yahoo Finance symbol works — US equities, ETFs, mutual funds, international ADRs.

---

## Reading the Dashboard

### At a Glance

The header states when the dashboard was generated and how many new bars the run scored (through which bar date) — the liveness proof. Below it, five summary statistics:
- **Monitored** — how many securities are in the current run
- **Anomalies** — total anomalous days found across all tickers since the anchor date
- **Actionable** — the subset of anomalies that translate into a clear Buy, Sell, Long, or Short recommendation
- **New This Run** — signals that fired on the latest run (zero on a quiet day is normal)
- **Anchor Date** — the fixed start of the analysis window (default 2024-11-01). Detection and the backtest run from here forward; anchoring (instead of a sliding window) is what keeps historical verdicts stable

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

- **Invest/divest capital model — no shorts, ever.** A $100k portfolio starts 100% in the baseline (SPY). An entry signal (**BUY only** by default — LONG is an informational momentum flag, fixed by the split-half robustness study in HOW_IT_WORKS.md) *invests* a $10k slice into the ticker at the **next session's close** after the signal existed (no same-bar fills, no backdated entries). Bearish signals (SELL/SHORT) *divest* the ticker's slices back to the baseline — they carry exit information, never short positions.
- Slices also return when price touches the trend target frozen at detection time (BUY) or at the 30-bar time stop. If the baseline cannot fund a slice, the signal is skipped and counted — capital is conserved, not invented. 5 bps costs per stock transaction.
- The benchmark (dashed line) is the identical capital left 100% in the baseline, so the strategy-vs-benchmark gap is exactly the value the signal overlay added.
- Frozen trend targets are **basis-translated** across corporate actions (see Data Integrity below), so trade outcomes do not change just because the backtest re-ran after a split.
- Trades are tagged by **provenance**: `backfill` (simulated history — legitimate because detection is causal) vs `live` (signals produced by scheduled runs on new bars, i.e., true out-of-sample). The dashboard reports both separately.

---

## Data Integrity

Three mechanisms (implemented in `anomaly_detection/adjustments.py`) keep the frozen record honest against a live, revisable price feed:

- **Price-basis reconciliation.** Yahoo retroactively rescales a ticker's entire history when it splits, but ledger rows keep the dollar basis of the fetch that wrote them. Every run compares frozen closes against the current fetch per bar; rows recorded at a different basis get a `×N basis` badge on the dashboard, and backtest targets are translated to the current basis via the signal bar's close in both bases — exact for any retroactive rescale. The ledger itself is never rewritten. Ordinary dividend re-adjustments sit inside `PRICE_BASIS_TOLERANCE` and are ignored.
- **Stale-feed watchdog.** A ticker whose feed flatlines (identical closes for `STALE_FEED_MIN_BARS`+ sessions) or stops publishing bars is quarantined: its bars stay out of the frozen record and its watermark holds until the feed recovers, so a dead feed can never mint permanent verdicts. Flagged tickers appear in `run_health.json` and as a dashboard banner.
- **Proof of run.** `alerts.json` carries a `run` block (bars scored, latest bar date) and a `ticker_status` block (current close/date and health flags per ticker), refreshed every run. Signal rows on the dashboard show `now $X (±Y%)` beside the frozen detection-time close.

## Running the System

### Automatic (recommended)

The system runs automatically every weekday at 10:00 PM UTC (safely after the US market close year-round) via GitHub Actions. Each run executes the test suite first — including the causality invariant — then commits results and deploys the dashboard to GitHub Pages. No manual intervention required.

### Manual — via GitHub Actions

1. Navigate to **Actions** > **Stock Anomaly Detection**
2. Click **Run workflow**
3. Optionally specify custom tickers, sensitivity, anchor date, or a ledger reset
4. Wait for the run to complete (~5–6 minutes for the full 130-ticker watchlist)
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
| `TICKER_REGISTRY` | 130 tickers, 12 categories | The canonical watchlist: each entry maps a Yahoo Finance symbol to its display name, category, sector, and fund flag. `DEFAULT_TICKERS`, `TICKER_NAMES`, and `TICKER_SECTORS` are derived from it |
| `SIGNAL_START_DATE` | 2024-11-01 | The fixed anchor date. Detection and the backtest run from here forward; anchoring (not a sliding window) keeps historical verdicts stable |
| `DEFAULT_SENSITIVITY` | medium | Detection threshold — low / medium / high |
| `Z_SCORE_CAP` | 4.0 | The top of the score scale: score = z / 4, so 0.5 = 2σ and 1.0 = 4σ+ |
| `CAUSAL_WARMUP_BARS` | 60 | Bars a detector observes before it may flag anything |
| `METHOD_WEIGHTS` | Ensemble 30%, MP 25%, EWMA 25%, Fourier 20% | How individual method scores are weighted in the consensus |
| `EWMA_SPAN` | 20 | EWMA lookback (roughly one trading month) |
| `MP_SUBSEQUENCE_LENGTH` | 10 | Matrix Profile window size (two trading weeks) |
| `FOURIER_TOP_K` | 5 | Number of frequency components to track |
| `ENSEMBLE_WEIGHTS` | Z-Score 40%, Seasonal 30%, IForest 30% | Sub-method weights within the ensemble |
| `TRADE_MIN_ABS_DEVIATION_PCT` | 1.0 | Materiality gate: minimum % distance from trend before a statistical anomaly may become a trade call |
| `BACKTEST_ENTRY_SIGNALS` | `("BUY",)` | Which bullish signals invest capital (LONG is informational by default — set by the split-half study) |
| `STALE_FEED_MIN_BARS` | 5 | Identical trailing closes (or missing sessions) before a ticker's feed is declared dead and quarantined |
| `STALE_FEED_EXEMPT` | empty | Tickers allowed to print flat closes without being flagged (e.g. a T-bill ETF in a zero-rate regime) |
| `PRICE_BASIS_TOLERANCE` | 0.02 | Frozen-vs-current close divergence (same bar) beyond which a corporate action is declared and frozen dollar values are basis-translated |
| `MODEL_VERSION` | 2.0.0 | Bumped when detection logic changes materially; part of every ledger row's primary key |

### Sensitivity Presets

Thresholds are fixed sigma cutoffs on the ticker's own standardized deviation — never percentiles of the run's output:

| Level | Reversion threshold (BUY/SELL) | Momentum threshold (LONG/SHORT) | Behavior |
|-------|-------------------------------|--------------------------------|----------|
| **Low** | 3.0σ | 2.0σ | Only the most extreme anomalies. Fewer signals, highest confidence. |
| **Medium** | 2.5σ | 1.5σ | Balanced. The default for daily monitoring. |
| **High** | 2.0σ | 1.5σ | Sensitive. Catches early-stage signals. More noise, but earlier detection. |

(The momentum threshold is lower because the trajectory requirement — the stretch must still be building — provides the confirmation that reversion setups get from magnitude.)

### Adding new tickers

1. Add one entry to `TICKER_REGISTRY` in `config.py` — symbol, display name, category, fund flag, sector
2. Run the pipeline — the new ticker is validated, backfilled as a walk-forward simulation over its history, and watermarked; everything else is automatic

Any valid Yahoo Finance symbol works: US equities (`AAPL`), ETFs (`SPY`), mutual funds (`DVRUX`), international ADRs (`TSM`, `BABA`).

---

## Architecture

```
  committed ledger (data/ledger/*.jsonl)     Yahoo Finance API
                 |                                 |
    [0. Restore durable state]           [1. Fetch (anchored history,
    (SQLite cache + watermarks            retry + coverage report)]
     rebuilt on every fresh checkout)              |
                 |                       [2. Compute Features]
                 |                       (returns, volatility, volume)
                 |                                 |
                 |               +--------+--------+--------+
                 |               |        |        |        |
                 |          [Fourier] [Matrix [Ensemble] [EWMA]
                 |                    Profile]
                 |               +--------+--------+--------+
                 |                                 |
                 |               [3. Consensus Scoring — causal]
                 |               (fixed sigma scale, 2+ method agreement)
                 |                                 |
                 +----------> [3a. Reconciliation: price basis + feed health]
                 |                                 |
                 +----------> [3b. Edge-only persistence] (only bars past
                 |            (frozen verdicts, provenance) each watermark)
                 |                                 |
                 |               [4. Signal Derivation]
                 |               (dev_z + trajectory + materiality gate)
                 |                                 |
                 +----------> [5. Walk-forward backtest] (full ledger,
                 |            (next-bar fills, basis-translated targets)
                 |                                 |
                 +<---------- ledger export  [6. Dashboard + alerts.json]
                                             (GitHub Pages)
```

The pipeline runs in seven stages and typically completes in ~5–6 minutes for the full 130-ticker watchlist.

---

## Provenance

This system adapts the four-method anomaly detection architecture originally developed for CPM (cost-per-media) monitoring in recruitment marketing campaigns. The core statistical methods — Fourier Transform, Matrix Profile, Statistical Ensemble, and EWMA Trend Analysis — were designed to detect anomalous spend patterns in programmatic job advertising.

The architecture has been re-engineered for general-purpose securities surveillance while preserving the same multi-method consensus approach that made it effective at identifying real anomalies in noisy, high-frequency data.

---

*Results Generation — Jacob E. Thomas, PhD*
