"""Detection quality on controlled synthetic data.

Two properties matter for a detector that feeds a trade ledger:
  SENSITIVITY — an injected crash must be caught, promptly;
  SPECIFICITY — featureless data must produce a quiet report, and a
                near-constant series must never produce trade calls.
The v1 percentile thresholds failed specificity by construction (they
flagged a fixed share of bars no matter what). These tests pin the fix.
"""

import numpy as np

from anomaly_detection.alerts import generate_alerts
from anomaly_detection.detection.engine import run_all


def test_injected_crash_is_detected(synthetic_features):
    """A 5-day ~22% crash must produce consensus anomalies within the window."""
    res = run_all(synthetic_features, sensitivity="medium")
    crash = res[res.Ticker == "CRASH"].reset_index(drop=True)
    window = crash.iloc[180:188]
    assert window["consensus_anomaly"].any(), "crash window produced no consensus anomaly"
    assert (window["methods_flagged"] >= 2).any(), "no multi-method agreement on the crash"
    # The standardized deviation must register the move as extreme.
    assert window["dev_z"].min() < -3.0


def test_crash_reaches_breakout_trajectory(synthetic_features):
    """The trajectory classifier must be reachable by real-world-sized moves
    (v1 required an 80% deviation — unreachable — so SHORT never fired)."""
    res = run_all(synthetic_features, sensitivity="medium")
    crash = res[res.Ticker == "CRASH"].reset_index(drop=True)
    assert (crash.iloc[180:190]["trajectory"] == "breakout").any()


def test_quiet_walk_has_low_false_positive_rate(synthetic_features):
    """A plain random walk should flag only a small share of bars."""
    res = run_all(synthetic_features, sensitivity="medium")
    walk = res[res.Ticker == "WALK"]
    rate = walk["consensus_anomaly"].mean()
    assert rate < 0.03, f"false-positive rate {rate:.1%} on featureless random walk"


def test_near_constant_series_produces_no_trade_calls(synthetic_features):
    """A BIL-like series may occasionally be statistically anomalous *for
    itself*, but the materiality gate must keep it out of the trade ledger."""
    res = run_all(synthetic_features, sensitivity="medium")
    quiet_bars = res[(res.Ticker == "QUIET") & res.consensus_anomaly]
    if quiet_bars.empty:
        return  # even better: nothing flagged at all
    alerts = generate_alerts(quiet_bars, sensitivity="medium")
    tradable = [a for a in alerts if a["signal"] in ("BUY", "SELL", "LONG", "SHORT")]
    assert not tradable, f"near-constant series produced trade calls: {tradable}"


def test_scores_share_a_fixed_interpretable_scale(synthetic_features):
    """All method scores live on [0,1] where 1.0 = 4 sigma — no per-ticker
    max-normalization (v1 pinned every ticker's worst day to exactly 1.0)."""
    res = run_all(synthetic_features, sensitivity="medium")
    for col in ["fourier_score", "mp_score", "ensemble_score", "ewma_score", "consensus_score"]:
        assert res[col].min() >= 0.0
        assert res[col].max() <= 1.0
    # A quiet series must NOT have its max score pinned at 1.0.
    quiet = res[res.Ticker == "QUIET"]
    assert quiet["mp_score"].max() < 1.0 or quiet["ewma_score"].max() < 1.0


def test_warmup_bars_never_flag(synthetic_features):
    """Detectors must not flag while still learning what normal looks like."""
    res = run_all(synthetic_features, sensitivity="medium")
    for _, grp in res.groupby("Ticker"):
        g = grp.sort_values("Date").head(60)
        assert not g["consensus_anomaly"].any(), "flag raised during warmup"


def test_dev_z_adapts_to_ticker_scale(synthetic_features):
    """The same |dev_z| threshold must judge each ticker against itself:
    the quiet series' deviations in % terms are tiny, but its dev_z spread
    should be comparable to the walk's (both are standardized)."""
    res = run_all(synthetic_features, sensitivity="medium")
    walk_z = res[res.Ticker == "WALK"]["dev_z"].abs().quantile(0.95)
    quiet_z = res[res.Ticker == "QUIET"]["dev_z"].abs().quantile(0.95)
    assert quiet_z > 0.5, "quiet series dev_z degenerate — standardization broken"
    assert np.isfinite(walk_z) and np.isfinite(quiet_z)
    assert 0.2 < quiet_z / walk_z < 5.0, "dev_z scales not comparable across tickers"
