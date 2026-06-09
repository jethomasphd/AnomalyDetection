"""Shared causal-scoring utilities.

THE invariant of the v2 detection regime lives here: every quantity computed
for bar t may use bars [0..t] and nothing later. Standardization is done
against a TRAILING window of the raw score's own history, using robust
statistics (median / MAD) so a single extreme day cannot poison its own
baseline, and so slow drift in a raw stream's level does not masquerade as
anomaly.

Because scores are prefix-invariant — appending future bars never changes
the score of an earlier bar — the historical backfill is a true walk-forward
simulation: the verdict recorded for a past bar is exactly the verdict the
system would have produced had it run that evening. test_causality.py
enforces this property for every detector.
"""

import numpy as np
import pandas as pd

from ..config import CAUSAL_WARMUP_BARS, Z_SCORE_CAP

# 90th percentile of the standard normal: converts (q90 - q50) into sigma.
_Q90_TO_SIGMA = 1.2816

# Trailing window for robust standardization of raw score streams, and the
# minimum number of observations required before a z can be produced.
ROBUST_Z_WINDOW = 120
ROBUST_Z_MIN_HISTORY = 20


def causal_robust_z(
    raw: np.ndarray,
    valid_from: int = CAUSAL_WARMUP_BARS,
    window: int = ROBUST_Z_WINDOW,
) -> np.ndarray:
    """Standardize raw[t] against the median/MAD of its trailing history.

    For each t >= valid_from + ROBUST_Z_MIN_HISTORY:
        hist  = raw[max(valid_from, t - window + 1) .. t]  (past + present)
        sigma = (q90(hist) - q50(hist)) / 1.2816
        z[t]  = max(0, (raw[t] - q50(hist)) / sigma)

    The spread estimate uses the upper quantile gap rather than the MAD
    because these streams are one-sided and heavy-tailed ("bigger =
    weirder"); the MAD of such a stream understates its spread and
    over-flags. 1.2816 is the 90th percentile of the standard normal, so
    sigma reads in familiar units.

    Bars before the start get z = 0 — the detector is still learning what
    normal looks like and is not allowed to flag. The denominator is floored
    at a fraction of the median (and an absolute epsilon) so near-degenerate
    score streams (e.g. an almost-constant series) cannot manufacture huge
    z values out of numerical dust.
    """
    n = len(raw)
    z = np.zeros(n, dtype=float)
    start = valid_from + ROBUST_Z_MIN_HISTORY
    if n <= start:
        return z

    for t in range(start, n):
        hist = raw[max(valid_from, t - window + 1) : t + 1]
        q50, q90 = np.quantile(hist, [0.5, 0.9])
        denom = max((q90 - q50) / _Q90_TO_SIGMA, 0.05 * abs(q50), 1e-9)
        z[t] = max(0.0, (raw[t] - q50) / denom)
    return z


def z_to_unit(z: np.ndarray | float, cap: float = Z_SCORE_CAP) -> np.ndarray | float:
    """Map a (non-negative) z value onto [0, 1]: 0.5 = 2 sigma, 1.0 = cap sigma.

    A fixed, documented mapping — NOT a per-ticker max-normalization — so a
    score of 0.7 means the same thing for every ticker on every day.
    """
    return np.clip(np.asarray(z, dtype=float), 0.0, cap) / cap


def trailing_std(values: np.ndarray, window: int, min_periods: int) -> np.ndarray:
    """Trailing standard deviation of values, EXCLUDING the current bar.

    std[t] is computed over values[max(0, t-window) .. t-1]. Excluding bar t
    keeps "today's surprise" from damping its own yardstick. Bars with fewer
    than `min_periods` past observations get NaN.
    """
    s = pd.Series(values)
    return s.rolling(window, min_periods=min_periods).std(ddof=1).shift(1).to_numpy()
