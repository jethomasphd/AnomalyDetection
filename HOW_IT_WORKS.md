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

## The Backtest Protocol — Invest/Divest Portfolio Model

Implemented in `anomaly_detection/backtest.py`, consuming the **full signals
ledger** (never the capped alerts.json). There are no shorts and no notional
side-bets — the simulation moves real, conserved capital:

1. **Portfolio** — $PORTFOLIO_CAPITAL (100k) starts 100% in the baseline
   (`BACKTEST_BASELINE_TICKER`, SPY). Every dollar is either in the baseline
   or in a signal position at all times.
2. **Invest** — an entry signal (`BACKTEST_ENTRY_SIGNALS`) moves a
   $BACKTEST_UNIT_DOLLARS slice from the baseline into the ticker at the
   close of the **first bar strictly after** `detected_at`. A signal exists
   only after that evening's close — no same-bar fills, no backdated
   entries. If the baseline holds less than half a slice, the signal is
   skipped and counted (`n_skipped_no_capital`); otherwise it invests
   min(slice, available). Capital is conserved, never invented.
3. **Divest** (earliest wins) — BUY slices return when the close touches the
   trend target frozen at detection time; any slice returns when the first
   SELL/SHORT fires on its ticker (bearish signals move capital OUT — they
   never open shorts); the time stop (`BACKTEST_MAX_HOLD_TRADING_DAYS`)
   returns whatever remains; still-open slices are marked at the last close.
4. **Costs** — `BACKTEST_COST_BPS_PER_SIDE` per stock transaction (buy and
   sell). Baseline trades are treated as frictionless (large index ETFs
   trade at ~1bp spreads).
5. **Benchmark** — the identical capital left 100% in the baseline. Strategy
   and benchmark share the same starting dollar and the same calendar, so
   `excess_return_pct` isolates exactly what the signal overlay added.
6. **Reporting** — Sharpe and max drawdown from the daily portfolio value
   (a real capital base); win rate / profit factor / holds from closed
   round trips; everything split by provenance (walk-forward vs live).

### Why these defaults

Measured on this universe (130 tickers, Nov 2024 anchor), reproducible from
the committed ledger:

- **Why invest on washouts:** extreme below-trend stretches rebounded +2.3%
  mean (+3.3% median) over the next 10 sessions; extreme above-trend
  stretches drifted ~0%. Bearish signals therefore carry exit information,
  not shortable edge — which is why they divest instead of shorting.
- **Entry-set and baseline choices** are fixed by a split-half robustness
  study run through the production engine (excess vs baseline must be
  positive in BOTH halves of the window) — see the table below, regenerated
  whenever the rules change.

**Split-half robustness study** (130-ticker universe, complete ledger,
production engine; H1/H2 = excess vs baseline earned in each half of the
window — the acceptance bar is positive in BOTH):

| Variant | Trades | Strategy | Baseline | Excess | H1 | H2 | Verdict |
|---|---|---|---|---|---|---|---|
| BUY+LONG entries, SPY baseline | 118 | +41.5% | +29.6% | +11.9pp | **−0.7pp** | +9.8pp | fails H1 |
| **BUY-only entries, SPY baseline** | **65** | **+41.1%** | **+29.6%** | **+11.5pp** | **+7.2pp** | **+1.7pp** | **ACCEPTED** |
| BUY+LONG entries, BIL baseline | 112 | +18.6% | +6.5% | +12.1pp | **−1.7pp** | +13.0pp | fails H1 |
| BUY-only entries, BIL baseline | 63 | +19.5% | +6.5% | +12.9pp | +9.6pp | +2.5pp | passes (reference) |

Adding LONG entries roughly doubles the trade count and adds no excess —
momentum entries spend the capital that washout entries use better. LONG
remains an informational momentum flag; only BUY invests. The SPY baseline is
a philosophy choice ("idle capital owns the market"), not a fitted parameter;
the BIL row shows the cash-parked view leads to the same entry-set decision.

Known limitations, stated rather than hidden: fills at closes (no intraday),
dividends only via adjusted closes, baseline assumed frictionless.

**Corporate actions (price-basis reconciliation).** Yahoo back-adjusts the
ENTIRE price history after a split or distribution, but frozen ledger rows
keep the dollar basis of the fetch that wrote them — after a 4:1 split, a
frozen close of $782.17 and a fresh close of $195.54 describe the same bar.
Every run therefore compares the frozen closes against the current fetch
(`adjustments.py`): each backtest target is translated into the current
basis via the signal bar's close in both bases (exact for any retroactive
rescale, so trade outcomes are invariant to when the backtest runs), and
tickers whose basis broke are flagged in `run_health.json` and on the
dashboard, with affected signal rows carrying a basis badge. The ledger
itself is never rewritten. Ordinary dividend re-adjustments sit far inside
the detection tolerance (`PRICE_BASIS_TOLERANCE`) and shift targets only
microscopically.

## Run Health & History

Every run writes `data/run_health.json` (coverage %, per-ticker fetch failures,
stale feeds, price-basis breaks, bars scored, duration) — surfaced as banners
on the dashboard — and appends a summary to `data/history/run_<date>.json`
with `index.json` rebuilt. Fetches retry 3x with exponential backoff before a
ticker is declared missing for the day; a missing ticker's verdicts simply
resume at the next successful fetch (the watermark waits).

**Stale-feed watchdog.** A ticker whose last `STALE_FEED_MIN_BARS` closes are
identical to the cent is treated as a frozen upstream feed, not a quiet
market: its new bars are kept OUT of the frozen record (its watermark does
not advance, so the bars are re-scored once the feed moves again), and the
condition is flagged in run health and on the dashboard. A dead feed can
never mint permanent verdicts.

**Proof-of-run metadata.** `alerts.json` carries a `run` block (bars scored,
latest bar date) and a `ticker_status` block (each ticker's current close and
date, stale/basis flags) refreshed every run, so a quiet day with zero new
signals is distinguishable from a job that only re-stamped the file — and a
frozen signal-row price is never mistaken for the model's current price.

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
