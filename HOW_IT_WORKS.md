# How It Works — Stock Anomaly Detection System (v2, Causal Regime)

## The One Rule Everything Hangs On

**Every score computed for bar t uses only bars [0..t]. Nothing later. Ever.**

This property — *causality*, enforced by `anomaly_detection/tests/test_causality.py`
for every detector at every sensitivity — is what makes three claims true at once:

1. **The backtest is real.** When the system backfills history, the verdict it
   records for a past bar is *exactly* the verdict a live run that evening would
   have produced. The historical simulation and the live system follow identical
   rules, so the backfill is a legitimate walk-forward backtest, not a fit to
   hindsight.
2. **Frozen verdicts stay frozen.** Re-scoring a bar after new data arrives
   produces the same answer, so the append-only ledger never fights the model.
3. **Prospective monitoring is the same machine.** "Live" operation is just the
   walk-forward simulation advancing one bar at a time.

## The Four Methods (all causal)

| Method | Raw measurement at bar t | Causality mechanism |
|---|---|---|
| **Fourier** | Divergence between the spectrum of the trailing 60 bars and the spectrum of *all bars up to t* | Expanding baseline ends at t; threshold standardized on trailing history |
| **Matrix Profile** | Distance from the 10-bar pattern ending at t to its nearest neighbor **strictly in the past** (STUMPY *left* matrix profile via `stumpy.stumpi`) | The left profile cannot see the future by construction |
| **Ensemble** | Weighted blend: return z-score (40%), one-sided seasonal-decomposition residual (30%), Isolation Forest (30%) | Trailing volatility (excludes today); weekday means learned from past bars only; forest refit walk-forward on blocks it never scores |
| **EWMA** | Deviation from the 20-day EWMA, divided by that deviation's own trailing volatility (`dev_z`) | Trailing std excludes the current bar |

### One scale for everything

Each method's raw stream is standardized against its own trailing history with a
robust z (median / upper-quantile spread — heavy-tail-safe), then mapped to
**[0, 1] where 0.5 = 2 sigma, 0.625 = 2.5 sigma, 1.0 = 4 sigma+**. No per-ticker
max-normalization (v1 pinned every ticker's worst day at exactly 1.0, even a
T-bill fund's), no percentile-of-own-output thresholds (v1 was forced to flag
~2.5% of bars no matter how quiet the tape). A quiet tape now produces a quiet
report.

`consensus_score` = weighted average (Fourier 0.20, MP 0.25, Ensemble 0.30, EWMA 0.25).
`consensus_anomaly` = **2+ methods flag** OR consensus_score >= sensitivity cutoff
(medium: 0.625 = 2.5-sigma-equivalent). Fixed, documented cutoffs.

### Warmup

Detectors observe `CAUSAL_WARMUP_BARS` (60) + 20 standardization bars before they
may flag. Scores during warmup are 0 — the system is not allowed to call something
abnormal before it has learned what normal looks like.

## Signal Derivation (sigma units + materiality)

`dev_z` = EWMA deviation / its own trailing sigma — so thresholds adapt per ticker.
Trajectory classifies what the stretch is doing: **extending** (growing),
**reverting** (snapping back), **breakout** (extreme), **stable**.

Two regimes, split by what the stretch is doing:

| Regime | Signal | Condition (medium sensitivity) |
|---|---|---|
| **breakout** — climactic extreme | **BUY** / **SELL** | fade it: BUY if dev_z <= -2.5, SELL if dev_z >= +2.5 |
| **extending** — stretch still building | **LONG** / **SHORT** | ride it: LONG if dev_z >= +1.5, SHORT if dev_z <= -1.5 |
| **reverting/stable** — stretch fading | **BUY** / **SELL** | reversion under way: BUY if dev_z <= -2.5, SELL if dev_z >= +2.5 |
| any | **REDUCE** | Fourier AND Matrix Profile both flag (structural break) |
| any | **WATCH** | consensus anomaly without a tradable setup |

**Why fade breakouts?** Measured on this universe (75 tickers, Nov 2024 anchor):
bars stretched more than ~3.5 sigma BELOW trend rebounded +2.3% on average
(+3.3% median) over the next 10 sessions, while extreme above-trend stretches
went nowhere. Chasing a capitulation with a SHORT — what a naive momentum rule
does — is systematically wrong-way; the documented short-term overreaction
reversal applies. Momentum entries are reserved for stretches that are still
BUILDING (extending), before the climax.

**Materiality gate:** a trade call also requires >=2 methods in agreement AND
|deviation| >= `TRADE_MIN_ABS_DEVIATION_PCT` (1%). A 4-sigma move of 0.15% in a
T-bill ETF is genuinely anomalous *for that fund* — it stays a WATCH, and never
enters the trade ledger.

## Storage: the Ledger Is the Truth

```
data/ledger/anomalies.jsonl    append-only, committed by every CI run
data/ledger/signals.jsonl      append-only, committed by every CI run
data/ledger/watermarks.json    per-ticker high-water mark of scored bars
data/anomaly_store.db          SQLite cache, gitignored, rebuilt from ledger
data/alerts.json               display view (capped at 200) for the dashboard
```

CI runners are ephemeral — v1's fatal flaw was keeping the durable store only in
a gitignored SQLite file, so every run started amnesiac and silently re-scored
all of history. v2 commits the ledger; on a fresh checkout
`storage.bootstrap_from_ledger()` reconstitutes the cache, watermarks included.
Git history doubles as the immutability proof: every verdict ever recorded is a
visible appended line in a commit.

### Provenance

Every row is tagged:

- **`backfill`** — produced by the walk-forward simulation over history.
  `detected_at` = bar date (causality makes this honest).
- **`live`** — produced by a scheduled run on a genuinely new bar.
  `detected_at` = run date. This is the out-of-sample record.

The dashboard reports the two populations separately, always.

### Edge-only operation

Each run scores the full anchored window (detectors need history for their
baselines) but **persists verdicts only for bars strictly newer than each
ticker's watermark**. A ticker never seen before is backfilled; a known ticker
gets live rows only. `INSERT OR IGNORE` on primary keys means a written verdict
can never be overwritten.

## The Backtest Protocol

Implemented in `anomaly_detection/backtest.py`, consuming the **full signals
ledger** (never the capped alerts.json):

1. **Entry** — a signal exists only after the close of `detected_at`; the trade
   fills at the close of the **first bar strictly after** `detected_at`.
   No same-bar fills, no backdated entries. Signals newer than the last bar are
   *pending*, not traded.
2. **Exits** (earliest wins) — BUY/SELL: price touches the trend target frozen in
   the signal at detection time; any trade: first opposite-direction signal on
   the ticker (at *its* entry bar); time stop after `BACKTEST_MAX_HOLD_TRADING_DAYS`
   (30) bars; otherwise marked open at the latest close.
3. **Costs** — `BACKTEST_COST_BPS_PER_SIDE` (5 bps) charged on entry and exit.
4. **Sizing** — every signal is an independent $10k unit; same-direction signals stack.
5. **Benchmark** — SPY buy-and-hold scaled to the strategy's average deployed
   capital, drawn on the same chart.
6. **Reporting** — Sharpe and max drawdown from the daily mark-to-market equity
   curve; win rate / profit factor / holding period from closed trades; all
   stats split by provenance (walk-forward vs live).

Known limitations, stated rather than hidden: fills at closes (no intraday),
no borrow fees or market impact, dividends only via adjusted closes, and Yahoo
back-adjusts prices after distributions (frozen verdicts are not retroactively
revised for this — the divergence is microscopic for the large caps tracked).

## Run Health & History

Every run writes `data/run_health.json` (coverage %, per-ticker fetch failures,
duration) — surfaced as a DEGRADED banner on the dashboard when below 100% —
and appends a summary to `data/history/run_<date>.json` with `index.json`
rebuilt. Fetches retry 3x with exponential backoff before a ticker is declared
missing for the day; a missing ticker's verdicts simply resume at the next
successful fetch (the watermark waits).

## Ticker Registry

`config.TICKER_REGISTRY` is the single source of truth: ticker -> name, category,
fund flag, sector. Categories group the watchlist on the dashboard ("Engines of
the Republic", "Critical Choke Points", ...). Yahoo format applies (`BRK-B`, not
`BRK.B`). Add a ticker, and the next run backfills its history as walk-forward
rows without touching anyone else's watermark.

## Dashboard Architecture

Jinja2 (`visualization/templates/dashboard.html`) renders a self-contained
`docs/index.html` for GitHub Pages; Plotly charts are serialized with
`to_plotly_json()` (plain arrays — CDN-compatible). Sections: attention queue
heatmap, signal cards (provenance-aware NEW badges), per-ticker deep dives with
per-method panels, the walk-forward backtest with benchmark overlay and the
trade ledger, and run-health surfacing. Dashboard generation is non-fatal: a
chart bug can never lose a day's verdicts.
