"""Matrix Profile anomaly detection via STUMPY (causal, left profile).

Uses STUMPY's incremental engine (`stumpy.stumpi`) to maintain the LEFT
matrix profile: for the subsequence ending at bar t, the z-normalized
distance to its nearest neighbor among subsequences that occurred STRICTLY
EARLIER. This is the honest formulation of novelty — "is this pattern
unlike anything that came before?" — whereas the classic full matrix
profile would happily match a pattern against its own future.

The raw left-profile distance stream is standardized against its expanding
history (robust z) so the flag adapts to each ticker's own pattern
variability.

Plain-English: "Is this stock doing something it's *never done before*?"
"""

import logging

import numpy as np
import pandas as pd
import stumpy

from ..config import CAUSAL_WARMUP_BARS, MP_SUBSEQUENCE_LENGTH, SENSITIVITY_PRESETS
from .causal import causal_robust_z, z_to_unit

logger = logging.getLogger(__name__)


def _left_profile(closes: np.ndarray, m: int) -> np.ndarray:
    """Left matrix profile distances, aligned to the LAST bar of each window.

    Returns an array the same length as `closes`; entry t is the distance
    from the subsequence closes[t-m+1 .. t] to its nearest preceding
    neighbor. The first bars (no complete window, or no left neighbor yet)
    are 0. Non-finite distances (constant subsequences, warmup infs) are 0.
    """
    n = len(closes)
    out = np.zeros(n)
    init = max(2 * m, m + 1)
    if n <= init:
        return out

    stream = stumpy.stumpi(closes[:init], m, egress=False)
    for x in closes[init:]:
        stream.update(x)

    left = np.asarray(stream.left_P_, dtype=float)  # length n - m + 1
    left[~np.isfinite(left)] = 0.0
    # left[i] describes the subsequence STARTING at i; its last bar is i+m-1.
    out[m - 1 :] = left
    return out


def detect(
    df: pd.DataFrame,
    sensitivity: str = "medium",
    subsequence_length: int = MP_SUBSEQUENCE_LENGTH,
) -> pd.DataFrame:
    """Run causal Matrix Profile anomaly detection on each ticker.

    Returns a DataFrame with columns:
        Ticker, Date, mp_score (0..1, 0.5 = 2 sigma), mp_z, mp_anomaly (bool)
    """
    z_threshold = SENSITIVITY_PRESETS[sensitivity]["z_threshold"]
    results = []

    for ticker, grp in df.groupby("Ticker"):
        g = grp.sort_values("Date")
        closes = g["Close"].values.astype(np.float64)
        dates = g["Date"].values
        n = len(closes)

        if n < subsequence_length * 2 + 1:
            logger.info("MatrixProfile: skipping %s (insufficient data)", ticker)
            continue

        raw = _left_profile(closes, subsequence_length)
        z = causal_robust_z(raw, valid_from=CAUSAL_WARMUP_BARS)
        scores = z_to_unit(z)

        for i in range(n):
            results.append(
                {
                    "Ticker": ticker,
                    "Date": dates[i],
                    "mp_score": round(float(scores[i]), 6),
                    "mp_z": round(float(z[i]), 4),
                    "mp_anomaly": bool(z[i] > z_threshold),
                }
            )

    return pd.DataFrame(results)
