"""Custom Ensemble anomaly detection for email click data.

Combines three complementary approaches:
  1. Z-Score (40%) — raw statistical outlier detection on click counts
  2. Seasonal Decomposition (30%) — residual after removing trend + 7-day seasonality
  3. Isolation Forest (30%) — ML-based outlier detection on click features

Plain-English: "Do multiple independent methods agree something is unusual?"
"""

import logging

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.ensemble import IsolationForest
from statsmodels.tsa.seasonal import seasonal_decompose

from ..config import ENSEMBLE_WEIGHTS, SENSITIVITY_PRESETS

logger = logging.getLogger(__name__)


def _zscore_scores(clicks: np.ndarray, window: int = 30) -> np.ndarray:
    """Rolling z-score of click counts."""
    scores = np.zeros(len(clicks))
    for i in range(window, len(clicks)):
        segment = clicks[i - window : i]
        mu, sigma = segment.mean(), segment.std()
        if sigma > 0:
            scores[i] = abs((clicks[i] - mu) / sigma)
    return scores


def _seasonal_scores(clicks: np.ndarray, period: int = 7) -> np.ndarray:
    """Residual magnitude from STL decomposition (period = 7 days for weekly cycle)."""
    scores = np.zeros(len(clicks))
    if len(clicks) < period * 4:
        return scores
    try:
        series = pd.Series(clicks)
        result = seasonal_decompose(series, model="additive", period=period, extrapolate_trend="freq")
        residuals = np.abs(result.resid.values)
        residuals = np.nan_to_num(residuals, nan=0.0)
        rmax = residuals.max()
        if rmax > 0:
            scores = residuals / rmax
    except Exception as exc:
        logger.debug("Seasonal decomposition failed: %s", exc)
    return scores


def _isolation_forest_scores(clicks: np.ndarray, changes: np.ndarray, volatility: np.ndarray) -> np.ndarray:
    """Isolation Forest anomaly scores using click features."""
    scores = np.zeros(len(clicks))
    features = np.column_stack([clicks, changes, volatility])
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
    """Run ensemble anomaly detection on each domain.

    Returns a DataFrame with columns:
        Domain, Date, ensemble_score, ensemble_anomaly (bool),
        zscore_component, seasonal_component, iforest_component
    """
    preset = SENSITIVITY_PRESETS[sensitivity]
    results = []

    for domain, grp in df.groupby("Domain"):
        g = grp.sort_values("Date").copy()
        clicks = g["Clicks"].values.astype(float)
        dates = g["Date"].values

        changes = g["click_change"].values.astype(float) if "click_change" in g.columns else np.diff(clicks, prepend=clicks[0]) / np.maximum(clicks, 1e-10)
        vol = g["volatility_20d"].values.astype(float) if "volatility_20d" in g.columns else np.zeros(len(clicks))

        z_scores = _zscore_scores(clicks)
        s_scores = _seasonal_scores(clicks)
        i_scores = _isolation_forest_scores(clicks, changes, vol)

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

        for i in range(len(clicks)):
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
