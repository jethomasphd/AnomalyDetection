"""Matrix Profile anomaly detection (via STUMPY).

Uses the Matrix Profile algorithm to find subsequences whose nearest-
neighbor distance is unusually large — these are patterns the stock
has *never done before*.

Plain-English: "Is this stock doing something it's never done?"
"""

import logging

import numpy as np
import pandas as pd
import stumpy

from ..config import MP_SUBSEQUENCE_LENGTH, SENSITIVITY_PRESETS

logger = logging.getLogger(__name__)


def detect(
    df: pd.DataFrame,
    sensitivity: str = "medium",
    subsequence_length: int = MP_SUBSEQUENCE_LENGTH,
) -> pd.DataFrame:
    """Run Matrix Profile anomaly detection on each ticker.

    Returns a DataFrame with columns:
        Ticker, Date, mp_score, mp_anomaly (bool)
    """
    preset = SENSITIVITY_PRESETS[sensitivity]
    results = []

    for ticker, grp in df.groupby("Ticker"):
        g = grp.sort_values("Date").copy()
        closes = g["Close"].values.astype(np.float64)
        dates = g["Date"].values

        if len(closes) < subsequence_length * 2:
            logger.info("MatrixProfile: skipping %s (insufficient data)", ticker)
            continue

        # Compute the matrix profile
        mp = stumpy.stump(closes, m=subsequence_length)
        mp_distances = mp[:, 0].astype(float)

        # Normalize to [0, 1] range for comparability
        mp_max = mp_distances.max()
        if mp_max > 0:
            mp_norm = mp_distances / mp_max
        else:
            mp_norm = mp_distances

        threshold = np.percentile(mp_norm, preset["percentile"])

        # Pad front (matrix profile is shorter than original series)
        pad_len = len(closes) - len(mp_norm)
        scores_full = np.concatenate([np.zeros(pad_len), mp_norm])

        for i in range(len(closes)):
            results.append(
                {
                    "Ticker": ticker,
                    "Date": dates[i],
                    "mp_score": round(float(scores_full[i]), 6),
                    "mp_anomaly": bool(scores_full[i] > threshold),
                }
            )

    return pd.DataFrame(results)
