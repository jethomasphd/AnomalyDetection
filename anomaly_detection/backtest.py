"""Walk-forward portfolio backtest — invest/divest capital, never short.

The capital model (how a real allocator would follow the Signal):

  PORTFOLIO  Capital starts 100% in a baseline portfolio (SPY by default —
             config.BACKTEST_BASELINE_TICKER). There are no shorts and no
             notional side-bets: every dollar is either in the baseline or
             in a signal position. The benchmark is, by construction, the
             same capital left 100% in the baseline — so "did the overlay
             add value?" is answered like-for-like.

  INVEST     An entry signal (config.BACKTEST_ENTRY_SIGNALS) divests one
             $BACKTEST_UNIT_DOLLARS slice from the baseline and invests it
             in the ticker at the close of the FIRST bar strictly after
             detected_at (a signal exists only after that evening's close —
             never the same bar, never a backdated price). If the baseline
             holds less than one slice, the signal is SKIPPED and counted:
             capital is conserved, not invented.

  DIVEST     Whichever comes first returns the slice to the baseline:
               - target:        BUY trades exit when the close touches the
                                trend value frozen in the signal
               - divest_signal: the first SELL or SHORT on the ticker
                                (at ITS next-bar entry) — bearish signals
                                mean "get out", they never open shorts
               - time_stop:     BACKTEST_MAX_HOLD_TRADING_DAYS bars
               - still open:    marked at the latest close

  COSTS      BACKTEST_COST_BPS_PER_SIDE charged on each stock transaction
             (buy and sell). Baseline trades are treated as frictionless
             (large index ETFs trade at ~1bp spreads).

Because detection is causal, the 'backfill' part of the ledger is a
legitimate walk-forward simulation and 'live' rows are true out-of-sample;
trades inherit that provenance and are reported separately.
"""

import bisect
import logging
from collections import Counter

import numpy as np
import pandas as pd

from .config import (
    BACKTEST_BASELINE_TICKER,
    BACKTEST_COST_BPS_PER_SIDE,
    BACKTEST_ENTRY_SIGNALS,
    BACKTEST_MAX_HOLD_TRADING_DAYS,
    BACKTEST_UNIT_DOLLARS,
    PORTFOLIO_CAPITAL,
    ticker_display,
)

logger = logging.getLogger(__name__)

# A signal invests min(slice, available baseline); below this fraction of a
# slice it is skipped instead (avoids dust positions; costs make a recycled
# slice land slightly under the nominal unit).
MIN_INVEST_FRACTION = 0.5

BULLISH = {"BUY", "LONG"}          # may invest (subject to BACKTEST_ENTRY_SIGNALS)
BEARISH = {"SELL", "SHORT"}        # always divest triggers, never positions
TARGET_SIGNALS = {"BUY"}           # exit at the frozen trend target


def _build_price_index(results: pd.DataFrame) -> dict[str, dict]:
    """Per-ticker sorted price arrays with O(log n) date lookup."""
    out: dict[str, dict] = {}
    for ticker, grp in results.groupby("Ticker"):
        g = grp[["Date", "Close"]].sort_values("Date").reset_index(drop=True)
        if g.empty:
            continue
        date_strs = pd.to_datetime(g["Date"]).dt.strftime("%Y-%m-%d").tolist()
        out[ticker] = {
            "DateStr": date_strs,
            "Close": g["Close"].to_numpy(dtype=float),
            "_index": {d: i for i, d in enumerate(date_strs)},
        }
    return out


def _entry_index(series: dict, detected_at: str) -> int | None:
    """Index of the first bar STRICTLY AFTER detected_at, or None."""
    i = bisect.bisect_right(series["DateStr"], detected_at)
    return i if i < len(series["DateStr"]) else None


def _price_on_or_before(series: dict, date_str: str) -> float | None:
    i = bisect.bisect_right(series["DateStr"], date_str) - 1
    return float(series["Close"][i]) if i >= 0 else None


def _methods_str(details: dict) -> str:
    methods = []
    if details.get("fourier_score", 0) > 0:
        methods.append("Fourier")
    if details.get("mp_score", 0) > 0:
        methods.append("MatrixProfile")
    if details.get("ensemble_score", 0) > 0:
        methods.append("Ensemble")
    if details.get("ewma_score", 0) > 0:
        methods.append("EWMA")
    return ", ".join(methods) if methods else "—"


def _find_exit(
    series: dict,
    entry_i: int,
    signal: str,
    target: float | None,
    divest_entries: list[int],
    max_hold: int,
) -> tuple[int | None, str]:
    """Earliest divest bar for a slice invested at entry_i (long positions only)."""
    closes = series["Close"]
    n = len(closes)

    j = bisect.bisect_right(divest_entries, entry_i)
    div_i = divest_entries[j] if j < len(divest_entries) else None
    time_i = entry_i + max_hold

    target_i = None
    if signal in TARGET_SIGNALS and target and target > 0:
        scan_end = min(n, time_i + 1, div_i + 1 if div_i is not None else n)
        for k in range(entry_i + 1, scan_end):
            if closes[k] >= target:
                target_i = k
                break

    candidates = [
        (target_i, "target"),
        (div_i, "divest_signal"),
        (time_i if time_i < n else None, "time_stop"),
    ]
    live = [(i, r) for i, r in candidates if i is not None]
    if not live:
        return None, "open"
    return min(live, key=lambda x: x[0])


def compute_backtest(
    results: pd.DataFrame,
    ledger_signals: list[dict],
    capital: float = PORTFOLIO_CAPITAL,
    unit: float = BACKTEST_UNIT_DOLLARS,
    entry_signals: tuple[str, ...] = BACKTEST_ENTRY_SIGNALS,
    baseline_ticker: str = BACKTEST_BASELINE_TICKER,
    max_hold: int = BACKTEST_MAX_HOLD_TRADING_DAYS,
) -> dict:
    """Run the invest/divest portfolio simulation over the full signal ledger."""
    empty = {
        "signal_ledger": [],
        "initial_capital": capital, "final_value": capital,
        "total_gain": 0.0, "total_pct": 0.0,
        "realized_gain": 0.0, "unrealized_gain": 0.0,
        "total_invested": int(capital),
        "n_trades": 0, "n_winning": 0, "n_open": 0, "n_closed": 0,
        "n_pending": 0, "n_skipped_no_capital": 0,
        "start_date": None, "end_date": None,
        "equity_curve": {"dates": [], "equity": [], "drawdown": []},
        "benchmark": {"dates": [], "equity": [], "ticker": baseline_ticker,
                      "return_pct": None},
        "stats": _empty_trade_stats(),
        "provenance_stats": {},
        "exit_reasons": {},
        "cost_bps_per_side": BACKTEST_COST_BPS_PER_SIDE,
        "max_hold_days": max_hold,
        "entry_signals": list(entry_signals),
        "baseline_ticker": baseline_ticker,
        "unit": unit,
    }
    if results.empty or not ledger_signals:
        return empty

    by_ticker = _build_price_index(results)
    baseline = by_ticker.get(baseline_ticker)
    if baseline is None:
        logger.warning("Baseline ticker %s not in results — backtest skipped", baseline_ticker)
        return empty
    all_dates = sorted({d for v in by_ticker.values() for d in v["DateStr"]})
    cost_frac = BACKTEST_COST_BPS_PER_SIDE / 10_000.0

    # ----- Resolve signals to candidate invests and divest triggers -----
    candidates = []          # potential invest events
    divests: dict[str, list[int]] = {}  # ticker -> sorted entry bars of bearish signals
    n_pending = 0
    for sig in ledger_signals:
        s = sig.get("signal")
        ticker = sig["ticker"]
        series = by_ticker.get(ticker)
        if series is None or ticker == baseline_ticker:
            continue
        detected_at = sig.get("detected_at") or sig["date"]
        if s in BEARISH:
            i = _entry_index(series, detected_at)
            if i is not None:
                divests.setdefault(ticker, []).append(i)
            continue
        if s not in BULLISH or s not in entry_signals:
            continue
        i = _entry_index(series, detected_at)
        if i is None:
            n_pending += 1
            continue
        rationale = sig.get("rationale") or {}
        details = rationale.get("details") or {}
        candidates.append({
            "ticker": ticker,
            "signal": s,
            "bar_date": sig["date"],
            "detected_at": detected_at,
            "provenance": sig.get("provenance") or "live",
            "confidence": sig.get("confidence") or "",
            "target": float(details.get("ewma_value") or 0) or None,
            "methods_flagged": int(rationale.get("methods_flagged") or 0),
            "details": details,
            "entry_i": i,
        })
    for v in divests.values():
        v.sort()

    # Exit of each candidate is signal/price-driven only (independent of
    # capital), so it can be precomputed before the capital walk.
    for c in candidates:
        series = by_ticker[c["ticker"]]
        exit_i, reason = _find_exit(
            series, c["entry_i"], c["signal"], c["target"],
            divests.get(c["ticker"], []), max_hold,
        )
        c["exit_i"], c["exit_reason"] = exit_i, reason
        c["entry_date"] = series["DateStr"][c["entry_i"]]
        c["exit_date"] = series["DateStr"][exit_i] if exit_i is not None else None

    candidates.sort(key=lambda c: (c["entry_date"], c["ticker"], c["signal"]))

    # ----- Chronological capital walk: invest only what the baseline holds -----
    base_price0 = float(baseline["Close"][0])
    baseline_shares = capital / base_price0
    bench_shares = capital / base_price0  # benchmark: never touched

    entries_by_date: dict[str, list[dict]] = {}
    for c in candidates:
        entries_by_date.setdefault(c["entry_date"], []).append(c)

    exits_by_date: dict[str, list[dict]] = {}
    trades: list[dict] = []
    skipped: list[dict] = []
    open_positions: list[dict] = []
    seq = 0

    pf_dates, pf_values, bench_values = [], [], []

    for d in all_dates:
        base_px = _price_on_or_before(baseline, d) or base_price0

        # 1) Divest: positions exiting today return capital to the baseline.
        for pos in exits_by_date.pop(d, []):
            series = by_ticker[pos["ticker"]]
            exit_px = float(series["Close"][pos["exit_i"]])
            proceeds = pos["shares"] * exit_px * (1 - cost_frac)
            baseline_shares += proceeds / base_px
            pos["exit_price"] = round(exit_px, 4)
            pos["dollar_gain"] = round(proceeds - pos["unit"], 2)
            pos["pct_change"] = round((exit_px / pos["entry_price_raw"] - 1) * 100, 2)
            pos["status"] = "CLOSED"
            open_positions.remove(pos)

        # 2) Invest: new signals fill at today's close if capital is available.
        # A signal takes min(slice, what the baseline holds); below half a
        # slice it is skipped — capital is conserved, never invented.
        for c in entries_by_date.pop(d, []):
            available = baseline_shares * base_px
            if available < unit * MIN_INVEST_FRACTION:
                skipped.append({"ticker": c["ticker"], "date": c["entry_date"],
                                "signal": c["signal"]})
                continue
            invested = min(unit, available)
            series = by_ticker[c["ticker"]]
            entry_px = float(series["Close"][c["entry_i"]])
            if entry_px <= 0:
                continue
            baseline_shares -= invested / base_px
            seq += 1
            pos = {
                "id": seq,
                "ticker": c["ticker"],
                "display": ticker_display(c["ticker"]),
                "action": c["signal"],
                "date": c["bar_date"],
                "detected_at": c["detected_at"],
                "provenance": c["provenance"],
                "confidence": c["confidence"],
                "methods": _methods_str(c["details"]),
                "methods_flagged": c["methods_flagged"],
                "entry_i": c["entry_i"],
                "entry_date": c["entry_date"],
                "entry_price_raw": entry_px,
                "entry_price": round(entry_px, 4),
                "shares": invested * (1 - cost_frac) / entry_px,
                "unit": invested,
                "exit_i": c["exit_i"],
                "exit_date": c["exit_date"],
                "exit_reason": c["exit_reason"],
                "status": "OPEN",
                "holding_days": (
                    (c["exit_i"] - c["entry_i"]) if c["exit_i"] is not None
                    else (len(series["Close"]) - 1 - c["entry_i"])
                ),
            }
            trades.append(pos)
            open_positions.append(pos)
            if c["exit_i"] is not None:
                exits_by_date.setdefault(c["exit_date"], []).append(pos)

        # 3) Mark the portfolio.
        stock_value = 0.0
        for pos in open_positions:
            px = _price_on_or_before(by_ticker[pos["ticker"]], d)
            if px:
                stock_value += pos["shares"] * px
        pf_dates.append(d)
        pf_values.append(baseline_shares * base_px + stock_value)
        bench_values.append(bench_shares * base_px)

    # Mark still-open positions (net of the exit cost they will pay).
    for pos in open_positions:
        series = by_ticker[pos["ticker"]]
        last_px = float(series["Close"][-1])
        pos["exit_price"] = round(last_px, 4)
        pos["exit_date"] = series["DateStr"][-1]
        pos["dollar_gain"] = round(pos["shares"] * last_px * (1 - cost_frac) - pos["unit"], 2)
        pos["pct_change"] = round((last_px / pos["entry_price_raw"] - 1) * 100, 2)
        pos["exit_reason"] = "open"

    closed = [t for t in trades if t["status"] == "CLOSED"]
    open_t = [t for t in trades if t["status"] == "OPEN"]

    pf = np.asarray(pf_values)
    bench = np.asarray(bench_values)
    equity = pf - capital
    running_max = np.maximum.accumulate(pf)
    drawdown = running_max - pf

    final_value = float(pf[-1])
    baseline_final = float(bench[-1])
    realized = sum(t["dollar_gain"] for t in closed)
    unrealized = sum(t["dollar_gain"] for t in open_t)

    stats = _compute_trade_stats(closed, pf, drawdown, capital)
    stats["strategy_return_pct"] = round((final_value / capital - 1) * 100, 2)
    stats["benchmark_return_pct"] = round((baseline_final / capital - 1) * 100, 2)
    stats["excess_return_pct"] = round(
        stats["strategy_return_pct"] - stats["benchmark_return_pct"], 2)
    stats["excess_gain"] = round(final_value - baseline_final, 2)
    stats["baseline_earnings"] = round(
        (final_value - capital) - (realized + unrealized), 2)
    deployed = [unit * len([1 for t in trades
                            if t["entry_date"] <= d <= (t["exit_date"] or d)])
                for d in pf_dates[:: max(1, len(pf_dates) // 200)]]
    stats["avg_deployed"] = round(float(np.mean([x for x in deployed if x > 0]) if any(deployed) else 0), 2)
    stats["n_skipped_no_capital"] = len(skipped)

    ledger_rows = sorted(trades, key=lambda t: (t["entry_date"], t["id"]), reverse=True)

    return {
        "signal_ledger": ledger_rows,
        "initial_capital": capital,
        "final_value": round(final_value, 2),
        "total_gain": round(final_value - capital, 2),
        "total_pct": stats["strategy_return_pct"],
        "realized_gain": round(realized, 2),
        "unrealized_gain": round(unrealized, 2),
        "total_invested": int(capital),
        "n_trades": len(trades),
        "n_winning": sum(1 for t in trades if t["dollar_gain"] > 0),
        "n_open": len(open_t),
        "n_closed": len(closed),
        "n_pending": n_pending,
        "n_skipped_no_capital": len(skipped),
        "start_date": pf_dates[0] if pf_dates else None,
        "end_date": pf_dates[-1] if pf_dates else None,
        "equity_curve": {
            "dates": pf_dates,
            "equity": [round(float(x), 2) for x in equity],
            "drawdown": [round(float(x), 2) for x in drawdown],
        },
        "benchmark": {
            "dates": pf_dates,
            "equity": [round(float(x - capital), 2) for x in bench],
            "ticker": baseline_ticker,
            "return_pct": stats["benchmark_return_pct"],
        },
        "stats": stats,
        "provenance_stats": _provenance_split(trades),
        "exit_reasons": dict(Counter(t["exit_reason"] for t in closed)),
        "cost_bps_per_side": BACKTEST_COST_BPS_PER_SIDE,
        "max_hold_days": max_hold,
        "entry_signals": list(entry_signals),
        "baseline_ticker": baseline_ticker,
        "unit": unit,
    }


def _provenance_split(trades: list[dict]) -> dict:
    """Stats split by provenance: walk-forward backfill vs live out-of-sample."""
    out = {}
    for prov in ("backfill", "live"):
        sub = [t for t in trades if t["provenance"] == prov]
        closed = [t for t in sub if t["status"] == "CLOSED"]
        wins = [t for t in closed if t["dollar_gain"] > 0]
        out[prov] = {
            "n_trades": len(sub),
            "n_closed": len(closed),
            "n_open": len(sub) - len(closed),
            "realized_gain": round(sum(t["dollar_gain"] for t in closed), 2),
            "unrealized_gain": round(
                sum(t["dollar_gain"] for t in sub if t["status"] == "OPEN"), 2
            ),
            "win_rate": round(len(wins) / len(closed) * 100, 1) if closed else None,
        }
    return out


def _empty_trade_stats() -> dict:
    return {
        "sharpe": None, "max_drawdown": 0.0, "max_drawdown_pct": 0.0,
        "win_rate": 0.0, "avg_hold_days": 0.0,
        "avg_win": 0.0, "avg_loss": 0.0, "profit_factor": None,
        "hit_rate_by_signal": {}, "n_closed": 0,
        "strategy_return_pct": 0.0, "benchmark_return_pct": None,
        "excess_return_pct": None, "excess_gain": 0.0,
        "baseline_earnings": 0.0, "avg_deployed": 0.0,
        "n_skipped_no_capital": 0,
    }


def _compute_trade_stats(
    closed_trades: list[dict],
    pf_values: np.ndarray,
    drawdown: np.ndarray,
    capital: float,
) -> dict:
    """Risk & quality stats.

    Sharpe and max drawdown come from the DAILY portfolio value — a real
    capital base, so daily returns are well-defined. Win rate, profit
    factor, holding period, and hit-rate-by-signal come from CLOSED
    round-trips only.
    """
    stats = _empty_trade_stats()
    n_closed = len(closed_trades)
    stats["n_closed"] = n_closed

    if pf_values.size >= 2:
        rets = np.diff(pf_values) / pf_values[:-1]
        std = float(rets.std(ddof=1)) if rets.size > 1 else 0.0
        if std > 0:
            stats["sharpe"] = round(float(rets.mean()) / std * float(np.sqrt(252)), 2)
        if drawdown.size:
            max_dd = float(drawdown.max())
            peak = float(np.maximum.accumulate(pf_values).max())
            stats["max_drawdown"] = round(max_dd, 2)
            stats["max_drawdown_pct"] = round(max_dd / peak * 100, 2) if peak > 0 else 0.0

    if n_closed:
        pnl = np.array([float(t["dollar_gain"]) for t in closed_trades])
        holds = np.array([int(t.get("holding_days") or 0) for t in closed_trades], dtype=float)
        wins = pnl[pnl > 0]
        losses = pnl[pnl < 0]
        stats["win_rate"] = round(len(wins) / n_closed * 100, 1)
        stats["avg_hold_days"] = round(float(holds.mean()) if holds.size else 0.0, 1)
        stats["avg_win"] = round(float(wins.mean()), 2) if wins.size else 0.0
        stats["avg_loss"] = round(float(losses.mean()), 2) if losses.size else 0.0
        loss_sum = float(abs(losses.sum()))
        if loss_sum > 0:
            stats["profit_factor"] = round(float(wins.sum()) / loss_sum, 2)

        by_sig: dict[str, list[float]] = {}
        for t in closed_trades:
            by_sig.setdefault(t["action"], []).append(float(t["dollar_gain"]))
        hit: dict[str, dict] = {}
        for sig, vals in by_sig.items():
            arr = np.array(vals)
            n_sig = len(arr)
            n_win = int((arr > 0).sum())
            hit[sig] = {
                "n": n_sig,
                "n_win": n_win,
                "win_rate": (n_win / n_sig) if n_sig else 0.0,
                "avg_pnl": float(arr.mean()) if n_sig else 0.0,
            }
        stats["hit_rate_by_signal"] = hit
    return stats
