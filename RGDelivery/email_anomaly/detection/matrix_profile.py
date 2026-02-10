"""Matrix Profile anomaly detection (via STUMPY) for email click data.

Uses the Matrix Profile algorithm to find subsequences whose nearest-
neighbor distance is unusually large — these are click patterns the
domain has *never exhibited before*.

Plain-English: "Is this domain showing a click pattern it's never had?"
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
    """Run Matrix Profile anomaly detection on each domain.

    Returns a DataFrame with columns:
        Domain, Date, mp_score, mp_anomaly (bool)
    """
    preset = SENSITIVITY_PRESETS[sensitivity]
    results = []

    for domain, grp in df.groupby("Domain"):
        g = grp.sort_values("Date").copy()
        clicks = g["Clicks"].values.astype(np.float64)
        dates = g["Date"].values

        if len(clicks) < subsequence_length * 2:
            logger.info("MatrixProfile: skipping %s (insufficient data)", domain)
            continue

        # Compute the matrix profile
        mp = stumpy.stump(clicks, m=subsequence_length)
        mp_distances = mp[:, 0].astype(float)

        # Normalize to [0, 1] range
        mp_max = mp_distances.max()
        if mp_max > 0:
            mp_norm = mp_distances / mp_max
        else:
            mp_norm = mp_distances

        threshold = np.percentile(mp_norm, preset["percentile"])

        # Pad front (matrix profile is shorter than original series)
        pad_len = len(clicks) - len(mp_norm)
        scores_full = np.concatenate([np.zeros(pad_len), mp_norm])

        for i in range(len(clicks)):
            results.append(
                {
                    "Domain": domain,
                    "Date": dates[i],
                    "mp_score": round(float(scores_full[i]), 6),
                    "mp_anomaly": bool(scores_full[i] > threshold),
                }
            )

    return pd.DataFrame(results)
