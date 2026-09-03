"""The dashboard's "What am I looking at?" panel states the protocol from the
parameters and the record from the backtest — never from typed-in copy."""

from anomaly_detection.backtest import compute_backtest
from anomaly_detection.config import (
    BACKTEST_MAX_HOLD_TRADING_DAYS,
    SENSITIVITY_PRESETS,
    TRADE_MIN_ABS_DEVIATION_PCT,
)
from anomaly_detection.visualization.dashboard import explainer_context

from .test_backtest import _dates, _results_frame, _signal


def test_explainer_reads_protocol_parameters_without_a_record():
    ctx = explainer_context(None, sensitivity="Medium")
    assert ctx["z_threshold"] == SENSITIVITY_PRESETS["medium"]["z_threshold"]
    assert ctx["materiality_pct"] == TRADE_MIN_ABS_DEVIATION_PCT
    assert ctx["max_hold"] == BACKTEST_MAX_HOLD_TRADING_DAYS
    assert ctx["unit_pct"] == 10
    assert ctx["has_record"] is False
    assert ctx["live_n"] == 0


def test_explainer_reports_the_backtest_record():
    res = _results_frame({"AAA": [100, 101, 102, 103, 104, 105, 106, 107, 108, 109]})
    d = _dates(res)
    bt = compute_backtest(res, [_signal("AAA", d[2], "BUY", target=104.0, provenance="live")])
    ctx = explainer_context(bt, sensitivity="medium")
    assert ctx["has_record"] is True
    assert ctx["n_trades"] == 1
    assert ctx["live_n"] == 1
    assert ctx["final_value"] == bt["final_value"]
    assert abs(ctx["benchmark_value"] - bt["initial_capital"]) < 1e-6  # flat baseline
    assert ctx["baseline"] == bt["baseline_ticker"]
    assert ctx["start_date"] == d[0] and ctx["end_date"] == d[-1]
