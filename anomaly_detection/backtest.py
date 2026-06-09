"""Walk-forward backtest — simulates trading the signal ledger honestly.

Protocol (the same rules a live trader following the system would face):

  ENTRY   A signal exists only after the close of its `detected_at` day.
          The trade therefore fills at the close of the FIRST bar strictly
          after detected_at. Never the bar the signal describes, never the
          same day it was produced. Signals whose next bar hasn't happened
          yet remain pending (no trade).

  EXIT    Whichever comes first:
            - target:          BUY/SELL mean-reversion trades exit when the
                               close crosses the trend value frozen in the
                               signal at detection time
            - opposite_signal: an opposite-direction signal on the ticker
                               closes every open position of the other side
                               at ITS entry bar
            - time_stop:       BACKTEST_MAX_HOLD_TRADING_DAYS bars after entry
            - still open:      marked to the latest close (unrealised)

  COSTS   BACKTEST_COST_BPS_PER_SIDE per side, charged on entry and on exit.

  CAPITAL Every signal is an independent $BACKTEST_UNIT_DOLLARS position;
          same-direction signals stack.

Because detection is causal (verdicts for historical bars are exactly what
a live run that evening would have produced — see detection/causal.py), the
'backfill' portion of the ledger is a legitimate walk-forward simulation,
and the 'live' portion is true out-of-sample record. Stats are reported for
the combined book and split by provenance so the two are never conflated.

Input is the FULL signals ledger (storage.get_signals_for_backtest), not
the display-capped alerts.json — the trade set cannot silently shrink as
old alerts roll off the dashboard.
"""

import bisect
import logging
from collections import Counter

import numpy as np
import pandas as pd

from .config import (
    BACKTEST_BENCHMARK_TICKER,
    BACKTEST_COST_BPS_PER_SIDE,
    BACKTEST_LONG_ONLY,
    BACKTEST_MAX_HOLD_TRADING_DAYS,
    BACKTEST_UNIT_DOLLARS,
    ticker_display,
)

logger = logging.getLogger(__name__)

TRADABLE = {"BUY": +1, "LONG": +1, "SELL": -1, "SHORT": -1}
REVERSION_SIGNALS = {"BUY", "SELL"}  # these exit at the frozen trend target


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


def _signal_to_order(sig: dict) -> dict | None:
    """Convert a ledger signal row into an order intent, or None if not tradable."""
    direction = TRADABLE.get(sig.get("signal"))
    if direction is None:
        return None
    rationale = sig.get("rationale") or {}
    details = rationale.get("details") or {}
    return {
        "ticker": sig["ticker"],
        "signal": sig["signal"],
        "direction": direction,
        "bar_date": sig["date"],
        "detected_at": sig.get("detected_at") or sig["date"],
        "provenance": sig.get("provenance") or "live",
        "confidence": sig.get("confidence") or "",
        "target": float(details.get("ewma_value") or 0) or None,
        "methods_flagged": int(rationale.get("methods_flagged") or 0),
        "details": details,
    }


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
    direction: int,
    signal: str,
    target: float | None,
    opposite_entries: list[int],
    max_hold: int = BACKTEST_MAX_HOLD_TRADING_DAYS,
) -> tuple[int | None, str]:
    """Earliest exit bar index for a position opened at entry_i.

    Scans closes after entry for (a) the mean-reversion target, (b) the
    first opposite-direction signal's entry bar, (c) the time stop. Returns
    (exit_index, reason) or (None, 'open') if nothing triggers before the
    end of data.
    """
    closes = series["Close"]
    n = len(closes)

    # First opposite-signal entry bar strictly after our entry bar.
    j = bisect.bisect_right(opposite_entries, entry_i)
    opp_i = opposite_entries[j] if j < len(opposite_entries) else None

    time_i = entry_i + max_hold

    target_i = None
    if signal in REVERSION_SIGNALS and target and target > 0:
        scan_end = min(n, time_i + 1, opp_i + 1 if opp_i is not None else n)
        for k in range(entry_i + 1, scan_end):
            # Long reversion exits when price recovers UP to the trend;
            # short reversion exits when price falls back DOWN to it.
            if (direction > 0 and closes[k] >= target) or (
                direction < 0 and closes[k] <= target
            ):
                target_i = k
                break

    candidates = [
        (target_i, "target"),
        (opp_i, "opposite_signal"),
        (time_i if time_i < n else None, "time_stop"),
    ]
    live = [(i, r) for i, r in candidates if i is not None]
    if not live:
        return None, "open"
    return min(live, key=lambda x: x[0])


def compute_backtest(
    results: pd.DataFrame,
    ledger_signals: list[dict],
    unit: float = BACKTEST_UNIT_DOLLARS,
    long_only: bool = BACKTEST_LONG_ONLY,
    max_hold: int = BACKTEST_MAX_HOLD_TRADING_DAYS,
) -> dict:
    """Run the walk-forward simulation over the full signal ledger.

    With long_only=True (the default; see config.BACKTEST_LONG_ONLY for the
    measured rationale), only BUY/LONG open positions. SELL/SHORT signals
    still act on the book — they close every open long on their ticker at
    their own next-bar entry — but never open shorts. Their information is
    used as risk management, which matches their dashboard semantics
    ("take profits / tighten stops"), without taking the systematically
    edge-less short side of the book.
    """
    empty = {
        "signal_ledger": [],
        "total_gain": 0.0, "total_pct": 0.0,
        "realized_gain": 0.0, "unrealized_gain": 0.0,
        "total_invested": 0, "n_trades": 0, "n_winning": 0,
        "n_open": 0, "n_closed": 0, "n_pending": 0,
        "start_date": None, "end_date": None,
        "equity_curve": {"dates": [], "equity": [], "drawdown": []},
        "benchmark": {"dates": [], "equity": [], "ticker": BACKTEST_BENCHMARK_TICKER},
        "stats": _empty_trade_stats(),
        "provenance_stats": {},
        "exit_reasons": {},
        "cost_bps_per_side": BACKTEST_COST_BPS_PER_SIDE,
        "max_hold_days": max_hold,
        "long_only": long_only,
    }
    if results.empty or not ledger_signals:
        return empty

    by_ticker = _build_price_index(results)
    all_dates = sorted({d for v in by_ticker.values() for d in v["DateStr"]})
    if not all_dates:
        return empty

    cost_frac = BACKTEST_COST_BPS_PER_SIDE / 10_000.0
    cost_per_side = unit * cost_frac

    # ----- Resolve orders to entry bars -----
    orders = []
    n_pending = 0
    for sig in ledger_signals:
        order = _signal_to_order(sig)
        if order is None:
            continue
        series = by_ticker.get(order["ticker"])
        if series is None:
            continue
        entry_i = _entry_index(series, order["detected_at"])
        if entry_i is None:
            n_pending += 1  # signal produced after the last available bar
            continue
        order["entry_i"] = entry_i
        orders.append(order)

    # Entry bars of each direction per ticker (for opposite-signal exits).
    # In long-only mode, short-side orders contribute their entry bars here
    # (so they CLOSE longs) but are excluded from position opening below.
    entries_by_dir: dict[tuple[str, int], list[int]] = {}
    for o in orders:
        entries_by_dir.setdefault((o["ticker"], o["direction"]), []).append(o["entry_i"])
    for v in entries_by_dir.values():
        v.sort()

    position_orders = [o for o in orders if not (long_only and o["direction"] < 0)]

    # ----- Simulate each position independently -----
    trades = []
    for seq, o in enumerate(
        sorted(position_orders, key=lambda x: (x["entry_i"], x["ticker"], x["signal"])), start=1
    ):
        series = by_ticker[o["ticker"]]
        closes, dates = series["Close"], series["DateStr"]
        entry_i = o["entry_i"]
        entry_price = float(closes[entry_i])
        if entry_price <= 0:
            continue

        opposite = entries_by_dir.get((o["ticker"], -o["direction"]), [])
        exit_i, reason = _find_exit(
            series, entry_i, o["direction"], o["signal"], o["target"], opposite,
            max_hold=max_hold,
        )

        if exit_i is None:
            status, exit_idx_eff = "OPEN", len(closes) - 1
        else:
            status, exit_idx_eff = "CLOSED", exit_i
        exit_price = float(closes[exit_idx_eff])

        gross = o["direction"] * (exit_price - entry_price) / entry_price * unit
        costs = cost_per_side + (cost_per_side if status == "CLOSED" else 0.0)
        pnl = gross - costs

        trades.append({
            "id": seq,
            "ticker": o["ticker"],
            "display": ticker_display(o["ticker"]),
            "direction": o["direction"],
            "action": o["signal"],
            "date": o["bar_date"],
            "detected_at": o["detected_at"],
            "provenance": o["provenance"],
            "entry_date": dates[entry_i],
            "entry_price": round(entry_price, 4),
            "entry_i": entry_i,
            "exit_i": exit_idx_eff,
            "exit_date": dates[exit_idx_eff],
            "exit_price": round(exit_price, 4),
            "exit_reason": reason if status == "CLOSED" else "open",
            "status": status,
            "unit": unit,
            "dollar_gain": round(pnl, 2),
            "pct_change": round(o["direction"] * (exit_price - entry_price) / entry_price * 100, 2),
            "holding_days": exit_idx_eff - entry_i,
            "confidence": o["confidence"],
            "methods": _methods_str(o["details"]),
            "methods_flagged": o["methods_flagged"],
        })

    closed = [t for t in trades if t["status"] == "CLOSED"]
    open_t = [t for t in trades if t["status"] == "OPEN"]

    # ----- Daily mark-to-market equity curve -----
    equity_curve = _build_equity_curve(trades, by_ticker, all_dates, cost_per_side)

    # Average capital actually at risk on days the book held anything —
    # the honest denominator for a % return, and the same capital base the
    # benchmark is scaled to (so the two percentages are comparable).
    avg_deployed = _average_deployed(trades, all_dates, unit)

    # ----- Benchmark: buy-and-hold the benchmark ticker, same capital -----
    benchmark = _benchmark_curve(by_ticker, all_dates, trades, avg_deployed)

    realized = sum(t["dollar_gain"] for t in closed)
    unrealized = sum(t["dollar_gain"] for t in open_t)
    total_gain = realized + unrealized
    n_trades = len(trades)
    total_invested = n_trades * unit

    stats = _compute_trade_stats(closed, equity_curve, unit=unit, n_trades_total=n_trades)
    stats["benchmark_return_pct"] = benchmark.get("return_pct")
    stats["avg_deployed"] = round(avg_deployed, 2)
    stats["return_on_avg_deployed_pct"] = (
        round(total_gain / avg_deployed * 100, 2) if avg_deployed > 0 else None
    )

    ledger_rows = sorted(trades, key=lambda t: (t["entry_date"], t["id"]), reverse=True)

    return {
        "signal_ledger": ledger_rows,
        "total_gain": round(total_gain, 2),
        "total_pct": round((total_gain / total_invested * 100) if total_invested else 0, 2),
        "realized_gain": round(realized, 2),
        "unrealized_gain": round(unrealized, 2),
        "total_invested": int(total_invested),
        "n_trades": n_trades,
        "n_winning": sum(1 for t in trades if t["dollar_gain"] > 0),
        "n_open": len(open_t),
        "n_closed": len(closed),
        "n_pending": n_pending,
        "start_date": min((t["entry_date"] for t in trades), default=all_dates[0]),
        "end_date": all_dates[-1],
        "equity_curve": equity_curve,
        "benchmark": benchmark,
        "stats": stats,
        "provenance_stats": _provenance_split(trades),
        "exit_reasons": dict(Counter(t["exit_reason"] for t in closed)),
        "cost_bps_per_side": BACKTEST_COST_BPS_PER_SIDE,
        "max_hold_days": max_hold,
        "long_only": long_only,
    }


def _average_deployed(trades: list[dict], all_dates: list[str], unit: float) -> float:
    """Mean $ at risk across days where the book held at least one position."""
    if not trades or not all_dates:
        return 0.0
    date_pos = {d: i for i, d in enumerate(all_dates)}
    deployed = np.zeros(len(all_dates))
    for t in trades:
        lo = date_pos.get(t["entry_date"])
        if lo is None:
            continue
        hi = len(all_dates) - 1 if t["status"] == "OPEN" else date_pos.get(
            t["exit_date"], len(all_dates) - 1
        )
        deployed[lo : hi + 1] += unit
    active = deployed[deployed > 0]
    return float(active.mean()) if active.size else 0.0


def _build_equity_curve(
    trades: list[dict],
    by_ticker: dict[str, dict],
    all_dates: list[str],
    cost_per_side: float,
) -> dict:
    """Daily mark-to-market of the whole book.

    For each day d and each trade: 0 before entry; entry cost + MTM gross
    P&L while the position is on; the realized (cost-inclusive) P&L after
    exit. Costs hit the curve the day they are incurred, like real fills.
    """
    if not all_dates:
        return {"dates": [], "equity": [], "drawdown": []}
    date_pos = {d: i for i, d in enumerate(all_dates)}
    equity = np.zeros(len(all_dates))

    for t in trades:
        series = by_ticker.get(t["ticker"])
        if series is None:
            continue
        closes, dates = series["Close"], series["DateStr"]
        gi_entry = date_pos[dates[t["entry_i"]]]
        gi_exit = date_pos[dates[t["exit_i"]]]
        entry_price = t["entry_price"]
        # Active window: mark against the ticker's own bars; carry forward
        # across days the ticker didn't trade.
        local = t["entry_i"]
        last_mark = 0.0
        for gi in range(gi_entry, len(all_dates)):
            if t["status"] == "CLOSED" and gi >= gi_exit:
                equity[gi] += t["dollar_gain"]
                continue
            d = all_dates[gi]
            li = series["_index"].get(d)
            if li is not None:
                local = li
            mark_price = closes[local]
            last_mark = (
                t["direction"] * (mark_price - entry_price) / entry_price * t["unit"]
                - cost_per_side
            )
            equity[gi] += last_mark

    running_max = np.maximum.accumulate(equity)
    drawdown = running_max - equity
    return {
        "dates": all_dates,
        "equity": [round(float(x), 2) for x in equity],
        "drawdown": [round(float(x), 2) for x in drawdown],
    }


def _benchmark_curve(
    by_ticker: dict[str, dict],
    all_dates: list[str],
    trades: list[dict],
    avg_deployed: float,
) -> dict:
    """Buy-and-hold benchmark over the same window, scaled to average deployed capital.

    Answers: "what if the average dollars the strategy had at risk had just
    sat in the benchmark instead?" Uses the same capital base as the
    strategy's return_on_avg_deployed_pct, so the two percentages compare
    like for like.
    """
    out = {"dates": [], "equity": [], "ticker": BACKTEST_BENCHMARK_TICKER, "return_pct": None}
    series = by_ticker.get(BACKTEST_BENCHMARK_TICKER)
    if series is None or not trades or avg_deployed <= 0:
        return out

    start = min(t["entry_date"] for t in trades)
    bench_dates, bench_equity = [], []
    base = None
    idx = series["_index"]
    closes = series["Close"]
    for d in all_dates:
        if d < start:
            continue
        li = idx.get(d)
        if li is None:
            continue
        if base is None:
            base = closes[li]
        bench_dates.append(d)
        bench_equity.append(round((closes[li] / base - 1.0) * avg_deployed, 2))

    out["dates"] = bench_dates
    out["equity"] = bench_equity
    out["avg_deployed"] = round(avg_deployed, 2)
    if bench_equity and avg_deployed:
        out["return_pct"] = round(bench_equity[-1] / avg_deployed * 100, 2)
    return out


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
        "benchmark_return_pct": None,
    }


def _compute_trade_stats(
    closed_trades: list[dict],
    equity_curve: dict,
    unit: float = BACKTEST_UNIT_DOLLARS,
    n_trades_total: int | None = None,
) -> dict:
    """Risk & quality stats.

    - Sharpe & Max Drawdown come from the DAILY mark-to-market equity curve
      (realized + unrealized): what the whole book actually did, day by day.
    - Win rate, profit factor, holding period, and hit-rate-by-signal come
      from CLOSED trades only, because "win" is only meaningful once
      realized.
    """
    stats = _empty_trade_stats()
    n_closed = len(closed_trades)
    stats["n_closed"] = n_closed

    equity = np.array(equity_curve.get("equity", []), dtype=float)
    if equity.size >= 2:
        daily_pnl = np.diff(equity)
        std_pnl = float(daily_pnl.std(ddof=1)) if daily_pnl.size > 1 else 0.0
        mean_pnl = float(daily_pnl.mean()) if daily_pnl.size else 0.0
        if std_pnl > 0:
            stats["sharpe"] = round((mean_pnl / std_pnl) * float(np.sqrt(252)), 2)

        drawdown = np.array(equity_curve.get("drawdown", []), dtype=float)
        if drawdown.size:
            max_dd = float(drawdown.max())
            stats["max_drawdown"] = round(max_dd, 2)
            capital = (n_trades_total or 1) * unit
            if capital > 0:
                stats["max_drawdown_pct"] = round(max_dd / capital * 100, 2)

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
