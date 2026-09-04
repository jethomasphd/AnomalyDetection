"""Portfolio backtest protocol tests.

Capital model invariants:
  - no trade may use information before it existed (next-bar fills),
  - capital is conserved (invest only what the baseline holds),
  - bearish signals divest, they NEVER open short positions,
  - strategy and benchmark share the same starting capital and calendar.
"""

import numpy as np
import pandas as pd

from anomaly_detection.backtest import compute_backtest
from anomaly_detection.config import (
    BACKTEST_COST_BPS_PER_SIDE,
    BACKTEST_MAX_HOLD_TRADING_DAYS,
    BACKTEST_UNIT_DOLLARS,
    PORTFOLIO_CAPITAL,
)

BASE = "SPY"


def _results_frame(closes: dict[str, list[float]], start="2026-01-05") -> pd.DataFrame:
    """Price frame; a flat baseline series is added automatically."""
    n = max(len(c) for c in closes.values())
    closes = {**closes, BASE: closes.get(BASE, [500.0] * n)}
    frames = []
    for ticker, cs in closes.items():
        dates = pd.bdate_range(start, periods=len(cs))
        frames.append(pd.DataFrame({
            "Date": dates, "Close": np.asarray(cs, dtype=float),
            "Volume": 1e6, "Ticker": ticker,
        }))
    return pd.concat(frames, ignore_index=True)


def _signal(ticker, date, signal, detected_at=None, target=None, provenance="live"):
    return {
        "ticker": ticker, "date": date, "signal": signal,
        "detected_at": detected_at or date, "provenance": provenance,
        "confidence": "Moderate",
        "rationale": {"methods_flagged": 2,
                      "details": {"ewma_value": target or 0, "ewma_score": 0.7}},
    }


def _dates(res, ticker="AAA"):
    g = res[res.Ticker == ticker].sort_values("Date")
    return pd.to_datetime(g["Date"]).dt.strftime("%Y-%m-%d").tolist()


def test_entry_is_strictly_after_detected_at():
    """The fill must be the first bar AFTER detected_at — never the signal's own bar."""
    res = _results_frame({"AAA": [100, 101, 102, 103, 104, 105, 106, 107, 108, 109]})
    d = _dates(res)
    bt = compute_backtest(res, [_signal("AAA", d[2], "BUY", detected_at=d[2])])
    assert bt["n_trades"] == 1
    trade = bt["signal_ledger"][0]
    assert trade["entry_date"] == d[3], "entry must be the next session"
    assert trade["entry_price"] == 103.0


def test_signal_with_no_next_bar_stays_pending():
    res = _results_frame({"AAA": [100, 101, 102]})
    d = _dates(res)
    bt = compute_backtest(res, [_signal("AAA", d[-1], "BUY", detected_at=d[-1])])
    assert bt["n_trades"] == 0
    assert bt["n_pending"] == 1


def test_backdated_signal_cannot_trade_at_old_price():
    """A signal about an old bar, detected later, must fill at post-detection
    prices (the v1 flaw: 40% of trades filled at prices that predated the
    signal's existence)."""
    closes = [100] * 10 + [50] * 10  # crash at bar 10
    res = _results_frame({"AAA": closes})
    d = _dates(res)
    sig = _signal("AAA", d[5], "BUY", detected_at=d[15])
    bt = compute_backtest(res, [sig])
    trade = bt["signal_ledger"][0]
    assert trade["entry_date"] == d[16]
    assert trade["entry_price"] == 50.0


def test_bearish_signals_divest_and_never_open_positions():
    """SELL/SHORT move capital out of the ticker — no position ever opens."""
    res = _results_frame({"AAA": [100] * 3 + [110] * 9})
    d = _dates(res)
    buy = _signal("AAA", d[0], "BUY", detected_at=d[0])
    short = _signal("AAA", d[4], "SHORT", detected_at=d[4])
    sell = _signal("AAA", d[6], "SELL", detected_at=d[6])
    bt = compute_backtest(res, [buy, short, sell])
    assert bt["n_trades"] == 1  # only the BUY invested
    trade = bt["signal_ledger"][0]
    assert trade["action"] == "BUY"
    assert trade["status"] == "CLOSED"
    assert trade["exit_reason"] == "divest_signal"
    assert trade["exit_date"] == d[5]  # the SHORT's next-bar entry divests


def test_reversion_trade_exits_at_frozen_target():
    closes = [100, 90, 88, 92, 96, 101, 103, 104, 105, 106]
    res = _results_frame({"AAA": closes})
    d = _dates(res)
    bt = compute_backtest(res, [_signal("AAA", d[2], "BUY", detected_at=d[2], target=100.0)])
    trade = bt["signal_ledger"][0]
    assert trade["entry_date"] == d[3]
    assert trade["exit_reason"] == "target"
    assert trade["exit_date"] == d[5]  # first close >= 100
    assert trade["exit_price"] == 101.0


def test_time_stop_closes_stale_positions():
    n = BACKTEST_MAX_HOLD_TRADING_DAYS + 10
    res = _results_frame({"AAA": [100.0] * n})
    d = _dates(res)
    bt = compute_backtest(res, [_signal("AAA", d[0], "BUY", detected_at=d[0])])
    trade = bt["signal_ledger"][0]
    assert trade["status"] == "CLOSED"
    assert trade["exit_reason"] == "time_stop"
    assert trade["holding_days"] == BACKTEST_MAX_HOLD_TRADING_DAYS


def test_costs_are_charged_per_stock_transaction():
    """Flat prices, flat baseline: the round trip must cost exactly ~2 sides."""
    n = BACKTEST_MAX_HOLD_TRADING_DAYS + 5
    res = _results_frame({"AAA": [100.0] * n})
    d = _dates(res)
    bt = compute_backtest(res, [_signal("AAA", d[0], "BUY", detected_at=d[0])])
    cost_frac = BACKTEST_COST_BPS_PER_SIDE / 10_000
    expected = BACKTEST_UNIT_DOLLARS * ((1 - cost_frac) ** 2 - 1)
    assert abs(bt["signal_ledger"][0]["dollar_gain"] - expected) < 0.01
    # Portfolio-level loss equals the trade loss (baseline is flat).
    assert abs(bt["total_gain"] - expected) < 0.01


def test_capital_is_conserved_signals_skip_when_pool_empty():
    """With $100k and $10k slices, the 11th same-day signal must be skipped."""
    tickers = {f"T{i:02d}": [100.0] * 40 for i in range(11)}
    res = _results_frame(tickers)
    d = pd.to_datetime(res[res.Ticker == "T00"]["Date"]).dt.strftime("%Y-%m-%d").tolist()
    sigs = [_signal(f"T{i:02d}", d[0], "BUY", detected_at=d[0], target=200.0)
            for i in range(11)]
    bt = compute_backtest(res, sigs)
    max_slices = int(PORTFOLIO_CAPITAL // BACKTEST_UNIT_DOLLARS)
    assert bt["n_trades"] == max_slices
    assert bt["n_skipped_no_capital"] == 11 - max_slices


def test_divested_capital_can_be_reinvested():
    """A slice that exits returns to the baseline and funds later signals."""
    n = BACKTEST_MAX_HOLD_TRADING_DAYS * 3
    tickers = {f"T{i:02d}": [100.0] * n for i in range(10)}
    tickers["LATE"] = [100.0] * n
    res = _results_frame(tickers)
    d = pd.to_datetime(res[res.Ticker == "T00"]["Date"]).dt.strftime("%Y-%m-%d").tolist()
    sigs = [_signal(f"T{i:02d}", d[0], "BUY", detected_at=d[0]) for i in range(10)]
    # All 10 slices out; T00 divests on its bearish signal, then LATE invests.
    sigs.append(_signal("T00", d[3], "SELL", detected_at=d[3]))
    sigs.append(_signal("LATE", d[5], "BUY", detected_at=d[5]))
    bt = compute_backtest(res, sigs)
    assert bt["n_skipped_no_capital"] == 0
    assert bt["n_trades"] == 11
    late = next(t for t in bt["signal_ledger"] if t["ticker"] == "LATE")
    assert late["entry_date"] == d[6]


def test_strategy_equals_benchmark_when_no_signals_fire():
    res = _results_frame({"AAA": [100 + i for i in range(30)],
                          BASE: [500 * (1.001 ** i) for i in range(30)]})
    bt = compute_backtest(res, [_signal("AAA", "2030-01-01", "WATCH")])
    assert bt["n_trades"] == 0
    # No trades -> portfolio is 100% baseline -> returns match exactly.
    assert bt["stats"]["strategy_return_pct"] == bt["stats"]["benchmark_return_pct"]


def test_excess_return_measures_overlay_value():
    """Stock doubles while baseline is flat: excess must be ~ the trade gain."""
    n = BACKTEST_MAX_HOLD_TRADING_DAYS + 5
    closes = [100.0, 100.0] + [200.0] * (n - 2)
    res = _results_frame({"AAA": closes})
    d = _dates(res)
    bt = compute_backtest(res, [_signal("AAA", d[0], "BUY", detected_at=d[0])])
    s = bt["stats"]
    assert s["benchmark_return_pct"] == 0.0
    assert s["excess_gain"] > 9000  # ~$10k slice doubled, minus costs
    assert abs(s["excess_return_pct"] - s["strategy_return_pct"]) < 1e-9


def test_default_entry_set_is_buy_only():
    """LONG is informational by default — only BUY invests (set by the
    split-half study; see config.BACKTEST_ENTRY_SIGNALS)."""
    n = BACKTEST_MAX_HOLD_TRADING_DAYS + 5
    res = _results_frame({"AAA": [100.0] * n})
    d = _dates(res)
    bt = compute_backtest(res, [_signal("AAA", d[0], "LONG", detected_at=d[0])])
    assert bt["n_trades"] == 0


def test_entry_signals_config_filters_long():
    n = BACKTEST_MAX_HOLD_TRADING_DAYS + 5
    res = _results_frame({"AAA": [100.0] * n})
    d = _dates(res)
    sigs = [_signal("AAA", d[0], "LONG", detected_at=d[0]),
            _signal("AAA", d[1], "BUY", detected_at=d[1])]
    bt = compute_backtest(res, sigs, entry_signals=("BUY",))
    assert bt["n_trades"] == 1
    assert bt["signal_ledger"][0]["action"] == "BUY"


def test_provenance_split_is_reported():
    res = _results_frame({"AAA": [100 + i for i in range(40)]})
    d = _dates(res)
    sigs = [
        _signal("AAA", d[1], "BUY", detected_at=d[1], provenance="backfill"),
        _signal("AAA", d[5], "LONG", detected_at=d[5], provenance="live"),
    ]
    bt = compute_backtest(res, sigs, entry_signals=("BUY", "LONG"))
    ps = bt["provenance_stats"]
    assert ps["backfill"]["n_trades"] == 1
    assert ps["live"]["n_trades"] == 1


def test_watch_and_reduce_never_trade():
    res = _results_frame({"AAA": [100] * 10})
    d = _dates(res)
    sigs = [_signal("AAA", d[0], "WATCH"), _signal("AAA", d[1], "REDUCE")]
    bt = compute_backtest(res, sigs)
    assert bt["n_trades"] == 0


def test_frozen_target_is_translated_after_a_split():
    """The CRWD 2026-07-02 incident: a 4:1 split rescales the fetched
    history ÷4 AFTER a signal froze its target pre-split. The pre-split
    target ($400) can never be touched by post-split closes (~$100); it
    must be translated via the signal bar's close in both bases so the
    exit lands where it did before the re-adjustment."""
    # Current (post-split) fetch. Frozen at detection: close 90*4=360,
    # target 100*4=400. Post-split the close touches 100 at bar 4.
    closes = [95.0, 90.0, 92.0, 96.0, 101.0, 103.0, 104.0, 105.0, 106.0, 107.0]
    res = _results_frame({"AAA": closes})
    d = _dates(res)
    sig = _signal("AAA", d[1], "BUY", detected_at=d[1], target=400.0)
    sig["rationale"]["details"]["close"] = 360.0  # frozen pre-split close of bar d[1]
    bt = compute_backtest(res, [sig])
    trade = bt["signal_ledger"][0]
    assert abs(trade["basis_factor"] - 4.0) < 1e-6
    assert trade["exit_reason"] == "target"
    assert trade["exit_date"] == d[4]      # first close >= 400/4 = 100
    assert trade["exit_price"] == 101.0


def test_frozen_target_derived_from_legacy_rationale_fields():
    """Rows written before the close field existed still reconcile: the
    frozen close is recovered from ewma_value and deviation_pct."""
    closes = [95.0, 90.0, 92.0, 96.0, 101.0, 103.0, 104.0, 105.0, 106.0, 107.0]
    res = _results_frame({"AAA": closes})
    d = _dates(res)
    sig = _signal("AAA", d[1], "BUY", detected_at=d[1], target=400.0)
    # frozen close 360 = ewma 400 * (1 - 10%)
    sig["rationale"]["details"]["deviation_pct"] = -10.0
    bt = compute_backtest(res, [sig])
    trade = bt["signal_ledger"][0]
    assert trade["exit_reason"] == "target"
    assert trade["exit_date"] == d[4]


def test_target_translated_via_ticker_break_when_bar_left_the_window():
    """If the signal's own bar is no longer in the fetched window (anchor
    moved / vendor revised the date), the ticker-level basis break must
    still translate the frozen target — otherwise the pre-split target
    silently reverts to being untouchable."""
    closes = [95.0, 90.0, 92.0, 96.0, 101.0, 103.0, 104.0, 105.0, 106.0, 107.0]
    res = _results_frame({"AAA": closes})
    d = _dates(res)
    sig = _signal("AAA", "2025-06-02", "BUY", detected_at="2025-06-02", target=400.0)
    sig["rationale"]["details"]["close"] = 360.0  # bar 2025-06-02 not in res
    breaks = {"AAA": {"factor": 4.0, "n_bars_affected": 3, "n_bars_checked": 3,
                      "last_affected_date": "2025-06-02"}}
    bt = compute_backtest(res, [sig], basis_breaks=breaks)
    trade = bt["signal_ledger"][0]
    assert trade["exit_reason"] == "target"   # 400/4 = 100, first touch d[4]
    assert trade["exit_date"] == d[4]


def test_full_precision_frozen_close_beats_rounded_derivation():
    """Legacy rows derive the frozen close from 2dp-rounded fields; the
    ~6e-5 noise could nudge a target past an exact-touch close. When the
    anomalies-ledger snapshot (full precision) is supplied, translation is
    an exact no-op and the exact-touch exit is preserved."""
    n = BACKTEST_MAX_HOLD_TRADING_DAYS + 5
    closes = [90.0049, 90.0049, 96.0, 100.0] + [98.0] * (n - 4)
    res = _results_frame({"AAA": closes})
    d = _dates(res)
    sig = _signal("AAA", d[1], "BUY", detected_at=d[1], target=100.0)
    sig["rationale"]["details"]["deviation_pct"] = -10.0  # derived close: 90.00
    frozen = {("AAA", d[1]): 90.0049}
    bt = compute_backtest(res, [sig], frozen_closes=frozen)
    trade = bt["signal_ledger"][0]
    assert trade["basis_factor"] == 1.0
    assert trade["exit_reason"] == "target"
    assert trade["exit_date"] == d[3]


def test_rounded_derivation_noise_does_not_shift_targets():
    """Without the snapshot, the last-resort 2dp derivation must not apply
    a phantom 0.99995-style factor — sub-0.1% factors snap to 1.0."""
    n = BACKTEST_MAX_HOLD_TRADING_DAYS + 5
    closes = [90.0049, 90.0049, 96.0, 100.0] + [98.0] * (n - 4)
    res = _results_frame({"AAA": closes})
    d = _dates(res)
    sig = _signal("AAA", d[1], "BUY", detected_at=d[1], target=100.0)
    sig["rationale"]["details"]["deviation_pct"] = -10.0
    bt = compute_backtest(res, [sig])
    trade = bt["signal_ledger"][0]
    assert trade["basis_factor"] == 1.0
    assert trade["exit_reason"] == "target"
    assert trade["exit_date"] == d[3]


def test_target_untouched_when_basis_matches():
    """No corporate action: frozen close equals the current close for the
    same bar, so the target must pass through bit-identical."""
    closes = [100.0, 90.0, 88.0, 92.0, 96.0, 101.0, 103.0, 104.0, 105.0, 106.0]
    res = _results_frame({"AAA": closes})
    d = _dates(res)
    sig = _signal("AAA", d[2], "BUY", detected_at=d[2], target=100.0)
    sig["rationale"]["details"]["close"] = 88.0
    bt = compute_backtest(res, [sig])
    trade = bt["signal_ledger"][0]
    assert trade["basis_factor"] == 1.0
    assert trade["exit_reason"] == "target"
    assert trade["exit_date"] == d[5]
    assert trade["exit_price"] == 101.0


def test_open_position_is_marked_at_last_real_close_when_latest_bar_is_empty():
    """2026-09-04: the vendor returned the latest bar with a NaN close for every
    ticker. An open slice marked at NaN made the equity curve — and Sharpe,
    drawdown, unrealised and total P&L — NaN. A bar without a price must be
    ignored, not multiplied."""
    import math
    closes = [100, 101, 102, 103, 104, 105, 106, 107, 108, float("nan")]
    res = _results_frame({"AAA": closes})
    d = _dates(res)
    bt = compute_backtest(res, [_signal("AAA", d[2], "BUY", target=10_000.0)])
    assert bt["n_trades"] == 1
    trade = bt["signal_ledger"][0]
    assert trade["status"] == "OPEN"
    assert trade["exit_price"] == 108.0, "marked at the last bar that has a real close"
    assert math.isfinite(bt["final_value"]) and math.isfinite(bt["unrealized_gain"])
    assert all(math.isfinite(x) for x in bt["equity_curve"]["equity"])
    assert bt["stats"]["sharpe"] is not None
