"""Statistical Ensemble anomaly detection for Google Postmaster spam rate data.

"GET ON UP"

Three independent statistical tests each look at the spam rate from a
different angle. When they independently agree something is unusual,
that's a strong signal. Like getting three different doctors' opinions.

  1. Z-Score (40%)  — Is the spam rate far from its recent average?
  2. Seasonal Decomposition (30%) — After removing weekly patterns,
     is there unexplained behavior left over?
  3. Isolation Forest (30%) — Does this combination of spam rate,
     change rate, and volatility look like an outlier?

Plain-English: "Do three independent check-ups agree something is off?"
"""

import logging

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from statsmodels.tsa.seasonal import seasonal_decompose

from ..config import ENSEMBLE_WEIGHTS, SENSITIVITY_PRESETS

logger = logging.getLogger(__name__)


def _zscore_scores(values: np.ndarray, window: int = 30) -> np.ndarray:
    """Rolling z-score of spam rate values."""
    scores = np.zeros(len(values))
    for i in range(window, len(values)):
        segment = values[i - window : i]
        mu, sigma = segment.mean(), segment.std()
        if sigma > 0:
            scores[i] = abs((values[i] - mu) / sigma)
    return scores


def _seasonal_scores(values: np.ndarray, period: int = 7) -> np.ndarray:
    """Residual magnitude from STL decomposition (period=7 for weekly cycle)."""
    scores = np.zeros(len(values))
    if len(values) < period * 4:
        return scores
    try:
        series = pd.Series(values)
        result = seasonal_decompose(series, model="additive", period=period, extrapolate_trend="freq")
        residuals = np.abs(result.resid.values)
        residuals = np.nan_to_num(residuals, nan=0.0)
        rmax = residuals.max()
        if rmax > 0:
            scores = residuals / rmax
    except Exception as exc:
        logger.debug("Seasonal decomposition failed: %s", exc)
    return scores


def _isolation_forest_scores(
    values: np.ndarray,
    changes: np.ndarray,
    volatility: np.ndarray,
) -> np.ndarray:
    """Isolation Forest anomaly scores using spam rate features."""
    scores = np.zeros(len(values))
    features = np.column_stack([values, changes, volatility])
    valid_mask = ~np.isnan(features).any(axis=1)

    if valid_mask.sum() < 30:
        return scores

    X_valid = features[valid_mask]
    clf = IsolationForest(contamination=0.05, random_state=42, n_estimators=100)
    clf.fit(X_valid)

    raw = -clf.score_samples(X_valid)
    rmin, rmax = raw.min(), raw.max()
    if rmax > rmin:
        normed = (raw - rmin) / (rmax - rmin)
    else:
        normed = np.zeros(len(raw))

    scores[valid_mask] = normed
    return scores


def detect(
    df: pd.DataFrame,
    sensitivity: str = "medium",
) -> pd.DataFrame:
    """Run ensemble anomaly detection on each domain's spam rate.

    Returns a DataFrame with columns:
        Domain, Date, ensemble_score, ensemble_anomaly (bool),
        zscore_component, seasonal_component, iforest_component
    """
    preset = SENSITIVITY_PRESETS[sensitivity]
    results = []

    for domain, grp in df.groupby("Domain"):
        g = grp.sort_values("Date").copy()
        spam_rate = g["SpamRate"].values.astype(float)
        dates = g["Date"].values

        changes = g["spam_rate_change"].values.astype(float) if "spam_rate_change" in g.columns else np.zeros(len(spam_rate))
        vol = g["volatility_7d"].values.astype(float) if "volatility_7d" in g.columns else np.zeros(len(spam_rate))

        z_scores = _zscore_scores(spam_rate)
        s_scores = _seasonal_scores(spam_rate)
        i_scores = _isolation_forest_scores(spam_rate, changes, vol)

        # Normalize each to [0, 1]
        for arr in [z_scores, s_scores, i_scores]:
            amax = arr.max()
            if amax > 0:
                arr[:] = arr / amax

        w = ENSEMBLE_WEIGHTS
        combined = (
            w["zscore"] * z_scores
            + w["seasonal"] * s_scores
            + w["isolation_forest"] * i_scores
        )

        threshold = np.percentile(combined[combined > 0], preset["percentile"]) if np.any(combined > 0) else 0

        for i in range(len(spam_rate)):
            results.append(
                {
                    "Domain": domain,
                    "Date": dates[i],
                    "ensemble_score": round(float(combined[i]), 6),
                    "ensemble_anomaly": bool(combined[i] > threshold) if threshold > 0 else False,
                    "zscore_component": round(float(z_scores[i]), 4),
                    "seasonal_component": round(float(s_scores[i]), 4),
                    "iforest_component": round(float(i_scores[i]), 4),
                }
            )

    return pd.DataFrame(results)
