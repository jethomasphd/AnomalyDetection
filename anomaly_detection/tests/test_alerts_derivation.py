"""Signal derivation rules: sigma-based, materiality-gated, honestly described."""

import pandas as pd

from anomaly_detection.alerts import _derive_signal, _describe_signal, generate_alerts


def _row(**kw) -> pd.Series:
    base = {
        "Ticker": "TEST", "Close": 100.0, "consensus_score": 0.6,
        "dev_z": 0.0, "deviation_pct": 0.0, "trajectory": "stable",
        "methods_flagged": 2, "fourier_anomaly": False, "mp_anomaly": False,
        "ensemble_anomaly": True, "ewma_anomaly": True, "ewma_value": 100.0,
        "consensus_anomaly": True, "Date": pd.Timestamp("2026-03-02"),
        "fourier_score": 0.0, "mp_score": 0.0, "ensemble_score": 0.7, "ewma_score": 0.7,
    }
    base.update(kw)
    return pd.Series(base)


def test_buy_deep_oversold_reverting():
    sig, conf = _derive_signal(_row(dev_z=-3.0, deviation_pct=-6.0, trajectory="reverting"))
    assert sig == "BUY"


def test_sell_deep_overbought_stable():
    sig, _ = _derive_signal(_row(dev_z=3.0, deviation_pct=6.0, trajectory="stable"))
    assert sig == "SELL"


def test_short_extending_decline():
    sig, _ = _derive_signal(_row(dev_z=-2.0, deviation_pct=-4.0, trajectory="extending"))
    assert sig == "SHORT"


def test_long_extending_rally():
    sig, _ = _derive_signal(_row(dev_z=2.0, deviation_pct=4.0, trajectory="extending"))
    assert sig == "LONG"


def test_breakout_washout_is_faded_not_shorted():
    """Climactic downside extremes are bought, not chased: the measured
    resolution of >3.5-sigma washouts is a rebound (overreaction reversal)."""
    sig, _ = _derive_signal(_row(dev_z=-3.8, deviation_pct=-8.0, trajectory="breakout"))
    assert sig == "BUY"


def test_breakout_blowoff_is_faded_not_chased():
    sig, _ = _derive_signal(_row(dev_z=3.8, deviation_pct=8.0, trajectory="breakout"))
    assert sig == "SELL"


def test_materiality_gate_blocks_tiny_moves():
    """Statistically extreme but economically trivial: WATCH, never a trade.
    This is the rule that keeps a 4-sigma 0.15% T-bill wiggle out of the book."""
    sig, _ = _derive_signal(_row(dev_z=-4.0, deviation_pct=-0.15, trajectory="reverting"))
    assert sig == "WATCH"


def test_single_method_cannot_trade():
    sig, _ = _derive_signal(_row(dev_z=-3.0, deviation_pct=-6.0,
                                 trajectory="reverting", methods_flagged=1))
    assert sig == "WATCH"


def test_structural_break_reduces():
    sig, _ = _derive_signal(_row(dev_z=0.5, deviation_pct=1.0,
                                 fourier_anomaly=True, mp_anomaly=True))
    assert sig == "REDUCE"


def test_confidence_tiers():
    _, strong = _derive_signal(_row(dev_z=-3.0, deviation_pct=-6.0,
                                    trajectory="reverting", methods_flagged=3))
    _, moderate = _derive_signal(_row(dev_z=-3.0, deviation_pct=-6.0,
                                      trajectory="reverting", methods_flagged=2))
    assert strong == "Strong"
    assert moderate == "Moderate"


def test_description_reports_sigma_not_method_count():
    """v1 wrote 'oversold at {methods_flagged} standard deviations' — the
    description must quote the actual standardized deviation."""
    row = _row(dev_z=-3.2, deviation_pct=-6.4, trajectory="reverting")
    desc = _describe_signal(row, "BUY", "Moderate")
    assert "3.2-sigma" in desc
    assert "2 of 4 methods" in desc


def test_backfill_alerts_are_dated_to_bar_and_not_new():
    df = pd.DataFrame([_row(dev_z=-3.0, deviation_pct=-6.0, trajectory="reverting")])
    alerts = generate_alerts(df, sensitivity="medium", provenance="backfill")
    assert len(alerts) == 1
    a = alerts[0]
    assert a["detected_at"] == a["date"] == "2026-03-02"
    assert a["is_new"] is False
    assert a["provenance"] == "backfill"


def test_live_alerts_are_marked_new():
    df = pd.DataFrame([_row(dev_z=-3.0, deviation_pct=-6.0, trajectory="reverting")])
    alerts = generate_alerts(df, sensitivity="medium", provenance="live")
    assert alerts[0]["is_new"] is True
    assert alerts[0]["provenance"] == "live"
    assert alerts[0]["details"]["dev_z"] == -3.0
