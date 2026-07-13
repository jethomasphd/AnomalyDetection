"""Price-basis reconciliation and feed-health checks.

The ledger freezes verdicts *and dollar values* at detection time, while
every run re-fetches the price history with auto_adjust=True. Those two
facts collide on corporate actions: when a ticker splits (or pays a large
dividend), the data source rescales the ENTIRE fetched history, but the
frozen rows keep the price basis of the fetch that wrote them. After a
4:1 split, a frozen close of $782.17 and a freshly fetched close of
$195.54 describe the exact same bar.

This module makes that divergence explicit instead of letting it silently
corrupt downstream consumers:

  * `bar_basis_factor` — per-bar frozen/current ratio, the exact rescale
    needed to translate a frozen dollar value into today's basis. Used by
    the backtest so a frozen trend target stays touchable after a split.
  * `detect_price_basis_breaks` — per-ticker report of frozen bars whose
    basis no longer matches the current fetch (dashboard + run health).
  * `detect_stale_feeds` — flags tickers whose series has flatlined (a
    frozen upstream feed), so dead data is surfaced and never written
    into the ledger as if it were real trading.

Nothing here ever rewrites the ledger: frozen rows stay frozen; consumers
are handed the factor they need to interpret them correctly.
"""

import logging

import pandas as pd

from .config import PRICE_BASIS_TOLERANCE, STALE_FEED_MIN_BARS

logger = logging.getLogger(__name__)


def frozen_close_from_details(details: dict) -> float | None:
    """Recover the detection-time close from a signal's frozen rationale.

    Newer rows store `close` directly. Older rows carry only the frozen
    trend value and the percent deviation from it, which determine the
    close algebraically: close = ewma * (1 + deviation_pct/100).
    """
    if not details:
        return None
    close = details.get("close")
    if close:
        return float(close)
    ewma = details.get("ewma_value")
    dev_pct = details.get("deviation_pct")
    if ewma and dev_pct is not None:
        return float(ewma) * (1.0 + float(dev_pct) / 100.0)
    return None


def bar_basis_factor(frozen_close: float | None, current_close: float | None) -> float | None:
    """frozen/current ratio for the SAME bar — 1.0 means the basis is unchanged.

    This is exact for any retroactive re-adjustment (splits, dividends):
    dividing a frozen dollar value by this factor expresses it in the
    current fetch's basis.
    """
    if not frozen_close or not current_close or current_close <= 0 or frozen_close <= 0:
        return None
    return float(frozen_close) / float(current_close)


def _close_lookup(results: pd.DataFrame) -> dict[str, dict[str, float]]:
    """{ticker: {date_str: close}} from a results/price frame."""
    out: dict[str, dict[str, float]] = {}
    for ticker, grp in results.groupby("Ticker"):
        dates = pd.to_datetime(grp["Date"]).dt.strftime("%Y-%m-%d")
        out[str(ticker)] = dict(zip(dates, grp["Close"].astype(float)))
    return out


def detect_price_basis_breaks(
    results: pd.DataFrame,
    reference_closes: dict[tuple[str, str], float],
    tolerance: float = PRICE_BASIS_TOLERANCE,
) -> dict[str, dict]:
    """Compare frozen ledger closes against the current fetch, per ticker.

    `reference_closes` maps (ticker, date) -> close as frozen at detection
    time. Returns {ticker: report} ONLY for tickers where at least one
    overlapping bar's basis deviates beyond `tolerance`:

        {"factor": 4.0,             # most-diverged frozen/current ratio
         "n_bars_affected": 6,      # frozen bars whose basis is off
         "n_bars_checked": 6,
         "last_affected_date": "2026-06-01"}

    A 4:1 split shows up as factor≈4.0 on every pre-split frozen bar; a
    routine dividend re-adjustment stays inside tolerance and is ignored.
    """
    if results.empty or not reference_closes:
        return {}
    current = _close_lookup(results)

    per_ticker: dict[str, list[tuple[str, float]]] = {}
    for (ticker, date), frozen in reference_closes.items():
        cur = current.get(ticker, {}).get(date)
        factor = bar_basis_factor(frozen, cur)
        if factor is not None:
            per_ticker.setdefault(ticker, []).append((date, factor))

    breaks: dict[str, dict] = {}
    for ticker, obs in per_ticker.items():
        affected = [(d, f) for d, f in obs if abs(f - 1.0) > tolerance]
        if not affected:
            continue
        worst = max(affected, key=lambda x: abs(x[1] - 1.0))
        breaks[ticker] = {
            "factor": round(worst[1], 4),
            "n_bars_affected": len(affected),
            "n_bars_checked": len(obs),
            "last_affected_date": max(d for d, _ in affected),
        }
        logger.warning(
            "Price-basis break on %s: %d/%d frozen bars diverge from the current "
            "fetch (factor ~%.4g, last affected %s) — corporate action suspected. "
            "Frozen dollar values are basis-translated for display and backtest.",
            ticker, len(affected), len(obs), worst[1], breaks[ticker]["last_affected_date"],
        )
    return breaks


def trailing_flat_run(closes: pd.Series) -> int:
    """Length of the run of identical closes at the END of the series.

    1 means the latest close differs from the one before it (a moving,
    healthy series); N means the last N bars printed the same close.
    """
    vals = closes.dropna().round(4).tolist()
    if not vals:
        return 0
    run = 1
    for prev, cur in zip(reversed(vals[:-1]), reversed(vals[1:])):
        if prev != cur:
            break
        run += 1
    return run


def detect_stale_feeds(
    df: pd.DataFrame,
    min_bars: int = STALE_FEED_MIN_BARS,
) -> dict[str, int]:
    """Flag tickers whose series has flatlined at the tail.

    A real equity/fund series never prints the same close `min_bars`
    sessions in a row; a frozen upstream feed does exactly that. Returns
    {ticker: trailing_flat_run} for flagged tickers. The pipeline keeps
    these tickers OUT of the frozen record for the run (bars are re-scored
    once the feed moves again), so a dead feed can never mint permanent
    verdicts.
    """
    if df.empty:
        return {}
    stale: dict[str, int] = {}
    for ticker, grp in df.groupby("Ticker"):
        run = trailing_flat_run(grp.sort_values("Date")["Close"])
        if run >= min_bars:
            stale[str(ticker)] = run
            logger.warning(
                "Stale feed suspected for %s: last %d bars printed an identical "
                "close — excluding its new bars from this run's frozen record.",
                ticker, run,
            )
    return stale


def compute_ticker_status(
    results: pd.DataFrame,
    basis_breaks: dict[str, dict] | None = None,
    stale_feeds: dict[str, int] | None = None,
) -> dict[str, dict]:
    """Per-ticker current-price context for alerts.json and the dashboard.

    This is deliberately a VIEW: it is recomputed every run from the fresh
    fetch and never merged into the frozen signal rows. It exists so a
    reader of alerts.json (or the dashboard) can always answer "what is
    this ticker at NOW, and on which bar?" next to any frozen verdict.
    """
    status: dict[str, dict] = {}
    if results.empty:
        return status
    basis_breaks = basis_breaks or {}
    stale_feeds = stale_feeds or {}
    for ticker, grp in results.groupby("Ticker"):
        g = grp.sort_values("Date")
        last = g.iloc[-1]
        t = str(ticker)
        entry = {
            "last_close": round(float(last["Close"]), 2),
            "last_date": pd.to_datetime(last["Date"]).strftime("%Y-%m-%d"),
            "stale_feed": t in stale_feeds,
        }
        if t in stale_feeds:
            entry["stale_bars"] = stale_feeds[t]
        if t in basis_breaks:
            entry["price_basis"] = basis_breaks[t]
        status[t] = entry
    return status
