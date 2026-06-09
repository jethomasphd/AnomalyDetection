"""THE load-bearing invariant: detection is causal.

Every score and flag computed for bar t must depend only on bars [0..t].
Operationally: scoring a PREFIX of the data must produce byte-identical
verdicts to scoring the full series, for every bar in the prefix.

This is what makes the historical backfill a legitimate walk-forward
simulation, makes frozen ledger verdicts stable across reruns, and makes
the live record follow the exact same rules as the backtest. If any of
these tests fails, the system's central claim is false — do not weaken
them to make a detector change pass.
"""

import pandas as pd
import pytest

from anomaly_detection.detection import ensemble, ewma, fourier, matrix_profile
from anomaly_detection.detection.engine import run_all

PREFIX_BARS = 200  # full series is 240 bars; 40 bars of "the future" appended


def _prefix(features: pd.DataFrame, n: int = PREFIX_BARS) -> pd.DataFrame:
    return features.groupby("Ticker", group_keys=False).head(n)


def _assert_prefix_invariant(full_df: pd.DataFrame, prefix_df: pd.DataFrame, cols: list[str]):
    merged = prefix_df.merge(full_df, on=["Ticker", "Date"], suffixes=("_prefix", "_full"))
    assert len(merged) == len(prefix_df), "prefix rows must all exist in full run"
    for col in cols:
        a, b = merged[f"{col}_prefix"], merged[f"{col}_full"]
        if pd.api.types.is_numeric_dtype(a) and not pd.api.types.is_bool_dtype(a):
            mismatches = ((a - b).abs() > 0).sum()
        else:
            mismatches = (a != b).sum()
        assert mismatches == 0, (
            f"{col}: {mismatches} of {len(merged)} prefix bars changed when "
            f"future data was appended — detector is NOT causal"
        )


def test_fourier_is_causal(synthetic_features):
    full = fourier.detect(synthetic_features)
    pre = fourier.detect(_prefix(synthetic_features))
    _assert_prefix_invariant(full, pre, ["fourier_score", "fourier_z", "fourier_anomaly"])


def test_matrix_profile_is_causal(synthetic_features):
    full = matrix_profile.detect(synthetic_features)
    pre = matrix_profile.detect(_prefix(synthetic_features))
    _assert_prefix_invariant(full, pre, ["mp_score", "mp_z", "mp_anomaly"])


def test_ensemble_is_causal(synthetic_features):
    full = ensemble.detect(synthetic_features)
    pre = ensemble.detect(_prefix(synthetic_features))
    _assert_prefix_invariant(
        full, pre,
        ["ensemble_score", "ensemble_z", "ensemble_anomaly",
         "zscore_component", "seasonal_component", "iforest_component"],
    )


def test_ewma_is_causal(synthetic_features):
    full = ewma.detect(synthetic_features)
    pre = ewma.detect(_prefix(synthetic_features))
    _assert_prefix_invariant(
        full, pre,
        ["ewma_score", "ewma_anomaly", "deviation_pct", "dev_z", "trajectory"],
    )


def test_engine_consensus_is_causal(synthetic_features):
    """The merged consensus — what actually gets persisted — is prefix-invariant."""
    full = run_all(synthetic_features, sensitivity="medium")
    pre = run_all(_prefix(synthetic_features), sensitivity="medium")
    _assert_prefix_invariant(
        full, pre,
        ["consensus_score", "consensus_anomaly", "methods_flagged"],
    )


@pytest.mark.parametrize("sensitivity", ["low", "high"])
def test_causality_holds_at_all_sensitivities(synthetic_features, sensitivity):
    full = run_all(synthetic_features, sensitivity=sensitivity)
    pre = run_all(_prefix(synthetic_features), sensitivity=sensitivity)
    _assert_prefix_invariant(full, pre, ["consensus_anomaly", "consensus_score"])
