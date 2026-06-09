"""Backtest protocol tests: no trade may use information before it existed."""

import numpy as np
import pandas as pd

from anomaly_detection.backtest import compute_backtest
from anomaly_detection.config import (
    BACKTEST_COST_BPS_PER_SIDE,
    BACKTEST_MAX_HOLD_TRADING_DAYS,
    BACKTEST_UNIT_DOLLARS,
)


def _results_frame(closes: dict[str, list[float]], start="2026-01-05") -> pd.DataFrame:
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


def test_entry_is_strictly_after_detected_at():
    """The fill must be the first bar AFTER detected_at — never the signal's own bar."""
    res = _results_frame({"AAA": [100, 101, 102, 103, 104, 105, 106, 107, 108, 109]})
    dates = pd.to_datetime(res["Date"]).dt.strftime("%Y-%m-%d").tolist()
    sig = _signal("AAA", dates[2], "BUY", detected_at=dates[2])
    bt = compute_backtest(res, [sig])
    assert bt["n_trades"] == 1
    trade = bt["signal_ledger"][0]
    assert trade["entry_date"] == dates[3], "entry must be the next session"
    assert trade["entry_price"] == 103.0


def test_signal_with_no_next_bar_stays_pending():
    """A signal detected on the last available bar cannot trade yet."""
    res = _results_frame({"AAA": [100, 101, 102]})
    dates = pd.to_datetime(res["Date"]).dt.strftime("%Y-%m-%d").tolist()
    sig = _signal("AAA", dates[-1], "BUY", detected_at=dates[-1])
    bt = compute_backtest(res, [sig])
    assert bt["n_trades"] == 0
    assert bt["n_pending"] == 1


def test_backdated_signal_cannot_trade_at_old_price():
    """A signal about an old bar, detected later, must fill at post-detection
    prices (this was the v1 flaw: 40% of trades filled at prices that
    predated the signal's existence)."""
    closes = [100] * 10 + [50] * 10  # crash at bar 10
    res = _results_frame({"AAA": closes})
    dates = pd.to_datetime(res["Date"]).dt.strftime("%Y-%m-%d").tolist()
    # Bar date = pre-crash bar 5 (price 100), but only detected at bar 15 (price 50)
    sig = _signal("AAA", dates[5], "SELL", detected_at=dates[15])
    bt = compute_backtest(res, [sig], long_only=False)
    trade = bt["signal_ledger"][0]
    assert trade["entry_date"] == dates[16]
    assert trade["entry_price"] == 50.0, "filled at a price from before the signal existed"


def test_opposite_signal_closes_position():
    res = _results_frame({"AAA": [100] * 3 + [110] * 3 + [120] * 6})
    dates = pd.to_datetime(res["Date"]).dt.strftime("%Y-%m-%d").tolist()
    buy = _signal("AAA", dates[0], "BUY", detected_at=dates[0])
    sell = _signal("AAA", dates[4], "SELL", detected_at=dates[4])
    bt = compute_backtest(res, [buy, sell])
    long_trade = next(t for t in bt["signal_ledger"] if t["action"] == "BUY")
    assert long_trade["status"] == "CLOSED"
    assert long_trade["exit_reason"] == "opposite_signal"
    assert long_trade["exit_date"] == dates[5]  # sell's entry bar


def test_reversion_trade_exits_at_frozen_target():
    """BUY exits when the close recovers to the trend value frozen at detection."""
    closes = [100, 90, 88, 92, 96, 101, 103, 104, 105, 106]
    res = _results_frame({"AAA": closes})
    dates = pd.to_datetime(res["Date"]).dt.strftime("%Y-%m-%d").tolist()
    sig = _signal("AAA", dates[2], "BUY", detected_at=dates[2], target=100.0)
    bt = compute_backtest(res, [sig])
    trade = bt["signal_ledger"][0]
    assert trade["entry_date"] == dates[3]
    assert trade["exit_reason"] == "target"
    assert trade["exit_date"] == dates[5]  # first close >= 100
    assert trade["exit_price"] == 101.0


def test_time_stop_closes_stale_positions():
    n = BACKTEST_MAX_HOLD_TRADING_DAYS + 10
    res = _results_frame({"AAA": [100.0] * n})
    dates = pd.to_datetime(res["Date"]).dt.strftime("%Y-%m-%d").tolist()
    sig = _signal("AAA", dates[0], "LONG", detected_at=dates[0])
    bt = compute_backtest(res, [sig])
    trade = bt["signal_ledger"][0]
    assert trade["status"] == "CLOSED"
    assert trade["exit_reason"] == "time_stop"
    assert trade["holding_days"] == BACKTEST_MAX_HOLD_TRADING_DAYS


def test_costs_are_charged_per_side():
    """A flat round trip must lose exactly the two-sided cost."""
    n = BACKTEST_MAX_HOLD_TRADING_DAYS + 5
    res = _results_frame({"AAA": [100.0] * n})
    dates = pd.to_datetime(res["Date"]).dt.strftime("%Y-%m-%d").tolist()
    sig = _signal("AAA", dates[0], "LONG", detected_at=dates[0])
    bt = compute_backtest(res, [sig])
    expected = -2 * BACKTEST_UNIT_DOLLARS * BACKTEST_COST_BPS_PER_SIDE / 10_000
    assert abs(bt["signal_ledger"][0]["dollar_gain"] - expected) < 0.01


def test_provenance_split_is_reported():
    res = _results_frame({"AAA": [100 + i for i in range(40)]})
    dates = pd.to_datetime(res["Date"]).dt.strftime("%Y-%m-%d").tolist()
    sigs = [
        _signal("AAA", dates[1], "BUY", detected_at=dates[1], provenance="backfill"),
        _signal("AAA", dates[5], "LONG", detected_at=dates[5], provenance="live"),
    ]
    bt = compute_backtest(res, sigs)
    ps = bt["provenance_stats"]
    assert ps["backfill"]["n_trades"] == 1
    assert ps["live"]["n_trades"] == 1


def test_watch_and_reduce_never_trade():
    res = _results_frame({"AAA": [100] * 10})
    dates = pd.to_datetime(res["Date"]).dt.strftime("%Y-%m-%d").tolist()
    sigs = [_signal("AAA", dates[0], "WATCH"), _signal("AAA", dates[1], "REDUCE")]
    bt = compute_backtest(res, sigs)
    assert bt["n_trades"] == 0


def test_short_pnl_sign():
    """Short mechanics stay correct when both sides are simulated."""
    closes = [100, 100, 90] + [90] * (BACKTEST_MAX_HOLD_TRADING_DAYS + 3)
    res = _results_frame({"AAA": closes})
    dates = pd.to_datetime(res["Date"]).dt.strftime("%Y-%m-%d").tolist()
    sig = _signal("AAA", dates[1], "SHORT", detected_at=dates[1])
    bt = compute_backtest(res, [sig], long_only=False)
    trade = bt["signal_ledger"][0]
    assert trade["entry_price"] == 90.0  # next bar after detection
    # price flat after entry: P&L is just costs (≈ 0 gross)
    assert trade["pct_change"] == 0.0


def test_long_only_book_never_opens_shorts():
    """Default book is long-only: SELL/SHORT open nothing."""
    res = _results_frame({"AAA": [100] * 12})
    dates = pd.to_datetime(res["Date"]).dt.strftime("%Y-%m-%d").tolist()
    sigs = [_signal("AAA", dates[0], "SHORT"), _signal("AAA", dates[1], "SELL")]
    bt = compute_backtest(res, sigs)  # default long_only=True
    assert bt["long_only"] is True
    assert bt["n_trades"] == 0


def test_long_only_sell_still_closes_longs():
    """In the long-only book, SELL/SHORT act as exit triggers for open longs."""
    res = _results_frame({"AAA": [100] * 3 + [110] * 9})
    dates = pd.to_datetime(res["Date"]).dt.strftime("%Y-%m-%d").tolist()
    buy = _signal("AAA", dates[0], "BUY", detected_at=dates[0])
    short = _signal("AAA", dates[4], "SHORT", detected_at=dates[4])
    bt = compute_backtest(res, [buy, short])
    assert bt["n_trades"] == 1  # only the BUY
    trade = bt["signal_ledger"][0]
    assert trade["action"] == "BUY"
    assert trade["status"] == "CLOSED"
    assert trade["exit_reason"] == "opposite_signal"
    assert trade["exit_date"] == dates[5]  # the SHORT's next-bar entry


def test_return_on_avg_deployed_is_reported():
    """Strategy % and benchmark % must share the same capital base."""
    res = _results_frame({"AAA": [100 + i for i in range(40)]})
    dates = pd.to_datetime(res["Date"]).dt.strftime("%Y-%m-%d").tolist()
    bt = compute_backtest(res, [_signal("AAA", dates[0], "BUY", detected_at=dates[0])])
    s = bt["stats"]
    assert s["avg_deployed"] == 10_000.0  # one $10k position
    assert s["return_on_avg_deployed_pct"] is not None
    assert abs(s["return_on_avg_deployed_pct"] - bt["total_gain"] / 10_000 * 100) < 0.1
