"""Detection engine — orchestrates all four detection methods and produces a consensus score."""

import logging

import pandas as pd

from ..config import METHOD_WEIGHTS
from . import ensemble, ewma, fourier, matrix_profile

logger = logging.getLogger(__name__)


def run_all(
    df: pd.DataFrame,
    sensitivity: str = "medium",
) -> pd.DataFrame:
    """Run all four detection methods and merge into a single results table.

    Returns a DataFrame indexed by (Domain, Date) with all individual
    method scores, anomaly flags, and a unified consensus_score + consensus_anomaly.
    """
    logger.info("Running Fourier detection ...")
    fourier_df = fourier.detect(df, sensitivity=sensitivity)

    logger.info("Running Matrix Profile detection ...")
    mp_df = matrix_profile.detect(df, sensitivity=sensitivity)

    logger.info("Running Ensemble detection ...")
    ensemble_df = ensemble.detect(df, sensitivity=sensitivity)

    logger.info("Running EWMA detection ...")
    ewma_df = ewma.detect(df, sensitivity=sensitivity)

    # Start with the base data
    base = df[["Domain", "Date", "Clicks", "Sent"]].copy()
    if "click_change" in df.columns:
        base["click_change"] = df["click_change"]

    # Merge all results
    key = ["Domain", "Date"]

    merged = base.copy()
    for result_df in [fourier_df, mp_df, ensemble_df, ewma_df]:
        if not result_df.empty:
            merged = merged.merge(result_df, on=key, how="left")

    # Fill NaN scores with 0
    score_cols = ["fourier_score", "mp_score", "ensemble_score", "ewma_score"]
    for col in score_cols:
        if col in merged.columns:
            merged[col] = merged[col].fillna(0)
        else:
            merged[col] = 0

    # Compute consensus score (weighted average of method scores)
    w = METHOD_WEIGHTS
    merged["consensus_score"] = (
        w["fourier"] * merged["fourier_score"]
        + w["matrix_profile"] * merged["mp_score"]
        + w["ensemble"] * merged["ensemble_score"]
        + w["ewma"] * merged["ewma_score"]
    )

    # Count how many methods flagged anomaly
    anomaly_cols = ["fourier_anomaly", "mp_anomaly", "ensemble_anomaly", "ewma_anomaly"]
    for col in anomaly_cols:
        if col not in merged.columns:
            merged[col] = False
        merged[col] = merged[col].fillna(False)

    merged["methods_flagged"] = merged[anomaly_cols].sum(axis=1).astype(int)

    # Consensus anomaly: flagged if 2+ methods agree OR consensus_score is extreme
    merged["consensus_anomaly"] = (merged["methods_flagged"] >= 2) | (
        merged["consensus_score"] > merged["consensus_score"].quantile(0.975)
    )

    merged = merged.sort_values(["Domain", "Date"]).reset_index(drop=True)

    n_anomalies = merged["consensus_anomaly"].sum()
    logger.info(
        "Detection complete: %d anomalies found across %d domain-days",
        n_anomalies,
        len(merged),
    )
    return merged
