"""Price-basis reconciliation and stale-feed watchdog tests.

The incident these guard against (CRWD, 2026-07-02): the data source
applied a 4:1 split between two runs, rescaling the ENTIRE fetched history
÷4, while the ledger kept its frozen pre-split dollar values. Frozen
targets became untouchable, the backtest silently rewrote historical
exits, and the dashboard showed three different price regimes for one
ticker. Separately: a feed that flatlines (ORCL was *suspected* of this)
must be surfaced as broken data, never scored as real trading.
"""

import json

import numpy as np
import pandas as pd

from anomaly_detection.adjustments import (
    bar_basis_factor,
    compute_ticker_status,
    detect_price_basis_breaks,
    detect_stale_feeds,
    frozen_close_from_details,
    trailing_flat_run,
)
from anomaly_detection.alerts import alerts_to_json, generate_alerts


def _frame(closes: dict[str, list[float]], start="2026-01-05") -> pd.DataFrame:
    frames = []
    for ticker, cs in closes.items():
        dates = pd.bdate_range(start, periods=len(cs))
        frames.append(pd.DataFrame({
            "Date": dates, "Close": np.asarray(cs, dtype=float),
            "Volume": 1e6, "Ticker": ticker,
        }))
    return pd.concat(frames, ignore_index=True)


def _dates(n, start="2026-01-05"):
    return pd.bdate_range(start, periods=n).strftime("%Y-%m-%d").tolist()


# ---------------------------------------------------------------------------
# Basis factor primitives
# ---------------------------------------------------------------------------

def test_bar_basis_factor_is_frozen_over_current():
    assert bar_basis_factor(400.0, 100.0) == 4.0
    assert bar_basis_factor(100.0, 100.0) == 1.0


def test_bar_basis_factor_guards_missing_and_nonpositive():
    assert bar_basis_factor(None, 100.0) is None
    assert bar_basis_factor(100.0, None) is None
    assert bar_basis_factor(100.0, 0.0) is None
    assert bar_basis_factor(0.0, 100.0) is None


def test_frozen_close_prefers_explicit_close():
    assert frozen_close_from_details({"close": 377.16, "ewma_value": 444.88,
                                      "deviation_pct": -15.22}) == 377.16


def test_frozen_close_derived_from_ewma_and_deviation():
    # Legacy rows (pre close-field): close = ewma * (1 + dev%/100).
    close = frozen_close_from_details({"ewma_value": 444.88, "deviation_pct": -15.22})
    assert abs(close - 377.16) < 0.05


def test_frozen_close_none_when_underivable():
    assert frozen_close_from_details({}) is None
    assert frozen_close_from_details({"ewma_value": 100.0}) is None
    assert frozen_close_from_details(None) is None


# ---------------------------------------------------------------------------
# Basis-break detection (the CRWD 4:1 split)
# ---------------------------------------------------------------------------

def test_split_is_detected_as_basis_break():
    n = 10
    d = _dates(n)
    # Current fetch is post-split (÷4); the frozen reference was written pre-split.
    res = _frame({"SPLIT": [100.0 + i for i in range(n)],
                  "SANE": [50.0 + i for i in range(n)]})
    reference = {
        ("SPLIT", d[2]): (100.0 + 2) * 4,
        ("SPLIT", d[5]): (100.0 + 5) * 4,
        ("SANE", d[3]): 53.0,
    }
    breaks = detect_price_basis_breaks(res, reference)
    assert set(breaks) == {"SPLIT"}
    assert abs(breaks["SPLIT"]["factor"] - 4.0) < 1e-6
    assert breaks["SPLIT"]["n_bars_affected"] == 2
    assert breaks["SPLIT"]["last_affected_date"] == d[5]


def test_dividend_sized_drift_is_not_a_break():
    """Routine dividend re-adjustments (<1%) must stay inside tolerance."""
    n = 6
    d = _dates(n)
    res = _frame({"DIV": [100.0] * n})
    reference = {("DIV", d[1]): 100.6}  # 0.6% drift
    assert detect_price_basis_breaks(res, reference) == {}


def test_reverse_split_detected_below_one():
    n = 6
    d = _dates(n)
    res = _frame({"RSPLIT": [200.0] * n})  # current basis after a 1:10 reverse split
    reference = {("RSPLIT", d[1]): 20.0}
    breaks = detect_price_basis_breaks(res, reference)
    assert abs(breaks["RSPLIT"]["factor"] - 0.1) < 1e-6


def test_bars_absent_from_current_fetch_are_ignored():
    res = _frame({"AAA": [100.0] * 5})
    reference = {("AAA", "2019-01-02"): 400.0, ("GONE", "2026-01-06"): 10.0}
    assert detect_price_basis_breaks(res, reference) == {}


# ---------------------------------------------------------------------------
# Stale-feed watchdog
# ---------------------------------------------------------------------------

def test_trailing_flat_run_counts_from_the_tail():
    assert trailing_flat_run(pd.Series([1.0, 2.0, 3.0, 3.0, 3.0])) == 3
    assert trailing_flat_run(pd.Series([5.0, 5.0, 5.0, 5.0, 6.0])) == 1
    assert trailing_flat_run(pd.Series([], dtype=float)) == 0


def test_flatlined_tail_is_flagged_stale():
    moving = [100 + i * 0.5 for i in range(20)]
    frozen = [100 + i * 0.5 for i in range(14)] + [248.15] * 6
    res = _frame({"OK": moving, "DEAD": frozen})
    stale = detect_stale_feeds(res, min_bars=5)
    assert stale == {"DEAD": 6}


def test_mid_series_flat_is_not_stale():
    """Only a flat TAIL means the feed is currently frozen."""
    closes = [100.0] * 6 + [101.0, 102.0, 103.0]
    res = _frame({"AAA": closes})
    assert detect_stale_feeds(res, min_bars=5) == {}


def test_feed_that_stops_publishing_bars_is_stale():
    """Second failure mode: the ticker's last bar falls N+ sessions behind
    the rest of the universe — dead feed, even with no flat tail."""
    n = 20
    moving = [100 + i * 0.5 for i in range(n)]
    res = _frame({"OK": moving, "GONE": moving[: n - 6]})
    stale = detect_stale_feeds(res, min_bars=5)
    assert stale == {"GONE": 6}


def test_exempt_tickers_are_never_stale_flagged():
    frozen = [91.5] * 12
    res = _frame({"BIL": frozen})
    assert detect_stale_feeds(res, min_bars=5, exempt=frozenset({"BIL"})) == {}
    assert detect_stale_feeds(res, min_bars=5) == {"BIL": 12}


def test_recovery_run_phantom_prints_never_persist():
    """When a frozen feed resumes without revising history, the flat run is
    mid-series, the ticker is un-flagged, and its held-back bars flow to
    persistence — the repeats must still be filtered out permanently."""
    from anomaly_detection.adjustments import phantom_flat_dates

    closes = [100.0, 101.0, 102.0] + [248.15] * 6 + [140.0]  # recovered at the tail
    res = _frame({"ORCL2": closes})
    d = _dates(len(closes))
    assert detect_stale_feeds(res, min_bars=5) == {}  # tail moved: un-flagged
    phantoms = phantom_flat_dates(res, min_bars=5)
    # Repeats of the 6-bar flat run (bars 4..8) are phantom; the first
    # print (bar 3) and the recovery bar are kept.
    assert phantoms == {("ORCL2", d[i]) for i in range(4, 9)}


def test_short_flat_runs_are_not_phantom():
    """2-3 identical closes happen on real, healthy series (measured max on
    this universe: 3) — they must never be withheld."""
    from anomaly_detection.adjustments import phantom_flat_dates

    closes = [100.0, 100.0, 100.0, 101.0, 102.0, 102.0, 103.0]
    res = _frame({"AAA": closes})
    assert phantom_flat_dates(res, min_bars=5) == set()


def test_drop_stale_tails_removes_phantom_bars_only():
    """The frame handed to the backtest must lose a stale ticker's repeated
    tail (keeping the first print, which may be genuine) so a dead feed
    cannot mint fills or exits; healthy tickers pass through untouched."""
    from anomaly_detection.adjustments import drop_stale_tails

    moving = [100 + i for i in range(10)]
    frozen = [50 + i for i in range(4)] + [53.0] * 5  # 53.0 printed 6x (incl. genuine)
    res = _frame({"OK": moving, "DEAD": frozen})
    stale = detect_stale_feeds(res, min_bars=5)
    out = drop_stale_tails(res, stale)
    assert len(out[out.Ticker == "OK"]) == 10
    dead = out[out.Ticker == "DEAD"].sort_values("Date")
    assert len(dead) == 4  # 3 moving bars + the first 53.0 print
    assert dead["Close"].iloc[-1] == 53.0


# ---------------------------------------------------------------------------
# Ticker status view + alerts.json run metadata
# ---------------------------------------------------------------------------

def test_ticker_status_reports_current_close_and_flags():
    n = 8
    res = _frame({"AAA": [100.0 + i for i in range(n)],
                  "BRK": [25.0] * n})
    status = compute_ticker_status(
        res,
        basis_breaks={"BRK": {"factor": 4.0, "n_bars_affected": 2,
                              "n_bars_checked": 2, "last_affected_date": "2026-01-07"}},
        stale_feeds={"BRK": 8},
    )
    aaa, brk = status["AAA"], status["BRK"]
    assert aaa["last_close"] == 100.0 + n - 1
    assert aaa["last_date"] == _dates(n)[-1]
    assert aaa["stale_feed"] is False
    assert "price_basis" not in aaa
    assert brk["stale_feed"] is True and brk["stale_bars"] == 8
    assert brk["price_basis"]["factor"] == 4.0


def test_alerts_json_carries_run_metadata_and_ticker_status(tmp_path):
    """A quiet run (0 new signals) must still prove the model ran: the file
    carries how many new bars were scored and through which bar date."""
    path = str(tmp_path / "alerts.json")
    run_info = {"run_date": "2026-07-10", "new_bars_scored": 130,
                "latest_bar_date": "2026-07-10", "tickers_scored": 130,
                "new_signals": 0}
    status = {"ORCL": {"last_close": 140.64, "last_date": "2026-07-10",
                       "stale_feed": False}}
    alerts_to_json([], path, run_info=run_info, ticker_status=status)
    data = json.loads(open(path).read())
    assert data["run"]["new_bars_scored"] == 130
    assert data["run"]["latest_bar_date"] == "2026-07-10"
    assert data["ticker_status"]["ORCL"]["last_close"] == 140.64
    assert data["new_signals"] == 0 and data["signals"] == []


def test_dashboard_annotation_falls_back_to_ticker_basis_for_missing_bars():
    """A split ticker's frozen row whose bar date is absent from the current
    fetch must still get a basis badge (via the ticker-level break factor) —
    never a bare pre-split price next to a post-split 'now' price."""
    from anomaly_detection.visualization.dashboard import _annotate_price_basis

    n = 6
    res = _frame({"SPLIT": [100.0 + i for i in range(n)]})
    alert = {"ticker": "SPLIT", "date": "2025-06-02", "close": 408.0}  # bar not in res
    status = {"SPLIT": {"last_close": 105.0, "last_date": _dates(n)[-1],
                        "stale_feed": False,
                        "price_basis": {"factor": 4.0, "n_bars_affected": 3,
                                        "n_bars_checked": 3,
                                        "last_affected_date": "2026-01-05"}}}
    _annotate_price_basis([alert], res, ticker_status=status)
    assert alert["basis_factor"] == 4.0
    assert alert["basis_changed"] is True
    assert alert["current_price"] == 105.0
    # pct measured basis-adjusted: 105 / (408/4) - 1 = +2.9%
    assert abs(alert["pct_since"] - 2.9) < 0.05


def test_dashboard_annotation_uses_exact_bar_factor_when_available():
    from anomaly_detection.visualization.dashboard import _annotate_price_basis

    n = 6
    d = _dates(n)
    res = _frame({"AAA": [100.0 + i for i in range(n)]})
    alert = {"ticker": "AAA", "date": d[2], "close": 102.0}  # matches current bar
    _annotate_price_basis([alert], res)
    assert alert["basis_factor"] == 1.0
    assert alert["basis_changed"] is False
    assert alert["current_price"] == 105.0
    assert abs(alert["pct_since"] - 2.9) < 0.05


def test_new_alerts_freeze_the_detection_basis_close():
    """Every new signal must record its close so future basis breaks can be
    reconciled without algebra on rounded fields."""
    row = pd.Series({
        "Ticker": "TEST", "Close": 782.17, "consensus_score": 0.6,
        "dev_z": 3.3, "deviation_pct": 27.07, "trajectory": "extending",
        "methods_flagged": 2, "fourier_anomaly": False, "mp_anomaly": False,
        "ensemble_anomaly": True, "ewma_anomaly": True, "ewma_value": 615.52,
        "consensus_anomaly": True, "Date": pd.Timestamp("2026-06-01"),
        "fourier_score": 0.0, "mp_score": 0.0, "ensemble_score": 0.7,
        "ewma_score": 0.7,
    })
    alerts = generate_alerts(pd.DataFrame([row]), provenance="live")
    assert alerts[0]["details"]["close"] == 782.17


def test_ticker_status_reports_last_real_close_not_nan():
    import numpy as np
    import pandas as pd
    from anomaly_detection.adjustments import compute_ticker_status
    dates = pd.bdate_range("2026-08-31", periods=4)
    res = pd.DataFrame({"Ticker": "AAA", "Date": dates, "Close": [10.0, 11.0, 12.0, np.nan]})
    status = compute_ticker_status(res)
    assert status["AAA"]["last_close"] == 12.0
    assert status["AAA"]["last_date"] == "2026-09-02"
