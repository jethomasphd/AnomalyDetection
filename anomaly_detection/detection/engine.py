"""Detection engine — orchestrates all four causal methods into a consensus.

All four methods emit scores on a single fixed scale (score = robust-z / 4,
capped at 1.0: 0.50 = 2 sigma, 0.625 = 2.5 sigma). The consensus score is a
weighted average on that same scale, and the consensus flag uses fixed,
documented cutoffs — never a quantile of the run's own output, which would
force a fixed share of bars to be "anomalous" no matter how quiet the tape.

Causality contract: every score and flag for bar t is computed from bars
[0..t] only. Appending future bars never changes a past verdict.
"""

import logging

import numpy as np
import pandas as pd

from ..config import METHOD_WEIGHTS, SENSITIVITY_PRESETS, Z_SCORE_CAP
from . import ensemble, ewma, fourier, matrix_profile

logger = logging.getLogger(__name__)


def consensus_cutoff(sensitivity: str) -> float:
    """Consensus-score cutoff on the 0..1 scale.

    Equal to z_threshold / Z_SCORE_CAP: a consensus score whose weighted
    average corresponds to the sensitivity's sigma threshold (e.g. medium:
    2.5 sigma -> 0.625).
    """
    return SENSITIVITY_PRESETS[sensitivity]["z_threshold"] / Z_SCORE_CAP


def run_all(
    df: pd.DataFrame,
    sensitivity: str = "medium",
) -> pd.DataFrame:
    """Run all four detection methods and merge into a single results table.

    Returns a DataFrame keyed by (Ticker, Date) with all individual method
    scores, anomaly flags, and unified consensus_score + consensus_anomaly.
    """
    logger.info("Running Fourier detection (causal) ...")
    fourier_df = fourier.detect(df, sensitivity=sensitivity)

    logger.info("Running Matrix Profile detection (causal left profile) ...")
    mp_df = matrix_profile.detect(df, sensitivity=sensitivity)

    logger.info("Running Ensemble detection (causal walk-forward) ...")
    ensemble_df = ensemble.detect(df, sensitivity=sensitivity)

    logger.info("Running EWMA detection (standardized deviation) ...")
    ewma_df = ewma.detect(df, sensitivity=sensitivity)

    base = df[["Ticker", "Date", "Close", "Volume"]].copy()
    if "daily_return" in df.columns:
        base["daily_return"] = df["daily_return"]

    key = ["Ticker", "Date"]
    merged = base.copy()
    for result_df in [fourier_df, mp_df, ensemble_df, ewma_df]:
        if not result_df.empty:
            merged = merged.merge(result_df, on=key, how="left")

    score_cols = ["fourier_score", "mp_score", "ensemble_score", "ewma_score"]
    for col in score_cols:
        if col in merged.columns:
            merged[col] = merged[col].fillna(0)
        else:
            merged[col] = 0.0

    # Consensus score: weighted average of method scores — all on the same
    # fixed 0..1 scale, so weights mean what they say.
    w = METHOD_WEIGHTS
    merged["consensus_score"] = (
        w["fourier"] * merged["fourier_score"]
        + w["matrix_profile"] * merged["mp_score"]
        + w["ensemble"] * merged["ensemble_score"]
        + w["ewma"] * merged["ewma_score"]
    )

    anomaly_cols = ["fourier_anomaly", "mp_anomaly", "ensemble_anomaly", "ewma_anomaly"]
    for col in anomaly_cols:
        if col not in merged.columns:
            merged[col] = False
        merged[col] = merged[col].astype(object).fillna(False).astype(bool)

    merged["methods_flagged"] = merged[anomaly_cols].sum(axis=1).astype(int)

    # Consensus anomaly: 2+ methods agree, OR the weighted score alone
    # crosses the sensitivity's sigma-equivalent cutoff. Fixed thresholds —
    # a quiet tape produces a quiet report.
    cutoff = consensus_cutoff(sensitivity)
    merged["consensus_anomaly"] = (merged["methods_flagged"] >= 2) | (
        merged["consensus_score"] >= cutoff
    )

    merged = merged.sort_values(["Ticker", "Date"]).reset_index(drop=True)

    n_anomalies = int(merged["consensus_anomaly"].sum())
    logger.info(
        "Detection complete: %d anomalies found across %d ticker-days",
        n_anomalies,
        len(merged),
    )
    return merged
