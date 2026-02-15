"""Matrix Profile anomaly detection (via STUMPY) for Google Postmaster spam rate data.

"FEEL THE RHYME"

The Matrix Profile algorithm answers: for every recent 7-day window
of spam rate behavior, what is the most similar historical window?
If even the best match is poor, the current pattern is genuinely
novel — something the domain has *never exhibited before*.

When the rhyme changes, it means this domain's spam rate is doing
something it has literally never done. That's worth paying attention to.

Plain-English: "Is this domain's spam rate doing something it's never done before?"
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
    """Run Matrix Profile anomaly detection on each domain's spam rate.

    Returns a DataFrame with columns:
        Domain, Date, mp_score, mp_anomaly (bool)
    """
    preset = SENSITIVITY_PRESETS[sensitivity]
    results = []

    for domain, grp in df.groupby("Domain"):
        g = grp.sort_values("Date").copy()
        spam_rate = g["SpamRate"].values.astype(np.float64)
        dates = g["Date"].values

        if len(spam_rate) < subsequence_length * 2:
            logger.info("MatrixProfile: skipping %s (insufficient data)", domain)
            continue

        # Check for constant series (STUMPY can't handle zero variance)
        if np.std(spam_rate) < 1e-10:
            logger.info("MatrixProfile: skipping %s (constant spam rate)", domain)
            for i in range(len(spam_rate)):
                results.append({
                    "Domain": domain,
                    "Date": dates[i],
                    "mp_score": 0.0,
                    "mp_anomaly": False,
                })
            continue

        # Compute the matrix profile
        mp = stumpy.stump(spam_rate, m=subsequence_length)
        mp_distances = mp[:, 0].astype(float)

        # Normalize to [0, 1] range
        mp_max = mp_distances.max()
        if mp_max > 0:
            mp_norm = mp_distances / mp_max
        else:
            mp_norm = mp_distances

        threshold = np.percentile(mp_norm, preset["percentile"])

        # Pad front (matrix profile is shorter than original series)
        pad_len = len(spam_rate) - len(mp_norm)
        scores_full = np.concatenate([np.zeros(pad_len), mp_norm])

        for i in range(len(spam_rate)):
            results.append(
                {
                    "Domain": domain,
                    "Date": dates[i],
                    "mp_score": round(float(scores_full[i]), 6),
                    "mp_anomaly": bool(scores_full[i] > threshold),
                }
            )

    return pd.DataFrame(results)
